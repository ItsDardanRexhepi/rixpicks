#!/usr/bin/env python3
"""The failure-watchdog never auto-retries a held card (ci review, spend).

refresh.sh exits 3 with a CARD HOLD line when the card is refused: manifest.json's picks do not
match its declared pick_content_hash, or the builder refuses it. A retry refuses the same card
again, and an odds-refresh retry used to pay for the odds pulls first: the watchdog redispatched
run 111 (failing step "refresh odds and rebuild") with "auto-redispatched once (30-min budget)".
When the failed job's log carries a CARD HOLD line anywhere (not only in the quoted tail: on the
late hold path a failed data-only push prints its git and guard output after it) the decision is
no retry; a line that only names the marker is no hold, and any other failure keeps the budgeted
retry.

Runs the real scripts/watchdog.py, offline: a stub `gh` on PATH answers the API and records the
dispatch POST, and the job log is served by a stand-in for the signed-URL download.
Run: python3 scripts/test_watchdog_card_hold.py   (exit 1 on any failure)
"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'watchdog.py')

failures = []
def check(label, ok, detail=''):
    if not ok:
        failures.append(label + (': ' + str(detail)[:400] if detail != '' else ''))
    print(f"{'OK  ' if ok else 'FAIL'} {label}" + ('' if ok or detail == '' else f'  [{str(detail)[:400]}]'))

GH_STUB = r'''#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
path = a[1] if len(a) > 1 else ''
method = a[a.index('-X') + 1] if '-X' in a else 'GET'
fx = os.environ['WD_FIX']
open(os.path.join(fx, 'gh_calls.txt'), 'a').write(method + ' ' + path + '\n')
if path.endswith('/dispatches'):
    sys.exit(0)
if '/actions/runs/' in path and path.endswith('/jobs'):
    print(json.dumps({'jobs': [
        {'id': 1, 'name': 'hold-check', 'conclusion': 'success', 'steps': [{'name': 'Run hold-check', 'conclusion': 'success'}]},
        {'id': 2, 'name': 'refresh', 'conclusion': 'failure', 'steps': [{'name': 'refresh odds and rebuild', 'conclusion': 'failure'}]}]}))
elif '/runs?per_page=3' in path:
    print(json.dumps({'workflow_runs': [{'id': 111, 'run_started_at': '2026-10-02T17:00:00Z'}]}))
else:
    print(json.dumps({'workflow_runs': []}))
'''

# The job log comes from a 302 to a signed download URL; the stand-in opener serves the fixture
# log for any request, so the real job_log() and error_tail() pick the tail.
RUNNER = r'''import io, os, runpy, sys, urllib.request
LOG = open(os.environ['WD_LOG'], 'rb').read()
class _Opener:
    def open(self, req, *a, **k):
        return io.BytesIO(LOG)
urllib.request.build_opener = lambda *a, **k: _Opener()
sys.argv = [os.environ['WD_SRC']]
runpy.run_path(os.environ['WD_SRC'], run_name='__main__')
'''

def log_lines(*tail):
    return '\n'.join(['2026-10-02T17:00:01Z ##[group]Run bash scripts/refresh.sh'] + ['2026-10-02T17:00:02Z setup noise'] * 20
                     + ['2026-10-02T17:00:03Z ' + t for t in tail]
                     + ['2026-10-02T17:00:04Z ##[error]Process completed with exit code %s.' % ('3' if any('CARD HOLD' in t for t in tail) else '1')]) + '\n'

def watchdog(case, log_text):
    root = tempfile.mkdtemp(prefix='rp-wd-hold-')
    roots.append(root)
    fx, bin_, ops, work = (os.path.join(root, x) for x in ('fx', 'bin', 'ops', 'work'))
    for d in (fx, bin_, ops, work):
        os.makedirs(d)
    open(os.path.join(bin_, 'gh'), 'w').write(GH_STUB.replace('/usr/bin/env python3', sys.executable, 1))
    os.chmod(os.path.join(bin_, 'gh'), 0o755)
    open(os.path.join(fx, 'job.log'), 'w').write(log_text)
    open(os.path.join(fx, 'runner.py'), 'w').write(RUNNER)
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(PATH=bin_ + os.pathsep + env['PATH'], WD_FIX=fx, WD_LOG=os.path.join(fx, 'job.log'), WD_SRC=SRC,
               RP_OPS_STATE=ops, GH_TOKEN='fixture-placeholder', RUN_ID='111', WF_NAME='odds-refresh',
               WF_ID='367062180', HEAD_SHA='0123456789abcdef', REPO='example/rixpicks')
    r = subprocess.run([sys.executable, os.path.join(fx, 'runner.py')], cwd=work, env=env, capture_output=True, text=True, timeout=120)
    calls = open(os.path.join(fx, 'gh_calls.txt')).read().splitlines() if os.path.exists(os.path.join(fx, 'gh_calls.txt')) else []
    try:
        diag = json.loads(r.stdout)
    except Exception:
        diag = {}
    try:
        state = json.load(open(os.path.join(work, 'watchdog_state.json')))
    except Exception:
        state = None
    note_p = os.path.join(work, 'incidents', '111-diag.md')
    note = open(note_p).read() if os.path.exists(note_p) else ''
    return {'rc': r.returncode, 'err': r.stderr, 'diag': diag, 'calls': calls, 'state': state, 'note': note}

roots = []
try:
    # A. the feeds refused the card before any paid pull (refresh.sh's pre-pull hold)
    W = watchdog('A', log_lines('CARD HOLD: manifest.json pick_content_hash does not match its picks - held before any paid odds pull',
                                'CARD HOLD: polymarket_feed.py - pages not rebuilt, manifest.json not committed; re-stamp or fix the card with build_manifest.py'))
    check('A watchdog ran to a decision', W['rc'] == 0 and 'decision' in W['diag'], (W['rc'], W['err'][-400:]))
    check('A a held card is not auto-retried', W['diag'].get('decision', '').startswith('no auto-retry') and 'card held' in W['diag'].get('decision', ''),
          W['diag'].get('decision'))
    check('A no dispatch is sent for a held card', not any(c.endswith('/dispatches') for c in W['calls']), W['calls'])
    check('A no retry is booked against the 30-min budget', 'odds-refresh' not in (W['state'] or {}), W['state'])
    check('A the incident note states the decision', 'card held' in W['note'], W['note'][:300])

    # B. the builder refused the card after the paid pulls (CARD HOLD from the build step)
    W = watchdog('B', log_lines('BUILD FAILED: Kalshi market unresolved for Rangers ML team \'NYR\' under KXNHLGAME',
                                'CARD HOLD: the builder refused the card (exit 3, see BUILD FAILED above)',
                                'CARD HOLD: build_gh_page_v2.py - pages not rebuilt, manifest.json not committed; re-stamp or fix the card with build_manifest.py'))
    check('B a builder hold is not auto-retried either', 'card held' in W['diag'].get('decision', '') and not any(c.endswith('/dispatches') for c in W['calls']),
          (W['diag'].get('decision'), W['calls']))

    # D. late hold path (r3 review): the card is held after the paid pulls, the data-only commit's
    #    push then fails in push_with_guard (set -e, exit 1), and its git and guard output pushes the
    #    CARD HOLD line far out of the 14 lines before ##[error]. The whole failed log is searched.
    late = (['BUILD FAILED: Kalshi market unresolved for Rangers ML team \'NYR\' under KXNHLGAME',
             'CARD HOLD: the builder refused the card (exit 3, see BUILD FAILED above)',
             '[main 1a2b3c4] odds refresh 10:15 PT (call 7 today) - live data only, card held']
            + ['To github.com:example/rixpicks.git ! [rejected] HEAD -> main (fetch first)'] * 12
            + ['REBASE GUARD: race touched lane-shipped/generated content ( manifest.json) - reset to origin/main, fail loud; next cycle regenerates',
               'HEAD is now at 9f8e7d6 odds refresh 10:16 PT (call 8 today)'] * 4)
    W = watchdog('D', log_lines(*late))
    check('D the late-path hold is far outside the quoted tail (the fixture bites)', 'CARD HOLD' not in W['note'].split('## error tail', 1)[-1],
          W['note'][-600:])
    check('D a hold anywhere in the failed log is not auto-retried', 'card held' in W['diag'].get('decision', '')
          and not any(c.endswith('/dispatches') for c in W['calls']) and 'odds-refresh' not in (W['state'] or {}),
          (W['diag'].get('decision'), W['calls'], W['state']))
    # E. the marker counts only as refresh.sh prints it (a line that is the CARD HOLD line), never as a
    #    word inside another line: a commit subject or a quoted script that names it is no hold
    W = watchdog('E', log_lines('git log: 5c4d3e2 docs: what a CARD HOLD means for the watchdog', 'grep -c "CARD HOLD" refresh.sh',
                                'odds_prefill.py: urllib.error.URLError: <urlopen error timed out>'))
    check('E a line that only mentions CARD HOLD is no hold: the ordinary failure is retried once',
          W['diag'].get('decision') == 'auto-redispatched once (30-min budget)', W['diag'].get('decision'))

    # C. control: any other failure keeps the budgeted retry (the fixture bites only the hold)
    W = watchdog('C', log_lines('odds_prefill.py: urllib.error.URLError: <urlopen error timed out>'))
    check('C an ordinary failure is still auto-redispatched once', W['diag'].get('decision') == 'auto-redispatched once (30-min budget)', W['diag'].get('decision'))
    check('C the retry dispatch is sent', any(c == 'POST repos/example/rixpicks/actions/workflows/367062180/dispatches' for c in W['calls']), W['calls'])
finally:
    for r in roots:
        shutil.rmtree(r, ignore_errors=True)

if failures:
    print(f'WATCHDOG CARD HOLD: {len(failures)} FAILURES')
    sys.exit(1)
print('WATCHDOG CARD HOLD: ALL PASS')
