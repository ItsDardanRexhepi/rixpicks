"""poly_us.py - authenticated Polymarket US reads (owner directive Sep 27: replace every Polymarket
public feed with the authenticated API; key lives in repo secrets POLYMARKET_API_KEY_ID /
POLYMARKET_API_SECRET, placed by the watcher via vault - secrets never move to agents).
Read-only: events/markets/quotes only. ZERO trades - no order endpoints are ever called.
Fail-closed everywhere: missing secrets, auth failure, network error, or shape drift -> None
(chip drops / quote stays null), never a guessed or stale-wearing value.

Auth scheme (docs.polymarket.us/api-reference/authentication): ed25519 signature over
"{timestamp_ms}{METHOD}{path}", headers X-PM-Access-Key / X-PM-Timestamp / X-PM-Signature.
"""
import base64, json, os, time, urllib.request

BASE = 'https://gateway.polymarket.us'

def _headers(method, path):
    kid = os.environ.get('POLYMARKET_API_KEY_ID')
    sec = os.environ.get('POLYMARKET_API_SECRET')
    if not kid or not sec:
        return None
    from cryptography.hazmat.primitives.asymmetric import ed25519
    pk = ed25519.Ed25519PrivateKey.from_private_bytes(base64.b64decode(sec)[:32])
    ts = str(int(time.time() * 1000))
    sig = base64.b64encode(pk.sign(f'{ts}{method}{path}'.encode())).decode()
    return {'X-PM-Access-Key': kid, 'X-PM-Timestamp': ts, 'X-PM-Signature': sig,
            'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}

def get_json(path):
    h = _headers('GET', path)
    if h is None:
        return None
    try:
        req = urllib.request.Request(BASE + path, headers=h)
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.load(r)
    except Exception:
        return None

def event_by_slug(slug):
    """Authenticated GET /v1/events/slug/{slug} -> event dict or None."""
    j = get_json('/v1/events/slug/' + slug)
    return (j or {}).get('event')

def gamma_shaped(slug):
    """Gateway event normalized to the legacy gamma-api shape consumers were written against:
    a one-element list whose event carries markets with outcomes/outcomePrices as JSON strings
    and sportsMarketType=='moneyline' on moneyline markets. Lets call sites swap transport
    without rewriting their matching/parsing logic."""
    ev = event_by_slug(slug)
    if not ev:
        return None
    mkts = []
    for m in ev.get('markets') or []:
        m2 = dict(m)
        if (m2.get('marketType') or '').lower() == 'moneyline' and not m2.get('sportsMarketType'):
            m2['sportsMarketType'] = 'moneyline'
        if isinstance(m2.get('outcomes'), list):
            m2['outcomes'] = json.dumps(m2['outcomes'])
        if isinstance(m2.get('outcomePrices'), list):
            m2['outcomePrices'] = json.dumps(m2['outcomePrices'])
        mkts.append(m2)
    ev2 = dict(ev)
    ev2['markets'] = mkts
    return [ev2]

def pick_side_cents(event, want_last_names):
    """Moneyline pick-side price in cents from a gateway event (outcomePrices are dollar strings,
    parallel to outcomes). None when no moneyline market or no side match."""
    if not event:
        return None
    cands = [m for m in (event.get('markets') or [])
             if (m.get('marketType') or '').lower() == 'moneyline'
             or (m.get('sportsMarketType') or '').lower() == 'moneyline']
    if not cands:
        return None
    m = cands[0]
    outs = m.get('outcomes') or []
    prs = m.get('outcomePrices') or []
    if isinstance(outs, str):
        outs = json.loads(outs)
    if isinstance(prs, str):
        prs = json.loads(prs)
    want = {w.lower() for w in want_last_names if w}
    for o, p in zip(outs, prs):
        if str(o).lower() in want:
            try:
                return round(float(p) * 100)
            except (TypeError, ValueError):
                return None
    return None
