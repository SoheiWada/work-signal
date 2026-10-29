#!/usr/bin/env python3
"""Owner-approved safe recovery for five verified-absent Threads posts.

Use Threads' documented one-request text publication with the canonical
article URL as an explicit link attachment, rather than the older UTM query
string as an automatically selected preview. No automatic retransmission:
a result uncertain after the POST remains needs_review.
"""
import base64
import json
import os
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import publish_social as social
from audit_social_delivery import collect, matches

IDS = (
    "20261029-nodejs-whisper-audio-path-command-injection",
    "20261029-graphql-scalars-phonenumber-redos",
    "20261029-systeminformation-windows-services-command-injection",
    "20261029-re2js-lookbehinds-quadratic-dos",
    "20261029-openai-servicenow-chatgpt-workflows",
)
REVIEW_ID = "threads-20261029-audit-40868867744-link-attachment-canonical"
REPO = os.environ["GITHUB_REPOSITORY"]
GH_TOKEN = os.environ["GITHUB_TOKEN"]
META_TOKEN = os.environ["THREADS_ACCESS_TOKEN"]
USER = os.environ["THREADS_USER_ID"]


def live_matches(article):
    posts, complete = collect(social.THREADS_API, USER + "/threads", META_TOKEN,
                              "id,text,timestamp,permalink", pages=8)
    if not complete or not posts:
        raise RuntimeError("STOP: Threads history incomplete")
    return matches(article, "threads", posts)


def claim(ledger, aid, expected):
    rows, sha = ledger.read()
    old = rows.get(aid, {}).get("threads", {})
    if old != expected or old.get("status") != "needs_review" or old.get("stage") != "publish_requested":
        raise RuntimeError("STOP: Concurrent claim or publication state changed")
    rows[aid]["threads"] = {
        "status": "attempting", "updated_at": social.now(),
        "recovery_review_id": REVIEW_ID,
        "stage": "publish_requested",
        "container_id": str(old["container_id"]),
        "previous_attempt": old,
    }
    payload = {"message": "Claim absent Threads post for audited canonical-link recovery " + aid,
               "content": base64.b64encode((json.dumps(rows, ensure_ascii=False, indent=2) +
                                             "\n").encode()).decode(),
               "sha": sha, "branch": "main"}
    req = Request(ledger.url, data=json.dumps(payload).encode(), method="PUT",
                  headers={"Authorization": "Bearer " + GH_TOKEN,
                           "Accept": "application/vnd.github+json",
                           "Content-Type": "application/json"})
    with urlopen(req, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError("STOP: Failed to obtain exclusive ledger claim")


def verify_post(article, attempts=5):
    for i in range(attempts):
        live = live_matches(article)
        if len(live) == 1:
            return live[0]
        if len(live) > 1:
            raise RuntimeError("STOP: Duplicate media detected, human review")
        if i + 1 < attempts:
            time.sleep(5)
    return None


def main():
    social.verify_account(social.THREADS_API, META_TOKEN, USER)
    ledger = social.GithubLedger(REPO, GH_TOKEN)
    index = {a["id"]: a for a in json.loads((social.ROOT / "data/articles.json").read_text())}
    completed = 0
    for aid in IDS:
        article = index[aid]
        if article.get("social_publish") is not True or "threads" not in social.requested_platforms(article):
            raise RuntimeError("STOP: No editorial permission to publish " + aid)
        rows, _ = ledger.read()
        old = rows.get(aid, {}).get("threads", {})
        if old.get("status") != "needs_review" or old.get("stage") != "publish_requested":
            print("SKIP_LEDGER_CHANGED", aid)
            continue
        original_container = str(old.get("container_id", ""))
        if not original_container.isdigit():
            raise RuntimeError("STOP: Missing original container")
        original = social.request_json(social.THREADS_API + "/" + original_container +
                                       "?fields=status,error_message", token=META_TOKEN)
        if original.get("status") != "FINISHED":
            raise RuntimeError("STOP: Original container is not safely unpublished")
        social.verify_live(social.article_url(article), attempts=1)
        live = live_matches(article)
        if live:
            raise RuntimeError("STOP: Already live (reconcile only), no new post for " + aid)
        # The previous URL with a long UTM query became an implicit link card.
        # Use the canonical article URL with an explicit link_attachment.
        approved_text = social.threads_text(article)
        tracked = social.tracked_article_url(article)
        canonical = social.article_url(article)
        safe_text = approved_text.replace(tracked, canonical)
        if canonical not in safe_text or not safe_text.endswith(article["source_url"]) or len(safe_text) > 500:
            raise RuntimeError("STOP: Approved copy validation failed")
        claim(ledger, aid, old)
        try:
            social.request_json(
                social.THREADS_API + "/" + USER + "/threads",
                method="POST", token=META_TOKEN,
                data={"media_type": "TEXT", "text": safe_text,
                      "link_attachment": canonical, "auto_publish_text": "true"})
        except Exception as exc:
            # Never repeat a write after an ambiguous transport/API result.
            try:
                found = verify_post(article, attempts=3)
                if found:
                    ledger.record(aid, "threads", "published",
                                  remote_id=str(found["id"]), permalink=found.get("permalink", ""))
                    print("RECOVERED_AFTER_AMBIGUOUS_RESPONSE", aid, found["id"])
                    completed += 1
                    continue
            except Exception:
                pass
            error = exc.metadata() if isinstance(exc, social.MetaAPIError) else {
                "error_type": type(exc).__name__}
            ledger.record(aid, "threads", "needs_review", error=error,
                          reason="Canonical-link autoprovision result unconfirmed")
            print("RECOVERY_HOLD", aid, json.dumps(error), file=sys.stderr)
            return 2
        found = verify_post(article, attempts=5)
        if not found:
            ledger.record(aid, "threads", "needs_review",
                          reason="Auto-publish response accepted but live post unconfirmed")
            print("RECOVERY_HOLD", aid, "live confirmation unavailable", file=sys.stderr)
            return 2
        ledger.record(aid, "threads", "published", remote_id=str(found["id"]),
                      permalink=found.get("permalink", ""))
        print("RECOVERED", aid, found["id"], found.get("permalink", ""))
        completed += 1
        time.sleep(9)
    print("RECOVERED_COUNT", completed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
