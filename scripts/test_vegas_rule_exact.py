#!/usr/bin/env python3
"""The Vegas rule (owner rule L-VEGAS-GATE-001, Sep 25: "never gamble on or against any Vegas teams ever",
"Exclude A's going forward from today too"; a hard gate under owner ruling 2026-10-02 (4)).
A pick is out when game.away, game.home or the pick name, read case-, space- and punctuation-blind, carries as
whole words anywhere in it 'Las Vegas', 'Vegas' or 'UNLV' (any team league), or one of its league's Vegas words:
the nickname (Raiders NFL, Golden Knights NHL, Aces WNBA, Athletics/A's MLB), a home city the team has played under,
or an abbreviation ('LV' is the Raiders in the NFL, the Aces in the WNBA, nothing in the NBA). That word rule is the
floor every earlier card was held to, and the rule never narrows it except by name: a non-Vegas team listed in
_VEGAS_NOT ('Texas Tech Red Raiders', 'Evansville Purple Aces', 'UCF Golden Knights') is blanked out before a
string is read, so that team filed under the nickname's league builds while any other Vegas word in the same
string still holds the pick.
 - The rule is one contract block carried byte for byte by build_manifest.py and both page-builder twins; the
   block is checked identical, and one case table (true positives, qualified names - 'Raiders 1H +3.5', "A's F5
   ML", 'Golden Knights (VGK)', "Sacramento A's" - near-miss names, other leagues, individual sports) runs through
   each copy's own code.
 - Floor: every case the word rule of origin/main held (a reference copy below) is still held, unless one of its
   strings names a _VEGAS_NOT team; each _VEGAS_NOT entry is a multi-word team name, never a Vegas word on its own,
   and never carries 'Vegas' or 'UNLV'.
 - End to end, both twins hold a card with an abbreviated, decorated or qualified Vegas team (exit 3, nothing
   written) and build a card whose only "Vegas word" is a near-miss name in the wrong league.
Builds run in a throwaway tree with the network sent to a dead proxy.
Run: python3 scripts/test_vegas_rule_exact.py"""
import ast, copy, json, os, re, shutil, subprocess, sys, tempfile

from fixtures.card_contract import stamped, market, published_snapshot

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
    # a Vegas word anywhere in a name or team string, qualifiers and prices attached (the word-rule floor)
    ('NFL first-half moneyline, game unreadable', 'football/nfl', 'Raiders 1H ML', None, None, True),
    ('NFL first-half spread, game unreadable', 'football/nfl', 'Raiders 1H +3.5', None, None, True),
    ('NFL future with a price', 'football/nfl', 'Raiders to win AFC West +500', None, None, True),
    ('NFL "win" with a price', 'football/nfl', 'Raiders win +150', None, None, True),
    ('NFL spread spelled out', 'football/nfl', 'Raiders spread +3.5', None, None, True),
    ('NFL team total', 'football/nfl', 'Raiders team total over 21.5', None, None, True),
    ('NFL prop with the team in brackets', 'football/nfl', 'Brock Bowers (Raiders) over 4.5 receptions', None, None, True),
    ('NFL prop with the abbreviation in brackets', 'football/nfl', 'Brock Bowers (LV) over 4.5 receptions', None, None, True),
    ('NFL game total written on both teams', 'football/nfl', 'Chiefs Raiders Over 45.5', None, None, True),
    ('NFL "@" moneyline name', 'football/nfl', 'Chiefs @ Raiders ML', None, None, True),
    ('NFL "vs" moneyline name', 'football/nfl', 'Chiefs vs Raiders ML', None, None, True),
    ('NFL "@" name on the abbreviation', 'football/nfl', 'Chiefs @ LV ML', None, None, True),
    ('NFL team string with the abbreviation attached', 'football/nfl', 'Chiefs ML', 'Kansas City Chiefs', 'Raiders (LV)', True),
    ('NFL team string with two cities', 'football/nfl', 'Chiefs ML', 'Kansas City Chiefs', 'Oakland/LV Raiders', True),
    ('NFL team string under a former city', 'football/nfl', 'Chiefs ML', 'Kansas City Chiefs', 'Los Angeles Raiders', True),
    ('NFL team string as the former city alone', 'football/nfl', 'Chiefs ML', 'Kansas City Chiefs', 'Oakland', True),
    ("MLB A's first five", 'baseball/mlb', "A's F5 ML", None, None, True),
    ('MLB Athletics first-five run line', 'baseball/mlb', 'Athletics F5 -0.5', None, None, True),
    ('MLB Athletics 1st 5', 'baseball/mlb', 'Athletics 1st 5 ML', None, None, True),
    ('MLB Athletics 1st 5 innings', 'baseball/mlb', 'Athletics 1st 5 innings ML', None, None, True),
    ('MLB Athletics team total', 'baseball/mlb', 'Athletics team total over 4.5', None, None, True),
    ("MLB Sacramento A's moneyline", 'baseball/mlb', "Sacramento A's ML", None, None, True),
    ("MLB team string Sacramento A's", 'baseball/mlb', 'Giants ML', "Sacramento A's", 'San Francisco Giants', True),
    ('MLB team string The Athletics', 'baseball/mlb', 'Giants ML', 'The Athletics', 'San Francisco Giants', True),
    ('MLB team string Athletics (SAC)', 'baseball/mlb', 'Giants ML', 'Athletics (SAC)', 'San Francisco Giants', True),
    ('MLB team string Athletics (ATH)', 'baseball/mlb', 'Giants ML', 'Athletics (ATH)', 'San Francisco Giants', True),
    ('MLB team string West Sacramento Athletics', 'baseball/mlb', 'Giants ML', 'West Sacramento Athletics', 'San Francisco Giants', True),
    ('MLB matchup on the abbreviation', 'baseball/mlb', 'Astros ML', 'HOU at ATH', None, True),
    ('MLB team string as the city alone', 'baseball/mlb', 'Giants ML', 'Sacramento', 'San Francisco Giants', True),
    ('NHL regulation moneyline', 'hockey/nhl', 'Golden Knights reg ML', None, None, True),
    ('NHL 60-minute moneyline', 'hockey/nhl', 'Golden Knights 60-min ML', None, None, True),
    ('NHL first-period moneyline', 'hockey/nhl', 'Golden Knights 1P ML', None, None, True),
    ('NHL team string Golden Knights (VGK)', 'hockey/nhl', 'Kings ML', 'Los Angeles Kings', 'Golden Knights (VGK)', True),
    ('NHL team string VGK Golden Knights', 'hockey/nhl', 'Kings ML', 'Los Angeles Kings', 'VGK Golden Knights', True),
    ('WNBA title future with a price', 'basketball/wnba', 'Aces to win title +300', None, None, True),
    ('WNBA prop with the team in brackets', 'basketball/wnba', "A'ja Wilson (Aces) over 24.5 points", None, None, True),
    ('WNBA first-quarter spread', 'basketball/wnba', 'Aces 1Q -1.5', None, None, True),
    ('WNBA team string Aces (LV)', 'basketball/wnba', 'Fever ML', 'Indiana Fever', 'Aces (LV)', True),
    ('a named non-Vegas team never shields a Vegas word beside it', 'football/nfl', 'Red Raiders ML', 'Texas Tech Red Raiders', 'Las Vegas Raiders', True),
    ('a named non-Vegas team never shields the nickname elsewhere in the string', 'football/nfl', 'Red Raiders vs Raiders ML', None, None, True),
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

# The floor: origin/main's word rule, kept here as a reference copy (build_manifest.vegas_hit before the contract
# block). Whatever it held stays held, unless one of the pick's strings names a _VEGAS_NOT team.
_OLD_NICK = {'football/nfl': ('raiders',), 'hockey/nhl': ('golden knights',), 'basketball/wnba': ('aces',),
             'baseball/mlb': ('athletics', "a's"), 'football/college-football': ('unlv',),
             'basketball/mens-college-basketball': ('unlv',), 'basketball/womens-college-basketball': ('unlv',)}
def old_word_rule(league, fields):
    lg = str(league or '').strip().lower()
    if lg.split('/')[0] in ('racing', 'golf', 'tennis', 'mma', 'boxing'):
        return None
    names = ('las vegas', 'vegas', 'unlv') + _OLD_NICK.get(lg, ())
    for f, v in fields:
        w = ' ' + re.sub(r"[^a-z0-9']+", ' ', str(v or '').lower().replace('\u2019', "'")) + ' '
        if any(' ' + n + ' ' in w for n in names):
            return f
    return None

contract = {'re': re}
exec(compile(blocks[MANIFEST_BUILDER] or '', MANIFEST_BUILDER, 'exec'), contract)
NOT, WORDS, CITY = contract.get('_VEGAS_NOT', ()), contract.get('_VEGAS_WORDS', {}), contract.get('_VEGAS_CITY', ())
vg = contract.get('_vg_words', lambda s: ' ')
check('the contract names its exceptions (_VEGAS_NOT) and its league words (_VEGAS_WORDS)', bool(NOT) and bool(WORDS) and bool(CITY))
for n in NOT:
    check(f'_VEGAS_NOT {n!r}: a normalized multi-word team name, never a Vegas word on its own, no city word in it, '
          f'and a near miss (it carries some league\'s Vegas word)',
          vg(n).strip() == n and len(n.split()) >= 2 and all(n not in ws for ws in WORDS.values()) and n not in CITY
          and not any(f' {c} ' in f' {n} ' for c in CITY) and any(f' {x} ' in f' {n} ' for ws in WORDS.values() for x in ws))
def names_an_exception(fields):
    return any(f' {n} ' in vg(v) for _, v in fields for n in NOT)
for tag, fn in list(rules.items()) + [('build_manifest.vegas_hit', None)]:
    lost = []
    for label, lg, name, away, home, _ in CASES:
        fields = (('name', name), ('away', away), ('home', home))
        if old_word_rule(lg, fields) and not names_an_exception(fields):
            got = fn(lg, fields) if fn else (vh({'espn_league': lg, 'name': name, 'away': away, 'home': home}) if vh else None)
            if not got:
                lost.append(label)
    check(f'{tag}: never weaker than the word rule - every case it held is still held (a named exception apart)', not lost, lost)

# end to end through both twins: an abbreviated, decorated or qualified Vegas team holds the card; a near-miss
# name builds
def build(builder, manifest):
    d = tempfile.mkdtemp(prefix='rp-vegas-')
    try:
        os.makedirs(os.path.join(d, 'scripts')); os.makedirs(os.path.join(d, 'slates'))
        shutil.copy(builder, os.path.join(d, 'scripts', 'build_gh_page_v2.py'))
        for f in ('index_v2.js', 'index_v2.css', 'game_page_template.html', 'team_page_template.html', 'poly_us.py'):
            shutil.copy(os.path.join(SD, f), os.path.join(d, 'scripts', f))
        for f in ('feed_arbiter.js', 'feed_registry.json', 'config_leagues.json'):
            shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
        manifest=dict(manifest,picks=[market(p) for p in manifest.get('picks',[])])
        manifest=stamped(builder,manifest)
        json.dump(manifest, open(os.path.join(d, 'manifest.json'), 'w'), indent=1)
        published_snapshot(d,builder,manifest)
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
                     ('NHL game with "VGK"', pick(1, 'Kings ML', 'hockey/nhl', 'NHL', 'LA', 'VGK', side='away')),
                     ("MLB game with away \"Sacramento A's\"", pick(1, 'Giants ML', 'baseball/mlb', 'MLB', "Sacramento A's", 'San Francisco Giants')),
                     ('NFL "Chiefs @ Raiders ML" at home "Raiders (LV)"', pick(1, 'Chiefs @ Raiders ML', 'football/nfl', 'NFL', 'Kansas City Chiefs', 'Raiders (LV)', side='away')),
                     ('NFL "Raiders 1H +3.5", game teams unreadable', pick(1, 'Raiders 1H +3.5', 'football/nfl', 'NFL', 'Team A', 'Team B'))):
        rc, log, written = build(B, card([p]))
        check(f'{tag}: {label}: the card is held (exit 3, the Vegas rule named), nothing written',
              rc == 3 and 'BUILD FAILED' in log and 'Las Vegas team' in log and written == [], (rc, log[-300:], written))
    rc, log, written = build(B, card([pick(1, 'Red Raiders ML', 'football/nfl', 'NFL', 'Baylor Bears', 'Texas Tech Red Raiders'),
                                      pick(2, 'UCF ML', 'hockey/nhl', 'NHL', 'Cincinnati Bearcats', 'UCF Golden Knights')]))
    check(f'{tag}: near-miss names filed under the NFL and NHL (Texas Tech Red Raiders, UCF Golden Knights): the card builds',
          rc == 0 and 'index.html' in written and 'Las Vegas team' not in log, (rc, log[-300:]))

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
