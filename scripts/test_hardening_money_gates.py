"""Money-gate hardening fixture (2026-10-13 ledger): one check per finding, each named for its id.
 - H-03: a bout (MMA, boxing) has no teams for the Vegas team rule to catch, so its VENUE is read. build_manifest
   refuses a bout candidate at a Las Vegas venue or with no venue given, and carries the venue onto the manifest
   pick; both page-builder twins hold a landed card with such a bout (not suspendable). The rule is one block
   carried byte for byte by build_manifest.py and both twins (RixPicksSystem engine/daily/bars.py is the source).
 - H-12: build_manifest writes the fragility it sized each pick at; the page builder holds units UNDER the exact
   rung the numbers clear (fragility 2 drops one rung, the tennis cap) as well as over it - exactly at the
   fragility the pick carries, and when it carries none, the rung at fragility 0 or the one rung lower.
 - H-13: build_manifest writes the fair at full precision (fair_c) and the page builder reads it before the
   sub-line's 'model X', which is rounded to 0.1c and could disagree with build_manifest at a rung boundary.
 - H-48b: build_manifest imports from its own checkout (no /home/sandbox path) and mirrors to this repo's
   manifest.json unless RIX_PROD_MANIFEST names the grading host's copy.
Builds run in throwaway trees with the network sent to a dead proxy.
Run: python3 scripts/test_hardening_money_gates.py"""
import copy, importlib.util, json, os, re, shutil, subprocess, sys, tempfile

from fixtures.card_contract import stamped, market, published_snapshot

SD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SD)
TWINS = [os.path.join(SD, 'build_gh_page_v2.py'), os.path.join(SD, '_build_nocanon_v2.py')]
BM = os.path.join(SD, 'build_manifest.py')
DEAD = 'http://127.0.0.1:9'
T0 = '2099-10-04T14:51:00Z'
failures = 0


def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or detail == '' else '  [' + str(detail)[-400:] + ']'))
    if not ok:
        failures += 1


# ------------------------------------------------------------------------------------------- the page builder
def build(builder, manifest):
    """Build manifest.json in a throwaway tree -> (rc, log, files written)."""
    d = tempfile.mkdtemp(prefix='rp-hard-mg-')
    try:
        os.makedirs(os.path.join(d, 'scripts')); os.makedirs(os.path.join(d, 'slates'))
        shutil.copy(builder, os.path.join(d, 'scripts', 'build_gh_page_v2.py'))
        for f in ('index_v2.js', 'index_v2.css', 'game_page_template.html', 'team_page_template.html', 'poly_us.py'):
            shutil.copy(os.path.join(SD, f), os.path.join(d, 'scripts', f))
        for f in ('feed_arbiter.js', 'feed_registry.json', 'config_leagues.json'):
            shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
        manifest = stamped(builder, manifest)
        json.dump(manifest, open(os.path.join(d, 'manifest.json'), 'w'), indent=1)
        published_snapshot(d, builder, manifest)
        json.dump([], open(os.path.join(d, 'slates', 'odds_prefill.json'), 'w'))
        before = {os.path.relpath(os.path.join(p, f), d): os.path.getmtime(os.path.join(p, f)) for p, _, fs in os.walk(d) for f in fs}
        env = dict(os.environ, RP_REFRESH='1', http_proxy=DEAD, https_proxy=DEAD, HTTP_PROXY=DEAD, HTTPS_PROXY=DEAD)
        r = subprocess.run([sys.executable, os.path.join(d, 'scripts', 'build_gh_page_v2.py'), 'manifest.json', 'index.html'],
                           cwd=d, env=env, capture_output=True, text=True, timeout=600)
        after = {os.path.relpath(os.path.join(p, f), d): os.path.getmtime(os.path.join(p, f)) for p, _, fs in os.walk(d) for f in fs}
        return r.returncode, r.stdout + r.stderr, sorted(f for f, t in after.items() if before.get(f) != t and '__pycache__' not in f)
    finally:
        shutil.rmtree(d, ignore_errors=True)


BASE = {'date': '2099-10-04', 'date_label': 'Sunday, Oct 4', 'updated': 'Oct 4, 8:42 AM PT', 'record': '21-11',
        'units_pl': '+4.76u', 'units_ledger': None, 'yesterday': '', 'status_note': '', 'preview': False, 'parlay': None}
LEAGUE = {'hockey/nhl': 'NHL', 'mma/ufc': 'UFC', 'boxing': 'BOXING', 'tennis/atp': 'ATP'}


def pick(num, name, league='hockey/nhl', away='A', home='B', units='5u', model=66.0, american=-150, **extra):
    p = {'num': num, 'name': name, 'market_class': 'ml', 'sub': f'fixture - model {model:.1f}', 'odds': f'{american:+d}',
         'card_american': american, 'units': units, 'side': 'home',
         'game': {'away': away, 'home': home, 'commence': '2099-10-04T20:25Z', 'eid': f'FIX-{num}'},
         'espn_league': league, 'league': LEAGUE[league], 'best_book': 'Kalshi', 'card_source': 'Kalshi ask at lock'}
    p = market(p)
    p.update(extra)
    return p


def card(picks, **kw):
    m = copy.deepcopy(BASE); m['picks'] = copy.deepcopy(picks); m.update(kw); return m


def held(rc, log, written, *words):
    return rc == 3 and 'BUILD FAILED' in log and written == [] and all(w in log for w in words)


def built(rc, written):
    return rc == 0 and 'index.html' in written


def bout(num, venue, city, league='mma/ufc'):
    p = pick(num, f'Fighter{num} ML', league, f'Opponent{num}', f'Fighter{num}')
    if venue is not None:
        p['game'].update(venue=venue, venue_city=city)
    return p


for B in TWINS:
    tag = os.path.basename(B)
    # H-03 ------------------------------------------------------------------------------------------------------
    for label, p in (('T-Mobile Arena, Las Vegas', bout(1, 'T-Mobile Arena', 'Las Vegas')),
                     ('UFC Apex (name only)', bout(1, 'UFC Apex', '')),
                     ('MGM Grand Garden Arena (name only)', bout(1, 'MGM Grand Garden Arena', '')),
                     ('a boxing card in Las Vegas', bout(1, 'Some Arena', 'Las Vegas', league='boxing'))):
        rc, log, written = build(B, card([p]))
        check(f'{tag}: test_h03 a bout at {label}: held (exit 3), nothing written',
              held(rc, log, written, 'Las Vegas rule, fights', 'Las Vegas'), (rc, log[-300:], written))
    rc, log, written = build(B, card([bout(1, None, None)]))
    check(f'{tag}: test_h03 a bout with no venue on the pick: held', held(rc, log, written, 'venue of this bout is not given'),
          (rc, log[-300:], written))
    rc, log, written = build(B, card([bout(1, 'Madison Square Garden', 'New York')]))
    check(f'{tag}: test_h03 a bout at Madison Square Garden, New York: builds', built(rc, written), (rc, log[-300:]))
    rc, log, written = build(B, card([pick(1, 'Devils ML')]))
    check(f'{tag}: test_h03 a team game is not read for a venue (no venue on an NHL pick): builds', built(rc, written), (rc, log[-300:]))

    # H-12 ------------------------------------------------------------------------------------------------------
    # 66c fair at a 60c Kalshi ask: 6c gross, 4c net after the 2c fee -> 6u; fragility 2 drops it to 5u
    rc, log, written = build(B, card([pick(1, 'Six ML', units='5u', fragility=0)]))
    check(f'{tag}: test_h12 6u numbers carded 5u at fragility 0: held, under the rung',
          held(rc, log, written, 'under the ladder rung 6u'), (rc, log[-300:], written))
    rc, log, written = build(B, card([pick(1, 'Six ML', units='5u', fragility=2)]))
    check(f'{tag}: test_h12 6u numbers carded 5u at fragility 2: builds', built(rc, written), (rc, log[-300:]))
    rc, log, written = build(B, card([pick(1, 'Six ML', units='6u', fragility=2)]))
    check(f'{tag}: test_h12 6u numbers carded 6u at fragility 2: held, over the rung 5u',
          held(rc, log, written, 'over the ladder rung 5u'), (rc, log[-300:], written))
    rc, log, written = build(B, card([pick(1, 'Six ML', units='5u')]))
    check(f'{tag}: test_h12 6u numbers carded 5u with no fragility on the pick (fragility 2 allows it): builds',
          built(rc, written), (rc, log[-300:]))
    # 77c fair at a 72c ask (-257): 5c gross, 3c net -> 9u; 8u at fragility 2; 7u is under both
    rc, log, written = build(B, card([pick(1, 'Nine ML', units='7u', model=77.0, american=-257)]))
    check(f'{tag}: test_h12 9u numbers carded 7u (a rung it cleared, but under its own): held',
          held(rc, log, written, 'under the ladder rung 9u'), (rc, log[-300:], written))
    rc, log, written = build(B, card([pick(1, 'Nine ML', units='9u', model=77.0, american=-257, fragility='2')]))
    check(f'{tag}: test_h12 a fragility that is not a whole number: held', held(rc, log, written, 'fragility'),
          (rc, log[-300:], written))
    t = pick(1, 'Player ML', 'tennis/atp', units='9u', model=77.0, american=-257, fragility=0)
    rc, log, written = build(B, card([t]))
    check(f'{tag}: test_h12 a 9u tennis pick (capped at 5u): held over the rung', held(rc, log, written, 'over the ladder rung'),
          (rc, log[-300:], written))

    # H-13 ------------------------------------------------------------------------------------------------------
    # 64c fair at a 60c ask is exactly 2c net; the sub-line prints 'model 64.0' for a 63.96c fair
    rc, log, written = build(B, card([pick(1, 'Edge ML', units='5u', model=64.0, fair_c=63.96)]))
    check(f'{tag}: test_h13 fair_c 63.96 under a sub-line that prints 64.0: held on the net it really has',
          held(rc, log, written, 'net 1.96c below the 2c floor'), (rc, log[-300:], written))
    rc, log, written = build(B, card([pick(1, 'Edge ML', units='5u', model=63.9, fair_c=64.0)]))
    check(f'{tag}: test_h13 fair_c 64.0 under a sub-line that prints 63.9: builds', built(rc, written), (rc, log[-300:]))


# --------------------------------------------------------------------------------------------- build_manifest
META = {'record': '21-11', 'units_pl': '+4.76u', 'units_ledger': None, 'yesterday': '', 'status_note': '', 'parlay': None}


def cand(num, name, model, units, cents=60, league='hockey/nhl', **extra):
    c = {'num': num, 'date': '2099-10-04', 'market_class': 'ml', 'name': name, 'side': 'home',
         'away': f'Away{num} Club', 'home': f'Home{num} Club', 'commence': '2099-10-04T23:00Z',
         'eid': str(401995000 + num), 'espn_league': league, 'units': units,
         'model': model, 'gross_c': 0, 'net_c': 0, 'sub_context': 'fixture',
         'kalshi': {'cents': cents, 'team': f'Home{num}', 'side': 'yes', 'ticker': 'KXFIX-99OCT04-%d' % num},
         'best_ask': {'venue': 'kalshi', 'price': cents, 'read_at': T0,
                      'compared': [{'venue': 'kalshi', 'price': cents, 'read_at': T0}]}}
    c.update(extra)
    return c


def bm(cands):
    d = tempfile.mkdtemp(prefix='rp-hard-bm-')
    try:
        os.makedirs(os.path.join(d, 'ledger')); os.makedirs(os.path.join(d, 'prod'))
        cf, mf, out = (os.path.join(d, x) for x in ('cands.json', 'meta.json', 'manifest.json'))
        env = dict(os.environ, PYTHONPATH=ROOT, RIX_PICKS_LEDGER=os.path.join(d, 'ledger', 'picks.jsonl'),
                   RIX_PROD_MANIFEST=os.path.join(d, 'prod', 'manifest.json'), http_proxy=DEAD, https_proxy=DEAD)
        json.dump(cands, open(cf, 'w')); json.dump(META, open(mf, 'w'))
        r = subprocess.run([sys.executable, BM, cf, out, '--meta', mf], capture_output=True, text=True, env=env, timeout=120)
        raw = open(out).read() if os.path.exists(out) else ''
        return r.returncode, r.stdout + r.stderr, (json.loads(raw) if raw else None)
    finally:
        shutil.rmtree(d, ignore_errors=True)


for label, extra in (('T-Mobile Arena, Las Vegas', {'venue': 'T-Mobile Arena', 'venue_city': 'Las Vegas'}),
                     ('UFC Apex', {'venue': 'UFC Apex'}), ('no venue', {})):
    rc, log, man = bm([cand(1, 'Fighter ML', 66.0, '6u', league='mma/ufc', **extra)])
    check(f'build_manifest: test_h03 a bout candidate at {label}: refused, nothing written',
          rc != 0 and man is None and 'Las Vegas rule, fights' in log, (rc, log[-300:]))
rc, log, man = bm([cand(1, 'Fighter ML', 66.0, '6u', league='mma/ufc', venue='Madison Square Garden', venue_city='New York')])
check('build_manifest: test_h03 a bout at Madison Square Garden builds and carries its venue onto the pick',
      rc == 0 and man and man['picks'][0]['game'].get('venue') == 'Madison Square Garden'
      and man['picks'][0]['game'].get('venue_city') == 'New York', (rc, log[-300:]))
rc, log, man = bm([cand(1, 'Six ML', 65.987654, '6u')])
p = (man or {}).get('picks', [{}])[0]
check('build_manifest: test_h13 the pick carries its fair at full precision (fair_c) beside the rounded sub-line',
      rc == 0 and p.get('fair_c') == 65.987654 and 'model 66.0' in p.get('sub', ''), (rc, log[-300:], p.get('fair_c')))
check('build_manifest: test_h12 the pick carries the fragility it was sized at (0 when the candidate gives none)',
      rc == 0 and p.get('fragility') == 0, p.get('fragility'))
rc, log, man = bm([cand(1, 'Six ML', 66.0, '5u', fragility=2)])
p = (man or {}).get('picks', [{}])[0]
check('build_manifest: test_h12 a fragility-2 pick carries fragility 2', rc == 0 and p.get('fragility') == 2, (rc, log[-300:]))

# H-03: the fights venue block is one contract, byte for byte, in build_manifest.py and both twins
blocks = []
for f in [BM] + TWINS:
    s = open(f).read()
    m = re.search(r'# >>> fights venue rule.*?# <<< fights venue rule', s, re.S)
    blocks.append(m.group(0) if m and s.count('# >>> fights venue rule') == 1 else None)
check('test_h03 the fights venue block is present once in build_manifest.py and both twins, byte for byte',
      blocks[0] is not None and all(b == blocks[0] for b in blocks), [b is not None for b in blocks])

# H-48b ------------------------------------------------------------------------------------------------------
src = open(BM).read()
check('build_manifest: test_h48b no /home/sandbox path is left in it', '/home/sandbox' not in src)
env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'RIX_PROD_MANIFEST')}
r = subprocess.run([sys.executable, '-c',
                    'import importlib.util,sys\n'
                    f'spec=importlib.util.spec_from_file_location("bm_h48b",{BM!r})\n'
                    'm=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\n'
                    'print(m.PROD_MANIFEST_PATH)\nprint(any("sandbox" in p for p in sys.path))'],
                   capture_output=True, text=True, env=env, cwd=tempfile.gettempdir(), timeout=60)
out = r.stdout.split()
check('build_manifest: test_h48b imports from its own checkout and mirrors to this repo\'s manifest.json by default',
      r.returncode == 0 and out[:2] == [os.path.join(ROOT, 'manifest.json'), 'False'], (r.returncode, r.stdout, r.stderr[-300:]))

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
