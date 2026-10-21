import test from 'node:test';
import assert from 'node:assert/strict';
import {createFreeClient,FREE_CACHE_KEY} from '../../assets/js/free-market-client.mjs';
const initial=Date.parse('2026-10-21T09:00:00Z');
const storage=()=>{const data=new Map();return {getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v)};};
const feed=time=>async(url,options)=>{
 assert.equal(options.credentials,'omit');assert.equal(options.referrerPolicy,'no-referrer');assert.equal(options.headers.Authorization,undefined);
 const symbol=url.split('/').at(-1),names={BTC:'Bitcoin',ETH:'Ethereum',XAU:'Gold'};
 return new Response(JSON.stringify(url.includes('frankfurter')?[
  {base:'USD',quote:'JPY',date:'2026-10-20',rate:150},{base:'USD',quote:'JPY',date:'2026-10-21',rate:151}
 ]:{symbol,name:names[symbol],price:100,currency:'USD',exchangeRate:1,updatedAt:new Date(time()-20000).toISOString()}));
};
test('free browser cache shares four quotes across reloads, preserves their times and bounds request starts',async()=>{
 let time=initial,calls=0;const saved=storage(),starts=[];
 const fetcher=async(...args)=>{calls++;return feed(()=>time)(...args);};
 const make=()=>createFreeClient({storage:saved,now:()=>time,fetcher,wait:async ms=>{starts.push(ms);}});
 const first=await make().getSnapshot();assert.equal(first.quotes.length,4);assert.deepEqual(starts,[0,1150,2300]);
 time+=120000;assert.deepEqual(await make().getSnapshot(),first);assert.equal(calls,4);
 assert.deepEqual(first.pendingIds,['nasdaq','sp500']);assert.ok(!JSON.stringify(first).includes('observations'));
 time+=181000;const next=await make().getSnapshot();assert.equal(calls,8);assert.notEqual(next.quotes[0].fetchedAt,first.quotes[0].fetchedAt);
});
test('failed free requests back off, do not retime prior prices and keep bounded observation history',async()=>{
 let time=initial;const saved=storage();
 const ready=createFreeClient({storage:saved,now:()=>time,fetcher:feed(()=>time),wait:async()=>{}});const first=await ready.getSnapshot();
 time+=301000;let failures=0;
 const failed=()=>createFreeClient({storage:saved,now:()=>time,fetcher:async()=>{failures++;throw Error('offline');},wait:async()=>{}});
 await assert.rejects(failed().getSnapshot());await assert.rejects(failed().getSnapshot());assert.equal(failures,4);
 const state=JSON.parse(saved.getItem(FREE_CACHE_KEY));assert.equal(state.snapshot.quotes.length,0);assert.equal(state.observations.length,3);
 assert.equal(state.observations[0].asOf,first.quotes[0].asOf);
});
test('denied storage works in memory; cancellation does not poison a later attempt',async()=>{
 const denied={getItem(){throw Error('denied');},setItem(){throw Error('denied');}};
 let calls=0;const client=createFreeClient({storage:denied,now:()=>initial,fetcher:async(...a)=>{calls++;return feed(()=>initial)(...a);},wait:async()=>{}});
 const stop=new AbortController();stop.abort();await assert.rejects(client.getSnapshot({signal:stop.signal}));assert.equal(calls,0);
 assert.equal((await client.getSnapshot()).quotes.length,4);await client.getSnapshot();assert.equal(calls,4);
});
