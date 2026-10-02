#!/usr/bin/env python3
"""Bite-proof fixture for K23 (Sep 30 drift): build_manifest.py's _pick_content_hash called
itself a "VERBATIM contract copy" of the builder's gate but lacked the Sep 29 pricing-snapshot
exclusions - every lane-shipped manifest failed the page build closed (dd2bbf6b vs c2bf0382).
All four contract copies (page builder, nocanon twin, lane manifest builder, both feed mirrors)
must hash the SAME manifest identically. Extracts each copy's real function via AST and runs
them over a live-shaped pick set. Bites on any drift.
"""
import ast, json, hashlib, sys, copy

FILES = ['scripts/build_gh_page_v2.py', 'scripts/_build_nocanon_v2.py',
         'scripts/build_manifest.py', 'scripts/prediction_feed.py', 'scripts/polymarket_feed.py']

def load_fn(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == '_pick_content_hash':
            ns = {'json': json, 'hashlib': hashlib, '_hl': hashlib}
            exec(compile(ast.Module(body=[node], type_ignores=[]), path, 'exec'), ns)
            return ns['_pick_content_hash']
    raise SystemExit(f'{path}: no _pick_content_hash found')

PICK = {
    'num': 1, 'name': 'White Sox ML', 'market_class': 'ml', 'sub': 'model 46.7',
    'odds': '+138', 'units': '5u', 'side': 'away',
    'game': {'away': 'Chicago White Sox', 'home': 'Houston Astros',
             'commence': '2026-09-30T21:00Z', 'eid': '401907897'},
    'espn_league': 'baseball/mlb', 'league': 'MLB', 'best_book': 'Kalshi',
    'kalshi': {'url': 'https://kalshi.com/x', 'cents': 42, 'team': 'Chicago WS',
               'gate_cents': 42, 'ticker': 'KXMLBGAME-X-CWS'},
    'card_american': 138, 'card_source': 'Kalshi ask at lock',
    'card_ts': '2026-09-30T07:04:26-07:00',
    'polymarket': {'url': 'https://polymarket.com/event/mlb-cws-hou-2026-09-30', 'cents': 42},
    'polymarket_us': {'url': 'https://polymarket.us/sports/mlb/mlb-cws-hou-2026-09-30', 'cents': 42, 'verified': True},
    'polycents': 42,
    'dkp': {'url': 'https://predictions.draftkings.com/en/event/x/1', 'team_cents': 42,
            'home_cents': 59, 'away_cents': 42, 'derived': False, 'harvested': '2026-09-30T14:25:54Z'},
    'line_shop': {'as_of': 't', 'books': {'draftkings': {'h2h': [{'side': 'away', 'price': 138}]}}},
    'books': {'dk': 1}, 'books_sp': {'dk': 2}, 'prop_books': {'dk': 3},
    'result': None, '_final': False,
}

def man(picks): return {'picks': picks}

checks = []
fns = {f: load_fn(f) for f in FILES}
base = man([copy.deepcopy(PICK)])
hashes = {f: fn(base) for f, fn in fns.items()}
uniq = set(hashes.values())
checks.append(('all five contract copies hash identically', len(uniq) == 1))

# volatile snapshots must NEVER move the hash
v = man([copy.deepcopy(PICK)])
v['picks'][0]['line_shop']['books']['draftkings']['h2h'][0]['price'] = 999
v['picks'][0]['kalshi']['cents'] = 51
v['picks'][0]['dkp']['team_cents'] = 51
v['picks'][0]['card_ts'] = '2099-01-01T00:00:00-07:00'
v['picks'][0]['polycents'] = 51
v['picks'][0]['num'] = 9
v['picks'][0]['result'] = 'hit'
v['picks'][0]['books'] = {'other': 9}
checks.append(('volatile snapshots (line_shop/books/cents/card_ts/result/num) do not move the hash',
               all(fn(v) == h for (f, fn), h in zip(fns.items(), hashes.values()))))

# DI-18 (Sep 30 - Oct 1): the feed re-prices polymarket/polymarket_us cents every refresh; those
# snapshots moved the card identity on nearly every odds refresh (b310924c, 5cf9c373, 1ff24cea ...)
p = man([copy.deepcopy(PICK)])
p['picks'][0]['polymarket']['cents'] = 57
p['picks'][0]['polymarket_us']['cents'] = 58
checks.append(('polymarket/polymarket_us cents ticks do not move the hash',
               all(fn(p) == h for fn, h in zip(fns.values(), hashes.values()))))
# an arm appearing or disappearing is still a content change (url stays in the hash)
a = man([copy.deepcopy(PICK)])
a['picks'][0]['polymarket_us']['url'] = 'https://polymarket.us/sports/mlb/mlb-cws-hou-2026-10-01'
checks.append(('a changed market url still moves the hash', all(fn(a) != h for fn, h in zip(fns.values(), hashes.values()))))
# legacy=True is exactly the canonicalization the Sep 30 manifests were stamped under (pinned value
# computed with the pre-change function), so their declared hashes keep verifying
LEGACY_PIN = '5b3f43e38468b304e91c3729fd4d9ae92bdf8a644b86763d6e0aca3a88b14ec3'
def _legacy(fn, m):
    try: return fn(m, legacy=True)
    except TypeError: return None  # copy without the legacy canonicalization
for f, fn in fns.items():
    checks.append((f'{f}: legacy canonicalization reproduces the pre-change hash',
                   _legacy(fn, man([copy.deepcopy(PICK)])) == LEGACY_PIN))

# real content MUST move the hash
c = man([copy.deepcopy(PICK)])
c['picks'][0]['odds'] = '+140'
checks.append(('real content change moves the hash', all(fn(c) != h for fn, h in zip(fns.values(), hashes.values()))))

failed = [n for n, ok in checks if not ok]
for n, ok in checks: print(('PASS ' if ok else 'FAIL ') + n)
if failed:
    print(f'\n{len(failed)} FAIL')
    for f, h in hashes.items(): print(f'  {f}: {h[:12]}')
    sys.exit(1)
print(f'\nall {len(checks)} PASS ({len(FILES)} copies, hash {list(uniq)[0][:12]})')
