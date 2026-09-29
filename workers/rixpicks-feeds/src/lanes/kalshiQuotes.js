// kalshi-quotes lane - Worker port of scripts/kalshi_quotes.py.
// Reads the card pipeline's nfl_chips.json (input), writes nfl_kalshi_quotes.json.
// Fail-closed: fetch/parse trouble = no write; last-good object stays in R2.
const API = 'https://api.elections.kalshi.com/trade-api/v2/markets?tickers=%s&limit=100';

function isoZ(s) {
  if (typeof s !== 'string') return null;
  const core = s.split('+')[0].replace('Z', '').split('.')[0];
  const t = Date.parse(core + 'Z');
  if (isNaN(t)) return null;
  return new Date(t).toISOString().replace(/\.\d{3}Z$/, 'Z');
}
function cents(v) {
  const f = parseFloat(v);
  if (isNaN(f) || f <= 0) return null;
  const c = f <= 1.0 ? Math.round(f * 100) : Math.round(f);
  return c >= 1 && c <= 100 ? c : null;
}

export async function runKalshiQuotes(env) {
  let slate;
  try { slate = JSON.parse(await (await fetch(env.PROD_BASE + '/slates/nfl_chips.json?cb=' + Date.now())).text()); }
  catch (e) { console.error('no slate readable - nothing to do'); return { skipped: 'slate unreadable' }; }
  const tickers = [];
  for (const leg of slate.legs || []) {
    const t = ((leg.kalshi || {}).ticker);
    if (typeof t === 'string' && t && !tickers.includes(t)) tickers.push(t);
  }
  if (!tickers.length) {
    let old = null;
    try { const o = await env.FEEDS.get('slates/nfl_kalshi_quotes.json'); if (o) old = JSON.parse(await o.text()); } catch (e) {}
    if (old && old.quotes && Object.keys(old.quotes).length) {
      await env.FEEDS.put('slates/nfl_kalshi_quotes.json', JSON.stringify({ quoted_at: new Date().toISOString(), quotes: {} }));
      return { cleared: true };
    }
    if (!old) {
      await env.FEEDS.put('slates/nfl_kalshi_quotes.json', JSON.stringify({ quoted_at: new Date().toISOString(), quotes: {} }));
      return { initialized_empty: true };
    }
    return { skipped: 'no tickers' };
  }
  let data;
  try {
    const r = await fetch(API.replace('%s', tickers.join(',')), { headers: { 'User-Agent': 'rixpicks-quotes/1.0' } });
    if (!r.ok) throw new Error('http ' + r.status);
    data = await r.json();
  } catch (e) { console.error('FAIL-CLOSED: kalshi fetch failed - keeping last-good'); return { failed: String(e).slice(0, 80) }; }
  if (!Array.isArray(data.markets)) { console.error('FAIL-CLOSED: unexpected payload'); return { failed: 'payload shape' }; }
  const quotes = {};
  for (const m of data.markets) {
    if (!m.ticker) continue;
    quotes[m.ticker] = { status: m.status, yes_bid: cents(m.yes_bid_dollars), yes_ask: cents(m.yes_ask_dollars), quoted_at: isoZ(m.updated_time) };
  }
  const payload = { quoted_at: new Date().toISOString(), quotes };
  await env.FEEDS.put('slates/nfl_kalshi_quotes.json', JSON.stringify(payload), { httpMetadata: { contentType: 'application/json' } });
  return { tickers: tickers.length, markets: Object.keys(quotes).length };
}
