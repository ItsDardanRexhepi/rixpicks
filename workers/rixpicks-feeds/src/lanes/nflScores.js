// nfl-scores lane - Worker port of scripts/nfl_scores_confirm.sh (nfl-scores-confirm workflow).
// Self-gates FREE on ESPN before spending a credit; bounded final chase (F3) for started games
// this feed still holds as not completed. Dormant without the THE_ODDS_API_KEY worker secret.
// Shadow: writes R2 nfl_scores.json only; credit reading goes to the run log + quota state,
// never the public artifact (LS-22).
import { getJson, prodJson, r2Json, putJson, sleep } from '../lib/util.js';
import { recordReading, quotaReading, tripwire } from '../lib/oddsQuota.js';

const ESPN_SB = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard';
const CHASE_HOURS = 5;
const NOPE = ['POSTPONED', 'CANCELED', 'CANCELLED', 'SUSPENDED'];

export async function runNflScores(env) {
  if (!env.THE_ODDS_API_KEY) return { dormant: 'THE_ODDS_API_KEY not set' };
  let sb = null;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try { sb = await getJson(ESPN_SB, { timeoutMs: 15000 }); break; }
    catch (e) { console.error(`nfl_scores ESPN gate probe attempt ${attempt} failed`); await sleep(2000); }
  }
  if (!sb) return { skipped: 'ESPN gate unavailable after 3 attempts - no credit spent' };
  const events = sb.events || [];
  const live = events.filter(e => { try { return e.status.type.state === 'in'; } catch (x) { return false; } }).length;
  // final chase: a started-but-not-completed game in our last artifact, kicked off within CHASE_HOURS
  let chase = 0;
  try {
    const prev = (await r2Json(env, 'nfl_scores.json')) || (await prodJson(env, '/nfl_scores.json'));
    const espn = {};
    for (const e of events) {
      try {
        const st = e.status.type;
        const side = {};
        for (const x of e.competitions[0].competitors) side[x.homeAway] = x.team.displayName.toLowerCase();
        espn[`${side.home}|${side.away}`] = st;
      } catch (x) { continue; }
    }
    const played = st => {
      const name = (String(st.name || '') + ' ' + String(st.description || '')).toUpperCase();
      if (NOPE.some(w => name.includes(w))) return false;
      return st.state === 'in' || (st.state === 'post' && st.completed === true);
    };
    const now = Date.now();
    for (const g of (prev && prev.games) || []) {
      const ko = Date.parse(String(g.commence_time || '').replace('Z', '+00:00'));
      if (isNaN(ko) || g.completed) continue;
      const age = now - ko;
      if (age < 0 || age > CHASE_HOURS * 3600000) continue;
      const st = espn[`${String(g.home_team || '').toLowerCase()}|${String(g.away_team || '').toLowerCase()}`];
      if (st && played(st)) chase++;
    }
  } catch (e) {}
  if (live === 0 && chase === 0) return { skipped: 'no live NFL - no credit spent' };
  const rem0 = await quotaReading(env);
  if (tripwire(rem0)) return { failed: 'quota tripwire' };
  const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 25000);
  let r;
  try { r = await fetch(`https://api.the-odds-api.com/v4/sports/americanfootball_nfl/scores/?daysFrom=1&apiKey=${env.THE_ODDS_API_KEY}`, { signal: ctl.signal }); }
  finally { clearTimeout(t); }
  if (!r.ok) return { failed: 'scores http ' + r.status };
  const remaining = r.headers.get('x-requests-remaining');
  const games = await r.json();
  if (!Array.isArray(games)) return { failed: 'scores payload shape' };
  await putJson(env, 'nfl_scores.json', {
    pulled_at_utc: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
    source: 'the-odds-api v4 nfl scores (daysFrom=1)', games });
  if (remaining != null) await recordReading(env, remaining);
  console.log(`nfl_scores: ${games.length} games, credits remaining: ${remaining}`);
  return { games: games.length, live, chase };
}
