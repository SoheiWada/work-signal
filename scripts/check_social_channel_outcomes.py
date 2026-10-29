#!/usr/bin/env python3
"""Check audited per-platform outcomes without hiding genuine publication failures.

The known Instagram FEED 4/2207051 protective hold is reported as WARNING,
never as a successful feed post. Threads and Stories must be fully published
for this separate channel-health gate to pass. All other API errors fail.
"""
import json
import os
import sys
from pathlib import Path
try:
    from . import publish_social as social
except ImportError:
    import publish_social as social

KNOWN_FEED_HOLD_MESSAGES = frozenset({
    "Requested Instagram media are action-blocked (4/2207051); no further writes to those media",
    "instagram protective action block 4/2207051; delivery held pending review",
})


def evaluate(summary, feed, ledger):
    if not isinstance(summary, dict) or not isinstance(summary.get("articles"), list):
        return False, "Delivery report missing/invalid", {}
    items = {x.get("id"): x.get("platforms", {}) for x in summary["articles"]
             if isinstance(x, dict)}
    approved = social.approved_articles(feed)
    active_feed_hold = any(social.active_instagram_action_block(
        entry.get("instagram", {})) for entry in ledger.values()
        if isinstance(entry, dict))
    counters = {"threads":0, "instagram_story":0, "feed_published":0,
                "feed_held":0, "feed_pending_other":0}
    errors = []
    for article in approved:
        aid = article["id"]
        status = items.get(aid)
        if status is None:
            errors.append("Missing delivery evidence for " + aid)
            continue
        selected = social.requested_platforms(article)
        for ch in ("threads", "instagram_story"):
            if ch not in selected:
                continue
            if status.get(ch) != "published":
                errors.append("Incomplete " + ch + " " + aid)
            else:
                counters[ch] += 1
        if "instagram" not in selected:
            continue
        state = status.get("instagram", "pending")
        if state == "published":
            counters["feed_published"] += 1
        elif active_feed_hold and (state == "pending" or (
            state == "needs_review" and social.active_instagram_action_block(
                ledger.get(aid, {}).get("instagram", {})))):
            counters["feed_held"] += 1
        else:
            counters["feed_pending_other"] += 1
            errors.append("Non-blocked Instagram feed incomplete " + aid)
    failures = summary.get("failures", [])
    if not isinstance(failures, list):
        errors.append("Unparseable publication failures")
    else:
        for failure in failures:
            if failure not in KNOWN_FEED_HOLD_MESSAGES or not active_feed_hold:
                errors.append("Unexpected publication failure: " + str(failure)[:160])
    return not errors, "; ".join(errors[:6]), counters


def main():
    report_path = social.ROOT / "social-delivery-status.json"
    if not report_path.is_file():
        print("CHANNEL_HEALTH_FAIL: Publisher did not create a delivery report")
        return 1
    summary = json.loads(report_path.read_text())
    feed = json.loads((social.ROOT / "data/articles.json").read_text())
    ledger = social.GithubLedger(os.environ["GITHUB_REPOSITORY"],
                                 os.environ["GITHUB_TOKEN"])
    rows, _ = ledger.read()
    ok, error, counts = evaluate(summary, feed, rows)
    print("CHANNEL_HEALTH", json.dumps({
        "threads":counts.get("threads",0),"stories":counts.get("instagram_story",0),
        "instagram_feed_published":counts.get("feed_published",0),
        "instagram_feed_on_protective_hold":counts.get("feed_held",0),
        "other_incomplete_feed":counts.get("feed_pending_other",0),
        "result":"success_with_explicit_feed_hold" if ok and counts.get("feed_held") else
                 ("success" if ok else "failure"),
        "error":error
    }))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:
            f.write("\n## Channel-specific verified delivery\n\n"
                    + "Threads published: " + str(counts.get("threads",0)) +
                    "; Stories published: " + str(counts.get("instagram_story",0)) +
                    "; Instagram feed published: " + str(counts.get("feed_published",0)) +
                    "; Instagram feed **HELD**: " + str(counts.get("feed_held",0)) +
                    "\n\nInstagram feed held by Meta protective action 4/2207051: **NOT POSTED**. "
                    "This is explicitly not a successful feed delivery.\n\n")
    if not ok:
        print("CHANNEL_HEALTH_FAIL", error, file=sys.stderr)
        return 1
    if counts.get("feed_held"):
        print("::warning::Instagram FEED is intentionally held by Meta 4/2207051; Threads and Stories are verified published")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
