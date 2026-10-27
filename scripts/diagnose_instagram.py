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
    quota=get(uid+'/content_publishing_limit?'+urlencode({'fields':'config,quota_usage'}),token)
    if quota:
        print('PUBLISHING_QUOTA',json.dumps({'quota_usage':quota.get('quota_usage'),'config':quota.get('config')},ensure_ascii=False))
    else:
        print('PUBLISHING_QUOTA unavailable')
    media=get(uid+'/media?'+urlencode({'fields':'id,caption,media_type,timestamp,permalink','limit':'100'}),token)
    if not isinstance(media,dict):return
    items=media.get('data',[])
    print('Instagram media inspected:',len(items))
    articles=json.loads((ROOT/'data/articles.json').read_text())
    index={a['id']:a for a in articles}
    targets=[k for k in ledger if k.startswith('20261027-') and any(t in k for t in ('arcgis-server','oracle-deep-trust','gridbox','analytics-insights','qode-membership','kirki'))]
    for article_id in targets:
        a=index.get(article_id,{})
        title=a.get('title','')
        caption=a.get('social_instagram_caption','')
        expected=(caption[:65] if caption else title[:65])
        matches=[m for m in items if expected and expected in (m.get('caption') or '')]
        state=ledger.get(article_id,{})
        print('VERIFY',article_id,'caption_matches',len(matches))
        for m in matches:
            print('MATCH',article_id,m.get('id'),m.get('media_type'),m.get('permalink',''))
        for kind in ('instagram','instagram_story'):
            remote=str(state.get(kind,{}).get('remote_id',''))
            if not remote: continue
            direct=get(remote+'?'+urlencode({'fields':'id,media_type,media_product_type,timestamp,permalink,caption'}),token)
            if direct:
                print('DIRECT',article_id,kind,'exists',direct.get('id')==remote,'type',direct.get('media_type'),'product',direct.get('media_product_type'),'permalink',direct.get('permalink',''))
            else: print('DIRECT',article_id,kind,'not_verifiable')
    print('Read-only diagnostic completed; no posts attempted')

if __name__=='__main__':main()
