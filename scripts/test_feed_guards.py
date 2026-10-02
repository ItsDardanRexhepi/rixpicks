#!/usr/bin/env python3
"""Feed guard fixture (DI-M1 / DI-18 / CP-08, Sep 30 - Oct 1).

1. Hash laundering: on Sep 30 a refresh rebase merged Sep 29's settled picks into the live card
   (b3801e40 declared c2bf0382, computed 293eb6b4) and polymarket_feed.py / prediction_feed.py
   re-stamped pick_content_hash over the corrupted list, so the builder's integrity gate passed it.
   A feed must refuse (exit 3, file untouched) when the declared hash does not match the picks,
   and must never add a hash to a manifest that carried none.
2. A manifest stamped before the polymarket cents exclusion (legacy canonicalization) still
   verifies, and the feed re-stamps it under the current one.
3. Moneyline feeds never attach a moneyline arm to a spread pick (side home/away).
Run: python3 scripts/test_feed_guards.py [scripts_dir]   (scripts_dir defaults to this file's dir)
"""
import ast, copy, hashlib, importlib.util, io, json, os, subprocess, sys, tempfile
from contextlib import redirect_stderr, redirect_stdout

SD = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
failures = 0
def check(name, ok):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name)
    if not ok: failures += 1

def hash_fn(path):
    tree = ast.parse(open(path).read())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == '_pick_content_hash':
            ns = {'json': json, 'hashlib': hashlib, '_hl': hashlib}
            exec(compile(ast.Module(body=[node], type_ignores=[]), path, 'exec'), ns)
            return ns['_pick_content_hash']
    raise SystemExit(f'{path}: no _pick_content_hash')

H = hash_fn(os.path.join(SD, 'polymarket_feed.py'))
def legacy_hash(m):
    try: return H(m, legacy=True)
    except TypeError: return None

ML = {'num': 1, 'name': 'Devils ML', 'market_class': 'ml', 'odds': '-162', 'units': '5u', 'side': 'home',
      'game': {'away': 'Philadelphia Flyers', 'home': 'New Jersey Devils', 'commence': '2099-10-01T23:00Z', 'eid': '401891817'},
      'espn_league': 'hockey/nhl', 'league': 'NHL', 'best_book': 'DraftKings',
      'polymarket': {'url': 'https://polymarket.com/event/nhl-phi-njd-2099-10-01', 'cents': 61},
      'polymarket_us': {'url': 'https://polymarket.us/sports/nhl/nhl-phi-njd-2099-10-01', 'cents': 60, 'verified': True}}
SPREAD = {'num': 2, 'name': 'Aces -4.5', 'market_class': 'spread', 'line': -4.5, 'odds': '-110', 'units': '5u', 'side': 'home',
          'game': {'away': 'Indiana Fever', 'home': 'Las Vegas Aces', 'commence': '2099-10-02T01:00Z', 'eid': '401918022'},
          'espn_league': 'basketball/wnba', 'league': 'WNBA', 'best_book': 'DraftKings'}
SETTLED = {'num': 3, 'name': 'Braves ML', 'market_class': 'ml', 'odds': '-120', 'units': '3u', 'side': 'away',
           'game': {'away': 'Atlanta Braves', 'home': 'Philadelphia Phillies', 'commence': '2099-09-29T23:00Z', 'eid': '401800001'},
           'espn_league': 'baseball/mlb', 'league': 'MLB', 'best_book': 'Kalshi', 'result': 'WIN'}
SIDECAR = {'updated': '2099-10-01T14:00:00Z', 'rows': [
    {'venue': 'dkp', 'date': '2099-10-01', 'away': 'Philadelphia Flyers', 'home': 'New Jersey Devils',
     'home_cents': 61, 'away_cents': 40, 'url': 'https://predictions.draftkings.com/en/event/phi-njd/1'},
    {'venue': 'dkp', 'date': '2099-10-01', 'away': 'Indiana Fever', 'home': 'Las Vegas Aces',
     'home_cents': 71, 'away_cents': 30, 'url': 'https://predictions.draftkings.com/en/event/ind-lv/2'}]}

def card(picks, stamp='current'):
    m = {'date': '2099-10-01', 'record': '21-11', 'units_pl': '+4.76u', 'picks': copy.deepcopy(picks)}
    if stamp == 'current': m['pick_content_hash'] = H(m)
    elif stamp == 'legacy': m['pick_content_hash'] = legacy_hash(m) or 'no-legacy-canonicalization'
    return m

def run_prediction_feed(man):
    d = tempfile.mkdtemp(prefix='rp-feedguard-')
    mp, sp = os.path.join(d, 'manifest.json'), os.path.join(d, 'pm.json')
    json.dump(man, open(mp, 'w'), indent=1); json.dump(SIDECAR, open(sp, 'w'))
    before = open(mp, 'rb').read()
    r = subprocess.run([sys.executable, os.path.join(SD, 'prediction_feed.py'), mp, sp], capture_output=True, text=True)
    return r.returncode, before, open(mp, 'rb').read(), json.load(open(mp)), r.stdout + r.stderr

def load_polymarket_feed():
    spec = importlib.util.spec_from_file_location('pmfeed_fixture', os.path.join(SD, 'polymarket_feed.py'))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod

def run_polymarket_feed(man):
    # network is blocked (dead proxy): every lookup fails fast, the guards run before any lookup
    for k in ('http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY'): os.environ[k] = 'http://127.0.0.1:9'
    d = tempfile.mkdtemp(prefix='rp-feedguard-')
    mp = os.path.join(d, 'manifest.json')
    json.dump(man, open(mp, 'w'), indent=1)
    before = open(mp, 'rb').read()
    mod = load_polymarket_feed()
    err, out, code = io.StringIO(), io.StringIO(), 0
    try:
        with redirect_stderr(err), redirect_stdout(out): mod.feed(mp)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    return code, before, open(mp, 'rb').read(), json.load(open(mp)), err.getvalue() + out.getvalue()

# --- prediction_feed.py ---
good = card([ML])
rc, b0, b1, after, log = run_prediction_feed(good)
check('prediction_feed: verified card is fed (dkp attached)', rc == 0 and (after['picks'][0].get('dkp') or {}).get('team_cents') == 61)
check('prediction_feed: re-stamped hash equals the picks it wrote', after.get('pick_content_hash') == H(after))

corrupt = card([ML]); corrupt['picks'].append(copy.deepcopy(SETTLED))  # declared hash certifies one pick, file holds two
rc, b0, b1, after, log = run_prediction_feed(corrupt)
check('prediction_feed: hash mismatch refuses with exit 3', rc == 3)
check('prediction_feed: refused manifest is left byte-identical (no laundered hash)', b0 == b1)

bare = card([ML], stamp=None)
rc, b0, b1, after, log = run_prediction_feed(bare)
check('prediction_feed: a manifest with no declared hash is fed but never certified', rc == 0 and 'pick_content_hash' not in after and after['picks'][0].get('dkp'))

leg = card([ML], stamp='legacy')
rc, b0, b1, after, log = run_prediction_feed(leg)
check('prediction_feed: legacy-stamped card verifies and is re-stamped under the current canon',
      rc == 0 and after.get('pick_content_hash') == H(after) and after['pick_content_hash'] != leg['pick_content_hash'])

sp = card([SPREAD])
rc, b0, b1, after, log = run_prediction_feed(sp)
check('prediction_feed: spread pick (side home) never takes a moneyline dkp arm', rc == 0 and not after['picks'][0].get('dkp'))

# --- polymarket_feed.py ---
rc, b0, b1, after, log = run_polymarket_feed(corrupt)
check('polymarket_feed: hash mismatch refuses with exit 3', rc == 3)
check('polymarket_feed: refused manifest is left byte-identical', b0 == b1)

rc, b0, b1, after, log = run_polymarket_feed(card([ML]))
check('polymarket_feed: verified card keeps a hash that matches its picks', rc == 0 and after.get('pick_content_hash') == H(after))

rc, b0, b1, after, log = run_polymarket_feed(card([ML], stamp=None))
check('polymarket_feed: a manifest with no declared hash is never certified', rc == 0 and 'pick_content_hash' not in after)

rc, b0, b1, after, log = run_polymarket_feed(card([SPREAD]))
check('polymarket_feed: spread pick is skipped as non-moneyline (never looked up)',
      rc == 0 and 'SKIP Aces -4.5: non-moneyline pick' in log and not after['picks'][0].get('polymarket'))

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
