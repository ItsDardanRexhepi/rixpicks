#!/usr/bin/env python3
"""odds-refresh lane fixture (Oct 1 sweep follow-ups): runs the real scripts/refresh.sh and
scripts/push_with_guard.sh in a scratch git repo against a scratch origin, with every paid or
network python step stubbed, a stub `curl` for the-odds-api and the ESPN game-window probe
answered 'live', fully offline.
 Card hold before any paid pull (ci review, spend): manifest.json's picks must match its declared
   pick_content_hash. refresh.sh runs the feeds' own check (polymarket_feed.py --verify-hash, no
   network, no write) before the paid odds pulls and holds right there (exit 3, nothing pulled,
   nothing pushed), so a held card - and the watchdog's retry of it - never pays for odds.
 Card hold after the pulls (builder review of the feed hash guard): a feed's or the builder's
   exit 3 later in the run is never swallowed as an ordinary feed failure or rebuilt; the live data
   unrelated to the card (futures, live games, the odds already pulled) still ships in a data-only
   commit, and the run then fails loud (exit 3). An ordinary feed failure keeps the last manifest
   and the run carries on.
 Credit count (LS-22): the paid API's x-requests-remaining never lands in a served file - the
   committed .odds_refresh_count.json carries the run count only (a legacy last_remaining is
   dropped by the next counted run); the reading lives in the ops state file outside the checkout
   ($RP_OPS_STATE/odds_quota.json), which the hard-cap tripwire reads before any paid pull.
 Hard-cap tripwire without a reading (ci review, spend): each reading is stored with its PT month,
   and a reading from an earlier month is ignored (the provider resets credits on the 1st). When
   neither the ops state nor the legacy counter gives this month's reading (an Actions cache miss,
   a new month), refresh.sh takes the free reading - GET /v4/sports, which the provider does not
   count against the quota and which returns x-requests-remaining - before any paid pull, records
   it, and applies the 200-credit floor to it. No reading at all means no paid pull (fail loud).
Run: python3 scripts/test_refresh_lane.py [path/to/refresh.sh]"""
import json, os, shutil, stat, subprocess, sys, tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
REFRESH = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(HERE, 'refresh.sh')
GUARD = os.path.join(HERE, 'push_with_guard.sh')
OPS_QUOTA = os.path.join(HERE, 'ops_quota.py')
REAL_PY = sys.executable
_NOW = datetime.now(ZoneInfo('America/Los_Angeles'))
TODAY = _NOW.strftime('%Y-%m-%d')
MONTH = TODAY[:7]
PREV_DAY = (_NOW.replace(day=1) - timedelta(days=1)).strftime('%Y-%m-%d')   # last day of the previous PT month
# made-up credit counts (every repo path is served, so no fixture carries a real provider reading)
REM = 18763     # the paid pull's reading: must appear in no served file
FREE = 17421    # the free GET /v4/sports reading
LEGACY = 16842  # a legacy reading left in the served counter
failures = 0

sys.path.insert(0, HERE)
from polymarket_feed import _pick_content_hash   # the feeds' own canonical hash (mirror of the builder)

def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or detail == '' else '  [' + str(detail)[:400] + ']'))
    if not ok:
        failures += 1

STUB = r'''import json, os, sys, time
name = os.path.basename(sys.argv[0]); T = os.environ['RP_TMP']
if name == 'polymarket_feed.py' and '--verify-hash' in sys.argv:
    # the pre-pull card check runs the REAL feed script (local hash check only: no network, no write)
    open(os.path.join(T, 'calls.txt'), 'a').write('verify-hash:' + name + '\n')
    import runpy
    real = os.path.join(os.environ['STUB_REAL_SCRIPTS'], name)
    sys.argv = [real] + sys.argv[1:]
    runpy.run_path(real, run_name='__main__')
    sys.exit(0)
open(os.path.join(T, 'calls.txt'), 'a').write(name + '\n')
tick = str(time.time())
def rc(var):
    return int(os.environ.get(var) or 0)
if name == 'odds_prefill.py':
    json.dump([{'away': 'A', 'home': 'B', 'tick': tick}], open(os.path.join(T, 'odds_prefill.json'), 'w'))
    print('americanfootball_nfl: 1 events, credits remaining %s' % os.environ['STUB_REMAINING'], file=sys.stderr)
elif name == 'futures_quotes.py':
    json.dump({'tick': tick}, open('futures.json', 'w'))
elif name == 'live_games.py':
    json.dump({'tick': tick}, open('slates/live_games.json', 'w'))
elif name in ('polymarket_feed.py', 'prediction_feed.py'):
    var = 'STUB_POLY_RC' if name == 'polymarket_feed.py' else 'STUB_PRED_RC'
    if rc(var) == 3:
        print('REFUSED: manifest pick_content_hash does not match its picks - not mutating or re-stamping it', file=sys.stderr)
        sys.exit(3)
    if rc(var):
        print('network down', file=sys.stderr); sys.exit(rc(var))
    m = json.load(open('manifest.json')); m.setdefault('feed_ticks', {})[name] = tick
    json.dump(m, open('manifest.json', 'w'), indent=1)
elif name == 'build_gh_page_v2.py':
    if rc('STUB_BUILD_RC'):
        open('index.html', 'w').write('<html>half-written ' + tick)  # a builder that dies mid-write
        print('BUILD FAILED: stub', file=sys.stderr); sys.exit(rc('STUB_BUILD_RC'))
    open('index.html', 'w').write('<html>built ' + tick + '</html>')
'''

# the-odds-api over curl: GET /v4/sports answers with the quota headers (STUB_FREE_REMAINING;
# 'down' = the request fails, '' = no quota header). Logs the path only, never the key.
CURL_STUB = r'''#!%s
import os, sys
a = sys.argv[1:]
url = next((x for x in a if x.startswith('http')), '')
T = os.environ['RP_TMP']
open(os.path.join(T, 'calls.txt'), 'a').write('curl:' + url.split('?')[0].replace('https://api.the-odds-api.com', '') + '\n')
rem = os.environ.get('STUB_FREE_REMAINING', '')
if rem == 'down':
    sys.exit(7)
if '-D' in a:
    open(a[a.index('-D') + 1], 'w').write('HTTP/2 200\r\ncontent-type: application/json; charset=utf-8\r\n'
        + ('x-requests-used: 1\r\nx-requests-remaining: %%s\r\nx-requests-last: 0\r\n' %% rem if rem else '') + '\r\n')
if '-o' in a and a[a.index('-o') + 1] != '/dev/null':
    open(a[a.index('-o') + 1], 'w').write('[]')
''' % REAL_PY

SHIM = '''#!/bin/bash
# python3 shim: answers the ESPN game-window heredoc 'live'; everything else runs the real python
if [ "$1" = "-" ]; then
  f=$(mktemp "$RP_TMP/heredoc.XXXXXX"); cat > "$f"
  if grep -q 'scoreboard?dates=' "$f"; then exit 0; fi
  exec "%s" "$f"
fi
exec "%s" "$@"
''' % (REAL_PY, REAL_PY)

STUBBED = ('odds_prefill.py', 'odds_prefill_st.py', 'odds_prefill_props.py', 'move_cause.py', 'futures_quotes.py',
           'wooder_td_feed.py', 'live_games.py', 'polymarket_feed.py', 'prediction_feed.py', 'build_gh_page_v2.py',
           'backfill_history.py')
PAID = ('odds_prefill.py', 'odds_prefill_st.py', 'odds_prefill_props.py')
FREE_CALLS = ('curl:/v4/sports', 'curl:/v4/sports/')
MANIFEST = {'date': TODAY, 'record': '21-11', 'units_pl': '+4.76u', 'picks': [{'name': 'Under 38.5', 'league': 'NFL'}]}
DATA = {'manifest.json': MANIFEST,
        'config_leagues.json': {'leagues': {'NFL': {'espn': 'football/nfl', 'odds_api': 'americanfootball_nfl'}}},
        '.odds_refresh_count.json': {PREV_DAY: 100, 'last_remaining': LEGACY},
        'futures.json': {'tick': '0'}, 'slates/nfl_live.json': {}, 'slates/live_games.json': {'tick': '0'},
        'slates/odds_prefill.json': [], 'slates/odds_prefill_st.json': [], 'slates/odds_prefill_st_pregame.json': [],
        'slates/odds_prefill_props.json': [], 'slates/game_routes.json': {}, '.odds_prev.json': {}, 'hist-1.json': {},
        'manifests/manifest-000000000000.json': {}}
TEXT = {'index.html': '<html>last verified build</html>', 'futures.html': '<html>futures</html>', 'game-1.html': '<html>g</html>',
        'team-a.html': '<html>t</html>', 'odds_moves.jsonl': '', 'price_history.jsonl': ''}
# the cache carried this month's reading (the ordinary case)
THIS_MONTH = {'pt_date': TODAY, 'month': MONTH, 'last_remaining': 18800}

def git(cwd, *a, check_=True):
    return subprocess.run(['git', *a], cwd=cwd, capture_output=True, text=True, check=check_)

def lane(env_extra, ops_state=THIS_MONTH, counter=None, manifest=None):
    """One refresh run in a fresh scratch repo against a scratch origin (ops_state None = cache miss)."""
    root = tempfile.mkdtemp(prefix='rp-refresh-lane-')
    origin, work, tmp, ops, bin_ = (os.path.join(root, x) for x in ('origin.git', 'work', 'tmp', 'ops', 'bin'))
    for d in (tmp, bin_, ops):
        os.makedirs(d)
    git(root, 'init', '-q', '--bare', '-b', 'main', origin)
    git(root, 'init', '-q', '-b', 'main', work)
    os.makedirs(os.path.join(work, 'scripts')); os.makedirs(os.path.join(work, 'slates')); os.makedirs(os.path.join(work, 'manifests'))
    shutil.copy(REFRESH, os.path.join(work, 'scripts', 'refresh.sh'))
    shutil.copy(GUARD, os.path.join(work, 'scripts', 'push_with_guard.sh'))
    if os.path.exists(OPS_QUOTA):
        shutil.copy(OPS_QUOTA, os.path.join(work, 'scripts', 'ops_quota.py'))
    for s_ in STUBBED:
        open(os.path.join(work, 'scripts', s_), 'w').write(STUB)
    data = dict(DATA)
    if counter is not None:
        data['.odds_refresh_count.json'] = counter
    if manifest is not None:
        data['manifest.json'] = manifest
    for rel, obj in data.items():
        json.dump(obj, open(os.path.join(work, rel), 'w'), indent=1)
    for rel, txt in TEXT.items():
        open(os.path.join(work, rel), 'w').write(txt)
    open(os.path.join(bin_, 'python3'), 'w').write(SHIM)
    os.chmod(os.path.join(bin_, 'python3'), 0o755)
    open(os.path.join(bin_, 'curl'), 'w').write(CURL_STUB)
    os.chmod(os.path.join(bin_, 'curl'), 0o755)
    if ops_state is not None:
        json.dump(ops_state, open(os.path.join(ops, 'odds_quota.json'), 'w'))
    git(work, 'add', '-A'); git(work, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'seed')
    git(work, 'remote', 'add', 'origin', origin); git(work, 'push', '-q', 'origin', 'main'); git(work, 'branch', '-q', '-u', 'origin/main')
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(PATH=bin_ + os.pathsep + env['PATH'], RP_TMP=tmp, RP_OPS_STATE=ops, THE_ODDS_API_KEY='fixture-placeholder',
               HOME=root, GIT_CONFIG_NOSYSTEM='1', STUB_REMAINING=str(REM), STUB_FREE_REMAINING=str(FREE),
               STUB_REAL_SCRIPTS=HERE)
    env.update(env_extra)
    r = subprocess.run(['bash', 'scripts/refresh.sh'], cwd=work, env=env, capture_output=True, text=True, timeout=300)
    roots.append(root)
    return {'rc': r.returncode, 'out': r.stdout, 'err': r.stderr, 'origin': origin, 'tmp': tmp, 'ops': ops}

def origin_file(origin, rel):
    r = subprocess.run(['git', '--git-dir', origin, 'show', 'main:' + rel], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None

def origin_log(origin):
    return subprocess.run(['git', '--git-dir', origin, 'log', '--format=%s', 'main'], capture_output=True, text=True).stdout.splitlines()

def calls(tmp):
    p = os.path.join(tmp, 'calls.txt')
    return open(p).read().split() if os.path.exists(p) else []

def changed_in_tip(origin):
    return subprocess.run(['git', '--git-dir', origin, 'show', '--name-only', '--format=', 'main'], capture_output=True, text=True).stdout.split()

def served_hits(origin, needle):
    r = subprocess.run(['git', '--git-dir', origin, 'grep', '-l', needle, 'main'], capture_output=True, text=True)
    return r.stdout.split()

def ops_file(L):
    qp = os.path.join(L['ops'], 'odds_quota.json')
    try:
        return json.load(open(qp))
    except Exception:
        return None

def paid(L):
    return [c for c in calls(L['tmp']) if c in PAID]

def free_before_paid(L):
    c = calls(L['tmp'])
    fi = next((i for i, x in enumerate(c) if x in FREE_CALLS), None)
    pi = next((i for i, x in enumerate(c) if x in PAID), None)
    return fi is not None and pi is not None and fi < pi

roots = []
try:
    # A. a normal run with this month's reading: rebuilt and pushed; the credit reading goes to ops
    #    state (with its PT date and month), not the served counter; no free reading is needed
    L = lane({})
    check('A normal run exits 0 and pushes', L['rc'] == 0 and 'rebuilt and pushed' in L['out'], (L['rc'], L['err'][-400:]))
    cnt = json.loads(origin_file(L['origin'], '.odds_refresh_count.json') or '{}')
    check('A served run counter carries no credit count (legacy last_remaining dropped)', 'last_remaining' not in cnt, cnt)
    check('A served run counter still counts the run', cnt.get(TODAY) == 1, cnt)
    check('A no served file carries the credit count', served_hits(L['origin'], str(REM)) == [], served_hits(L['origin'], str(REM)))
    check('A the reading lands in the ops state outside the checkout, with its PT date and month',
          ops_file(L) == {'pt_date': TODAY, 'month': MONTH, 'last_remaining': REM}, ops_file(L))
    check('A this month\'s reading needs no free reading', not any(c.startswith('curl:') for c in calls(L['tmp'])), calls(L['tmp']))

    # B. the hard-cap tripwire reads the ops state before any paid pull (a reading stored before the
    #    month was recorded counts in the month of its PT date)
    L = lane({}, ops_state={'pt_date': TODAY, 'last_remaining': 150})
    check('B tripwire: ops state under 200 fails loud before any pull',
          L['rc'] == 1 and 'HARD CAP TRIPWIRE' in L['err'] and 'odds_prefill.py' not in calls(L['tmp']), (L['rc'], calls(L['tmp']), L['err'][-300:]))
    L = lane({}, ops_state={'pt_date': TODAY, 'month': MONTH, 'last_remaining': 150})
    check('B1 tripwire: this month\'s reading under 200 fails loud before any pull',
          L['rc'] == 1 and 'HARD CAP TRIPWIRE' in L['err'] and paid(L) == [], (L['rc'], calls(L['tmp']), L['err'][-300:]))
    # B2. first run after the move: no ops state yet, the served counter's legacy reading (this
    #     month, by its latest counted day) still trips it
    L = lane({}, ops_state=None, counter={TODAY: 100, 'last_remaining': 150})
    check('B2 tripwire: legacy counter reading under 200 still fails loud before any pull (transition)',
          L['rc'] == 1 and 'HARD CAP TRIPWIRE' in L['err'] and 'odds_prefill.py' not in calls(L['tmp']), (L['rc'], L['err'][-300:]))

    # G. cache miss: no ops state and no legacy reading - the free reading comes first
    L = lane({}, ops_state=None, counter={PREV_DAY: 100})
    check('G cache miss: the free GET /v4/sports reading is taken before any paid pull', free_before_paid(L), calls(L['tmp']))
    check('G cache miss: the run then refreshes as usual (exit 0, pushed)', L['rc'] == 0 and 'rebuilt and pushed' in L['out'], (L['rc'], L['err'][-300:]))
    check('G no served file carries the free reading', served_hits(L['origin'], str(FREE)) == [], served_hits(L['origin'], str(FREE)))
    check('G the run log names the free reading without the count', 'free' in (L['out'] + L['err']).lower() and str(FREE) not in L['out'] + L['err'],
          (L['out'] + L['err'])[-300:])
    # G2. cache miss and the free reading is under the floor: the tripwire fires, nothing paid,
    #     and the reading is recorded (with its month) so the cache carries the trip
    L = lane({'STUB_FREE_REMAINING': '150'}, ops_state=None, counter={PREV_DAY: 100})
    check('G2 cache miss, free reading under 200: HARD CAP TRIPWIRE, no paid pull',
          L['rc'] == 1 and 'HARD CAP TRIPWIRE' in L['err'] and paid(L) == [] and any(c in FREE_CALLS for c in calls(L['tmp'])),
          (L['rc'], calls(L['tmp']), L['err'][-300:]))
    check('G2 the free reading is recorded with its PT date and month', ops_file(L) == {'pt_date': TODAY, 'month': MONTH, 'last_remaining': 150}, ops_file(L))
    check('G2 nothing pushed', origin_log(L['origin']) == ['seed'], origin_log(L['origin']))
    # G3. cache miss and no free reading either: no paid pull without a reading (fail loud)
    for case, rem in (('G3', 'down'), ('G3b', '')):
        L = lane({'STUB_FREE_REMAINING': rem}, ops_state=None, counter={PREV_DAY: 100})
        check(f'{case} cache miss, free reading {"fails" if rem else "has no quota header"}: fails loud, no paid pull',
              L['rc'] == 1 and 'QUOTA READING UNAVAILABLE' in L['err'] and paid(L) == [] and origin_log(L['origin']) == ['seed'],
              (L['rc'], calls(L['tmp']), L['err'][-300:]))

    # H. after the monthly reset: last month's trip does not hold this month
    L = lane({}, ops_state={'pt_date': PREV_DAY, 'month': PREV_DAY[:7], 'last_remaining': 150})
    check('H a reading from an earlier month is ignored: no tripwire', 'HARD CAP TRIPWIRE' not in L['err'], L['err'][-300:])
    check('H the free reading replaces it before any paid pull', free_before_paid(L), calls(L['tmp']))
    check('H the run refreshes (exit 0, pushed)', L['rc'] == 0 and 'rebuilt and pushed' in L['out'], (L['rc'], L['err'][-300:]))
    check('H ops state now holds this month\'s reading', (ops_file(L) or {}).get('month') == MONTH and (ops_file(L) or {}).get('pt_date') == TODAY, ops_file(L))
    L = lane({}, ops_state={'pt_date': PREV_DAY, 'last_remaining': 150})
    check('H2 a pre-month-format reading from an earlier PT date month is ignored too', L['rc'] == 0 and free_before_paid(L), (L['rc'], calls(L['tmp'])))
    L = lane({}, ops_state=None, counter={PREV_DAY: 100, 'last_remaining': 150})
    check('H3 a legacy counter reading from an earlier month is ignored: free reading, no tripwire',
          L['rc'] == 0 and 'HARD CAP TRIPWIRE' not in L['err'] and free_before_paid(L), (L['rc'], calls(L['tmp']), L['err'][-300:]))

    # P. the card is held before any paid pull: manifest.json's picks do not match its declared hash
    bad = dict(MANIFEST, pick_content_hash='f' * 64)
    L = lane({}, manifest=bad)
    check('P hash mismatch: held (exit 3, CARD HOLD) before any paid pull',
          L['rc'] == 3 and 'CARD HOLD' in L['err'] and paid(L) == [], (L['rc'], calls(L['tmp']), L['err'][-400:]))
    check('P the check is the feeds\' own (polymarket_feed.py --verify-hash)', 'verify-hash:polymarket_feed.py' in calls(L['tmp']), calls(L['tmp']))
    check('P no free reading either, no feed, no build', not any(c.startswith('curl:') for c in calls(L['tmp']))
          and not ({'polymarket_feed.py', 'prediction_feed.py', 'build_gh_page_v2.py'} & set(calls(L['tmp']))), calls(L['tmp']))
    check('P nothing pushed (no live-data commit either)', origin_log(L['origin']) == ['seed'], origin_log(L['origin']))
    check('P the last log line carries the CARD HOLD marker the watchdog reads',
          [l for l in L['err'].splitlines() if l.strip()][-1:] and 'CARD HOLD' in [l for l in L['err'].splitlines() if l.strip()][-1], L['err'][-300:])
    L = lane({}, ops_state=None, counter={PREV_DAY: 100}, manifest=bad)
    check('P1 a held card on a cache miss: held before the free reading too (no request at all)',
          L['rc'] == 3 and 'CARD HOLD' in L['err'] and paid(L) == [] and not any(c.startswith('curl:') for c in calls(L['tmp'])),
          (L['rc'], calls(L['tmp'])))
    good = dict(MANIFEST, pick_content_hash=_pick_content_hash(MANIFEST))
    L = lane({}, manifest=good)
    check('P2 a declared hash that matches passes the check: refreshed as usual',
          L['rc'] == 0 and 'rebuilt and pushed' in L['out'] and 'verify-hash:polymarket_feed.py' in calls(L['tmp']), (L['rc'], L['err'][-300:]))

    # C. a feed refuses the card later in the run (pick_content_hash mismatch after the pulls)
    L = lane({'STUB_POLY_RC': '3'})
    tip = changed_in_tip(L['origin'])
    check('C feed exit 3: the run fails loud (exit 3, CARD HOLD)', L['rc'] == 3 and 'CARD HOLD' in L['err'], (L['rc'], L['err'][-400:]))
    check('C the held card is never rebuilt', 'build_gh_page_v2.py' not in calls(L['tmp']), calls(L['tmp']))
    check('C live data unrelated to the card still ships (data-only commit)',
          'futures.json' in tip and 'slates/live_games.json' in tip and 'card held' in (origin_log(L['origin']) or [''])[0],
          (tip, origin_log(L['origin'])[:2]))
    check('C no page and no manifest ship with a held card', not ({'index.html', 'manifest.json'} & set(tip))
          and origin_file(L['origin'], 'index.html') == TEXT['index.html'], tip)
    check('C the data-only commit carries no credit count either', served_hits(L['origin'], str(REM)) == [], served_hits(L['origin'], str(REM)))

    # D. the builder refuses the card after the feeds touched the manifest and the page was half-written
    L = lane({'STUB_BUILD_RC': '3'})
    tip = changed_in_tip(L['origin'])
    check('D builder exit 3: the run fails loud (exit 3, CARD HOLD)', L['rc'] == 3 and 'CARD HOLD' in L['err'], (L['rc'], L['err'][-400:]))
    check('D live data still ships; the feed-touched manifest and the half-written page do not',
          'futures.json' in tip and 'manifest.json' not in tip and 'index.html' not in tip
          and json.loads(origin_file(L['origin'], 'manifest.json') or '{}') == DATA['manifest.json']
          and origin_file(L['origin'], 'index.html') == TEXT['index.html'], (tip, (origin_file(L['origin'], 'index.html') or '')[:60]))

    # E. an ordinary feed failure keeps the last manifest; the refresh carries on
    L = lane({'STUB_PRED_RC': '1'})
    check('E unrelated feed failure: rebuilt and pushed (exit 0)', L['rc'] == 0 and 'failed - keeping last manifest' in L['err']
          and 'build_gh_page_v2.py' in calls(L['tmp']) and 'index.html' in changed_in_tip(L['origin']), (L['rc'], L['err'][-300:]))

    # F. any other builder failure still stops the run with nothing pushed
    L = lane({'STUB_BUILD_RC': '2'})
    check('F builder exit 2: the run stops, nothing pushed', L['rc'] == 2 and origin_log(L['origin']) == ['seed'], (L['rc'], origin_log(L['origin'])))

    # V. the check itself (the real polymarket_feed.py): local only - it never writes the manifest
    vroot = tempfile.mkdtemp(prefix='rp-verify-hash-')
    roots.append(vroot)
    venv = {k: v for k, v in os.environ.items()}
    venv.update(http_proxy='http://127.0.0.1:9', https_proxy='http://127.0.0.1:9', HTTP_PROXY='http://127.0.0.1:9', HTTPS_PROXY='http://127.0.0.1:9')
    for case, man, want in (('mismatch', bad, 3), ('match', good, 0), ('no declared hash', dict(MANIFEST, picks=[]), 0)):
        mp = os.path.join(vroot, case.replace(' ', '_') + '.json')
        open(mp, 'w').write(json.dumps(man))
        before = open(mp, 'rb').read()
        r = subprocess.run([REAL_PY, os.path.join(HERE, 'polymarket_feed.py'), mp, '--verify-hash'], capture_output=True, text=True, env=venv, timeout=60)
        check(f'V --verify-hash on a {case} manifest exits {want} and leaves the file as it was',
              r.returncode == want and open(mp, 'rb').read() == before, (r.returncode, r.stderr[-300:]))
finally:
    for r in roots:
        shutil.rmtree(r, ignore_errors=True)

print('REFRESH LANE: ' + (f'{failures} FAILURES' if failures else 'ALL PASS'))
sys.exit(1 if failures else 0)
