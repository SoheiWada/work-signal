"""Durable approved-article backlog, bounded batches and read-only health reports.

Articles are delivery intentions; the shared ledger is the per-channel result.
Wake-up events carry no irreplaceable queue data. Never rearm uncertain writes.
"""
import argparse
import json
import os
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
               if social.active_instagram_action_block(history.get(kind, {}))}
    counts = {kind: {key: 0 for key in (
        "published", "ready", "deferred", "needs_review", "attempting", "held", "review_required")}
              for kind in social.SOCIAL_PLATFORMS}
    outstanding = []
    for article in social.approved_articles(feed):
        aid = article["id"]
        history = rows.get(aid, {})
        remaining = social.remaining_platforms(history)
        for kind in social.requested_platforms(article):
            entry = history.get(kind, {})
            status = entry.get("status", "pending")
            if status in ("published", "needs_review", "attempting"):
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
                output.write("\nScheduler: " + report["scheduler"]["state"] + "\n")


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
        response = social.request_json("https://api.github.com/repos/" + os.environ["GITHUB_REPOSITORY"]
            + "/actions/workflows/social-publish.yml/runs?branch=main&event=schedule&per_page=1",
            token=os.environ["GITHUB_TOKEN"])
        report["scheduler"] = scheduler_health(response.get("workflow_runs", []), datetime.now(timezone.utc))
    write_report(report)
    problems = [x for x in report["outstanding"] if x["state"] in
                ("ready", "needs_review", "attempting", "review_required")]
    if problems or report.get("scheduler", {}).get("stale"):
        print("::warning::SNS backlog needs attention; inspect global report, not only batch success")
        return 1 if args.action == "monitor" else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
