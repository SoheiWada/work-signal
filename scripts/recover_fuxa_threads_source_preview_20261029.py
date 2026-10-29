#!/usr/bin/env python3
"""Single owner-requested, fail-closed recovery of FUXA's verified absent Threads post.

Alternative link-preview attachment is the official Cisco Talos primary source,
while the visible post keeps the WORK SIGNAL article URL and source URL.
This script creates at most one Meta post; it must never automatically retry.
"""
import base64
import json
import os
import sys
import time
from urllib.request import Request, urlopen

import publish_social as social
from audit_social_delivery import collect, matches

ID = "20261029-fuxa-nodered-auth-bypass-rce"
REVIEW = "fuxa-read-only-audit-40882728528-source-preview-20261029"
REPO = os.environ["GITHUB_REPOSITORY"]
TOKEN = os.environ["GITHUB_TOKEN"]
META_TOKEN = os.environ["THREADS_ACCESS_TOKEN"]
USER = os.environ["THREADS_USER_ID"]


def visible(article, attempts=1):
    found = []
    for i in range(attempts):
        media, complete = collect(social.THREADS_API, USER + "/threads", META_TOKEN,
                                  "id,text,timestamp,permalink", pages=8)
        if not complete or not media:
            raise RuntimeError("STOP: Threads timeline incomplete")
        found = matches(article, "threads", media)
        if len(found) != 0:
            return found
        if i < attempts-1:
            time.sleep(5)
    return found


def write_exact(ledger, old, state):
    rows, sha = ledger.read()
    current = rows.get(ID, {}).get("threads")
    if current != old:
        raise RuntimeError("STOP: Concurrent publication ledger update")
    rows[ID]["threads"] = state
    payload = {
        "message": "Owner-reviewed FUXA Threads canonical/source card recovery",
        "content": base64.b64encode((json.dumps(rows, ensure_ascii=False, indent=2) + "\n").encode()).decode(),
        "sha": sha, "branch": "main",
    }
    req = Request(ledger.url, method="PUT", data=json.dumps(payload).encode(),
                  headers={"Authorization": "Bearer " + TOKEN,
                           "Accept": "application/vnd.github+json",
                           "Content-Type": "application/json"})
    with urlopen(req, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError("STOP: Ledger atomic compare-and-swap failed")


def main():
    social.verify_account(social.THREADS_API, META_TOKEN, USER)
    feed = json.loads((social.ROOT / "data/articles.json").read_text())
    article = next((a for a in feed if a.get("id") == ID), None)
    if not article or article.get("social_publish") is not True or article.get("status") != "published":
        raise RuntimeError("STOP: No explicit owner approval")
    if "threads" not in social.requested_platforms(article):
        raise RuntimeError("STOP: Threads not an approved platform")
    if article.get("source_url") != "https://www.talosintelligence.com/vulnerability_reports/TALOS-2026-2419":
        raise RuntimeError("STOP: Primary-source URL changed")
    social.verify_live(social.article_url(article), attempts=2)
    with urlopen(Request(article["source_url"],headers={"User-Agent":"WORK-SIGNAL-Audit/1.0"}),timeout=25) as response:
        if response.status != 200:
            raise RuntimeError("STOP: Original primary source unavailable")
    ledger = social.GithubLedger(REPO, TOKEN)
    rows, _ = ledger.read()
    old = rows.get(ID, {}).get("threads", {})
    if old.get("status") != "needs_review" or old.get("recovery_review_id"):
        raise RuntimeError("STOP: Unexpected ledger state")
    if visible(article):
        raise RuntimeError("STOP: Found existing Threads post; do not publish")
    text = social.threads_text(article)
    if social.article_url(article) not in text or not text.endswith(article["source_url"]):
        raise RuntimeError("STOP: Owner-approved Threads post copy invalid")
    claimed = {
        "status": "attempting", "updated_at": social.now(), "stage": "publish_requested",
        "recovery_review_id": REVIEW, "previous_attempt": old,
    }
    write_exact(ledger, old, claimed)
    try:
        social.request_json(social.THREADS_API + "/" + USER + "/threads",method="POST",
                            token=META_TOKEN,data={
                                "media_type": "TEXT", "text": text,
                                "link_attachment": article["source_url"],
                                "auto_publish_text": "true"})
    except Exception as exc:
        error = exc.metadata() if isinstance(exc, social.MetaAPIError) else {"type":type(exc).__name__}
        try:
            found = visible(article, attempts=3)
        except Exception:
            found = []
        if len(found) == 1:
            result = found[0]
        else:
            blocked = dict(claimed,status="needs_review",updated_at=social.now(),
                           reason="source_link_preview_result_unconfirmed",error=error)
            write_exact(ledger, claimed, blocked)
            print("RECOVERY_HELD", ID, json.dumps(error))
            return 2
    else:
        found = visible(article,attempts=5)
        if len(found) != 1:
            blocked = dict(claimed,status="needs_review",updated_at=social.now(),
                           reason="source_link_preview_not_verified")
            write_exact(ledger,claimed,blocked)
            print("RECOVERY_HELD",ID,"No unique confirmed live post")
            return 2
        result = found[0]
    success = dict(claimed,status="published",updated_at=social.now(),
                   remote_id=str(result["id"]),permalink=result.get("permalink",""))
    write_exact(ledger,claimed,success)
    print("RECOVERED_FUXA",ID,success["remote_id"],success["permalink"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
