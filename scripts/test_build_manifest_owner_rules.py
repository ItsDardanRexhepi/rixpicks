#!/usr/bin/env python3
"""Owner-rules fixture for scripts/build_manifest.py (RixPicks daily-card runbook 2.5 and 2.8).
 - Vegas: "never gamble on or against any Vegas teams ever" / "Exclude A's going forward from
   today too". A pick on or against the Raiders (NFL), Golden Knights (NHL), Aces (WNBA),
   Athletics/A's (MLB) or UNLV (college) refuses closed - exit nonzero, nothing written (no
   manifest, no ledger, no prod mirror). A nickname counts only inside its own league: Texas Tech
   Red Raiders (CFB) and Evansville Purple Aces (NCAAB) are not Vegas teams.
 - Units: only the J-096 ladder, 5u, 10u, 15u, 100u.
 - Either passes only on an explicit owner directive naming the rule with his verbatim words, on
   the candidate row or via --owner-directive. manifest.json is served publicly, so the manifest pick
   records only owner_directive {rules, via, ref} (ref = the first 12 hex digits of sha256 of his
   words); his verbatim words go only to the private picks ledger row (RIX_PICKS_LEDGER), beside the
   same ref. No word of his directive may appear anywhere in the written manifest, and no refusal
   echoes his words.
 - The Vegas rule is about teams: it skips the individual sports (racing, golf, tennis, MMA, boxing),
   so a NASCAR race at Las Vegas Motor Speedway builds; any other league keeps the rule.
 - A pick num names one pick (a CLI directive is keyed by it): two candidates sharing a num refuse.
 - The card date is the builder's _card_date_of rule (the most common PT game date across the
   picks, which record_final.card_date_of also uses), never the first-listed candidate's date.
 - A production card records posted_at (UTC ISO): the newest card_ts of its picks, which is the
   build time for a new card and is never restamped by a regeneration (a pick added later moves it
   to that pick's lock, so no pick claims a lock from before it was carded). The page builder
   prefers posted_at and says "after start" for a game that began before it. A preview has none.
 The page builder carries no such gate (it renders whatever card has landed): see
 test_card_shapes_build.py, which builds a card with an Aces pick.
Run: python3 scripts/test_build_manifest_owner_rules.py"""
import copy, datetime, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time

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

# distinctive tokens: none of them occurs anywhere else in a built manifest, so any hit is a leak
WORDS = "Quokka trellis, marzipan zanzibar okapi"
WORDS2 = "Pangolin harpsichord, kumquat gazebo"
def ref_of(words):
    return hashlib.sha256(words.encode('utf-8')).hexdigest()[:12]
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

# owner directives: per pick and on the command line. The public manifest pick records {rules, via,
# ref}; his verbatim words go only to the private ledger row, beside the same ref.
rc, log, man, _ = build([dict(cand(1, 'Raiders ML', 'football/nfl', 'Denver Broncos', 'Las Vegas Raiders'),
                              owner_directive={'rules': ['vegas'], 'words': WORDS, 'at': '2099-10-04T15:00:00Z'})])
check('a per-pick owner directive naming the Vegas rule passes', rc == 0 and man is not None, log)
check('the manifest pick records the directive as rules, via and ref only (no words, no time)',
      (man or {'picks': [{}]})['picks'][0].get('owner_directive') == {'rules': ['vegas'], 'via': 'candidate', 'ref': ref_of(WORDS)},
      (man or {'picks': [{}]})['picks'][0].get('owner_directive'))
check('no word of his directive appears anywhere in the written manifest', bool(LAST['raw']) and leaked(LAST['raw'], WORDS) == [],
      leaked(LAST['raw'], WORDS))
check('the private ledger row carries his verbatim words beside the same ref',
      ledger_row('401990001').get('owner_directive') == {'rules': ['vegas'], 'via': 'candidate', 'ref': ref_of(WORDS),
                                                         'words': WORDS, 'at': '2099-10-04T15:00:00Z'},
      ledger_row('401990001').get('owner_directive'))
check('the build log does not print his words', leaked(log, WORDS) == [], leaked(log, WORDS))
refused('a directive for the units rule does not cover a Vegas pick',
        [dict(cand(1, 'Raiders ML', 'football/nfl', 'Denver Broncos', 'Las Vegas Raiders'), owner_directive={'rules': ['units'], 'words': WORDS})],
        'Vegas team')
refused('a directive without his words is no directive',
        [dict(cand(1, 'Raiders ML', 'football/nfl', 'Denver Broncos', 'Las Vegas Raiders'), owner_directive={'rules': ['vegas'], 'words': '  '})],
        'verbatim words')
rc, log, man, _ = build([CLEAN, cand(2, 'Bills ML', 'football/nfl', 'New England Patriots', 'Buffalo Bills', '6u')],
                        '--owner-directive', json.dumps({'num': 2, 'rules': ['units'], 'words': WORDS}))
check('a CLI owner directive naming the units rule passes a 6u pick', rc == 0 and man is not None, log)
check('the CLI directive is recorded on that pick only, as rules, via and ref',
      man is not None and man['picks'][1].get('owner_directive') == {'rules': ['units'], 'via': 'cli', 'ref': ref_of(WORDS)}
      and 'owner_directive' not in man['picks'][0], man and [p.get('owner_directive') for p in man['picks']])
check('no word of a CLI directive appears in the written manifest', bool(LAST['raw']) and leaked(LAST['raw'], WORDS) == [],
      leaked(LAST['raw'], WORDS))
check('the CLI directive\'s words sit on that pick\'s ledger row only, beside the same ref',
      ledger_row('401990002').get('owner_directive') == {'rules': ['units'], 'via': 'cli', 'ref': ref_of(WORDS), 'words': WORDS}
      and 'owner_directive' not in ledger_row('401990001'), [ledger_row(e).get('owner_directive') for e in ('401990001', '401990002')])
rc, log, man, written = build([CLEAN], '--owner-directive', json.dumps({'rules': ['units'], 'words': WORDS}))
check('a CLI directive without a num is refused, nothing written', rc != 0 and man is None and written == [], log)
check('that refusal does not echo his words', leaked(log, WORDS) == [], leaked(log, WORDS))

# re-runs: the same directive is idempotent; different words for a published pick never fork his record
RAIDERS = cand(1, 'Raiders ML', 'football/nfl', 'Denver Broncos', 'Las Vegas Raiders')
r1, r2, r3 = build_runs([([dict(RAIDERS, owner_directive={'rules': ['vegas'], 'words': WORDS})], ()),
                         ([dict(RAIDERS, owner_directive={'rules': ['vegas'], 'words': WORDS})], ()),
                         ([dict(RAIDERS, owner_directive={'rules': ['vegas'], 'words': WORDS2})], ())])
check('a re-run with the same directive appends no ledger row and keeps the ref',
      r1['rc'] == 0 and r2['rc'] == 0 and len(r2['ledger']) == 1 and r2['ledger'] == r1['ledger']
      and (r2['man'] or {}).get('picks') == (r1['man'] or {}).get('picks'), [r1['log'], r2['log']])
check('a re-run with other words for a published pick refuses closed (his recorded words never change)',
      r3['rc'] != 0 and 'refusing to fork' in r3['log'] and r3['ledger'] == r2['ledger'] and r3['raw'] == r2['raw'], r3['log'])
check('that refusal names refs, never words', leaked(r3['log'], WORDS, WORDS2) == [], leaked(r3['log'], WORDS, WORDS2))
refused('a CLI directive for a pick that is not on the card', [CLEAN], 'not in the candidates',
        '--owner-directive', json.dumps({'num': 9, 'rules': ['units'], 'words': WORDS}))
refused('a CLI directive that is not JSON', [CLEAN], 'needs a JSON object', '--owner-directive', 'yes do it')

# a pick num names one pick: a CLI directive keyed by num must never cover two picks
refused('two candidates sharing a pick num', [CLEAN, cand(1, 'Bills ML', 'football/nfl', 'New England Patriots', 'Buffalo Bills', eid='401990777')],
        'pick num')
refused('a CLI directive for a num two candidates share', [cand(2, 'Bills ML', 'football/nfl', 'New England Patriots', 'Buffalo Bills', '6u'),
        cand(2, 'Jets ML', 'football/nfl', 'Miami Dolphins', 'New York Jets', '6u', eid='401990778')], 'pick num',
        '--owner-directive', json.dumps({'num': 2, 'rules': ['units'], 'words': WORDS}))
refused('a CLI directive whose num is true (not a pick num)', [cand(1, 'Bills ML', 'football/nfl', 'New England Patriots', 'Buffalo Bills', '6u')],
        'must carry num', '--owner-directive', json.dumps({'num': True, 'rules': ['units'], 'words': WORDS}))

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
BILLS = cand(2, 'Bills ML', 'football/nfl', 'New England Patriots', 'Buffalo Bills')
g1, g2, g3 = build_runs([([CLEAN], ()), ([CLEAN], (), 1.2), ([CLEAN, BILLS], (), 1.2)])
p1, p2, p3 = (utc((g['man'] or {}).get('posted_at')) for g in (g1, g2, g3))
check('a regeneration keeps posted_at (never restamped)', p1 is not None and p2 == p1, [g['man'] and g['man'].get('posted_at') for g in (g1, g2)])
check('a pick added later moves posted_at to that pick\'s own lock', p3 is not None and p1 is not None and p3 > p1
      and p3 == datetime.datetime.fromisoformat(g3['man']['picks'][1]['card_ts']).astimezone(datetime.timezone.utc)
      and g3['man']['picks'][0]['card_ts'] == g1['man']['picks'][0]['card_ts'], [g3['man'] and g3['man'].get('posted_at'), g3['log'][-300:]])

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
