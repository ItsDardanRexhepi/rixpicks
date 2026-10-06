#!/usr/bin/env python3
"""The Vegas rule reads team identity by league, never a word inside some longer name (owner rule
L-VEGAS-GATE-001, Sep 25: "never gamble on or against any Vegas teams ever", "Exclude A's going forward from
today too"; a hard gate under owner ruling 2026-10-02 (4)).
A team string (game.away, game.home, the team part of the pick name) is a Las Vegas team when, read case-,
space- and punctuation-blind, it is exactly one of its league's Vegas team names (full name, former name,
nickname or abbreviation: NFL Las Vegas Raiders, NHL Vegas Golden Knights, WNBA Las Vegas Aces, MLB
Athletics/A's), or it carries 'Las Vegas', 'Vegas' or 'UNLV' as whole words (a team named for Las Vegas, or
UNLV, in any team league). A nickname or abbreviation never counts inside a longer name or in another league:
'Texas Tech Red Raiders' filed under football/nfl is no Vegas team, 'LV' is the Raiders only in the NFL. A
free-form pick name that fits none of the card's name shapes keeps the word rule, so it is never weaker.
 - The rule is one contract block carried byte for byte by build_manifest.py and both page-builder twins; the
   block is checked identical, and one case table (true positives, near-miss names, other leagues, individual
   sports) runs through each copy's own code.
 - End to end, both twins hold a card with an abbreviated Vegas team (exit 3, nothing written) and build a card
   whose only "Vegas word" is a near-miss name in the wrong league.
Builds run in a throwaway tree with the network sent to a dead proxy.
Run: python3 scripts/test_vegas_rule_exact.py"""
import ast, copy, json, os, re, shutil, subprocess, sys, tempfile

SD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SD)
TWINS = [os.path.join(SD, 'build_gh_page_v2.py'), os.path.join(SD, '_build_nocanon_v2.py')]
MANIFEST_BUILDER = os.path.join(SD, 'build_manifest.py')
BEGIN, END = '# >>> vegas-rule contract copy', '# <<< vegas-rule contract copy'
DEAD = 'http://127.0.0.1:9'
failures = 0

def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or detail == '' else '  [' + str(detail)[-400:] + ']'))
    if not ok:
        failures += 1

def block_of(path):
    src = open(path, encoding='utf-8').read()
    if src.count(BEGIN) != 1 or src.count(END) != 1:
        return None
    return src[src.index(BEGIN):src.index(END) + len(END)]

def rule_of(path):
    """(league, [(field, value)]) -> hit or None, from this file's own contract block."""
    blk = block_of(path)
    if blk is None:
        return None
    ns = {'re': re}
    exec(compile(blk, path, 'exec'), ns)
    return ns.get('vegas_hit_fields')

def manifest_vegas_hit():
    """build_manifest.vegas_hit, lifted out by AST with the contract block it calls."""
    blk = block_of(MANIFEST_BUILDER)
    if blk is None:
        return None
    ns = {'re': re}
    exec(compile(blk, MANIFEST_BUILDER, 'exec'), ns)
    for node in ast.walk(ast.parse(open(MANIFEST_BUILDER, encoding='utf-8').read())):
        if isinstance(node, ast.FunctionDef) and node.name == 'vegas_hit':
            exec(compile(ast.Module(body=[node], type_ignores=[]), MANIFEST_BUILDER, 'exec'), ns)
            return ns['vegas_hit']
    return None

# (label, league, pick name, away, home, Vegas?)
CASES = [
    # true positives: on and against, full names, nicknames, abbreviations, the name alone
    ('NFL Raiders ML (on)', 'football/nfl', 'Raiders ML', 'Denver Broncos', 'Las Vegas Raiders', True),
    ('NFL Broncos at the Raiders (against)', 'football/nfl', 'Broncos ML', 'Denver Broncos', 'Las Vegas Raiders', True),
    ('NFL abbreviation LV', 'football/nfl', 'Broncos -3', 'DEN', 'LV', True),
    ('NFL former name Oakland Raiders', 'football/nfl', 'Chiefs ML', 'Oakland Raiders', 'Kansas City Chiefs', True),
    ('NFL Raiders spread name only (game teams unreadable)', 'football/nfl', 'Raiders +3.5', 'Team A', 'Team B', True),
    ('NHL Golden Knights game', 'hockey/nhl', 'Kings ML', 'Los Angeles Kings', 'Vegas Golden Knights', True),
    ('NHL abbreviation VGK', 'hockey/nhl', 'Kings ML', 'LA', 'VGK', True),
    ('NHL nickname only, league in capitals', 'Hockey/NHL ', 'Kings ML', 'Los Angeles Kings', 'Golden Knights', True),
    ('NHL "Vegas ML" by name', 'hockey/nhl', 'Vegas ML', 'Team A', 'Team B', True),
    ('NHL total named on the Golden Knights', 'hockey/nhl', 'Golden Knights-Kings Over 5.5', 'Team A', 'Team B', True),
    ('WNBA Aces game', 'basketball/wnba', 'Fever ML', 'Indiana Fever', 'Las Vegas Aces', True),
    ('WNBA abbreviation LVA', 'basketball/wnba', 'Fever +4.5', 'IND', 'LVA', True),
    ('WNBA Aces spread name', 'basketball/wnba', 'Aces -4.5', 'Indiana Fever', 'Team B', True),
    ('WNBA prop in an Aces game', 'basketball/wnba', "A'ja Wilson over 24.5 points", 'Indiana Fever', 'Las Vegas Aces', True),
    ('MLB Athletics (ESPN name)', 'baseball/mlb', 'Astros ML', 'Athletics', 'Houston Astros', True),
    ("MLB A's in the pick name (curly apostrophe)", 'baseball/mlb', 'A\u2019s ML', 'Sacramento Club', 'Houston Astros', True),
    ('MLB abbreviation ATH', 'baseball/mlb', 'Astros ML', 'ATH', 'HOU', True),
    ('MLB former name Oakland Athletics', 'baseball/mlb', 'Astros ML', 'Oakland Athletics', 'Houston Astros', True),
    ('CFB UNLV game', 'football/college-football', 'Under 55.5', 'UNLV Rebels', 'Boise State Broncos', True),
    ('college baseball UNLV (a league with no table entry)', 'baseball/college-baseball', 'Rebels ML', 'UNLV Rebels', 'Fresno State Bulldogs', True),
    ('USL team named for Las Vegas', 'soccer/usa.usl.1', 'Rising ML', 'Las Vegas Lights FC', 'Phoenix Rising FC', True),
    ('a free-form name keeps the word rule', 'football/nfl', 'Raiders to win the AFC West', 'Denver Broncos', 'Kansas City Chiefs', True),
    # near-miss names: a Vegas nickname inside another team's name, in the nickname's league or any other
    ('Texas Tech Red Raiders filed under the NFL', 'football/nfl', 'Red Raiders ML', 'Baylor Bears', 'Texas Tech Red Raiders', False),
    ('Texas Tech Red Raiders in CFB', 'football/college-football', 'Red Raiders ML', 'Baylor Bears', 'Texas Tech Red Raiders', False),
    ('Evansville Purple Aces filed under the WNBA', 'basketball/wnba', 'Purple Aces ML', 'Murray State Racers', 'Evansville Purple Aces', False),
    ('Evansville Purple Aces in NCAAB', 'basketball/mens-college-basketball', 'Purple Aces ML', 'Murray State Racers', 'Evansville Purple Aces', False),
    ('UCF Golden Knights filed under the NHL', 'hockey/nhl', 'UCF ML', 'Cincinnati Bearcats', 'UCF Golden Knights', False),
    ('UCF Golden Knights in CFB (the NHL nickname is NHL only)', 'football/college-football', 'Golden Knights ML', 'Cincinnati Bearcats', 'UCF Golden Knights', False),
    ('a Vegas abbreviation in a league where it names no team', 'basketball/nba', 'Kings ML', 'Sacramento Kings', 'LV', False),
    ('Raiders nickname outside the NFL', 'basketball/mens-college-basketball', 'Raiders ML', 'Wright State Raiders', 'Detroit Mercy Titans', False),
    ('Athletics outside MLB', 'soccer/usa.1', 'Athletics ML', 'Philadelphia Union', 'Team B', False),
    # clean cards and the individual sports
    ('clean NFL game', 'football/nfl', 'Bills ML', 'New England Patriots', 'Buffalo Bills', False),
    ('bare total, clean game', 'football/nfl', 'Under 41.5', 'Denver Broncos', 'Kansas City Chiefs', False),
    ('MLB prop, clean game', 'baseball/mlb', 'Yordan Alvarez over 1.5 hits', 'Houston Astros', 'Seattle Mariners', False),
    ('NASCAR at Las Vegas Motor Speedway (no teams)', 'racing/nascar-premier', 'Kyle Larson to win', 'South Point 400', 'Las Vegas Motor Speedway', False),
    ('UFC Vegas card (no teams)', 'mma/ufc', 'Rosas ML', 'Raul Rosas Jr.', 'UFC Vegas 121', False),
]

blocks = {p: block_of(p) for p in TWINS + [MANIFEST_BUILDER]}
check('the Vegas contract block is present exactly once in build_manifest.py and both twins',
      all(b is not None for b in blocks.values()), [os.path.basename(p) for p, b in blocks.items() if b is None])
check('the three copies of the Vegas contract block are byte-identical', len({b for b in blocks.values()}) == 1)

rules = {os.path.basename(p): rule_of(p) for p in TWINS + [MANIFEST_BUILDER]}
vh = manifest_vegas_hit()
for label, lg, name, away, home, want in CASES:
    for tag, fn in rules.items():
        got = fn(lg, (('name', name), ('away', away), ('home', home))) if fn else 'no rule'
        check(f'{tag}: {label}: {"Vegas" if want else "not Vegas"}', (got is not None and got != 'no rule') if want else got is None, got)
    got = vh({'espn_league': lg, 'name': name, 'away': away, 'home': home}) if vh else 'no vegas_hit'
    check(f'build_manifest.vegas_hit: {label}: {"Vegas" if want else "not Vegas"}', (got is not None and got != 'no vegas_hit') if want else got is None, got)

# end to end through both twins: an abbreviated Vegas team holds the card; a near-miss name builds
def build(builder, manifest):
    d = tempfile.mkdtemp(prefix='rp-vegas-')
    try:
        os.makedirs(os.path.join(d, 'scripts')); os.makedirs(os.path.join(d, 'slates'))
        shutil.copy(builder, os.path.join(d, 'scripts', 'build_gh_page_v2.py'))
        for f in ('index_v2.js', 'index_v2.css', 'game_page_template.html', 'team_page_template.html', 'poly_us.py'):
            shutil.copy(os.path.join(SD, f), os.path.join(d, 'scripts', f))
        for f in ('feed_arbiter.js', 'feed_registry.json', 'config_leagues.json'):
            shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
        json.dump(manifest, open(os.path.join(d, 'manifest.json'), 'w'), indent=1)
        json.dump([], open(os.path.join(d, 'slates', 'odds_prefill.json'), 'w'))
        before = {os.path.relpath(os.path.join(p, f), d): os.path.getmtime(os.path.join(p, f)) for p, _, fs in os.walk(d) for f in fs}
        env = dict(os.environ, RP_REFRESH='1', http_proxy=DEAD, https_proxy=DEAD, HTTP_PROXY=DEAD, HTTPS_PROXY=DEAD, NO_PROXY='', no_proxy='')
        r = subprocess.run([sys.executable, os.path.join(d, 'scripts', 'build_gh_page_v2.py'), 'manifest.json', 'index.html'],
                           cwd=d, env=env, capture_output=True, text=True, timeout=600)
        after = {os.path.relpath(os.path.join(p, f), d): os.path.getmtime(os.path.join(p, f)) for p, _, fs in os.walk(d) for f in fs}
        return r.returncode, r.stdout + r.stderr, sorted(f for f, t in after.items() if before.get(f) != t and '__pycache__' not in f)
    finally:
        shutil.rmtree(d, ignore_errors=True)

BASE = {'date': '2099-10-04', 'date_label': 'Sunday, Oct 4', 'updated': 'Oct 4, 8:42 AM PT', 'record': '21-11',
        'units_pl': '+4.76u', 'units_ledger': None, 'yesterday': '', 'status_note': '', 'preview': False, 'parlay': None}
def pick(num, name, league, lab, away, home, side='home'):
    return {'num': num, 'name': name, 'market_class': 'ml', 'sub': 'fixture - model 66.0', 'odds': '-150', 'card_american': -150,
            'units': '5u', 'side': side, 'game': {'away': away, 'home': home, 'commence': '2099-10-04T20:25Z', 'eid': f'FIX-{num}'},
            'espn_league': league, 'league': lab, 'best_book': 'Kalshi', 'card_source': 'Kalshi ask at lock'}
def card(picks):
    m = copy.deepcopy(BASE); m['picks'] = picks; return m

for B in TWINS:
    tag = os.path.basename(B)
    for label, p in (('NFL game at "LV"', pick(1, 'Broncos ML', 'football/nfl', 'NFL', 'DEN', 'LV', side='away')),
                     ('NHL game with "VGK"', pick(1, 'Kings ML', 'hockey/nhl', 'NHL', 'LA', 'VGK', side='away'))):
        rc, log, written = build(B, card([p]))
        check(f'{tag}: {label}: the card is held (exit 3, the Vegas rule named), nothing written',
              rc == 3 and 'BUILD FAILED' in log and 'Las Vegas team' in log and written == [], (rc, log[-300:], written))
    rc, log, written = build(B, card([pick(1, 'Red Raiders ML', 'football/nfl', 'NFL', 'Baylor Bears', 'Texas Tech Red Raiders'),
                                      pick(2, 'UCF ML', 'hockey/nhl', 'NHL', 'Cincinnati Bearcats', 'UCF Golden Knights')]))
    check(f'{tag}: near-miss names filed under the NFL and NHL (Texas Tech Red Raiders, UCF Golden Knights): the card builds',
          rc == 0 and 'index.html' in written and 'Las Vegas team' not in log, (rc, log[-300:]))

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
