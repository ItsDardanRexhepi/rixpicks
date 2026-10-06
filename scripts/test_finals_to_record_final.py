#!/usr/bin/env python3
"""finals_watch -> record_final end to end (Oct 2 review): the record write request finals_watch
queues goes straight into record_final, with nothing edited in between, and lands. finals_watch
queued the score with full team names ('Vancouver Canucks 1 @ Seattle Kraken 4'), which
record_final's score format (ESPN abbreviations, 'VAN 1 @ SEA 4') refuses as unparseable, so every
grade it queued stopped the in-order record write. One card, four finals in commence order: a
moneyline win, a total loss, an away spread cover (the card line is the HOME spread) and a total push.
finals_watch.main() runs for real with its private-infra calls (ledger, POST, second source, card
price ledger) stubbed; ESPN reads come from the fixtures below, the same ones record_final verifies
against. It runs with --live (finals_watch is a dry run by default; the queue is a live write).
Offline; writes only into a temp folder. Run: python3 scripts/test_finals_to_record_final.py"""
import contextlib, copy, importlib.util, io, json, os, shutil, sys, tempfile
from datetime import datetime as _real_dt, timezone
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
failures = 0

def check(name, actual, expected):
    global failures
    ok = actual == expected
    print(('OK  ' if ok else 'FAIL'), name, '' if ok else f'(got {actual!r}, want {expected!r})')
    if not ok:
        failures += 1

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

sys.path.insert(0, ROOT)  # core/ from this checkout
os.environ.setdefault('RIX_UNIT_DOLLARS', '1')
fw = load('finals_watch_e2e', os.path.join(HERE, 'finals_watch.py'))
rf = load('record_final_e2e', os.path.join(HERE, 'record_final.py'))

CORE = 'https://sports.core.api.espn.com/v2/sports/{lg}/events/{e}/competitions/{e}'
def core(away, away_ab, a_sc, home, home_ab, h_sc):
    # ESPN core competition shape (the $ref links resolved inline)
    return {'status': {'type': {'completed': True, 'name': 'STATUS_FINAL'}},
            'competitors': [{'homeAway': 'home', 'team': {'displayName': home, 'abbreviation': home_ab}, 'score': {'value': float(h_sc)}},
                            {'homeAway': 'away', 'team': {'displayName': away, 'abbreviation': away_ab}, 'score': {'value': float(a_sc)}}]}
FIX = {
    CORE.format(lg='hockey/leagues/nhl', e='401891900'): core('Vancouver Canucks', 'VAN', 1, 'Seattle Kraken', 'SEA', 4),
    CORE.format(lg='football/leagues/nfl', e='401872964'): core('Pittsburgh Steelers', 'PIT', 24, 'Cleveland Browns', 'CLE', 27),
    CORE.format(lg='basketball/leagues/wnba', e='401918022'): core('Indiana Fever', 'IND', 83, 'Las Vegas Aces', 'LV', 94),
    CORE.format(lg='baseball/leagues/mlb', e='401907897'): core('Chicago White Sox', 'CHW', 7, 'Houston Astros', 'HOU', 3)}
def fake_get(url, *a, **k):
    if url not in FIX:
        raise OSError(f'offline fixture missing {url}')
    return copy.deepcopy(FIX[url])

def pick(name, eid, league, away, home, commence, odds, cents, units, side, mc, line=None):
    p = {'name': name, 'market_class': mc, 'side': side, 'odds': odds, 'card_american': int(odds), 'units': units,
         'espn_league': league, 'kalshi': {'cents': cents},
         'game': {'away': away, 'home': home, 'commence': commence, 'eid': eid}}
    if line is not None:
        p['line'] = line
    return p
CARD = {'date': '2026-10-01', 'date_label': 'Thursday, Oct 1', 'record': '21-11', 'units_pl': '+4.76u', 'picks': [
    pick('Under 38.5', '401872964', 'football/nfl', 'Pittsburgh Steelers', 'Cleveland Browns', '2026-10-02T00:15Z', '-115', 53, '6u', 'under', 'total', 38.5),
    pick('Over 10', '401907897', 'baseball/mlb', 'Chicago White Sox', 'Houston Astros', '2026-10-01T23:10Z', '-110', 52, '5u', 'over', 'total', 10),
    # 'Fever +11.5': an away spread pick; the card line is the HOME spread (Aces -11.5)
    pick('Fever +11.5', '401918022', 'basketball/wnba', 'Indiana Fever', 'Las Vegas Aces', '2026-10-02T02:00Z', '-110', 52, '5u', 'away', 'spread', -11.5),
    pick('Kraken ML', '401891900', 'hockey/nhl', 'Vancouver Canucks', 'Seattle Kraken', '2026-10-01T23:00Z', '-140', 58, '5u', 'home', 'ml')]}
U0 = Decimal('4.761952343474163')  # exact running units behind the shown +4.76u

class FixedNow(_real_dt):  # 9:00 AM PT Oct 2: the Oct 1 card is yesterday's, inside the stale-manifest guard
    @classmethod
    def now(cls, tz=None):
        t = _real_dt(2026, 10, 2, 16, 0, tzinfo=timezone.utc)
        return t.astimezone(tz) if tz else t.astimezone().replace(tzinfo=None)

def run_finals_watch(tmp):
    """finals_watch.main() over the card, the private-infra edges stubbed; returns its stdout."""
    os.makedirs(os.path.join(tmp, 'scripts'), exist_ok=True)
    json.dump(CARD, open(os.path.join(tmp, 'manifest.json'), 'w'), indent=2)
    fw.MANIFEST = os.path.join(tmp, 'manifest.json')
    fw.HERE = os.path.join(tmp, 'scripts')  # record_request.json lands at tmp/record_request.json
    fw.STATE = os.path.join(tmp, 'finals_seen.json')
    fw.LEDGER = os.path.join(tmp, 'record_rows.jsonl')
    fw._secret = lambda name: ''  # no keychain or env secret is read in a fixture
    fw.datetime = FixedNow
    fw._get = fake_get
    fw.second_source = lambda p, primary, commence: {'source': 'fixture (independent)', 'away_id': primary['away'],
                                                     'home_id': primary['home'], 'away_score': primary['away_score'],
                                                     'home_score': primary['home_score']}
    fw._api_live_record = lambda: None
    fw._repo_mirror_record = lambda: None
    rp = fw.record_pipe
    rp.verified_grade_ids = lambda ledger: set()
    rp.resume_pending = lambda *a, **k: []
    rp.current_state = lambda ledger: (21, 11, U0)
    rp.on_final = lambda *a, **k: {'chain': 'post-failed-resumable', 'stages': {'post': 'dead token'}}
    by_eid = {p['game']['eid']: p for p in CARD['picks']}
    fw.fill_leak.card_price = lambda p: (by_eid[p['game']['eid']]['kalshi']['cents'],
                                         {'card_american': by_eid[p['game']['eid']]['card_american']}, 1)
    fw.fill_leak.fill_divergence = lambda p: []
    argv, sys.argv = sys.argv, ['finals_watch.py', '--live']  # dry run is the default; the queue is a live write
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            fw.main()
    finally:
        sys.argv = argv
    return out.getvalue()

def run_record_final(tmp):
    """record_final.main() on finals_watch's queue file exactly as it was written."""
    os.makedirs(os.path.join(tmp, 'manifests'), exist_ok=True)
    os.makedirs(os.path.join(tmp, 'slates'), exist_ok=True)
    json.dump(CARD, open(os.path.join(tmp, 'manifests', 'manifest-1001e2e00000.json'), 'w'), indent=2)
    json.dump({'days': []}, open(os.path.join(tmp, 'history.json'), 'w'), indent=2)
    json.dump({'processed': [], 'at': None, 'record_after': '21-11', 'units_after_exact': str(U0)},
              open(os.path.join(tmp, 'record_done.json'), 'w'), indent=2)
    rf.ROOT = tmp
    rf.REQ, rf.MAN, rf.HIST, rf.DONE = (os.path.join(tmp, f) for f in
                                        ('record_request.json', 'manifest.json', 'history.json', 'record_done.json'))
    rf.MANIFESTS = os.path.join(tmp, 'manifests')
    rf._get = fake_get
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = rf.main()
    return code, out.getvalue(), err.getvalue()

tmp = tempfile.mkdtemp(prefix='fw_rf_e2e_')
try:
    fw_out = run_finals_watch(tmp)
    queued = json.load(open(os.path.join(tmp, 'record_request.json')))['requests']
    check('finals_watch queued all four finals, in commence order', [q['pick'] for q in queued],
          ['Kraken ML', 'Over 10', 'Under 38.5', 'Fever +11.5'])
    check('finals_watch queues the score as ESPN abbreviations in the record_final format', [q['score'] for q in queued],
          ['VAN 1 @ SEA 4', 'CHW 7 @ HOU 3', 'PIT 24 @ CLE 27', 'IND 83 @ LV 94'])
    check('results as finals_watch graded them (ml W, total push, total L, away spread cover W)',
          [(q['market_class'], q['result']) for q in queued], [('ml', 'WON'), ('total', 'PUSH'), ('total', 'LOST'), ('spread', 'WON')])
    queued_before = copy.deepcopy(queued)
    code, out, err = run_record_final(tmp)
    check('record_final takes the queue file as finals_watch wrote it: exit 0, no refusal', (code, err.strip()), (0, ''))
    hist = json.load(open(os.path.join(tmp, 'history.json')))
    check('all four rows land on the Oct 1 card, in order, with the verified scores',
          [(d['date'], [(p['name'], p['result'], p['score']) for p in d['picks']]) for d in hist['days']],
          [('2026-10-01', [('Kraken ML', 'W', 'VAN 1, SEA 4'), ('Over 10', 'P', 'CHW 7, HOU 3'),
                           ('Under 38.5', 'L', 'PIT 24, CLE 27'), ('Fever +11.5', 'W', 'IND 83, LV 94')])])
    man = json.load(open(os.path.join(tmp, 'manifest.json')))
    want_units = U0 + Decimal(500) / 140 - 6 + Decimal(500) / 110
    check('record and units continue the chain', (man['record'], man['units_pl']), ('23-12', rf.fmt_units(want_units)))
    check('the queue is drained', json.load(open(os.path.join(tmp, 'record_request.json'))), {'requests': []})
    check('every queued grade key is recorded as processed', json.load(open(os.path.join(tmp, 'record_done.json')))['processed'],
          [q['grade_id'] for q in queued_before])
    # a score finals_watch cannot put in the record_final format is never queued: the chain stops
    tmp2 = tempfile.mkdtemp(prefix='fw_rf_e2e_')
    try:
        FIX[CORE.format(lg='hockey/leagues/nhl', e='401891900')]['competitors'][0]['team'].pop('abbreviation')
        fw_out = run_finals_watch(tmp2)
        q2 = json.load(open(os.path.join(tmp2, 'record_request.json')))['requests'] if os.path.exists(os.path.join(tmp2, 'record_request.json')) else []
        check('no ESPN abbreviation: the chain stops before that final, nothing queued after it', [q['pick'] for q in q2], [])
        check('no ESPN abbreviation: finals_watch says why', 'abbreviation' in fw_out and 'chain STOPS' in fw_out, True)
    finally:
        shutil.rmtree(tmp2, ignore_errors=True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
