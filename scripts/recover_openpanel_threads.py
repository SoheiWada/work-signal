#!/usr/bin/env python3
"""One-time explicitly approved recovery. Never touches Instagram."""
import json,os,time,sys
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError
import publish_social as social
ID="20261027-openpanel-two-security-advisories"
def main():
    repo=os.environ["GITHUB_REPOSITORY"]
    token=os.environ["GITHUB_TOKEN"]
    ledger=social.GithubLedger(repo,token)
    rows,sha=ledger.read()
    state=rows.get(ID,{})
    if state.get("threads",{}).get("status")!="needs_review":
        print("STOP: Threads not in confirmed review state");return 0
    if any(state.get(p,{}).get("status")!="published" for p in ("instagram","instagram_story")):
        print("STOP: Instagram state inconsistent");return 1
    article=next(a for a in json.loads((social.ROOT/"data/articles.json").read_text()) if a["id"]==ID)
    if not article.get("social_publish"):raise RuntimeError("Not approved")
    text=social.threads_text(article)
    social.verify_account(social.THREADS_API,os.environ["THREADS_ACCESS_TOKEN"],os.environ["THREADS_USER_ID"])
    social.verify_live(social.article_url(article))
    # Manual confirmation by owner that Threads is absent; claim before API call.
    # Replace only Threads needs_review -> attempting, with optimistic SHA.
    state["threads"]={"status":"attempting","updated_at":social.now()}
    import base64
    body={"message":"Claim owner-approved OpenPanel Threads recovery","content":base64.b64encode((json.dumps(rows,ensure_ascii=False,indent=2)+"\n").encode()).decode(),"sha":sha,"branch":"main"}
    req=Request("https://api.github.com/repos/"+repo+"/contents/"+social.LEDGER,method="PUT",data=json.dumps(body).encode(),headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json","Content-Type":"application/json"})
    with urlopen(req,timeout=30) as response:
        if response.status!=200:raise RuntimeError("Claim failed")
    try:
        # Only one publish attempt, no automatic retry.
        remote=social.publish_threads(text,os.environ["THREADS_ACCESS_TOKEN"],os.environ["THREADS_USER_ID"])
        ledger.record(ID,"threads","published",remote_id=remote)
        print("PUBLISHED",ID,"threads",remote)
    except Exception as exc:
        ledger.record(ID,"threads","needs_review")
        print("NEEDS REVIEW",ID,type(exc).__name__,file=sys.stderr)
        return 1
    return 0
if __name__=="__main__":sys.exit(main())
