#!/usr/bin/env python3
"""The predictions void clock comes after the result lookup (scripts/predictions.py settle()).

settle() is documented as "grade pending predictions whose event finished; void if unverifiable
after 36h". Before this, it voided every pending row older than 36 hours before it read the board,
so a result that was on the board and verifiable was dropped from the public record whenever the
producer reached the row late (a run gap, a billing lock, or a result the old code could not read,
such as the NWSL 401854019 draw). A dropped miss raises the hit rate.

Checked here, offline, on board-shaped payloads with the clock pinned:
  - past 36 h, a verifiable result settles (hit and miss), never a void;
  - past 36 h, a row that cannot be verified still voids: event not on any board, event not final,
    a winner name that resolves to neither team, a board fetch that fails;
  - inside 36 h an unverifiable row stays pending, and a row under 2.5 h is not looked up at all.
Run: python3 scripts/test_predictions_void_clock.py"""
import importlib.util, os, sys
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('predictions_void_clock', os.path.join(HERE, 'predictions.py'))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
M.now = lambda: NOW

failures = 0
def check(name, actual, expected):
    global failures
    ok = actual == expected
    print(('OK  ' if ok else 'FAIL'), name, '' if ok else f'(got {actual!r}, want {expected!r})')
    if not ok:
        failures += 1

def ev(eid, home, away, winner, state='post'):
    return {'id': eid, 'competitions': [{'status': {'type': {'state': state}}, 'competitors': [
        {'team': {'displayName': home}, 'homeAway': 'home', 'winner': winner == home},
        {'team': {'displayName': away}, 'homeAway': 'away', 'winner': winner == away}]}]}

def row(eid, home, away, pick, age_h):
    ko = NOW - timedelta(hours=age_h)
    return {'id': 'r' + eid, 'event_id': eid, 'league': 'NHL', 'path': 'hockey/nhl', 'home': home, 'away': away,
            'pick_team': pick, 'prediction': f'{pick} to beat {away if pick == home else home}',
            'kickoff_utc': ko.isoformat(), 'status': 'pending'}

calls = []
def board(events):
    def get(url, timeout=30):
        calls.append(url)
        return {'events': events}
    return get

# ---------- past 36 h: a verifiable result settles ----------
M.get_json = board([ev('A1', 'Pittsburgh Penguins', 'Winnipeg Jets', 'Winnipeg Jets'),
                    ev('A2', 'Dallas Stars', 'San Jose Sharks', 'Dallas Stars')])
led = [row('A1', 'Pittsburgh Penguins', 'Winnipeg Jets', 'Pittsburgh Penguins', 48),
       row('A2', 'Dallas Stars', 'San Jose Sharks', 'Dallas Stars', 72)]
n = M.settle(led)
check('48 h old, verifiable loss on the board: settles miss, not void', (led[0]['status'], bool(led[0].get('settled_at'))), ('miss', True))
check('72 h old, verifiable win on the board: settles hit, not void', (led[1]['status'], bool(led[1].get('settled_at'))), ('hit', True))
check('both counted as changed', n, 2)

# ---------- past 36 h: an unverifiable row still voids ----------
M.get_json = board([ev('B2', 'Seattle Kraken', 'Calgary Flames', None, state='in'),
                    ev('B3', 'Utah Mammoth', 'Anaheim Ducks', 'Some Other Club')])
led = [row('B1', 'Boston Bruins', 'Buffalo Sabres', 'Boston Bruins', 40),       # on no board
       row('B2', 'Seattle Kraken', 'Calgary Flames', 'Seattle Kraken', 40),     # not final
       row('B3', 'Utah Mammoth', 'Anaheim Ducks', 'Utah Mammoth', 40)]          # winner resolves to neither team
n = M.settle(led)
check('40 h old, event on no board: void', led[0]['status'], 'void')
check('40 h old, event not final: void', led[1]['status'], 'void')
check('40 h old, winner name resolves to neither team: void', led[2]['status'], 'void')
check('void rows carry no settled_at', any(p.get('settled_at') for p in led), False)
check('three voids counted as changed', n, 3)

def offline(url, timeout=30):
    raise OSError('offline')
M.get_json = offline
led = [row('C1', 'Boston Bruins', 'Buffalo Sabres', 'Boston Bruins', 40)]
n = M.settle(led)
check('40 h old, board fetch fails: void (the clock still closes)', (led[0]['status'], n), ('void', 1))

# ---------- inside 36 h: nothing voids; under 2.5 h: no lookup ----------
M.get_json = board([])
led = [row('D1', 'Boston Bruins', 'Buffalo Sabres', 'Boston Bruins', 10)]
n = M.settle(led)
check('10 h old, event on no board: stays pending', (led[0]['status'], n), ('pending', 0))
M.get_json = offline
led = [row('D2', 'Boston Bruins', 'Buffalo Sabres', 'Boston Bruins', 10)]
n = M.settle(led)
check('10 h old, board fetch fails: stays pending', (led[0]['status'], n), ('pending', 0))
calls.clear()
M.get_json = board([ev('E1', 'Boston Bruins', 'Buffalo Sabres', 'Boston Bruins')])
led = [row('E1', 'Boston Bruins', 'Buffalo Sabres', 'Boston Bruins', 1)]
n = M.settle(led)
check('1 h old: stays pending and the board is not read', (led[0]['status'], n, len(calls)), ('pending', 0, 0))
led = [dict(row('E1', 'Boston Bruins', 'Buffalo Sabres', 'Boston Bruins', 48), status='hit')]
n = M.settle(led)
check('a settled row is left alone', (led[0]['status'], n), ('hit', 0))

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
