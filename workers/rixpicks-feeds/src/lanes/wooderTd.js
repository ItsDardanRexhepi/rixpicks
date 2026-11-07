// wooder-td lane - Worker port of scripts/wooder_td_feed.py (the wooder-td-tracker workflow's
// TD half; the futures-quote half is lanes/futuresQuotes.js). Reads the card pipeline's
// slates/nfl_latest.json (prod input), resolves ESPN event ids, polls per-event scoringPlays
// for pick-side TDs. Shadow: writes R2 slates/nfl_live.json only. Fail-soft per leg.
import { getJson, prodJson, putJson, sleep, ptDetail, etDay } from '../lib/util.js';

const ESPN_SB = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={d}&limit=50';
const ESPN_SUM = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={eid}';
const AL = { WSH: 'WAS' };

const norm = s => String(s || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

export async function runWooderTd(env) {
  let slate;
  try { slate = await prodJson(env, '/slates/nfl_latest.json'); }
  catch (e) { return { skipped: 'slate unreadable' }; }
  const legs = ((slate.dk || {}).singles) || [];
  const d = etDay();
  let sb;
  try { sb = await getJson(ESPN_SB.replace('{d}', d)); }
  catch (e) { return { failed: 'scoreboard unreadable' }; }
  const events = {};
  for (const ev of sb.events || []) {
    try {
      const comp = ev.competitions[0];
      const away = comp.competitors.find(c => c.homeAway === 'away');
      const home = comp.competitors.find(c => c.homeAway === 'home');
      const a = AL[away.team.abbreviation] || away.team.abbreviation;
      const h = AL[home.team.abbreviation] || home.team.abbreviation;
      events[`${a} @ ${h}`] = ev;
    } catch (e) { continue; }
  }
  const games = {}; const outLegs = [];
  for (const leg of legs) {
    const mu = leg.matchup, player = leg.player;
    const ev = events[mu];
    const rec = { player, team: leg.team, matchup: mu, price_c: leg.price_c,
      td_scored: false, td_count: 0, last_td: null };
    if (!ev) { rec.note = 'espn event unresolved'; outLegs.push(rec); continue; }
    const eid = ev.id;
    const comp = ev.competitions[0];
    const st = ev.status;
    games[eid] = { matchup: mu, espn_event_id: eid, commence: ev.date,
      status: st.type.state, detail: ptDetail(st.type.shortDetail || ''),
      score: (comp.competitors || []).map(c => `${c.team.abbreviation} ${c.score || '0'}`).join(' - ') };
    rec.espn_event_id = eid;
    try {
      const summ = await getJson(ESPN_SUM.replace('{eid}', eid));
      const np = norm(player);
      const hits = [];
      for (const sp of summ.scoringPlays || []) {
        const txt = sp.text || '';
        const ttype = norm((sp.type || {}).text || '');
        if (ttype.includes('touchdown') || norm(txt).includes('td')) {
          if (norm(txt).includes(np)) hits.push(txt);
        }
      }
      rec.td_count = hits.length;
      rec.td_scored = hits.length > 0;
      rec.last_td = hits.length ? hits[hits.length - 1] : null;
    } catch (ex) { rec.note = `summary fetch failed: ${String(ex).slice(0, 60)}`; }
    outLegs.push(rec);
    await sleep(150);
  }
  const out = { version: 1, generated_at: new Date().toISOString(), window: slate.window,
    legs: outLegs, games: Object.values(games) };
  await putJson(env, 'slates/nfl_live.json', out);
  return { legs: outLegs.length, td: outLegs.filter(l => l.td_scored).length, games: Object.keys(games).length };
}
