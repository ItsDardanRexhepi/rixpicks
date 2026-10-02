#!/usr/bin/env python3
"""Fixture for scripts/nfl_scores_confirm.sh (the nfl-scores-confirm lane). No network, no key,
no credits: the script runs in a scratch tree with a stub `curl` on PATH that serves an ESPN
scoreboard and a the-odds-api scores body from fixtures and logs every request.

F3 (Oct 2 TNF): the lane pulled only while an ESPN event was 'in', so the last game of each
live window was frozen mid-game (PIT @ CLE 7-7, completed false) and never recorded final.
A game the file holds as started-but-not-completed, kicked off within the chase window, gets
one more pull per cycle until the-odds-api reports it completed.
F5 (ci review): the chase is bounded to games ESPN reports in progress or final; a postponed,
canceled, still-'pre' or unlisted game never spends a pull.
LS-22: the public nfl_scores.json must not carry the API credit count.
Run: python3 scripts/test_nfl_scores_confirm.py   (exit 1 on any failure)
"""
import json, os, shutil, subprocess, sys, tempfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, 'nfl_scores_confirm.sh')
NOW = datetime.now(timezone.utc)
ISO = lambda dt: dt.strftime('%Y-%m-%dT%H:%M:%SZ')

failures = []
def check(label, got, want):
    ok = got == want
    if not ok:
        failures.append(f'{label}: want {want!r} got {got!r}')
    print(f"{'OK  ' if ok else 'FAIL'} {label}" + ('' if ok else f'  [want {want!r} got {got!r}]'))

STUB_CURL = r'''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
url = next(a for a in args if a.startswith('http'))
out = args[args.index('-o') + 1] if '-o' in args else None
hdr = args[args.index('-D') + 1] if '-D' in args else None
fx = os.environ['FIXDIR']
with open(os.path.join(fx, 'calls.log'), 'a') as f:
    f.write(url.split('apiKey=')[0] + '\n')
body = open(os.path.join(fx, 'espn.json' if 'site.api.espn.com' in url else 'odds.json')).read()
if hdr:
    open(hdr, 'w').write('HTTP/2 200\r\nx-requests-used: 663\r\nx-requests-remaining: 19337\r\n\r\n')
if out:
    open(out, 'w').write(body)
else:
    sys.stdout.write(body)
'''

def game(gid, home, away, commence, completed, scores):
    g = {'id': gid, 'sport_key': 'americanfootball_nfl', 'commence_time': ISO(commence),
         'home_team': home, 'away_team': away, 'completed': completed,
         'scores': None if scores is None else [{'name': home, 'score': str(scores[0])}, {'name': away, 'score': str(scores[1])}],
         'last_update': ISO(NOW - timedelta(minutes=5)) if scores else None}
    return g

def run(case, espn_states, prior_games, odds_games):
    """Run the lane once. Returns (pulls, written nfl_scores.json or None)."""
    root = tempfile.mkdtemp(prefix='nflsc_')
    try:
        os.makedirs(os.path.join(root, 'scripts'))
        shutil.copy(SCRIPT, os.path.join(root, 'scripts', 'nfl_scores_confirm.sh'))
        fx = os.path.join(root, 'fx'); os.makedirs(fx)
        bindir = os.path.join(root, 'bin'); os.makedirs(bindir)
        open(os.path.join(bindir, 'curl'), 'w').write('#!' + sys.executable + '\n' + STUB_CURL.split('\n', 1)[1])
        os.chmod(os.path.join(bindir, 'curl'), 0o755)
        json.dump({'events': [ev if isinstance(ev, dict) else {'id': str(i), 'status': {'type': {'state': ev}}}
                              for i, ev in enumerate(espn_states)]}, open(os.path.join(fx, 'espn.json'), 'w'))
        json.dump(odds_games, open(os.path.join(fx, 'odds.json'), 'w'))
        prior = os.path.join(root, 'nfl_scores.json')
        if prior_games is not None:
            json.dump({'pulled_at_utc': ISO(NOW - timedelta(hours=3)), 'source': 'the-odds-api v4 nfl scores (daysFrom=1)',
                       'games': prior_games}, open(prior, 'w'), indent=1)
        before = open(prior).read() if os.path.exists(prior) else None
        env = dict(os.environ, PATH=bindir + os.pathsep + os.environ.get('PATH', ''), FIXDIR=fx,
                   THE_ODDS_API_KEY='fixture-key')
        r = subprocess.run(['bash', os.path.join(root, 'scripts', 'nfl_scores_confirm.sh')],
                           capture_output=True, text=True, env=env, timeout=120)
        if r.returncode != 0:
            failures.append(f'{case}: lane exited {r.returncode}: {(r.stderr or r.stdout)[-300:]}')
        calls = open(os.path.join(fx, 'calls.log')).read().splitlines() if os.path.exists(os.path.join(fx, 'calls.log')) else []
        pulls = sum(1 for c in calls if 'api.the-odds-api.com' in c)
        after = open(prior).read() if os.path.exists(prior) else None
        written = json.loads(after) if after is not None and after != before else None
        return pulls, written, r.stdout + r.stderr
    finally:
        shutil.rmtree(root, ignore_errors=True)

def espn(home, away, state, completed=False, name=None, desc=None):
    # ESPN scoreboard event shape: the chase binds the file's game to it by home and away team
    return {'id': home[:3] + away[:3], 'date': ISO(NOW), 'status': {'type': {
                'state': state, 'completed': completed, 'name': name or {'pre': 'STATUS_SCHEDULED', 'in': 'STATUS_IN_PROGRESS', 'post': 'STATUS_FINAL'}[state],
                'description': desc or ''}},
            'competitions': [{'competitors': [{'homeAway': 'home', 'team': {'displayName': home}},
                                              {'homeAway': 'away', 'team': {'displayName': away}}]}]}

TNF_KO = NOW - timedelta(hours=3, minutes=50)
LIVE = game('tnf', 'Cleveland Browns', 'Pittsburgh Steelers', TNF_KO, False, (7, 7))
FINAL = game('tnf', 'Cleveland Browns', 'Pittsburgh Steelers', TNF_KO, True, (27, 24))
UPCOMING = game('sun1', 'Detroit Lions', 'Chicago Bears', NOW + timedelta(days=3), False, None)

# A (F3): no ESPN event 'in' any more, the file froze TNF mid-game -> one more pull lands the final
TNF_FINAL_ESPN = espn('Cleveland Browns', 'Pittsburgh Steelers', 'post', True, 'STATUS_FINAL', 'Final')
pulls, w, log = run('A', [TNF_FINAL_ESPN], [LIVE, UPCOMING], [FINAL, UPCOMING])
check('A final whistle: one chase pull after the game left the live state', pulls, 1)
g = next((x for x in (w or {}).get('games', []) if x.get('id') == 'tnf'), {})
check('A final recorded: completed true', g.get('completed'), True)
check('A final recorded: 27-24', sorted(int(s['score']) for s in g.get('scores') or []), [24, 27])

# B: the chase stops once the file holds the final (free, no write)
pulls, w, log = run('B', ['post'], [FINAL, UPCOMING], [FINAL, UPCOMING])
check('B final already recorded: no pull', pulls, 0)
check('B final already recorded: file untouched', w, None)

# C: the chase is bounded - a game that kicked off outside the window never pulls
OLD = game('old', 'Cleveland Browns', 'Pittsburgh Steelers', NOW - timedelta(hours=9), False, (7, 7))
pulls, w, log = run('C', ['post'], [OLD, UPCOMING], [OLD, UPCOMING])
check('C stale unfinished game outside the chase window: no pull', pulls, 0)

# D: a not-yet-started game never triggers a pull
pulls, w, log = run('D', ['pre'], [UPCOMING], [UPCOMING])
check('D upcoming only: no pull', pulls, 0)

# E: a live game still pulls (existing gate)
pulls, w, log = run('E', ['in', 'pre'], [UPCOMING], [LIVE, UPCOMING])
check('E live game: one pull', pulls, 1)
check('E live game: file written', w is not None, True)

# F (LS-22): the public file never carries the provider credit count
for case_w in (w,):
    keys = set((case_w or {}).keys())
    check('F public nfl_scores.json has no credit count', sorted(k for k in keys if 'credit' in k or 'remaining' in k), [])
check('F credit count stays visible in the run log', 'credits remaining: 19337' in log, True)

# H-K (F5): the chase spends a pull only on a game ESPN reports in progress or played to a final;
# a postponed, canceled, still-'pre' or unlisted game is never chased (it used to pull every cycle
# for the whole 5h window: up to 20 paid pulls on a game that never started)
for case, ev, why in (
        ('H', espn('Cleveland Browns', 'Pittsburgh Steelers', 'post', True, 'STATUS_POSTPONED', 'Postponed'), 'postponed (ESPN post, completed)'),
        ('H2', espn('Cleveland Browns', 'Pittsburgh Steelers', 'post', False, 'STATUS_POSTPONED', 'Postponed'), 'postponed (ESPN post, not completed)'),
        ('I', espn('Cleveland Browns', 'Pittsburgh Steelers', 'post', True, 'STATUS_CANCELED', 'Canceled'), 'canceled'),
        ('J', espn('Cleveland Browns', 'Pittsburgh Steelers', 'pre', False, 'STATUS_DELAYED', 'Delayed'), "still 'pre' (delayed start)"),
        ('K', espn('Detroit Lions', 'Chicago Bears', 'pre'), 'not on the ESPN board')):
    pulls, w, log = run(case, [ev], [LIVE, UPCOMING], [FINAL, UPCOMING])
    check(f'{case} game the file holds as kicked off but ESPN reports {why}: no pull', pulls, 0)
    check(f'{case} {why}: file untouched', w, None)
check('K the skipped chase says why in the run log', 'chase skipped: Pittsburgh Steelers @ Cleveland Browns' in log, True)
pulls, w, log = run('L', [espn('Cleveland Browns', 'Pittsburgh Steelers', 'in')], [LIVE, UPCOMING], [LIVE, UPCOMING])
check('L the same game ESPN reports in progress: one pull', pulls, 1)

# G: no prior file (first run) with nothing live - free
pulls, w, log = run('G', ['post'], None, [FINAL])
check('G no prior file, nothing live: no pull', pulls, 0)

if failures:
    print(f'NFL SCORES CONFIRM: {len(failures)} FAILURES')
    sys.exit(1)
print('NFL SCORES CONFIRM: ALL PASS')
