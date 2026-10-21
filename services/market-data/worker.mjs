import { INSTRUMENTS, validQuote, fetchMaxAge } from '../../assets/js/market-model.mjs';

import { FREE_IDS, collectFree, nextHistory } from './free-feeds.mjs';

// Cron is the ONLY upstream caller. A million page views still read one shared snapshot.
// Keep this service separate from GitHub Pages; never copy it into the site artifact.
const KEY = 'quotes-v1';
export const freeEnabled = env => env.PUBLIC_DISPLAY_APPROVED === 'yes' && env.FREE_FEEDS_ENABLED === 'yes';
const pendingIds = env => INSTRUMENTS.map(i => i.id).filter(id => !approvedConfig(env).some(c => c.id === id) && !(freeEnabled(env) && FREE_IDS.includes(id)));
const number = v => typeof v === 'number' || typeof v === 'string' && v.trim() !== '' ? Number(v) : NaN;
export function approvedConfig(env) {
  if (env.PUBLIC_DISPLAY_APPROVED !== 'yes' || !env.TWELVE_DATA_API_KEY) return [];
  let config; try { config = JSON.parse(env.LICENSED_INSTRUMENTS || '[]'); } catch { return []; }
  if (!Array.isArray(config)) return [];
  return config.filter(c => INSTRUMENTS.some(i => i.id === c?.id) && config.filter(x => x?.id === c.id).length === 1
    && c.publicDisplay === true && c.identityConfirmed === true && typeof c.symbol === 'string' && /^[A-Za-z0-9./:_-]{1,40}$/.test(c.symbol)
    && typeof c.expectedName === 'string' && c.expectedName.length > 0
    && typeof c.expectedExchange === 'string' && c.expectedExchange.length > 0
    && ['realtime','delayed','eod'].includes(c.timing)
    && Number.isInteger(c.delaySeconds) && c.delaySeconds >= 0 && c.delaySeconds <= 86400
    && (c.timing !== 'realtime' || c.delaySeconds === 0)
    && (c.timing !== 'delayed' || c.delaySeconds > 0));
}
export function toQuote(config, raw, now = Date.now()) {
  // Names/exchange are confirmed from the contracted feed. No ETF/futures substitutes.
  if (!raw || raw.status === 'error' || raw.symbol !== config.symbol || raw.name !== config.expectedName || raw.exchange !== config.expectedExchange) return null;
  if (raw.currency && raw.currency !== (config.id === 'usdjpy' ? 'JPY' : 'USD')) return null;
  // timestamp is a BAR OPEN time; it must not be presented as a current quote timestamp.
  const seconds = number(raw.last_quote_at);
  if (!Number.isSafeInteger(seconds) || seconds <= 0 || seconds * 1000 > now + 60_000) return null;
  const crypto = ['btc','eth'].includes(config.id);
  const q = {
    id: config.id, provider:'twelve-data', price: number(raw.close),
    changePercent: number(crypto ? raw.rolling_1d_change : raw.percent_change),
    changeBasis: crypto ? '24h' : 'previous_close',
    asOf: new Date(seconds * 1000).toISOString(), fetchedAt: new Date(now).toISOString(),
    marketState: typeof raw.is_market_open === 'boolean' ? raw.is_market_open ? 'open' : 'closed' : 'unknown',
    timing: config.timing, delaySeconds: config.delaySeconds,
  };
  return validQuote(q, now) ? q : null;
}
export async function collect(env, fetcher = fetch, now = Date.now(), history = []) {
  const config = approvedConfig(env), started = Date.now();
  const freeJob = freeEnabled(env) ? collectFree(fetcher, now, history) : Promise.resolve([]);
  const settled = await Promise.allSettled(config.map(async c => {
    const u = new URL('https://api.twelvedata.com/quote');
    u.searchParams.set('symbol', c.symbol); u.searchParams.set('interval','1day');
    u.searchParams.set('exchange', c.expectedExchange);
    if (c.timing === 'eod') u.searchParams.set('eod','true');
    u.searchParams.set('prepost','false'); u.searchParams.set('rolling_period','24');
    const response = await fetcher(u.href, {headers:{Authorization:`apikey ${env.TWELVE_DATA_API_KEY}`}, signal:AbortSignal.timeout(8000)});
    if (!response.ok) return null;
    return toQuote(c, await response.json(), now + Date.now() - started);
  }));
  // Partial failure removes only the failed instrument; no refreshed timestamps on old prices.
  const licensed = settled.flatMap(r => r.status === 'fulfilled' && r.value ? [r.value] : []);
  const free = await freeJob;
  // A configured licensed instrument never silently falls back to another feed.
  const quotes = [...licensed, ...free.filter(q => !config.some(c => c.id === q.id))];
  return {version:1, generatedAt:new Date(now + Date.now() - started).toISOString(), pendingIds:pendingIds(env), quotes, observations:freeEnabled(env) ? nextHistory(history, free, now) : []};
}
export default {
  async scheduled(event, env, context) {
    if (!approvedConfig(env).length && !freeEnabled(env)) return;
    if (!approvedConfig(env).length && new Date(event.scheduledTime).getUTCMinutes() % 5 !== 0) return;
    context.waitUntil((async () => {
      const prior = await env.MARKET_SNAPSHOTS.get(KEY, 'json');
      const snapshot = await collect(env, fetch, Date.now(), prior?.observations);
      // Keep only the bounded rolling history across quiet hours; never expose it publicly.
      await env.MARKET_SNAPSHOTS.put(KEY, JSON.stringify(snapshot), {expirationTtl:60 * 3600});
    })());
  },
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== '/v1/quotes') return new Response('Not found', {status:404});
    if (request.method !== 'GET' && request.method !== 'OPTIONS') return new Response(null, {status:405, headers:{Allow:'GET, OPTIONS'}});
    const origin = request.headers.get('Origin');
    if (origin && origin !== env.ALLOWED_ORIGIN) return new Response(null, {status:403});
    const headers = {'Content-Type':'application/json; charset=utf-8', 'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff', 'Vary':'Origin'};
    if (origin && origin === env.ALLOWED_ORIGIN) headers['Access-Control-Allow-Origin'] = origin;
    if (request.method === 'OPTIONS') return new Response(null, {status:204, headers:{...headers,'Access-Control-Allow-Methods':'GET'}});
    // Revoking approval suppresses even a still-cached snapshot immediately.
    if (!approvedConfig(env).length && !freeEnabled(env)) return new Response(JSON.stringify({version:1,quotes:[]}), {headers});
    const stored = await env.MARKET_SNAPSHOTS.get(KEY, 'json');
    const licensed = new Set(approvedConfig(env).map(c => c.id));
    const allowed = q => licensed.has(q.id) ? !q.provider || q.provider === 'twelve-data' : freeEnabled(env) && FREE_IDS.includes(q.id) && ['gold-api','frankfurter'].includes(q.provider);
    const now = Date.now();
    const quotes = stored?.version === 1 && Array.isArray(stored.quotes) ? stored.quotes.filter(q => validQuote(q, now) && allowed(q) && now - Date.parse(q.fetchedAt) <= fetchMaxAge(q)) : [];
    return new Response(JSON.stringify({version:1, pendingIds:pendingIds(env), quotes}), {headers});
  },
};
