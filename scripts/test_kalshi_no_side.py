#!/usr/bin/env python3
"""Explicit Kalshi market + side fixture (Oct 2: the Under 6.5 on STL @ DAL is the NO side of the Kalshi
market "Over 6.5 goals", KXNHLTOTAL-26OCT02STLDAL-7, YES ask 44c / NO ask 57c). The builder priced Kalshi
chips only from a team-matched market's YES ask, so the Under would have worn the Over's 44c (or failed to
resolve: a total has no team text) and shipped with no kalshi block at all.
A pick's kalshi block may now name its exact market and side:
    kalshi: {url, ticker: '<full market ticker>', side: 'no'|'yes', cents, gate_cents}
Builds real cards with each builder twin in a throwaway tree, the network replaced by canned Kalshi
responses (sitecustomize stub; every other host fails fast, nothing leaves the machine), and checks:
 A. a NO-side total resolves to that market's NO ask: chip 'KAL -133', data-cents 57, data-kalpx="no", and
    data-kalticker/data-kalside rebuild the exact market ticker; the market record names (event, market,
    side); the game page row shows the same price and side, never the YES-ask board.
 B. the YES side of the same market still reads the YES ask (44c, +127); an explicit YES moneyline keeps
    the both-sides board when the board's picked-side market is that ticker.
 C. the ship ceiling compares the SAME side's ask: NO 57 vs gate 57 ships, NO 58 vs gate 57 fails (exit 3)
    although the YES ask sits under the gate, and a YES ask above the gate never fails a NO pick.
 D. an unresolved explicit market (no market, a zero ask) takes the unchanged unresolved path: pre-game
    hard fail, in play the pinned snapshot.
 E. an old team-matched pick (kalshi.ticker present, no side - every build_manifest pick since Sep 29) is
    unchanged: same chip markup beside an explicit pick as alone, team-matched suffix, YES ask, no
    data-kalpx (the single-market endpoint is poisoned at 99c), and a card without an explicit pick
    emits the original YES-only client tick on the index and its game pages.
 F. the client tick (node, no DOM library) fetches the exact market and reads no_ask for a data-kalpx="no"
    chip, the YES ask for a chip without it, and settles a NO chip as won on result 'no'; the game page
    tick reads no_ask too.
 G. a malformed explicit side fails the build (exit 3); build_manifest.py carries kalshi.side into the
    manifest pick (only when given, yes|no only) and the page built from that manifest prices the NO ask.
 H. a game carrying a moneyline and a NO-side total, in play: the total's game page reads its own shipped pin
    (market class + line + market + side key, 57c NO) and never the moneyline's game-key pin (41c); the
    moneyline's page keeps it.
 I. side vs lock at pre-game publish (lock = kalshi.cents, tolerance 6c): the Oct 2 card ships; an Under declared
    YES or an Over declared NO on an "Over 6.5" market fails (and the reverse on an "Under 6.5" market); a title
    naming no single direction is not read; a picked ask past 6c from the lock fails (the neighbouring line at
    18c, a 7c move), 6c ships; the other side's ask sitting closer to the lock fails (a tie ships); refresh,
    in-play, settled and display-only builds keep their existing paths.
 J. an explicit ticker that is not a market of the url's event (another event, a prefix, no url, a series-level
    url that names no event, a market-level url) fails (exit 3); an event url with a slug segment binds; an old
    pick is not held to it.
 K. build_gh_page.py (the v1 preview builder) and its preview overlay copy (the file card_chain_preview.sh
    actually runs, after copying previews/overlay over scripts/) refuse any pick whose kalshi block names a side
    (exit 3) and still build a card without one.
 L. two explicit props on one game and one line: the approved publish writes one Kalshi pin per market + side;
    in play each game page wears its own pin and market record, never the other prop's, and never a shared
    class-key slot (with no pin of its own it wears its lock).
 M. a moneyline's side is bound to its team at pre-game publish: Toronto declared NO on Toronto's own near-even
    market fails (the lock checks cannot see it), YES on the opponent's market fails, NO on the opponent's
    market ships only on a two-way event, a YES naming both teams fails; same-city teams bind through
    kalshi.team (the market code), and an unbindable market fails.
 P. the original intent end to end: a + run line (White Sox +1.5 = NO on "Houston wins by over 1.5") prices its
    NO ask on the chip, market record, game page and client tick; the YES side (Astros -1.5) reads the YES ask;
    the + line declared YES on the opponent's market fails.
Run: python3 scripts/test_kalshi_no_side.py [builder.py ...]   (default: both twins)
"""
import copy, datetime, hashlib, json, os, re, shutil, subprocess, sys, tempfile, warnings
warnings.simplefilter("ignore", SyntaxWarning)

SD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SD)
BUILDERS = [os.path.abspath(a) for a in sys.argv[1:]] or [os.path.join(SD, 'build_gh_page_v2.py'), os.path.join(SD, '_build_nocanon_v2.py')]
failures = 0
def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or not detail else '  [' + str(detail)[-600:] + ']'))
    if not ok: failures += 1

DEAD = 'http://127.0.0.1:9'
FAKENET = r'''
import io, json, os, re, socket, urllib.request
_ROUTES = json.load(open(os.environ['RP_FAKENET']))
class _Resp(io.BytesIO):
    status = 200
    def __enter__(self): return self
    def __exit__(self, *a): self.close()
    def getcode(self): return 200
def _fake(req, *a, **k):
    url = req.full_url if hasattr(req, 'full_url') else str(req)
    for pat, body in _ROUTES:
        if re.search(pat, url): return _Resp(json.dumps(body).encode())
    raise OSError('offline fixture: no route for ' + url)
def _blocked(*a, **k): raise OSError('offline fixture')
urllib.request.urlopen = _fake
socket.create_connection = _blocked
'''

NOW = datetime.datetime.now(datetime.timezone.utc)
FUT = (NOW + datetime.timedelta(days=2)).strftime('%Y-%m-%dT00:00Z')
PAST = (NOW - datetime.timedelta(hours=1)).strftime('%Y-%m-%dT%H:%MZ')
EV = 'KXNHLTOTAL-26OCT02STLDAL'
TK = EV + '-7'
KURL = 'https://kalshi.com/markets/kxnhltotal/' + EV.lower()
LEV = 'KXNHLGAME-26OCT02MTLTOR'
LURL = 'https://kalshi.com/markets/kxnhlgame/' + LEV.lower()
GEV = 'KXNHLGAME-26OCT02STLDAL'
GURL = 'https://kalshi.com/markets/kxnhlgame/' + GEV.lower()

def total_mkt(sfx, ya, na, **kw):
    return dict({'ticker': EV + '-' + sfx, 'title': 'Over %s goals' % sfx, 'yes_sub_title': 'Over %d.5 goals scored' % (int(sfx) - 1),
                 'yes_ask_dollars': ya, 'no_ask_dollars': na, 'status': 'active'}, **kw)
LEAFS_MKTS = [{'ticker': LEV + '-TOR', 'title': 'Toronto', 'yes_sub_title': 'Toronto', 'yes_ask_dollars': '0.50', 'no_ask_dollars': '0.51'},
              {'ticker': LEV + '-MTL', 'title': 'Montreal', 'yes_sub_title': 'Montreal', 'yes_ask_dollars': '0.51', 'no_ask_dollars': '0.50'}]

def routes(seven=None, poison=True, extra=()):
    """seven: the KXNHLTOTAL ...-7 market (None = the API has no such market). poison: the Leafs single-market
    endpoint answers 99c both sides - a team-matched pick that reached it would change its chip. extra: more
    markets answered by the single-market endpoint (a pick bound to another line of the event)."""
    rows = [total_mkt('6', '0.62', '0.39'), total_mkt('8', '0.27', '0.74')] + ([seven] if seven else [])
    r = [[r'markets\?event_ticker=' + EV + '&', {'markets': rows}]]
    if seven: r.append([r'trade-api/v2/markets/' + TK + r'(\?|$)', {'market': seven}])
    for m in extra: r.append([r'trade-api/v2/markets/' + m['ticker'] + r'(\?|$)', {'market': m}])
    r.append([r'markets\?event_ticker=' + LEV + '&', {'markets': LEAFS_MKTS}])
    for m in LEAFS_MKTS:
        r.append([r'trade-api/v2/markets/' + m['ticker'] + r'(\?|$)', {'market': dict(m, yes_ask_dollars='0.99', no_ask_dollars='0.99') if poison else m}])
    return r
SEVEN = total_mkt('7', '0.44', '0.57')

# two player props on one game and one line (L): each its own market and lock
PEV = 'KXNHLGOAL-26OCT02STLDAL'
PURL = 'https://kalshi.com/markets/kxnhlgoal/' + PEV.lower()
PTA, PTB = PEV + '-RTHOMAS1', PEV + '-JROBERTSON1'
PMA = {'ticker': PTA, 'title': 'Robert Thomas: 1+ goals', 'yes_sub_title': 'Robert Thomas', 'yes_ask_dollars': '0.38', 'no_ask_dollars': '0.64', 'status': 'active'}
PMB = {'ticker': PTB, 'title': 'Jason Robertson: 1+ goals', 'yes_sub_title': 'Jason Robertson', 'yes_ask_dollars': '0.45', 'no_ask_dollars': '0.57', 'status': 'active'}
def prop_pick(player, tk, cents, commence):
    return {'num': 1, 'name': player + ' Over 0.5 goals', 'market_class': 'prop', 'player': player, 'line': 0.5, 'sub': 'STL @ DAL',
            'odds': '+160', 'units': '5u', 'side': 'over', 'game': {'away': 'St. Louis Blues', 'home': 'Dallas Stars', 'commence': commence, 'eid': ''},
            'espn_league': 'hockey/nhl', 'league': 'NHL', 'best_book': 'Kalshi',
            'kalshi': {'url': PURL, 'ticker': tk, 'side': 'yes', 'cents': cents, 'gate_cents': cents, 'team': player}}
PROP_ROUTES = [[r'trade-api/v2/markets/' + PTA + r'(\?|$)', {'market': PMA}], [r'trade-api/v2/markets/' + PTB + r'(\?|$)', {'market': PMB}],
               [r'markets\?event_ticker=' + PEV + '&', {'markets': [PMA, PMB]}]]

# a run line (P): White Sox +1.5 is the NO side of "Houston wins by over 1.5 runs"
SEV = 'KXMLBSPREAD-26OCT03CWSHOU'
SURL = 'https://kalshi.com/markets/kxmlbspread/' + SEV.lower()
STK = SEV + '-HOU2'
HOU2 = {'ticker': STK, 'title': 'Houston wins by over 1.5 runs?', 'yes_sub_title': 'Houston wins by over 1.5 runs',
        'yes_ask_dollars': '0.35', 'no_ask_dollars': '0.66', 'status': 'active'}
SOX = {'num': 1, 'name': 'White Sox +1.5', 'market_class': 'spread', 'line': -1.5, 'sub': 'CWS @ HOU', 'odds': '-194', 'units': '5u', 'side': 'away',
       'game': {'away': 'Chicago White Sox', 'home': 'Houston Astros', 'commence': FUT, 'eid': ''},
       'espn_league': 'baseball/mlb', 'league': 'MLB', 'best_book': 'Kalshi',
       'kalshi': {'url': SURL, 'ticker': STK, 'side': 'no', 'cents': 66, 'gate_cents': 66, 'team': 'Chicago WS'}}
ASTROS = dict(copy.deepcopy(SOX), name='Astros -1.5', odds='+186', side='home',
              kalshi={'url': SURL, 'ticker': STK, 'side': 'yes', 'cents': 35, 'gate_cents': 35, 'team': 'Houston'})
def spread_routes(m=HOU2):
    return [[r'trade-api/v2/markets/' + STK + r'(\?|$)', {'market': m}]]

# same-city moneyline (M): the names alone cannot tell New York Y from New York M; kalshi.team (the market code) can
YEV = 'KXMLBGAME-26OCT03NYMNYY'
YURL = 'https://kalshi.com/markets/kxmlbgame/' + YEV.lower()
YMKTS = [{'ticker': YEV + '-NYY', 'title': 'New York M vs New York Y Winner?', 'yes_sub_title': 'New York Y', 'yes_ask_dollars': '0.52', 'no_ask_dollars': '0.49'},
         {'ticker': YEV + '-NYM', 'title': 'New York M vs New York Y Winner?', 'yes_sub_title': 'New York M', 'yes_ask_dollars': '0.49', 'no_ask_dollars': '0.52'}]
YANKS = {'num': 1, 'name': 'Yankees ML', 'market_class': 'ml', 'sub': 'NYM @ NYY', 'odds': '-108', 'units': '5u', 'side': 'home',
         'game': {'away': 'New York Mets', 'home': 'New York Yankees', 'commence': FUT, 'eid': ''},
         'espn_league': 'baseball/mlb', 'league': 'MLB', 'best_book': 'Kalshi',
         'kalshi': {'url': YURL, 'ticker': YEV + '-NYY', 'side': 'yes', 'cents': 52, 'gate_cents': 52, 'team': 'NYY'}}
YROUTES = [[r'trade-api/v2/markets/' + m['ticker'] + r'(\?|$)', {'market': m}] for m in YMKTS] + [[r'markets\?event_ticker=' + YEV + '&', {'markets': YMKTS}]]

UNDER = {'num': 1, 'name': 'Under 6.5', 'market_class': 'total', 'line': 6.5, 'sub': 'STL @ DAL', 'odds': '-133', 'units': '5u', 'side': 'under',
         'game': {'away': 'St. Louis Blues', 'home': 'Dallas Stars', 'commence': FUT, 'eid': ''},
         'espn_league': 'hockey/nhl', 'league': 'NHL', 'best_book': 'Kalshi',
         'kalshi': {'url': KURL, 'ticker': TK, 'side': 'no', 'cents': 57, 'gate_cents': 57, 'team': ''}}
OVER = dict(copy.deepcopy(UNDER), name='Over 6.5', odds='+127', side='over',
            kalshi={'url': KURL, 'ticker': TK, 'side': 'yes', 'cents': 44, 'gate_cents': 44, 'team': ''})
# build_manifest shape of an old pick: ticker present, NO side - the team-matched path
LEAFS = {'num': 2, 'name': 'Maple Leafs ML', 'market_class': 'ml', 'sub': 'MTL @ TOR', 'odds': '+100', 'units': '5u', 'side': 'home',
         'game': {'away': 'Montreal Canadiens', 'home': 'Toronto Maple Leafs', 'commence': FUT, 'eid': ''},
         'espn_league': 'hockey/nhl', 'league': 'NHL', 'best_book': 'Kalshi',
         'kalshi': {'url': LURL, 'cents': 50, 'team': 'Toronto', 'gate_cents': 50, 'ticker': LEV + '-TOR'}}
BASE = {'date_label': 'Fixture', 'updated': '', 'record': '1-0', 'units_pl': '+1.00u', 'units_ledger': None,
        'yesterday': '', 'status_note': '', 'preview': False, 'parlay': None}

def card(*picks):
    m = copy.deepcopy(BASE); m['picks'] = [copy.deepcopy(p) for p in picks]
    for i, p in enumerate(m['picks'], 1): p['num'] = i
    return m

GAME_PAGES = {}
LEDGER = {}
def build(builder, manifest, rts, refresh=False, files=None, as_name='build_gh_page_v2.py', extra_env=None):
    """files: {name: text} written at the tree root before the build (shipped_books.json, shipped_pick_hash.txt).
    as_name: the builder's file name in the tree (build_gh_page.py for the v1 preview builder).
    extra_env: more environment for the build (RP_PUBLISH=1, the only ledger writer). LEDGER holds the
    tree's shipped_books.json after the build ({} when none)."""
    d = tempfile.mkdtemp(prefix='rp-kalno-')
    try:
        os.makedirs(os.path.join(d, 'scripts')); os.makedirs(os.path.join(d, 'slates')); os.makedirs(os.path.join(d, '_net'))
        bsrc = os.path.dirname(builder)
        shutil.copy(builder, os.path.join(d, 'scripts', as_name))
        for f in ('index_v2.js', 'index_v2.css', 'game_page_template.html', 'team_page_template.html', 'poly_us.py'):
            shutil.copy(os.path.join(bsrc if os.path.exists(os.path.join(bsrc, f)) else SD, f), os.path.join(d, 'scripts', f))
        for f in ('feed_arbiter.js', 'feed_registry.json', 'config_leagues.json'):
            shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
        json.dump(manifest, open(os.path.join(d, 'manifest.json'), 'w'), indent=1)
        json.dump([], open(os.path.join(d, 'slates', 'odds_prefill.json'), 'w'))
        open(os.path.join(d, '_net', 'sitecustomize.py'), 'w').write(FAKENET)
        json.dump(rts, open(os.path.join(d, '_net', 'routes.json'), 'w'))
        for fn, body in (files or {}).items(): open(os.path.join(d, fn), 'w').write(body)
        env = dict(os.environ, http_proxy=DEAD, https_proxy=DEAD, HTTP_PROXY=DEAD, HTTPS_PROXY=DEAD, NO_PROXY='',
                   PYTHONPATH=os.path.join(d, '_net'), RP_FAKENET=os.path.join(d, '_net', 'routes.json'), PYTHONWARNINGS='ignore')
        for k in ('RP_REFRESH', 'RP_PUBLISH', 'RP_KAL_TICKER'): env.pop(k, None)
        if refresh: env['RP_REFRESH'] = '1'
        env.update(extra_env or {})
        r = subprocess.run([sys.executable, os.path.join(d, 'scripts', as_name), 'manifest.json', 'index.html'],
                           cwd=d, env=env, capture_output=True, text=True, timeout=600)
        page = open(os.path.join(d, 'index.html')).read() if os.path.exists(os.path.join(d, 'index.html')) else ''
        GAME_PAGES.clear()
        for f in os.listdir(d):
            if re.fullmatch(r'game-\d+\.html', f): GAME_PAGES[f] = open(os.path.join(d, f)).read()
        LEDGER.clear()
        try: LEDGER.update(json.load(open(os.path.join(d, 'shipped_books.json'))))
        except (OSError, ValueError): pass
        return r.returncode, page, r.stderr
    finally:
        shutil.rmtree(d, ignore_errors=True)

def kal_chips(page):
    return re.findall(r'<a class="chip[^"]*"[^>]*data-book="KAL"[^>]*>.*?</a>', page)
def chip_for(page, href):
    c = [x for x in kal_chips(page) if 'href="%s"' % href in x]
    return c[0] if len(c) == 1 else ''
def label(markup):
    return re.sub(r'<[^>]+>', '', markup).replace('★', '').strip()
def attr(markup, name):
    m = re.search(r' data-%s="([^"]*)"' % name, markup)
    return m.group(1) if m else None
def records(html_):
    m = re.search(r'let RP_MARKETS=(\[.*?\]);', html_)
    return json.loads(m.group(1)) if m else []
def kal_row(gp):
    m = re.search(r'<div class="mrow" data-book="KAL">.*?</div>', gp)
    return m.group(0) if m else ''
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

def run_tick(page, fn_name, anchors, markets):
    """Run the built page's own tick function in node with a stub DOM: anchors = [{dataset, innerHTML}],
    markets = {ticker: market}. Returns {fetched: [market tickers], anchors: [{dataset, innerHTML}]}."""
    code = '\n'.join([
        js_fn(page, 'rpC2ML'), js_fn(page, 'rpMLF'),
        'const A=%s.map(function(x){x.closest=function(){return null;};return x;});' % json.dumps(anchors),
        'const MK=%s;const fetched=[];' % json.dumps(markets),
        'var window={};var document={querySelectorAll:function(){return A;}};',
        'function rpMkt(){return null;}function rpInPlay(){return false;}function rpCxUpd(){}function rpQuoteMut(){}',
        'function fetch(u){const inner=decodeURIComponent(String(u).split("url=")[1]||"");const t=inner.split("/markets/")[1].split("?")[0];'
        'fetched.push(t);return Promise.resolve({json:function(){return Promise.resolve({market:MK[t]});}});}',
        js_fn(page, fn_name),
        fn_name + '();',
        'setTimeout(function(){console.log(JSON.stringify({fetched:fetched,anchors:A.map(function(a){return {dataset:a.dataset,innerHTML:a.innerHTML};})}));},30);'])
    r = subprocess.run(['node', '-e', code], capture_output=True, text=True, timeout=60)
    try: return json.loads(r.stdout)
    except ValueError: return {'error': r.stderr[-800:]}

def ds(markup):
    return {k: v for k, v in re.findall(r' data-(\w+)="([^"]*)"', markup.split('>', 1)[0])}

for B in BUILDERS:
    tag = os.path.basename(B)

    # A. NO-side total, pre-game publish build (ship ceiling live): NO ask 57 vs gate 57
    rc, page, log = build(B, card(UNDER), routes(SEVEN))
    ch = chip_for(page, KURL)
    check(f'{tag}: A NO-side card builds (NO ask 57c at the 57c gate)', rc == 0 and bool(ch), log[-800:])
    check(f'{tag}: A chip shows the NO ask as American: KAL -133 (never the Over\'s 44c / +127)', label(ch) == 'KAL -133', label(ch))
    check(f'{tag}: A chip data-cents is the NO ask 57', attr(ch, 'cents') == '57', ch)
    check(f'{tag}: A chip names the side (data-kalpx="no") and its kalticker-kalside pair is the exact market ticker',
          attr(ch, 'kalpx') == 'no' and '%s-%s' % (attr(ch, 'kalticker'), attr(ch, 'kalside')) == TK, ch)
    rec = records(page)[int(attr(ch, 'mr'))] if attr(ch, 'mr') else {}
    check(f'{tag}: A market record is (event, exact market, side no) at 57c',
          (rec.get('src'), rec.get('ev'), rec.get('mkt'), rec.get('side'), rec.get('c')) == ('Kalshi', EV, TK, 'no', 57), rec)
    gp = GAME_PAGES.get('game-1.html', '')
    row = kal_row(gp)
    check(f'{tag}: A game page Kalshi row: Under 6.5, KAL -133, data-cents 57, data-kalpx no, exact market pair',
          '>Under 6.5</a>' in row and '>KAL -133</a>' in row and 'data-kalticker="%s" data-kalside="7" data-kalpx="no" data-cents="57"' % EV in row, row)
    check(f'{tag}: A game page never shows the YES-ask board for a NO pick (no data-kalmkt row; listing was available)', 'data-kalmkt="' not in gp)
    check(f'{tag}: A game page chip matches the index chip (KAL -133, data-kalpx no)',
          any(label(x) == 'KAL -133' and attr(x, 'kalpx') == 'no' for x in kal_chips(gp)))
    # F. the client ticks of this build (index + game page)
    if ch:
        t = run_tick(page, 'rpKalTick', [{'dataset': ds(ch), 'innerHTML': 'KAL -133'}], {TK: dict(SEVEN, no_ask_dollars='0.60', yes_ask_dollars='0.41')})
        a = (t.get('anchors') or [{}])[0]
        check(f'{tag}: F index tick fetches the exact market {TK} (got {t.get("fetched")})', t.get('fetched') == [TK], t)
        check(f'{tag}: F index tick reads no_ask for data-kalpx="no" (60c -> KAL -150, not the 41c YES)',
              a.get('dataset', {}).get('cents') == 60 and a.get('innerHTML') == 'KAL -150', a)
        t = run_tick(page, 'rpKalTick', [{'dataset': ds(ch), 'innerHTML': 'KAL -133'}], {TK: dict(SEVEN, result='no')})
        a = (t.get('anchors') or [{}])[0].get('dataset', {})
        check(f'{tag}: F index tick settles a NO chip as won on result "no"', a.get('won') == '1' and a.get('lost') == '', a)
        t = run_tick(page, 'rpKalTick', [{'dataset': ds(ch), 'innerHTML': 'KAL -133'}], {TK: dict(SEVEN, result='yes')})
        a = (t.get('anchors') or [{}])[0].get('dataset', {})
        check(f'{tag}: F index tick settles a NO chip as lost on result "yes"', a.get('lost') == '1' and a.get('won') == '', a)
    pr = re.search(r'<a data-kalticker[^>]*>KAL[^<]*</a>', row)
    if pr:
        t = run_tick(gp, 'rpKalTick', [{'dataset': ds(pr.group(0)), 'innerHTML': 'KAL -133'}], {TK: dict(SEVEN, no_ask_dollars='0.60', yes_ask_dollars='0.41')})
        a = (t.get('anchors') or [{}])[0]
        check(f'{tag}: F game page tick reads no_ask for the NO row (60c -> KAL -150)',
              t.get('fetched') == [TK] and a.get('dataset', {}).get('cents') == 60 and a.get('innerHTML') == 'KAL -150', t)
    else:
        check(f'{tag}: F game page NO row present for the tick', False, row)

    # B. YES side of the same market: the YES ask, unchanged reading
    rc, page, log = build(B, card(OVER), routes(SEVEN))
    ch = chip_for(page, KURL)
    check(f'{tag}: B YES-side total reads the YES ask: KAL +127, data-cents 44, data-kalpx yes',
          rc == 0 and label(ch) == 'KAL +127' and attr(ch, 'cents') == '44' and attr(ch, 'kalpx') == 'yes', log[-400:] + ch)
    row = kal_row(GAME_PAGES.get('game-1.html', ''))
    check(f'{tag}: B YES-side game page row: Over 6.5 at KAL +127', '>Over 6.5</a>' in row and '>KAL +127</a>' in row and 'data-kalpx="yes"' in row, row)
    LEAFS_YES = copy.deepcopy(LEAFS); LEAFS_YES['kalshi']['side'] = 'yes'
    rc, page, log = build(B, card(LEAFS_YES), routes(SEVEN, poison=False))
    ch = chip_for(page, LURL); gp = GAME_PAGES.get('game-1.html', '')
    check(f'{tag}: B explicit YES moneyline prices its exact market from the single-market read (data-kalpx yes, 50c)',
          rc == 0 and attr(ch, 'kalpx') == 'yes' and attr(ch, 'cents') == '50' and '%s-%s' % (attr(ch, 'kalticker'), attr(ch, 'kalside')) == LEV + '-TOR', log[-400:] + ch)
    check(f'{tag}: B explicit YES moneyline keeps the both-sides board when its ticker is the picked side\'s market',
          'data-kalmkt="%s-TOR"' % LEV in gp and 'data-kalmkt="%s-MTL"' % LEV in gp)

    # C. ship ceiling on the side's own ask
    rc, page, log = build(B, card(UNDER), routes(total_mkt('7', '0.43', '0.58')))
    check(f'{tag}: C NO ask 58c over the 57c gate fails the build (exit 3) though the YES ask is 43c',
          rc == 3 and 'BUILD FAILED: Under 6.5 Kalshi ask 58c exceeds ship-condition ceiling 57c' in log, log[-600:])
    rc, page, log = build(B, card(UNDER), routes(total_mkt('7', '0.58', '0.57')))
    check(f'{tag}: C a YES ask of 58c never fails a NO pick at its 57c NO ask', rc == 0 and label(chip_for(page, KURL)) == 'KAL -133', log[-600:])
    rc, page, log = build(B, card(UNDER), routes(SEVEN), refresh=True)
    check(f'{tag}: C refresh build of the same card ships (exit 0)', rc == 0 and label(chip_for(page, KURL)) == 'KAL -133', log[-400:])

    # D. unresolved explicit market: unchanged unresolved path
    rc, page, log = build(B, card(UNDER), routes(None))
    check(f'{tag}: D no such market pre-game: hard fail naming the exact market and side',
          rc == 3 and 'BUILD FAILED: Kalshi market unresolved for Under 6.5 market %s side no under %s' % (TK, EV) in log, log[-600:])
    rc, page, log = build(B, card(UNDER), routes(total_mkt('7', '0.44', '0.0000')))
    check(f'{tag}: D a zero NO ask is unresolved (hard fail), never a 0c or the YES ask',
          rc == 3 and 'Kalshi market unresolved for Under 6.5 market %s side no' % TK in log, log[-600:])
    U_LIVE = copy.deepcopy(UNDER); U_LIVE['game']['commence'] = PAST
    rc, page, log = build(B, card(U_LIVE), routes(None), refresh=True)
    ch = chip_for(page, KURL)
    check(f'{tag}: D in play, market gone: degrades to the pinned 57c snapshot (KAL -133), build continues',
          rc == 0 and 'IN-PLAY DEGRADE: Under 6.5 Kalshi market unresolved under %s - pinned snapshot 57c' % EV in log
          and label(ch) == 'KAL -133' and attr(ch, 'cents') == '57' and attr(ch, 'kalpx') == 'no', log[-600:] + ch)
    row = kal_row(GAME_PAGES.get('game-1.html', ''))
    check(f'{tag}: D in play, the game page snapshot row wears the pinned NO price (Under 6.5, KAL -133, data-kalpx no)',
          '>Under 6.5</a>' in row and '>KAL -133</a>' in row and 'data-kalside="7" data-kalpx="no" data-cents="57"' in row and 'pre-game snapshot' in row, row)

    # E. old team-matched pick: unchanged alone and beside an explicit pick
    rc, page_old, log = build(B, card(LEAFS), routes(SEVEN))
    old_alone = chip_for(page_old, LURL); gp_old = GAME_PAGES.get('game-1.html', '')
    check(f'{tag}: E old pick (ticker, no side) builds and stays team-matched: data-kalticker = url event, data-kalside TOR, YES ask 50c (endpoint poisoned at 99c)',
          rc == 0 and attr(old_alone, 'kalticker') == LEV and attr(old_alone, 'kalside') == 'TOR' and attr(old_alone, 'cents') == '50'
          and label(old_alone) == 'KAL -100' and 'data-kalpx' not in old_alone, log[-400:] + old_alone)
    check(f'{tag}: E a card without an explicit pick emits the original YES-only index tick and no data-kalpx',
          "if(m.result==='yes'){a.dataset.won='1'" in page_old and "if(m.result==='no'){a.dataset.lost='1'" in page_old
          and 'const d=parseFloat(m.yes_ask_dollars);if(!(d>0&&d<=1))return;' in page_old and 'kalpx' not in page_old)
    check(f'{tag}: E its game page keeps the template tick line verbatim and the both-sides board',
          'const d=parseFloat(m.yes_ask_dollars);' in gp_old and 'kalpx' not in gp_old and 'data-kalmkt="%s-TOR"' % LEV in gp_old)
    rc, page_mix, log = build(B, card(UNDER, LEAFS), routes(SEVEN))
    strip = lambda s: re.sub(r' data-mr="\d+"', '', s)
    old_mixed = chip_for(page_mix, LURL)
    check(f'{tag}: E the old chip\'s markup is identical beside an explicit pick (data-mr index aside)',
          rc == 0 and bool(old_alone) and strip(old_alone) == strip(old_mixed), old_mixed)
    t = run_tick(page_mix, 'rpKalTick', [{'dataset': ds(old_mixed), 'innerHTML': 'KAL -100'}, {'dataset': ds(chip_for(page_mix, KURL)), 'innerHTML': 'KAL -133'}],
                 {LEV + '-TOR': dict(LEAFS_MKTS[0], yes_ask_dollars='0.55', no_ask_dollars='0.46'), TK: SEVEN})
    a = t.get('anchors') or [{}, {}]
    check(f'{tag}: F on a mixed card the old chip still ticks its YES ask (55c -> KAL -122) and the NO chip its NO ask (57c)',
          sorted(t.get('fetched') or []) == sorted([LEV + '-TOR', TK]) and a[0].get('dataset', {}).get('cents') == 55
          and a[0].get('innerHTML') == 'KAL -122' and a[1].get('dataset', {}).get('cents') == 57, t)
    t = run_tick(page_mix, 'rpKalTick', [{'dataset': ds(old_mixed), 'innerHTML': 'KAL -100'}], {LEV + '-TOR': dict(LEAFS_MKTS[0], result='no')})
    a = ((t.get('anchors') or [{}])[0]).get('dataset', {})
    check(f'{tag}: F an old (YES) chip still settles lost on result "no"', a.get('lost') == '1' and a.get('won') == '', a)

    # G. malformed explicit sides fail closed
    bad = copy.deepcopy(UNDER); bad['kalshi']['side'] = 'under'
    rc, page, log = build(B, card(bad), routes(SEVEN))
    check(f'{tag}: G side "under" fails the build (exit 3)', rc == 3 and 'an explicit side needs side yes|no' in log, log[-400:])
    bad = copy.deepcopy(UNDER); bad['kalshi'].pop('ticker')
    rc, page, log = build(B, card(bad), routes(SEVEN))
    check(f'{tag}: G a side without the market ticker fails the build (exit 3)', rc == 3 and 'an explicit side needs side yes|no' in log, log[-400:])

    # H. same game, a moneyline and a NO-side total, in play: each game page reads its own shipped pin
    BLUES = {'num': 1, 'name': 'Blues ML', 'market_class': 'ml', 'sub': 'STL @ DAL', 'odds': '+144', 'units': '5u', 'side': 'away',
             'game': {'away': 'St. Louis Blues', 'home': 'Dallas Stars', 'commence': PAST, 'eid': ''},
             'espn_league': 'hockey/nhl', 'league': 'NHL', 'best_book': 'Kalshi',
             'kalshi': {'url': GURL, 'cents': 41, 'team': 'St. Louis', 'gate_cents': 41, 'ticker': GEV + '-STL'}}
    GK = 'St. Louis Blues|Dallas Stars|' + PAST[:10]
    shipped = {GK: {'Kalshi': {'link': GURL, 'cents': 41, 'commence': PAST}},
               GK + '|total|6.5|' + TK + '|no': {'Kalshi': {'link': KURL, 'cents': 57, 'commence': PAST}}}
    rc, page, log = build(B, card(BLUES, U_LIVE), routes(SEVEN), refresh=True, files={'shipped_books.json': json.dumps(shipped)})
    gp_ml, gp_tot = GAME_PAGES.get('game-1.html', ''), GAME_PAGES.get('game-2.html', '')
    row = kal_row(gp_tot)
    check(f'{tag}: H in play, the total\'s game page shows its own pinned NO price (KAL -133, 57c), not the moneyline\'s 41c (+144)',
          rc == 0 and '>Under 6.5</a>' in row and '>KAL -133</a>' in row and 'data-kalpx="no" data-cents="57"' in row
          and 'pre-game snapshot' in row and '+144' not in row, log[-600:] + row)
    m = re.search(r' data-mr="(\d+)"', row)
    rec = records(gp_tot)[int(m.group(1))] if m else {}
    check(f'{tag}: H the total\'s game page market record is (event, exact market, side no) at its own 57c pin',
          (rec.get('src'), rec.get('ev'), rec.get('mkt'), rec.get('side'), rec.get('c')) == ('Kalshi', EV, TK, 'no', 57), rec)
    row = kal_row(gp_ml)
    check(f'{tag}: H the moneyline\'s game page keeps its game-key pin (Blues, KAL +144, 41c, no data-kalpx)',
          '>St. Louis Blues</a>' in row and '>KAL +144</a>' in row and 'data-cents="41"' in row and 'kalpx' not in row, row)
    check(f'{tag}: H the index chips agree (Under KAL -133, Blues KAL +144)',
          label(chip_for(page, KURL)) == 'KAL -133' and label(chip_for(page, GURL)) == 'KAL +144', [label(x) for x in kal_chips(page)])

    # I. side vs lock sanity at pre-game publish (lock = kalshi.cents; tolerance 6c)
    rc, page, log = build(B, card(UNDER), routes(SEVEN))
    check(f'{tag}: I the Oct 2 card passes: Under 6.5, NO ask 57c, lock 57, YES 44c (KAL -133)',
          rc == 0 and label(chip_for(page, KURL)) == 'KAL -133' and 'BUILD FAILED' not in log, log[-400:])
    u = copy.deepcopy(UNDER); u['kalshi']['side'] = 'yes'
    rc, page, log = build(B, card(u), routes(SEVEN))
    check(f'{tag}: I an Under declared YES on an "Over 6.5" market fails (exit 3): an Under there is NO',
          rc == 3 and 'BUILD FAILED: Under 6.5 is the under on %s, whose YES is the over - its side is no, the kalshi block says yes' % TK in log, log[-600:])
    o = copy.deepcopy(OVER); o['kalshi'].update(side='no', cents=57, gate_cents=57)
    rc, page, log = build(B, card(o), routes(SEVEN))
    check(f'{tag}: I an Over declared NO on an "Over 6.5" market fails (exit 3) though its NO ask equals the lock',
          rc == 3 and 'BUILD FAILED: Over 6.5 is the over on %s, whose YES is the over - its side is yes, the kalshi block says no' % TK in log, log[-600:])
    UNDER_MKT = total_mkt('7', '0.57', '0.44', title='Under 7 goals', yes_sub_title='Under 6.5 goals scored')
    u = copy.deepcopy(UNDER); u['kalshi']['side'] = 'yes'
    rc, page, log = build(B, card(u), routes(UNDER_MKT))
    ch = chip_for(page, KURL)
    check(f'{tag}: I on an "Under 6.5" market the Under is YES: side yes at the 57c YES ask ships (KAL -133, data-kalpx yes)',
          rc == 0 and label(ch) == 'KAL -133' and attr(ch, 'kalpx') == 'yes', log[-400:] + ch)
    rc, page, log = build(B, card(UNDER), routes(UNDER_MKT))
    check(f'{tag}: I on an "Under 6.5" market an Under declared NO fails (exit 3)',
          rc == 3 and 'whose YES is the under - its side is yes, the kalshi block says no' in log, log[-600:])
    for title, ysub in (('St. Louis at Dallas: Total Goals', '7 or more goals'), ('Over/Under 6.5 goals', 'Over/Under 6.5 goals')):
        amb = total_mkt('7', '0.44', '0.57', title=title, yes_sub_title=ysub)
        rc, page, log = build(B, card(UNDER), routes(amb))
        check(f'{tag}: I a title naming no single direction ({title!r}) is not read: the NO Under at its lock ships',
              rc == 0 and label(chip_for(page, KURL)) == 'KAL -133', log[-400:])
    rc, page, log = build(B, card(u), routes(total_mkt('7', '0.44', '0.57', title='Total Goals', yes_sub_title='7 or more goals')))
    check(f'{tag}: I direction unread, the lock still catches a swapped side: YES 44c is 13c from the 57c lock (exit 3)',
          rc == 3 and 'BUILD FAILED: Under 6.5 Kalshi YES ask 44c on %s is 13c from the 57c lock (tolerance 6c)' % TK in log, log[-600:])
    SIX = total_mkt('6', '0.62', '0.39')
    wrong = copy.deepcopy(UNDER); wrong['kalshi']['ticker'] = EV + '-6'
    rc, page, log = build(B, card(wrong), routes(SEVEN, extra=[SIX]))
    check(f'{tag}: I a pick bound to the neighbouring line (Over 5.5, NO 39c) fails: 18c from the 57c lock (exit 3)',
          rc == 3 and 'BUILD FAILED: Under 6.5 Kalshi NO ask 39c on %s-6 is 18c from the 57c lock (tolerance 6c)' % EV in log, log[-600:])
    rc, page, log = build(B, card(UNDER), routes(total_mkt('7', '0.30', '0.51')))
    check(f'{tag}: I a NO ask 6c under the lock is inside the tolerance and ships at the lock (KAL -133)',
          rc == 0 and label(chip_for(page, KURL)) == 'KAL -133', log[-400:])
    rc, page, log = build(B, card(UNDER), routes(total_mkt('7', '0.30', '0.50')))
    check(f'{tag}: I a NO ask 7c under the lock is past the tolerance (exit 3)',
          rc == 3 and 'NO ask 50c on %s is 7c from the 57c lock (tolerance 6c)' % TK in log, log[-600:])
    swp = copy.deepcopy(LEAFS); swp['kalshi'].update(side='yes', cents=51, gate_cents=51)
    rc, page, log = build(B, card(swp), routes(SEVEN, poison=False))
    check(f'{tag}: I a 51c lock on a YES 50c / NO 51c market declared YES fails: the NO ask is the closer one (exit 3)',
          rc == 3 and 'BUILD FAILED: Maple Leafs ML NO ask 51c on %s-TOR is closer to the 51c lock than the picked YES ask 50c' % LEV in log, log[-600:])
    u = copy.deepcopy(UNDER); u['kalshi'].update(cents=50, gate_cents=51)
    rc, page, log = build(B, card(u), routes(total_mkt('7', '0.50', '0.51')))
    check(f'{tag}: I a NO pick locked at 50c on a YES 50c / NO 51c market fails: the YES ask sits on the lock (exit 3)',
          rc == 3 and 'YES ask 50c on %s is closer to the 50c lock than the picked NO ask 51c' % TK in log, log[-600:])
    LEAFS_YES_TIE = copy.deepcopy(LEAFS); LEAFS_YES_TIE['kalshi']['side'] = 'yes'
    tie = [[r'trade-api/v2/markets/' + LEV + r'-TOR(\?|$)', {'market': dict(LEAFS_MKTS[0], no_ask_dollars='0.50')}]] + routes(SEVEN, poison=False)
    rc, page, log = build(B, card(LEAFS_YES_TIE), tie)  # first matching route wins: TOR answers YES 50c / NO 50c
    check(f'{tag}: I an explicit YES at a 50c lock on a YES 50c / NO 50c market ships (a tie is not closer)',
          rc == 0 and attr(chip_for(page, LURL), 'kalpx') == 'yes' and attr(chip_for(page, LURL), 'cents') == '50', log[-400:])
    # the publish checks stay out of every non-publish path: the wrong-line pick builds and wears its lock
    for what, mf, kw in (('refresh', card(wrong), {'refresh': True}),
                         ('in play', card(dict(copy.deepcopy(wrong), game=dict(wrong['game'], commence=PAST))), {}),
                         ('settled', card(dict(copy.deepcopy(wrong), result='WIN')), {})):
        rc, page, log = build(B, mf, routes(SEVEN, extra=[SIX]), **kw)
        check(f'{tag}: I {what} build of the wrong-line pick keeps its existing path (exit 0, chip at the 57c lock)',
              rc == 0 and label(chip_for(page, KURL)) == 'KAL -133' and 'from the 57c lock' not in log, log[-600:])
    src = open(B).read(); i = src.index('def _pick_content_hash'); ns = {'json': json, '_hl': hashlib}
    exec(src[i:src.index('\n_PC_HASH=', i)], ns)
    mf = card(wrong)
    rc, page, log = build(B, mf, routes(SEVEN, extra=[SIX]), files={'shipped_pick_hash.txt': ns['_pick_content_hash'](mf) + '\n'})
    check(f'{tag}: I display-only build of the wrong-line pick keeps its existing path (exit 0, chip at the 57c lock)',
          rc == 0 and 'DISPLAY-ONLY' in log and label(chip_for(page, KURL)) == 'KAL -133' and 'from the 57c lock' not in log, log[-600:])

    # J. the explicit ticker must be a market of the url's event
    for what, url in (("another event's url", LURL), ('an event url that is only a prefix of the ticker', 'https://kalshi.com/markets/kxnhltotal/kxnhltotal-26oct02stl'),
                      ('no url', None)):
        bad = copy.deepcopy(UNDER)
        if url: bad['kalshi']['url'] = url
        else: bad['kalshi'].pop('url')
        rc, page, log = build(B, card(bad), routes(SEVEN))
        check(f'{tag}: J {what} fails the build (exit 3)',
              rc == 3 and 'BUILD FAILED: kalshi ticker %s is not a market of the url\'s event' % TK in log and not page, log[-600:])
    old = copy.deepcopy(LEAFS); old['kalshi']['ticker'] = TK
    rc, page, log = build(B, card(old), routes(SEVEN))
    check(f'{tag}: J an old pick (no side) is not held to it: a foreign ticker still builds the team-matched chip',
          rc == 0 and attr(chip_for(page, LURL), 'kalside') == 'TOR' and attr(chip_for(page, LURL), 'cents') == '50', log[-400:])
    for what, url in (('a series-level url (names no event) with another game\'s market', 'https://kalshi.com/markets/kxnhltotal'),
                      ('a series-level url with the pick\'s own market', 'https://kalshi.com/markets/kxnhltotal/'),
                      ('a market-level url', KURL + '-7')):
        bad = copy.deepcopy(UNDER); bad['kalshi']['url'] = url
        if 'another game' in what: bad['kalshi']['ticker'] = 'KXNHLTOTAL-26OCT02BOSCHI-7'
        other = dict(total_mkt('7', '0.45', '0.56'), ticker='KXNHLTOTAL-26OCT02BOSCHI-7')
        rc, page, log = build(B, card(bad), routes(SEVEN, extra=[other]))
        check(f'{tag}: J {what} fails the build (exit 3): the url must end at the event itself',
              rc == 3 and 'BUILD FAILED: kalshi ticker %s is not a market of the url\'s event' % bad['kalshi']['ticker'] in log and not page, log[-600:])
    ok_url = copy.deepcopy(UNDER); ok_url['kalshi']['url'] = 'https://kalshi.com/markets/kxnhltotal/total-goals/' + EV.lower() + '/'
    rc, page, log = build(B, card(ok_url), routes(SEVEN))
    check(f'{tag}: J an event url with a slug segment and a trailing slash still binds (KAL -133)',
          rc == 0 and label(chip_for(page, ok_url['kalshi']['url'])) == 'KAL -133', log[-400:])

    # L. two explicit props on one game and one line: each pin is its own market + side, never one shared slot
    SOON = (NOW + datetime.timedelta(hours=3)).strftime('%Y-%m-%dT%H:%MZ')
    rc, page, log = build(B, card(prop_pick('Robert Thomas', PTA, 38, SOON), prop_pick('Jason Robertson', PTB, 45, SOON)),
                          PROP_ROUTES + routes(SEVEN), extra_env={'RP_PUBLISH': '1'})
    pk = 'St. Louis Blues|Dallas Stars|' + SOON[:10] + '|prop|0.5'
    pins = {k: (v.get('Kalshi') or {}).get('cents') for k, v in LEDGER.items() if k != '__card__' and (v or {}).get('Kalshi')}
    check(f'{tag}: L the approved publish of two explicit props on one game and line writes two Kalshi pins, each under its market + side',
          rc == 0 and pins == {pk + '|' + PTA + '|yes': 38, pk + '|' + PTB + '|yes': 45}, log[-400:] + str(pins))
    PK = 'St. Louis Blues|Dallas Stars|' + PAST[:10] + '|prop|0.5'
    # in play: own pins 40 / 47 (distinct from the 38 / 45 locks), plus the shared class-key slot an earlier build wrote (45)
    led = {PK: {'Kalshi': {'link': PURL, 'cents': 45, 'commence': PAST}},
           PK + '|' + PTA + '|yes': {'Kalshi': {'link': PURL, 'cents': 40, 'commence': PAST}},
           PK + '|' + PTB + '|yes': {'Kalshi': {'link': PURL, 'cents': 47, 'commence': PAST}}}
    for refresh in (False, True):
        rc, page, log = build(B, card(prop_pick('Robert Thomas', PTA, 38, PAST), prop_pick('Jason Robertson', PTB, 45, PAST)),
                              PROP_ROUTES + routes(SEVEN), refresh=refresh, files={'shipped_books.json': json.dumps(led)})
        got = []
        for gpn, tk in (('game-1.html', PTA), ('game-2.html', PTB)):
            gp = GAME_PAGES.get(gpn, ''); row = kal_row(gp); m = re.search(r' data-mr="(\d+)"', row)
            rec = records(gp)[int(m.group(1))] if m else {}
            got.append((re.sub(r'<[^>]+>', ' ', row).split()[-3:-2], '%s-%s' % (attr(row, 'kalticker'), attr(row, 'kalside')), rec.get('mkt'), rec.get('c')))
        check(f'{tag}: L in play (refresh={refresh}) each prop\'s game page wears its own pin and market (Thomas 40c +150, Robertson 47c +113), never the shared 45c slot',
              rc == 0 and got == [(['+150'], PTA, PTA, 40), (['+113'], PTB, PTB, 47)], log[-400:] + str(got))
    rc, page, log = build(B, card(prop_pick('Robert Thomas', PTA, 38, PAST)), PROP_ROUTES + routes(SEVEN), refresh=True,
                          files={'shipped_books.json': json.dumps({PK: led[PK]})})
    row = kal_row(GAME_PAGES.get('game-1.html', ''))
    check(f'{tag}: L an explicit prop never inherits the shared class-key slot (45c): with no pin of its own it wears its 38c lock (+163)',
          rc == 0 and '>KAL +163</a>' in row and 'data-cents="38"' in row, log[-400:] + row)

    # M. moneyline side bound to the team at pre-game publish (a near-even swap passes the lock checks)
    sw = copy.deepcopy(LEAFS); sw['kalshi'].update(side='no', cents=50, gate_cents=50)
    tor = dict(LEAFS_MKTS[0], yes_ask_dollars='0.51', no_ask_dollars='0.50')
    near = [[r'trade-api/v2/markets/' + LEV + r'-TOR(\?|$)', {'market': tor}]] + routes(SEVEN, poison=False)
    rc, page, log = build(B, card(sw), near)
    check(f'{tag}: M Toronto ML declared NO on Toronto\'s own market (YES 51c / NO 50c, lock 50) fails (exit 3): its side is yes',
          rc == 3 and "BUILD FAILED: Maple Leafs ML - the YES of %s-TOR is 'Toronto', the picked team: its side is yes, the kalshi block says no" % LEV in log and not page, log[-600:])
    rc, page, log = build(B, card(sw), near, refresh=True)
    check(f'{tag}: M the same card on a refresh build keeps its existing path (publish checks only at pre-game publish)', rc == 0, log[-400:])
    nom = copy.deepcopy(LEAFS); nom['kalshi'].update(ticker=LEV + '-MTL', side='no', cents=50, gate_cents=50)
    rc, page, log = build(B, card(nom), routes(SEVEN, poison=False))
    ch = chip_for(page, LURL)
    check(f'{tag}: M Toronto ML as NO on Montreal\'s market of a two-way event ships at the NO ask (KAL -100, data-kalpx no, pair -MTL)',
          rc == 0 and label(ch) == 'KAL -100' and attr(ch, 'kalpx') == 'no' and '%s-%s' % (attr(ch, 'kalticker'), attr(ch, 'kalside')) == LEV + '-MTL', log[-400:] + ch)
    yom = copy.deepcopy(LEAFS); yom['kalshi'].update(ticker=LEV + '-MTL', side='yes', cents=51, gate_cents=51)
    rc, page, log = build(B, card(yom), routes(SEVEN, poison=False))
    check(f'{tag}: M Toronto ML declared YES on Montreal\'s market fails (exit 3): the opponent\'s YES is the pick\'s NO',
          rc == 3 and "the YES of %s-MTL is 'Montreal', the opponent: its side is no, the kalshi block says yes" % LEV in log, log[-600:])
    three = LEAFS_MKTS + [{'ticker': LEV + '-TIE', 'title': 'Tie', 'yes_sub_title': 'Tie', 'yes_ask_dollars': '0.20', 'no_ask_dollars': '0.81'}]
    rt3 = [[r'markets\?event_ticker=' + LEV + '&', {'markets': three}]] + routes(SEVEN, poison=False)
    rc, page, log = build(B, card(nom), rt3)
    check(f'{tag}: M NO on the opponent\'s market of a three-way event fails (exit 3): a NO there is not the picked team\'s win',
          rc == 3 and 'is the picked team\'s win only on a two-way event; %s lists 3 market(s)' % LEV in log, log[-600:])
    both = [[r'trade-api/v2/markets/' + LEV + r'-TOR(\?|$)', {'market': dict(LEAFS_MKTS[0], yes_sub_title='Montreal vs Toronto')}]] + routes(SEVEN, poison=False)
    unb = copy.deepcopy(LEAFS); unb['kalshi'].update(side='yes', team='')
    rc, page, log = build(B, card(unb), both)
    check(f'{tag}: M a market whose YES names both teams (and no kalshi.team) cannot bind the side: fails (exit 3)',
          rc == 3 and 'names neither team of the pick or both, so side yes cannot be bound' in log, log[-600:])
    rc, page, log = build(B, card(YANKS), YROUTES)
    ch = chip_for(page, YURL)
    check(f'{tag}: M same-city teams (New York Y / New York M): kalshi.team, the market code, binds the YES side (ships, 52c)',
          rc == 0 and attr(ch, 'kalpx') == 'yes' and attr(ch, 'cents') == '52', log[-400:] + ch)
    ym = copy.deepcopy(YANKS); ym['kalshi'].update(ticker=YEV + '-NYM', side='yes', cents=49, gate_cents=49)
    rc, page, log = build(B, card(ym), YROUTES)
    check(f'{tag}: M same-city teams: YES on the other New York market with no name or code tying it to the pick fails (exit 3)',
          rc == 3 and 'cannot be bound' in log, log[-600:])

    # P. the original intent end to end: a + run line priced from its NO ask; the YES side unchanged
    rc, page, log = build(B, card(SOX), spread_routes())
    ch = chip_for(page, SURL)
    check(f'{tag}: P White Sox +1.5 (NO on "Houston wins by over 1.5", NO 66c / YES 35c) ships at the NO ask: KAL -194, data-cents 66, data-kalpx no',
          rc == 0 and label(ch) == 'KAL -194' and attr(ch, 'cents') == '66' and attr(ch, 'kalpx') == 'no'
          and '%s-%s' % (attr(ch, 'kalticker'), attr(ch, 'kalside')) == STK, log[-400:] + ch)
    rec = records(page)[int(attr(ch, 'mr'))] if attr(ch, 'mr') else {}
    check(f'{tag}: P its market record is (event, exact market, side no) at 66c', (rec.get('ev'), rec.get('mkt'), rec.get('side'), rec.get('c')) == (SEV, STK, 'no', 66), rec)
    row = kal_row(GAME_PAGES.get('game-1.html', ''))
    check(f'{tag}: P its game page row: Chicago White Sox at KAL -194, data-kalpx no, never the YES board',
          '>Chicago White Sox</a>' in row and '>KAL -194</a>' in row and 'data-kalpx="no" data-cents="66"' in row, row)
    if ch:
        t = run_tick(page, 'rpKalTick', [{'dataset': ds(ch), 'innerHTML': 'KAL -194'}], {STK: dict(HOU2, no_ask_dollars='0.70', yes_ask_dollars='0.31')})
        a = (t.get('anchors') or [{}])[0]
        check(f'{tag}: P the client tick reads the run line\'s NO ask (70c -> KAL -233, not the 31c YES)',
              t.get('fetched') == [STK] and a.get('dataset', {}).get('cents') == 70 and a.get('innerHTML') == 'KAL -233', t)
    rc, page, log = build(B, card(ASTROS), spread_routes())
    ch = chip_for(page, SURL)
    check(f'{tag}: P Astros -1.5 (YES on the same market) still reads the YES ask: KAL +186, data-cents 35, data-kalpx yes',
          rc == 0 and label(ch) == 'KAL +186' and attr(ch, 'cents') == '35' and attr(ch, 'kalpx') == 'yes', log[-400:] + ch)
    sw = copy.deepcopy(SOX); sw['kalshi'].update(side='yes')
    rc, page, log = build(B, card(sw), spread_routes(dict(HOU2, yes_ask_dollars='0.66', no_ask_dollars='0.35')))
    check(f'{tag}: P White Sox +1.5 declared YES on Houston\'s market fails (exit 3) even when the YES ask sits on the lock',
          rc == 3 and "the YES of %s is 'Houston wins by over 1.5 runs', the opponent: its side is no, the kalshi block says yes" % STK in log, log[-600:])

# K. the v1 preview builder (card_chain_preview.sh) cannot price a side: it refuses any pick that names one
V1 = os.path.join(SD, 'build_gh_page.py')
rc, page, log = build(V1, card(LEAFS, UNDER), routes(SEVEN), as_name='build_gh_page.py')
check('K build_gh_page.py refuses a card with a kalshi.side pick (exit 3, names the pick, no page written)',
      rc == 3 and 'BUILD FAILED: kalshi.side on Under 6.5 - this builder prices Kalshi from a team-matched YES ask' in log and not page, log[-600:])
yes_only = copy.deepcopy(LEAFS); yes_only['kalshi']['side'] = 'yes'
rc, page, log = build(V1, card(yes_only), routes(SEVEN), as_name='build_gh_page.py')
check('K build_gh_page.py refuses a YES side too (it reads a team match, never the named market)',
      rc == 3 and 'BUILD FAILED: kalshi.side on Maple Leafs ML' in log and not page, log[-600:])
rc, page, log = build(V1, card(LEAFS), routes(SEVEN), as_name='build_gh_page.py')
check('K build_gh_page.py still builds a card without a side (old pick, team-matched chip)',
      rc == 0 and 'kalshi.side' not in log and 'data-book="KAL"' in page, log[-600:])
# card_chain_preview.sh runs 'cp -rf previews/overlay/. .' before it builds the preview, so the v1 builder it
# runs is the overlay copy: that copy must refuse a side too
OV1 = os.path.join(ROOT, 'previews', 'overlay', 'scripts', 'build_gh_page.py')
ccp = open(os.path.join(SD, 'card_chain_preview.sh')).read()
check('K card_chain_preview.sh applies the overlay and then builds with scripts/build_gh_page.py (the overlay copy)',
      'cp -rf previews/overlay/. .' in ccp and 'python3 scripts/build_gh_page.py' in ccp and os.path.exists(OV1))
rc, page, log = build(OV1, card(LEAFS, UNDER), routes(SEVEN), as_name='build_gh_page.py')
check('K the overlay v1 builder (card_chain_preview.sh) refuses a card with a kalshi.side pick (exit 3, no page)',
      rc == 3 and 'BUILD FAILED: kalshi.side on Under 6.5 - this builder prices Kalshi from a team-matched YES ask' in log and not page, log[-600:])
rc, page, log = build(OV1, card(LEAFS), routes(SEVEN), as_name='build_gh_page.py')
check('K the overlay v1 builder still builds a card without a side',
      rc == 0 and 'kalshi.side' not in log and 'data-book="KAL"' in page, log[-600:])

# G. build_manifest.py carries the side through to the manifest, and the page prices it
T0 = (NOW - datetime.timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ')
def bm_cand(**kal):
    c = {'num': 1, 'date': FUT[:10], 'market_class': 'total', 'line': 6.5, 'name': 'Under 6.5', 'side': 'under',
         'away': 'St. Louis Blues', 'home': 'Dallas Stars', 'commence': FUT, 'eid': '401999777', 'espn_league': 'hockey/nhl',
         'units': '5u', 'model': 62.0, 'gross_c': 5.0, 'net_c': 3.28, 'sub_context': 'STL @ DAL',
         'kalshi': dict({'cents': 57, 'team': '', 'ticker': TK, 'url': KURL}, **kal),
         'best_ask': {'venue': 'kalshi', 'price': 57, 'read_at': T0, 'compared': [{'venue': 'kalshi', 'price': 57, 'read_at': T0}]}}
    return c
def build_manifest(cands):
    d = tempfile.mkdtemp(prefix='rp-kalno-bm-')
    try:
        os.makedirs(os.path.join(d, 'ledger')); os.makedirs(os.path.join(d, 'prod'))
        cf, mf, out = (os.path.join(d, x) for x in ('cands.json', 'meta.json', 'manifest.json'))
        env = dict(os.environ, PYTHONPATH=ROOT, RIX_PICKS_LEDGER=os.path.join(d, 'ledger', 'picks.jsonl'),
                   RIX_PROD_MANIFEST=os.path.join(d, 'prod', 'manifest.json'), http_proxy=DEAD, https_proxy=DEAD, HTTP_PROXY=DEAD, HTTPS_PROXY=DEAD)
        json.dump(cands, open(cf, 'w'))
        json.dump({'record': '1-0', 'units_pl': '+1.00u', 'units_ledger': None, 'yesterday': '', 'status_note': '', 'parlay': None}, open(mf, 'w'))
        r = subprocess.run([sys.executable, os.path.join(SD, 'build_manifest.py'), cf, out, '--meta', mf], capture_output=True, text=True, env=env, timeout=120)
        return r.returncode, (json.load(open(out)) if os.path.exists(out) else None), r.stdout + r.stderr
    finally:
        shutil.rmtree(d, ignore_errors=True)
rc, man, log = build_manifest([bm_cand(side='no')])
kb = ((man or {}).get('picks') or [{}])[0].get('kalshi') or {}
check('G build_manifest carries kalshi.side "no" with the full ticker into the manifest pick',
      rc == 0 and kb.get('side') == 'no' and kb.get('ticker') == TK and kb.get('cents') == 57 and kb.get('gate_cents') == 57, log[-600:])
if man:
    for B in BUILDERS:
        brc, page, blog = build(B, man, routes(SEVEN))
        ch = chip_for(page, KURL)
        check(f'G {os.path.basename(B)}: the page built from that manifest prices the NO ask (KAL -133, data-kalpx no)',
              brc == 0 and label(ch) == 'KAL -133' and attr(ch, 'kalpx') == 'no', blog[-600:] + ch)
rc, man, log = build_manifest([bm_cand()])
kb = ((man or {}).get('picks') or [{}])[0].get('kalshi') or {}
check('G build_manifest without a side writes no side key (old picks unchanged)', rc == 0 and 'side' not in kb and kb.get('ticker') == TK, log[-600:])
rc, man, log = build_manifest([bm_cand(side='NO')])
check('G build_manifest refuses a side other than yes|no (nothing written)', rc != 0 and man is None and "kalshi side 'NO'" in log, log[-600:])

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
