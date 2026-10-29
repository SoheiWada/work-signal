#!/usr/bin/env python3
"""Read-only audit of five uncertain 2026-10-29 Threads publication requests.

Queries the entire available Threads timeline and the existing containers.
Never creates, publishes, or changes the social-post ledger.
"""
import json
import os
import sys
from pathlib import Path

import publish_social as social
from audit_social_delivery import collect, matches

IDS = (
    "20261029-openai-servicenow-chatgpt-workflows",
    "20261029-re2js-lookbehinds-quadratic-dos",
    "20261029-systeminformation-windows-services-command-injection",
    "20261029-graphql-scalars-phonenumber-redos",
    "20261029-nodejs-whisper-audio-path-command-injection",
)


def main():
    token = os.environ["THREADS_ACCESS_TOKEN"]
    user = os.environ["THREADS_USER_ID"]
    social.verify_account(social.THREADS_API, token, user)
    ledger = social.GithubLedger(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"])
    rows, _ = ledger.read()
    articles = {a["id"]: a for a in json.loads((social.ROOT / "data/articles.json").read_text())}
    posts, complete = collect(social.THREADS_API, user + "/threads", token,
                              "id,text,timestamp,permalink", pages=8)
    result = {"checked_at": social.now(), "complete": complete,
              "live_count": len(posts), "articles": []}
    for aid in IDS:
        article = articles[aid]
        entry = rows.get(aid, {}).get("threads", {})
        found = matches(article, "threads", posts)
        cid = entry.get("container_id")
        status, status_error = None, None
        if cid:
            try:
                status = social.request_json(social.THREADS_API + "/" + str(cid) +
                                             "?fields=status,error_message", token=token).get("status")
            except RuntimeError as exc:
                status_error = str(exc)
        row = {"id": aid, "approved": article.get("social_publish") is True,
               "ledger": entry.get("status"), "stage": entry.get("stage"),
               "container_id": cid, "container_status": status,
               "container_status_error": status_error,
               "live_matches": [{"id": x.get("id"), "permalink": x.get("permalink"),
                                 "timestamp": x.get("timestamp")} for x in found]}
        result["articles"].append(row)
        print("THREADS_CASE", json.dumps(row, ensure_ascii=False))
    (social.ROOT / "threads-five-audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("THREADS_AUDIT_SUMMARY", json.dumps({"complete": complete,
          "count": len(posts), "cases": len(result["articles"])}))
    return 0 if complete and len(posts) > 0 else 2


if __name__ == "__main__":
    sys.exit(main())
