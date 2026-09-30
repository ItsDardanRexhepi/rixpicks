#!/usr/bin/env python3
# Standing regression fixture for the Sep 29 MLB class kill: when ESPN's team schedule
# endpoint yields no completed MLB games, team pages must fall back to the MLB Stats API.
# Extracts the real mlb_form_fallback + _MLBAM map from the shipped builder and runs them
# offline against canned payloads. Run: python3 scripts/test_mlb_form_fallback.py
# Wired into x_feed.yml beside soc_fixtures.py - a failure aborts the chain.
import re, sys, os

src = open(os.path.join(os.path.dirname(__file__), 'build_gh_page_v2.py')).read()

m = re.search(r'^(_MLBAM=\{.*?\})$', src, re.M)
if not m: print('FAIL: _MLBAM map not found'); sys.exit(1)
start = src.index('def mlb_form_fallback(')
end = src.index('# end mlb_form_fallback')
ns = {}
exec(m.group(1) + '\n\n' + src[start:end], ns)
fb = ns['mlb_form_fallback']; MLBAM = ns['_MLBAM']

fails = []
def check(label, cond):
    print(('OK   ' if cond else 'FAIL ') + label)
    if not cond: fails.append(label)

# 1. map completeness: all 30 MLB teams, Yankees 10 -> 147
check('map has 30 teams', len(MLBAM) == 30)
check('yankees 10->147', MLBAM.get('10') == '147')
check('map values unique', len(set(MLBAM.values())) == 30)

# 2. unknown / non-MLB tid -> None (fail closed)
check('unknown tid returns None', fb('999', lambda u: {}, '2026-09-29') is None)

# 3. canned Stats API payload: 2 Final (1 win away, 1 loss home) + 1 future Preview
PAYLOAD = {'dates': [
  {'date': '2026-09-26', 'games': [{'gameDate': '2026-09-26T23:05:00Z',
     'status': {'abstractGameState': 'Final'},
     'teams': {'away': {'team': {'id': 147, 'name': 'New York Yankees', 'abbreviation': 'NYY'}, 'score': 5},
               'home': {'team': {'id': 111, 'name': 'Boston Red Sox', 'abbreviation': 'BOS'}, 'score': 3}}}]},
  {'date': '2026-09-28', 'games': [{'gameDate': '2026-09-28T23:05:00Z',
     'status': {'abstractGameState': 'Final'},
     'teams': {'away': {'team': {'id': 117, 'name': 'Toronto Blue Jays', 'abbreviation': 'TOR'}, 'score': 7},
               'home': {'team': {'id': 147, 'name': 'New York Yankees', 'abbreviation': 'NYY'}, 'score': 2}}}]},
  {'date': '2026-09-30', 'games': [{'gameDate': '2026-09-30T23:05:00Z',
     'status': {'abstractGameState': 'Preview'},
     'teams': {'away': {'team': {'id': 147, 'name': 'New York Yankees', 'abbreviation': 'NYY'}},
               'home': {'team': {'id': 141, 'name': 'Baltimore Orioles', 'abbreviation': 'BAL'}}}}]},
]}
r = fb('10', lambda u: PAYLOAD, '2026-09-29')
check('fallback returns dict', isinstance(r, dict))
check('last5 chronological both finals', r['last5'] == ['W 5-3 @ BOS \u00b7 09-26', 'L 2-7 vs TOR \u00b7 09-28'])
check('scored tuples', r['scored'] == [(5, 3), (2, 7)])
check('upcoming from preview', r['upcoming'] == ['@ BAL \u00b7 09-30'])
check('next event wired', r['next'] and r['next']['commence'] == '2026-09-30T23:05:00Z'
      and r['next']['away'] == 'New York Yankees' and r['next']['home'] == 'Baltimore Orioles')
check('next event eid empty (never unverifiable)', r['next']['eid'] == '')

# 4. empty Stats API response -> empty lists, not an exception
r2 = fb('10', lambda u: {'dates': []}, '2026-09-29')
check('empty payload fails closed', r2['last5'] == [] and r2['scored'] == [] and r2['next'] is None)

# 5. fetch error propagates to caller's try/except (function itself must raise, caller swallows)
def boom(u): raise RuntimeError('network down')
try:
    fb('10', boom, '2026-09-29'); check('fetch error raises for caller guard', False)
except RuntimeError:
    check('fetch error raises for caller guard', True)


# --- K16/K17 guards (Sep 29 site-audit): postseason-thin ESPN schedules + UTC/PT date split ---
# K17: the team form loop must PT-convert ESPN event dates - raw [:10] UTC slicing labeled
# tonight's 5 PM PT game 09-30 while the header said Sep 29.
check('K17 form loop PT-converts ESPN dates', "dt=_pt_date(str(ev.get('date','')))" in src)
check('K17 no raw UTC slice in form loop', "dt=str(ev.get('date',''))[:10]" not in src)
check('K17 upcoming filter uses PT today', "if dt and dt >= _dtn.datetime.now(_ZI('America/Los_Angeles')).date().isoformat() and len(upcoming)<3" in src)

# _pt_date itself must really convert (midnight-UTC game lands on the prior PT day)
ptstart = src.index('def _pt_date(')
ptend = src.index('\n', src.index('except Exception:', ptstart))
ns_pt = {}
exec(src[ptstart:ptend], ns_pt)
check('K17 _pt_date converts midnight-UTC to prior PT day', ns_pt['_pt_date']('2026-09-30T00:00Z') == '2026-09-29')

# K16: the statsapi fallback must ALSO fire when postseason ESPN yields a thin (1-4 game)
# completed set, and must MERGE (dedupe) instead of replace.
check('K16 fallback fires on thin completed set', "len(_scored)<5" in src)
check('K16 zero-only trigger gone', "tid and not _scored" not in src)
check('K16 merge keeps score-keyed dedupe', "_k=r.rsplit(' \u00b7 ',1)[-1]+'|'+' '.join(r.split()[:3])" in src)

# Functional: run the shipped merge statements offline. ESPN postseason row names the opponent
# by abbreviation (vs BOS), statsapi by full name (vs Boston Red Sox) - the Sep 29 dup-row bug.
import textwrap as _tw
mstart = src.rindex('\n', 0, src.index('_merged=[]; _seen=set()')) + 1
mend = src.index("last5=[r for r,_ in _merged][-5:]; _scored=[s for _,s in _merged]")
merge_src = _tw.dedent(src[mstart:mend] + "last5=[r for r,_ in _merged][-5:]; _scored=[s for _,s in _merged]\n")
ns_m = {
  '_fb': {'last5': ['W 6-3 vs Baltimore Orioles \u00b7 09-25', 'W 9-0 vs Boston Red Sox \u00b7 09-29'],
          'scored': [(6, 3), (9, 0)]},
  'last5': ['W 9-0 vs BOS \u00b7 09-29'],
  '_scored': [(9, 0)],
}
exec(merge_src, ns_m)
check('K16 merge dedupes abbr-vs-full-name dup', ns_m['last5'] == ['W 6-3 vs Baltimore Orioles \u00b7 09-25', 'W 9-0 vs Boston Red Sox \u00b7 09-29'])
check('K16 merged scores aligned', ns_m['_scored'] == [(6, 3), (9, 0)])

print('PASS' if not fails else 'FAIL: %d assertion(s)' % len(fails))
sys.exit(1 if fails else 0)
