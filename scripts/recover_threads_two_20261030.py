#!/usr/bin/env python3
"""One-time owner-authorized recovery of two uncertain Threads posts.

Safety gates:
- inspect the complete recent Threads timeline, including a known positive control;
- reconcile existing live posts instead of posting duplicates;
- use an exclusive GitHub ledger claim for a verified-absent post;
- issue at most one Meta write per article; ambiguous results stay needs_review;
- never operate on Instagram, unapproved articles, or other Threads posts.
"""
import base64
import json
import os
import sys
import time
from urllib.request import Request, urlopen

import publish_social as social
from audit_social_delivery import collect, matches

IDS = (
    "20261030-openai-model-spec-five-values-human-intent",
    "20261030-consumer-confidence-35-inflation-expectations",
)
CONTROL_ID = "20261030-chrome-156-mediastream-critical-update"
REVIEW_ID = "owner-approved-threads-two-20261030"
REPO = os.environ["GITHUB_REPOSITORY"]
TOKEN = os.environ["GITHUB_TOKEN"]
META_TOKEN = os.environ["THREADS_ACCESS_TOKEN"]
USER = os.environ["THREADS_USER_ID"]


def update_entry(ledger, aid, expected, replacement, reason):
    """Compare-and-swap the one Threads entry; never modify another platform."""
    rows, sha = ledger.read()
    old = rows.get(aid, {}).get("threads")
    if old != expected or old.get("status") != "needs_review":
        raise RuntimeError("STOP: Threads ledger state changed for " + aid)
    rows[aid]["threads"] = replacement
    body = {
        "message": reason + " " + aid,
        "content": base64.b64encode(
            (json.dumps(rows, ensure_ascii=False, indent=2) + "\n").encode()
        ).decode(),
        "sha": sha, "branch": "main",
    }
    request = Request(
        ledger.url, method="PUT", data=json.dumps(body).encode(),
        headers={
            "Authorization": "Bearer " + TOKEN,
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "WORK-SIGNAL-Social/1.0",
        },
    )
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError("STOP: Ledger claim failed")


def live_history(articles, ledger):
    posts, complete = collect(
        social.THREADS_API, USER + "/threads", META_TOKEN,
        "id,text,timestamp,permalink", pages=8,
    )
    control = articles[CONTROL_ID]
    rows, _ = ledger.read()
    if rows.get(CONTROL_ID, {}).get("threads", {}).get("status") != "published":
        raise RuntimeError("STOP: Published positive control missing from ledger")
    if not complete or not posts or not matches(control, "threads", posts):
        raise RuntimeError("STOP: Threads history incomplete or positive control absent")
    return posts


def main():
    if REPO != "SoheiWada/work-signal":
        raise RuntimeError("STOP: Wrong repository")
    social.verify_account(social.THREADS_API, META_TOKEN, USER)
    articles = {
        a["id"]: a for a in json.loads((social.ROOT / "data/articles.json").read_text())
    }
    ledger = social.GithubLedger(REPO, TOKEN)
    count, reconciled = 0, 0
    for aid in IDS:
        article = articles[aid]
        if article not in social.approved_articles([article]) or (
            "threads" not in social.requested_platforms(article)
        ):
            raise RuntimeError("STOP: Missing explicit publication approval " + aid)
        canonical = social.article_url(article)
        text = social.threads_text(article)
        if canonical not in text or not text.endswith(article["source_url"]):
            raise RuntimeError("STOP: Approved copy invalid")
        social.verify_live(canonical, attempts=1)
        rows, _ = ledger.read()
        prior = rows.get(aid, {}).get("threads", {})
        if prior.get("status") == "published":
            print("ALREADY_PUBLISHED", aid, prior.get("permalink", ""))
            continue
        if prior.get("status") != "needs_review":
            print("STOP_STATE_UNCERTAIN", aid, prior.get("status", "missing"))
            return 2
        found = matches(article, "threads", live_history(articles, ledger))
        if len(found) > 1:
            print("STOP_DUPLICATES", aid, file=sys.stderr)
            return 2
        if len(found) == 1:
            post = found[0]
            update_entry(ledger, aid, prior, {
                "status": "published", "updated_at": social.now(),
                "remote_id": str(post["id"]),
                "permalink": post.get("permalink", ""),
                "recovery_review_id": REVIEW_ID,
            }, "Reconcile existing live Threads post")
            print("RECONCILED_EXISTING", aid, post["id"], post.get("permalink", ""))
            reconciled += 1
            continue
        update_entry(ledger, aid, prior, {
            "status": "attempting", "updated_at": social.now(),
            "recovery_review_id": REVIEW_ID, "previous_attempt": prior,
        }, "Claim once for verified-absent Threads post")
        try:
            # One Meta write only. An explicit canonical link card avoids using
            # the PDF/HTTP-error primary-source URL as a preview attachment.
            social.publish_threads(
                text, META_TOKEN, USER, link_attachment=canonical,
                progress=lambda stage, container: ledger.progress(
                    aid, "threads", stage, container
                ),
            )
        except Exception as exc:
            # A failed response does not prove publication failed. Never resend.
            try:
                found = matches(article, "threads", live_history(articles, ledger))
            except Exception:
                found = []
            if len(found) != 1:
                error = ({"error": exc.metadata()} if isinstance(exc, social.MetaAPIError)
                         else {"reason": "Meta response uncertain; no automatic retry"})
                ledger.record(aid, "threads", "needs_review", **error)
                print("NEEDS_REVIEW", aid, type(exc).__name__, file=sys.stderr)
                return 2
        for attempt in range(4):
            found = matches(article, "threads", live_history(articles, ledger))
            if len(found) == 1:
                post = found[0]
                ledger.record(aid, "threads", "published",
                              remote_id=str(post["id"]),
                              permalink=post.get("permalink", ""))
                print("PUBLISHED_VERIFIED", aid, post["id"], post.get("permalink", ""))
                count += 1
                break
            if len(found) > 1:
                print("STOP_DUPLICATES_AFTER_WRITE", aid, file=sys.stderr)
                return 2
            if attempt < 3:
                time.sleep(5)
        else:
            ledger.record(aid, "threads", "needs_review",
                          reason="Post result unconfirmed; do not retry")
            print("NEEDS_REVIEW", aid, "Post result unconfirmed", file=sys.stderr)
            return 2
    print("RECOVERY_SUMMARY", json.dumps({
        "verified_new": count, "reconciled_existing": reconciled, "targets": len(IDS)
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
