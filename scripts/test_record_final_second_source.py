#!/usr/bin/env python3
"""record_final.py step 2b - the cross-company second source (hardening H-04, C-0b.3; J-115).
record_final said it applied "two-source attestation" but read only ESPN, and copied the request's own claimed
source onto the public API mirror. Now, before anything is written:
 - a team final must be confirmed by one of the grader's own cross-company readers (scripts/second_source.py:
   same teams, same ORDERED scores, two_source_ok), never ESPN's own site API;
 - a fight's winner must be confirmed by the settlement of the card pick's own Kalshi market;
 - missing, disagreeing or same-company: exit 3, nothing written, the chain stops;
 - the API mirror's `source` names the sources this run read, never the request's claim.
Offline: ESPN, the second sources and Kalshi are all served from the fixtures below.
Run: python3 scripts/test_record_final_second_source.py"""
import contextlib, copy, importlib.util, io, json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
failures = 0


def check(name, actual, expected):
    global failures
    ok = actual == expected
    print(('OK  ' if ok else 'FAIL'), name, '' if ok else f'(got {actual!r}, want {expected!r})')
    if not ok:
        failures += 1


CORE = 'https://sports.core.api.espn.com/v2/sports/{lg}/events/{e}/competitions/{c}'
KAL = 'https://api.elections.kalshi.com/trade-api/v2/markets/{}'
DOE_TICK = 'KXUFCFIGHT-26OCT24DOEROE-DOE'
FIX = {
    CORE.format(lg='hockey/leagues/nhl', e='401891817', c='401891817'): {
        'status': {'type': {'completed': True, 'name': 'STATUS_FINAL'}},
        'competitors': [{'homeAway': 'home', 'team': {'displayName': 'New Jersey Devils', 'abbreviation': 'NJ'},
                         'score': {'value': 3.0}},
                        {'homeAway': 'away', 'team': {'displayName': 'Philadelphia Flyers', 'abbreviation': 'PHI'},
                         'score': {'value': 2.0}}]},
    CORE.format(lg='mma/leagues/ufc', e='600070001', c='401900001'): {
        'status': {'type': {'completed': True}},
        'competitors': [{'athlete': {'displayName': 'Rick Roe'}, 'winner': False},
                        {'athlete': {'displayName': 'Jon Doe'}, 'winner': True}]},
}
U0 = 4.761952343474163
OCT1 = {'date': '2026-10-01', 'record': '21-11', 'units_pl': '+4.76u', 'picks': [
    {'name': 'Devils ML', 'market_class': 'ml', 'side': 'home', 'odds': '-162', 'card_american': -162, 'units': '5u',
     'espn_league': 'hockey/nhl', 'game': {'away': 'Philadelphia Flyers', 'home': 'New Jersey Devils',
                                           'commence': '2026-10-01T23:00Z', 'eid': '401891817'}}]}
OCT24 = {'date': '2026-10-24', 'record': '21-11', 'units_pl': '+4.76u', 'picks': [
    {'name': 'Jon Doe ML', 'market_class': 'ml', 'side': 'home', 'odds': '+150', 'card_american': 150, 'units': '5u',
     'espn_league': 'mma/ufc', 'kalshi': {'ticker': DOE_TICK, 'side': 'yes'},
     'game': {'away': 'Rick Roe', 'home': 'Jon Doe', 'commence': '2026-10-25T02:00Z', 'eid': '600070001'}}]}
LIVE = {'date': '2026-10-25', 'record': '21-11', 'units_pl': '+4.76u', 'picks': []}
HIST = {'days': []}
DONE = {'processed': [], 'at': None}
D_DEV = 5 * 100 / 162


def devils(**x):
    r = {'grade_id': '401891817|ml|home', 'event_id': '401891817', 'league': 'hockey/nhl', 'pick': 'Devils ML',
         'side': 'home', 'result': 'WON', 'score': 'PHI 2 @ NJ 3', 'stake_units': '5u', 'locked_american': '-162',
         'delta_units_exact': D_DEV, 'record_after': '22-11', 'units_after_exact': U0 + D_DEV,
         'two_source': ['espn_core completed', 'CLAIMED by the request'], 'source': 'CLAIMED by the request'}
    r.update(x)
    return r


def doe(**x):
    r = {'grade_id': 'G-600070001', 'event_id': '600070001', 'league': 'mma/ufc', 'pick': 'Jon Doe ML', 'side': 'home',
         'result': 'WON', 'score': 'DOE 1 @ ROE 0', 'stake_units': '5u', 'locked_american': '+150',
         'delta_units_exact': 7.5, 'record_after': '22-11', 'units_after_exact': U0 + 7.5,
         'competition_id': '401900001', 'graded_pick': 'Doe def. Roe', 'source': 'CLAIMED by the request'}
    r.update(x)
    return r


def load():
    spec = importlib.util.spec_from_file_location('record_final_second_source', os.path.join(HERE, 'record_final.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run(reqs, second=None, kalshi=None, snap=OCT1):
    """Run record_final on reqs. `second` is what the grader's cross-company reader returns for the final (None:
    nothing found); `kalshi` is the market read for the fight's own ticker (None: not served)."""
    tmp = tempfile.mkdtemp(prefix='rf_second_')
    try:
        os.makedirs(os.path.join(tmp, 'manifests')); os.makedirs(os.path.join(tmp, 'slates'))
        for rel, obj in {'manifest.json': LIVE, 'history.json': HIST, 'record_done.json': DONE,
                         'record_request.json': {'requests': reqs}, 'manifests/manifest-aaaaaaaaaaaa.json': snap}.items():
            json.dump(obj, open(os.path.join(tmp, rel), 'w'), indent=2)
        rf = load()
        rf.ROOT = tmp
        rf.REQ, rf.MAN, rf.HIST, rf.DONE = (os.path.join(tmp, f) for f in
                                            ('record_request.json', 'manifest.json', 'history.json', 'record_done.json'))
        rf.MANIFESTS = os.path.join(tmp, 'manifests')
        fix = dict(FIX)
        if kalshi is not None:
            fix[KAL.format(DOE_TICK)] = {'market': kalshi}

        def fake_get(url, *a, **k):
            if url not in fix:
                raise OSError(f'offline fixture missing {url}')
            return copy.deepcopy(fix[url])
        rf._get = fake_get
        FW = rf._second_source()
        FW.second_source = lambda pick, primary, commence: (dict(second, away_id=primary['away'], home_id=primary['home'])
                                                            if second else None)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = rf.main()
            except Exception as e:
                code = f'raised {type(e).__name__}: {e}'
        st = {f: json.load(open(os.path.join(tmp, f))) for f in ('manifest.json', 'history.json')}
        mp = os.path.join(tmp, 'slates', 'api_record.json')
        st['mirror'] = json.load(open(mp)) if os.path.exists(mp) else None
        return code, st, err.getvalue()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def refused(name, why, *a, **k):
    code, st, err = run(*a, **k)
    check(f'{name}: refused (exit 3)', code, 3)
    check(f'{name}: the reason is named ({why})', why in err, True)
    check(f'{name}: nothing written', (st['manifest.json']['record'], st['history.json'], st['mirror']), ('21-11', HIST, None))


CBS = {'source': 'cbs scoreboard (independent; final, 20261001)', 'away_score': 2, 'home_score': 3}
# H-04 team finals ---------------------------------------------------------------------------------------------
refused('test_h04 a team final no cross-company source confirms', 'no cross-company second source', [devils()], second=None)
refused('test_h04 a second source that disagrees on the score', 'no cross-company second source',
        [devils()], second=dict(CBS, away_score=3, home_score=2))
refused('test_h04 ESPN\'s own site API is never the second source', 'same company',
        [devils()], second={'source': 'espn_site (SAME COMPANY as primary - weaker independence)', 'away_score': 2, 'home_score': 3})
code, st, err = run([devils()], second=CBS)
check('test_h04 a team final confirmed by CBS lands', (code, st['manifest.json']['record']), (0, '22-11'))
check('test_h04 the API mirror names the sources this run read, not the request\'s claim',
      (st['mirror'] or {}).get('source'), 'record_final: espn_core completed + cbs scoreboard (independent; final, 20261001)')

# C-0b.3 fights ------------------------------------------------------------------------------------------------
SETTLED = {'ticker': DOE_TICK, 'status': 'finalized', 'result': 'yes'}
refused('test_c0b3 a fight whose Kalshi market cannot be read', 'could not be read', [doe()], snap=OCT24, kalshi=None)
refused('test_c0b3 a fight whose Kalshi market has not settled', 'has not settled',
        [doe()], snap=OCT24, kalshi={'ticker': DOE_TICK, 'status': 'active', 'result': ''})
refused('test_c0b3 a fight whose Kalshi settlement disagrees with ESPN\'s winner', 'disagrees',
        [doe()], snap=OCT24, kalshi=dict(SETTLED, result='no'))
nok = copy.deepcopy(OCT24); del nok['picks'][0]['kalshi']
refused('test_c0b3 a fight card pick with no Kalshi market to read', 'names no Kalshi market', [doe()], snap=nok, kalshi=SETTLED)
code, st, err = run([doe()], snap=OCT24, kalshi=SETTLED)
check('test_c0b3 a fight confirmed by its own Kalshi settlement lands', (code, st['manifest.json']['record'], err.strip()),
      (0, '22-11', ''))
check('test_c0b3 the mirror names ESPN\'s winner flags and the Kalshi settlement', (st['mirror'] or {}).get('source'),
      f'record_final: espn_core winner flags + kalshi settlement (independent; {DOE_TICK} settled yes)')

src = open(os.path.join(HERE, 'record_final.py')).read()
check('test_h04 the docstring no longer claims an attestation it did not read', 'two-source attestation' in src, False)

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
