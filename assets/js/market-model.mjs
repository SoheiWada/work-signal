// Shared wire contract. Credentials and arbitrary provider URLs never cross this boundary.
export const INSTRUMENTS = Object.freeze([
  { id: 'btc', name: 'BITCOIN', ticker: 'BTC', unit: 'USD / BTC', prefix: '$', description: 'ビットコインの市場価格', url: 'https://www.coinbase.com/price/bitcoin' },
  { id: 'eth', name: 'ETHEREUM', ticker: 'ETH', unit: 'USD / ETH', prefix: '$', description: 'イーサリアムの市場価格', url: 'https://www.coinbase.com/price/ethereum' },
  { id: 'nasdaq', name: 'NASDAQ COMPOSITE', ticker: 'NASDAQ', unit: 'POINTS', prefix: '', description: 'ナスダック総合指数', url: 'https://www.nasdaq.com/market-activity/index/comp' },
  { id: 'sp500', name: 'S&P 500', ticker: 'S&P 500', unit: 'POINTS', prefix: '', description: '米国主要企業の株価指数', url: 'https://www.spglobal.com/spdji/en/indices/equity/sp-500/' },
  { id: 'gold', name: 'GOLD SPOT', ticker: 'GOLD', unit: 'USD / TROY OZ', prefix: '$', description: '金の現物価格 · 1トロイオンス', url: 'https://www.lbma.org.uk/prices-and-data/precious-metal-prices' },
  { id: 'usdjpy', name: 'US DOLLAR / YEN', ticker: 'USD/JPY', unit: 'JPY / USD', prefix: '¥', description: '1米ドルあたりの日本円', url: 'https://www.boj.or.jp/statistics/market/forex/fxdaily/index.htm' },
]);
export const PROVIDERS = Object.freeze({
  'twelve-data': {name:'Twelve Data', url:'https://twelvedata.com/'},
  'gold-api': {name:'Gold API', url:'https://gold-api.com/'},
  frankfurter: {name:'Frankfurter', url:'https://frankfurter.dev/'},
});
const finite = n => typeof n === 'number' && Number.isFinite(n);
export const validDate = s => typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s) && Number.isFinite(Date.parse(s)) && new Date(s).toISOString().slice(0,10) === s;
const instant = s => typeof s === 'string' && validDate(s.slice(0,10)) && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(s) && Number.isFinite(Date.parse(s));
export const formatFigure = price => new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(price);
export const formatPrice = (id, price) => (INSTRUMENTS.find(i => i.id === id)?.prefix || '') + formatFigure(price);
export const fetchMaxAge = q => ['gold-api','frankfurter'].includes(q?.provider) ? 15 * 60_000 : 180_000;
export function validQuote(q, now = Date.now()) {
  if (!q || !INSTRUMENTS.some(i => i.id === q.id) || !finite(q.price) || q.price <= 0) return false;
  if (q.provider !== undefined && !Object.hasOwn(PROVIDERS, q.provider)) return false;
  if (!instant(q.fetchedAt) || Date.parse(q.fetchedAt) > now + 60_000) return false;
  if (!['open','closed','unknown'].includes(q.marketState)) return false;
  if (q.provider === 'frankfurter') {
    return q.id === 'usdjpy' && q.timing === 'daily_reference' && q.marketState === 'unknown' && q.delaySeconds === null
      && validDate(q.asOf) && q.asOf <= new Date(Math.min(now + 60_000, Date.parse(q.fetchedAt) + 60_000)).toISOString().slice(0,10)
      && q.changeBasis === 'previous_publication' && (q.changePercent === null && q.comparisonAt === null || finite(q.changePercent) && validDate(q.comparisonAt) && q.comparisonAt < q.asOf);
  }
  if (!instant(q.asOf) || Date.parse(q.asOf) > Math.min(now + 60_000, Date.parse(q.fetchedAt) + 60_000)) return false;
  if (q.provider === 'gold-api') {
    return ['btc','eth','gold'].includes(q.id) && q.timing === 'reference' && q.marketState === 'unknown' && q.delaySeconds === null
      && q.changeBasis === 'observed_24h' && (q.changePercent === null && q.comparisonAt === null || finite(q.changePercent) && instant(q.comparisonAt) && Math.abs(Date.parse(q.asOf) - Date.parse(q.comparisonAt) - 86400_000) <= 900_000);
  }
  return finite(q.changePercent) && ['realtime','delayed','eod'].includes(q.timing)
    && Number.isInteger(q.delaySeconds) && q.delaySeconds >= 0 && q.delaySeconds <= 86400
    && (q.timing !== 'realtime' || q.delaySeconds === 0)
    && ['24h','previous_close'].includes(q.changeBasis);
}
export function quoteState(q, now = Date.now()) {
  if (!validQuote(q, now)) return 'unavailable';
  if (q.fetchFailed || now - Date.parse(q.fetchedAt) > fetchMaxAge(q)) return 'stale';
  if (q.provider === 'frankfurter') return now - Date.parse(q.asOf) > 7 * 86400_000 ? 'stale' : 'daily_reference';
  if (q.provider === 'gold-api') return now - Date.parse(q.asOf) > 15 * 60_000 ? 'stale' : 'reference';
  const maxAge = q.marketState === 'closed' || q.timing === 'eod' ? 4 * 86400_000 : (q.delaySeconds + 180) * 1000;
  if (now - Date.parse(q.asOf) > maxAge) return 'stale';
  return q.marketState === 'closed' ? 'closed' : q.timing === 'eod' ? 'eod' : q.timing === 'delayed' ? 'delayed' : q.marketState === 'unknown' ? 'unknown' : 'current';
}
export function normalizeSnapshot(raw, now = Date.now()) {
  if (raw?.version !== 1 || !Array.isArray(raw.quotes)) return [];
  return INSTRUMENTS.flatMap(i => {
    const matches = raw.quotes.filter(q => q?.id === i.id);
    return matches.length === 1 && validQuote(matches[0], now) ? [matches[0]] : [];
  });
}
export const canFloat = (q, now = Date.now()) => !['stale','unavailable','unknown'].includes(quoteState(q, now));
export function statusLabel(q, now = Date.now()) {
  const state = quoteState(q, now);
  return ({ current:'取引中 · 参考値', closed:'休場中 · 最終取引値', eod:'終値', delayed:`${Math.ceil(q?.delaySeconds / 60)}分遅延`, reference:'提供元参考値 · 取引状態未確認', daily_reference:'日次参考レート', unknown:'取引状態を確認できません', stale:'更新が止まっています', unavailable:'現在取得できません' })[state];
}
