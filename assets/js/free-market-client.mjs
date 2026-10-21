import {FREE_IDS, collectFree, cleanHistory, nextHistory} from './free-market-feeds.mjs';
import {normalizeSnapshot} from './market-model.mjs';

export const FREE_CACHE_KEY='work-signal-free-market-v1', FREE_REFRESH_MS=300_000;
const pendingIds=['nasdaq','sp500'];
function pause(ms,signal){
  signal?.throwIfAborted();
  if(!ms)return Promise.resolve();
  return new Promise((resolve,reject)=>{
    const finish=()=>{signal?.removeEventListener('abort',abort);resolve();};
    const timer=setTimeout(finish,ms);
    const abort=()=>{clearTimeout(timer);signal.removeEventListener('abort',abort);reject(signal.reason);};
    signal?.addEventListener('abort',abort,{once:true});
  });
}
export function createFreeClient({fetcher=fetch,storage=null,locks=null,now=Date.now,wait=pause}={}){
  let memory=null;
  const read=()=>{
    try{const raw=storage?.getItem(FREE_CACHE_KEY);if(raw&&raw.length<750_000)memory=JSON.parse(raw);}catch{/* Storage is optional. */}
    return memory;
  };
  const write=value=>{memory=value;try{storage?.setItem(FREE_CACHE_KEY,JSON.stringify(value));}catch{/* Memory-only in private/restricted contexts. */}};
  const publicSnapshot=state=>({version:1,pendingIds,quotes:normalizeSnapshot(state?.snapshot,now()).filter(q=>FREE_IDS.includes(q.id)&&['gold-api','frankfurter'].includes(q.provider))});
  async function load(signal){
    signal?.throwIfAborted();
    const prior=read(),time=now();
    if(Number.isFinite(prior?.checkedAt)&&prior.checkedAt<=time&&time-prior.checkedAt<FREE_REFRESH_MS){
      const snapshot=publicSnapshot(prior);if(!snapshot.quotes.length)throw Error('Free feeds unavailable');return snapshot;
    }
    let goldRequest=0;
    const anonymous=async(url,options)=>{
      // Spread the three Gold API starts; reloads and same-origin tabs share the cache.
      if(new URL(url).hostname==='api.gold-api.com')await wait(goldRequest++*1150,signal);
      signal?.throwIfAborted();
      return fetcher(url,{...options,credentials:'omit',referrerPolicy:'no-referrer',cache:'no-store',
        signal:signal?AbortSignal.any([signal,options.signal]):options.signal});
    };
    const history=cleanHistory(prior?.observations, time);
    const quotes=await collectFree(anonymous,time,history);
    signal?.throwIfAborted();
    const state={checkedAt:now(),snapshot:{version:1,quotes},observations:nextHistory(history,quotes,now())};
    write(state); // Failed attempts are also backed off; cached quote times never advance.
    if(!quotes.length)throw Error('Free feeds unavailable');
    return publicSnapshot(state);
  }
  return {getSnapshot:({signal}={})=>locks?locks.request(FREE_CACHE_KEY,{signal},()=>load(signal)):load(signal)};
}
let client;
export function getFreeSnapshot(options){
  if(!client){
    let storage;try{storage=localStorage;}catch{/* Storage may be disabled. */}
    client=createFreeClient({storage,locks:navigator.locks});
  }
  return client.getSnapshot(options);
}
