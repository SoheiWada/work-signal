#!/usr/bin/env python3
"""One-time Threads-only delivery of five approved, never-attempted articles."""
import json
import os
import sys
import publish_social as social
from audit_social_delivery import collect, matches

IDS = (
 "20261028-legora-ai-nda-legal-workflow",
 "20261028-enveda-claude-pharma-quality-record-review",
 "20261028-bis-central-banks-ai-readiness-governance-survey",
 "20261028-oracle-google-tpu-multichip-ai-cloud",
 "20261028-skhynix-q3-ai-memory-supply-2030",
)
def main():
 token=os.environ["THREADS_ACCESS_TOKEN"]
 uid=os.environ["THREADS_USER_ID"]
 social.verify_account(social.THREADS_API,token,uid)
 ledger=social.GithubLedger(os.environ["GITHUB_REPOSITORY"],os.environ["GITHUB_TOKEN"])
 articles={a["id"]:a for a in social.approved_articles(json.loads((social.ROOT/"data/articles.json").read_text()))}
 for aid in IDS:
  a=articles[aid]
  if "threads" not in social.requested_platforms(a):
   raise RuntimeError("Threads not authorized for "+aid)
  rows,_=ledger.read()
  if "threads" in rows.get(aid,{}):
   print("SKIP: existing Threads ledger entry",aid)
   continue
  social.verify_live(social.article_url(a),attempts=1)
  posts,complete=collect(social.THREADS_API,uid+"/threads",token,"id,text,timestamp,permalink",pages=8)
  if not complete or not posts:
   raise RuntimeError("STOP: Threads history incomplete")
  if matches(a,"threads",posts):
   raise RuntimeError("STOP: live post already exists for "+aid)
  ledger.record(aid,"threads","attempting")
  try:
   remote=social.publish_threads(social.threads_text(a),token,uid,progress=lambda stage,cid:ledger.progress(aid,"threads",stage,cid))
   ledger.record(aid,"threads","published",remote_id=remote)
   print("PUBLISHED",aid,remote)
  except Exception as exc:
   try:
    ledger.record(aid,"threads","needs_review")
   except Exception:
    print("STOP: manual ledger reconciliation required",file=sys.stderr)
   raise RuntimeError("STOP: ambiguous Threads outcome for "+aid) from exc
 return 0
if __name__=="__main__":
 sys.exit(main())
