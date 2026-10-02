#!/usr/bin/env python3
"""The watchdog's provider-quota floor (skip the auto-retry when the-odds-api credits are nearly
gone) must keep a live reading without any served file carrying the credit count (LS-22:
nfl_scores.json and then .odds_refresh_count.json exposed it). The reading is ops state kept
outside the checkout - refresh.sh writes the provider's last x-requests-remaining to
$RP_OPS_STATE/odds_quota.json (default ~/.rixpicks-ops), the workflows carry it between runs in
the Actions cache - and it counts only when taken today (PT).
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
    elif isinstance(node, ast.Assign) and any(getattr(t, 'id', '') in ('REPO', 'COUNT_FILE', 'QUOTA_FILE') for t in node.targets):
        keep.append(node)
    elif isinstance(node, ast.FunctionDef) and node.name in ('provider_remaining', 'redact_credits'):
        keep.append(node)
    elif isinstance(node, ast.Assign) and any(getattr(t, 'id', '') == '_CREDIT_RE' for t in node.targets):
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
qf = os.path.join(tmp, 'odds_quota.json')

def call(**kw):
    try:
        return pr(**kw)
    except TypeError:
        return pr()   # legacy signature (reads nfl_scores.json through gh)

json.dump({'pt_date': '2026-10-01', 'last_remaining': 19337}, open(qf, 'w'))
check('reading from the ops quota state taken today (PT)', call(path=qf, now=NOW), 19337)
check('nfl_scores.json is not consulted for the count', gh_calls, [])

json.dump({'pt_date': '2026-09-30', 'last_remaining': 19400}, open(qf, 'w'))
check('stale reading (taken before today PT) gives no reading', call(path=qf, now=NOW), None)

json.dump({'pt_date': '2026-10-01', 'last_remaining': 57}, open(qf, 'w'))
check('low quota reads through (watchdog skips the retry under 100)', call(path=qf, now=NOW), 57)

check('missing state gives no reading', call(path=os.path.join(tmp, 'absent.json'), now=NOW), None)
open(qf, 'w').write('{corrupt')
check('unreadable state gives no reading', call(path=qf, now=NOW), None)

# the served counter is never the source, even while it still carries a legacy count
cf = os.path.join(tmp, '.odds_refresh_count.json')
json.dump({'2026-10-01': 87, 'last_remaining': 19337}, open(cf, 'w'))
check('the served run counter is not a quota source', call(path=cf, now=NOW), None)

qdef = ns.get('QUOTA_FILE') or ''
qdef = os.path.abspath(qdef) if qdef else ''
check('default state lives outside the checkout (nothing in the repo is unserved)', bool(qdef) and not qdef.startswith(ROOT + os.sep), True)
check('default state is ~/.rixpicks-ops/odds_quota.json unless RP_OPS_STATE says otherwise',
      qdef == os.path.join(os.environ.get('RP_OPS_STATE') or os.path.expanduser('~/.rixpicks-ops'), 'odds_quota.json'), True)
# the committed incident note never carries the count: not in the decision, not in the log tail
src = open(SRC).read()
check('the quota-low decision does not print the count', "provider quota low: %s" not in src and '% prem' not in src, True)
rc = ns.get('redact_credits') or (lambda t: t)
tail = ('americanfootball_nfl: 14 events, credits remaining 19337\nnfl/401: credits used 3, remaining 19334\n'
        'x-requests-remaining: 19330\nnfl_scores.json: 2 games, credits remaining: 19328\n{"last_remaining": 19327}\nBUILD FAILED: card 21-11')
red = rc(tail)
check('incident log tail is written with every credit count redacted', [n for n in ('19337', '19334', '19330', '19328', '19327') if n in red], [])
check('the rest of the tail stays readable', 'BUILD FAILED: card 21-11' in red and 'credits remaining N' in red, True)
check('the incident note writes the redacted tail', 'redact_credits(diag[\'error_tail\'])' in src, True)
wf = open(os.path.join(ROOT, '.github', 'workflows', 'watchdog.yml')).read()
check('failure-watchdog restores the odds quota state from the Actions cache', 'actions/cache/restore@' in wf and 'odds-quota-' in wf, True)
if failures:
    print(f'WATCHDOG PROVIDER REMAINING: {len(failures)} FAILURES')
    sys.exit(1)
print('WATCHDOG PROVIDER REMAINING: ALL PASS')
