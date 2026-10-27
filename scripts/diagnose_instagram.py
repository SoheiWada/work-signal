#!/usr/bin/env python3
"""Read-only Instagram API diagnostics. No posting and no ledger mutation."""
import json, os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
IDS = ('20261027-arcgis-server-sql-injection-cve-2026-10757', '20261027-oracle-deep-trust-ai-architecture')

def get(path, token):
    url = 'https://graph.instagram.com/v25.0/' + path
    req = Request(url, headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json'})
    try:
        with urlopen(req, timeout=20) as response:
            return json.load(response)
    except HTTPError as e:
        # Never print raw Meta responses or tokens; code and stage only.
        print('IG API HTTP', e.code, 'for', path.split('?')[0]); return None
    except (URLError, TimeoutError, ValueError) as e:
        print('IG API transport error', type(e).__name__); return None

def main():
    token=os.environ.get('INSTAGRAM_ACCESS_TOKEN','')
    uid=os.environ.get('INSTAGRAM_USER_ID','')
    if not token or not uid.isdigit():
        print('Instagram credentials unavailable');return
    ledger=json.loads((ROOT/'.github/social-post-ledger.json').read_text())
    for article_id in IDS:
        state=ledger.get(article_id,{})
        print('Review', article_id, {k:state.get(k,{}).get('status') for k in ('instagram','instagram_story')})
    profile=get('me?'+urlencode({'fields':'user_id,username,account_type'}),token)
    if profile: print('Account verified:', profile.get('username')=='work_signal_japan', 'type:',profile.get('account_type'))
    media=get(uid+'/media?'+urlencode({'fields':'id,caption,media_type,timestamp,permalink','limit':'100'}),token)
    if not isinstance(media,dict):return
    items=media.get('data',[])
    print('Instagram media inspected:',len(items))
    for article_id in IDS:
        hits=[m for m in items if article_id in (m.get('caption') or '')]
        print('Article ID matches in recent media:',article_id,len(hits))
    print('Read-only diagnostic completed; no posts attempted')

if __name__=='__main__':main()
