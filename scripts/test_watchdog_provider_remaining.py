#!/usr/bin/env python3
"""The watchdog's provider-quota floor (skip the auto-retry when the-odds-api credits are nearly
gone) must keep a live reading after nfl_scores.json stopped carrying the credit count (LS-22:
the public file no longer exposes it). The reading now comes from the odds-refresh lane's own
counter, .odds_refresh_count.json last_remaining - the value refresh.sh's hard-cap tripwire
already trusts - and only while that lane has counted a call today (PT).
Run: python3 scripts/test_watchdog_provider_remaining.py   (exit 1 on any failure)
"""
import ast, datetime, json, os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'scripts', 'watchdog.py')

# watchdog.py runs its diagnosis at import time: load only the imports, constants and the
# helper under test. gh() is replaced by a stub that serves an nfl_scores.json WITHOUT the count.
tree = ast.parse(open(SRC).read())
keep = []
for node in tree.body:
    if isinstance(node, (ast.Import, ast.ImportFrom)) and not (isinstance(node, ast.ImportFrom) and node.module == 'watchdog_diag'):
        keep.append(node)
    elif isinstance(node, ast.Assign) and any(getattr(t, 'id', '') in ('REPO', 'COUNT_FILE') for t in node.targets):
        keep.append(node)
    elif isinstance(node, ast.FunctionDef) and node.name == 'provider_remaining':
        keep.append(node)
gh_calls = []
def gh(path, *a, **k):
    gh_calls.append(path)
    import base64
    body = {'pulled_at_utc': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'source': 'the-odds-api v4 nfl scores (daysFrom=1)', 'games': []}
    return {'content': base64.b64encode(json.dumps(body).encode()).decode()}
ns = {'__name__': 'watchdog_helpers', '__file__': SRC, 'gh': gh}
exec(compile(ast.Module(body=keep, type_ignores=[]), SRC, 'exec'), ns)
ns['gh'] = gh

failures = []
def check(label, got, want):
    ok = got == want
    if not ok:
        failures.append(f'{label}: want {want!r} got {got!r}')
    print(f"{'OK  ' if ok else 'FAIL'} {label}" + ('' if ok else f'  [want {want!r} got {got!r}]'))

pr = ns['provider_remaining']
NOW = datetime.datetime(2026, 10, 2, 4, 30, tzinfo=datetime.timezone.utc)   # 2026-10-01 21:30 PT
tmp = tempfile.mkdtemp(prefix='wdpr_')
cf = os.path.join(tmp, '.odds_refresh_count.json')

def call(**kw):
    try:
        return pr(**kw)
    except TypeError:
        return pr()   # legacy signature (reads nfl_scores.json through gh)

json.dump({'2026-09-30': 100, '2026-10-01': 87, 'last_remaining': 19337}, open(cf, 'w'))
check('reading from the odds-refresh counter while it counted a call today (PT)', call(path=cf, now=NOW), 19337)
check('nfl_scores.json is not consulted for the count', gh_calls, [])

json.dump({'2026-09-29': 92, '2026-09-30': 100, 'last_remaining': 19400}, open(cf, 'w'))
check('stale counter (no call counted today PT) gives no reading', call(path=cf, now=NOW), None)

json.dump({'2026-10-01': 3, 'last_remaining': 57}, open(cf, 'w'))
check('low quota reads through (watchdog skips the retry under 100)', call(path=cf, now=NOW), 57)

check('missing counter gives no reading', call(path=os.path.join(tmp, 'absent.json'), now=NOW), None)
open(cf, 'w').write('{corrupt')
check('unreadable counter gives no reading', call(path=cf, now=NOW), None)

check('default path is the repo-root counter', os.path.abspath(ns.get('COUNT_FILE', '')), os.path.join(ROOT, '.odds_refresh_count.json'))

if failures:
    print(f'WATCHDOG PROVIDER REMAINING: {len(failures)} FAILURES')
    sys.exit(1)
print('WATCHDOG PROVIDER REMAINING: ALL PASS')
