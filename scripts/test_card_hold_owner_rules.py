#!/usr/bin/env python3
"""Card hold on the standing rules at the page builder (owner ruling 2026-10-02 (4), relayed verbatim by muse:
"NO - an owner-approved card cannot break a standing rule. Vegas rule, ladder sizes, all of it: hard gates, no
exceptions.").
build_manifest.py refuses such a card, but a manifest.json can land another way (by hand, an older builder), and
publish.yml, refresh.sh and record_final.yml build whatever card has landed. So the page builder (both twins)
holds the CURRENT card - exit 3, the CARD HOLD path refresh.sh reports loudly, nothing written - when a pick is on
or against a Las Vegas team (Raiders, Golden Knights, Aces, Athletics/A's, UNLV; a nickname counts only inside
its own league, and the individual sports have no teams), its units are off the J-096 ladder (5u, 10u, 15u,
100u, written exactly so), or it breaks a numeric standing bar (rulings (1), (2), (4)): card ask
>= 85c, gross < 2c, net below the class bar, units over the J-096 rung of its fair, a card_american that is not
the best ask of its recorded venues, or a parlay over length or short of the 2c/2c bar. The fair is read from the
pick's "model X" sub (or its best_ask), the card price from card_american; a pick whose fair/price cannot be read
is left unchecked on the numeric bars.
 - An empty card builds, and so does the live manifest.json.
 - An earlier card's manifests/ snapshot, rebuilt for its game pages after the day rolls to an empty card, is
   not gated: those pages belong to a card already published.
Builds run in a throwaway tree with the network sent to a dead proxy.
Run: python3 scripts/test_card_hold_owner_rules.py [builder.py ...]   (default: both twins)"""
import copy, json, os, re, shutil, subprocess, sys, tempfile

from fixtures.card_contract import stamped, market, published_snapshot

SD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SD)
BUILDERS = [os.path.abspath(a) for a in sys.argv[1:]] or [os.path.join(SD, 'build_gh_page_v2.py'), os.path.join(SD, '_build_nocanon_v2.py')]
DEAD = 'http://127.0.0.1:9'
failures = 0

def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or detail == '' else '  [' + str(detail)[-400:] + ']'))
    if not ok:
        failures += 1

def build(builder, manifest, seed=None):
    """Build manifest.json in a throwaway tree; returns (rc, stderr, files written by the build)."""
    d = tempfile.mkdtemp(prefix='rp-cardhold-')
    try:
        os.makedirs(os.path.join(d, 'scripts')); os.makedirs(os.path.join(d, 'slates'))
        for rel, text in (seed or {}).items():
            os.makedirs(os.path.dirname(os.path.join(d, rel)) or d, exist_ok=True)
            open(os.path.join(d, rel), 'w').write(text)
        bsrc = os.path.dirname(builder)
        shutil.copy(builder, os.path.join(d, 'scripts', 'build_gh_page_v2.py'))
        for f in ('index_v2.js', 'index_v2.css', 'game_page_template.html', 'team_page_template.html', 'poly_us.py'):
            shutil.copy(os.path.join(bsrc if os.path.exists(os.path.join(bsrc, f)) else SD, f), os.path.join(d, 'scripts', f))
        for f in ('feed_arbiter.js', 'feed_registry.json', 'config_leagues.json'):
            shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
        manifest=stamped(builder,manifest)
        json.dump(manifest, open(os.path.join(d, 'manifest.json'), 'w'), indent=1)
        published_snapshot(d,builder,manifest)
        json.dump([], open(os.path.join(d, 'slates', 'odds_prefill.json'), 'w'))
        before = {os.path.relpath(os.path.join(p, f), d): os.path.getmtime(os.path.join(p, f)) for p, _, fs in os.walk(d) for f in fs}
        env = dict(os.environ, RP_REFRESH='1', http_proxy=DEAD, https_proxy=DEAD, HTTP_PROXY=DEAD, HTTPS_PROXY=DEAD)
        r = subprocess.run([sys.executable, os.path.join(d, 'scripts', 'build_gh_page_v2.py'), 'manifest.json', 'index.html'],
                           cwd=d, env=env, capture_output=True, text=True, timeout=600)
        after = {os.path.relpath(os.path.join(p, f), d): os.path.getmtime(os.path.join(p, f)) for p, _, fs in os.walk(d) for f in fs}
        written = sorted(f for f, t in after.items() if before.get(f) != t and '__pycache__' not in f)
        pages = {f: open(os.path.join(d, f)).read() for f in written if re.fullmatch(r'game-\d+\.html', f)}
        return r.returncode, r.stdout + r.stderr, written, pages
    finally:
        shutil.rmtree(d, ignore_errors=True)

BASE = {'date': '2099-10-04', 'date_label': 'Sunday, Oct 4', 'updated': 'Oct 4, 8:42 AM PT', 'record': '21-11',
        'units_pl': '+4.76u', 'units_ledger': None, 'yesterday': '', 'status_note': '', 'preview': False, 'parlay': None}
LEAGUE = {'football/nfl': 'NFL', 'hockey/nhl': 'NHL', 'basketball/wnba': 'WNBA', 'baseball/mlb': 'MLB',
          'football/college-football': 'CFB', 'basketball/mens-college-basketball': 'NCAAB'}
def pick(num, name, league, away, home, units='5u', side='home', eid='', model=66.0, american=-150, **extra):
    p = {'num': num, 'name': name, 'market_class': 'ml', 'sub': f'fixture - model {model:.1f}', 'odds': f'{american:+d}',
         'card_american': american, 'units': units,
         'side': side, 'game': {'away': away, 'home': home, 'commence': '2099-10-04T20:25Z', 'eid': eid},
         'espn_league': league, 'league': LEAGUE[league], 'best_book': 'Kalshi', 'card_source': 'Kalshi ask at lock'}
    p=market(p)
    p.update(extra)
    return p
def card(picks, **kw):
    m = copy.deepcopy(BASE); m['picks'] = copy.deepcopy(picks); m.update(kw); return m

DEVILS = pick(1, 'Devils ML', 'hockey/nhl', 'Philadelphia Flyers', 'New Jersey Devils')
VEGAS = [
    ('Raiders ML (NFL, on)', pick(1, 'Raiders ML', 'football/nfl', 'Denver Broncos', 'Las Vegas Raiders')),
    ('Broncos ML at the Raiders (NFL, against)', pick(1, 'Broncos ML', 'football/nfl', 'Denver Broncos', 'Las Vegas Raiders', side='away')),
    ('Golden Knights game (NHL)', pick(1, 'Kings ML', 'hockey/nhl', 'Los Angeles Kings', 'Vegas Golden Knights', side='away')),
    ('Aces game (WNBA)', pick(1, 'Fever ML', 'basketball/wnba', 'Indiana Fever', 'Las Vegas Aces', side='away')),
    ('Athletics game (MLB)', pick(1, 'Astros ML', 'baseball/mlb', 'Athletics', 'Houston Astros')),
    ("A's in the pick name (MLB)", pick(1, 'A’s ML', 'baseball/mlb', 'Sacramento Club', 'Houston Astros', side='away')),
    ('UNLV game (CFB)', pick(1, 'Broncos ML', 'football/college-football', 'UNLV Rebels', 'Boise State Broncos')),
    ('a Vegas nickname with its league written in capitals', pick(1, 'Kings ML', 'hockey/nhl', 'Los Angeles Kings', 'Golden Knights', side='away')
                                                        | {'espn_league': 'Hockey/NHL '}),
]

for B in BUILDERS:
    tag = os.path.basename(B)
    rc, log, written, _ = build(B, card([DEVILS]))
    check(f'{tag}: a clean card builds', rc == 0 and 'index.html' in written, log[-300:])

    for label, vp in VEGAS:
        rc, log, written, _ = build(B, card([DEVILS, dict(vp, num=2)]))
        check(f'{tag}: {label}: the card is held (exit 3, BUILD FAILED, the Vegas rule named)',
              rc == 3 and 'BUILD FAILED' in log and 'Vegas' in log and 'owner ruling 2026-10-02 (4)' in log, (rc, log[-300:]))
        check(f'{tag}: {label}: nothing written (no index, no game page, no manifest snapshot)', written == [], written)

    for u in ('6u', '2u', '20u', '5', '5.0u', ' 5u', '', None, 5):
        rc, log, written, _ = build(B, card([DEVILS, pick(2, 'Bills ML', 'football/nfl', 'New England Patriots', 'Buffalo Bills', units=u)]))
        check(f'{tag}: units {u!r} off the ladder: the card is held (exit 3), nothing written',
              rc == 3 and 'BUILD FAILED' in log and 'J-096' in log and written == [], (rc, log[-300:], written))

    rc, log, written, _ = build(B, card([pick(1, 'Raiders ML', 'football/nfl', 'Denver Broncos', 'Las Vegas Raiders'),
                                         pick(2, 'Bills ML', 'football/nfl', 'New England Patriots', 'Buffalo Bills', units='6u')]))
    check(f'{tag}: a Vegas pick and a 6u pick are both named in the one hold, with no override offered',
          rc == 3 and 'Raiders ML' in log and 'Bills ML' in log and 'override' in log and 'directive' not in log.lower(), log[-400:])

    rc, log, written, _ = build(B, card([pick(1, 'Red Raiders ML', 'football/college-football', 'Baylor Bears', 'Texas Tech Red Raiders'),
                                         pick(2, 'Purple Aces ML', 'basketball/mens-college-basketball', 'Murray State Racers', 'Evansville Purple Aces'),
                                         pick(3, 'Rangers ML', 'baseball/mlb', 'Texas Rangers', 'Seattle Mariners', units='100u', model=92.0)]))
    check(f'{tag}: Texas Tech Red Raiders (CFB) and Evansville Purple Aces (NCAAB) are no Vegas teams; 100u (at its fair) is on the ladder',
          rc == 0 and 'index.html' in written, log[-300:])

    # numeric standing bars on the CURRENT card (owner rulings 2026-10-02 (1), (2), (4)): the fair is read from
    # each pick's "model X" sub, the card price from card_american. A clean numeric card builds; each bar held.
    rc, log, written, _ = build(B, card([pick(1, 'Clean ML', 'hockey/nhl', 'A', 'B', model=66.0, american=-150)]))
    check(f'{tag}: a clean numeric card builds', rc == 0 and 'index.html' in written, log[-300:])
    NUM = [
        ('fair 55c has negative gross at 60c ask', pick(1, 'SubFair ML', 'hockey/nhl', 'A', 'B', model=55.0, american=-150), 'gross'),
        ('card ask 85c at the cut', pick(1, 'Fav ML', 'hockey/nhl', 'A', 'B', units='100u', model=96.0, american=-567), '85c cut'),
        ('gross 1.0c below the 2c bar', pick(1, 'Thin ML', 'hockey/nhl', 'A', 'B', model=61.0, american=-150), 'gross'),
        ('fair 66c carded at 10u (rung 5u)', pick(1, 'OffRung ML', 'hockey/nhl', 'A', 'B', units='10u', model=66.0, american=-150), 'J-096 rung'),
    ]
    for label, p, token in NUM:
        rc, log, written, _ = build(B, card([p]))
        check(f'{tag}: {label}: the card is held (exit 3), nothing written',
              rc == 3 and 'BUILD FAILED' in log and token in log and written == [], (rc, log[-300:], written))
    # spread net below the 2c bar: fair 63.5c against Kalshi 60c (-150) -> net 3.5 - fee(60)=1.68 = 1.82c
    sp = pick(1, 'Home1 -1.5', 'hockey/nhl', 'A', 'B', model=63.5, american=-150)
    sp['market_class'] = 'spread'; sp['line'] = -1.5
    rc, log, written, _ = build(B, card([sp]))
    check(f'{tag}: spread net below the 2c bar is held', rc == 3 and 'net' in log and written == [], (rc, log[-300:], written))
    # card_american that is not the best ask of the recorded venues (DK -150 is 60c; card claims -130 = 56.5c)
    ba = pick(1, 'BadAm ML', 'hockey/nhl', 'A', 'B', model=66.0, american=-130)
    ba['best_ask'] = {'venue': 'dk', 'price': -150, 'read_at': '2099-10-04T14:51:00Z', 'cost_c': 60.0, 'fee_c': 0.0,
                      'gross_c': 6.0, 'net_c': 6.0, 'compared': [{'venue': 'dk', 'price': -150, 'read_at': '2099-10-04T14:51:00Z'},
                                                                 {'venue': 'kalshi', 'price': 61, 'read_at': '2099-10-04T14:51:00Z'}]}
    ba['kalshi'] = {'cents':61,'team':'B','ticker':'KXFIXGAME-99OCT04AH-H','side':'yes','url':'https://kalshi.com/markets/kxfixgame/kxfixgame-99oct04ah'}
    rc, log, written, _ = build(B, card([ba]))
    check(f'{tag}: a card_american that is not the best recorded ask is held', rc == 3 and 'best recorded ask' in log and written == [], (rc, log[-300:], written))
    # a parlay failing the 2c/2c bar: two legs that clear on their own (fair 63c, net 1.32c) but combine to net 1.65c
    l1 = pick(1, 'Leg1 ML', 'hockey/nhl', 'A1', 'B1', model=63.0, american=-150)
    l2 = pick(2, 'Leg2 ML', 'hockey/nhl', 'A2', 'B2', model=63.0, american=-150)
    rc, log, written, _ = build(B, card([l1, l2], parlay={'legs': ['Leg1 ML', 'Leg2 ML'], 'note': ''}))
    check(f'{tag}: a parlay short of the 2c/2c bar is held', rc == 3 and 'parlay' in log and written == [], (rc, log[-300:], written))
    # an over-length parlay (5 legs) is held
    legs5 = [pick(i, f'P{i} ML', 'hockey/nhl', f'A{i}', f'B{i}', units='100u', model=92.0, american=-150) for i in range(1, 6)]
    rc, log, written, _ = build(B, card(legs5, parlay={'legs': [p['name'] for p in legs5], 'note': ''}))
    check(f'{tag}: an over-length parlay (5 legs) is held', rc == 3 and 'J-098' in log and written == [], (rc, log[-300:], written))

    rc, log, written, _ = build(B, card([], status_note='No official picks today'))
    check(f'{tag}: an empty card builds', rc == 0 and 'index.html' in written, log[-300:])

    live = json.load(open(os.path.join(ROOT, 'manifest.json')))
    # The live card is built with the same inputs production has: the append-only owner suspension log
    # (slates/owner_rule_suspensions.jsonl). Without it the throwaway tree has nothing to waive and a
    # logged owner card is held (Oct 3 12:04 PM card failed tests run 37157768761 for exactly that).
    _slog = os.path.join(ROOT, 'slates', 'owner_rule_suspensions.jsonl')
    _seed = {'slates/owner_rule_suspensions.jsonl': open(_slog).read()} if os.path.exists(_slog) else None
    rc, log, written, _ = build(B, live, seed=_seed)
    # The build runs with the network dead, so the pre-game live-market verification (hunter ruling Sep 26:
    # "no live market, no pin") cannot pass for a pregame pick here - production checks it against the real
    # market. That verdict is evaluated AFTER the standing-rules card hold, so reaching it means the hold
    # cleared. The live card passes this check when it builds, or when the ONLY thing stopping it is that
    # network-dependent verdict and the standing-rules card hold is not in the log.
    _net_only = (rc == 3 and 'standing-rules card hold' not in log and 'pre-game NEW content hard-fail' in log
                 and 'no live market, no pin' in log and 'BUILD FAILED' in log and not written)
    check(f"{tag}: the live manifest.json ({live.get('date')}, {len(live.get('picks') or [])} picks) clears the standing-rules card hold and builds",
          (rc == 0 and 'index.html' in written) or _net_only, log[-300:])

    # the day rolls to an empty card: the last card's game pages rebuild from its manifests/ snapshot, which
    # is not the current card and is not gated, even when it carries a Vegas pick and a 6u pick
    OLD = [pick(1, 'Raiders ML', 'football/nfl', 'Denver Broncos', 'Las Vegas Raiders', eid='401990301'),
           pick(2, 'Bills ML', 'football/nfl', 'New England Patriots', 'Buffalo Bills', units='6u', eid='401990302')]
    seed = {'game-1.html': '<div class="pick" data-eid="401990301"></div>', 'game-2.html': '<div class="pick" data-eid="401990302"></div>',
            'manifests/manifest-2099-10-03.json': json.dumps(card(OLD, date='2099-10-03', date_label='Saturday, Oct 3'))}
    rc, log, written, pages = build(B, card([]), seed=seed)
    check(f'{tag}: an earlier snapshot rebuilt for its game pages is not gated (empty current card builds, both pages rebuilt)',
          rc == 0 and 'index.html' in written and sorted(pages) == ['game-1.html', 'game-2.html']
          and 'data-eid="401990301"' in pages.get('game-1.html', '') and 'HISTORICAL GAME HOLD' not in log, (rc, log[-300:], sorted(pages)))

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
