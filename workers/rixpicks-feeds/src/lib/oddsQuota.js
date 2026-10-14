// The Odds API quota discipline, Worker-side (port of scripts/ops_quota.py + core/budget.py's
// standing rule): no self-imposed cap; the only tripwire is the plan's 20,000 credits/month hard
// limit, enforced fail-loud. Readings are the provider's authoritative x-requests-remaining
// header, stored per PT month in R2 state/odds_quota.json (a reading from an earlier month is
// ignored - the provider resets credits on the 1st). Every paid pull is ledgered to R2
// state/odds_credits.jsonl (telemetry + monthly projection guard). Key material never logged.
import { r2Json, putJson, ptDate } from './util.js';

const QUOTA_KEY = 'state/odds_quota.json';
const LEDGER_KEY = 'state/odds_credits.jsonl';
export const TRIPWIRE_REMAINING = 200;
export const MONTHLY_PLAN_LIMIT = 20000;

const ptMonth = () => ptDate().slice(0, 7);

export async function quotaReading(env) {
  try {
    const d = await r2Json(env, QUOTA_KEY);
    if (d && Number.isInteger(d.last_remaining) && d.month === ptMonth()) return d.last_remaining;
  } catch (e) {}
  return null;
}

export async function recordReading(env, remaining) {
  const r = parseInt(remaining, 10);
  if (!Number.isInteger(r) || r < 0) return;
  await putJson(env, QUOTA_KEY, { last_remaining: r, month: ptMonth(), pt_date: ptDate(), at: new Date().toISOString() });
}

// free reading: GET /v4/sports does not count against the quota and returns x-requests-remaining
export async function freeReading(env) {
  try {
    const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 20000);
    const r = await fetch(`https://api.the-odds-api.com/v4/sports/?apiKey=${env.THE_ODDS_API_KEY}`, { signal: ctl.signal });
    clearTimeout(t);
    const rem = r.headers.get('x-requests-remaining');
    if (rem != null) { await recordReading(env, rem); return parseInt(rem, 10); }
  } catch (e) { console.error('odds free reading failed:', String(e).slice(0, 60)); }
  return null;
}

export function tripwire(remaining) {
  if (remaining != null && remaining < TRIPWIRE_REMAINING) {
    console.error(`HARD CAP TRIPWIRE: provider monthly quota nearly exhausted (${remaining} remaining, authoritative x-requests-remaining) - fail loud per standing rule 9/27`);
    return true;
  }
  return false;
}

// atomic-enough ledger for a single-cron worker: read, project, append, trim to this month
export async function ledgerCheckAndLog(env, sport, markets, credits) {
  let lines = [];
  try { const o = await env.FEEDS.get(LEDGER_KEY); if (o) lines = (await o.text()).trim().split('\n').filter(Boolean); } catch (e) {}
  const m = ptMonth();
  let monthUsed = 0;
  const kept = [];
  for (const ln of lines) {
    try { const d = JSON.parse(ln); if (String(d.local_date || '').startsWith(m)) { monthUsed += d.credits; kept.push(ln); } }
    catch (e) {}
  }
  if (monthUsed + credits > MONTHLY_PLAN_LIMIT)
    throw new Error(`credit cap: monthly ${monthUsed}+${credits} would exceed plan hard limit ${MONTHLY_PLAN_LIMIT}/mo (standing rule 9/27)`);
  kept.push(JSON.stringify({ ts: new Date().toISOString(), local_date: ptDate(), sport, markets, credits, lane: 'worker' }));
  await env.FEEDS.put(LEDGER_KEY, kept.join('\n') + '\n', { httpMetadata: { contentType: 'text/plain' } });
  return monthUsed + credits;
}
