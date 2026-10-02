#!/usr/bin/env python3
"""Fail-closed record write fixture (sweep CP-05, CP-07, CP-16, M1, DI-06, DI-11): record_final.py
must REFUSE (exit 3, nothing written) a grade whose result contradicts the verified final, whose
unit delta does not follow from the card price and stake, whose units chain does not continue,
whose pick was never on a published card, or that repeats a pick already on its day's row. It
files each grade under its card's date (the builder's _card_date_of, not the date the live manifest
carries when the grade lands, and not a late game's own date), and labels totals and props from the game, not from the over/under side.
Offline: every ESPN read is served from the fixtures below.
Bite-proof: red on the pre-fix record_final.py (any well-formed request that chained W-L landed).
Run: python3 scripts/test_record_final_verify.py"""
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
SITE = 'https://site.api.espn.com/apis/site/v2/sports/{lg}/summary?event={e}'

def core(away, a_sc, home, h_sc):
    return {'status': {'type': {'completed': True, 'name': 'STATUS_FINAL'}},
            'competitors': [{'homeAway': 'home', 'team': {'displayName': home}, 'score': {'value': float(h_sc)}},
                            {'homeAway': 'away', 'team': {'displayName': away}, 'score': {'value': float(a_sc)}}]}

FIX = {
    CORE.format(lg='hockey/leagues/nhl', e='401891817', c='401891817'): core('Philadelphia Flyers', 2, 'New Jersey Devils', 3),
    CORE.format(lg='hockey/leagues/nhl', e='401891828', c='401891828'): core('Chicago Blackhawks', 0, 'Utah Mammoth', 6),
    CORE.format(lg='football/leagues/nfl', e='401872964', c='401872964'): core('Pittsburgh Steelers', 24, 'Cleveland Browns', 27),
    CORE.format(lg='basketball/leagues/wnba', e='401918022', c='401918022'): core('Indiana Fever', 83, 'Las Vegas Aces', 94),
    CORE.format(lg='baseball/leagues/mlb', e='401907896', c='401907896'): core('Chicago White Sox', 6, 'Houston Astros', 3),
    CORE.format(lg='hockey/leagues/nhl', e='401891900', c='401891900'): core('Vancouver Canucks', 1, 'Seattle Kraken', 4),
    CORE.format(lg='baseball/leagues/mlb', e='401907897', c='401907897'): core('Chicago White Sox', 7, 'Houston Astros', 3),
    CORE.format(lg='mma/leagues/ufc', e='600060739', c='401891663'): {
        'status': {'type': {'completed': True}},
        'competitors': [{'athlete': {'displayName': 'Loai Abushaar'}, 'winner': False},
                        {'athlete': {'displayName': 'George Staines'}, 'winner': True}]},
    # box score: Alvarez (Astros, HOME) 1 hit; a White Sox pitcher's 'hits' (allowed) must not be read
    SITE.format(lg='baseball/mlb', e='401907896'): {
        'header': {'competitions': [{'competitors': [{'homeAway': 'home', 'team': {'id': '18'}},
                                                     {'homeAway': 'away', 'team': {'id': '4'}}]}]},
        'boxscore': {'players': [
            {'team': {'id': '4', 'displayName': 'Chicago White Sox'}, 'statistics': [
                {'keys': ['fullInnings.partInnings', 'hits', 'runs', 'earnedRuns'],
                 'athletes': [{'athlete': {'id': '9', 'displayName': 'Some Pitcher'}, 'stats': ['6.0', '4', '3', '3']}]}]},
            {'team': {'id': '18', 'displayName': 'Houston Astros'}, 'statistics': [
                {'keys': ['hits-atBats', 'atBats', 'runs', 'hits'],
                 'athletes': [{'athlete': {'id': '33', 'displayName': 'Yordan Alvarez'}, 'stats': ['1-4', '4', '0', '1']}]}]}]}},
}
FIX[SITE.format(lg='baseball/mlb', e='401907897')] = FIX[SITE.format(lg='baseball/mlb', e='401907896')]

def fake_get(url, *a, **k):
    if url not in FIX:
        raise OSError(f'offline fixture missing {url}')
    return copy.deepcopy(FIX[url])

def pick(name, eid, league, away, home, commence, odds, units, side, mc='ml', **extra):
    p = {'name': name, 'market_class': mc, 'side': side, 'odds': odds, 'card_american': int(odds),
         'units': units, 'espn_league': league,
         'game': {'away': away, 'home': home, 'commence': commence, 'eid': eid}}
    p.update(extra)
    return p

OCT1 = {'date': '2026-10-01', 'record': '21-11', 'units_pl': '+4.76u', 'picks': [
    pick('Devils ML', '401891817', 'hockey/nhl', 'Philadelphia Flyers', 'New Jersey Devils', '2026-10-01T23:00Z', '-162', '5u', 'home'),
    pick('Under 38.5', '401872964', 'football/nfl', 'Pittsburgh Steelers', 'Cleveland Browns', '2026-10-02T00:15Z', '-115', '6u', 'under', 'total', line=38.5),
    pick('Aces -11', '401918022', 'basketball/wnba', 'Indiana Fever', 'Las Vegas Aces', '2026-10-02T02:00Z', '-110', '5u', 'home', 'spread', line=-11),
    # published on the Oct 1 card, puck drop 12:05 AM PT Oct 2: the card's date is the builder's
    # _card_date_of (the most common PT game date across the card), not this pick's own date
    pick('Kraken ML', '401891900', 'hockey/nhl', 'Vancouver Canucks', 'Seattle Kraken', '2026-10-02T07:05Z', '-140', '5u', 'home')]}
SEP29 = {'date': '2026-09-29', 'record': '19-8', 'units_pl': '+10.05u', 'picks': [
    pick('Yordan Alvarez over 1.5 hits', '401907896', 'baseball/mlb', 'Chicago White Sox', 'Houston Astros', '2026-09-29T21:00Z',
         '+270', '5u', 'over', 'prop', line=1.5, player='Yordan Alvarez', market='bat_hits'),
    {'name': 'Loai Abushaar ML', 'market_class': 'ml', 'side': 'home', 'odds': '+285', 'card_american': 285, 'units': '5u',
     'espn_league': 'mma/ufc', 'game': {'away': 'George Staines', 'home': 'Loai Abushaar', 'commence': '2026-09-29T23:00Z', 'eid': None}}]}
# manifest-388bdcec23a0 shape: an archive copy dated Sep 30 carrying Sep 29's picks, one of them
# re-bound to the Sep 30 game (eid 401907897). Its picks say Sep 29, its date says Sep 30: it is no
# card, so nothing on it is graded - even a row whose price agrees with itself.
CORRUPT930 = {'date': '2026-09-30', 'record': '19-8', 'units_pl': '+10.05u', 'picks': [
    pick('Braves ML', '401907965', 'baseball/mlb', 'Philadelphia Phillies', 'Atlanta Braves', '2026-09-29T23:15Z', '-125', '5u', 'home'),
    SEP29['picks'][1],
    pick('Yordan Alvarez over 1.5 hits', '401907897', 'baseball/mlb', 'Chicago White Sox', 'Houston Astros', '2026-09-30T23:10Z',
         '+270', '5u', 'over', 'prop', line=1.5, player='Yordan Alvarez', market='bat_hits')]}
# the next morning's card already replaced manifest.json when the Oct 1 grades land
LIVE = {'date': '2026-10-02', 'record': '21-11', 'units_pl': '+4.76u', 'picks': []}
HIST = {'days': [{'date': '2026-09-30', 'label': 'Wednesday, Sep 30', 'record': '1-0', 'units': '+6.90u', 'brief': '',
                  'picks': [{'name': 'White Sox ML', 'game': 'at Astros', 'odds': '+138', 'units': '5u', 'result': 'W',
                             'score': 'CHW 7, HOU 3', '_delta': '6.9'}]}]}
DONE = {'processed': ['401907897|ml|away'], 'at': '2026-10-01T00:32:08+00:00'}
U0 = 4.761952343474163  # exact running units behind the shown +4.76u

def req(gid, eid, league, pick_, side, result, score, odds, stake, delta, rec, units_after, **extra):
    r = {'grade_id': gid, 'event_id': eid, 'league': league, 'pick': pick_, 'side': side, 'result': result,
         'score': score, 'stake_units': stake, 'locked_american': odds, 'delta_units_exact': delta,
         'record_after': rec, 'units_after_exact': units_after}
    r.update(extra)
    return r

D_DEV = 5 * 100 / 162          # Devils ML -162, 5u
D_UNDER_W = 6 * 100 / 115      # Under 38.5 -115, 6u
def devils(result='WON', delta=D_DEV, rec='22-11', ua=U0 + D_DEV, **x):
    return req('401891817|ml|home', '401891817', 'hockey/nhl', 'Devils ML', 'home', result, 'PHI 2 @ NJ 3', '-162', '5u', delta, rec, ua, **x)
def under(result='LOST', delta=-6.0, rec='21-12', ua=U0 - 6, **x):
    return req('401872964|total|under|38.5', '401872964', 'football/nfl', 'Under 38.5', 'under', result, 'PIT 24 @ CLE 27', '-115', '6u', delta, rec, ua, **x)
def aces(result='PUSH', delta=0.0, rec='21-11', ua=U0):
    return req('401918022|spread|home|-11', '401918022', 'basketball/wnba', 'Aces -11', 'home', result, 'IND 83 @ LV 94', '-110', '5u', delta, rec, ua)
def yordan(result='LOST', delta=-5.0, rec='21-12', ua=U0 - 5):
    return req('401907896|prop|yordanalvarez|bat_hits|over|1.5', '401907896', 'baseball/mlb', 'Yordan Alvarez over 1.5 hits',
               'over', result, 'CHW 6 @ HOU 3', '+270', '5u', delta, rec, ua)

def load():
    spec = importlib.util.spec_from_file_location('record_final_under_test', os.path.join(HERE, 'record_final.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def run(reqs, hist=HIST, done=DONE, live=LIVE, payload=None, snaps=None):
    tmp = tempfile.mkdtemp(prefix='rf_verify_')
    try:
        os.makedirs(os.path.join(tmp, 'manifests'))
        os.makedirs(os.path.join(tmp, 'slates'))
        files = {'manifest.json': live, 'history.json': hist, 'record_done.json': done,
                 'record_request.json': payload if payload is not None else {'requests': reqs},
                 'manifests/manifest-0c7101aaaaaa.json': OCT1, 'manifests/manifest-0929bbbbbbbb.json': SEP29}
        files.update(snaps or {})
        for rel, obj in files.items():
            json.dump(obj, open(os.path.join(tmp, rel), 'w'), indent=2)
        rf = load()
        rf.ROOT = tmp
        rf.REQ, rf.MAN, rf.HIST, rf.DONE = (os.path.join(tmp, f) for f in
                                            ('record_request.json', 'manifest.json', 'history.json', 'record_done.json'))
        rf.MANIFESTS = os.path.join(tmp, 'manifests')
        rf._get = fake_get
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = rf.main()
            except Exception as e:  # a crash is not a refusal
                code = f'raised {type(e).__name__}'
        state = {f: json.load(open(os.path.join(tmp, f))) for f in ('manifest.json', 'history.json', 'record_done.json', 'record_request.json')}
        mirror = os.path.join(tmp, 'slates', 'api_record.json')
        state['slates/api_record.json'] = json.load(open(mirror)) if os.path.exists(mirror) else None
        return code, state, err.getvalue()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def sig(man, hist):
    return man.get('record'), man.get('units_pl'), [(d['date'], len(d['picks'])) for d in hist['days']]

def refused(name, reqs, why, **kw):
    code, st, err = run(reqs, **kw)
    check(f'{name}: refused (exit 3)', code, 3)
    check(f'{name}: refused for the right reason ({why})', why in err, True)
    check(f'{name}: nothing written (record, units, day rows)', sig(st['manifest.json'], st['history.json']),
          sig(kw.get('live', LIVE), kw.get('hist', HIST)))
    check(f'{name}: history.json byte-for-byte untouched', st['history.json'] == kw.get('hist', HIST), True)
    return err

def day(st, date):
    return next((d for d in st['history.json']['days'] if d['date'] == date), None)

# CP-05: the result must follow from the verified final, side and line
refused('CP-05 Devils ML LOST on a Devils 3-2 win', [devils('LOST', -5.0, '21-12', U0 - 5)], 'contradicts the verified final')
refused('CP-05 Under 38.5 WON on a 51-point final', [under('WON', D_UNDER_W, '22-11', U0 + D_UNDER_W)], 'contradicts the verified final')
refused('CP-05 Aces -11 WON on an 11-point margin (a push)', [aces('WON', 5 * 100 / 110, '22-11', U0 + 5 * 100 / 110)],
        'contradicts the verified final')
code, st, _ = run([aces()])
check('CP-05 Aces -11 PUSH on an 11-point margin lands', code, 0)
check('CP-05 push row stored as P with 0 delta', [(p['name'], p['result'], p['_delta']) for p in (day(st, '2026-10-01') or {}).get('picks', [])],
      [('Aces -11', 'P', '0.0')])
refused('CP-05 prop WON when the box score shows 1 hit on over 1.5', [yordan('WON', 13.5, '22-11', U0 + 13.5)],
        'contradicts the verified final')

# M1: delta must follow from card price + stake; units_after must continue the running units
refused('M1 delta -7.5 on a WON at -162 for 5u', [devils(delta=-7.5, ua=U0 - 7.5)], 'does not follow from')
refused('M1 units_after_exact 50.00 off the chain', [devils(ua=50.0)], 'units chain broken')
refused('M1 locked price differs from the card', [dict(devils(), locked_american='+150')], 'price/stake')

# CP-07: only published picks are graded; each grade lands on its own card date, in date order
refused('CP-07 pick on no published card (Mammoth ML)',
        [req('401891828|ml|home', '401891828', 'hockey/nhl', 'Mammoth ML', 'home', 'WON', 'CHI 0 @ UTA 6', '-218', '5u',
             500 / 218, '22-11', U0 + 500 / 218)], 'not on any published card')
refused('CP-07 card_date that is not the pick\'s card', [devils(card_date='2026-10-02')], 'not on any published card dated 2026-10-02')
code, st, err = run([devils()])
check('CP-07 Oct 1 grade landing after the Oct 2 card: exit 0', code, 0)
check('CP-07 filed under 2026-10-01, not the live manifest date', [d['date'] for d in st['history.json']['days']],
      ['2026-09-30', '2026-10-01'])
check('CP-07 day row label is the card date', (day(st, '2026-10-01') or {}).get('label'), 'Thursday, Oct 1')
check('CP-07 manifest record + units move', (st['manifest.json']['record'], st['manifest.json']['units_pl']), ('22-11', '+7.85u'))

# F1: a pick published on the Oct 1 card whose game starts after midnight PT belongs to the Oct 1 card
D_KRAKEN = 5 * 100 / 140
def kraken(**x):
    return req('401891900|ml|home', '401891900', 'hockey/nhl', 'Kraken ML', 'home', 'WON', 'VAN 1 @ SEA 4', '-140', '5u',
               D_KRAKEN, '22-11', U0 + D_KRAKEN, **x)
code, st, err = run([kraken()])
check('F1 after-midnight pick on the Oct 1 card lands', (code, err.strip()), (0, ''))
check('F1 filed under the card date 2026-10-01, not its own game date', [d['date'] for d in st['history.json']['days']],
      ['2026-09-30', '2026-10-01'])
check('F1 row on the Oct 1 day', [(p['name'], p['result']) for p in (day(st, '2026-10-01') or {}).get('picks', [])], [('Kraken ML', 'W')])
code, st, _ = run([kraken(card_date='2026-10-01', market_class='ml', line=None)])
check('F1 request carrying the card date 2026-10-01 lands', code, 0)
refused('F1 request dating it by its own game day (2026-10-02)', [kraken(card_date='2026-10-02')],
        'not on any published card dated 2026-10-02')
# the corrupted Sep 30 archive copy stays refused, by membership (its price agrees with itself here)
refused('F1 row of the corrupted Sep 30 archive copy', [req('401907897|prop|yordanalvarez|bat_hits|over|1.5', '401907897', 'baseball/mlb',
        'Yordan Alvarez over 1.5 hits', 'over', 'LOST', 'CHW 7 @ HOU 3', '+270', '5u', -5.0, '21-12', U0 - 5)],
        'not on any published card', snaps={'manifests/manifest-388bdcec23a0.json': CORRUPT930})
code, st, _ = run([yordan()], snaps={'manifests/manifest-388bdcec23a0.json': CORRUPT930})
check('F1 the real Sep 29 card still grades its own pick beside the corrupted copy', (code, [d['date'] for d in st['history.json']['days']]),
      (0, ['2026-09-29', '2026-09-30']))

# F1 review (Oct 2): a game that began BEFORE the card's date is not on that card, even when the
# card's own picks carry its date - a pick copied onto the Oct 2 card after its Oct 1 game started
# is never graded and filed under Oct 2 (the record is append-only; a wrong-date row stays wrong)
FIX[CORE.format(lg='hockey/leagues/nhl', e='401891950', c='401891950')] = core('New York Islanders', 1, 'New Jersey Devils', 4)
OCT2 = {'date': '2026-10-02', 'record': '21-11', 'units_pl': '+4.76u', 'picks': [
    pick('Rangers ML', '401891960', 'hockey/nhl', 'Boston Bruins', 'New York Rangers', '2026-10-02T23:00Z', '-130', '5u', 'home'),
    pick('Kings ML', '401891961', 'hockey/nhl', 'Anaheim Ducks', 'Los Angeles Kings', '2026-10-03T02:00Z', '-150', '5u', 'home'),
    pick('Devils ML', '401891950', 'hockey/nhl', 'New York Islanders', 'New Jersey Devils', '2026-10-01T23:00Z', '-162', '5u', 'home')]}
def stale_devils(**x):
    return req('401891950|ml|home', '401891950', 'hockey/nhl', 'Devils ML', 'home', 'WON', 'NYI 1 @ NJ 4', '-162', '5u',
               D_DEV, '22-11', U0 + D_DEV, **x)
refused('F1 a pick whose game began the day before its card is not on that card', [stale_devils()],
        'not on any published card', snaps={'manifests/manifest-1002cccccccc.json': OCT2})
refused('F1 the same stale pick requested under the card date', [stale_devils(card_date='2026-10-02')],
        'not on any published card dated 2026-10-02', snaps={'manifests/manifest-1002cccccccc.json': OCT2})
refused('F1 the same stale pick on the live manifest', [stale_devils(card_date='2026-10-02')],
        'not on any published card dated 2026-10-02', live=dict(LIVE, picks=OCT2['picks']))

code, st, _ = run([devils(market_class='ml', line=None, card_date='2026-10-01'),
                   under(rec='22-12', ua=U0 + D_DEV - 6, market_class='total', line=38.5, card_date='2026-10-01')])
check('CP-07 requests carrying market_class/line/card_date that match the card land', code, 0)
refused('CP-05 request line differing from the card line', [under(market_class='total', line=40.5)], 'disagrees with the')

# CP-16: a total records the matchup, not 'at <home>'
code, st, _ = run([under()])
check('CP-16 Under 38.5 LOST lands', code, 0)
check('CP-16 total game label is the matchup', [(p['name'], p['game']) for p in (day(st, '2026-10-01') or {}).get('picks', [])],
      [('Under 38.5', 'Steelers at Browns')])

# DI-11 / M3: a prop's context is the player's team (Alvarez is an Astro, home) and it files on its own card
code, st, _ = run([yordan()])
check('DI-11 prop LOST lands', code, 0)
check('DI-11 prop row filed under its Sep 29 card, inserted in date order', [d['date'] for d in st['history.json']['days']],
      ['2026-09-29', '2026-09-30'])
check('DI-11 prop game label from the player team', [(p['name'], p['game'], p['result']) for p in (day(st, '2026-09-29') or {}).get('picks', [])],
      [('Yordan Alvarez over 1.5 hits', 'vs White Sox', 'L')])

# exact chain across a batch, and the exact anchor carried to the next run
code, st, _ = run([devils(), under(rec='22-12', ua=U0 + D_DEV - 6)])
check('chain: two grades in one batch land', code, 0)
check('chain: exact units anchor kept for the next run', (st['record_done.json'].get('record_after'),
      st['record_done.json'].get('units_after_exact')), ('22-12', str(U0 + D_DEV - 6)))
nxt_live = dict(LIVE, record='22-12', units_pl=st['manifest.json']['units_pl'])
refused('chain: next run 0.004u off the exact anchor', [aces(rec='22-12', ua=U0 + D_DEV - 6 + 0.004)], 'units chain broken',
        live=nxt_live, done=st['record_done.json'])
code, _, _ = run([aces(rec='22-12', ua=U0 + D_DEV - 6)], live=nxt_live, done=st['record_done.json'])
check('chain: next run on the exact anchor lands', code, 0)

# displayed units round half-up (the owner's rule in core/units; record_today.js shows 3.125 as +3.13u),
# and a total in (-0.005, 0] prints '+0.00u' - '+-0.00u' was written to manifest units_pl and every
# later grade then refused it as unparsable (exit 3) until a manual fix
_rf = load()
from decimal import Decimal as _D
check('units display: half-up and a signed zero', [_rf.fmt_units(_D(v)) for v in
      ('3.125', '-3.125', '0.005', '-0.005', '-0.0049999', '-0.004', '-0.001', '-0', '0', '0.004', '2.124999')],
      ['+3.13u', '-3.13u', '+0.01u', '-0.01u', '+0.00u', '+0.00u', '+0.00u', '+0.00u', '+0.00u', '+0.00u', '+2.12u'])
LIVE_6 = dict(LIVE, record='21-11', units_pl='+6.00u')
DONE_6 = dict(DONE, record_after='21-11', units_after_exact='5.997')
code, st, err = run([under(rec='21-12', ua=5.997 - 6)], live=LIVE_6, done=DONE_6)
check('units display: a grade leaving -0.003u running lands', (code, err.strip()), (0, ''))
check("units display: manifest units_pl reads '+0.00u', never '+-0.00u'", st['manifest.json']['units_pl'], '+0.00u')
check('units display: the api mirror carries units 0.0, never -0.0', str(st['slates/api_record.json']['units']), '0.0')
code, st2, err = run([devils(rec='22-12', ua=5.997 - 6 + D_DEV)], live=st['manifest.json'], done=st['record_done.json'])
check('units display: the next grade continues the chain from +0.00u', (code, err.strip(), st2['manifest.json']['units_pl']),
      (0, '', '+3.08u'))
code, st, _ = run([devils(delta=D_DEV, ua=3.125)], live=dict(LIVE, units_pl='+0.04u'),
                  done=dict(DONE, record_after='21-11', units_after_exact=str(3.125 - D_DEV)))
check('units display: manifest and api mirror agree, half-up (3.125 exactly)', (code, st['manifest.json']['units_pl'],
      st['slates/api_record.json']['units']), (0, '+3.13u', 3.13))

# DI-06: a pick already on its card date's row is refused, never double counted
hist_dup = copy.deepcopy(HIST)
hist_dup['days'].append({'date': '2026-10-01', 'label': 'Thursday, Oct 1', 'record': '1-0', 'units': '+3.09u', 'brief': '',
                         'picks': [{'name': 'Devils ML', 'game': 'vs Flyers', 'odds': '-162', 'units': '5u', 'result': 'W',
                                    'score': 'PHI 2, NJ 3', '_delta': str(D_DEV)}]})
refused('DI-06 re-grade of a pick already on its day row', [devils()], 'duplicate', hist=hist_dup)

# eod_day_close (Oct 2 review): the brief fill writes only an EMPTY day brief. A day whose brief was
# filed another way (Sep 27: _delta rows + brief, no eod receipt) keeps it - a stored note is never replaced.
def _eod_day(date, label, brief):
    return {'date': date, 'label': label, 'record': '2-1', 'units': '+0.09u', 'brief': brief, 'picks': [
        {'name': 'Lions ML', 'game': 'vs Jets', 'odds': '-162', 'units': '5u', 'result': 'W', 'score': 'NYJ 24, DET 31', '_delta': '3.086419753'},
        {'name': 'Phillies ML', 'game': 'vs Rays', 'odds': '+100', 'units': '2u', 'result': 'W', 'score': 'TB 1, PHI 4', '_delta': '2.0'},
        {'name': 'Bengals ML', 'game': 'at Steelers', 'odds': '-120', 'units': '5u', 'result': 'L', 'score': 'CIN 27, PIT 30', '_delta': '-5.0'}]}
HIST_EOD = {'days': [_eod_day('2026-09-27', 'Sunday, Sep 27', '2-1, +0.09u on the day. The brief already filed for this day.'),
                     _eod_day('2026-09-29', 'Tuesday, Sep 29', '')]}
def eod(date, brief):
    return {'kind': 'eod_day_close', 'date': date, 'record': '2-1', 'units': '+0.09u', 'brief': brief}
err = refused('EOD a brief already filed on a past day is never replaced', [], 'never replaced',
              hist=HIST_EOD, payload=eod('2026-09-27', 'Replacement brief text for a day that already has one.'))
code, st, err = run([], hist=HIST_EOD, payload=eod('2026-09-29', 'Sep 29 closed 2-1.'))
check('EOD an empty day brief is filled (exit 0)', code, 0)
check('EOD the filled brief is the payload brief', (day(st, '2026-09-29') or {}).get('brief'), 'Sep 29 closed 2-1.')
check('EOD the other day\'s filed brief is untouched', (day(st, '2026-09-27') or {}).get('brief'), HIST_EOD['days'][0]['brief'])
check('EOD receipt recorded', 'eod_day_close:2026-09-29' in st['record_done.json'].get('processed', []), True)
# an eod re-sent for a day eod already closed (receipt in record_done.json) is skipped - exit 0, the
# request cleared - even when its brief text was regenerated; it used to be refused (exit 3, a red
# record-final run, the payload left queued). The day with a filed brief and no receipt still refuses.
DONE_EOD = dict(DONE, processed=DONE['processed'] + ['eod_day_close:2026-09-29'])
HIST_EOD_CLOSED = copy.deepcopy(HIST_EOD)
HIST_EOD_CLOSED['days'][1]['brief'] = 'Sep 29 closed 2-1.'
for label, brief in [('regenerated brief text', 'Sep 29 closed 2-1 (regenerated wording).'), ('the same brief text', 'Sep 29 closed 2-1.')]:
    code, st, err = run([], hist=HIST_EOD_CLOSED, done=DONE_EOD, payload=eod('2026-09-29', brief))
    check(f'EOD re-sent for a closed day ({label}): skipped, exit 0', (code, 'REFUSE' in err), (0, False))
    check(f'EOD re-sent for a closed day ({label}): request cleared', st['record_request.json'], {'requests': []})
    check(f'EOD re-sent for a closed day ({label}): history.json untouched', st['history.json'], HIST_EOD_CLOSED)
refused('EOD a filed brief with no eod receipt still refuses', [], 'never replaced', hist=HIST_EOD_CLOSED,
        payload=eod('2026-09-29', 'Sep 29 closed 2-1 (regenerated wording).'))

# MLS scorer props (Oct 2 review): build_manifest cards anytime/first/last goal and finals_watch grades
# them from the ESPN summary's goal events; the record write checks them the same way (scoringPlay
# events, own goals never credit, periods 1-2 only, strict roster identity, tied first/last clock
# refused) instead of refusing every one and stalling the in-order queue behind it.
SOC_LG = 'soccer/usa.1'
def _goal(clock, period, text, typ='goal'):
    return {'scoringPlay': True, 'type': {'type': typ}, 'period': {'number': period}, 'clock': {'value': clock}, 'text': text}
def _roster(side, tid, team, names):
    return {'homeAway': side, 'team': {'id': tid, 'displayName': team},
            'roster': [{'athlete': {'id': f'{tid}-{i}', 'displayName': n}} for i, n in enumerate(names)]}
def soc_summary(goals):
    return {'header': {'competitions': [{'competitors': [{'homeAway': 'home', 'team': {'id': '183'}}, {'homeAway': 'away', 'team': {'id': '20232'}}]}]},
            'boxscore': {'teams': []},
            'rosters': [_roster('home', '183', 'Columbus Crew', ['Josef Mart\u00ednez', 'Jamal Thiar\u00e9', 'Carlos Gomez']),
                        _roster('away', '20232', 'Inter Miami CF', ['Lionel Messi', 'Jordi Alba', 'Luis Su\u00e1rez', 'Luis Gomez'])],
            'keyEvents': [{'scoringPlay': False, 'type': {'type': 'yellow-card'}, 'period': {'number': 1}, 'clock': {'value': 900.0}, 'text': 'Jordi Alba (Inter Miami CF) is shown the yellow card.'}] + goals}
SOC_GOALS = [
    _goal(1634.0, 1, 'Goal! Columbus Crew 1, Inter Miami CF 0. Josef Mart\u00ednez (Columbus Crew) converts the penalty with a right footed shot.', 'penalty---scored'),
    _goal(1976.0, 1, 'Goal! Columbus Crew 1, Inter Miami CF 1. Lionel Messi (Inter Miami CF) from a free kick with a left footed shot.', 'goal---free-kick'),
    _goal(3100.0, 2, 'Own Goal by Jordi Alba, Inter Miami CF. Columbus Crew 2, Inter Miami CF 1.', 'own-goal'),
    _goal(5400.0, 2, 'Goal! Columbus Crew 3, Inter Miami CF 1. Jamal Thiar\u00e9 (Columbus Crew) right footed shot from the centre of the box.', 'goal---volley'),
    _goal(5700.0, 5, 'Goal! Luis Su\u00e1rez (Inter Miami CF) scores in the shootout.')]
FIX[CORE.format(lg='soccer/leagues/usa.1', e='761844', c='761844')] = core('Inter Miami CF', 1, 'Columbus Crew', 3)
FIX[SITE.format(lg=SOC_LG, e='761844')] = soc_summary(SOC_GOALS)
FIX[CORE.format(lg='soccer/leagues/usa.1', e='761845', c='761845')] = core('Inter Miami CF', 1, 'Columbus Crew', 2)
FIX[SITE.format(lg=SOC_LG, e='761845')] = soc_summary([  # two stoppage-time goals share the 90' clock value
    _goal(1976.0, 1, 'Goal! Columbus Crew 0, Inter Miami CF 1. Lionel Messi (Inter Miami CF) left footed shot.'),
    _goal(5400.0, 2, 'Goal! Columbus Crew 1, Inter Miami CF 1. Josef Mart\u00ednez (Columbus Crew) header.'),
    _goal(5400.0, 2, 'Goal! Columbus Crew 2, Inter Miami CF 1. Jamal Thiar\u00e9 (Columbus Crew) right footed shot.')])
SOC_MKT = {'anytime_goal': 'anytime goal', 'first_goal': '1st goal', 'last_goal': 'last goal'}
def soc_pick(player, market, eid='761844'):
    return pick(f'{player} {SOC_MKT[market]}', eid, SOC_LG, 'Inter Miami CF', 'Columbus Crew', '2026-09-27T23:30Z', '+150', '5u', 'over', 'prop',
                line=0.5, player=player, market=market)
SOC_PLAYS = [('Lionel Messi', 'anytime_goal'), ('Josef Mart\u00ednez', 'first_goal'), ('Jamal Thiar\u00e9', 'last_goal'), ('Lionel Messi', 'first_goal'),
             ('Jordi Alba', 'anytime_goal'), ('Luis Su\u00e1rez', 'anytime_goal'), ('Gomez', 'anytime_goal')]
SOC_CARD = {'date': '2026-09-27', 'record': '13-6', 'units_pl': '+3.89u',
            'picks': [soc_pick(pl, mk) for pl, mk in SOC_PLAYS] + [soc_pick('Jamal Thiar\u00e9', 'last_goal', '761845')]}
SOC_SNAP = {'manifests/manifest-0927dddddddd.json': SOC_CARD}
def soc_req(player, market, result, eid='761844', score='MIA 1 @ CLB 3'):
    gid = f"{eid}|prop|{''.join(ch for ch in player.lower() if ch.isascii() and ch.isalnum())}|{market}|over|0.5"
    delta, rec = {'WON': (7.5, '22-11'), 'LOST': (-5.0, '21-12')}[result]
    return req(gid, eid, SOC_LG, f'{player} {SOC_MKT[market]}', 'over', result, score, '+150', '5u', delta, rec, U0 + delta)
for player, market, result, label in [('Lionel Messi', 'anytime_goal', 'WON', 'anytime goal by the away scorer'),
                                      ('Josef Mart\u00ednez', 'first_goal', 'WON', 'first goal (earliest clock)'),
                                      ('Jamal Thiar\u00e9', 'last_goal', 'WON', 'last goal (latest clock)'),
                                      ('Lionel Messi', 'first_goal', 'LOST', 'first goal by another player'),
                                      ('Jordi Alba', 'anytime_goal', 'LOST', 'an own goal never credits its scorer'),
                                      ('Luis Su\u00e1rez', 'anytime_goal', 'LOST', 'a shootout goal is not a goal')]:
    code, st, err = run([soc_req(player, market, result)], snaps=SOC_SNAP)
    check(f'MLS {label}: {result} lands', (code, err.strip()), (0, ''))
    check(f'MLS {label}: row filed on the Sep 27 card', [(p['name'], p['result']) for p in (day(st, '2026-09-27') or {}).get('picks', [])],
          [(f'{player} {SOC_MKT[market]}', result[0])])
    refused(f'MLS {label}: the opposite label', [soc_req(player, market, 'LOST' if result == 'WON' else 'WON')],
            'contradicts the verified final', snaps=SOC_SNAP)
code, st, _ = run([soc_req('Lionel Messi', 'anytime_goal', 'WON')], snaps=SOC_SNAP)
check('MLS scorer prop game label is the player\'s own team (Messi is away)', [p['game'] for p in (day(st, '2026-09-27') or {}).get('picks', [])], ['at Crew'])
refused('MLS a name two roster players share is refused', [soc_req('Gomez', 'anytime_goal', 'LOST')], 'independent prop verification failed', snaps=SOC_SNAP)
refused('MLS last goal on a tied stoppage-time clock is refused', [soc_req('Jamal Thiar\u00e9', 'last_goal', 'WON', '761845', 'MIA 1 @ CLB 2')],
        'independent prop verification failed', snaps=SOC_SNAP)

# MLS scorer props on D.C. United and St. Louis CITY SC games (Oct 2 re-check): ESPN's goal text is
# 'Goal! <home> <n>, <away> <n>. <Scorer> (<Team>) ...', and the first '. ' can fall inside a team
# name ('D.C. United', 'St. Louis City SC'), so the scorer is read after the scoreline, never after
# the first '. '. Trimmed real ESPN summaries: 761518 FC Dallas 4 at D.C. United 0 (Farrington 16',
# Delgado 45+1', Urhoghide 78', Musa 90+1') and 761439 Charlotte FC 1 at St. Louis 1 (Hartel 60', Biel 73').
FIXDIR = os.path.join(os.path.dirname(HERE), 'tests', 'fixtures')
FIX[CORE.format(lg='soccer/leagues/usa.1', e='761518', c='761518')] = core('FC Dallas', 4, 'D.C. United', 0)
FIX[SITE.format(lg=SOC_LG, e='761518')] = json.load(open(os.path.join(FIXDIR, 'soccer_summary_dc_761518.json')))
FIX[CORE.format(lg='soccer/leagues/usa.1', e='761439', c='761439')] = core('Charlotte FC', 1, 'St. Louis CITY SC', 1)
FIX[SITE.format(lg=SOC_LG, e='761439')] = json.load(open(os.path.join(FIXDIR, 'soccer_summary_stl_761439.json')))
REAL_MLS = {  # eid -> (card date, commence, away, home, final score, plays)
    '761518': ('2026-04-04', '2026-04-04T23:30Z', 'FC Dallas', 'D.C. United', 'DAL 4 @ DC 0', [
        ('Petar Musa', 'anytime_goal', 'WON'), ('Logan Farrington', 'first_goal', 'WON'),
        ('Petar Musa', 'last_goal', 'WON'), ('Logan Farrington', 'last_goal', 'LOST'), ('Tai Baribo', 'anytime_goal', 'LOST')]),
    '761439': ('2026-02-21', '2026-02-21T19:30Z', 'Charlotte FC', 'St. Louis CITY SC', 'CLT 1 @ STL 1', [
        ('Marcel Hartel', 'first_goal', 'WON'), ('Pep Biel', 'last_goal', 'WON'),
        ('Marcel Hartel', 'anytime_goal', 'WON'), ('Marcel Hartel', 'last_goal', 'LOST')])}
for eid, (cdate, commence, away, home, score, plays) in REAL_MLS.items():
    snap = {f'manifests/manifest-{eid}eeeeee.json': {'date': cdate, 'record': '21-11', 'units_pl': '+4.76u', 'picks': [
        pick(f'{pl} {SOC_MKT[mk]}', eid, SOC_LG, away, home, commence, '+150', '5u', 'over', 'prop', line=0.5, player=pl, market=mk)
        for pl, mk, _ in plays]}}
    for player, market, result in plays:
        code, st, err = run([soc_req(player, market, result, eid, score)], snaps=snap)
        check(f'MLS real {eid} {player} {market} {result} lands', (code, err.strip()), (0, ''))
        check(f'MLS real {eid} {player} {market}: row filed on the {cdate} card', [(p['name'], p['result'], p['score'])
              for p in (day(st, cdate) or {}).get('picks', [])], [(f'{player} {SOC_MKT[market]}', result[0], score.replace(' @', ','))])
        refused(f'MLS real {eid} {player} {market}: the opposite label', [soc_req(player, market, 'LOST' if result == 'WON' else 'WON', eid, score)],
                'contradicts the verified final', snaps=snap)

# MMA: a PUSH label on a fight with a winner flag is a contradiction
rf = load()
rf._get = fake_get
with contextlib.redirect_stderr(io.StringIO()):
    mma = rf.espn_verify_mma('mma/ufc', '600060739', '401891663',
                             {'pick': 'Loai Abushaar ML', 'result': 'PUSH', 'graded_pick': 'Staines def. Abushaar'})
    mma_ok = rf.espn_verify_mma('mma/ufc', '600060739', '401891663',
                                {'pick': 'Loai Abushaar ML', 'result': 'LOST', 'graded_pick': 'Staines def. Abushaar'})
check('MMA PUSH on a decided fight refused', mma, None)
check('MMA LOST on the loser verified', (mma_ok or {}).get('winner'), 'George Staines')

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
