import test from 'node:test';
import assert from 'node:assert/strict';
import { canFloat, normalizeSnapshot, quoteState, formatPrice } from '../../assets/js/market-model.mjs';
import worker, { approvedConfig, collect, toQuote } from '../../services/market-data/worker.mjs';

const now = Date.now();
const quote = overrides => ({id:'btc', price:64000, changePercent:1, changeBasis:'24h', asOf:new Date(now - 30000).toISOString(), fetchedAt:new Date(now).toISOString(), marketState:'open', timing:'realtime', delaySeconds:0, ...overrides});
const config = {id:'btc', symbol:'BTC/USD', expectedName:'Bitcoin', expectedExchange:'Fixture exchange', publicDisplay:true, identityConfirmed:true, timing:'realtime', delaySeconds:0};
const env = {PUBLIC_DISPLAY_APPROVED:'yes', TWELVE_DATA_API_KEY:'TEST_SECRET_NOT_REAL', LICENSED_INSTRUMENTS:JSON.stringify([config])};
const raw = {symbol:'BTC/USD', name:'Bitcoin', exchange:'Fixture exchange', close:'64000', rolling_1d_change:'1.23', percent_change:'4.56', last_quote_at:Math.floor((now-30000)/1000), is_market_open:true};

test('old/future/invalid values never appear as current market data', () => {
  assert.equal(quoteState(quote(), now), 'current');
  for (const bad of [{price:0}, {price:Infinity}, {changePercent:null}, {asOf:'bad'}, {asOf:new Date(now+120000).toISOString()}, {delaySeconds:-1}, {timing:'unknown'}]) assert.equal(canFloat(quote(bad), now), false);
  assert.equal(canFloat(quote({fetchedAt:new Date(now-181000).toISOString(), asOf:new Date(now-181000).toISOString()}), now), false);
  assert.equal(canFloat(quote({fetchFailed:true}), now), false);
  assert.equal(canFloat(quote({marketState:'unknown'}), now), false);
});
test('delay and closed prices use their actual timestamps and expire', () => {
  assert.equal(quoteState(quote({timing:'delayed', delaySeconds:900, asOf:new Date(now-925000).toISOString()}), now), 'delayed');
  assert.equal(quoteState(quote({marketState:'closed', asOf:new Date(now-2*86400000).toISOString()}), now), 'closed');
  assert.equal(quoteState(quote({marketState:'closed', asOf:new Date(now-5*86400000).toISOString()}), now), 'stale');
});
test('wire validation drops duplicates, unknown symbols, missing change and wrong versions', () => {
  assert.deepEqual(normalizeSnapshot({version:1, quotes:[quote(),quote()]},now), []);
  assert.deepEqual(normalizeSnapshot({version:2, quotes:[quote()]},now), []);
  assert.deepEqual(normalizeSnapshot({version:1, quotes:[quote({id:'spy'}),quote({changePercent:undefined})]},now), []);
  assert.equal(formatPrice('usdjpy',149.8), '¥149.80');
});
test('permission and exact instrument identity gates fail closed', async () => {
  for (const denied of [{...env,PUBLIC_DISPLAY_APPROVED:'no'}, {...env,LICENSED_INSTRUMENTS:'invalid'}, {...env,LICENSED_INSTRUMENTS:JSON.stringify([{...config,identityConfirmed:false}])}]) {
    assert.deepEqual(approvedConfig(denied), []);
    const result = await collect(denied, () => {throw new Error('must not call upstream');},now);
    assert.deepEqual(result.quotes, []);
  }
  for (const bad of [{symbol:'SPY'}, {name:'Different asset'}, {exchange:'Wrong feed'}, {currency:'EUR'}, {last_quote_at:undefined}, {close:''}, {rolling_1d_change:null}, {is_market_open:'false'}]) {
    const q = toQuote(config,{...raw,...bad},now);
    assert.ok(q === null || !canFloat(q,now));
  }
  assert.equal(toQuote(config,raw,now).changePercent,1.23);
});
test('upstream auth is in headers, partial failures omit instruments, errors never leak secrets', async () => {
  const result = await collect(env, async (url, options) => {
    assert.ok(!url.includes(env.TWELVE_DATA_API_KEY));
    assert.equal(options.headers.Authorization, 'apikey ' + env.TWELVE_DATA_API_KEY);
    return new Response(JSON.stringify(raw));
  }, now);
  assert.equal(result.quotes.length,1);
  assert.ok(!JSON.stringify(result).includes(env.TWELVE_DATA_API_KEY));
  assert.deepEqual((await collect(env, async()=>{throw Error('secret');},now)).quotes,[]);
  assert.deepEqual((await collect(env, async()=>new Response('{}',{status:429}),now)).quotes,[]);
});
test('public endpoint has no upstream calls, enforces origin, method, approval and snapshot age', async () => {
  const store = {...env, ALLOWED_ORIGIN:'https://signal.amberlight.co.jp', MARKET_SNAPSHOTS:{get:async()=>({version:1,quotes:[quote()]})}};
  const req = (origin, method='GET') => new Request('https://market.example/v1/quotes',{method,headers:{Origin:origin}});
  const response = await worker.fetch(req(store.ALLOWED_ORIGIN),store);
  assert.equal(response.headers.get('Access-Control-Allow-Origin'), store.ALLOWED_ORIGIN);
  assert.equal((await response.json()).quotes.length,1);
  assert.equal((await worker.fetch(req('https://evil.example'),store)).status,403);
  assert.equal((await worker.fetch(req(store.ALLOWED_ORIGIN,'POST'),store)).status,405);
  assert.deepEqual((await (await worker.fetch(req(store.ALLOWED_ORIGIN),{...store,PUBLIC_DISPLAY_APPROVED:'no'})).json()).quotes,[]);
  store.MARKET_SNAPSHOTS.get=async()=>({version:1,quotes:[quote({asOf:new Date(0).toISOString(),fetchedAt:new Date(0).toISOString()})]});
  assert.deepEqual((await (await worker.fetch(req(store.ALLOWED_ORIGIN),store)).json()).quotes,[]);
});
