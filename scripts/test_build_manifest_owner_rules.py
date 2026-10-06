#!/usr/bin/env python3
"""Owner-rules fixture for scripts/build_manifest.py (RixPicks daily-card runbook 2.5 and 2.8).
 - Vegas: "never gamble on or against any Vegas teams ever" / "Exclude A's going forward from
   today too". A pick on or against the Raiders (NFL), Golden Knights (NHL), Aces (WNBA),
   Athletics/A's (MLB) or UNLV (college) refuses closed - exit nonzero, nothing written (no
   manifest, no ledger, no prod mirror). A nickname counts only inside its own league: Texas Tech
   Red Raiders (CFB) and Evansville Purple Aces (NCAAB) are not Vegas teams.
 - Units: only the J-096 ladder, 5u, 10u, 15u, 100u.
 - Both are hard gates with no override (owner ruling 2026-10-02, relayed verbatim by muse: "NO - an
   owner-approved card cannot break a standing rule. Vegas rule, ladder sizes, all of it: hard gates,
   no exceptions."). The owner-directive override is gone: a candidate row carrying owner_directive, or
   an --owner-directive argument in any form, is an error (exit nonzero, nothing written), even on a
   card that breaks no rule; no refusal echoes the words it was given, and no manifest pick or ledger
   row carries owner_directive.
 - The Vegas rule is about teams: it skips the individual sports (racing, golf, tennis, MMA, boxing),
   so a NASCAR race at Las Vegas Motor Speedway builds; any other league keeps the rule.
 - A pick num names one pick on the card: two candidates sharing a num refuse.
 - The card date is the builder's _card_date_of rule (the most common PT game date across the
   picks, which record_final.card_date_of also uses), never the first-listed candidate's date.
 - A production card records posted_at (UTC ISO): the newest card_ts of its picks, which is the
   build time for a new card and is never restamped by a regeneration (a pick added later moves it
   to that pick's lock, so no pick claims a lock from before it was carded). The page builder
   prefers posted_at and says "after start" for a game that began before it. A preview has none,
   and neither has an empty card (no pick to lock).
 The standing bars (fair, ask, gross, net, the rung of each pick, the parlay bar) and the best-ask card price
 are in test_build_manifest_bars.py. The page builder holds a landed card with a Vegas pick or an off-ladder
 size (exit 3): test_card_hold_owner_rules.py.
Run: python3 scripts/test_build_manifest_owner_rules.py"""
import copy, datetime, json, os, re, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
failures = 0

def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or detail == '' else '  [' + str(detail)[-300:] + ']'))
    if not ok:
        failures += 1

META = {'record': '21-11', 'units_pl': '+4.76u', 'units_ledger': None, 'yesterday': '', 'status_note': '', 'parlay': None}
# owner ruling 2026-10-02 (1): a non-preview card must carry a best_ask block, so every real candidate gets a
# Kalshi best_ask at its own cents (nothing cheaper compared) unless the case passes one explicitly.
T0 = '2099-10-04T14:51:00Z'
def cand(num, name, league, away, home, units='5u', mc='ml', side='home', **extra):
    c = {'num': num, 'date': '2099-10-04', 'market_class': mc, 'name': name, 'side': side, 'away': away, 'home': home,
         'commence': '2099-10-04T20:25Z', 'eid': str(401990000 + num), 'espn_league': league, 'units': units,
         'model': 66.0, 'gross_c': 3.0, 'net_c': 2.2, 'sub_context': 'fixture',
         'kalshi': {'cents': 61, 'team': home, 'side': 'yes', 'ticker': 'KXFIX-99OCT04-%d' % num}}
    c.update(extra)
    cents = c.get('kalshi', {}).get('cents')
    if 'best_ask' not in extra and isinstance(cents, int) and not isinstance(cents, bool):
        c['best_ask'] = {'venue': 'kalshi', 'price': cents, 'read_at': T0,
                         'compared': [{'venue': 'kalshi', 'price': cents, 'read_at': T0}]}
    return c

# distinctive tokens: none of them occurs anywhere else in a built manifest, so any hit is a leak
WORDS = "Quokka trellis, marzipan zanzibar okapi"
def leaked(text, *phrases):
    """Every directive token (3+ letters) found in text, case-insensitive."""
    low = (text or '').lower()
    return sorted({t for ph in phrases for t in re.findall(r'[a-z0-9]{3,}', ph.lower()) if t in low})

def build_runs(runs):
    """Runs build_manifest once per (cands, extra_args[, pause_s]) in ONE throwaway tree: the ledger,
    the prod mirror and the published manifest carry over between runs, as on the box."""
    d = tempfile.mkdtemp(prefix='rp-bm-owner-')
    try:
        os.makedirs(os.path.join(d, 'ledger')); os.makedirs(os.path.join(d, 'prod'))
        cf, mf, out = (os.path.join(d, x) for x in ('cands.json', 'meta.json', 'manifest.json'))
        ledger = os.path.join(d, 'ledger', 'picks.jsonl')
        env = dict(os.environ, PYTHONPATH=ROOT, RIX_PICKS_LEDGER=ledger,
                   RIX_PROD_MANIFEST=os.path.join(d, 'prod', 'manifest.json'),
                   http_proxy='http://127.0.0.1:9', https_proxy='http://127.0.0.1:9')
        results = []
        for spec in runs:
            cands, extra_args = spec[0], spec[1]
            if len(spec) > 2: time.sleep(spec[2])
            json.dump(cands, open(cf, 'w')); json.dump(META, open(mf, 'w'))
            r = subprocess.run([sys.executable, os.path.join(HERE, 'build_manifest.py'), cf, out, '--meta', mf, *extra_args],
                               capture_output=True, text=True, env=env, timeout=120)
            raw = open(out).read() if os.path.exists(out) else ''
            results.append({'rc': r.returncode, 'log': r.stdout + r.stderr, 'man': json.loads(raw) if raw else None, 'raw': raw,
                            'ledger': [json.loads(l) for l in open(ledger)] if os.path.exists(ledger) else [],
                            'written': sorted(os.path.relpath(os.path.join(p, f), d) for p, _, fs in os.walk(d) for f in fs
                                              if f not in ('cands.json', 'meta.json', 'picks.jsonl.lock'))})
        return results
    finally:
        shutil.rmtree(d, ignore_errors=True)

LAST = {}  # raw manifest text and ledger rows of the last build()
def build(cands, *extra_args):
    r = build_runs([(cands, extra_args)])[0]
    LAST.update(raw=r['raw'], ledger=r['ledger'])
    return r['rc'], r['log'], r['man'], r['written']

def ledger_row(eid):
    rows = [x for x in LAST.get('ledger') or [] if x.get('event_id') == eid]
    return rows[0] if len(rows) == 1 else {}

def refused(label, cands, why, *args):
    rc, log, man, written = build(cands, *args)
    check(f'{label}: refused (exit nonzero)', rc != 0, log)
    check(f'{label}: refused for the stated reason ({why})', why in log, log)
    check(f'{label}: nothing written (no manifest, ledger or prod mirror)', man is None and written == [], written)

CLEAN = cand(1, 'Chiefs ML', 'football/nfl', 'Denver Broncos', 'Kansas City Chiefs', '10u', model=74.0)  # 70-79 with gross >= 3c: the 10u rung

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
refused('a Vegas team with its league written in capitals (the page builder holds it too)',
        [cand(1, 'Kings ML', 'Hockey/NHL ', 'Los Angeles Kings', 'Golden Knights', side='away')], 'Vegas team')
refused('UNLV in a college league the nickname table does not list', [cand(1, 'Rebels ML', 'baseball/college-baseball', 'UNLV Rebels', 'Fresno State Bulldogs')],
        'Vegas team')
refused('one Vegas pick refuses the whole card', [CLEAN, cand(2, 'Raiders ML', 'football/nfl', 'Denver Broncos', 'Las Vegas Raiders')], 'Raiders ML')

# nicknames only inside their own league
rc, log, man, _ = build([cand(1, 'Red Raiders ML', 'football/college-football', 'Baylor Bears', 'Texas Tech Red Raiders'),
                         cand(2, 'Purple Aces ML', 'basketball/mens-college-basketball', 'Murray State Racers', 'Evansville Purple Aces')])
check('Texas Tech Red Raiders (CFB) and Evansville Purple Aces (NCAAB) are not Vegas teams', rc == 0 and man and len(man['picks']) == 2, log)

# the J-096 ladder
for u in ('6u', '7u', '8u', '2u', '20u', 'max'):
    refused(f'units {u} off the ladder', [cand(1, 'Chiefs ML', 'football/nfl', 'Denver Broncos', 'Kansas City Chiefs', u)], 'not on the J-096 ladder')
# each at the J-096 rung of its fair (build_manifest also refuses a size that is not its pick's rung: test_build_manifest_bars.py)
rc, log, man, _ = build([cand(i, f'Team{i} ML', 'hockey/nhl', f'Away{i} Club', f'Home{i} Club', u, model=m)
                         for i, (u, m) in enumerate((('5u', 66.0), ('10u', 74.0), ('15u', 84.0), ('100u', 92.0)), 1)])
check('5u, 10u, 15u and 100u build', rc == 0 and man and [p['units'] for p in man['picks']] == ['5u', '10u', '15u', '100u'], log)
check('a card that breaks no rule carries no owner_directive', bool(man) and all('owner_directive' not in p for p in man['picks']), man and man['picks'][0])

# owner ruling 2026-10-02: no owner directive passes a pick - the override, per pick and on the command
# line, is gone, and giving either one is an error (nothing written), whatever the card
RAIDERS = cand(1, 'Raiders ML', 'football/nfl', 'Denver Broncos', 'Las Vegas Raiders')
SIX_U = cand(2, 'Bills ML', 'football/nfl', 'New England Patriots', 'Buffalo Bills', '6u')
DIRECTIVE = {'rules': ['vegas', 'units'], 'words': WORDS, 'at': '2099-10-04T15:00:00Z'}
for label, c in (('a Vegas pick', RAIDERS), ('a 6u pick', SIX_U), ('a pick that breaks no rule', CLEAN)):
    refused(f'a per-pick owner_directive on {label} is an error', [dict(c, owner_directive=DIRECTIVE)], 'owner_directive is not accepted')
    rc, log, man, written = build([dict(c, owner_directive=DIRECTIVE)])
    check(f'that refusal ({label}) names the hard gates and does not echo his words', 'hard gates' in log and leaked(log, WORDS) == [],
          [log[-200:], leaked(log, WORDS)])
for label, cands in (('a Vegas pick', [RAIDERS]), ('a 6u pick', [CLEAN, SIX_U]), ('a card that breaks no rule', [CLEAN])):
    for form in (['--owner-directive', json.dumps({'num': cands[-1]['num'], 'rules': ['vegas', 'units'], 'words': WORDS})],
                 ['--owner-directive=' + json.dumps({'num': cands[-1]['num'], 'rules': ['vegas', 'units'], 'words': WORDS})],
                 ['--owner-directive', 'yes do it']):
        refused(f'--owner-directive ({form[0][:19]}...) with {label} is an error', cands, '--owner-directive does not exist', *form)
        rc, log, man, written = build(cands, *form)
        check(f'that refusal ({label}) names the hard gates and does not echo his words', 'hard gates' in log and leaked(log, WORDS) == [],
              [log[-200:], leaked(log, WORDS)])
rc, log, man, written = build([RAIDERS, SIX_U])
check('a Vegas pick and a 6u pick refuse together, each named, with no override offered',
      rc != 0 and 'Raiders ML' in log and 'Bills ML' in log and 'hard gates' in log and 'directive' not in log.lower() and written == [], log)
rc, log, man, _ = build([CLEAN])
check('a clean card writes no owner_directive on its manifest pick or its ledger row',
      rc == 0 and man and 'owner_directive' not in LAST['raw'] and all('owner_directive' not in r for r in LAST['ledger']), log)
SRC = open(os.path.join(HERE, 'build_manifest.py')).read()
check('build_manifest.py carries no override path (no directive parser, no public record, no private words)',
      all(x not in SRC for x in ('def owner_directive', 'def public_directive', 'def directive_ref', "'words'")),
      [x for x in ('def owner_directive', 'def public_directive', 'def directive_ref', "'words'") if x in SRC])

# a pick num names one pick on the card
refused('two candidates sharing a pick num', [CLEAN, cand(1, 'Bills ML', 'football/nfl', 'New England Patriots', 'Buffalo Bills', eid='401990777')],
        'pick num')

# the Vegas rule is about teams: individual sports skip it, every other league keeps it
rc, log, man, _ = build([cand(1, 'Kyle Larson to win', 'racing/nascar-premier', 'South Point 400', 'Las Vegas Motor Speedway')])
check('a NASCAR race at Las Vegas Motor Speedway is not a Vegas team pick', rc == 0 and man and len(man['picks']) == 1, log)
refused('an unlisted league keeps the Vegas rule (fails closed)', [cand(1, 'Cannons ML', 'lacrosse/pll', 'Las Vegas Desert Dogs', 'Boston Cannons')],
        'Vegas team')

# the card date: the builder's _card_date_of (most common PT game date), not the first candidate's date
def _record_final():
    import importlib.util
    spec = importlib.util.spec_from_file_location('record_final_for_owner_rules', os.path.join(HERE, 'record_final.py'))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
RF = _record_final()
LATE_FIRST = [cand(1, 'Sharks ML', 'hockey/nhl', 'Anaheim Ducks', 'San Jose Sharks', commence='2099-10-03T07:30Z', date='2099-10-03'),  # 00:30 PT Oct 3
              cand(2, 'Rangers ML', 'hockey/nhl', 'Boston Bruins', 'New York Rangers', commence='2099-10-02T23:00Z', date='2099-10-02'),
              cand(3, 'Kings ML', 'hockey/nhl', 'Seattle Kraken', 'Los Angeles Kings', commence='2099-10-03T02:00Z', date='2099-10-02')]
rc, log, man, _ = build(LATE_FIRST)
check('a card whose first-listed pick starts after PT midnight is dated by its most common PT game date (Oct 2)',
      rc == 0 and man and man['date'] == '2099-10-02' and man['date_label'] == 'Friday, Oct 2', (man or {}).get('date') or log)
check('the manifest date is the one record_final files the card under', bool(man) and RF.card_date_of(man) == man['date'],
      man and RF.card_date_of(man))
refused('a card with no timezone-aware commence cannot be dated', [cand(1, 'Chiefs ML', 'football/nfl', 'Denver Broncos', 'Kansas City Chiefs',
        commence='2099-10-04T20:25')], 'card date')

# posted_at: a production card records when it was posted (UTC ISO); the builder prefers it, so a
# late card says "after start" for a game that began before it instead of claiming a lock
def utc(s):
    try:
        return datetime.datetime.fromisoformat(str(s).replace('Z', '+00:00')) if re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', str(s)) else None
    except ValueError:
        return None
t0 = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
LATE_CARD = cand(1, 'Chiefs ML', 'football/nfl', 'Denver Broncos', 'Kansas City Chiefs', commence='2020-10-04T17:00Z')  # began before the build
rc, log, man, _ = build([LATE_CARD])
t1 = datetime.datetime.now(datetime.timezone.utc)
pa = utc((man or {}).get('posted_at'))
check('a production card records posted_at as UTC ISO (YYYY-MM-DDTHH:MM:SSZ) at build time', rc == 0 and pa is not None and t0 <= pa <= t1,
      (man or {}).get('posted_at') or log)
check('posted_at of a late card is after its game began (the builder says "after start", never "locked")',
      pa is not None and pa >= utc('2020-10-04T17:00:00Z'), (man or {}).get('posted_at'))
rc, log, man, _ = build([CLEAN], '--preview')
check('a preview card carries no posted_at', rc == 0 and man is not None and 'posted_at' not in man, man and man.get('posted_at'))
rc, log, man, _ = build([])
check('an empty card carries no posted_at (no pick to lock; its time must not reach the last card\'s game pages)',
      rc == 0 and man is not None and man['picks'] == [] and 'posted_at' not in man, man and man.get('posted_at') or log)
BILLS = cand(2, 'Bills ML', 'football/nfl', 'New England Patriots', 'Buffalo Bills')
g1, g2, g3 = build_runs([([CLEAN], ()), ([CLEAN], (), 1.2), ([CLEAN, BILLS], (), 1.2)])
p1, p2, p3 = (utc((g['man'] or {}).get('posted_at')) for g in (g1, g2, g3))
check('a regeneration keeps posted_at (never restamped)', p1 is not None and p2 == p1, [g['man'] and g['man'].get('posted_at') for g in (g1, g2)])
check('a pick added later moves posted_at to that pick\'s own lock', p3 is not None and p1 is not None and p3 > p1
      and p3 == datetime.datetime.fromisoformat(g3['man']['picks'][1]['card_ts']).astimezone(datetime.timezone.utc)
      and g3['man']['picks'][0]['card_ts'] == g1['man']['picks'][0]['card_ts'], [g3['man'] and g3['man'].get('posted_at'), g3['log'][-300:]])

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
