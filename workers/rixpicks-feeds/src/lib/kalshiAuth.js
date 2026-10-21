// Kalshi authenticated REST (lane 3 futures-switch gate): RSA-PSS/SHA256 over ts+method+path,
// base64 - the exact scheme scripts/futures_ws_listener.py uses (KALSHI-ACCESS-* headers).
// Secrets KALSHI_KEY_ID / KALSHI_PRIVATE_KEY arrive as Worker secrets (cf_feeds_secrets.yml);
// key material is NEVER logged. Without them every caller falls back to the unauthenticated
// public REST exactly as before - fail-open to the pre-auth behavior, never a dead lane.
let _keyPromise = null;
let _keyPem = null;

function pemToDer(pem) {
  const body = pem.replace(/-----(BEGIN|END)[^-]+-----/g, '').replace(/\s+/g, '');
  const bin = atob(body);
  const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  return buf;
}

// DER length bytes for PKCS#1 -> PKCS#8 wrap
function derLen(n) {
  if (n < 0x80) return [n];
  const bytes = [];
  while (n > 0) { bytes.unshift(n & 0xff); n >>= 8; }
  return [0x80 | bytes.length, ...bytes];
}

// Wrap a PKCS#1 RSAPrivateKey into a PKCS#8 PrivateKeyInfo (WebCrypto imports pkcs8 only).
function pkcs1ToPkcs8(pkcs1) {
  const algId = [0x30, 0x0d, 0x06, 0x09, 0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x01, 0x01, 0x05, 0x00];
  const octet = [0x04, ...derLen(pkcs1.length)];
  const inner = 3 + algId.length + octet.length + pkcs1.length; // version(3) + alg + octet hdr + key
  const out = new Uint8Array([0x30, ...derLen(inner), 0x02, 0x01, 0x00, ...algId, ...octet]);
  const full = new Uint8Array(out.length + pkcs1.length);
  full.set(out); full.set(pkcs1, out.length);
  return full;
}

async function importKey(pemRaw) {
  // GHA-seeded secrets sometimes carry literal \n escapes (same handling as the listener)
  const pem = pemRaw.includes('\\n') ? pemRaw.replace(/\\n/g, '\n') : pemRaw;
  let der = pemToDer(pem);
  if (/BEGIN RSA PRIVATE KEY/.test(pem)) der = pkcs1ToPkcs8(der);
  return crypto.subtle.importKey('pkcs8', der, { name: 'RSA-PSS', hash: 'SHA-256' }, false, ['sign']);
}

export function kalshiAuthed(env) {
  return !!(env.KALSHI_KEY_ID && env.KALSHI_PRIVATE_KEY);
}

// headers for one request; path is the path ONLY (no query), e.g. '/trade-api/v2/markets'
export async function kalshiHeaders(env, method, path) {
  if (!kalshiAuthed(env)) return { 'User-Agent': 'rix/1.0' };
  try {
    if (!_keyPromise || _keyPem !== env.KALSHI_PRIVATE_KEY) {
      _keyPem = env.KALSHI_PRIVATE_KEY;
      _keyPromise = importKey(env.KALSHI_PRIVATE_KEY);
    }
    const key = await _keyPromise;
    const ts = String(Date.now());
    const msg = new TextEncoder().encode(ts + method + path);
    const sig = await crypto.subtle.sign({ name: 'RSA-PSS', saltLength: 32 }, key, msg);
    const b64 = btoa(String.fromCharCode(...new Uint8Array(sig)));
    return {
      'KALSHI-ACCESS-KEY': env.KALSHI_KEY_ID,
      'KALSHI-ACCESS-TIMESTAMP': ts,
      'KALSHI-ACCESS-SIGNATURE': b64,
      'User-Agent': 'rix/1.0',
      'Content-Type': 'application/json',
    };
  } catch (e) {
    // unparseable key = unauthenticated mode, loudly (value never logged)
    console.error('kalshi auth: private key unusable, falling back to public REST:', String(e).slice(0, 80));
    return { 'User-Agent': 'rix/1.0' };
  }
}
