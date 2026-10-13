#!/usr/bin/env python3
"""C-3: no page price comes through an anonymous third-party CORS relay. The client Kalshi tick fetched each market
through a free public proxy and wrote whatever came back into the price chip (only a 1-99c range check, no read
time, failures swallowed), and the futures detail sheet did the same for non-seeded Kalshi rows. Both are gone:
 - no generator or template (scripts/, previews/) and no tracked served page names a public CORS relay;
 - a built index page carries no client Kalshi tick and no browser request to the Kalshi API: a Kalshi chip keeps
   the built price (data-cents, its label), which the page's own rebuild refresh replaces from this origin;
 - a built game page's live-market footer no longer claims a 60-second Kalshi tick;
 - a futures row with a Kalshi ticker that is not a seeded, server-read quote says the live price is unavailable
   instead of fetching one through a relay.
Builds real cards with each builder twin in a throwaway tree, network sent to a dead proxy.
Run: python3 scripts/test_c3_no_cors_proxy.py [builder.py ...]   (default: both twins)"""
import copy, json, os, re, shutil, subprocess, sys, tempfile

from fixtures.card_contract import stamped, market, published_snapshot

SD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SD)
BUILDERS = [os.path.abspath(a) for a in sys.argv[1:]] or [os.path.join(SD, 'build_gh_page_v2.py'), os.path.join(SD, '_build_nocanon_v2.py')]
DEAD = 'http://127.0.0.1:9'
SELF = os.path.relpath(os.path.abspath(__file__), ROOT)
# public CORS relays, built from parts so this file never names one itself
RELAYS = re.compile('|'.join(re.escape(a + b) for a, b in (('allorigins', '.win'), ('api.code', 'tabs.com'), ('corsproxy', '.io'),
                                                          ('cors-', 'anywhere'), ('thing', 'proxy'))), re.I)
failures = 0

def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or detail == '' else '  [' + str(detail)[-400:] + ']'))
    if not ok:
        failures += 1

tracked = [f for f in subprocess.run(['git', '-C', ROOT, 'ls-files'], capture_output=True, text=True).stdout.split('\n') if f]
src_hits, page_hits = [], []
for f in tracked:
    if f == SELF or not f.endswith(('.py', '.html', '.js')):
        continue
    try:
        text = open(os.path.join(ROOT, f), encoding='utf-8').read()
    except (UnicodeDecodeError, OSError):
        continue
    if RELAYS.search(text):
        (page_hits if '/' not in f else src_hits).append(f)
check('C-3 no generator, template or script names a public CORS relay', not src_hits, src_hits)
check('C-3 no tracked served page names a public CORS relay (pages rebuilt from the builder)', not page_hits, page_hits)

def build(builder, manifest, futures=None):
    d = tempfile.mkdtemp(prefix='rp-c3-')
    try:
        os.makedirs(os.path.join(d, 'scripts')); os.makedirs(os.path.join(d, 'slates'))
        bsrc = os.path.dirname(builder)
        shutil.copy(builder, os.path.join(d, 'scripts', 'build_gh_page_v2.py'))
        for f in ('index_v2.js', 'index_v2.css', 'game_page_template.html', 'team_page_template.html', 'poly_us.py'):
            shutil.copy(os.path.join(bsrc if os.path.exists(os.path.join(bsrc, f)) else SD, f), os.path.join(d, 'scripts', f))
        for f in ('feed_arbiter.js', 'feed_registry.json', 'config_leagues.json'):
            shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
        if futures is not None:
            json.dump(futures, open(os.path.join(d, 'futures.json'), 'w'))
        manifest = dict(manifest, picks=[market(p) for p in manifest.get('picks', [])])
        manifest = stamped(builder, manifest)
        json.dump(manifest, open(os.path.join(d, 'manifest.json'), 'w'), indent=1)
        published_snapshot(d, builder, manifest)
        json.dump([], open(os.path.join(d, 'slates', 'odds_prefill.json'), 'w'))
        env = dict(os.environ, RP_REFRESH='1', http_proxy=DEAD, https_proxy=DEAD, HTTP_PROXY=DEAD, HTTPS_PROXY=DEAD,
                   NO_PROXY='', no_proxy='', TZ='America/Los_Angeles')
        env.pop('RP_PUBLISH', None)
        r = subprocess.run([sys.executable, os.path.join(d, 'scripts', 'build_gh_page_v2.py'), 'manifest.json', 'index.html'],
                           cwd=d, env=env, capture_output=True, text=True, timeout=600)
        pages = {}
        for f in os.listdir(d):
            if f.endswith('.html'):
                pages[f] = open(os.path.join(d, f), encoding='utf-8').read()
        return r.returncode, r.stdout + r.stderr, pages
    finally:
        shutil.rmtree(d, ignore_errors=True)

BASE = {'date': '2099-10-04', 'date_label': 'Sunday, Oct 4', 'updated': 'fixture', 'record': '21-11', 'units_pl': '+4.76u',
        'units_ledger': None, 'yesterday': '', 'status_note': '', 'preview': False, 'parlay': None, 'posted_at': '2099-10-04T15:00:00Z'}
PICK = {'num': 1, 'name': 'Bills ML', 'market_class': 'ml', 'sub': 'fixture - model 66.0', 'odds': '-150', 'card_american': -150,
        'units': '5u', 'side': 'home',
        'game': {'away': 'New England Patriots', 'home': 'Buffalo Bills', 'commence': '2099-10-04T20:25:00Z', 'eid': '401999999'},
        'espn_league': 'football/nfl', 'league': 'NFL', 'best_book': 'Kalshi', 'card_source': 'Kalshi ask at lock'}

for B in BUILDERS:
    tag = os.path.basename(B)
    m = copy.deepcopy(BASE); m['picks'] = [copy.deepcopy(PICK)]
    rc, out, pages = build(B, m)
    index = pages.get('index.html', '')
    check(f'{tag}: C-3 the card builds', rc == 0 and bool(index), out[-500:])
    chips = re.findall(r'<a [^>]*data-book="KAL"[^>]*data-kalticker="[^"]*"[^>]*>', index)
    check(f'{tag}: C-3 the index page carries its Kalshi chip at the built price', bool(chips) and all('data-cents="60"' in c for c in chips), chips[:2])
    check(f'{tag}: C-3 the index page names no public CORS relay', not RELAYS.search(index))
    check(f'{tag}: C-3 the index page has no client Kalshi tick and no browser request to the Kalshi API',
          'function rpKalTick' not in index and 'api.elections.kalshi.com' not in index)
    games = {k: v for k, v in pages.items() if k.startswith('game-')}
    check(f'{tag}: C-3 a game page is built', bool(games), sorted(pages))
    for k, gp in games.items():
        check(f'{tag}: C-3 {k} has no client Kalshi tick, no relay and no Kalshi API request',
              'function rpKalTick' not in gp and not RELAYS.search(gp) and 'api.elections.kalshi.com' not in gp)
        check(f'{tag}: C-3 {k} footer claims no 60-second Kalshi tick', 'Kalshi ticks every 60s' not in gp)
    # the futures detail sheet: a Kalshi row that is not a seeded quote
    src = open(B, encoding='utf-8').read()
    check(f'{tag}: C-3 the futures sheet code fetches no Kalshi market through a relay',
          not RELAYS.search(src) and "var u2='https://api.elections.kalshi.com" not in src)

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
