import { validQuote, validDate, canFloat } from './market-model.mjs';

export const FREE_IDS = Object.freeze(['btc','eth','gold','usdjpy']);
const GOLD = Object.freeze({btc:{symbol:'BTC',name:'Bitcoin'}, eth:{symbol:'ETH',name:'Ethereum'}, gold:{symbol:'XAU',name:'Gold'}});
const iso = n => new Date(n).toISOString();
export function goldQuote(id, raw, now, history = []) {
  const asset = GOLD[id];
  if (!asset || raw?.symbol !== asset.symbol || raw.name !== asset.name || raw.currency !== 'USD' || raw.exchangeRate !== 1 || typeof raw.price !== 'number') return null;
  const q = {id, provider:'gold-api', price:raw.price, asOf:raw.updatedAt, fetchedAt:iso(now), changePercent:null, changeBasis:'observed_24h', comparisonAt:null, marketState:'unknown', timing:'reference', delaySeconds:null};
  if (!validQuote(q, now)) return null;
  // Compare only this same feed's actual observations, within 15 minutes of 24h.
  const target = Date.parse(q.asOf) - 86400_000;
  const prior = cleanHistory(history, now).filter(h => h.id === id && Math.abs(Date.parse(h.asOf) - target) <= 900_000)
    .sort((a,b) => Math.abs(Date.parse(a.asOf)-target) - Math.abs(Date.parse(b.asOf)-target))[0];
  if (prior) { q.changePercent = (q.price / prior.price - 1) * 100; q.comparisonAt = prior.asOf; }
  return validQuote(q, now) ? q : null;
}
export function fxQuote(raw, now) {
  if (!Array.isArray(raw) || !raw.length || raw.length > 32) return null;
  // Reject a mixed currency, malformed date or duplicate rather than silently select it.
  if (raw.some(r => r?.base !== 'USD' || r.quote !== 'JPY' || !validDate(r.date) || typeof r.rate !== 'number' || !Number.isFinite(r.rate) || r.rate <= 0)
    || new Set(raw.map(r => r.date)).size !== raw.length) return null;
  const rows = [...raw].sort((a,b) => a.date.localeCompare(b.date));
  const latest = rows.at(-1), previous = rows.at(-2);
  const q = {id:'usdjpy', provider:'frankfurter', price:latest.rate, asOf:latest.date, fetchedAt:iso(now), changePercent:previous ? (latest.rate / previous.rate - 1) * 100 : null, changeBasis:'previous_publication', comparisonAt:previous?.date || null, marketState:'unknown', timing:'daily_reference', delaySeconds:null};
  return validQuote(q, now) ? q : null;
}
export function cleanHistory(history, now) {
  if (!Array.isArray(history)) return [];
  return Object.keys(GOLD).flatMap(id => history.filter(h => h?.id === id && h.provider === 'gold-api' && typeof h.price === 'number' && Number.isFinite(h.price) && h.price > 0 && typeof h.asOf === 'string' && h.asOf.includes('T') && Number.isFinite(Date.parse(h.asOf)) && Date.parse(h.asOf) <= now + 60_000 && now - Date.parse(h.asOf) <= 50 * 3600_000)
    .sort((a,b) => Date.parse(a.asOf) - Date.parse(b.asOf))
    // One last observation per 5-minute bucket, even when licensed feeds run every minute.
    .filter((h,i,a) => i === a.length-1 || Math.floor(Date.parse(h.asOf)/300_000) !== Math.floor(Date.parse(a[i+1].asOf)/300_000)).slice(-610)
    .map(({id,price,asOf}) => ({id,price,asOf,provider:'gold-api'})));
}
export function nextHistory(previous, quotes, now) {
  return cleanHistory([...cleanHistory(previous, now), ...quotes.filter(q => q.provider === 'gold-api' && canFloat(q,now))],now);
}
export async function collectFree(fetcher = fetch, now = Date.now(), history = []) {
  const started = Date.now();
  const completed = () => now + Date.now() - started;
  const get = async url => {
    const response = await fetcher(url, {headers:{Accept:'application/json'}, signal:AbortSignal.timeout(6000)});
    if (!response.ok) throw new Error('Provider unavailable');
    return response.json();
  };
  const start = iso(now - 14 * 86400_000).slice(0,10);
  const jobs = Object.keys(GOLD).map(id => async () => goldQuote(id, await get(`https://api.gold-api.com/price/${GOLD[id].symbol}`), completed(), history));
  jobs.push(async () => fxQuote(await get(`https://api.frankfurter.dev/v2/rates?base=USD&quotes=JPY&from=${start}&to=${iso(now).slice(0,10)}`), completed()));
  const settled = await Promise.allSettled(jobs.map(run => run()));
  // Failure never re-stamps an old observation. Other successful feeds remain usable.
  return settled.flatMap(r => r.status === 'fulfilled' && r.value ? [r.value] : []);
}
