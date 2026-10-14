// rec-yards lane - Worker port of scripts/nfl_rec_yards.py (nfl-rec-yards workflow, every 6h).
// ESPN byathlete season receiving yards for the futures-card players. Fail-closed: a player
// missing from the feed is omitted (card renders Unavailable), never zero-filled; zero players
// parsed = no write. Shadow: writes R2 slates/nfl_rec_yards.json only.
import { getJson, putJson } from '../lib/util.js';

const NAMES = ['Mike Evans', 'Emeka Egbuka', 'Tetairoa McMillan', 'Trey McBride', 'Zay Flowers',
  'Chris Olave', 'Ladd McConkey', 'Drake London', 'Christian Watson', "Wan'Dale Robinson"];
const URL = 'https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/statistics/byathlete?season={s}&seasontype=2&sort=receiving.receivingYards:desc&limit=400';

export async function runRecYards(env, season = 2026) {
  let d;
  try { d = await getJson(URL.replace('{s}', String(season)), { headers: { 'User-Agent': 'Mozilla/5.0' }, timeoutMs: 30000 }); }
  catch (e) { return { failed: String(e).slice(0, 80) }; }
  let cat;
  try { cat = d.categories.find(c => c.name === 'receiving'); } catch (e) { return { failed: 'shape' }; }
  if (!cat) return { failed: 'no receiving category' };
  const iy = cat.names.indexOf('receivingYards');
  const players = {};
  for (const a of d.athletes || []) {
    const n = a.athlete && a.athlete.displayName;
    if (!NAMES.includes(n)) continue;
    const r = (a.categories || []).find(c => c.name === 'receiving');
    if (r && r.values[iy] != null) players[n] = { yards: Math.trunc(r.values[iy]), espn_id: a.athlete.id };
  }
  if (Object.keys(players).length < 1) return { refused: 'no players parsed - fail-closed, no write' };
  const doc = { source: 'ESPN season receiving yards (regular season to date)', season,
    fetched_at: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'), players };
  await putJson(env, 'slates/nfl_rec_yards.json', doc);
  return { players: Object.keys(players).length };
}
