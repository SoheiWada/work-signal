// GET-only Meta adapter. Never return bearer tokens, paging URLs, raw errors or audience profiles.
const BASE={threads:'https://graph.threads.net/v1.0',instagram:'https://graph.instagram.com/v25.0'};
export async function collectMetaInsights(env,articles,fetcher=fetch,now=new Date()){
 const accounts={};
 await Promise.all(['threads','instagram'].map(async platform=>{
  const token=env[platform==='threads'?'SOCIAL_THREADS_ACCESS_TOKEN':'SOCIAL_INSTAGRAM_ACCESS_TOKEN'];
  if(!token){accounts[platform]={status:'not_connected',followers:null,posts:[],message:'インサイトの取得接続が必要です。投稿用の接続とは別に確認します。'};return;}
  const base=BASE[platform];
  const get=async(path)=>{const r=await fetcher(base+path,{method:'GET',headers:{Authorization:'Bearer '+token,Accept:'application/json'},signal:AbortSignal.timeout(12000)});const d=await r.json();if(!r.ok||d.error){const e=Error('Meta read failed');e.state=d.error?.code===190?'authentication_expired':r.status===403||[10,200].includes(d.error?.code)?'authorization_required':'unavailable';throw e;}return d;};
  try{
   const identity=await get(platform==='threads'?'/me?fields=id,username':'/me?fields=user_id,username,account_type');
   if(identity.username?.toLowerCase()!=='work_signal_japan')throw Object.assign(Error('Account mismatch'),{state:'wrong_account'});
   const id=String(identity.user_id||identity.id||'');if(!/^\d+$/.test(id))throw Error('Invalid account');
   const account={status:'available',username:'work_signal_japan',fetchedAt:now.toISOString(),followers:null,followersStatus:'unavailable',posts:[],postMetricBasis:'lifetime_at_fetch',notes:[]};accounts[platform]=account;
   try{if(platform==='instagram'){const d=await get('/'+id+'?fields=followers_count');if(Number.isFinite(d.followers_count)&&d.followers_count>=0){account.followers=d.followers_count;account.followersStatus='available';}}
    else{const d=await get('/'+id+'/threads_insights?metric=followers_count');const m=(d.data||[]).find(x=>x.name==='followers_count');const n=m?.total_value?.value??m?.values?.at(-1)?.value;if(Number.isFinite(n)&&n>=0){account.followers=n;account.followersStatus='available';}}}
   catch(e){account.followersStatus=e.state||'unavailable';account.status='partial';}
   const candidates=articles.flatMap(a=>Object.entries(a.platforms||{}).filter(([key,p])=>p.status==='published'&&p.remoteId&&((platform==='threads'&&key==='threads')||(platform==='instagram'&&['instagram','instagram_story'].includes(key)))).map(([kind,p])=>({articleId:a.id,title:a.title,kind,...p}))).slice(0,20);
   const inspect=async post=>{
    const row={articleId:post.articleId,title:post.title,platform:post.kind,remoteId:post.remoteId,status:'available',metrics:{}};account.posts.push(row);
    const names=platform==='threads'?['views','likes','replies','reposts','quotes']:['views','reach','saved','shares','total_interactions'];
    try{const d=await get('/'+post.remoteId+'/insights?metric='+names.join(','));for(const m of d.data||[]){const v=m.total_value?.value??m.values?.at(-1)?.value;if(names.includes(m.name)&&Number.isFinite(v)&&v>=0)row.metrics[m.name]=v;}if(!Object.keys(row.metrics).length)row.status='unavailable';}
    catch(e){row.status=e.state||'unavailable';account.status='partial';}
   };
   const queue=[...candidates];await Promise.all(Array.from({length:4},async()=>{while(queue.length)await inspect(queue.shift());}));
   if(articles.flatMap(a=>Object.entries(a.platforms||{}).filter(([k,p])=>p.status==='published'&&(platform==='threads'?k==='threads':['instagram','instagram_story'].includes(k)))).length>20){account.truncated=true;account.status='partial';account.notes.push('投稿指標は最大20件。');}
  }catch(e){accounts[platform]={status:e.state||'unavailable',followers:null,posts:[],message:'インサイトを取得できませんでした。アカウント・読み取り権限・有効期限を確認してください。'};}
 }));
 return{source:'Meta Insights API',fetchedAt:now.toISOString(),accounts,notes:['フォロワー数は取得時点の値。投稿指標は投稿以来の累計で、選択期間内の増分ではありません。','媒体ごとに指標の定義が異なります。閲覧数やリーチを合算して人数にしないでください。','期限切れのストーリーズ等は取得できない場合があります。未取得は0ではありません。']};
}
