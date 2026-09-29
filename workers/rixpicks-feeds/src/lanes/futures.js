// futures lane - poll-based Worker port of scripts/futures_ws_listener.py's discovery+tick shape.
// Trades the WS's sub-second fidelity for CF-cron reliability (root kill of the 340-min
// self-respawning GHA runner + every-75s git-push churn). Same row shape:
//   {"ts","league","board":{"P:<question>":cents|"K:<ticker>":cents}}
// Shadow: writes R2 only (futures/current.json + futures/ticks/<day>/<hhmm>.jsonl).
// Cutover (FUTURES_REPO_BATCH=on): ALSO commits an hourly compacted batch to the repo
// data/futures_ws_ticks.jsonl via the contents API, so analysis-side readers keep working
// unchanged while they repoint. 24 commits/day instead of ~1150.
import { kalshiCoolingDown, tripKalshiCooldown, is429 } from '../lib/cooldown.js';
const GAMMA = 'https://gamma-api.polymarket.com/events?slug=';
const KAPI = 'https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker=%s&limit=200&status=open';

async function getJson(url, timeoutMs = 20000) {
  const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { headers: { 'User-Agent': 'rix/1.0' }, signal: ctl.signal });
    if (!r.ok) throw new Error('http ' + r.status);
    return await r.json();
  } finally { clearTimeout(t); }
}
const toCents = f => { const c = Math.round(f * 100); return c > 0 && c < 100 ? c : null; };

async function polyBoard(slug) {
  const board = {};
  try {
    const ev = await getJson(GAMMA + slug);
    const e = (ev || [])[0];
    if (!e) return board;
    if (e.endDate && e.endDate < new Date().toISOString()) return board; // settled slug
    for (const m of e.markets || []) {
      let prs = m.outcomePrices; if (typeof prs === 'string') { try { prs = JSON.parse(prs || '[]'); } catch { prs = []; } }
      if (prs && prs.length && prs.every(p => parseFloat(p) === 0 || parseFloat(p) === 1)) continue; // settled market
      const q = m.question; if (!q || !prs || !prs[0]) continue;
      const c = toCents(parseFloat(prs[0]));
      if (c) board['P:' + q] = c;
    }
  } catch (e) { console.error('poly discover/poll ERR', slug, String(e).slice(0, 100)); }
  return board;
}
async function kalshiBoard(env, series) {
  const board = {}; let err429 = false;
  for (const s of series || []) {
    try {
      const d = await getJson(KAPI.replace('%s', s));
      for (const m of d.markets || []) {
        const f = parseFloat(m.yes_bid_dollars);
        const c = isNaN(f) ? null : toCents(f);
        if (c) board['K:' + m.ticker] = c;
      }
    } catch (e) {
      console.error('kalshi futures poll ERR', s, String(e).slice(0, 100));
      if (is429(e)) { err429 = true; break; }  // shared-egress limit: stop hammering, cool down
    }
    await new Promise(r => setTimeout(r, 250)); // gentle pacing on the shared IP pool
  }
  if (err429) await tripKalshiCooldown(env, 'futures 429');
  return board;
}

export async function runFutures(env) {
  let cfg;
  try { const o = await env.FEEDS.get('config/leagues.json'); cfg = o ? JSON.parse(await o.text())
      : JSON.parse(await (await fetch(env.PROD_BASE + '/config_leagues.json?cb=' + Date.now())).text()); }
  catch (e) { return { failed: 'config unreadable' }; }
  const ts = new Date().toISOString();
  const rows = []; const current = {}; const errs = [];
  const kalshiCool = await kalshiCoolingDown(env);
  let prev = {};
  try { const o = await env.FEEDS.get('futures/current.json'); if (o) prev = (JSON.parse(await o.text())).leagues || {}; } catch (e) {}
  for (const [lg, ent] of Object.entries(cfg.leagues || {})) {
    const fut = ent.futures || {};
    const pb = fut.poly_slug ? await polyBoard(fut.poly_slug) : {};
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
  ]);
  // heartbeat, same shape as the GHA listener's
  await env.FEEDS.put('futures/heartbeat.json', JSON.stringify({ ts, mode: 'cf-cron-poll', leagues: Object.keys(current).length, kalshi_cooldown: kalshiCool, leg_errors: errs }));
  return { leagues: Object.keys(current).length, keys: rows.reduce((n, r) => n + Object.keys(JSON.parse(r).board).length, 0) };
}
