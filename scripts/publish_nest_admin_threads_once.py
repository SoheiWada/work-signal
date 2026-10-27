#!/usr/bin/env python3
"""Publish only the explicitly approved nest-admin article to Threads once."""
import json,os,sys
import publish_social as social
ID="20261028-nest-admin-jwt-auth-bypass-cve-2026-117564"
def main():
    ledger=social.GithubLedger(os.environ["GITHUB_REPOSITORY"],os.environ["GITHUB_TOKEN"])
    rows,_=ledger.read()
    entry=rows.get(ID,{})
    social.remaining_platforms(entry)
    if entry.get("threads"):
        print("STOP: Threads state already exists; manual verification required")
        return 0
    article=next(a for a in json.loads((social.ROOT/"data/articles.json").read_text()) if a["id"]==ID)
    if article.get("status")!="published":raise RuntimeError("Article not approved")
    social.verify_account(social.THREADS_API,os.environ["THREADS_ACCESS_TOKEN"],os.environ["THREADS_USER_ID"])
    social.verify_live(social.article_url(article))
    ledger.record(ID,"threads","attempting")
    try:
        remote=social.publish_threads(social.threads_text(article),os.environ["THREADS_ACCESS_TOKEN"],os.environ["THREADS_USER_ID"])
        ledger.record(ID,"threads","published",remote_id=remote)
        print("PUBLISHED Threads",ID,remote)
    except Exception as exc:
        ledger.record(ID,"threads","needs_review")
        print("NEEDS_REVIEW Threads",ID,type(exc).__name__,file=sys.stderr)
        return 1
    return 0
if __name__=="__main__":sys.exit(main())
