// Read-only collection using the existing GitHub Secrets. No publication or ledger writes.
import {readFile,writeFile} from 'node:fs/promises';
import {collectMetaInsights} from './social_meta.mjs';
const root=new URL('../',import.meta.url);
const [feed,ledger]=await Promise.all(['data/articles.json','.github/social-post-ledger.json'].map(async p=>JSON.parse(await readFile(new URL(p,root),'utf8'))));
const articles=feed.filter(a=>a.social_publish===true&&a.status==='published').map(a=>({id:a.id,title:a.title,platforms:Object.fromEntries(Object.entries(ledger[a.id]||{}).filter(([key,p])=>['threads','instagram','instagram_story'].includes(key)&&p.status==='published'&&/^\d+$/.test(p.remote_id||'')).map(([key,p])=>[key,{status:p.status,remoteId:p.remote_id}]))}));
const insights=await collectMetaInsights({SOCIAL_THREADS_ACCESS_TOKEN:process.env.THREADS_ACCESS_TOKEN,SOCIAL_INSTAGRAM_ACCESS_TOKEN:process.env.INSTAGRAM_ACCESS_TOKEN},articles);
await writeFile(new URL('../work-signal-social-insights.json',import.meta.url),JSON.stringify({source:'WORK SIGNAL Social Insights',siteId:'signal',insights},null,2));
// Public CI logs only show connection status, never credentials or private metric values.
for(const [key,account]of Object.entries(insights.accounts))console.log(key+': '+account.status+'; followers status='+account.followersStatus+'; inspected posts='+(account.posts?.length||0));
