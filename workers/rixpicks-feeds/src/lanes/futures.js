// futures lane - poll-based Worker port of scripts/futures_ws_listener.py's discovery+tick shape.
// Trades the WS's sub-second fidelity for CF-cron reliability (root kill of the 340-min
// self-respawning GHA runner + every-75s git-push churn). Same row shape:
//   {"ts","league","board":{"P:<question>":cents|"K:<ticker>":cents}}
// Shadow: writes R2 only (futures/current.json + futures/ticks/<day>/<hhmm>.jsonl).
// Kalshi leg (2026-10-14 futures-switch prep): when Worker secrets KALSHI_KEY_ID /
// KALSHI_PRIVATE_KEY are present the Kalshi reads are AUTHENTICATED (own rate bucket - the
// shared-IP 429 class goes away), paginated like the listener (4 pages, status=open), and the
// price basis is the listener's: yes_ask cents, NOT last/bid (the old basis made the parity
// kalshi_leg price_close structurally fail: ask vs last routinely differ >2c).
// Analysis-side repoint artifact: futures/ticks_recent.jsonl - rolling 48h CHANGED-KEYS-ONLY
// rows (first row after deploy is the full-board baseline), the exact shape of prod
// data/futures_ws_ticks.jsonl, served at /feeds/futures/ticks.jsonl for futures_247.py.
import { kalshiCoolingDown, tripKalshiCooldown, is429 } from '../lib/cooldown.js';
import { kalshiHeaders, kalshiAuthed } from '../lib/kalshiAuth.js';
const GAMMA = 'https://gamma-api.polymarket.com/events?slug=';
const KHOST = 'https://api.elections.kalshi.com';
const KPATH = '/trade-api/v2/markets';
const TICKS_RECENT_KEY = 'futures/ticks_recent.jsonl';
const TICKS_RECENT_H = 48;

async function getJson(url, headers, timeoutMs = 20000) {
  const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { headers: headers || { 'User-Agent': 'rix/1.0' }, signal: ctl.signal });
    if (!r.ok) throw new Error('http ' + r.status);
    return await r.json();
  } finally { clearTimeout(t); }
}
// prod ticks carry decimal cents (WS book prices); match the basis and precision.
const toCents = f => { const c = Math.round(f * 1000) / 10; return c > 0 && c < 100 ? c : null; };

async function polyBoard(slug) {
  const board = {}; const quality = {}; const book = {};
  try {
    const ev = await getJson(GAMMA + slug);
    const e = (ev || [])[0];
    if (!e) return { board, quality, book };
    if (e.endDate && e.endDate < new Date().toISOString()) return { board, quality, book }; // settled slug
    for (const m of e.markets || []) {
      let prs = m.outcomePrices; if (typeof prs === 'string') { try { prs = JSON.parse(prs || '[]'); } catch { prs = []; } }
      if (prs && prs.length && prs.every(p => parseFloat(p) === 0 || parseFloat(p) === 1)) continue; // settled market
      const q = m.question; if (!q) continue;
      // WS-listener basis is the book: prefer bestBid/bestAsk mid, then last trade, then outcomePrices
      let px = null;
      const bb = parseFloat(m.bestBid), ba = parseFloat(m.bestAsk);
      if (!isNaN(bb) && !isNaN(ba) && bb > 0 && ba > 0) px = (bb + ba) / 2;
      else if (!isNaN(parseFloat(m.lastTradePrice))) px = parseFloat(m.lastTradePrice);
      else if (prs && prs[0]) px = parseFloat(prs[0]);
      const c = px === null ? null : toCents(px);
      if (c) {
        board['P:' + q] = c;
        // illiquidity marker: a book wider than 25c has no knowable mid - parity excludes it
        if (!isNaN(bb) && !isNaN(ba)) { quality['P:' + q] = Math.round((ba - bb) * 1000) / 10; book['P:' + q] = [Math.round(bb * 1000) / 10, Math.round(ba * 1000) / 10]; }
      }
    }
  } catch (e) { console.error('poly discover/poll ERR', slug, String(e).slice(0, 100)); }
  return { board, quality, book };
}
async function kalshiBoard(env, series) {
  const board = {}; let err429 = false;
  for (const s of series || []) {
    let cursor = null;
    for (let page = 0; page < 4; page++) {   // listener parity: paginate up to 4 pages per series
      try {
        let url = `${KHOST}${KPATH}?series_ticker=${s}&status=open&limit=200`;
        if (cursor) url += `&cursor=${cursor}`;
        const d = await getJson(url, await kalshiHeaders(env, 'GET', KPATH));
        for (const m of d.markets || []) {
          // listener price basis: yes_ask (ticker channel), dollars preferred, cents fallback
          let f = parseFloat(m.yes_ask_dollars);
          let c = isNaN(f) ? null : toCents(f);
          if (c === null && m.yes_ask != null && m.yes_ask !== '') { const ci = parseFloat(m.yes_ask); c = ci > 0 && ci < 100 ? ci : null; }
          if (c) board['K:' + m.ticker] = c;
        }
        cursor = d.cursor;
        if (!cursor) break;
      } catch (e) {
        console.error('kalshi futures poll ERR', s, String(e).slice(0, 100));
        if (is429(e)) err429 = true;
        break;
      }
      await new Promise(r => setTimeout(r, 200));
    }
    if (err429) break;  // shared-egress limit: stop hammering, cool down
    await new Promise(r => setTimeout(r, 250)); // gentle pacing on the shared IP pool
  }
  if (err429) await tripKalshiCooldown(env, 'futures 429');
  return board;
}

// rolling changed-keys ticks (prod data/futures_ws_ticks.jsonl shape) for the analysis-side reader
async function appendRecentTicks(env, ts, current, prev) {
  try {
    let lines = [];
    let baseline = false;
    try { const o = await env.FEEDS.get(TICKS_RECENT_KEY); if (o) lines = (await o.text()).trim().split('\n').filter(Boolean); else baseline = true; }
    catch (e) { baseline = true; }
    if (!lines.length) baseline = true;
    const cutoff = new Date(Date.parse(ts) - TICKS_RECENT_H * 3600000).toISOString();
    lines = lines.filter(ln => { const t = ln.slice(7, 31); return t >= cutoff; }); // {"ts":"<iso>" - cheap prefix read
    let appended = 0;
    for (const [lg, ent] of Object.entries(current)) {
      const prevBoard = (prev[lg] || {}).board || {};
      const delta = {};
      for (const [k, v] of Object.entries(ent.board)) {
        if (baseline || prevBoard[k] !== v) delta[k] = v;
      }
      if (Object.keys(delta).length) { lines.push(JSON.stringify({ ts, league: lg, board: delta })); appended++; }
    }
    if (appended || baseline) await env.FEEDS.put(TICKS_RECENT_KEY, lines.join('\n') + '\n', { httpMetadata: { contentType: 'text/plain' } });
    return appended;
  } catch (e) { console.error('ticks_recent append ERR', String(e).slice(0, 100)); return -1; }
}

export async function runFutures(env) {
  let cfg;
  try { const o = await env.FEEDS.get('config/leagues.json'); cfg = o ? JSON.parse(await o.text())
      : JSON.parse(await (await fetch(env.PROD_BASE + '/config_leagues.json?cb=' + Date.now())).text()); }
  catch (e) { return { failed: 'config unreadable' }; }
  const ts = new Date().toISOString();
  const rows = []; const current = {}; const errs = []; const qualityAll = {}; const bookAll = {};
  const kalshiCool = await kalshiCoolingDown(env);
  let prev = {};
  try { const o = await env.FEEDS.get('futures/current.json'); if (o) prev = (JSON.parse(await o.text())).leagues || {}; } catch (e) {}
  for (const [lg, ent] of Object.entries(cfg.leagues || {})) {
    const fut = ent.futures || {};
    const pres = fut.poly_slug ? await polyBoard(fut.poly_slug) : { board: {}, quality: {}, book: {} };
    const pb = pres.board; Object.assign(qualityAll, pres.quality); Object.assign(bookAll, pres.book);
    const kb = kalshiCool ? {} : await kalshiBoard(env, fut.kalshi);
    // last-good carry: a failed leg never blanks the board - previous keys ride until fresh data
    const prevBoard = (prev[lg] || {}).board || {};
    const carryK = Object.keys(kb).length ? {} : Object.fromEntries(Object.entries(prevBoard).filter(([k]) => k.startsWith('K:')));
    const carryP = Object.keys(pb).length || !fut.poly_slug ? {} : Object.fromEntries(Object.entries(prevBoard).filter(([k]) => k.startsWith('P:')));
    if (fut.poly_slug && !Object.keys(pb).length) errs.push('poly:' + lg + (Object.keys(carryP).length ? '(carried)' : ''));
    if ((fut.kalshi || []).length && !Object.keys(kb).length) errs.push('kalshi:' + lg + (Object.keys(carryK).length ? '(carried)' : ''));
    const board = { ...carryP, ...carryK, ...pb, ...kb };
    if (!Object.keys(board).length) continue;
    rows.push(JSON.stringify({ ts, league: lg, board }));
    current[lg] = { ts, board };
  }
  if (!rows.length) return { skipped: 'no boards' };
  const day = ts.slice(0, 10), hhmm = ts.slice(11, 16).replace(':', '');
  await Promise.all([
    env.FEEDS.put('futures/current.json', JSON.stringify({ ts, leagues: current }), { httpMetadata: { contentType: 'application/json' } }),
    env.FEEDS.put(`futures/ticks/${day}/${hhmm}.jsonl`, rows.join('\n') + '\n'),
    env.FEEDS.put('futures/quality.json', JSON.stringify({ ts, spread_c: qualityAll, book_c: bookAll })),
  ]);
  const recent = await appendRecentTicks(env, ts, current, prev);
  // heartbeat, same shape as the GHA listener's
  await env.FEEDS.put('futures/heartbeat.json', JSON.stringify({ ts, mode: 'cf-cron-poll', leagues: Object.keys(current).length, kalshi_cooldown: kalshiCool, kalshi_authed: kalshiAuthed(env), leg_errors: errs }));
  return { leagues: Object.keys(current).length, keys: rows.reduce((n, r) => n + Object.keys(JSON.parse(r).board).length, 0), kalshi_authed: kalshiAuthed(env), recent_rows: recent };
}
