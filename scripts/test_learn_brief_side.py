#!/usr/bin/env python3
"""Learning-engine side fixture (sweep DI-04, code cause only - published Sep 27 notes are not
touched here): learn_brief.our_side must bind a pick to ITS team. The old matcher took the
first competitor (home) whose name was a substring of the pick text, so 'Bengals ML @ Steelers'
read the Steelers' closing line (+154) and win probability: the Sep 27 record published
'CLV -22.6pp (market flipped)' and 'peaked at 99%+ - bad beat' for a pick that closed -185
(CLV +2.9pp) and peaked at 71%. Offline: the ESPN summary is a fixture.
Bite-proof: red on the pre-fix learn_brief.py. Run: python3 scripts/test_learn_brief_side.py"""
import contextlib, io, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import learn_brief  # noqa: E402

failures = 0
def check(name, actual, expected):
    global failures
    ok = actual == expected
    print(('OK  ' if ok else 'FAIL'), name, '' if ok else f'(got {actual!r}, want {expected!r})')
    if not ok:
        failures += 1

def team(display, short, abbr):
    return {'displayName': display, 'shortDisplayName': short, 'name': short, 'abbreviation': abbr}

SUMMARY = {
    'header': {'competitions': [{'competitors': [
        {'homeAway': 'home', 'team': team('Pittsburgh Steelers', 'Steelers', 'PIT')},
        {'homeAway': 'away', 'team': team('Cincinnati Bengals', 'Bengals', 'CIN')}]}]},
    'pickcenter': [{'provider': {'name': 'DraftKings'}, 'homeTeamOdds': {'moneyLine': 154}, 'awayTeamOdds': {'moneyLine': -185}}],
    'winprobability': [{'homeWinPercentage': x} for x in (0.5, 0.2905, 0.6, 1.0)],
    'article': {'headline': 'Steelers rally late'}}

def side(text, s=None):
    try:
        return learn_brief.our_side(SUMMARY, text, s)[0]
    except TypeError:  # a matcher that cannot take the card side ignores it
        return learn_brief.our_side(SUMMARY, text)[0]
check('away pick named before the @ is the away team', side('Bengals ML @ Steelers'), 'away')
check('home pick named before vs is the home team', side('Steelers ML vs Bengals'), 'home')
check('plain away pick', side('Bengals ML'), 'away')
check('abbreviation pick', side('CIN ML at PIT'), 'away')
check('explicit card side wins over the text', side('Bengals ML @ Steelers', 'home'), 'home')
check('a total has no team side', side('Under 38.5 CIN @ PIT'), None)
check('text naming both teams before any clause is a gap, not a guess', side('Bengals Steelers combo'), None)
check('whole words only: no team inside another word', side('Pittsburghers ML'), None)

with contextlib.redirect_stdout(io.StringIO()):
    note, facts = learn_brief.pick_note({'pick': 'Bengals ML @ Steelers', 'locked_odds': '-163 published card',
                                         'units': '5u', 'result': 'L 17-20', 'note': ''}, SUMMARY)
check('CLV read from the Bengals close (-185 vs card -163)', facts.get('clv_pp'), 2.9)
check('no false market-flip claim', 'market flipped' in note, False)
check('win probability peak is the Bengals\' (71%)', facts.get('max_wp'), 0.71)
check('note never claims a 99%+ bad beat', '99%+' in note, False)
with contextlib.redirect_stdout(io.StringIO()):
    _, facts2 = learn_brief.pick_note({'pick': 'Road favorite ML', 'side': 'away', 'locked_odds': '-163 published card',
                                       'units': '5u', 'result': 'L 17-20', 'note': ''}, SUMMARY)
check('a row carrying its card side is read from that side', facts2.get('clv_pp'), 2.9)

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
