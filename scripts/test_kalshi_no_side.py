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
Run: python3 scripts/test_kalshi_no_side.py [builder.py ...]   (default: both twins)
"""
import copy, datetime, json, os, re, shutil, subprocess, sys, tempfile, warnings
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

def total_mkt(sfx, ya, na, **kw):
    return dict({'ticker': EV + '-' + sfx, 'title': 'Over %s goals' % sfx, 'yes_sub_title': 'Over %d.5 goals scored' % (int(sfx) - 1),
                 'yes_ask_dollars': ya, 'no_ask_dollars': na, 'status': 'active'}, **kw)
LEAFS_MKTS = [{'ticker': LEV + '-TOR', 'title': 'Toronto', 'yes_sub_title': 'Toronto', 'yes_ask_dollars': '0.50', 'no_ask_dollars': '0.51'},
              {'ticker': LEV + '-MTL', 'title': 'Montreal', 'yes_sub_title': 'Montreal', 'yes_ask_dollars': '0.51', 'no_ask_dollars': '0.50'}]

def routes(seven=None, poison=True):
    """seven: the KXNHLTOTAL ...-7 market (None = the API has no such market). poison: the Leafs single-market
    endpoint answers 99c both sides - a team-matched pick that reached it would change its chip."""
    rows = [total_mkt('6', '0.62', '0.39'), total_mkt('8', '0.27', '0.74')] + ([seven] if seven else [])
    r = [[r'markets\?event_ticker=' + EV + '&', {'markets': rows}]]
    if seven: r.append([r'trade-api/v2/markets/' + TK + r'(\?|$)', {'market': seven}])
    r.append([r'markets\?event_ticker=' + LEV + '&', {'markets': LEAFS_MKTS}])
    for m in LEAFS_MKTS:
        r.append([r'trade-api/v2/markets/' + m['ticker'] + r'(\?|$)', {'market': dict(m, yes_ask_dollars='0.99', no_ask_dollars='0.99') if poison else m}])
    return r
SEVEN = total_mkt('7', '0.44', '0.57')

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
def build(builder, manifest, rts, refresh=False):
    d = tempfile.mkdtemp(prefix='rp-kalno-')
    try:
        os.makedirs(os.path.join(d, 'scripts')); os.makedirs(os.path.join(d, 'slates')); os.makedirs(os.path.join(d, '_net'))
        bsrc = os.path.dirname(builder)
        shutil.copy(builder, os.path.join(d, 'scripts', 'build_gh_page_v2.py'))
        for f in ('index_v2.js', 'index_v2.css', 'game_page_template.html', 'team_page_template.html', 'poly_us.py'):
            shutil.copy(os.path.join(bsrc if os.path.exists(os.path.join(bsrc, f)) else SD, f), os.path.join(d, 'scripts', f))
        for f in ('feed_arbiter.js', 'feed_registry.json', 'config_leagues.json'):
            shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
        json.dump(manifest, open(os.path.join(d, 'manifest.json'), 'w'), indent=1)
        json.dump([], open(os.path.join(d, 'slates', 'odds_prefill.json'), 'w'))
        open(os.path.join(d, '_net', 'sitecustomize.py'), 'w').write(FAKENET)
        json.dump(rts, open(os.path.join(d, '_net', 'routes.json'), 'w'))
        env = dict(os.environ, http_proxy=DEAD, https_proxy=DEAD, HTTP_PROXY=DEAD, HTTPS_PROXY=DEAD, NO_PROXY='',
                   PYTHONPATH=os.path.join(d, '_net'), RP_FAKENET=os.path.join(d, '_net', 'routes.json'), PYTHONWARNINGS='ignore')
        for k in ('RP_REFRESH', 'RP_PUBLISH', 'RP_KAL_TICKER'): env.pop(k, None)
        if refresh: env['RP_REFRESH'] = '1'
        r = subprocess.run([sys.executable, os.path.join(d, 'scripts', 'build_gh_page_v2.py'), 'manifest.json', 'index.html'],
                           cwd=d, env=env, capture_output=True, text=True, timeout=600)
        page = open(os.path.join(d, 'index.html')).read() if os.path.exists(os.path.join(d, 'index.html')) else ''
        GAME_PAGES.clear()
        for f in os.listdir(d):
            if re.fullmatch(r'game-\d+\.html', f): GAME_PAGES[f] = open(os.path.join(d, f)).read()
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
