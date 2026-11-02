"""Durable approved-article backlog, bounded batches and read-only health reports.

Articles are delivery intentions; the shared ledger is the per-channel result.
Wake-up events carry no irreplaceable queue data. Never rearm uncertain writes.
"""
import argparse
import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from datetime import datetime, timezone, timedelta
try:
    from . import publish_social as social
    from .select_scheduled_social import scheduled_ids
except ImportError:
    import publish_social as social
    from select_scheduled_social import scheduled_ids

BATCH_LIMIT = 5
MAX_CONTINUATIONS = 2


def batch_ids(feed, rows, scope="", clock=None):
    ready = set(scheduled_ids(feed, rows, clock))
    approved = social.approved_in_scope(feed, scope)
    # Preserve SECURITY WATCH priority, then oldest approved article first.
    ordered = sorted(enumerate(approved), key=lambda pair: (
        0 if pair[1].get("social_security_severity") else 1,
        pair[1]["published_at"], -pair[0]))
    return [a["id"] for _, a in ordered if a["id"] in ready][:BATCH_LIMIT]


def published_keys(rows, ids):
    return {(aid, kind) for aid in ids for kind in social.SOCIAL_PLATFORMS
            if rows.get(aid, {}).get(kind, {}).get("status") == "published"}


def continuation_ids(feed, before, after, ids, depth, clock=None):
    if not 0 <= depth < MAX_CONTINUATIONS:
        return []
    if not (published_keys(after, ids) - published_keys(before, ids)):
        return []  # No progress: do not loop on API failures or unverified absence.
    return batch_ids(feed, after, clock=clock)


def backlog_report(feed, rows, clock=None):
    clock = clock or datetime.now(timezone.utc)
    ready_ids = set(scheduled_ids(feed, rows, clock))
    blocked = {kind for history in rows.values() if isinstance(history, dict)
               for kind in ("instagram", "instagram_story")
               if isinstance(history.get(kind, {}), dict)
               and social.active_instagram_action_block(history.get(kind, {}))}
    counts = {kind: {key: 0 for key in (
        "published", "ready", "deferred", "needs_review", "attempting", "held", "review_required")}
              for kind in social.SOCIAL_PLATFORMS}
    outstanding = []
    for article in social.approved_articles(feed):
        aid = article["id"]
        history = rows.get(aid, {})
        invalid_history = False
        try:
            remaining = social.remaining_platforms(history, clock)
        except RuntimeError:
            remaining, invalid_history = [], True
        if not isinstance(history, dict):
            history = {}
        for kind in social.requested_platforms(article):
            entry = history.get(kind, {})
            invalid_entry = not isinstance(entry, dict)
            if invalid_entry:
                entry = {}
            status = entry.get("status", "pending")
            if invalid_entry or (invalid_history and status not in ("published", "needs_review", "attempting")):
                category = "review_required"
            elif status in ("published", "needs_review", "attempting"):
                category = status
            elif kind in blocked:
                category = "held"
            elif aid in ready_ids and kind in remaining:
                category = "ready"
            elif status == "deferred" and kind not in remaining:
                category = "deferred"
            else:
                category = "review_required"  # stale/expired: never silently drop
            counts[kind][category] += 1
            if category != "published":
                outstanding.append({"id": aid, "platform": kind, "state": category})
    return {"checked_at": clock.isoformat(), "counts": counts,
            "ready_article_ids": sorted(ready_ids), "outstanding": outstanding,
            "note": "Cumulative ledger evidence, not current visibility. Stories expire."}


def write_report(report):
    (social.ROOT / "social-backlog-status.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("GLOBAL_SOCIAL_BACKLOG", json.dumps(report["counts"]))
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as output:
            output.write("\n## Entire approved SNS backlog (separate from this batch)\n\n")
            output.write("| Channel | Published | Ready | Deferred | Needs review | Attempting | Protective hold | Freshness review required |\n")
            output.write("|---|---:|---:|---:|---:|---:|---:|---:|\n")
            for kind, counts in report["counts"].items():
                output.write("| " + kind + " | " + " | ".join(str(n) for n in counts.values()) + " |\n")
            output.write("\nPublished counts are cumulative ledger records. Held/review items are **not completed deliveries**. "
                         "See social-backlog-status.json for every outstanding article.\n")
            if "scheduler" in report:
                output.write("\nScheduled trigger: **" + report["scheduler"]["state"] + "** (independent of delivery).\n")
            if "publisher" in report:
                output.write("\nLatest successful publisher: " + report["publisher"]["state"] + "\n")
            if "delivery_health" in report:
                output.write("\nDelivery: **" + report["delivery_health"] + "**. Protective holds remain incomplete.\n")
            if "recovery" in report:
                output.write("\nRecovery wake-up: " + report["recovery"]["state"] + "\n")


def output_values(**values):
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            for key, value in values.items():
                output.write(key + "=" + str(value) + "\n")


def scheduler_health(runs, clock):
    if not runs:
        return {"state": "missing", "stale": True}
    last = datetime.fromisoformat(runs[0]["created_at"].replace("Z", "+00:00"))
    minutes = (clock - last).total_seconds() / 60
    return {"state": "stale" if minutes > 90 else "recent", "stale": minutes > 90,
            "last_created_at": last.isoformat(), "minutes_since_last_run": round(minutes, 1)}


def delivery_health(report):
    problems = [x for x in report["outstanding"] if x["state"] in
                ("ready", "needs_review", "attempting", "review_required")]
    if problems:
        return "needs_attention"
    return "waiting" if report["outstanding"] else "complete"


def recovery_decision(ready_ids, runs, clock):
    if not ready_ids:
        return {"state": "idle", "dispatch": False}
    if any(r.get("status") != "completed" for r in runs):
        return {"state": "publisher_active", "dispatch": False}
    if runs:
        last = datetime.fromisoformat(runs[0]["created_at"].replace("Z", "+00:00"))
        if (clock - last).total_seconds() < 600:
            return {"state": "cooldown", "dispatch": False}
    return {"state": "requested", "dispatch": True}


def dispatch_queue(endpoint, token):
    # GitHub dispatch expects JSON and returns an empty 204, unlike Meta APIs.
    request = Request(endpoint + "/actions/workflows/social-publish.yml/dispatches",
        data=json.dumps({"ref": "main", "inputs": {"wake_source": "monitor_recovery"}}).encode(),
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json", "User-Agent": "WORK-SIGNAL-Monitor/1.0"},
        method="POST")
    try:
        with urlopen(request, timeout=20) as response:
            if response.status != 204:
                raise RuntimeError("Queue dispatch response not acknowledged")
    except HTTPError as error:
        raise RuntimeError("Queue dispatch HTTP " + str(error.code)) from None
    except (URLError, TimeoutError):
        raise RuntimeError("Queue dispatch result unknown; canonical lock prevents duplicate writes") from None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "finish", "monitor"))
    args = parser.parse_args()
    feed = json.loads((social.ROOT / "data/articles.json").read_text())
    ledger = social.GithubLedger(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"])
    rows, _ = ledger.read()
    snapshot = social.ROOT / "social-queue-before.json"
    if args.action == "prepare":
        ids = batch_ids(feed, rows, os.getenv("REQUESTED_ARTICLE_IDS", ""))
        snapshot.write_text(json.dumps({"rows": rows, "ids": ids}))
        output_values(ready="true" if ids else "false", article_ids=",".join(ids))
        print("SAFE_QUEUE_BATCH", json.dumps(ids))
        return 0
    report = backlog_report(feed, rows)
    if args.action == "finish" and snapshot.is_file():
        initial = json.loads(snapshot.read_text())
        depth = int(os.getenv("CONTINUATION_DEPTH", "0"))
        ids = continuation_ids(feed, initial["rows"], rows, initial["ids"], depth)
        # An explicit manual scope cannot authorize unrelated recovery.
        if os.getenv("REQUESTED_ARTICLE_IDS"):
            ids = []
        output_values(continue_ready="true" if ids else "false", next_depth=depth + 1)
    if args.action == "monitor":
        endpoint = "https://api.github.com/repos/" + os.environ["GITHUB_REPOSITORY"]
        response = social.request_json(endpoint
            + "/actions/workflows/social-publish.yml/runs?branch=main&per_page=20",
            token=os.environ["GITHUB_TOKEN"])
        runs = response.get("workflow_runs")
        scheduled = social.request_json(endpoint
            + "/actions/workflows/social-publish.yml/runs?branch=main&event=schedule&per_page=1",
            token=os.environ["GITHUB_TOKEN"]).get("workflow_runs")
        if not isinstance(runs, list) or not isinstance(scheduled, list):
            raise RuntimeError("Publisher run history unavailable")
        clock = datetime.now(timezone.utc)
        report["scheduler"] = scheduler_health(scheduled, clock)
        report["publisher"] = scheduler_health([r for r in runs if r.get("conclusion") == "success"], clock)
        report["recovery"] = recovery_decision(report["ready_article_ids"], runs, clock)
        if report["recovery"]["dispatch"]:
            dispatch_queue(endpoint, os.environ["GITHUB_TOKEN"])
        if report["scheduler"]["stale"]:
            print("::warning::SCHEDULER_DELAY: scheduled trigger overdue; see delivery and recovery separately")
    report["delivery_health"] = delivery_health(report)
    write_report(report)
    print("DELIVERY_HEALTH", report["delivery_health"])
    if report["delivery_health"] == "needs_attention":
        print("::warning::DELIVERY_INCOMPLETE: inspect per-channel outstanding work and recovery")
        return 1 if args.action == "monitor" else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
