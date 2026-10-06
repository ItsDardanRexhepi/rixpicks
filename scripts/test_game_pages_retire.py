#!/usr/bin/env python3
# Past-card game pages fixture (Oct 1 site sweep, LS-21/DI-09/LS-10). game-N.html is reused by
# every card; a number the current card does not rebuild kept serving an older card's game
# (game-5 bound a graded Sep 29 prop to the Sep 30 game, live and indexable) and
# backfill_history.py kept refreshing its hist-N.json from that market (hist-5 == hist-1).
# Runs the real builder end to end in a scratch copy of the site with a canned, offline network:
#  A. a 1-pick card retires game-2..4 (fixed notice, no event id, no market); the builder never
#     writes hist-*.json (record-final stages only the pages it rebuilds), and
#     backfill_history.py finds no market left to pull for a retired page and empties its stale
#     hist-N.json once (a second run leaves it alone)
#  B. a rebuild leaves the notices byte-identical (no commit churn every refresh)
#  C. the empty-card hold keeps the last card's page once the strays are retired
#  D. an empty card whose numbered pages match no snapshot serves no stale game page
#  E. LS-10: a prop pick carrying a game-winner Kalshi market never pastes its price on a side
# Run: python3 scripts/test_game_pages_retire.py [builder.py ...]  (default: both twins)
import datetime, json, os, re, shutil, subprocess, sys, tempfile

from fixtures.card_contract import stamped, published_snapshot

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILDERS = [os.path.basename(b) for b in sys.argv[1:]] or ['build_gh_page_v2.py', '_build_nocanon_v2.py']

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
GDAY = (NOW + datetime.timedelta(days=2)).date()
COMMENCE = GDAY.isoformat() + 'T21:00Z'
TICK = 'KXMLBGAME-%s1400CWSHOU' % GDAY.strftime('%y%b%d').upper()
KURL = 'https://kalshi.com/markets/kxmlbgame/professional-baseball-game/' + TICK.lower()
EID = '401999001'

ROUTES = [
    [r'site\.api\.espn\.com/apis/site/v2/sports/baseball/mlb/scoreboard\?dates=' + GDAY.strftime('%Y%m%d'),
     {'events': [{'id': EID, 'date': COMMENCE, 'competitions': [{'id': EID, 'status': {'type': {'state': 'pre', 'completed': False}},
        'competitors': [{'homeAway': 'away', 'team': {'id': '4', 'displayName': 'Chicago White Sox', 'abbreviation': 'CHW'}},
                        {'homeAway': 'home', 'team': {'id': '18', 'displayName': 'Houston Astros', 'abbreviation': 'HOU'}}]}]}]}],
    [r'api\.elections\.kalshi\.com/trade-api/v2/markets\?event_ticker=' + TICK + r'&',
     {'markets': [{'ticker': TICK + '-CWS', 'side':'yes', 'yes_ask_dollars': '0.42', 'yes_sub_title': 'Chicago WS', 'title': 'Chicago WS vs Houston'},
                  {'ticker': TICK + '-HOU', 'yes_ask_dollars': '0.59', 'yes_sub_title': 'Houston', 'title': 'Chicago WS vs Houston'}]}],
]

GAME = {'away': 'Chicago White Sox', 'home': 'Houston Astros', 'commence': COMMENCE, 'eid': EID}
KAL = {'url': KURL, 'cents': 42, 'team': 'Chicago WS', 'gate_cents': 42, 'ticker': TICK + '-CWS', 'side':'yes'}
ML = {'name': 'White Sox ML', 'sub': 'fixture - model 66.0', 'odds': '+138', 'units': '5u', 'side': 'away', 'market': None,
      'market_class': 'ml', 'league': 'MLB', 'espn_league': 'baseball/mlb', 'best_book': 'Kalshi',
      'game': dict(GAME), 'kalshi': dict(KAL), 'polymarket': None, 'dkp': None}
PROP = dict(ML, name='Yordan Alvarez over 1.5 hits', odds='+270', side='over', market='bat_hits', market_class='prop')

def stale_page(n, eid, tick):
    return ('<!DOCTYPE html><html><head><title>Old card game %d</title></head><body><div class="wrap">'
            '<div class="pick" data-espn="baseball/mlb" data-num="%d" data-eid="%s"><a data-kalticker="%s" data-kalside="CWS">KAL +138</a></div>'
            '</div></body></html>' % (n, n, eid, tick))
HIST_DUP = '{"kal": [[1790000000, 42.0], [1790000060, 43.0]]}'

def manifest(base, picks):
    m = dict(base); m.pop('pick_content_hash', None); m['picks'] = [json.loads(json.dumps(p)) for p in picks]
    return m

fails = []
def check(label, cond):
    print(('OK   ' if cond else 'FAIL ') + label)
    if not cond: fails.append(label)

def read(p):
    try: return open(p).read()
    except Exception: return None

for B in BUILDERS:
    site = os.path.join(tempfile.mkdtemp(prefix='rp-gp-'), 'site')
    shutil.copytree(ROOT, site, ignore=shutil.ignore_patterns('.git', 'node_modules', '__pycache__'))
    for f in os.listdir(site):
        if re.match(r'(game-\d+\.html|hist-\d+\.json)$', f): os.remove(os.path.join(site, f))
    net = os.path.join(site, '_fakenet'); os.makedirs(net)
    open(os.path.join(net, 'sitecustomize.py'), 'w').write(FAKENET)
    json.dump(ROUTES, open(os.path.join(net, 'routes.json'), 'w'))
    env = dict(os.environ, PYTHONPATH=net, RP_FAKENET=os.path.join(net, 'routes.json'), RP_REFRESH='1', PYTHONWARNINGS='ignore')
    env.pop('RP_PUBLISH', None)
    base = json.load(open(os.path.join(ROOT, 'manifest.json')))
    P = lambda f: os.path.join(site, f)

    def build(picks, label):
        man=stamped(P('scripts/'+B),manifest(base,picks))
        json.dump(man,open(P('fixture_manifest.json'),'w'))
        published_snapshot(site,P('scripts/'+B),man)
        r = subprocess.run([sys.executable, 'scripts/' + B, 'fixture_manifest.json', 'index.html'], cwd=site, env=env, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            print(r.stderr[-3000:])
        check(f'{B} {label}: builder exits 0', r.returncode == 0)
        return r

    def retired(n):
        pg = read(P('game-%d.html' % n)) or ''
        return ('noindex' in pg and 'record.html' in pg and 'data-retired="1"' in pg and 'data-eid=' not in pg
                and 'data-kalticker' not in pg and 'data-polyslug' not in pg and 'Old card game' not in pg)

    def backfill():
        r = subprocess.run([sys.executable, 'scripts/backfill_history.py'], cwd=site, env=env, capture_output=True, text=True, timeout=600)
        return r.stdout + r.stderr

    # A. one-pick card over a stale family: game-1 live, game-2..4 retired, their hist emptied
    open(P('game-1.html'), 'w').write(stale_page(1, '401907896', TICK))
    open(P('game-2.html'), 'w').write(stale_page(2, '401891774', 'KXNHLGAME-26SEP29NYRBOS'))
    open(P('game-3.html'), 'w').write(stale_page(3, '', 'KXUFCFIGHT-26SEP29GSLA'))
    open(P('game-4.html'), 'w').write(stale_page(4, EID, TICK))  # DI-09 shape: a stray page bound to the live game
    for n in (1, 2, 3, 4): open(P('hist-%d.json' % n), 'w').write(HIST_DUP)
    build([ML], 'A one-pick card')
    g1 = read(P('game-1.html')) or ''
    check(f'{B} A game-1 is the live card page (eid {EID})', 'data-eid="%s"' % EID in g1 and 'Old card game' not in g1)
    for n in (2, 3, 4):
        check(f'{B} A game-{n} (not on the card) is retired: URL kept, noindex, no event id or market', retired(n))
    check(f'{B} A builder writes no hist-*.json (outside record-final\'s staged outputs)',
          all(read(P('hist-%d.json' % n)) == HIST_DUP for n in (1, 2, 3, 4)))
    bf = backfill()
    check(f'{B} A backfill_history.py pulls no market history for retired pages',
          not re.search(r'game-[234]\.html (->\s*\{|kal ERR|poly ERR)', bf))
    check(f'{B} A backfill_history.py empties the retired pages\' stale hist-N.json',
          all(read(P('hist-%d.json' % n)) == '{}' for n in (2, 3, 4)) and len(re.findall(r'game-[234]\.html -> retired, hist emptied', bf)) == 3)
    check(f'{B} A a second backfill run leaves the emptied files alone', not re.search(r'game-[234]\.html', backfill()))
    routes = json.load(open(P('slates/game_routes.json')))
    check(f'{B} A routes map only the live page', routes == {EID: 'game-1.html'})

    # B. rebuild: notices are byte-stable, so the 15-min refresh commits nothing for them
    snap = {n: read(P('game-%d.html' % n)) for n in (2, 3, 4)}
    build([ML], 'B rebuild')
    check(f'{B} B retired notices are byte-identical across rebuilds', all(read(P('game-%d.html' % n)) == snap[n] for n in (2, 3, 4)))

    # C. empty card: the hold keeps the last card's own page once the strays are gone
    rc = build([], 'C empty card')
    g1c = read(P('game-1.html')) or ''
    check(f'{B} C empty-card hold matches the last card snapshot', 'HISTORICAL GAME HOLD: no exact' not in rc.stderr)
    check(f'{B} C empty-card hold keeps the last card page (eid {EID})', 'data-eid="%s"' % EID in g1c)
    check(f'{B} C retired pages stay retired on an empty card', all(retired(n) for n in (2, 3, 4)))

    # D. empty card whose numbered pages match no snapshot (two pages on one event, as game-1/game-5 did)
    open(P('game-5.html'), 'w').write(stale_page(5, EID, TICK)); open(P('hist-5.json'), 'w').write(HIST_DUP)
    build([], 'D empty card, no matching snapshot')
    check(f'{B} D no stale game page survives an unmatched empty card', all(retired(n) for n in (1, 2, 3, 4, 5)))
    bf = backfill()
    check(f'{B} D backfill_history.py no longer feeds hist-1 and hist-5 from one market',
          not re.search(r'game-[15]\.html (->\s*\{|kal ERR|poly ERR)', bf) and read(P('hist-1.json')) == '{}' and read(P('hist-5.json')) == '{}')

    # E. LS-10: the prop's locked Kalshi price must not land on the Houston side of the board
    build([ML, PROP], 'E prop on a game-winner market')
    gp = ''
    for n in (1, 2):
        pg = read(P('game-%d.html' % n)) or ''
        if 'Yordan Alvarez' in pg: gp = pg
    hou = re.search(r'data-kalmkt="%s-HOU" data-cents="(\d+)"' % TICK, gp)
    cws = re.search(r'data-kalmkt="%s-CWS" data-cents="(\d+)"' % TICK, gp)
    check(f'{B} E explicit prop snapshot never labels its locked price as Houston', not hou and 'data-kalpx="yes"' in gp)
    check(f'{B} E explicit snapshot retains its declared CWS YES price (42c)', 'data-kalside="CWS" data-kalpx="yes" data-cents="42"' in gp)
    shutil.rmtree(os.path.dirname(site), ignore_errors=True)

print(('ALL OK' if not fails else '%d FAIL' % len(fails)))
sys.exit(1 if fails else 0)
