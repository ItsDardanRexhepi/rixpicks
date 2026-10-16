// futures-quotes lane - Worker port of scripts/futures_quotes.py (the wooder-td-tracker /
// odds-refresh workflows' carded-futures quote half). Prod writes quotes INLINE into
// futures.json; shadow writes the quoted rows to R2 futures/futures_quotes.json only.
// Kalshi reads go authenticated when the worker secrets are set. The .com gamma leg stays
// on public gamma per the venue-lock ruling (main 9/27 2:44 PM, option 3).
import { getJson, prodJson, putJson, sleep } from '../lib/util.js';
import { kalshiHeaders } from '../lib/kalshiAuth.js';
import { kalshiCoolingDown, tripKalshiCooldown, is429 } from '../lib/cooldown.js';

const KPATH = '/trade-api/v2/markets';
const KHOST = 'https://api.elections.kalshi.com';

// carded market -> (kalshi series, ticker suffix abbr) ; abbr = Kalshi team code
const MAP = {
  'Super Bowl LXI Champion': ['KXSB', { sf: 'SF', kc: 'KC', sea: 'SEA' }],
  'AFC West Champion': ['KXNFLAFCWEST', { kc: 'KC' }],
  'NFC West Champion': ['KXNFLNFCWEST', { sf: 'SF' }],
  'NFC East Champion': ['KXNFLNFCEAST', { phi: 'PHI' }],
  'NFC North Champion': ['KXNFLNFCNORTH', { min: 'MIN' }],
  'AFC Champion': ['KXNFLAFCCHAMP', { buf: 'BUF' }],
  'NFC Champion': ['KXNFLNFCCHAMP', { sf: 'SF' }],
  'WNBA Championship': ['KXWNBA', { min: 'MIN' }],
};
const SEASON = { KXSB: '27', KXNFLAFCWEST: '27', KXNFLNFCWEST: '27', KXNFLNFCEAST: '27',
  KXNFLNFCNORTH: '27', KXNFLAFCCHAMP: '27', KXNFLNFCCHAMP: '27', KXWNBA: '26' };

async function pullSeries(env, series) {
  const out = {};
  let cursor = null;
  for (let i = 0; i < 4; i++) {
    let url = `${KHOST}${KPATH}?series_ticker=${series}&limit=200`;
    if (cursor) url += `&cursor=${cursor}`;
    const d = await getJson(url, { headers: await kalshiHeaders(env, 'GET', KPATH) });
    for (const m of d.markets || []) out[m.ticker] = m;
    cursor = d.cursor;
    if (!cursor) break;
    await sleep(200);
  }
  return out;
}

export async function runFuturesQuotes(env) {
  let rows;
  try { rows = await prodJson(env, '/futures.json'); }
  catch (e) { return { skipped: 'prod futures.json unreadable' }; }
  if (!Array.isArray(rows)) return { skipped: 'unexpected futures shape' };
  const cache = {}; let kq = 0, com = 0;
  const cool = await kalshiCoolingDown(env);
  for (const r of rows) {
    const ent = MAP[r.market];
    if (!ent || !(r.abbr in ent[1])) { r.kalshi_quote = null; continue; }
    if (cool) continue; // keep prod's last quote fields; cooldown = no kalshi reads this cycle
    const [series, teammap] = ent;
    const ticker = `${series}-${SEASON[series]}-${teammap[r.abbr]}`;
    if (!(series in cache)) {
      try { cache[series] = await pullSeries(env, series); }
      catch (ex) {
        console.error(`futures_quotes SERIES ERR ${series}: ${String(ex).slice(0, 80)}`);
        if (is429(ex)) await tripKalshiCooldown(env, 'futures_quotes 429');
        cache[series] = {};
      }
      await sleep(250);
    }
    const m = cache[series][ticker];
    if (!m || m.status !== 'active') { r.kalshi_quote = null; continue; }
    const bid = m.yes_bid_dollars, ask = m.yes_ask_dollars;
    const mid = bid && ask ? Math.round((parseFloat(bid) + parseFloat(ask)) * 50) : null;
    r.kalshi_quote = { ticker, bid_c: bid ? Math.round(parseFloat(bid) * 100) : null,
      ask_c: ask ? Math.round(parseFloat(ask) * 100) : null, mid_c: mid, status: m.status,
      quoted_at: new Date().toISOString().replace(/\.\d{3}/, '') };
    kq++;
  }
  // .com gamma leg (venue-lock: public gamma only, never .us data on a .com board)
  for (const r of rows) {
    const pc = r.polymarket_com;
    if (!pc || !pc.url) continue;
    const slug = pc.url.replace(/\/+$/, '').split('/').pop();
    try {
      const ev = await getJson(`https://gamma-api.polymarket.com/events?slug=${slug}`);
      const mkts = (ev && ev[0] && ev[0].markets) || [];
      const lbl = (pc.market_label || '').toLowerCase();
      const kw = (r.poly_kw || '').toLowerCase();
      let m = null;
      if (lbl) m = mkts.find(c => ((c.question || '').toLowerCase()) === lbl) || null;
      if (!m && lbl) m = mkts.find(c => (c.question || '').toLowerCase().includes(lbl)) || null;
      if (!m && kw) m = mkts.find(c => (c.question || '').toLowerCase().includes(kw)) || null;
      if (!m) { console.error(`futures_quotes COM-NOMATCH ${slug}`); continue; }
      const outs = JSON.parse(m.outcomes || '[]');
      const prs = JSON.parse(m.outcomePrices || '[]');
      let idx = outs.findIndex(o => String(o).toLowerCase() === 'yes');
      if (idx < 0) idx = 0;
      const pr = parseFloat(prs[idx]);
      if (!(pr > 0 && pr < 1)) { console.error(`futures_quotes COM-BADPX ${slug}: ${pr}`); continue; }
      pc.cents = Math.round(pr * 100);
      pc.quoted_at = new Date().toISOString().replace(/\.\d{3}/, '');
      com++;
    } catch (ex) { console.error(`futures_quotes COM-ERR ${slug}: ${String(ex).slice(0, 80)}`); }
    await sleep(150);
  }
  const payload = { quoted_at: new Date().toISOString(), rows };
  await putJson(env, 'futures/futures_quotes.json', payload);
  return { rows: rows.length, kalshi_quotes: kq, com_quotes: com, cooldown: cool };
}
