// Shared lane plumbing: timed JSON fetches, prod/R2 reads, R2 JSON writes.
export const DEFAULT_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) RixPicks/1.0';
export const PY_UA = 'python-urllib/3.10'; // some ESPN endpoints key on UA (see /diag note)

export async function getJson(url, { headers, timeoutMs = 20000 } = {}) {
  const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { headers: headers || { 'User-Agent': PY_UA }, signal: ctl.signal });
    if (!r.ok) throw new Error('http ' + r.status);
    return await r.json();
  } finally { clearTimeout(t); }
}

export async function prodJson(env, path) {
  return getJson(env.PROD_BASE + path + (path.includes('?') ? '&' : '?') + 'cb=' + Date.now());
}

export async function r2Json(env, key) {
  const o = await env.FEEDS.get(key);
  return o ? JSON.parse(await o.text()) : null;
}

export async function putJson(env, key, obj) {
  await env.FEEDS.put(key, JSON.stringify(obj, null, 1), { httpMetadata: { contentType: 'application/json' } });
}

export const sleep = ms => new Promise(r => setTimeout(r, ms));
export const isoZ = () => new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');

// owner rule 9/27: ALL times render PT, never ET. ESPN shortDetail arrives ET - shift -3h, suffix PT.
export function ptDetail(s) {
  if (!s) return s;
  return s.replace(/(\d{1,2}):(\d{2}) ([AP])M E[DS]T/g, (m0, h, mi, ap) => {
    let h24 = (parseInt(h, 10) % 12) + (ap === 'P' ? 12 : 0);
    h24 = (h24 + 21) % 24;
    const ap2 = h24 < 12 ? 'AM' : 'PM';
    return `${h24 % 12 || 12}:${mi} ${ap2} PT`;
  });
}

// ET game day (same fixed -4h the GHA scripts use)
export function etDay(now = new Date()) {
  const d = new Date(now.getTime() - 4 * 3600000);
  return d.toISOString().slice(0, 10).replace(/-/g, '');
}

// PT date/month (fixed -7h, matching the scripts' PDT math)
export function ptDate(now = new Date()) {
  return new Date(now.getTime() - 7 * 3600000).toISOString().slice(0, 10);
}
