#!/usr/bin/env python3
"""One-time owner-confirmed missing social posts recovery, fail closed.\nRecheck Meta structured errors before any further remediation.\n"""
import base64,json,os,sys
from urllib.request import Request,urlopen
import publish_social as social
TARGETS={
"20261027-analytics-insights-stored-xss-cve-2026-111820":("threads",),
"20261027-qode-membership-auth-bypass-cve-2026-92885":("threads",),
"20261027-arcgis-server-sql-injection-cve-2026-10757":("instagram","instagram_story"),
"20261027-oracle-deep-trust-ai-architecture":("instagram","instagram_story"),
}
def claim(ledger,aid,kind):
    rows,sha=ledger.read()
    entry=rows.get(aid,{})
    if entry.get(kind,{}).get("status")!="needs_review":return False
    entry[kind]={"status":"attempting","updated_at":social.now()}
    payload={"message":"Claim owner-confirmed missing "+kind+" "+aid,"content":base64.b64encode((json.dumps(rows,ensure_ascii=False,indent=2)+"\n").encode()).decode(),"sha":sha,"branch":"main"}
    req=Request(ledger.url,method="PUT",data=json.dumps(payload).encode(),headers={"Authorization":"Bearer "+ledger.token,"Accept":"application/vnd.github+json","Content-Type":"application/json"})
    with urlopen(req,timeout=30) as res:
        if res.status!=200:raise RuntimeError("Claim failed")
    return True
def main():
    repo=os.environ["GITHUB_REPOSITORY"]
    ledger=social.GithubLedger(repo,os.environ["GITHUB_TOKEN"])
    articles={a["id"]:a for a in json.loads((social.ROOT/"data/articles.json").read_text())}
    social.verify_account(social.THREADS_API,os.environ["THREADS_ACCESS_TOKEN"],os.environ["THREADS_USER_ID"])
    social.verify_account(social.IG_API,os.environ["INSTAGRAM_ACCESS_TOKEN"],os.environ["INSTAGRAM_USER_ID"],instagram=True)
    # Confirm missing Instagram captions via current API before any write.
    ig=social.request_json(social.IG_API+"/"+os.environ["INSTAGRAM_USER_ID"]+"/media?fields=id,caption,media_type,timestamp,permalink&limit=100",token=os.environ["INSTAGRAM_ACCESS_TOKEN"])
    media=ig.get("data",[])
    failures=0
    for aid,kinds in TARGETS.items():
        a=articles[aid]
        if a.get("social_publish") is not True:raise RuntimeError("Article not approved")
        social.verify_live(social.article_url(a))
        for kind in kinds:
            if kind.startswith("instagram"):
                caption=a.get("social_instagram_caption","")
                if caption and any(caption[:60] in (m.get("caption") or "") for m in media):
                    print("STOP duplicate caption detected",aid,kind);continue
                if kind=="instagram":social.verify_live(social.image_url(a),jpg=True)
                else:social.verify_live(social.story_image_url(a),jpg=True)
            # Explicit owner reported missing posts; one attempt per item and medium.
            if not claim(ledger,aid,kind):
                print("SKIP state not needs_review",aid,kind);continue
            try:
                if kind=="threads":
                    remote=social.publish_threads(social.threads_text(a),os.environ["THREADS_ACCESS_TOKEN"],os.environ["THREADS_USER_ID"])
                elif kind=="instagram":
                    remote=social.publish_instagram(social.instagram_text(a),social.image_url(a),os.environ["INSTAGRAM_ACCESS_TOKEN"],os.environ["INSTAGRAM_USER_ID"])
                else:
                    remote=social.publish_instagram_story(social.story_image_url(a),os.environ["INSTAGRAM_ACCESS_TOKEN"],os.environ["INSTAGRAM_USER_ID"])
                ledger.record(aid,kind,"published",remote_id=remote)
                print("RECOVERED",aid,kind,remote)
            except Exception as exc:
                ledger.record(aid,kind,"needs_review")
                print("FAILED",aid,kind,str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__,file=sys.stderr)
                failures+=1
    return 1 if failures else 0
if __name__=="__main__":sys.exit(main())
