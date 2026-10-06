#!/usr/bin/env python3
"""Card-shape build fixture (Oct 1 sweep: CP-02, CP-08, CP-09, CP-10, W/L percent).

Builds real cards with each builder twin in a throwaway tree, network blocked (dead proxy: every
feed lookup fails fast, nothing leaves the machine), and checks the built index.html:
- CP-02: a card with no MLB pick still mounts the Dingers module exactly once (as a Home panel
  after the league panels); an MLB card keeps it on the MLB tab only. The health gate holds every
  posting job when the module is missing.
- CP-08: a spread pick (market_class 'spread', the build_manifest.py shape) prices only from
  spread quotes on its own line, never from the moneyline prefill; a total pick never takes a
  moneyline price or link; rows carry data-market/data-line.
- CP-09: the refresh run's own pull (slates/odds_prefill.json) beats a frozen repo-root copy.
- CP-10: a card with no lock provenance never claims "locked" from manifest.updated; posted_at
  marks picks whose game began before the card was published; a normal card_ts card is unchanged.
  The late stamp is short ('Posted 5:30 PM · after start') and breaks into two lines on phones
  (Oct 2 review: 'Posted Oct 2, 12:30 PM PT · after start' in a nowrap, non-shrinking meta group
  pushed the index to 381px and the game page to 397px at a 320px viewport); neither phone line
  is longer than the '12:30 PM · locked' stamp that fits at 320px. A game page reads ITS OWN
  card's posted_at: after the PT day rolls to an empty card, the last card's game pages (rebuilt
  from its manifests/ snapshot) keep 'after start' for a game that began before that card was
  posted, and an empty card's own posted_at never stamps them. Each pick is stamped from its OWN
  card_ts (r3 review: a pick added later moved posted_at, so the earlier Yankees pick read 'Posted
  4:00 PM - after start' and the added Dodgers pick's game page read the card's earliest 9:00 AM): after
  start only when card_ts >= its own commence, else locked at card_ts, the same on the index and its
  game page; posted_at stamps only a pick with no card_ts.
- W/L percent: the baked nav and popover values use the client's half-up rule (21-11 = 65.63%).
- Date roll (Oct 2 review): the .rpdate header carries the card's ISO date (data-date: manifest date,
  else the builder's _card_date_of), which rpDateRoll compares with today's PT date.
- Away spread (Oct 2 review): the pipeline stores a spread pick's line as the HOME spread (record_final,
  finals_watch, st_card_candidates); the page grades with the picked side's own line. An away-cover
  pick 'Lynx +4' (line -4) emits data-line 4 on its row, combo leg and game page, prices its away
  chips from the +4 quotes, and the built page's verdict agrees with record_final.score_result on
  every final (85-84 W, 82-84 W, 80-84 P, 70-84 L).
Run: python3 scripts/test_card_shapes_build.py [builder.py ...]   (default: both twins)
"""
import ast, copy, json, os, re, shutil, subprocess, sys, tempfile, warnings
warnings.simplefilter("ignore", SyntaxWarning)  # the builder source carries pre-existing invalid escapes inside JS templates

SD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SD)
BUILDERS = [os.path.abspath(a) for a in sys.argv[1:]] or [os.path.join(SD, 'build_gh_page_v2.py'), os.path.join(SD, '_build_nocanon_v2.py')]
failures = 0
def check(name, ok):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name)
    if not ok: failures += 1

DEAD = 'http://127.0.0.1:9'
def build(builder, manifest, slates_prefill, root_prefill=None, seed=None):
    d = tempfile.mkdtemp(prefix='rp-cardshape-')
    os.makedirs(os.path.join(d, 'scripts')); os.makedirs(os.path.join(d, 'slates'))
    for rel, text in (seed or {}).items():  # files already served before this build (game pages, manifests/ snapshots)
        os.makedirs(os.path.dirname(os.path.join(d, rel)) or d, exist_ok=True)
        open(os.path.join(d, rel), 'w').write(text)
    bsrc = os.path.dirname(builder)
    shutil.copy(builder, os.path.join(d, 'scripts', 'build_gh_page_v2.py'))
    for f in ('index_v2.js', 'index_v2.css', 'game_page_template.html', 'team_page_template.html', 'poly_us.py'):
        shutil.copy(os.path.join(bsrc if os.path.exists(os.path.join(bsrc, f)) else SD, f), os.path.join(d, 'scripts', f))
    for f in ('feed_arbiter.js', 'feed_registry.json', 'config_leagues.json'):
        shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
    json.dump(manifest, open(os.path.join(d, 'manifest.json'), 'w'), indent=1)
    json.dump(slates_prefill, open(os.path.join(d, 'slates', 'odds_prefill.json'), 'w'))
    if root_prefill is not None: json.dump(root_prefill, open(os.path.join(d, 'odds_prefill.json'), 'w'))
    env = dict(os.environ, RP_REFRESH='1', http_proxy=DEAD, https_proxy=DEAD, HTTP_PROXY=DEAD, HTTPS_PROXY=DEAD)
    r = subprocess.run([sys.executable, os.path.join(d, 'scripts', 'build_gh_page_v2.py'), 'manifest.json', 'index.html'],
                       cwd=d, env=env, capture_output=True, text=True, timeout=600)
    page = open(os.path.join(d, 'index.html')).read() if os.path.exists(os.path.join(d, 'index.html')) else ''
    GAME_PAGES.clear()
    for f in os.listdir(d):
        if re.fullmatch(r'game-\d+\.html', f): GAME_PAGES[f] = open(os.path.join(d, f)).read()
    shutil.rmtree(d, ignore_errors=True)
    return r.returncode, page, r.stderr
GAME_PAGES = {}  # game-N.html of the last build

def row(page, away):
    i = page.find('data-away="%s"' % away)
    if i < 0: return ''
    s = page.rfind('<div class="pick"', 0, i)
    e = page.find('class="rplineshop"', i)
    return page[s:e if e > 0 else i + 4000]

BASE = {'date': '2099-10-01', 'date_label': 'Thursday, Oct 1', 'updated': 'Oct 1, 8:42 AM PT', 'record': '21-11',
        'units_pl': '+4.76u', 'units_ledger': None, 'yesterday': '', 'status_note': '', 'preview': False, 'parlay': None}
DEVILS = {'num': 1, 'name': 'Devils ML', 'market_class': 'ml', 'sub': 'PHI @ NJ', 'odds': '-162', 'units': '5u', 'side': 'home',
          'game': {'away': 'Philadelphia Flyers', 'home': 'New Jersey Devils', 'commence': '2099-10-01T23:00Z', 'eid': ''},
          'espn_league': 'hockey/nhl', 'league': 'NHL', 'best_book': 'DraftKings'}
MERCURY = {'num': 2, 'name': 'Mercury -4.5', 'market_class': 'spread', 'line': -4.5, 'sub': 'IND @ PHX', 'odds': '-110', 'units': '5u', 'side': 'home',
           'game': {'away': 'Indiana Fever', 'home': 'Phoenix Mercury', 'commence': '2099-10-02T01:00Z', 'eid': ''},
           'espn_league': 'basketball/wnba', 'league': 'WNBA', 'best_book': 'DraftKings',
           'books_sp': {'draftkings': {'home': {'price': -110, 'point': -4.5, 'link': 'https://sportsbook.draftkings.com/?outcomes=SP_MERC_DK'},
                                       'away': {'price': -110, 'point': 4.5, 'link': 'https://sportsbook.draftkings.com/?outcomes=SP_FEVER_DK'}},
                        'hardrockbet': {'home': {'price': -105, 'point': -5.5, 'link': 'https://app.hardrock.bet/?deep_link_value=betslip/SP_MERC_HR_OTHERLINE'}}}}
UNDER = {'num': 3, 'name': 'Under 38.5', 'market_class': 'total', 'line': 38.5, 'sub': 'PIT @ CLE', 'odds': '-115', 'units': '5u', 'side': 'under',
         'game': {'away': 'Pittsburgh Steelers', 'home': 'Cleveland Browns', 'commence': '2099-10-02T00:15Z', 'eid': ''},
         'espn_league': 'football/nfl', 'league': 'NFL', 'best_book': 'DraftKings'}
SOX = {'num': 1, 'name': 'White Sox ML', 'market_class': 'ml', 'sub': 'CWS @ HOU', 'odds': '+138', 'units': '5u', 'side': 'away',
       'game': {'away': 'Chicago White Sox', 'home': 'Houston Astros', 'commence': '2099-09-30T21:00Z', 'eid': ''},
       'espn_league': 'baseball/mlb', 'league': 'MLB', 'best_book': 'DraftKings', 'card_ts': '2099-09-30T07:04:26-07:00'}
# build_manifest shape of an away-cover spread (st_card_candidates.adapt_alt): line is the HOME spread
LYNX = {'num': 1, 'name': 'Lynx +4', 'market_class': 'spread', 'line': -4, 'sub': 'MIN @ NY - away cover', 'odds': '-110', 'units': '5u',
        'side': 'away', 'game': {'away': 'Minnesota Lynx', 'home': 'New York Liberty', 'commence': '2099-10-01T23:30Z', 'eid': ''},
        'espn_league': 'basketball/wnba', 'league': 'WNBA', 'best_book': 'DraftKings',
        'books_sp': {'draftkings': {'away': {'price': -110, 'point': 4, 'link': 'https://sportsbook.draftkings.com/?outcomes=SP_LYNX_DK'},
                                    'home': {'price': -110, 'point': -4, 'link': 'https://sportsbook.draftkings.com/?outcomes=SP_LIB_DK'}},
                     'hardrockbet': {'away': {'price': -115, 'point': 4, 'link': 'https://app.hardrock.bet/?deep_link_value=betslip/SP_LYNX_HR'}}}}
def ml_entry(away, home, commence, hml, aml, tag):
    return {'away': away, 'home': home, 'commence': commence, 'books': {'draftkings': {
        'home_ml': hml, 'away_ml': aml, 'event': 'https://sportsbook.draftkings.com/event/' + tag,
        'home_link': 'https://sportsbook.draftkings.com/?outcomes=%s_HOME' % tag, 'away_link': 'https://sportsbook.draftkings.com/?outcomes=%s_AWAY' % tag}}}
FRESH = [ml_entry('Philadelphia Flyers', 'New Jersey Devils', '2099-10-01T23:00Z', -162, 140, 'ML_DEVILS_FRESH'),
         ml_entry('Indiana Fever', 'Phoenix Mercury', '2099-10-02T01:00Z', -250, 205, 'ML_MERC'),
         ml_entry('Pittsburgh Steelers', 'Cleveland Browns', '2099-10-02T00:15Z', -140, 120, 'ML_PITCLE'),
         ml_entry('Chicago White Sox', 'Houston Astros', '2099-09-30T21:00Z', -160, 138, 'ML_SOX')]
# frozen repo-root copy: a stale Devils price plus the same moneyline entries for the other games
STALE = [ml_entry('Philadelphia Flyers', 'New Jersey Devils', '2099-10-01T23:00Z', -999, 777, 'ML_DEVILS_STALE')] + FRESH[1:3]

def card(picks, **kw):
    m = copy.deepcopy(BASE); m['picks'] = copy.deepcopy(picks); m.update(kw); return m

def js_fn(src, name):
    i = src.find('function ' + name + '(')
    if i < 0: return ''
    d = 0
    for k in range(src.find('{', i), len(src)):
        if src[k] == '{': d += 1
        elif src[k] == '}':
            d -= 1
            if not d: return src[i:k + 1]
    return ''

def page_verdicts(page, game_page, side, line, finals):
    # the built pages' own verdict code: index rpGrade (pick rows + combo legs) and game-page rpGameGrade
    code = js_fn(page, 'rpGrade') + '\n' + js_fn(game_page, 'rpGameGrade') + '\n' + (
        'const F=%s;console.log(JSON.stringify([F.map(f=>rpGrade("spread",%s,%s,f[0],f[1])),'
        'F.map(f=>rpGameGrade({dataset:{side:%s,market:"spread",line:%s}},f[0],f[1]))]));'
        % (json.dumps(finals), json.dumps(side), json.dumps(line), json.dumps(side), json.dumps(line)))
    r = subprocess.run(['node', '-e', code], capture_output=True, text=True)
    try: return json.loads(r.stdout)
    except ValueError: return [None, None]

def _load_record_final():
    import importlib.util
    spec = importlib.util.spec_from_file_location('record_final_for_cardshape', os.path.join(SD, 'record_final.py'))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
RF = _load_record_final()

for B in BUILDERS:
    tag = os.path.basename(B)
    # 1. Oct 1 shape: NFL total + WNBA spread + NHL ML, no MLB pick, no lock provenance
    rc, page, log = build(B, card([DEVILS, MERCURY, UNDER], parlay={'legs': ['Under 38.5', 'Mercury -4.5', 'Devils ML'], 'note': ''}), FRESH, STALE)
    check(f'{tag}: non-MLB card builds', rc == 0 and len(page) > 10000)
    n_ding = len(re.findall(r'slates/wooder_dingers\.json', page))
    check(f'{tag}: CP-02 non-MLB card mounts the Dingers module exactly once', n_ding == 1)
    ding_at = page.find('slates/wooder_dingers.json'); panel = page.rfind('<div class="state"', 0, ding_at)
    check(f'{tag}: CP-02 Dingers (Wooder Ice) sits under the Wooder tab only, never a Home panel',
          'id="st-ding"' not in page and panel == page.find('<div class="state" id="st-wooder"') > 0)
    merc, under, devils = row(page, 'Indiana Fever'), row(page, 'Pittsburgh Steelers'), row(page, 'Philadelphia Flyers')
    check(f'{tag}: CP-08 spread row carries data-market="spread" data-line="-4.5"', 'data-market="spread" data-line="-4.5"' in merc)
    check(f'{tag}: CP-08 spread pick never shows the moneyline price or link', '-250' not in merc and 'ML_MERC' not in merc)
    check(f'{tag}: CP-08 spread pick prices from its own line (DK -110)', 'SP_MERC_DK' in merc and 'DK -110' in merc)
    check(f'{tag}: CP-08 a book quoting another point is not shown as this line', 'SP_MERC_HR_OTHERLINE' not in merc and '-105' not in merc)
    check(f'{tag}: CP-08 total row carries data-market="total" data-line="38.5"', 'data-market="total" data-line="38.5"' in under)
    check(f'{tag}: CP-08 total pick never takes a moneyline price or link', 'ML_PITCLE' not in under and '-140' not in under and '+120' not in under)
    legs = re.findall(r'<li class="cxleg"[^>]*>', page)
    check(f'{tag}: CP-03 parlay legs carry the verdict inputs (market class and line)',
          len(legs) == 3 and any('data-side="under" data-market="total" data-line="38.5"' in l for l in legs)
          and any('data-side="home" data-market="spread" data-line="-4.5"' in l for l in legs)
          and any('data-away="Philadelphia Flyers"' in l and 'data-market="ml"' in l for l in legs))
    check(f'{tag}: CP-09 chips read the refresh pull (slates/), not the frozen root copy',
          'ML_DEVILS_FRESH_HOME' in devils and 'DK -162' in devils and 'ML_DEVILS_STALE' not in page and '-999' not in devils)
    stamps = re.findall(r'class="oddslock">([^<]*)<', page)
    check(f'{tag}: CP-10 no lock claim from manifest.updated when nothing records the lock',
          len(stamps) == 3 and not any('locked' in s or '8:42' in s for s in stamps))
    check(f'{tag}: W/L nav percent bakes the client value 65.63% (half-up)', 'id="rpNavPct">65.63%<' in page)
    check(f'{tag}: the date header carries the card\'s ISO date for the PT roll', '<div class="rpdate" data-date="2099-10-01">Thursday, Oct 1</div>' in page)

    # 2. same card published late: posted_at 5:30 PM PT Oct 1 (after Devils and Under began, before Mercury)
    rc, page, log = build(B, card([DEVILS, MERCURY, UNDER], posted_at='2099-10-02T00:30:00Z'), FRESH)
    raw = {a: re.search(r'class="oddslock">(.*?)</span></a>', row(page, a)) for a in ('Philadelphia Flyers', 'Indiana Fever', 'Pittsburgh Steelers')}
    raw = {a: (m.group(1) if m else '') for a, m in raw.items()}
    st = {a: re.sub(r'<[^>]+>', '', v) for a, v in raw.items()}
    check(f'{tag}: CP-10 posted_at after a game began says so (never "locked"), short: "Posted 5:30 PM · after start"',
          st['Philadelphia Flyers'] == 'Posted 5:30 PM &middot; after start' and st['Pittsburgh Steelers'] == 'Posted 5:30 PM &middot; after start')
    check(f'{tag}: CP-10 posted_at before a game began is that pick\'s lock time', st['Indiana Fever'] == '5:30 PM &middot; locked')
    lines = [x for x in re.split(r'<span class="lkbr">.*?</span>', raw['Philadelphia Flyers']) if x]
    check(f'{tag}: CP-10 the late stamp breaks into two lines on phones, neither longer than "12:30 PM · locked" ({lines})',
          lines == ['Posted 5:30 PM', 'after start'] and max(len(x) for x in lines) <= len('12:30 PM \u00b7 locked')
          and re.search(r'@media \(max-width:600px\)\{[^}]*\.oddslock \.lkbr\{display:block;height:0;overflow:hidden\}', page) is not None)
    gp1, gp2 = GAME_PAGES.get('game-1.html', ''), GAME_PAGES.get('game-2.html', '')
    gst = re.search(r'class="oddslock">(.*?)</span></div>', gp1)
    check(f'{tag}: CP-10 the game page wears the same short late stamp and phone line break',
          bool(gst) and gst.group(1) == 'Posted 5:30 PM<span class="lkbr"> &middot; </span>after start'
          and re.search(r'@media \(max-width:600px\)\{[^}]*\.oddslock \.lkbr\{display:block;height:0;overflow:hidden\}', gp1) is not None
          and 'class="oddslock">5:30 PM &middot; locked<' in gp2)

    # 3. normal MLB card with card_ts: Dingers stays on the MLB tab, lock stamp unchanged
    rc, page, log = build(B, card([SOX], record='1-15'), FRESH)
    n_ding = len(re.findall(r'slates/wooder_dingers\.json', page))
    ding_at = page.find('slates/wooder_dingers.json')
    check(f'{tag}: CP-02 MLB card keeps Dingers on the Wooder tab only',
          n_ding == 1 and 'id="st-ding"' not in page and page.rfind('<div class="state"', 0, ding_at) == page.find('<div class="state" id="st-wooder"'))
    check(f'{tag}: CP-10 card_ts card keeps its lock stamp', re.findall(r'class="oddslock">([^<]*)<', page) == ['7:04 AM &middot; locked'])
    check(f'{tag}: W/L popover rounds the 6.25% tie half-up like the client (6.3%)', 'id="rpWlPct">W/L: 6.3%<' in page and 'id="rpNavPct">6.25%<' in page)

    # 4. away-cover spread from the pipeline manifest (line -4 = home spread) beside a home spread, in a parlay
    rc, page, log = build(B, card([LYNX, dict(MERCURY, num=2)], parlay={'legs': ['Lynx +4', 'Mercury -4.5'], 'note': ''}), FRESH)
    lynx, gp = row(page, 'Minnesota Lynx'), GAME_PAGES.get('game-1.html', '')
    check(f'{tag}: away spread card builds', rc == 0 and len(page) > 10000 and bool(gp))
    check(f'{tag}: away spread row carries the picked side\'s own line (data-line="4", not the home -4)',
          'data-side="away" data-market="spread" data-line="4"' in lynx)
    legs = re.findall(r'<li class="cxleg"[^>]*>', page)
    check(f'{tag}: away spread combo leg carries data-line="4"',
          any('data-away="Minnesota Lynx"' in l and 'data-side="away" data-market="spread" data-line="4"' in l for l in legs))
    gpick = re.search(r'<div class="pick"[^>]*>', gp)
    check(f'{tag}: away spread game page carries data-line="4"', bool(gpick) and 'data-side="away"' in gpick.group(0)
          and 'data-market="spread" data-line="4"' in gpick.group(0))
    check(f'{tag}: away spread prices its away chips from the +4 quotes (DK -110, HR -115)',
          'SP_LYNX_DK' in lynx and 'DK -110' in lynx and 'SP_LYNX_HR' in lynx and 'SP_LIB_DK' not in lynx)
    m = re.search(r'data-line="([^"]+)"', lynx)
    finals = [[85, 84], [82, 84], [80, 84], [70, 84]]
    want = [{'WON': 'W', 'LOST': 'L', 'PUSH': 'P'}[RF.score_result('spread', 'away', LYNX['line'], a, h)] for a, h in finals]
    check(f'{tag}: record_final grades Lynx +4 (home line -4) W, W, P, L on 85-84, 82-84, 80-84, 70-84', want == ['W', 'W', 'P', 'L'])
    ix, gv = page_verdicts(page, gp, 'away', m.group(1) if m else '', finals)
    check(f'{tag}: Home row and combo verdict match the record on every final (got {ix})', ix == want)
    check(f'{tag}: game page verdict matches the record on every final (got {gv})', gv == want)

    # 5. the PT day rolls to an empty card: the numbered game pages rebuild from the last card's snapshot,
    #    and each reads ITS OWN card's posted_at, never the building card's
    DEV_E = dict(DEVILS, game=dict(DEVILS['game'], eid='401990101'), card_ts='2099-10-01T17:30:00-07:00')
    MERC_E = dict(MERCURY, game=dict(MERCURY['game'], eid='401990102'), card_ts='2099-10-01T17:30:00-07:00')
    seed = {'game-1.html': '<div class="pick" data-eid="401990101"></div>', 'game-2.html': '<div class="pick" data-eid="401990102"></div>',
            # build_manifest's late card: card_ts and posted_at 5:30 PM PT Oct 1, after the 4 PM Devils start
            'manifests/manifest-2099-10-01.json': json.dumps(card([DEV_E, MERC_E], posted_at='2099-10-02T00:30:00Z'))}
    gstamp = lambda f: (lambda m: re.sub(r'<[^>]+>', '', m.group(1)) if m else None)(re.search(r'class="oddslock">(.*?)</span></div>', GAME_PAGES.get(f, '')))
    rc, page, log = build(B, card([], date='2099-10-02', date_label='Friday, Oct 2'), FRESH, seed=seed)
    got = [gstamp('game-1.html'), gstamp('game-2.html')]
    check(f'{tag}: rolled day: the last card\'s game pages keep their own "after start" (got {got})',
          got == ['Posted 5:30 PM &middot; after start', '5:30 PM &middot; locked'])
    seed2 = dict(seed, **{'manifests/manifest-2099-10-01.json': json.dumps(card([dict(DEV_E, card_ts='2099-10-01T08:00:00-07:00'),
                                                                                 dict(MERC_E, card_ts='2099-10-01T08:00:00-07:00')]))})
    rc, page, log = build(B, card([], date='2099-10-02', date_label='Friday, Oct 2', posted_at='2099-10-02T16:00:00Z'), FRESH, seed=seed2)
    got = [gstamp('game-1.html'), gstamp('game-2.html')]
    check(f'{tag}: rolled day: an empty card\'s posted_at never stamps the last card\'s game pages (got {got})',
          got == ['8:00 AM &middot; locked', '8:00 AM &middot; locked'])
    # r3 review: on the last card's snapshot too, a pick is stamped from its own card_ts (Devils carded
    # 8:00 AM, before its 4 PM start, though the card was last posted at 5:30 PM), and a pick with no
    # card_ts from its card's posted_at - never from another pick's earlier card_ts
    MERC_NOTS = {k: v for k, v in MERC_E.items() if k != 'card_ts'}
    seed3 = dict(seed, **{'manifests/manifest-2099-10-01.json': json.dumps(card([dict(DEV_E, card_ts='2099-10-01T08:00:00-07:00'), MERC_NOTS],
                                                                                posted_at='2099-10-02T00:30:00Z'))})
    rc, page, log = build(B, card([], date='2099-10-02', date_label='Friday, Oct 2'), FRESH, seed=seed3)
    got = [gstamp('game-1.html'), gstamp('game-2.html')]
    check(f'{tag}: rolled day: the snapshot\'s picks read their own card_ts, else its posted_at (got {got})',
          got == ['8:00 AM &middot; locked', '5:30 PM &middot; locked'])

    # 6. a pick added to the card later (r3 review, shapes-1/addpick): each pick is stamped from its OWN
    #    card_ts, never the card's posted_at (the newest card_ts) or its earliest card_ts. Yankees ML was
    #    carded at 9:00 AM PT for a 1:05 PM first pitch and Dodgers ML added at 4:00 PM PT; posted_at is
    #    4:00 PM. Rays ML was added at 4:00 PM for a game that began at 1:10 PM: after start.
    YANKS = dict(SOX, num=1, name='Yankees ML', sub='BOS @ NYY', side='home', odds='-150', card_ts='2099-10-01T09:00:00-07:00',
                 game={'away': 'Boston Red Sox', 'home': 'New York Yankees', 'commence': '2099-10-01T20:05Z', 'eid': '401990201'})
    DODG = dict(SOX, num=2, name='Dodgers ML', sub='SD @ LAD', side='home', odds='-140', card_ts='2099-10-01T16:00:00-07:00',
                game={'away': 'San Diego Padres', 'home': 'Los Angeles Dodgers', 'commence': '2099-10-02T02:10Z', 'eid': '401990202'})
    RAYS = dict(SOX, num=3, name='Rays ML', sub='TB @ TOR', side='away', odds='+120', card_ts='2099-10-01T16:00:00-07:00',
                game={'away': 'Tampa Bay Rays', 'home': 'Toronto Blue Jays', 'commence': '2099-10-01T20:10Z', 'eid': '401990203'})
    ADD = [ml_entry('Boston Red Sox', 'New York Yankees', '2099-10-01T20:05Z', -150, 130, 'ML_NYY'),
           ml_entry('San Diego Padres', 'Los Angeles Dodgers', '2099-10-02T02:10Z', -140, 120, 'ML_LAD'),
           ml_entry('Tampa Bay Rays', 'Toronto Blue Jays', '2099-10-01T20:10Z', -140, 120, 'ML_TB')]
    def gp_stamp(away):  # the game page carrying this game (pages are numbered in card display order)
        gp = next((h for h in GAME_PAGES.values() if re.search(r'<div class="pick"[^>]*data-away="%s"' % re.escape(away), h)), '')
        m = re.search(r'class="oddslock">(.*?)</span></div>', gp)
        return re.sub(r'<[^>]+>', '', m.group(1)) if m else None
    rc, page, log = build(B, card([YANKS, DODG, RAYS], posted_at='2099-10-01T23:00:00Z'), ADD)
    ist = {a: (lambda m: re.sub(r'<[^>]+>', '', m.group(1)) if m else None)(re.search(r'class="oddslock">(.*?)</span></a>', row(page, a)))
           for a in ('Boston Red Sox', 'San Diego Padres', 'Tampa Bay Rays')}
    gst = [gp_stamp(a) for a in ('Boston Red Sox', 'San Diego Padres', 'Tampa Bay Rays')]
    want = ['9:00 AM &middot; locked', '4:00 PM &middot; locked', 'Posted 4:00 PM &middot; after start']
    check(f'{tag}: added pick: each index stamp is its own card_ts (got {list(ist.values())})', rc == 0 and list(ist.values()) == want)
    check(f'{tag}: added pick: each game page stamp is its own card_ts, the same as the index (got {gst})', gst == want)
    # a card with no card_ts on any pick still reads posted_at (section 2), and a pick with no card_ts on
    # a card whose other picks carry one reads posted_at too
    NOTS = {k: v for k, v in RAYS.items() if k != 'card_ts'}
    rc, page, log = build(B, card([YANKS, NOTS], posted_at='2099-10-01T23:00:00Z'), ADD)
    ist = [(lambda m: re.sub(r'<[^>]+>', '', m.group(1)) if m else None)(re.search(r'class="oddslock">(.*?)</span></a>', row(page, a)))
           for a in ('Boston Red Sox', 'Tampa Bay Rays')]
    gst = [gp_stamp(a) for a in ('Boston Red Sox', 'Tampa Bay Rays')]
    check(f'{tag}: a pick with no card_ts reads the card\'s posted_at, on the index and its game page (got {ist}, {gst})',
          ist == gst == ['9:00 AM &middot; locked', 'Posted 4:00 PM &middot; after start'])

    # DI-18: a manifest stamped before the polymarket-cents exclusion still verifies; a mismatch still fails closed
    hf = None
    for node in ast.parse(open(B).read()).body:
        if isinstance(node, ast.FunctionDef) and node.name == '_pick_content_hash':
            import hashlib as _h; ns = {'json': json, '_hl': _h, 'hashlib': _h}
            exec(compile(ast.Module(body=[node], type_ignores=[]), B, 'exec'), ns); hf = ns['_pick_content_hash']
    poly = dict(copy.deepcopy(DEVILS), polymarket={'url': 'https://polymarket.com/event/nhl-phi-njd-2099-10-01', 'cents': 61},
                polymarket_us={'url': 'https://polymarket.us/sports/nhl/nhl-phi-njd-2099-10-01', 'cents': 60, 'verified': True})
    m = card([poly])
    try: m['pick_content_hash'] = hf(m, legacy=True)
    except TypeError: m['pick_content_hash'] = hf(m)
    rc, page, log = build(B, m, FRESH)
    check(f'{tag}: DI-18 a legacy-stamped manifest still builds', rc == 0 and 'BUILD FAILED' not in log)
    m['pick_content_hash'] = 'f' * 64
    rc, page, log = build(B, m, FRESH)
    check(f'{tag}: DI-18 a declared hash that matches neither canonicalization fails closed (exit 3)', rc == 3 and 'manifest integrity' in log)

    # W/L percent parity sweep: builder formatter vs the page's JS toFixed, every record up to 120-120
    fn = None
    for node in ast.parse(open(B).read()).body:
        if isinstance(node, ast.FunctionDef) and node.name == '_pct_half_up':
            ns = {}; exec(compile(ast.Module(body=[node], type_ignores=[]), B, 'exec'), ns); fn = ns['_pct_half_up']
    if fn is None:
        check(f'{tag}: _pct_half_up formatter present', False)
    else:
        js = subprocess.run(['node', '-e', 'const o=[];for(let w=0;w<=120;w++)for(let l=0;l<=120;l++){if(w+l>0)o.push((100*w/(w+l)).toFixed(2)+"|"+(100*w/(w+l)).toFixed(1));}console.log(o.join(","));'],
                            capture_output=True, text=True).stdout.strip().split(',')
        py = [fn(w, l, 2) + '|' + fn(w, l, 1) for w in range(121) for l in range(121) if w + l > 0]
        check(f'{tag}: W/L percent matches the client toFixed for every record up to 120-120 (1 and 2 dp)', js == py)

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
