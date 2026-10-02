#!/usr/bin/env python3
"""Predictions wording fixture (Oct 1 sweep, OS-15) for scripts/predictions.py.

'Predictions by UltRix' read 'Orlando Pride beat San Diego Wave FC' for games not yet played
(J-103 narrative truth: a prediction must read as a prediction). Rules under test:
- probe() writes new predictions as 'X to beat Y' for every league
- the public artifact words every pending prediction as 'X to beat Y', including ledger rows
  written before the fix, while the ledger's stored text stays exactly as written
Network and the model calls are mocked; time is pinned.
"""
import importlib.util, json, os, re, sys, tempfile
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('predictions', os.path.join(HERE, 'predictions.py'))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

PINNED = datetime(2026, 10, 2, 4, 30, tzinfo=timezone.utc)
M.now = lambda: PINNED
M.get_json = lambda url, timeout=30: {'events': []}
M.time.sleep = lambda s: None

checks = []
def check(name, ok):
    checks.append((name, bool(ok)))
PAST = re.compile(r'^(?!.*\bto beat\b).*\bbeat\b')

# probe(): every league, both sides of the old MLS/NWSL conditional
for league, home, away, pick in [('NWSL', 'Orlando Pride', 'San Diego Wave FC', 'Orlando Pride'),
                                 ('CFB', 'Alabama Crimson Tide', 'Mississippi State Bulldogs', 'Alabama Crimson Tide'),
                                 ('NHL', 'Detroit Red Wings', 'New York Rangers', 'New York Rangers')]:
    M.probe_once = lambda prompt, _p=pick: (_p, 0.8, 'fixture')
    ev = {'id': 'E-' + league, 'league': league, 'path': 'x/y', 'home': home, 'away': away,
          'date': PINNED + timedelta(days=1)}
    r = M.probe(ev, '', '')
    other = away if pick == home else home
    check(f'probe() {league}: new prediction reads as a forecast', r and r['prediction'] == f'{pick} to beat {other}')

# main(): legacy past-tense pending rows are worded as forecasts in the artifact only
tmp = tempfile.mkdtemp()
M.ARTIFACT = os.path.join(tmp, 'predictions.json')
M.LEDGER = os.path.join(tmp, 'predictions_ledger.json')
KO = (PINNED + timedelta(hours=20)).isoformat()
legacy = [
    {'id': 'a1', 'event_id': 'E1', 'league': 'NWSL', 'path': 'soccer/usa.nwsl', 'home': 'Orlando Pride',
     'away': 'San Diego Wave FC', 'pick_team': 'Orlando Pride', 'prediction': 'Orlando Pride beat San Diego Wave FC',
     'kickoff_utc': KO, 'status': 'pending', 'created_at': PINNED.isoformat()},
    {'id': 'a2', 'event_id': 'E2', 'league': 'NHL', 'path': 'hockey/nhl', 'home': 'Detroit Red Wings',
     'away': 'New York Rangers', 'pick_team': 'New York Rangers', 'prediction': 'New York Rangers beat Detroit Red Wings',
     'kickoff_utc': KO, 'status': 'pending', 'created_at': PINNED.isoformat()},
    {'id': 'a3', 'event_id': 'E3', 'league': 'NFL', 'path': 'football/nfl', 'home': 'Cleveland Browns',
     'away': 'Pittsburgh Steelers', 'pick_team': 'Cleveland Browns', 'prediction': 'Cleveland Browns beat Pittsburgh Steelers',
     'kickoff_utc': (PINNED - timedelta(hours=30)).isoformat(), 'status': 'hit', 'created_at': PINNED.isoformat()},
]
json.dump(legacy, open(M.LEDGER, 'w'))
json.dump({'generated_at': '2000-01-01T00:00:00+00:00', 'items': []}, open(M.ARTIFACT, 'w'))
M.upcoming = lambda: []
sys.argv = ['predictions.py', '--force']
M.main()
art = json.load(open(M.ARTIFACT))
led = json.load(open(M.LEDGER))
words = {i['id']: i['prediction'] for i in art['items']}
check('artifact: legacy NWSL row reads Orlando Pride to beat San Diego Wave FC', words.get('a1') == 'Orlando Pride to beat San Diego Wave FC')
check('artifact: legacy away pick reads New York Rangers to beat Detroit Red Wings', words.get('a2') == 'New York Rangers to beat Detroit Red Wings')
check('artifact: no pending prediction is worded in the past tense', words and not any(PAST.search(w) for w in words.values()))
check('ledger: stored prediction text unchanged (record is append-only)',
      [p['prediction'] for p in led] == [p['prediction'] for p in legacy])
check('ledger: settled row untouched', led[2]['status'] == 'hit' and led[2]['prediction'] == 'Cleveland Browns beat Pittsburgh Steelers')

for name, ok in checks:
    print(('PASS ' if ok else 'FAIL ') + name)
failed = [n for n, ok in checks if not ok]
if failed:
    print('\n%d FAIL' % len(failed)); sys.exit(1)
print('\nall %d PASS' % len(checks))
