#!/usr/bin/env python3
"""Fixture-based unit tests for scripts/odds_prefill_props.py.
No network, no API key, no credits: fixtures under scripts/fixtures/ stand in
for The Odds API responses, and budget/urlopen are stubbed where the real-pull
path is under test. Run: python3 scripts/test_odds_prefill_props.py"""
import importlib.util, json, os, sys, tempfile
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('odds_prefill_props', os.path.join(HERE, 'odds_prefill_props.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

FIX_NFL = os.path.join(HERE, 'fixtures', 'odds_prefill_props_nfl.json')
FIX_MLB = os.path.join(HERE, 'fixtures', 'odds_prefill_props_mlb.json')

fails = []
def check(cond, label):
    if not cond:
        fails.append(label)

# T1 shared normalization: lowercase + strip non-alphanumerics
check(m.norm_player('Jalen Hurts') == 'jalenhurts', 'T1 basic')
check(m.norm_player('T.J. Watt Jr.') == 'tjwattjr', 'T1 punctuation')
check(m.norm_player("De'Von Achane") == 'devonachane', 'T1 apostrophe')
check(m.norm_player('  D.K. METCALF ') == 'dkmetcalf', 'T1 case/space')
check(m.norm_player('') == '' and m.norm_player(None) == '', 'T1 empty')
print('T1 OK')

# T2 NFL fixture end-to-end: writes only the props json, correct rows
tmp = tempfile.mkdtemp()
out = os.path.join(tmp, 'odds_prefill_props.json')
m.OUT, m.FIXTURE = out, FIX_NFL
m.main(['americanfootball_nfl', 'a512a48a58c4329048174217b2cc7ce0'])
payload = json.load(open(out))
check(payload['markets'] == m.MARKETS_BY_SPORT['americanfootball_nfl'], 'T2 market list')
props = {(r['player_key'], r['market'], r['book']): r for r in payload['props']}
check(len(payload['props']) == 3, 'T2 row count')
hurts_dk = props.get(('jalenhurts', 'player_pass_yds', 'draftkings'))
check(hurts_dk and hurts_dk['point'] == 243.5 and hurts_dk['over'] == -115 and hurts_dk['under'] == -105, 'T2 hurts dk')
hurts_fd = props.get(('jalenhurts', 'player_pass_yds', 'fanduel'))
check(hurts_fd and hurts_fd['point'] == 244.5, 'T2 hurts fd distinct line per book')
saquon = props.get(('saquonbarkley', 'player_anytime_td', 'draftkings'))
check(saquon and saquon['yes'] == -140 and saquon['no'] == 110 and saquon['point'] is None, 'T2 anytime td yes/no')
check(all(r['provider_event_id'] == 'a512a48a58c4329048174217b2cc7ce0' for r in payload['props']), 'T2 event id stamped')
check(all(r['home_team'] == 'Philadelphia Eagles' for r in payload['props']), 'T2 teams carried')
check(sorted(os.listdir(tmp)) == ['odds_prefill_props.json'], 'T2 writes ONLY the props json')
print('T2 OK')

# T3 MLB fixture: batter_*/pitcher_* keys parse
out = os.path.join(tmp, 'mlb.json')
m.OUT, m.FIXTURE = out, FIX_MLB
m.main(['baseball_mlb', 'b7c2f1a09e4d4f3c8c1f0aabbccddeef'])
payload = json.load(open(out))
props = {(r['player_key'], r['market']): r for r in payload['props']}
check(payload['markets'] == m.MARKETS_BY_SPORT['baseball_mlb'], 'T3 market list')
wheeler = props.get(('zackwheeler', 'pitcher_strikeouts'))
check(wheeler and wheeler['point'] == 6.5 and wheeler['over'] == -120, 'T3 pitcher ks')
turner = props.get(('treaturner', 'batter_hits'))
check(turner and turner['over'] == -150 and turner['under'] == 120, 'T3 batter hits')
print('T3 OK')

# T4 budget guard: cap refusal blocks the pull before any network
m.FIXTURE = None
with mock.patch('core.budget.check_and_log', side_effect=ValueError('credit cap')) as guard, \
     mock.patch('urllib.request.urlopen') as net:
    try:
        m.fetch_event('americanfootball_nfl', 'eid-x')
        check(False, 'T4 cap refusal must propagate')
    except ValueError:
        pass
    check(net.call_count == 0, 'T4 no network call after cap refusal')
    check(guard.call_count == 1, 'T4 guard consulted once')
    _, markets_arg, credits_arg = guard.call_args[0]
    check(credits_arg == len(m.MARKETS_BY_SPORT['americanfootball_nfl']), 'T4 worst-case credits logged pre-pull')
    check('player_anytime_td' in markets_arg, 'T4 markets logged')
print('T4 OK')

# T5 key comes from THE_ODDS_API_KEY env only; missing key errors before network
os.environ.pop('THE_ODDS_API_KEY', None)
m._K = None
with mock.patch('core.budget.check_and_log'), mock.patch('urllib.request.urlopen') as net:
    try:
        m.fetch_event('baseball_mlb', 'eid-y')
        check(False, 'T5 missing key must raise')
    except RuntimeError as e:
        check('THE_ODDS_API_KEY' in str(e), 'T5 error names the env var')
    check(net.call_count == 0, 'T5 no network without key')
print('T5 OK')

# T6 URL/params of the real pull (endpoint, region, markets) without hitting network
os.environ['THE_ODDS_API_KEY'] = 'fixture-key'
m._K = None
class FakeResp:
    headers = {'x-requests-last': '6', 'x-requests-remaining': '994'}
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return open(FIX_NFL, 'rb').read()
with mock.patch('core.budget.check_and_log') as guard, \
     mock.patch('urllib.request.urlopen', return_value=FakeResp()) as net:
    ev = m.fetch_event('americanfootball_nfl', 'a512a48a58c4329048174217b2cc7ce0')
url = net.call_args[0][0].full_url
check('/v4/sports/americanfootball_nfl/events/a512a48a58c4329048174217b2cc7ce0/odds' in url, 'T6 event-scoped endpoint')
check('regions=us' in url, 'T6 us region only')
check('markets=' + ','.join(m.MARKETS_BY_SPORT['americanfootball_nfl']) in url, 'T6 all NFL markets requested in one pull')
check('apiKey=fixture-key' in url, 'T6 env key used')
check(ev['id'] == 'a512a48a58c4329048174217b2cc7ce0', 'T6 event parsed')
print('T6 OK')

os.environ.pop('THE_ODDS_API_KEY', None)
if fails:
    print('FAILS:', fails)
    sys.exit(1)
print('ALL TESTS PASSED')
