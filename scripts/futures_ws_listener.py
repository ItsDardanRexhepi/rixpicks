#!/usr/bin/env python3
"""Futures WS listener (builder spec v2, 2026-09-28): persistent Polymarket + Kalshi
outright-board tick writer. Appends futures_board_snapshots.jsonl-shaped rows
({"ts","league","board":{"P:<q>":cents|"K:<ticker>":cents}}) to data/futures_ws_ticks.jsonl
and git-pushes on a cadence (Option A transport). Dumb tick writer - trip logic stays
analysis-side (futures_247.py reads unchanged). Kalshi auth from env KALSHI_KEY_ID /
KALSHI_PRIVATE_KEY (GHA secrets, vault sealed-fill seeded); key material is NEVER logged.
Poly leg needs no auth. Runs MAX_MINUTES then exits 0; the workflow re-dispatches itself
and the builder wake backstops a dead feed."""
import asyncio, json, os, random, subprocess, sys, time, base64, datetime, urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TICKS = os.path.join(REPO, 'data', 'futures_ws_ticks.jsonl')
HEART = os.path.join(REPO, 'data', 'futures_ws_heartbeat.json')
CONFIG = os.path.join(REPO, 'config_leagues.json')
MAX_MINUTES = int(os.environ.get('LISTENER_MAX_MINUTES', '340'))
PUSH_EVERY = int(os.environ.get('LISTENER_PUSH_EVERY', '75'))
FLUSH_EVERY = 5.0
MOVE_IMMEDIATE_C = 1.0   # flush immediately on >=1c move
STALE_S = 60             # no message 60s = stale socket, reconnect

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')

def log(*a):
    print(now_iso(), *a, file=sys.stderr, flush=True)

def http_json(url, headers=None, timeout=25):
    req = urllib.request.Request(url, headers={'User-Agent': 'rix/1.0', **(headers or {})})
    return json.load(urllib.request.urlopen(req, timeout=timeout))

# ---------- Kalshi signing (RSA-PSS/SHA256 over ts+method+path, base64) ----------
def kalshi_priv():
    pem = os.environ.get('KALSHI_PRIVATE_KEY', '')
    if not pem:
        return None
    if '\\n' in pem:
        pem = pem.replace('\\n', '\n')
    from cryptography.hazmat.primitives import serialization
    return serialization.load_pem_private_key(pem.encode(), password=None)

def kalshi_headers(priv, method, path):
    ts = str(int(time.time() * 1000))
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    sig = priv.sign((ts + method + path).encode(),
                    padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                    hashes.SHA256())
    return {'KALSHI-ACCESS-KEY': os.environ['KALSHI_KEY_ID'], 'KALSHI-ACCESS-TIMESTAMP': ts,
            'KALSHI-ACCESS-SIGNATURE': base64.b64encode(sig).decode(),
            'User-Agent': 'rix/1.0', 'Content-Type': 'application/json'}

# ---------- shared state ----------
class State:
    def __init__(self):
        self.board = {}            # key -> cents (P:<question> / K:<ticker>)
        self.key_league = {}       # key -> league
        self.dirty = {}            # league -> {key: cents} pending flush
        self.last_msg = {'poly': 0.0, 'kalshi': 0.0}
        self.reconnects = {'poly': 0, 'kalshi': 0}
        self.connected = {'poly': False, 'kalshi': False}
        self.immediate = asyncio.Event()
        self.rows_written = 0

    def update(self, league, key, cents):
        if cents is None or cents <= 0 or cents >= 100:
            return
        old = self.board.get(key)
        if old == cents:
            return
        self.board[key] = cents
        self.key_league[key] = league
        self.dirty.setdefault(league, {})[key] = cents
        if old is not None and abs(cents - old) >= MOVE_IMMEDIATE_C:
            self.immediate.set()

ST = State()

def load_leagues():
    cfg = json.load(open(CONFIG))
    out = {}
    for lg, ent in (cfg.get('leagues') or {}).items():
        fut = ent.get('futures') or {}
        out[lg] = {'poly_slug': fut.get('poly_slug'), 'kalshi': fut.get('kalshi') or []}
    return out

# ---------- Polymarket discovery ----------
def poly_discover(leagues):
    """asset_id -> (league, question); guards settled/stale slugs."""
    amap = {}
    for lg, f in leagues.items():
        slug = f.get('poly_slug')
        if not slug:
            continue
        try:
            ev = http_json(f'https://gamma-api.polymarket.com/events?slug={slug}')
            e = (ev or [None])[0]
            if not e:
                log('poly discover empty:', lg, slug); continue
            end = e.get('endDate') or ''
            if end and end < now_iso():
                log('poly discover SKIP settled slug:', lg, slug, end); continue
            live = 0
            for m in e.get('markets') or []:
                q = m.get('question')
                ids = m.get('clobTokenIds')
                if isinstance(ids, str):
                    ids = json.loads(ids)
                prs = m.get('outcomePrices')
                if isinstance(prs, str):
                    prs = json.loads(prs or '[]')
                if prs and all(float(p) in (0.0, 1.0) for p in prs):
                    continue  # settled market
                if not q or not ids:
                    continue
                for aid in ids[:1]:  # YES token is index 0
                    amap[aid] = (lg, q); live += 1
            log('poly discover:', lg, slug, '->', live, 'markets')
        except Exception as ex:
            log('poly discover ERR:', lg, slug, repr(ex)[:120])
    return amap

# ---------- Kalshi discovery ----------
def kalshi_discover(leagues, priv):
    """ticker -> league (open markets per configured series)."""
    tmap = {}
    if not priv:
        return tmap
    for lg, f in leagues.items():
        for series in f.get('kalshi') or []:
            cursor, n = None, 0
            for _ in range(4):
                path = '/trade-api/v2/markets'
                url = f'https://api.elections.kalshi.com{path}?series_ticker={series}&status=open&limit=200'
                if cursor:
                    url += f'&cursor={cursor}'
                try:
                    d = http_json(url, headers=kalshi_headers(priv, 'GET', path))
                except Exception as ex:
                    log('kalshi discover ERR:', series, repr(ex)[:120]); break
                for m in d.get('markets') or []:
                    tmap[m['ticker']] = lg; n += 1
                cursor = d.get('cursor')
                if not cursor:
                    break
                time.sleep(0.25)
            log('kalshi discover:', lg, series, '->', n, 'open markets')
            time.sleep(0.25)
    return tmap

# ---------- Poly WS leg ----------
async def poly_leg(leagues_ref):
    import websockets
    backoff = 1
    while True:
        try:
            amap = poly_discover(leagues_ref['lg'])
            if not amap:
                log('poly: no assets; retry in 60s'); await asyncio.sleep(60); continue
            async with websockets.connect('wss://ws-subscriptions-clob.polymarket.com/ws/market',
                                          ping_interval=None, max_size=4 * 1024 * 1024) as ws:
                await ws.send(json.dumps({'type': 'market', 'assets_ids': list(amap.keys())}))
                ST.connected['poly'] = True; ST.last_msg['poly'] = time.time()
                ST.reconnects['poly'] += 1; backoff = 1
                log('poly: connected,', len(amap), 'assets')

                async def pinger():
                    while True:
                        await asyncio.sleep(20)
                        try:
                            await ws.send('PING')
                        except Exception:
                            return
                pt = asyncio.create_task(pinger())
                try:
                    async for raw in ws:
                        ST.last_msg['poly'] = time.time()
                        if raw in ('PONG', 'PING') or not raw:
                            continue
                        try:
                            msg = json.loads(raw)
                        except Exception:
                            continue
                        events = msg if isinstance(msg, list) else [msg]
                        for ev in events:
                            if not isinstance(ev, dict):
                                continue
                            et = ev.get('event_type')
                            if et == 'book':
                                aid = ev.get('asset_id')
                                if aid not in amap:
                                    continue
                                lg, q = amap[aid]
                                bids = [float(b['price']) for b in ev.get('bids') or [] if b.get('price')]
                                asks = [float(a['price']) for a in ev.get('asks') or [] if a.get('price')]
                                v = (min(asks) if asks else (max(bids) if bids else None))
                                if v is not None:
                                    ST.update(lg, 'P:' + q, round(v * 100, 1))
                            elif et == 'price_change':
                                for c in ev.get('changes') or []:
                                    aid = c.get('asset_id')
                                    if aid not in amap or c.get('side') != 'SELL':
                                        continue  # board value = best ask; BUY side tracked implicitly via book refreshes
                                    lg, q = amap[aid]
                                    try:
                                        ST.update(lg, 'P:' + q, round(float(c['price']) * 100, 1))
                                    except Exception:
                                        pass
                finally:
                    pt.cancel()
        except Exception as ex:
            log('poly leg ERR:', repr(ex)[:150])
        ST.connected['poly'] = False
        await asyncio.sleep(backoff + random.random())
        backoff = min(60, backoff * 2)

# ---------- Kalshi WS leg ----------
async def kalshi_leg(leagues_ref, priv):
    import websockets
    if not priv:
        log('kalshi: no key material in env - leg disabled (poly-only mode)')
        ST.connected['kalshi'] = False
        return
    backoff = 1
    while True:
        try:
            tmap = kalshi_discover(leagues_ref['lg'], priv)
            if not tmap:
                log('kalshi: no markets; retry in 60s'); await asyncio.sleep(60); continue
            hdrs = kalshi_headers(priv, 'GET', '/trade-api/ws/v2')
            kw = {}
            try:
                conn = websockets.connect('wss://api.elections.kalshi.com/trade-api/ws/v2',
                                          additional_headers=hdrs, max_size=4 * 1024 * 1024)
                async with conn as ws:
                    await ws.send(json.dumps({'id': 1, 'cmd': 'subscribe',
                                              'params': {'channels': ['ticker'],
                                                         'market_tickers': list(tmap.keys())}}))
                    await _kalshi_pump(ws, tmap)
            except TypeError:
                conn = websockets.connect('wss://api.elections.kalshi.com/trade-api/ws/v2',
                                          extra_headers=hdrs, max_size=4 * 1024 * 1024)
                async with conn as ws:
                    await ws.send(json.dumps({'id': 1, 'cmd': 'subscribe',
                                              'params': {'channels': ['ticker'],
                                                         'market_tickers': list(tmap.keys())}}))
                    await _kalshi_pump(ws, tmap)
        except Exception as ex:
            log('kalshi leg ERR:', repr(ex)[:150])
        ST.connected['kalshi'] = False
        await asyncio.sleep(backoff + random.random())
        backoff = min(60, backoff * 2)

async def _kalshi_pump(ws, tmap):
    ST.connected['kalshi'] = True; ST.last_msg['kalshi'] = time.time()
    ST.reconnects['kalshi'] += 1
    log('kalshi: connected,', len(tmap), 'markets')
    async for raw in ws:
        ST.last_msg['kalshi'] = time.time()
        try:
            msg = json.loads(raw)
        except Exception:
            continue
        if msg.get('type') != 'ticker':
            continue
        m = msg.get('msg') or {}
        tk = m.get('market_ticker')
        if tk not in tmap:
            continue
        ask = m.get('yes_ask_dollars')
        cents = round(float(ask) * 100, 1) if ask not in (None, '') else (
            float(m['yes_ask']) if m.get('yes_ask') not in (None, '') else None)
        if cents is not None:
            ST.update(tmap[tk], 'K:' + tk, cents)

# ---------- staleness watchdog (no message 60s = reconnect) ----------
async def stale_watch():
    while True:
        await asyncio.sleep(15)
        now = time.time()
        for leg in ('poly', 'kalshi'):
            if ST.connected[leg] and ST.last_msg[leg] and now - ST.last_msg[leg] > STALE_S:
                log(leg, 'socket stale (', int(now - ST.last_msg[leg]), 's silent) - forcing reconnect')
                ST.connected[leg] = False
                # websockets lib raises on next recv timeout; close handled by leg loop reconnect
                ST.last_msg[leg] = now  # avoid log spam; leg loop's own error path reconnects

# ---------- flusher + pusher ----------
def flush_rows():
    if not ST.dirty:
        return
    lines = []
    for lg, kv in ST.dirty.items():
        lines.append(json.dumps({'ts': now_iso(), 'league': lg, 'board': kv}, separators=(',', ':')))
        ST.rows_written += 1
    ST.dirty = {}
    with open(TICKS, 'a') as f:
        f.write('\n'.join(lines) + '\n')

async def flusher():
    while True:
        try:
            await asyncio.wait_for(ST.immediate.wait(), timeout=FLUSH_EVERY)
        except asyncio.TimeoutError:
            pass
        ST.immediate.clear()
        flush_rows()

GIT_TIMEOUT = 45   # hang guard: a git call that never returns froze the pusher for 5h on Oct 3 (last tick 17:51Z)
GIT_ENV = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_EDITOR='true', GIT_HTTP_LOW_SPEED_LIMIT='1000', GIT_HTTP_LOW_SPEED_TIME='20')

def _git(args, **kw):
    return subprocess.run(['git'] + args, cwd=REPO, capture_output=True, text=True,
                          timeout=GIT_TIMEOUT, env=GIT_ENV, **kw)

def git_push():
    try:
        _git(['add', 'data/futures_ws_ticks.jsonl', 'data/futures_ws_heartbeat.json'], check=True)
        r = _git(['commit', '-m', 'futures ws ticks ' + now_iso() + ' [skip ci]'])  # skip-ci: tick churn must not starve legacy Pages deploys (publish starvation class 03:32Z)
        if r.returncode != 0:
            return 'nothing-to-commit'
        p = None
        for _ in range(4):
            try:
                pr = _git(['pull', '--rebase', '--autostash', 'origin', 'main'])
                if pr.returncode != 0:
                    _git(['rebase', '--abort'])  # never leave a half-finished rebase blocking the next cycle
                p = _git(['push', 'origin', 'main'])
                if p.returncode == 0:
                    return 'pushed'
            except subprocess.TimeoutExpired as ex:
                p = None
                try:
                    _git(['rebase', '--abort'])
                except Exception:
                    pass
                log('git timeout:', ' '.join(map(str, ex.cmd))[:80])
            time.sleep(2)
        return 'push-failed: ' + ((p.stderr if p is not None else 'timeout') or '')[:120]
    except Exception as ex:
        return 'push-err: ' + repr(ex)[:120]

async def pusher():
    while True:
        await asyncio.sleep(PUSH_EVERY)
        try:
            flush_rows()
            heart = {'ts': now_iso(), 'connected': ST.connected, 'reconnects': ST.reconnects,
                     'last_msg_age_s': {k: (round(time.time() - v, 1) if v else None) for k, v in ST.last_msg.items()},
                     'keys_tracked': len(ST.board), 'rows_written': ST.rows_written}
            json.dump(heart, open(HEART, 'w'), indent=1)
            res = await asyncio.wait_for(asyncio.to_thread(git_push), 240)
            log('push:', res, '| keys', len(ST.board), 'rows', ST.rows_written)
        except Exception as ex:
            log('pusher cycle ERR (loop continues):', repr(ex)[:160])

async def rediscovery(leagues_ref):
    while True:
        await asyncio.sleep(3600)
        try:
            leagues_ref['lg'] = load_leagues()
            log('config rediscovered')
        except Exception as ex:
            log('rediscovery ERR:', repr(ex)[:120])

async def main():
    leagues_ref = {'lg': load_leagues()}
    priv = kalshi_priv() if os.environ.get('KALSHI_KEY_ID') else None
    if os.environ.get('KALSHI_KEY_ID') and not priv:
        log('kalshi: KALSHI_KEY_ID set but private key unparseable - poly-only mode')
    tasks = [asyncio.create_task(poly_leg(leagues_ref)),
             asyncio.create_task(flusher()),
             asyncio.create_task(pusher()),
             asyncio.create_task(stale_watch()),
             asyncio.create_task(rediscovery(leagues_ref))]
    if priv:
        tasks.append(asyncio.create_task(kalshi_leg(leagues_ref, priv)))
    log('listener up: max', MAX_MINUTES, 'min, push every', PUSH_EVERY, 's, kalshi', 'ON' if priv else 'OFF')
    await asyncio.sleep(MAX_MINUTES * 60)
    flush_rows()
    heart = {'ts': now_iso(), 'connected': ST.connected, 'reconnects': ST.reconnects,
             'keys_tracked': len(ST.board), 'rows_written': ST.rows_written, 'final': True}
    json.dump(heart, open(HEART, 'w'), indent=1)
    try:
        await asyncio.wait_for(asyncio.to_thread(git_push), 240)
    except Exception as ex:
        log('final push ERR:', repr(ex)[:120])
    for t in tasks:
        t.cancel()
    log('listener window complete - clean exit for respawn')

if __name__ == '__main__':
    os.makedirs(os.path.join(REPO, 'data'), exist_ok=True)
    open(TICKS, 'a').close()
    asyncio.run(main())
