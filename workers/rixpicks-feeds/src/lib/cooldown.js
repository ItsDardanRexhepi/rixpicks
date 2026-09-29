// Shared-egress rate-limit discipline (diag 9/29 05:16Z: api.elections.kalshi.com 429s from
// CF's shared IP pool). One 429 parks the Kalshi legs for COOLDOWN_MS instead of hammering;
// last-good data carries the board meanwhile (fail-closed continuity, never a cold state).
const KEY = 'state/kalshi_cooldown.json';
export const COOLDOWN_MS = 10 * 60 * 1000;
export async function kalshiCoolingDown(env) {
  try {
    const o = await env.FEEDS.get(KEY);
    if (!o) return false;
    const until = JSON.parse(await o.text()).until || 0;
    return Date.now() < until;
  } catch (e) { return false; }
}
export async function tripKalshiCooldown(env, why) {
  try {
    await env.FEEDS.put(KEY, JSON.stringify({ until: Date.now() + COOLDOWN_MS, why: String(why).slice(0, 80), at: new Date().toISOString() }));
  } catch (e) {}
}
export function is429(e) { return String(e).includes('429'); }
