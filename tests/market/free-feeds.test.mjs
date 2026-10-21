import test from 'node:test';
import assert from 'node:assert/strict';
import { goldQuote, fxQuote, collectFree, cleanHistory, nextHistory } from '../../services/market-data/free-feeds.mjs';
import worker, {collect} from '../../services/market-data/worker.mjs';
import {validQuote, quoteState, canFloat} from '../../assets/js/market-model.mjs';

const now = Date.parse('2026-10-20T09:00:00Z');
const stamp = n => new Date(now-n).toISOString();
const raw = (symbol='BTC',name='Bitcoin') => ({symbol,name,price:80000,currency:'USD',exchangeRate:1,updatedAt:stamp(20000)});
const freeEnv = {PUBLIC_DISPLAY_APPROVED:'yes', FREE_FEEDS_ENABLED:'yes'};
const fxRows = [{base:'USD',quote:'JPY',date:'2026-10-19',rate:150},{base:'USD',quote:'JPY',date:'2026-10-20',rate:153}];
const feed = async url => new Response(JSON.stringify(url.includes('frankfurter') ? fxRows : url.endsWith('ETH') ? raw('ETH','Ethereum') : url.endsWith('XAU') ? raw('XAU','Gold') : raw()));

test('free quotes preserve actual timestamps, null change and unconfirmed market status', () => {
  const q = goldQuote('btc',raw(),now);
  assert.equal(q.asOf,raw().updatedAt);
  assert.equal(q.changePercent,null);
  assert.equal(q.marketState,'unknown');
  assert.equal(q.delaySeconds,null);
  assert.equal(quoteState(q,now),'reference');
  assert.ok(canFloat(q,now));
  assert.equal(quoteState(q,now+16*60000),'stale');
  for (const bad of [{currency:'EUR'}, {exchangeRate:0.9}, {symbol:'BTCUSD'}, {name:'Bitcoin future'}, {price:'80000'}, {price:-1}, {updatedAt:'2026-10-20'}, {updatedAt:stamp(-120000)}]) assert.equal(goldQuote('btc',{...raw(),...bad},now),null);
  assert.equal(validQuote({...q,changePercent:0,comparisonAt:null},now),false);
  assert.equal(validQuote({...q,provider:'invented'},now),false);
});
test('24h change uses only same-feed history within the declared tolerance', () => {
  const h = {id:'btc',provider:'gold-api',price:40000,asOf:stamp(86420000)};
  const q = goldQuote('btc',raw(),now,[h]);
  assert.equal(q.changePercent,100);
  assert.equal(q.comparisonAt,h.asOf);
  for (const bad of [{provider:'twelve-data'}, {id:'eth'}, {price:0}, {asOf:stamp(86420000+901000)}]) assert.equal(goldQuote('btc',raw(),now,[{...h,...bad}]).changePercent,null);
  const merged = nextHistory([h,h], [q], now);
  assert.equal(merged.length,2);
  assert.equal(cleanHistory([{...h,asOf:stamp(51*3600000)}, {...h,asOf:stamp(-120000)}],now).length,0);
  const minuteHistory=cleanHistory(Array.from({length:3000},(_,i)=>({...h,asOf:stamp(i*60000)})),now);
  assert.ok(minuteHistory.length <= 610);
  assert.ok(Date.parse(minuteHistory[0].asOf) < now - 49*3600000);
  assert.notEqual(goldQuote('btc',raw(),now,minuteHistory).changePercent,null);
});
test('FX compares prior publication and keeps date-only precision, never invents tick time', () => {
  const q=fxQuote(fxRows,now);
  assert.equal(q.asOf,'2026-10-20');
  assert.equal(q.comparisonAt,'2026-10-19');
  assert.ok(Math.abs(q.changePercent-2)<1e-10);
  assert.equal(quoteState(q,now),'daily_reference');
  assert.ok(canFloat(q,now));
  assert.equal(fxQuote(fxRows.slice(0,1),now).changePercent,null);
  for (const bad of [[...fxRows,fxRows[0]], [{...fxRows[0],quote:'EUR'}], [{...fxRows[0],date:'2026-02-30'}], [{...fxRows[0],rate:'150'}], [{...fxRows[0],date:'2026-10-21'}]]) assert.equal(fxQuote(bad,now),null);
  assert.equal(quoteState({...q,fetchedAt:stamp(16*60000)},now),'stale');
  assert.equal(quoteState({...q,asOf:'2026-10-10',comparisonAt:'2026-10-09'},now),'stale');
});
test('collector calls fixed anonymous endpoints and isolates failures', async () => {
  const urls=[];
  const q=await collectFree(async(url,options)=>{
    urls.push(url);assert.equal(options.headers.Authorization,undefined);
    assert.ok(['api.gold-api.com','api.frankfurter.dev'].includes(new URL(url).hostname));
    if(url.endsWith('ETH'))return new Response('{}',{status:429});
    return feed(url);
  },now);
  assert.equal(urls.length,4);
  assert.deepEqual(q.map(q=>q.id),['btc','gold','usdjpy']);
  assert.deepEqual(await collectFree(async()=>{throw Error('offline');},now),[]);
});
test('approval gates apply to free feeds and licensed identities do not silently switch provider', async () => {
  for(const denied of [{FREE_FEEDS_ENABLED:'yes'},{...freeEnv,PUBLIC_DISPLAY_APPROVED:'no'}, {...freeEnv,FREE_FEEDS_ENABLED:'no'}]) assert.deepEqual((await collect(denied,()=>{throw Error('No upstream expected');},now)).quotes,[]);
  const result=await collect(freeEnv,feed,now);
  assert.equal(result.quotes.length,4);
  assert.deepEqual(result.pendingIds,['nasdaq','sp500']);
  assert.equal(result.observations.length,3);
  const config={id:'btc',symbol:'BTC/USD',expectedName:'Bitcoin',expectedExchange:'Contracted',timing:'realtime',delaySeconds:0,publicDisplay:true,identityConfirmed:true};
  const mixed=await collect({...freeEnv,TWELVE_DATA_API_KEY:'TEST_ONLY',LICENSED_INSTRUMENTS:JSON.stringify([config])},feed,now);
  assert.ok(!mixed.quotes.some(q=>q.id==='btc')); // licensed call failed; no free fallback
});
test('public free endpoint excludes history, revoked feeds and expired snapshots', async () => {
  // Request validation uses wall time; create fixtures relative to it.
  const time=Date.now();
  const q=goldQuote('btc',{...raw(),updatedAt:new Date(time-20000).toISOString()},time);
  const env={...freeEnv,ALLOWED_ORIGIN:'https://signal.amberlight.co.jp',MARKET_SNAPSHOTS:{get:async()=>({version:1,quotes:[q],observations:[{private:'internal history'}]})}};
  const request=new Request('https://market.example/v1/quotes');
  const body=await (await worker.fetch(request,env)).json();
  assert.equal(body.quotes.length,1);
  assert.ok(!JSON.stringify(body).includes('observations'));
  assert.equal((await (await worker.fetch(request,{...env,FREE_FEEDS_ENABLED:'no'})).json()).quotes.length,0);
  env.MARKET_SNAPSHOTS.get=async()=>({version:1,quotes:[{...q,fetchedAt:new Date(time-16*60000).toISOString(),asOf:new Date(time-16*60000).toISOString()}]});
  assert.equal((await (await worker.fetch(request,env)).json()).quotes.length,0);
});
test('free-only schedule skips intermediate minutes without storage or upstream work', async () => {
  let work=false;
  await worker.scheduled({scheduledTime:Date.parse('2026-10-20T09:01:00Z')},freeEnv,{waitUntil(){work=true;}});
  assert.equal(work,false);
  await worker.scheduled({scheduledTime:now},{PUBLIC_DISPLAY_APPROVED:'no'},{waitUntil(){work=true;}});
  assert.equal(work,false);
});
