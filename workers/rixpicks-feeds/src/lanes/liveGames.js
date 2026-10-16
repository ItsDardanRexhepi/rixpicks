// live-games lane - Worker port of scripts/live_games.py (+ core/timeouts.py).
// Registry-driven ESPN scoreboards; keeps in-progress, pre<=2h, final<=4h; per-team timeouts
// for in-progress football/basketball/hockey. Shadow: writes R2 slates/live_games.json only.
// Fail-closed per league and per game; 0-game overwrite refused while prod is carded or the
// previous artifact had games (same guard as the script).
import { getJson, prodJson, r2Json, putJson, sleep, ptDetail, etDay, ptDate, PY_UA } from '../lib/util.js';

const SB = 'https://site.api.espn.com/apis/site/v2/sports/{lg}/scoreboard?dates={d}{prm}';
const CORE = 'https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/events/{eid}/competitions/{eid}/situation';
const TO_PREFIXES = ['football/', 'basketball/', 'hockey/'];
const MAX_IN_AGE = 6 * 3600; // seconds (script default; tennis override is the same value)
const AL = { WSH: 'WAS' };

function toInt(v) {
  if (typeof v === 'boolean') return null;
  if (Number.isInteger(v)) return v;
  if (v && typeof v === 'object') {
    for (const k of ['timeoutsRemainingCurrent', 'timeoutsCurrent']) if (Number.isInteger(v[k])) return v[k];
  }
  return null;
}
async function fetchTimeouts(espnPath, eid) {
  try {
    const [sport, league] = espnPath.split('/', 2);
    const d = await getJson(CORE.replace(/\{sport\}/, sport).replace(/\{league\}/, league).replace(/\{eid\}/g, eid), { timeoutMs: 15000 });
    return [toInt(d.awayTimeouts), toInt(d.homeTimeouts)];
  } catch (e) { return [null, null]; }
}

export async function runLiveGames(env) {
  let cfg;
  try { cfg = (await r2Json(env, 'config/leagues.json')) || (await prodJson(env, '/config_leagues.json')); }
  catch (e) { return { failed: 'config unreadable' }; }
  const now = new Date();
  const d = etDay(now);
  const outLeagues = []; let nGames = 0;
  for (const [key, v] of Object.entries(cfg.leagues || {})) {
    const lg = v.espn;
    if (!lg) continue;
    const prm = v.espn_params ? '&' + v.espn_params : '';
    let sb;
    try { sb = await getJson(SB.replace('{lg}', lg).replace('{d}', d).replace('{prm}', prm), { headers: { 'User-Agent': PY_UA } }); }
    catch (e) { console.error(`live_games league ${key} fetch failed: ${String(e).slice(0, 80)}`); continue; }
    const games = [];
    for (const ev of sb.events || []) {
      const comps = [];
      if (ev.competitions && ev.competitions.length) comps.push(ev.competitions[0]);
      for (const g of ev.groupings || []) comps.push(...(g.competitions || []));
      for (const c of comps) {
        try {
          const st = ((c.status || {}).type) || {};
          const state = st.state || '';
          const dt = ev.date ? new Date(ev.date.replace('Z', '+00:00')) : null;
          const delta = dt ? (dt.getTime() - now.getTime()) / 1000 : null;
          const keep = (state === 'in' && delta != null && delta >= -MAX_IN_AGE)
            || (state === 'pre' && delta != null && delta >= 0 && delta <= 7200)
            || (state === 'post' && delta != null && delta >= -14400 && delta <= 0);
          if (!keep) continue;
          const teams = {};
          for (const comp of c.competitors || []) {
            const t = comp.team || comp.athlete || {};
            let ab = t.abbreviation || t.displayName || '';
            ab = AL[ab] || ab;
            teams[comp.homeAway] = [ab, comp.score || '0'];
          }
          if (!teams.away || !teams.home || !teams.away[0] || !teams.home[0]) continue;
          const [aab, asc] = teams.away, [hab, hsc] = teams.home;
          let eid = String(c.id || ev.id || '');
          if (games.some(g => g.espn_event_id === eid))
            eid = `${eid}-${aab.toLowerCase().replace(/ /g, '')}-${hab.toLowerCase().replace(/ /g, '')}`;
          const rec = { espn_event_id: eid, matchup: `${aab} @ ${hab}`, commence: ev.date,
            status: state, detail: ptDetail(st.shortDetail || ''), score: `${aab} ${asc} - ${hab} ${hsc}` };
          if (state === 'in' && TO_PREFIXES.some(p => lg.startsWith(p))) {
            const [aTo, hTo] = await fetchTimeouts(lg, ev.id);
            rec.away_to = aTo; rec.home_to = hTo;
            await sleep(100);
          }
          games.push(rec);
        } catch (e) { continue; }
      }
    }
    if (games.length) { outLeagues.push({ league: key, games }); nGames += games.length; }
    await sleep(100);
  }
  if (nGames === 0) {
    let carded = false, prevGames = 0;
    try {
      const man = await prodJson(env, '/manifest.json');
      carded = !!(man.picks && man.picks.length) && String(man.date || '') === ptDate(now);
    } catch (e) {}
    try {
      const prev = await r2Json(env, 'slates/live_games.json');
      if (prev) prevGames = (prev.leagues || []).reduce((n, l) => n + (l.games || []).length, 0);
    } catch (e) {}
    if (carded || prevGames) return { refused: `0-game overwrite (carded=${carded}, prev_games=${prevGames})` };
  }
  const out = { version: 1, generated_at: now.toISOString(), leagues: outLeagues };
  await putJson(env, 'slates/live_games.json', out);
  return { leagues: outLeagues.length, games: nGames };
}
