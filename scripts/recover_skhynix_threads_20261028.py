#!/usr/bin/env python3
"""One-time owner-approved recovery of exactly two absent Threads posts."""
import base64
import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import publish_social as social
from audit_social_delivery import collect, matches

IDS = ("20261028-skhynix-q3-ai-memory-supply-2030",)
REPO = os.environ["GITHUB_REPOSITORY"]
TOKEN = os.environ["GITHUB_TOKEN"]
THREADS_TOKEN = os.environ["THREADS_ACCESS_TOKEN"]
THREADS_USER = os.environ["THREADS_USER_ID"]
ledger = social.GithubLedger(REPO, TOKEN)

def claim(article_id):
    rows, sha = ledger.read()
    old = rows.get(article_id, {}).get("threads", {})
    if old.get("status") != "needs_review" or old.get("stage") != "publish_requested":
        raise RuntimeError("STOP: Threads ledger state changed; manual review required")
    rows[article_id]["threads"] = {
        "status": "attempting", "updated_at": social.now(),
        "recovery_review_id": "threads-verified-absent-20261028-run-40699015844",
        "previous_attempt": old,
    }
    body = {"message": "Claim verified absent Threads recovery " + article_id,
            "content": base64.b64encode((json.dumps(rows, ensure_ascii=False, indent=2)+"\n").encode()).decode(),
            "sha": sha, "branch": "main"}
    req = Request(ledger.url, method="PUT", data=json.dumps(body).encode(),
                  headers={"Authorization": "Bearer " + TOKEN,
                           "Accept": "application/vnd.github+json",
                           "Content-Type": "application/json"})
    with urlopen(req, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError("Failed to claim Threads recovery")

def main():
    social.verify_account(social.THREADS_API, THREADS_TOKEN, THREADS_USER)
    articles = json.loads((social.ROOT / "data/articles.json").read_text())
    index = {a["id"]: a for a in articles}
    for aid in IDS:
        a = index[aid]
        if a.get("social_publish") is not True or "threads" not in social.requested_platforms(a):
            raise RuntimeError("STOP: Article is not approved for Threads")
        social.verify_live(social.article_url(a), attempts=1)
        rows, _ = ledger.read()
        old = rows.get(aid, {}).get("threads", {})
        if old.get("status") != "needs_review" or old.get("stage") != "publish_requested":
            raise RuntimeError("STOP: Review status changed for " + aid)
        posts, complete = collect(social.THREADS_API, THREADS_USER + "/threads",
                                  THREADS_TOKEN, "id,text,timestamp,permalink", pages=8)
        if not complete or len(posts) == 0:
            raise RuntimeError("STOP: Threads history incomplete")
        if matches(a, "threads", posts):
            raise RuntimeError("STOP: Existing live Threads post found for " + aid)
        claim(aid)
        try:
            remote = social.publish_threads(social.threads_text(a), THREADS_TOKEN, THREADS_USER,
                                            progress=lambda stage, cid: ledger.progress(aid, "threads", stage, cid))
            ledger.record(aid, "threads", "published", remote_id=remote)
            print("RECOVERED", aid, remote)
        except Exception as exc:
            try:
                ledger.record(aid, "threads", "needs_review")
            except Exception:
                print("STOP: Manual ledger reconciliation required", file=sys.stderr)
            raise RuntimeError("STOP: Ambiguous Threads result for " + aid) from exc
    return 0

if __name__ == "__main__":
    sys.exit(main())
