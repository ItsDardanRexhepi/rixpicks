// odds lane - Worker port of the FEED-PULL half of scripts/refresh.sh (odds-refresh workflow):
// odds_prefill.py (h2h+links), odds_prefill_st.py (spreads/totals + pregame snapshot),
// odds_prefill_props.py (event-scoped player props). The HTML build half
// (build_gh_page_v2.py, 5.5k lines of Python) deliberately does NOT move in this pass -
// splitting feed-from-build is exactly what lets these pulls run here (CUTOVER_PLAN.md #4).
//
// Discipline, identical to the GHA lane:
//  - gates FREE on ESPN game proximity (live or starting within 2h) before any paid pull
//  - THE ODDS API KEY IS THE PAID KEY ONLY (worker secret THE_ODDS_API_KEY; no free-tier
//    fallback path exists - core/budget.py PAID_TIER with the 20K/mo plan)
//  - no self-imposed cap (standing rule 9/27); tripwire = authoritative x-requests-remaining
//    < 200, fail loud; with no reading for this PT month the free GET /v4/sports reading is
//    taken before any paid pull
//  - every paid pull is ledgered (R2 state/odds_credits.jsonl) with a monthly projection guard
// Dormant without the secret. Shadow: writes R2 slates/odds_prefill*.json only.
import { getJson, prodJson, r2Json, putJson, sleep } from '../lib/util.js';
import { quotaReading, recordReading, freeReading, tripwire, ledgerCheckAndLog } from '../lib/oddsQuota.js';

const BOOKS = 'fanduel,draftkings,betmgm,betrivers,espnbet,hardrockbet';
const CLEAN_BOOKS = ['fanduel', 'draftkings', 'espnbet', 'hardrockbet'];
const TEMPLATE_BOOKS = ['betmgm', 'betrivers'];
const MARKETS_BY_SPORT = {
  americanfootball_nfl: ['player_pass_yds', 'player_pass_tds', 'player_rush_yds',
    'player_reception_yds', 'player_receptions', 'player_anytime_td'],
  baseball_mlb: ['batter_home_runs', 'batter_hits', 'batter_total_bases', 'pitcher_strikeouts'],
};
const normPlayer = s => String(s || '').toLowerCase().replace(/[^a-z0-9]/g, '');

async function oddsGet(env, pathAndQuery) {
  const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 30000);
  try {
    const r = await fetch(`https://api.the-odds-api.com${pathAndQuery}&apiKey=${env.THE_ODDS_API_KEY}`,
      { headers: { 'User-Agent': 'curl/8' }, signal: ctl.signal });
    if (!r.ok) throw new Error('http ' + r.status);
    return { data: await r.json(), remaining: r.headers.get('x-requests-remaining'), last: r.headers.get('x-requests-last') };
  } finally { clearTimeout(t); }
}

// Game window check: any registry-league game live or starting within 2h (ESPN, free) -
// the same gate refresh.sh runs before any paid pull.
async function gameWindow(env, cfg) {
  const now = new Date();
  const d = new Date(now.getTime() - 4 * 3600000).toISOString().slice(0, 10).replace(/-/g, '');
  for (const v of Object.values(cfg.leagues || {})) {
    const lg = v.espn;
    if (!lg) continue;
    const prm = v.espn_params ? '&' + v.espn_params : '';
    let sb;
    try { sb = await getJson(`https://site.api.espn.com/apis/site/v2/sports/${lg}/scoreboard?dates=${d}${prm}`, { timeoutMs: 15000 }); }
    catch (e) { continue; }
    for (const e of sb.events || []) {
      const comps = [];
      if (e.competitions && e.competitions.length) comps.push(e.competitions[0]);
      for (const g of e.groupings || []) comps.push(...(g.competitions || []));
      for (const c of comps) {
        const st = ((c.status || {}).type) || {};
        const dt = e.date ? Date.parse(e.date.replace('Z', '+00:00')) : now.getTime();
        const delta = (dt - now.getTime()) / 1000;
        if (st.state === 'in' || (st.state === 'pre' && delta >= 0 && delta <= 7200)) return true;
      }
    }
    await sleep(80);
  }
  return false;
}

function prefillRows(data, awayHomeBooks) {
  for (const e of data) {
    const key = `${e.away_team}|${e.home_team}|${e.commence_time || ''}`; // J-090: game instance, never matchup
    const rec = awayHomeBooks.get(key) || { away: e.away_team, home: e.home_team, commence: e.commence_time, books: {} };
    for (const b of e.bookmakers || []) {
      const oc = ((b.markets || [{}])[0].outcomes) || [];
      const links = {}, mls = {};
      for (const o of oc) {
        let side = null;
        if (o.name === e.away_team) side = 'away';
        else if (o.name === e.home_team) side = 'home';
        else continue; // 3-way sports (soccer Draw) - never mislabel as home (J-099)
        if (o.link) links[side] = o.link;
        if (o.price != null) mls[side] = o.price;
      }
      const entry = { event: b.link };
      for (const [s, l] of Object.entries(links)) entry[`${s}_link`] = l;
      for (const [s, m] of Object.entries(mls)) entry[`${s}_ml`] = m;
      if (CLEAN_BOOKS.includes(b.key)) rec.books[b.key] = entry;
      else if (TEMPLATE_BOOKS.includes(b.key)) { rec.books.state_templates = rec.books.state_templates || {}; rec.books.state_templates[b.key] = entry; }
    }
    awayHomeBooks.set(key, rec);
  }
}

function stRows(data, sport, out) {
  for (const e of data) {
    const key = `${e.away_team}|${e.home_team}|${e.commence_time || ''}`;
    const rec = out.get(key) || { away: e.away_team, home: e.home_team, commence: e.commence_time,
      sport, provider_event_id: e.id, books: {} };
    for (const b of e.bookmakers || []) {
      const ent = {};
      for (const m of b.markets || []) {
        if (m.key === 'spreads') {
          for (const o of m.outcomes || []) {
            if (o.name === e.home_team) { ent.spread_home_pts = o.point; ent.spread_home_price = o.price; }
            else if (o.name === e.away_team) ent.spread_away_price = o.price;
          }
        } else if (m.key === 'totals') {
          for (const o of m.outcomes || []) {
            if (o.name === 'Over') { ent.total_pts = o.point; ent.over_price = o.price; }
            else if (o.name === 'Under') ent.under_price = o.price;
          }
        }
      }
      if (Object.keys(ent).length) rec.books[b.key] = ent;
    }
    out.set(key, rec);
  }
}

function parsePropsEvent(event) {
  const base = { id: event.id, sport_key: event.sport_key, commence_time: event.commence_time,
    home_team: event.home_team, away_team: event.away_team };
  const rows = new Map();
  for (const b of event.bookmakers || []) {
    for (const m of b.markets || []) {
      for (const o of m.outcomes || []) {
        const player = o.description || o.name;
        const pkey = normPlayer(player);
        if (!pkey) continue;
        const k = `${pkey}|${m.key}|${b.key}`;
        const row = rows.get(k) || { player, player_key: pkey, market: m.key, book: b.key,
          point: null, last_update: m.last_update };
        if (o.point != null) row.point = o.point;
        const side = String(o.name || '').toLowerCase();
        if (side) row[side] = o.price;
        rows.set(k, row);
      }
    }
  }
  return [...rows.values()].map(r => ({ ...base, ...r }));
}

export async function runOdds(env) {
  if (env.ODDS_LANE !== 'on') return { dormant: 'ODDS_LANE off' };
  if (!env.THE_ODDS_API_KEY) return { dormant: 'THE_ODDS_API_KEY not set' };
  let cfg, man;
  try { cfg = (await r2Json(env, 'config/leagues.json')) || (await prodJson(env, '/config_leagues.json')); }
  catch (e) { return { failed: 'config unreadable' }; }
  try { man = await prodJson(env, '/manifest.json'); }
  catch (e) { return { failed: 'manifest unreadable' }; }
  if (!(await gameWindow(env, cfg))) return { skipped: 'no live/imminent game' };
  // quota: stored reading for this PT month, else the free reading; tripwire before any paid pull
  let rem = await quotaReading(env);
  if (rem == null) {
    rem = await freeReading(env);
    if (rem == null) return { failed: 'QUOTA READING UNAVAILABLE - no paid pull without one' };
    console.log('odds quota: free reading taken (GET /v4/sports) and recorded for this month');
  }
  if (tripwire(rem)) return { failed: 'quota tripwire' };
  const reg = cfg.leagues || {};
  const sports = [...new Set((man.picks || []).map(p => ((reg[p.league || ''] || {}).odds_api) || 'baseball_mlb'))].sort();
  if (!sports.length) return { skipped: 'no carded sports' };
  // --- h2h prefill (odds_prefill.py) ---
  const h2h = new Map();
  let lastRem = null;
  for (const sport of sports) {
    try {
      await ledgerCheckAndLog(env, sport, 'h2h', 1);
      const { data, remaining } = await oddsGet(env, `/v4/sports/${sport}/odds/?regions=us&markets=h2h&oddsFormat=american&includeLinks=true&includeSids=true&bookmakers=${BOOKS}`);
      if (remaining != null) lastRem = remaining;
      console.log(`odds h2h ${sport}: ${data.length} events, credits remaining ${remaining}`);
      prefillRows(data, h2h);
    } catch (e) { console.error(`odds h2h ${sport} failed: ${String(e).slice(0, 80)}`); }
  }
  await putJson(env, 'slates/odds_prefill.json', [...h2h.values()]);
  // --- spreads/totals prefill + pregame snapshot (odds_prefill_st.py) ---
  const st = new Map();
  for (const sport of sports) {
    try {
      await ledgerCheckAndLog(env, sport, 'spreads,totals', 2);
      const { data, remaining } = await oddsGet(env, `/v4/sports/${sport}/odds/?regions=us&markets=spreads,totals&oddsFormat=american&bookmakers=${BOOKS}`);
      if (remaining != null) lastRem = remaining;
      console.log(`odds st ${sport}: ${data.length} events, credits remaining ${remaining}`);
      stRows(data, sport, st);
    } catch (e) { console.error(`odds st ${sport} failed: ${String(e).slice(0, 80)}`); }
  }
  const stList = [...st.values()];
  await putJson(env, 'slates/odds_prefill_st.json', stList);
  // pregame snapshot: first pull BEFORE commence freezes a game's lines forever
  try {
    const now = new Date();
    const snapList = (await r2Json(env, 'slates/odds_prefill_st_pregame.json')) || [];
    const snap = new Map(snapList.map(r0 => [[r0.sport || '', r0.away, r0.home, r0.commence || ''].join('|'), r0]));
    for (const r of stList) {
      const gk = [r.sport, r.away, r.home, r.commence || ''].join('|');
      if (snap.has(gk)) continue;
      const ct = Date.parse(String(r.commence || '').replace('Z', '+00:00'));
      if (!isNaN(ct) && ct > now.getTime()) snap.set(gk, { ...r, snapshot_at: now.toISOString() });
    }
    await putJson(env, 'slates/odds_prefill_st_pregame.json', [...snap.values()]);
  } catch (e) { console.error('odds pregame snapshot failed:', String(e).slice(0, 80)); }
  // --- props (odds_prefill_props.py): in-window NFL/MLB events from the st pull ---
  let jobs = null;
  try {
    const j = await prodJson(env, '/slates/props_jobs.json');
    const m = {};
    for (const v of Object.values(j.leagues || {})) if (v.sport && v.markets && v.markets.length) m[v.sport] = v.markets;
    jobs = Object.keys(m).length ? m : null;
  } catch (e) {}
  const nowMs = Date.now();
  const bySport = {};
  for (const r of stList) {
    if (!['americanfootball_nfl', 'baseball_mlb'].includes(r.sport) || !r.provider_event_id) continue;
    const ct = Date.parse(String(r.commence || '').replace('Z', '+00:00'));
    if (isNaN(ct)) continue;
    if (ct - nowMs > 7200000 || nowMs - ct > 14400000) continue;
    (bySport[r.sport] = bySport[r.sport] || []).push(r.provider_event_id);
  }
  let propsRows = []; let propsEvents = 0; const propsSports = Object.keys(bySport);
  for (const [sport, ids] of Object.entries(bySport)) {
    const markets = (jobs && jobs[sport]) || MARKETS_BY_SPORT[sport] || [];
    if (!markets.length) continue;
    for (const eid of [...new Set(ids)]) {
      try {
        await ledgerCheckAndLog(env, sport, markets.join(','), markets.length); // worst case; empty markets are not charged
        const { data, remaining, last } = await oddsGet(env, `/v4/sports/${sport}/events/${eid}/odds?regions=us&markets=${markets.join(',')}&oddsFormat=american`);
        if (remaining != null) lastRem = remaining;
        console.log(`odds props ${sport}/${eid}: credits used ${last}, remaining ${remaining}`);
        if (!data) continue;
        const rows = parsePropsEvent(data).map(r => ({ ...r, provider_event_id: eid }));
        propsRows = propsRows.concat(rows);
        propsEvents++;
      } catch (e) { console.error(`odds props ${sport}/${eid} failed: ${String(e).slice(0, 80)}`); }
      await sleep(200);
    }
  }
  if (propsSports.length) {
    let existing = [];
    try { existing = ((await r2Json(env, 'slates/odds_prefill_props.json')) || {}).props || []; } catch (e) {}
    existing = existing.filter(r => !propsSports.includes(r.sport_key));
    await putJson(env, 'slates/odds_prefill_props.json', {
      sport_key: propsSports[propsSports.length - 1], regions: 'us',
      markets: (jobs && jobs[propsSports[propsSports.length - 1]]) || MARKETS_BY_SPORT[propsSports[propsSports.length - 1]] || [],
      props: existing.concat(propsRows) });
  }
  if (lastRem != null) await recordReading(env, lastRem);
  return { sports, h2h_games: h2h.size, st_games: st.size, props_events: propsEvents, props_rows: propsRows.length, remaining: lastRem };
}
