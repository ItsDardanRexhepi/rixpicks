// extras lane - Worker port of scripts/extras_pull.sh (extras-sweep workflow, 2x/day).
// MLS/MMA/boxing h2h book pulls, 3 credits/run. A single sport failing is recorded inline as
// {"error": ...} and does not kill the run; the run fails only if ALL sports fail.
// Dormant without the THE_ODDS_API_KEY worker secret. Shadow: writes R2 extras_books.json only.
import { putJson, sleep } from '../lib/util.js';
import { recordReading, quotaReading, tripwire, ledgerCheckAndLog } from '../lib/oddsQuota.js';

const SPORTS = ['soccer_usa_mls', 'mma_mixed_martial_arts', 'boxing_boxing'];

export async function runExtras(env) {
  if (!env.THE_ODDS_API_KEY) return { dormant: 'THE_ODDS_API_KEY not set' };
  const rem0 = await quotaReading(env);
  if (tripwire(rem0)) return { failed: 'quota tripwire' };
  try { await ledgerCheckAndLog(env, SPORTS.join('+'), 'h2h', SPORTS.length); }
  catch (e) { console.error('extras:', String(e)); return { failed: 'monthly cap projection' }; }
  const out = { pulled_at_utc: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'), sports: {} };
  let ok = 0, lastRem = null;
  for (const s of SPORTS) {
    try {
      const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 25000);
      const r = await fetch(`https://api.the-odds-api.com/v4/sports/${s}/odds/?regions=us&markets=h2h&oddsFormat=american&apiKey=${env.THE_ODDS_API_KEY}`, { signal: ctl.signal });
      clearTimeout(t);
      const body = await r.json().catch(() => null);
      const rem = r.headers.get('x-requests-remaining');
      if (rem != null) lastRem = rem;
      if (r.status === 200 && Array.isArray(body)) { out.sports[s] = body; ok++; }
      else out.sports[s] = { error: `HTTP ${r.status}`, detail: body && typeof body === 'object' ? body : { body: String(body).slice(0, 200) } };
    } catch (e) {
      out.sports[s] = { error: 'fetch failed', detail: { body: String(e).slice(0, 200) } };
    }
    await sleep(1000);
  }
  if (lastRem != null) await recordReading(env, lastRem);
  await putJson(env, 'extras_books.json', out);
  const events = Object.values(out.sports).reduce((n, v) => n + (Array.isArray(v) ? v.length : 0), 0);
  if (ok < 1) { console.error('EXTRAS PULL TOTAL FAILURE - all sports errored'); return { failed: 'all sports errored' }; }
  return { ok_sports: ok, events };
}
