#!/usr/bin/env python3
"""Soccer results grade on regulation time, as Kalshi settles (core/soccer_result.py).

Kalshi's MLS and NWSL game, spread and total contracts settle after 90 minutes plus stoppage time:
a draw resolves the TIE contract yes and both team contracts no, and extra time or a shootout never
counts. Before this, record_final.score_result and finals_watch.grade scored a level moneyline as a
PUSH for every league and graded on ESPN's final, which includes extra time, and predictions.py left
a drawn match pending until it voided. Checked here, offline, on recorded ESPN data (trimmed to the
fields the graders read, values untouched; tests/fixtures/soccer/):
  - MLS 761439 (St. Louis 1-1 Charlotte, full time): either side's moneyline is LOST;
  - NWSL 760606 (Kansas City 1-1 Gotham at 90 minutes, Gotham 2-1 after extra time): a Gotham
    moneyline is LOST and Under 2.5 is WON - through record_final's full record write and
    finals_watch's grade;
  - NWSL 760609 (1-1, Washington won the shootout): Washington's moneyline is LOST;
  - an NFL tie still grades PUSH;
  - the predictions ledger row for NWSL 401854019 (Angel City to beat Gotham, 1-1) settles a miss.
The card used for 760606 is a fixture card (no card carried those picks); the scores are ESPN's.
Run: python3 scripts/test_soccer_regulation.py"""
import contextlib, copy, importlib.util, io, json, os, shutil, sys, tempfile
from datetime import datetime, timezone
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIX = os.path.join(ROOT, 'tests', 'fixtures', 'soccer')
sys.path.insert(0, ROOT)
os.environ.setdefault('RIX_UNIT_DOLLARS', '1')  # placeholder: unit results do not depend on the size
for k in ('RPS_KB', 'RIX_REPO', 'RIX_FINALS_CONFIG'):
    os.environ.pop(k, None)  # finals_watch reads these at import; this fixture runs on its own paths
from core import soccer_result

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

def fx(name):
    return json.load(open(os.path.join(FIX, name)))

def raises(fn):
    try:
        fn()
    except ValueError as e:
        return str(e)
    return None

SUM = {eid: fx(f'summary_{eid}.json') for eid in ('761439', '760606', '760609', '401854019')}
CORE = fx('espn_core.json')
SUMMARY_URL = 'https://site.api.espn.com/apis/site/v2/sports/{lg}/summary?event={eid}'
LEAGUE = {'761439': 'soccer/usa.1', '760606': 'soccer/usa.nwsl', '760609': 'soccer/usa.nwsl', '401854019': 'soccer/usa.nwsl'}

# ---------- 1. the regulation score, from the recorded summaries ----------
reg = {eid: soccer_result.regulation_score(d) for eid, d in SUM.items()}
check('761439 MLS full time: 1-1 in regulation, no extra time',
      (reg['761439']['home'], reg['761439']['away'], reg['761439']['extra_time']), (1, 1, False))
check('760606 NWSL: 1-1 at 90 minutes, ESPN final 1-2 after extra time (Gotham away)',
      (reg['760606']['home'], reg['760606']['away'], reg['760606']['final_home'], reg['760606']['final_away'], reg['760606']['status']),
      (1, 1, 1, 2, 'STATUS_FINAL_AET'))
check('760609 NWSL: 1-1, shootout never counts', (reg['760609']['home'], reg['760609']['away'], reg['760609']['shootout']), (1, 1, True))
check('401854019 NWSL: 1-1 full time', (reg['401854019']['home'], reg['401854019']['away']), (1, 1))

# fail closed on anything the summary cannot establish
def mutate(eid, fn):
    d = copy.deepcopy(SUM[eid]); fn(d); return d
comp = lambda d: d['header']['competitions'][0]
check('a period that does not add up to the final refuses',
      bool(raises(lambda: soccer_result.regulation_score(mutate('760606', lambda d: comp(d)['competitors'][0]['linescores'][1].update(displayValue='2'))))), True)
check('a line score missing its extra-time periods refuses',
      bool(raises(lambda: soccer_result.regulation_score(mutate('760606', lambda d: [c.update(linescores=c['linescores'][:2]) for c in comp(d)['competitors']])))), True)
check('goal events that disagree with the line scores refuse',
      bool(raises(lambda: soccer_result.regulation_score(mutate('761439', lambda d: d['keyEvents'].pop())))), True)
check('a match that is not final refuses',
      bool(raises(lambda: soccer_result.regulation_score(mutate('761439', lambda d: comp(d)['status']['type'].update(completed=False, state='in'))))), True)
check('an unknown final state (abandoned) refuses',
      bool(raises(lambda: soccer_result.regulation_score(mutate('761439', lambda d: comp(d)['status']['type'].update(name='STATUS_ABANDONED'))))), True)
check('a non-numeric period refuses',
      bool(raises(lambda: soccer_result.regulation_score(mutate('761439', lambda d: comp(d)['competitors'][0]['linescores'][0].update(displayValue='-'))))), True)

# ---------- 2. record_final.score_result, by league ----------
rf = load('record_final_soccer', os.path.join(HERE, 'record_final.py'))
sr = rf.score_result
check('mls ml 1-1: home moneyline LOST', sr('ml', 'home', None, 1, 1, league='soccer/usa.1', regulation=reg['761439']), 'LOST')
check('mls ml 1-1: away moneyline LOST', sr('ml', 'away', None, 1, 1, league='soccer/usa.1', regulation=reg['761439']), 'LOST')
check('nwsl 760606 Gotham YES (1-1 at 90, 2-1 AET): LOST', sr('ml', 'away', None, 2, 1, league='soccer/usa.nwsl', regulation=reg['760606']), 'LOST')
check('nwsl 760606 Kansas City YES: LOST', sr('ml', 'home', None, 2, 1, league='soccer/usa.nwsl', regulation=reg['760606']), 'LOST')
check('Under 2.5 on 760606: WON on 2 regulation goals (3 with extra time)',
      sr('total', 'under', 2.5, 2, 1, league='soccer/usa.nwsl', regulation=reg['760606']), 'WON')
check('Over 2.5 on 760606: LOST', sr('total', 'over', 2.5, 2, 1, league='soccer/usa.nwsl', regulation=reg['760606']), 'LOST')
check('760609 Washington YES (won the shootout, 1-1): LOST', sr('ml', 'home', None, 1, 1, league='soccer/usa.nwsl', regulation=reg['760609']), 'LOST')
check('a soccer grade with no regulation score is no grade (None)', sr('ml', 'home', None, 1, 1, league='soccer/usa.1'), None)
check('nfl ml tie still grades PUSH', sr('ml', 'home', None, 20, 20, league='football/nfl'), 'PUSH')
check('no league given (older callers): unchanged tie = PUSH', sr('ml', 'home', None, 20, 20), 'PUSH')
check('soccer spread on regulation: Gotham +1.5 (home line -1.5) WON on 1-1', sr('spread', 'away', -1.5, 2, 1, league='soccer/usa.nwsl', regulation=reg['760606']), 'WON')

# ---------- 3. record_final's record write on 760606: grade from the regulation score ----------
def fake_get(url, *a, **k):
    for lg_eid in LEAGUE.items():
        if url == SUMMARY_URL.format(lg=lg_eid[1], eid=lg_eid[0]):
            return copy.deepcopy(SUM[lg_eid[0]])
    if url in CORE:
        return copy.deepcopy(CORE[url])
    raise OSError(f'offline fixture missing {url}')

CARD = {'date': '2025-11-09', 'date_label': 'Sunday, Nov 9', 'record': '0-0', 'units_pl': '+0.00u', 'picks': [
    {'name': 'Gotham ML', 'market_class': 'ml', 'side': 'away', 'odds': '-120', 'card_american': -120, 'units': '5u',
     'espn_league': 'soccer/usa.nwsl', 'game': {'away': 'Gotham FC', 'home': 'Kansas City Current', 'commence': '2025-11-09T17:30Z', 'eid': '760606'}},
    {'name': 'Under 2.5', 'market_class': 'total', 'side': 'under', 'line': 2.5, 'odds': '-110', 'card_american': -110, 'units': '5u',
     'espn_league': 'soccer/usa.nwsl', 'game': {'away': 'Gotham FC', 'home': 'Kansas City Current', 'commence': '2025-11-09T17:30Z', 'eid': '760606'}}]}

def req(pick, gid, result, delta, record_after, units_after, line=None):
    q = {'grade_id': gid, 'event_id': '760606', 'league': 'soccer/usa.nwsl', 'pick': pick['name'], 'side': pick['side'],
         'market_class': pick['market_class'], 'card_date': '2025-11-09', 'result': result, 'score': 'GFC 2 @ KC 1',
         'stake_units': '5u', 'locked_american': pick['odds'], 'delta_units_exact': float(delta),
         'record_after': record_after, 'units_after_exact': float(units_after)}
    if line is not None:
        q['line'] = line
    return q

def run_record_final(tmp, requests, summary=None):
    os.makedirs(os.path.join(tmp, 'manifests'), exist_ok=True)
    os.makedirs(os.path.join(tmp, 'slates'), exist_ok=True)
    json.dump(CARD, open(os.path.join(tmp, 'manifest.json'), 'w'))
    json.dump(CARD, open(os.path.join(tmp, 'manifests', 'manifest-soccer000001.json'), 'w'))
    json.dump({'days': []}, open(os.path.join(tmp, 'history.json'), 'w'))
    json.dump({'processed': [], 'at': None, 'record_after': '0-0', 'units_after_exact': '0'}, open(os.path.join(tmp, 'record_done.json'), 'w'))
    json.dump({'requests': requests}, open(os.path.join(tmp, 'record_request.json'), 'w'))
    rf.ROOT = tmp
    rf.REQ, rf.MAN, rf.HIST, rf.DONE = (os.path.join(tmp, f) for f in ('record_request.json', 'manifest.json', 'history.json', 'record_done.json'))
    rf.MANIFESTS = os.path.join(tmp, 'manifests')
    rf._get = summary or fake_get
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = rf.main()
    hist = json.load(open(rf.HIST))
    return code, err.getvalue(), [(p['name'], p['result'], p['score']) for d in hist['days'] for p in d['picks']]

gotham, under = CARD['picks']
win_under = Decimal(5) * 100 / 110
tmp = tempfile.mkdtemp(prefix='soccer_reg_')
try:
    code, err, rows = run_record_final(tmp, [req(gotham, '760606|ml|away', 'LOST', -5, '0-1', -5),
                                             req(under, '760606|total|under|2.5', 'WON', win_under, '1-1', Decimal(-5) + win_under, line=2.5)])
    check('record_final: Gotham ML LOST and Under 2.5 WON on 760606 are written (exit 0)', (code, err.strip()), (0, ''))
    check('the rows show ESPN\'s final and the 90-minute score the grade used', rows,
          [('Gotham ML', 'L', 'GFC 2, KC 1 (90 min: GFC 1, KC 1)'), ('Under 2.5', 'W', 'GFC 2, KC 1 (90 min: GFC 1, KC 1)')])
    tmp2 = tempfile.mkdtemp(prefix='soccer_reg_')
    try:
        code, err, rows = run_record_final(tmp2, [req(gotham, '760606|ml|away', 'WON', Decimal(500) / 120, '1-0', Decimal(500) / 120)])
        check('a Gotham ML labeled WON on the extra-time final is refused (exit 3, nothing written)',
              (code, 'contradicts the verified final' in err, rows), (3, True, []))
    finally:
        shutil.rmtree(tmp2, ignore_errors=True)
    tmp3 = tempfile.mkdtemp(prefix='soccer_reg_')
    try:
        def no_summary(url, *a, **k):
            if 'summary' in url:
                raise OSError('summary down')
            return fake_get(url)
        code, err, rows = run_record_final(tmp3, [req(gotham, '760606|ml|away', 'LOST', -5, '0-1', -5)], summary=no_summary)
        check('no summary, no regulation score: refused (exit 3, nothing written)', (code, 'regulation' in err, rows), (3, True, []))
    finally:
        shutil.rmtree(tmp3, ignore_errors=True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ---------- 4. finals_watch grades the same way ----------
fw = load('finals_watch_soccer', os.path.join(HERE, 'finals_watch.py'))
def fw_pick(eid, side, mc='ml', line=None):
    p = {'name': 'x', 'espn_league': LEAGUE[eid], 'market_class': mc, 'side': side, 'odds': '-120', 'card_american': -120,
         'units': '5u', 'kalshi': {'cents': 55}, 'game': {'eid': eid}}
    if line is not None:
        p['line'] = line
    return p
def primary(eid):
    r = reg[eid]
    return {'home_score': r['final_home'], 'away_score': r['final_away']}
for eid in SUM:
    fw._PROP_BOX[(LEAGUE[eid], eid)] = copy.deepcopy(SUM[eid])
check('finals_watch: mls ml 1-1 home is L', fw.result_of(fw_pick('761439', 'home'), primary('761439')), 'L')
check('finals_watch: mls ml 1-1 away is L', fw.result_of(fw_pick('761439', 'away'), primary('761439')), 'L')
check('finals_watch: nwsl 760606 Gotham YES is L (1-1 at 90)', fw.result_of(fw_pick('760606', 'away'), primary('760606')), 'L')
check('finals_watch: Under 2.5 on 760606 is W', fw.result_of(fw_pick('760606', 'under', 'total', 2.5), primary('760606')), 'W')
check('finals_watch: 760609 Washington YES is L (shootout win)', fw.result_of(fw_pick('760609', 'home'), primary('760609')), 'L')
check('finals_watch: nfl ml tie still PUSH',
      fw.result_of({'espn_league': 'football/nfl', 'market_class': 'ml', 'side': 'home', 'game': {'eid': '1'}}, {'home_score': 20, 'away_score': 20}), 'PUSH')
fw.fill_leak.card_price = lambda p, **kw: (55, {'card_american': -120}, 1)
fw.fill_leak.fill_divergence = lambda p, **kw: []
g = fw.grade(fw_pick('760606', 'away'), primary('760606'))
check('finals_watch.grade: Gotham ML on 760606 loses the stake', (g[0], fw.units.pnl_to_units(g[1])), ('L', Decimal(-5)))
check('finals_watch: summary final that differs from the verified final refuses',
      'REFUSING' in (raises(lambda: fw.result_of(fw_pick('760606', 'away'), {'home_score': 1, 'away_score': 1})) or ''), True)
fw._PROP_BOX.pop(('soccer/usa.nwsl', '760606'))
fw._get = lambda url, *a, **k: (_ for _ in ()).throw(OSError('offline'))
check('finals_watch: no summary refuses (ValueError, chain stops)',
      'summary unavailable' in (raises(lambda: fw.result_of(fw_pick('760606', 'away'), primary('760606'))) or ''), True)
check('finals_watch: a soccer class with no rule refuses',
      bool(raises(lambda: fw.result_of(fw_pick('761439', 'home', 'btts'), primary('761439')))), True)

# ---------- 5. predictions: a drawn match settles a miss ----------
pr = load('predictions_soccer', os.path.join(HERE, 'predictions.py'))
BOARD = fx('scoreboard_nwsl_20261004.json')
def fake_board(url, timeout=30):
    if 'soccer/usa.nwsl/scoreboard?dates=' in url:
        return copy.deepcopy(BOARD) if 'dates=20261004' in url else {'events': []}
    raise OSError(f'offline fixture missing {url}')
pr.get_json = fake_board
pr.now = lambda: datetime(2026, 10, 5, 3, 0, tzinfo=timezone.utc)  # 10 hours after kickoff, inside the 36h clock
row = {'id': '376035ba06', 'event_id': '401854019', 'league': 'NWSL', 'path': 'soccer/usa.nwsl', 'home': 'Gotham FC',
       'away': 'Angel City FC', 'pick_team': 'Angel City FC', 'prediction': 'Angel City FC to beat Gotham FC',
       'kickoff_utc': '2026-10-04T17:00:00+00:00', 'status': 'pending', 'created_at': '2026-10-04T10:50:11.531642+00:00'}
other = {'id': 'fixture-den', 'event_id': '401854090', 'league': 'NWSL', 'path': 'soccer/usa.nwsl', 'home': 'Chicago Stars FC',
         'away': 'Denver Summit FC', 'pick_team': 'Chicago Stars FC', 'prediction': 'Chicago Stars FC to beat Denver Summit FC',
         'kickoff_utc': '2026-10-04T20:00:00+00:00', 'status': 'pending'}
led = [dict(row), dict(other)]
n = pr.settle(led)
check('prediction 401854019 (Angel City to beat Gotham, 1-1) settles: miss', (led[0]['status'], bool(led[0].get('settled_at'))), ('miss', True))
check('a soccer prediction with a winner still settles by the winner flag (miss)', led[1]['status'], 'miss')
check('both settled this pass', n, 2)
live = copy.deepcopy(BOARD)
live['events'][0]['competitions'][0]['status']['type'].update(state='in', completed=False, name='STATUS_SECOND_HALF')
pr.get_json = lambda url, timeout=30: copy.deepcopy(live) if 'dates=20261004' in url else {'events': []}
led = [dict(row)]
pr.settle(led)
check('a level match still in play stays pending', led[0]['status'], 'pending')

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
