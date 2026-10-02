#!/usr/bin/env python3
"""Fail-closed record write fixture (sweep CP-05, CP-07, CP-16, M1, DI-06, DI-11): record_final.py
must REFUSE (exit 3, nothing written) a grade whose result contradicts the verified final, whose
unit delta does not follow from the card price and stake, whose units chain does not continue,
whose pick was never on a published card, or that repeats a pick already on its day's row. It
files each grade under the pick's own card date (not the date the live manifest carries when the
grade lands), and labels totals and props from the game, not from the over/under side.
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
    pick('Aces -11', '401918022', 'basketball/wnba', 'Indiana Fever', 'Las Vegas Aces', '2026-10-02T02:00Z', '-110', '5u', 'home', 'spread', line=-11)]}
SEP29 = {'date': '2026-09-29', 'record': '19-8', 'units_pl': '+10.05u', 'picks': [
    pick('Yordan Alvarez over 1.5 hits', '401907896', 'baseball/mlb', 'Chicago White Sox', 'Houston Astros', '2026-09-29T21:00Z',
         '+270', '5u', 'over', 'prop', line=1.5, player='Yordan Alvarez', market='bat_hits'),
    {'name': 'Loai Abushaar ML', 'market_class': 'ml', 'side': 'home', 'odds': '+285', 'card_american': 285, 'units': '5u',
     'espn_league': 'mma/ufc', 'game': {'away': 'George Staines', 'home': 'Loai Abushaar', 'commence': '2026-09-29T23:00Z', 'eid': None}}]}
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

def run(reqs, hist=HIST, done=DONE, live=LIVE, payload=None):
    tmp = tempfile.mkdtemp(prefix='rf_verify_')
    try:
        os.makedirs(os.path.join(tmp, 'manifests'))
        os.makedirs(os.path.join(tmp, 'slates'))
        files = {'manifest.json': live, 'history.json': hist, 'record_done.json': done,
                 'record_request.json': payload if payload is not None else {'requests': reqs},
                 'manifests/manifest-0c7101aaaaaa.json': OCT1, 'manifests/manifest-0929bbbbbbbb.json': SEP29}
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
        state = {f: json.load(open(os.path.join(tmp, f))) for f in ('manifest.json', 'history.json', 'record_done.json')}
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

# DI-06: a pick already on its card date's row is refused, never double counted
hist_dup = copy.deepcopy(HIST)
hist_dup['days'].append({'date': '2026-10-01', 'label': 'Thursday, Oct 1', 'record': '1-0', 'units': '+3.09u', 'brief': '',
                         'picks': [{'name': 'Devils ML', 'game': 'vs Flyers', 'odds': '-162', 'units': '5u', 'result': 'W',
                                    'score': 'PHI 2, NJ 3', '_delta': str(D_DEV)}]})
refused('DI-06 re-grade of a pick already on its day row', [devils()], 'duplicate', hist=hist_dup)

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
