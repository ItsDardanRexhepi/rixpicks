#!/usr/bin/env python3
"""Bite-proof fixture for K20/K21 in scripts/predictions.py (auditor 9/30).

K20: settle() searched the ESPN board only at the kickoff's UTC date; late PT/ET
events live on the prior local-date board (VAN 6-EDM 5 OT, VGK 5-CHI 2 on the
Sep 29 board with kickoffs on Sep 30 UTC) and were headed for the 36h void.
K21: main() read ev['kickoff_utc'] but upcoming() returns the kickoff under
'date' (a datetime) - every genuine new candidate KeyError'd out before probe().

Runs the REAL settle()/main() paths against live-shaped board payloads (network
mocked, time pinned). Bites on the unfixed source.
"""
import json, os, sys, types, importlib.util
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('predictions', os.path.join(HERE, 'predictions.py'))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

PINNED_NOW = datetime(2026, 9, 30, 11, 0, 0, tzinfo=timezone.utc)  # kickoffs ~9h old, well inside 36h
ET, PT = ZoneInfo('America/New_York'), ZoneInfo('America/Los_Angeles')

def ev_json(eid, home, away, winner_name, state='post'):
    return {'id': eid, 'competitions': [{'status': {'type': {'state': state}}, 'competitors': [
        {'team': {'displayName': home}, 'homeAway': 'home', 'winner': winner_name == home},
        {'team': {'displayName': away}, 'homeAway': 'away', 'winner': winner_name == away}]}]}

# real shapes: both NHL finals sit on the Sep 29 board; kickoffs are Sep 30 UTC
EDM_KO = datetime(2026, 9, 30, 2, 0, 0, tzinfo=timezone.utc)   # ET Sep 29 22:00, PT Sep 29 19:00
VGK_KO = datetime(2026, 9, 30, 3, 30, 0, tzinfo=timezone.utc)  # ET Sep 29 23:30
BOARDS = {
    '20260929': {'events': [ev_json('E1', 'Vancouver Canucks', 'Edmonton Oilers', 'Vancouver Canucks'),
                            ev_json('E2', 'Vegas Golden Knights', 'Chicago Blackhawks', 'Vegas Golden Knights')]},
    '20260930': {'events': []},  # the date the old code searched
}

def fake_get_json(url, timeout=30):
    assert 'scoreboard' in url, url
    day = url.split('dates=')[1][:8] if 'dates=' in url else None
    if day is None:
        return {'events': []}  # upcoming() default board: nothing new in this fixture's settle phase
    return BOARDS.get(day, {'events': []})

M.get_json = fake_get_json
M.now = lambda: PINNED_NOW

led = [
    {'id': 'p1', 'event_id': 'E1', 'path': 'hockey/nhl', 'league': 'NHL', 'home': 'Vancouver Canucks',
     'away': 'Edmonton Oilers', 'pick_team': 'Edmonton Oilers', 'prediction': 'Edmonton Oilers win',
     'kickoff_utc': EDM_KO.isoformat().replace('+00:00', 'Z'), 'status': 'pending'},
    {'id': 'p2', 'event_id': 'E2', 'path': 'hockey/nhl', 'league': 'NHL', 'home': 'Vegas Golden Knights',
     'away': 'Chicago Blackhawks', 'pick_team': 'Vegas Golden Knights', 'prediction': 'Vegas Golden Knights win',
     'kickoff_utc': VGK_KO.isoformat().replace('+00:00', 'Z'), 'status': 'pending'},
]

checks = []
n = M.settle(led)
checks.append(('K20 settle() settles both board-date-mismatched finals (n==2)', n == 2))
checks.append(('K20 EDM away pick graded miss (VAN won 6-5 OT)', led[0].get('status') == 'miss'))
checks.append(('K20 VGK home pick graded hit (VGK won 5-2)', led[1].get('status') == 'hit'))
checks.append(('K20 both rows carry settled_at', all(p.get('settled_at') for p in led)))
checks.append(('K20 neither row voided before the 36h clock', all(p.get('status') != 'void' for p in led)))

# K21: main() end-to-end with one genuine upcoming() candidate carrying 'date' (no 'kickoff_utc')
import tempfile
tmp = tempfile.mkdtemp()
M.ARTIFACT = os.path.join(tmp, 'predictions.json')
M.LEDGER = os.path.join(tmp, 'predictions_ledger.json')
json.dump([], open(M.LEDGER, 'w'))
json.dump({'generated_at': '2000-01-01T00:00:00+00:00', 'items': []}, open(M.ARTIFACT, 'w'))
sys.argv = ['predictions.py', '--force']

NEW_KO = PINNED_NOW + timedelta(hours=20)
probed = []
M.upcoming = lambda: [{'id': 'E9', 'league': 'NHL', 'path': 'hockey/nhl',
                       'home': 'Seattle Kraken', 'away': 'Calgary Flames', 'date': NEW_KO}]
def fake_probe(ev, news, misses):
    probed.append(ev)
    return {'id': 'p9', 'event_id': ev['id'], 'path': ev['path'], 'league': ev['league'],
            'home': ev['home'], 'away': ev['away'], 'pick_team': ev['home'],
            'prediction': f"{ev['home']} win", 'kickoff_utc': ev['date'].isoformat().replace('+00:00', 'Z'),
            'status': 'pending'}
M.probe = fake_probe
M.news_context = lambda lg: ''
M.miss_context = lambda ledger, lg: ''
M.time.sleep = lambda s: None

M.main()
led2 = json.load(open(M.LEDGER))
checks.append(('K21 main() actually probed the genuine upcoming() candidate (not KeyError-skipped)', len(probed) == 1))
checks.append(('K21 approved prediction landed in the ledger', any(p.get('id') == 'p9' for p in led2)))
art = json.load(open(M.ARTIFACT))
checks.append(('K21 artifact carries the new pending prediction', any(i.get('id') == 'p9' for i in art.get('items', []))))
src = open(os.path.join(HERE, 'predictions.py')).read()
main_body = src.split('def main():', 1)[1]
checks.append(("K21 main() no longer reads ev['kickoff_utc']", "ev['kickoff_utc']" not in main_body))
checks.append(("K20 settle() searches local-date boards, not kickoff-date only", 'America/New_York' in src and 'America/Los_Angeles' in src))

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(('PASS ' if ok else 'FAIL ') + name)
if failed:
    print(f'\n{len(failed)} FAIL'); sys.exit(1)
print(f'\nall {len(checks)} PASS')
