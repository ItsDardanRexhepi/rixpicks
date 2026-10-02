#!/usr/bin/env python3
"""Owner-rules fixture for scripts/build_manifest.py (RixPicks daily-card runbook 2.5 and 2.8).
 - Vegas: "never gamble on or against any Vegas teams ever" / "Exclude A's going forward from
   today too". A pick on or against the Raiders (NFL), Golden Knights (NHL), Aces (WNBA),
   Athletics/A's (MLB) or UNLV (college) refuses closed - exit nonzero, nothing written (no
   manifest, no ledger, no prod mirror). A nickname counts only inside its own league: Texas Tech
   Red Raiders (CFB) and Evansville Purple Aces (NCAAB) are not Vegas teams.
 - Units: only the J-096 ladder, 5u, 10u, 15u, 100u.
 - Either passes only on an explicit owner directive naming the rule with his verbatim words, on
   the candidate row or via --owner-directive, and the manifest pick records it as owner_directive.
 The page builder carries no such gate (it renders whatever card has landed): see
 test_card_shapes_build.py, which builds a card with an Aces pick.
Run: python3 scripts/test_build_manifest_owner_rules.py"""
import copy, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
failures = 0

def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or detail == '' else '  [' + str(detail)[-300:] + ']'))
    if not ok:
        failures += 1

META = {'record': '21-11', 'units_pl': '+4.76u', 'units_ledger': None, 'yesterday': '', 'status_note': '', 'parlay': None}
def cand(num, name, league, away, home, units='5u', mc='ml', side='home', **extra):
    c = {'num': num, 'date': '2099-10-04', 'market_class': mc, 'name': name, 'side': side, 'away': away, 'home': home,
         'commence': '2099-10-04T20:25Z', 'eid': str(401990000 + num), 'espn_league': league, 'units': units,
         'model': 66.0, 'gross_c': 3.0, 'net_c': 2.2, 'sub_context': 'fixture',
         'kalshi': {'cents': 61, 'team': home, 'ticker': 'KXFIX-99OCT04-%d' % num}}
    c.update(extra)
    return c

WORDS = "fixture: the owner's verbatim words go here"

def build(cands, *extra_args):
    d = tempfile.mkdtemp(prefix='rp-bm-owner-')
    try:
        os.makedirs(os.path.join(d, 'ledger')); os.makedirs(os.path.join(d, 'prod'))
        cf, mf, out = (os.path.join(d, x) for x in ('cands.json', 'meta.json', 'manifest.json'))
        json.dump(cands, open(cf, 'w')); json.dump(META, open(mf, 'w'))
        env = dict(os.environ, PYTHONPATH=ROOT, RIX_PICKS_LEDGER=os.path.join(d, 'ledger', 'picks.jsonl'),
                   RIX_PROD_MANIFEST=os.path.join(d, 'prod', 'manifest.json'),
                   http_proxy='http://127.0.0.1:9', https_proxy='http://127.0.0.1:9')
        r = subprocess.run([sys.executable, os.path.join(HERE, 'build_manifest.py'), cf, out, '--meta', mf, *extra_args],
                           capture_output=True, text=True, env=env, timeout=120)
        man = json.load(open(out)) if os.path.exists(out) else None
        written = sorted(os.path.relpath(os.path.join(p, f), d) for p, _, fs in os.walk(d) for f in fs
                         if f not in ('cands.json', 'meta.json', 'picks.jsonl.lock'))
        return r.returncode, r.stdout + r.stderr, man, written
    finally:
        shutil.rmtree(d, ignore_errors=True)

def refused(label, cands, why, *args):
    rc, log, man, written = build(cands, *args)
    check(f'{label}: refused (exit nonzero)', rc != 0, log)
    check(f'{label}: refused for the stated reason ({why})', why in log, log)
    check(f'{label}: nothing written (no manifest, ledger or prod mirror)', man is None and written == [], written)

CLEAN = cand(1, 'Chiefs ML', 'football/nfl', 'Denver Broncos', 'Kansas City Chiefs', '10u')

# Vegas teams, on and against, every league the rule names
refused('Raiders ML (NFL, on)', [cand(1, 'Raiders ML', 'football/nfl', 'Denver Broncos', 'Las Vegas Raiders')], 'never on or against a Vegas team')
refused('Chiefs ML at the Raiders (NFL, against)', [cand(1, 'Chiefs ML', 'football/nfl', 'Kansas City Chiefs', 'Las Vegas Raiders', side='away')],
        'never on or against a Vegas team')
refused('Golden Knights game (NHL)', [cand(1, 'Kings ML', 'hockey/nhl', 'Los Angeles Kings', 'Vegas Golden Knights', side='away')], 'Vegas team')
refused('Aces spread (WNBA)', [cand(1, 'Fever +4.5', 'basketball/wnba', 'Indiana Fever', 'Las Vegas Aces', mc='spread', side='away', line=4.5)], 'Vegas team')
refused('Athletics game (MLB, ESPN name "Athletics")', [cand(1, 'Astros ML', 'baseball/mlb', 'Athletics', 'Houston Astros')], 'Vegas team')
refused("A's in the pick text (MLB)", [cand(1, 'A’s ML', 'baseball/mlb', 'Sacramento Club', 'Houston Astros', side='away')], 'Vegas team')
refused('UNLV game (CFB)', [cand(1, 'Under 55.5', 'football/college-football', 'UNLV Rebels', 'Boise State Broncos', mc='total', side='under', line=55.5)],
        'Vegas team')
refused('a Vegas prop: the game involves the Aces', [cand(1, "A'ja Wilson over 24.5 points", 'basketball/wnba', 'Indiana Fever', 'Las Vegas Aces',
        mc='prop', side='over', line=24.5, player="A'ja Wilson", market='points')], 'Vegas team')
refused('one Vegas pick refuses the whole card', [CLEAN, cand(2, 'Raiders ML', 'football/nfl', 'Denver Broncos', 'Las Vegas Raiders')], 'Raiders ML')

# nicknames only inside their own league
rc, log, man, _ = build([cand(1, 'Red Raiders ML', 'football/college-football', 'Baylor Bears', 'Texas Tech Red Raiders'),
                         cand(2, 'Purple Aces ML', 'basketball/mens-college-basketball', 'Murray State Racers', 'Evansville Purple Aces')])
check('Texas Tech Red Raiders (CFB) and Evansville Purple Aces (NCAAB) are not Vegas teams', rc == 0 and man and len(man['picks']) == 2, log)

# the J-096 ladder
for u in ('6u', '7u', '8u', '2u', '20u', 'max'):
    refused(f'units {u} off the ladder', [cand(1, 'Chiefs ML', 'football/nfl', 'Denver Broncos', 'Kansas City Chiefs', u)], 'not on the J-096 ladder')
rc, log, man, _ = build([cand(i, f'Team{i} ML', 'hockey/nhl', f'Away{i} Club', f'Home{i} Club', u) for i, u in enumerate(('5u', '10u', '15u', '100u'), 1)])
check('5u, 10u, 15u and 100u build', rc == 0 and man and [p['units'] for p in man['picks']] == ['5u', '10u', '15u', '100u'], log)
check('a card that breaks no rule carries no owner_directive', bool(man) and all('owner_directive' not in p for p in man['picks']), man and man['picks'][0])

# owner directives: per pick and on the command line, recorded on the manifest pick
rc, log, man, _ = build([dict(cand(1, 'Raiders ML', 'football/nfl', 'Denver Broncos', 'Las Vegas Raiders'),
                              owner_directive={'rules': ['vegas'], 'words': WORDS, 'at': '2099-10-04T15:00:00Z'})])
check('a per-pick owner directive naming the Vegas rule passes', rc == 0 and man is not None, log)
check('the manifest pick records the directive with his verbatim words',
      (man or {'picks': [{}]})['picks'][0].get('owner_directive') == {'rules': ['vegas'], 'words': WORDS, 'via': 'candidate', 'at': '2099-10-04T15:00:00Z'},
      (man or {'picks': [{}]})['picks'][0].get('owner_directive'))
refused('a directive for the units rule does not cover a Vegas pick',
        [dict(cand(1, 'Raiders ML', 'football/nfl', 'Denver Broncos', 'Las Vegas Raiders'), owner_directive={'rules': ['units'], 'words': WORDS})],
        'Vegas team')
refused('a directive without his words is no directive',
        [dict(cand(1, 'Raiders ML', 'football/nfl', 'Denver Broncos', 'Las Vegas Raiders'), owner_directive={'rules': ['vegas'], 'words': '  '})],
        'verbatim words')
rc, log, man, _ = build([CLEAN, cand(2, 'Bills ML', 'football/nfl', 'New England Patriots', 'Buffalo Bills', '6u')],
                        '--owner-directive', json.dumps({'num': 2, 'rules': ['units'], 'words': WORDS}))
check('a CLI owner directive naming the units rule passes a 6u pick', rc == 0 and man is not None, log)
check('the CLI directive is recorded on that pick only',
      man is not None and man['picks'][1].get('owner_directive') == {'rules': ['units'], 'words': WORDS, 'via': 'cli'}
      and 'owner_directive' not in man['picks'][0], man and [p.get('owner_directive') for p in man['picks']])
refused('a CLI directive for a pick that is not on the card', [CLEAN], 'not in the candidates',
        '--owner-directive', json.dumps({'num': 9, 'rules': ['units'], 'words': WORDS}))
refused('a CLI directive that is not JSON', [CLEAN], 'needs a JSON object', '--owner-directive', 'yes do it')

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
