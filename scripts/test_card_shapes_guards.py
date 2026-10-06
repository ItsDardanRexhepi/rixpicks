#!/usr/bin/env python3
"""Builder guard fixture (Oct 1 sweep, builder review of the card-shape commit): three guards that
no test failed without.
 1. No lock pin without provenance: an approved publish (RP_PUBLISH=1) of a card with no pin,
    entry_locked, posted_at or card_ts must not seed the shipped ledger's __card__ pin from
    manifest.updated; otherwise every later refresh reads '8:42 AM - locked' from that pin.
 2. A combo with a spread/total/prop leg never gets a sportsbook combo price multiplied out of
    moneyline prefill prices ([Mercury -4.5, Devils ML] priced DK +126 from the moneylines).
 3. The shipped ledger keys a non-moneyline pick by class and line: a spread chip with no live
    link never inherits the moneyline link and price shipped under the game key.
Builds real cards with each builder twin in a throwaway tree, network blocked (dead proxy).
Run: python3 scripts/test_card_shapes_guards.py [builder.py ...]   (default: both twins)"""
import copy, json, os, re, shutil, subprocess, sys, tempfile

SD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SD)
BUILDERS = [os.path.abspath(a) for a in sys.argv[1:]] or [os.path.join(SD, 'build_gh_page_v2.py'), os.path.join(SD, '_build_nocanon_v2.py')]
DEAD = 'http://127.0.0.1:9'
failures = 0

def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or not detail else '  [' + str(detail)[:300] + ']'))
    if not ok:
        failures += 1

def tree(builder):
    d = tempfile.mkdtemp(prefix='rp-guards-')
    os.makedirs(os.path.join(d, 'scripts')); os.makedirs(os.path.join(d, 'slates'))
    bsrc = os.path.dirname(builder)
    shutil.copy(builder, os.path.join(d, 'scripts', 'build_gh_page_v2.py'))
    for f in ('index_v2.js', 'index_v2.css', 'game_page_template.html', 'team_page_template.html', 'poly_us.py'):
        shutil.copy(os.path.join(bsrc if os.path.exists(os.path.join(bsrc, f)) else SD, f), os.path.join(d, 'scripts', f))
    for f in ('feed_arbiter.js', 'feed_registry.json', 'config_leagues.json'):
        shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
    return d

from fixtures.card_contract import stamped, market, published_snapshot

def build(d, manifest, prefill, shipped=None, **env_extra):
    builder=os.path.join(d,"scripts","build_gh_page_v2.py")
    manifest=stamped(builder,manifest)
    published_snapshot(d,builder,manifest)
    json.dump(manifest, open(os.path.join(d, 'manifest.json'), 'w'), indent=1)
    json.dump(prefill, open(os.path.join(d, 'slates', 'odds_prefill.json'), 'w'))
    if shipped is not None:
        json.dump(shipped, open(os.path.join(d, 'shipped_books.json'), 'w'), indent=1)
    env = dict(os.environ, RP_REFRESH='1', http_proxy=DEAD, https_proxy=DEAD, HTTP_PROXY=DEAD, HTTPS_PROXY=DEAD, **env_extra)
    r = subprocess.run([sys.executable, os.path.join(d, 'scripts', 'build_gh_page_v2.py'), 'manifest.json', 'index.html'],
                       cwd=d, env=env, capture_output=True, text=True, timeout=600)
    p = os.path.join(d, 'index.html')
    return r.returncode, (open(p).read() if os.path.exists(p) else ''), r.stderr

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
                                       'away': {'price': -110, 'point': 4.5, 'link': 'https://sportsbook.draftkings.com/?outcomes=SP_FEVER_DK'}}}}

def ml_entry(away, home, commence, hml, aml, tag):
    return {'away': away, 'home': home, 'commence': commence, 'books': {'draftkings': {
        'home_ml': hml, 'away_ml': aml, 'event': 'https://sportsbook.draftkings.com/event/' + tag,
        'home_link': 'https://sportsbook.draftkings.com/?outcomes=%s_HOME' % tag, 'away_link': 'https://sportsbook.draftkings.com/?outcomes=%s_AWAY' % tag}}}
FRESH = [ml_entry('Philadelphia Flyers', 'New Jersey Devils', '2099-10-01T23:00Z', -162, 140, 'ML_DEVILS'),
         ml_entry('Indiana Fever', 'Phoenix Mercury', '2099-10-02T01:00Z', -250, 205, 'ML_MERC')]

def card(picks, **kw):
    m=copy.deepcopy(BASE);m['picks']=[market(p) for p in picks]
    for p in m['picks']: p['sub']=str(p.get('sub') or '')+' - model 95.0'
    m.update(kw);return m

for B in BUILDERS:
    tag = os.path.basename(B)

    # 1. approved publish of a card with no lock provenance, then the 15-min refresh rebuild
    d = tree(B)
    try:
        rc, page, log = build(d, card([DEVILS]), FRESH, RP_PUBLISH='1')
        check(f'{tag}: 1 publish build of a provenance-less card exits 0', rc == 0, log[-300:])
        led = json.load(open(os.path.join(d, 'shipped_books.json'))) if os.path.exists(os.path.join(d, 'shipped_books.json')) else {}
        pin = led.get('__card__') or {}
        check(f'{tag}: 1 publish seeds no __card__ lock pin from manifest.updated', '8:42' not in str(pin.get('locked') or ''), pin)
        rc, page, log = build(d, card([DEVILS]), FRESH)
        stamps = re.findall(r'class="oddslock">([^<]*)<', page)
        check(f'{tag}: 1 the next refresh claims no lock ("8:42 AM - locked" never returns)',
              rc == 0 and len(stamps) == 1 and not any('locked' in s or '8:42' in s for s in stamps), stamps)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # 2. a two-leg combo with a spread leg: the moneyline prefill must not price it
    d = tree(B)
    try:
        rc, page, log = build(d, card([DEVILS, MERCURY], parlay={'legs': ['Mercury -4.5', 'Devils ML'], 'note': ''}), FRESH)
        cx = re.findall(r'<(?:a|span) class="chip[^"]*"[^>]*data-book="DK" data-market="parlay"[^>]*>.*?</(?:a|span)>', page)
        check(f'{tag}: 2 combo with a spread leg builds a DK combo chip', rc == 0 and len(cx) >= 1, (rc, log[-200:]))
        check(f'{tag}: 2 DK combo chip is unpriced, never multiplied from moneylines (no +126)',
              bool(cx) and all('rpunpriced' in c and '+126' not in c for c in cx), cx[:1])
        rc2, page2, _ = build(d, card([DEVILS, dict(copy.deepcopy(DEVILS), num=2, name='Mercury ML', market_class='ml', side='home',
                                                    game=copy.deepcopy(MERCURY['game']), espn_league='basketball/wnba', league='WNBA')],
                                      parlay={'legs': ['Mercury ML', 'Devils ML'], 'note': ''}), FRESH)
        cx2 = re.findall(r'<(?:a|span) class="chip[^"]*"[^>]*data-book="DK" data-market="parlay"[^>]*>.*?</(?:a|span)>', page2)
        check(f'{tag}: 2 control: [Mercury ML, Devils ML] prices DK +126 from the same prefill',
              any('+126' in c for c in cx2), cx2[:1])
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # 3. the shipped ledger holds a moneyline BetMGM link for the Mercury game under the game key; the
    #    spread pick has no live BetMGM quote, so only a class+line ledger entry may fill that chip
    d = tree(B)
    try:
        gk = 'Indiana Fever|Phoenix Mercury|2099-10-02'
        shipped = {gk: {'BetMGM': {'link': 'https://sports.betmgm.com/en/sports/events/ml-merc-shipped-777', 'ml': -250,
                                   'commence': '2099-10-02T01:00Z'}}}
        rc, page, log = build(d, card([MERCURY]), FRESH, shipped=shipped)
        merc = row(page, 'Indiana Fever')
        check(f'{tag}: 3 spread card builds', rc == 0 and bool(merc), log[-200:])
        check(f'{tag}: 3 spread chip never inherits the moneyline link or price shipped under the game key',
              'ml-merc-shipped-777' not in merc and 'MGM -250' not in merc, re.findall(r'data-book="MGM"[^>]*>[^<]*', merc))
        shipped[gk + '|spread|-4.5'] = {'BetMGM': {'link': 'https://sports.betmgm.com/en/sports/events/sp-merc-shipped-778', 'ml': -112,
                                                   'commence': '2099-10-02T01:00Z'}}
        rc, page, log = build(d, card([MERCURY]), FRESH, shipped=shipped)
        merc = row(page, 'Indiana Fever')
        check(f'{tag}: 3 control: the class+line ledger entry does fill the spread chip',
              'sp-merc-shipped-778' in merc and 'ml-merc-shipped-777' not in merc, re.findall(r'data-book="MGM"[^>]*>[^<]*', merc))
    finally:
        shutil.rmtree(d, ignore_errors=True)

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
