#!/usr/bin/env python3
"""League tabs carry every source's picks (owner, 2026-10-07): "Each leagues picks should be in their proper league
tabs, no matter where they comes from. System picks stay on the home page and go to their proper league tabs too."
/ "There should never be duplicate league tabs." / Trinity's tab is the last tab in the nav, always.

Builds a real page with each builder twin in a throwaway tree, network blocked, from a fixture card (an MLB pick and
a WNBA pick) plus fixture Wooder Ice feeds and a futures book, then:
- runs the shipped page's own league binder (window.rpLg) and the Wooder Ice modules as built (tickets, combos,
  batch, first TD, Dingers) on the fixture feeds, in node, and reads the league each rendered pick carries;
- checks every league tab holds every source's picks for that league: the tab's own panel (the card's picks, the
  league's open futures) plus each Wooder Ice item bound to that league, which the page shows on that tab through
  the generated #rpLgShare rules (checked present for every league tab);
- a league with picks only from other sources gets its tab (NFL, NCAAF, NHL here); a ticket with legs in two
  leagues is in both, whole; a pick whose data names no league stays on its source tab and is in the build note;
- Wooder Ice tickets stay on the Wooder tab, the card stays on Home (league panels projected there), nothing from
  Wooder Ice is projected on Home, nothing is labelled a card pick that is not one;
- one tab per league, one panel per id, no repeated id on the page, Trinity's tab last, and the retired second
  WNBA ticket box / module are gone.
Run: python3 scripts/test_league_tabs_sources.py [builder.py ...]   (default: both twins; exit 1 on any failure)
"""
import json, os, re, shutil, subprocess, sys, tempfile, warnings, datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo
warnings.simplefilter('ignore', SyntaxWarning)  # the builder source carries pre-existing invalid escapes inside JS templates

from fixtures.card_contract import stamped, market, published_snapshot

SD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SD)
BUILDERS = [os.path.abspath(a) for a in sys.argv[1:]] or [os.path.join(SD, 'build_gh_page_v2.py'), os.path.join(SD, '_build_nocanon_v2.py')]
failures = 0
def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or not detail else '  [' + str(detail)[:300] + ']'))
    if not ok: failures += 1

TODAY = datetime.datetime.now(ZoneInfo('America/Los_Angeles')).date().isoformat()
DEAD = 'http://127.0.0.1:9'

SOX = {'num': 1, 'name': 'White Sox ML', 'market_class': 'ml', 'sub': 'CWS @ HOU - model 95.0', 'odds': '+138', 'units': '5u', 'side': 'away',
       'game': {'away': 'Chicago White Sox', 'home': 'Houston Astros', 'commence': '2099-10-01T21:00Z', 'eid': ''},
       'espn_league': 'baseball/mlb', 'league': 'MLB', 'best_book': 'DraftKings'}
LYNX = {'num': 2, 'name': 'Lynx ML', 'market_class': 'ml', 'sub': 'MIN @ NY - model 95.0', 'odds': '-110', 'units': '5u', 'side': 'away',
        'game': {'away': 'Minnesota Lynx', 'home': 'New York Liberty', 'commence': '2099-10-01T23:30Z', 'eid': ''},
        'espn_league': 'basketball/wnba', 'league': 'WNBA', 'best_book': 'DraftKings'}
MANIFEST = {'date': '2099-10-01', 'date_label': 'Thursday, Oct 1', 'updated': 'Oct 1, 8:42 AM PT', 'record': '21-11',
            'units_pl': '+4.76u', 'units_ledger': None, 'yesterday': '', 'status_note': '', 'preview': False, 'parlay': None,
            'picks': [market(SOX), market(LYNX)]}
PREFILL = []

# --- fixture Wooder Ice feeds (each pick carries a marker its rendering shows) ---
TICKETS = {'version': 1, 'generated_at': TODAY + 'T09:00:00-07:00', 'tickets': [
    {'id': 'fx-nfl', 'sport': 'nfl', 'title': 'FXNFLTICKET', 'status': 'NOT PLACED', 'bought': False,
     'legs': [{'player': 'Fx Receiver', 'market': '4+ receptions', 'matchup': 'TB @ DAL', 'time': 'Thu'}]},
    {'id': 'fx-wnba', 'sport': 'wnba', 'title': 'FXWNBATICKET', 'status': 'PLACED - reported by Wooder Ice', 'bought': False,
     'placement_note': 'FXPLACEMENTNOTE receipt, stake and fill not independently verified.',
     'legs': [{'player': 'Fx Forward', 'market': '10+ points', 'stat_key': 'points', 'target': 10, 'event_id': '401918297', 'matchup': 'NYL @ ATL', 'time': 'Oct 7'},
              {'player': 'Fx Center', 'market': '20+ points (intended)', 'stat_key': 'points', 'target': 20, 'event_id': '401918298',
               'matchup': 'LVA @ GS', 'time': 'Oct 7', 'intended_only': True}]},
    {'id': 'fx-multi', 'title': 'FXMULTITICKET', 'status': 'NOT PLACED',
     'legs': [{'player': 'Fx Back', 'market': 'anytime TD', 'sport': 'nfl', 'matchup': 'PHI @ CHI'},
              {'player': 'Fx Wing', 'market': '1+ goal', 'league': 'NHL', 'matchup': 'BOS @ TOR'}]},
    {'id': 'fx-none', 'title': 'FXNOLEAGUETICKET', 'status': 'NOT PLACED',
     'legs': [{'player': 'Fx Nobody', 'market': '1+ hit', 'matchup': 'AAA @ BBB'}]},
]}
COMBOS = {'version': 4, 'generated_at': TODAY + 'T09:00:00-07:00', 'combos': [
    {'id': 'fx-nfl-futures', 'type': 'idea', 'futures': True, 'title': 'FXNFLFUTURESIDEA', 'matchup': 'NFL regular season',
     'sport': 'nfl', 'league': 'NFL', 'legs': [{'player': 'Fx Wideout', 'market': '1000+ receiving yards'}]},
    {'id': 'fx-mlb-20991231', 'type': 'idea', 'date': '2099-12-31', 'title': 'FXMLBIDEA', 'matchup': 'CWS@HOU', 'sport': 'mlb', 'league': 'MLB',
     'legs': [{'player': 'Fx Pitcher', 'market': '7+ strikeouts', 'kalshi': '+117'}]},
    {'id': 'fx-mlb-stale-20000101', 'type': 'idea', 'date': '2000-01-01', 'title': 'FXSTALEIDEA', 'matchup': 'X', 'sport': 'mlb',
     'legs': [{'player': 'Fx Old', 'market': '1+ hit', 'kalshi': '+100'}]},
]}
BATCH = {'date': TODAY, 'cards': [{'id': 'fxb1', 'title': 'FXNCAAFCARD', 'league': 'NCAAF', 'matchup': 'A at B', 'time': '5 PM PT',
                                   'legs': [{'player': 'Fx Qb', 'market': '250+ passing yards', 'links': [{'venue': 'KAL', 'cents': 40}]}]}]}
FIRST_TD = {'version': 1, 'generated_at': TODAY + 'T09:00:00-07:00', 'picks': [
    {'player': 'FXFIRSTTDNFL', 'market': 'First TD', 'american': '+700', 'matchup': 'PHI @ CHI', 'sport': 'nfl'},
    {'player': 'FXFIRSTTDNONE', 'market': 'First TD', 'american': '+900', 'matchup': 'PHI @ CHI'}]}
DINGERS = {'date': TODAY, 'picks': [{'player': 'FXDINGER', 'team': 'CWS', 'matchup': 'CLE at CWS', 'time': '1:00 PM PT', 'market': 'Home Run', 'links': []}]}
NFL_IDEAS = {'date': '2000-01-01', 'cards': []}
FUTURES = [
    {'id': 'F-FX-NFL', 'league': 'NFL', 'team': 'Fxville Futures', 'market': 'Super Bowl LXI Champion', 'odds': '+1400', 'units': 4, 'placed': '2026-09-24',
     'abbr': 'sf', 'fair_price_est': '+900', 'est_prob': 0.1, 'resolution': 'Super Bowl LXI result (Feb 2027)'},
    {'id': 'F-FX-WNBA', 'league': 'WNBA', 'team': 'Fxtown Settled', 'market': 'WNBA Championship', 'odds': '+133', 'units': 2, 'placed': '2026-09-26',
     'abbr': 'min', 'fair_price_est': '+100', 'est_prob': 0.5, 'resolution': 'WNBA Finals result (Oct 2026)',
     'settlement': {'status': 'SETTLED', 'result': 'LOST', 'settled_date': '2026-09-29'}},
]
FEEDS = {'wooder_tickets.json': TICKETS, 'wooder_combos.json': COMBOS, 'wooder_batch.json': BATCH, 'wooder_first_td.json': FIRST_TD,
         'wooder_dingers.json': DINGERS, 'nfl_ideas.json': NFL_IDEAS}

def build(builder, feeds=None):
    d = tempfile.mkdtemp(prefix='rp-leaguetabs-')
    os.makedirs(os.path.join(d, 'scripts')); os.makedirs(os.path.join(d, 'slates'))
    bsrc = os.path.dirname(builder)
    shutil.copy(builder, os.path.join(d, 'scripts', 'build_gh_page_v2.py'))
    for f in ('index_v2.js', 'index_v2.css', 'game_page_template.html', 'team_page_template.html', 'poly_us.py'):
        shutil.copy(os.path.join(bsrc if os.path.exists(os.path.join(bsrc, f)) else SD, f), os.path.join(d, 'scripts', f))
    for f in ('feed_arbiter.js', 'feed_registry.json', 'config_leagues.json'):
        shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
    if os.path.isdir(os.path.join(ROOT, 'trinity')):
        shutil.copytree(os.path.join(ROOT, 'trinity'), os.path.join(d, 'trinity'))
    m = stamped(builder, MANIFEST)
    json.dump(m, open(os.path.join(d, 'manifest.json'), 'w'), indent=1)
    published_snapshot(d, builder, m)
    json.dump(PREFILL, open(os.path.join(d, 'slates', 'odds_prefill.json'), 'w'))
    for name, data in (FEEDS if feeds is None else feeds).items():
        json.dump(data, open(os.path.join(d, 'slates', name), 'w'))
    json.dump(FUTURES, open(os.path.join(d, 'futures.json'), 'w'))
    env = dict(os.environ, RP_REFRESH='1', http_proxy=DEAD, https_proxy=DEAD, HTTP_PROXY=DEAD, HTTPS_PROXY=DEAD)
    r = subprocess.run([sys.executable, os.path.join(d, 'scripts', 'build_gh_page_v2.py'), 'manifest.json', 'index.html'],
                       cwd=d, env=env, capture_output=True, text=True, timeout=900)
    page = open(os.path.join(d, 'index.html')).read() if os.path.exists(os.path.join(d, 'index.html')) else ''
    shutil.rmtree(d, ignore_errors=True)
    return r.returncode, page, r.stderr

def script_after(page, marker):
    i = page.find(marker)
    if i < 0: return ''
    a = page.find('<script>', i)
    b = page.find('</script>', a)
    return page[a + 8:b] if a >= 0 and b > a else ''

def js_fn(src, name):
    i = src.find('function ' + name + '(')
    if i < 0: return ''
    depth = 0
    for k in range(src.find('{', i), len(src)):
        if src[k] == '{': depth += 1
        elif src[k] == '}':
            depth -= 1
            if not depth: return src[i:k + 1]
    return ''

# Runs the page's binder and the Wooder Ice modules as shipped, on the fixture feeds, with a small stand-in DOM.
HARNESS = r"""
const vm=require('vm');const IN=JSON.parse(require('fs').readFileSync(0,'utf8'));
function El(id){return {id:id,innerHTML:'',style:{},hidden:false,attrs:{},setAttribute(k,v){this.attrs[k]=String(v);},getAttribute(k){return this.attrs[k]==null?null:this.attrs[k];},
 querySelector(){return null;},querySelectorAll(){return [];},appendChild(){},parentNode:null};}
const E={};function get(id){if(!E[id]){E[id]=El(id);E[id].parentNode=El(id+'^');E[id].parentNode.parentNode=El(id+'^^');}return E[id];}
const timers=[];
const ctx={console,JSON,Math,Date,Intl,String,Number,Array,Object,Promise,RegExp,isFinite,parseInt,parseFloat,
 document:{readyState:'complete',hidden:false,getElementById:get,querySelector:()=>null,querySelectorAll:()=>[],createElement:()=>El('x'),head:{appendChild(){}},addEventListener(){}},
 localStorage:{getItem:()=>null,setItem(){}},setTimeout:(f)=>{timers.push(f);return 1;},setInterval:()=>1,
 fetch:(u)=>{const m=/slates\/([a-z_]+\.json)/.exec(String(u));const d=m?IN.feeds[m[1]]:undefined;
   return Promise.resolve(d===undefined?{ok:false,json:()=>Promise.reject(0)}:{ok:true,json:()=>Promise.resolve(JSON.parse(JSON.stringify(d)))});}};
ctx.window=ctx;ctx.window.addEventListener=function(){};
vm.createContext(ctx);
vm.runInContext(IN.lg,ctx);
vm.runInContext(IN.fresh+';window.rpComboFresh=rpComboFresh;',ctx);
for(const s of IN.mods){try{vm.runInContext(s,ctx);}catch(e){console.error('module threw: '+e.message);}}
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{for(let i=0;i<8;i++){await tick();while(timers.length)timers.shift()();}
 const out={boxes:{},attrs:{},bind:{}};
 for(const id of ['rpTix','rpCmb','rpCmbFut','rpBatchIdeas','rpFtd','rpDing'])out.boxes[id]=(E[id]||{}).innerHTML||'';
 out.attrs.dingWrap=(E.rpDing&&E.rpDing.parentNode.parentNode.attrs)||{};
 for(const [k,list] of Object.entries(IN.items))out.bind[k]=list.map(it=>ctx.rpLg.of(it));
 process.stdout.write(JSON.stringify(out));})();
"""

class Tree(HTMLParser):
    """Top-level children of a rendered fragment: tag, attributes and text - enough to read each rendered item."""
    VOID = {'img', 'br', 'hr', 'input', 'meta', 'link'}
    def __init__(self, src):
        super().__init__(convert_charrefs=True)
        self.kids, self.depth, self.cur = [], 0, None
        self.feed(src)
    def handle_starttag(self, tag, attrs):
        if self.depth == 0:
            self.cur = {'tag': tag, 'attrs': dict(attrs), 'text': ''}
            self.kids.append(self.cur)
        if tag not in self.VOID: self.depth += 1
    def handle_endtag(self, tag):
        if tag not in self.VOID: self.depth -= 1
    def handle_data(self, data):
        if self.cur is not None and self.depth > 0: self.cur['text'] += data + ' '
def items(html_frag): return Tree(html_frag).kids
def lg_of(k): return set((k['attrs'].get('data-rplg') or '').split())

def strip_code(page):
    return re.sub(r'<script\b[^>]*>[\s\S]*?</script>|<style\b[^>]*>[\s\S]*?</style>', '', page)
def panel(page, key):
    m = re.search(r'<div class="state" id="st-%s"[^>]*>' % re.escape(key), page)
    if not m: return ''
    nxt = re.search(r'\n<div class="state" id="st-', page[m.end():])
    return page[m.start(): m.end() + (nxt.start() if nxt else len(page))]

for B in BUILDERS:
    tag = os.path.basename(B)
    rc, page, log = build(B)
    check(f'{tag}: fixture card builds', rc == 0 and len(page) > 10000, log[-600:])
    if not page: continue

    # 1. one tab per league, in order, Trinity last; one panel per id; no repeated id on the page
    m = re.search(r'window\.RP_TABS=(\[.*?\]);', page)
    tabs = [t['key'] for t in json.loads(m.group(1))] if m else []
    nav = re.findall(r'<a class="tab"[^>]*data-tab="([a-z0-9]+)"', page)
    want = ['home', 'mlb', 'wnba', 'nfl', 'ncaaf', 'nhl', 'wooder', 'past', 'trinity']
    check(f'{tag}: tabs = card leagues, then leagues with picks from other sources (config order), Wooder, Past, Trinity', tabs == want, tabs)
    check(f'{tag}: the nav carries the same tabs, each once, Trinity last', nav == tabs and len(set(nav)) == len(nav) and nav[-1:] == ['trinity'], nav)
    hidden_tabs = re.findall(r'<a class="tab"[^>]*style="display:none"[^>]*data-tab="([a-z0-9]+)"', page)
    check(f'{tag}: a league with picks from other sources shows its tab (NFL is not the hidden ideas-only tab)', not hidden_tabs, hidden_tabs)
    pids = re.findall(r'<div class="state[^"]*" id="([^"]+)"', page)
    check(f'{tag}: one panel per id', len(pids) == len(set(pids)) and set('st-' + k for k in tabs) <= set(pids), pids)
    ids = re.findall(r'\sid="([^"]+)"', strip_code(page))
    dup = sorted({i for i in ids if ids.count(i) > 1})
    check(f'{tag}: no id repeats anywhere on the page', not dup, dup)
    check(f'{tag}: the second WNBA ticket box and the separate WNBA module are gone',
          'rpTixW' not in page and 'rpWnbaShared' not in page and 'wooder_wnba_shared' not in page)

    # 2. Home keeps the card: the card's league panels are projected on Home, nothing from other sources is
    home_panels = [k for k in tabs if re.search(r'<div class="state" id="st-%s" data-home-league="1">' % k, page)]
    check(f'{tag}: Home projects exactly the card leagues (MLB, WNBA)', home_panels == ['mlb', 'wnba'], home_panels)
    check(f'{tag}: Home carries the system card (both picks in their projected panels)',
          'White Sox ML' in panel(page, 'mlb') and 'Lynx ML' in panel(page, 'wnba') and '<div class="state" id="st-home">' in page)
    check(f'{tag}: Dingers stays one shared Home/Wooder panel', page.count('id="st-ding" data-home-league="1"') == 1 and page.count('slates/wooder_dingers.json') == 1)
    for k in ('nfl', 'ncaaf', 'nhl'):
        p = panel(page, k)
        check(f'{tag}: {k} panel (other sources only) is not projected on Home and claims no card pick',
              'data-home-league' not in p.split('>', 1)[0] and 'Today&rsquo;s picks' not in p)

    # 3. the page shows Wooder Ice items on their league tabs: the rules for every league tab are there
    css = (re.search(r'<style id="rpLgShare">([^<]*)</style>', page) or [None, ''])[1]
    for k in [t for t in tabs if t not in ('home', 'wooder', 'past', 'trinity')]:
        rules = ['body.tab-%s #st-wooder:has([data-rplg~="%s"]){display:block}' % (k, k),
                 'body.tab-%s #st-wooder>:not(.rpsec):not(.rpkeep){display:none!important}' % k,
                 'body.tab-%s #st-wooder .rpsec:not([data-rplg~="%s"]):not(:has([data-rplg~="%s"])){display:none!important}' % (k, k, k),
                 'body.tab-%s #st-wooder .rpbox>:not([data-rplg~="%s"]){display:none!important}' % (k, k),
                 'body.tab-%s #st-ding:has([data-rplg~="%s"]){display:block}' % (k, k)]
        check(f'{tag}: {k} tab shows the Wooder Ice items bound to {k} (rules present)', all(r in css for r in rules), k)
    check(f'{tag}: league futures rows never show on Home', 'body.tab-home .rplgfut{display:none}' in css)
    check(f'{tag}: build note lists the picks that bind to no league',
          'LEAGUE BIND NOTE: wooder_tickets fx-none binds to no league' in log and 'LEAGUE BIND NOTE: wooder_first_td FXFIRSTTDNONE binds to no league' in log, log[-800:])

    # 4. run the binder and the modules as shipped
    lg = script_after(page, '<style id="rpLgShare">')
    mods = [script_after(page, 'id="rpTix"'), script_after(page, 'id="rpCmbFut"'), script_after(page, 'id="rpBatchIdeas"'),
            script_after(page, 'id="rpFtd"'), script_after(page, 'id="rpDing"')]
    fresh = js_fn(page, 'rpComboFresh')
    check(f'{tag}: binder and modules found in the page', bool(lg) and all(mods) and bool(fresh))
    feeds = dict(FEEDS)
    probe = {'tickets': TICKETS['tickets'], 'combos': COMBOS['combos'], 'batch': BATCH['cards'], 'ftd': FIRST_TD['picks']}
    r = subprocess.run(['node', '-e', HARNESS], input=json.dumps({'lg': lg, 'fresh': fresh, 'mods': mods, 'feeds': feeds, 'items': probe}),
                       capture_output=True, text=True, timeout=60)
    try: out = json.loads(r.stdout)
    except ValueError: out = None
    check(f'{tag}: modules run on the fixture feeds', out is not None and 'module threw' not in r.stderr, (r.stderr or r.stdout)[-400:])
    if out is None: continue
    check(f'{tag}: the page binds each item to the leagues the builder does',
          out['bind'] == {'tickets': [['nfl'], ['wnba'], ['nfl', 'nhl'], []], 'combos': [['nfl'], ['mlb'], ['mlb']], 'batch': [['ncaaf']], 'ftd': [['nfl'], []]}, out['bind'])

    tix = {k['text'].split('Ticket ', 1)[-1].split(' ', 1)[0]: k for k in items(out['boxes']['rpTix']) if 'Ticket ' in k['text']}
    check(f'{tag}: every Wooder Ice ticket renders in the one Wooder ticket box (WNBA included)', sorted(tix) == ['fx-multi', 'fx-nfl', 'fx-none', 'fx-wnba'], sorted(tix))
    check(f'{tag}: tickets carry their leagues; a two-league ticket both; an unbindable one none',
          [sorted(lg_of(tix.get(i, {'attrs': {}}))) for i in ('fx-nfl', 'fx-wnba', 'fx-multi', 'fx-none')] == [['nfl'], ['wnba'], ['nfl', 'nhl'], []])
    check(f'{tag}: the two-league ticket shows whole and says where it shows', 'Fx Back' in tix.get('fx-multi', {}).get('text', '') and 'Fx Wing' in tix.get('fx-multi', {}).get('text', '')
          and 'Legs in NFL and NHL: the whole ticket shows in each of their tabs.' in tix.get('fx-multi', {}).get('text', ''))
    wn = out['boxes']['rpTix']
    check(f'{tag}: WNBA legs track their own ESPN event (event id, league path, stat, target, intended-only)',
          'class="rpevtrk" data-eid="401918297" data-espn="basketball/wnba" data-p="Fx Forward" data-stat="points" data-target="10" data-intended="0"' in wn
          and 'data-eid="401918298" data-espn="basketball/wnba" data-p="Fx Center" data-stat="points" data-target="20" data-intended="1"' in wn)
    check(f'{tag}: the placement note shows with its ticket, labelled as reported by Wooder Ice', 'FXPLACEMENTNOTE' in tix.get('fx-wnba', {}).get('text', '')
          and 'PLACED - reported by Wooder Ice' in tix.get('fx-wnba', {}).get('text', ''))
    cmb = {k['text'].strip().split(' ')[0]: k for k in items(out['boxes']['rpCmb'])}
    fut = {k['text'].strip().split(' ')[0]: k for k in items(out['boxes']['rpCmbFut'])}
    check(f'{tag}: combos carry their league; a stale one is not shown', sorted(lg_of(cmb.get('FXMLBIDEA', {'attrs': {}}))) == ['mlb']
          and sorted(lg_of(fut.get('FXNFLFUTURESIDEA', {'attrs': {}}))) == ['nfl'] and 'FXSTALEIDEA' not in out['boxes']['rpCmb'] + out['boxes']['rpCmbFut'], (list(cmb), list(fut)))
    bat = items(out['boxes']['rpBatchIdeas'])
    check(f'{tag}: a batch card carries its league', len(bat) == 1 and lg_of(bat[0]) == {'ncaaf'} and 'FXNCAAFCARD' in bat[0]['text'])
    ftd = {('FXFIRSTTDNFL' if 'FXFIRSTTDNFL' in k['text'] else 'FXFIRSTTDNONE'): k for k in items(out['boxes']['rpFtd'])}
    check(f'{tag}: first-TD picks carry the league their data names, none when it names none',
          lg_of(ftd.get('FXFIRSTTDNFL', {'attrs': {}})) == {'nfl'} and lg_of(ftd.get('FXFIRSTTDNONE', {'attrs': {'data-rplg': 'x'}})) == set())
    check(f'{tag}: the Dingers section is bound to MLB once it renders', out['attrs']['dingWrap'].get('data-rplg') == 'mlb' and 'FXDINGER' in out['boxes']['rpDing'])

    # 5. every league tab holds every source's picks for that league
    shared = []  # (marker, leagues) for each Wooder Ice item in the shared panels
    for t in TICKETS['tickets']: shared.append((t['title'], lg_of(tix.get(t['id'], {'attrs': {}}))))
    shared += [('FXMLBIDEA', lg_of(cmb['FXMLBIDEA'])), ('FXNFLFUTURESIDEA', lg_of(fut['FXNFLFUTURESIDEA'])), ('FXNCAAFCARD', lg_of(bat[0])),
               ('FXFIRSTTDNFL', lg_of(ftd['FXFIRSTTDNFL'])), ('FXFIRSTTDNONE', lg_of(ftd['FXFIRSTTDNONE'])), ('FXDINGER', {'mlb'})]
    def holds(key):
        own = re.sub(r'<[^>]+>', ' ', panel(page, key))
        got = {mk for mk in ('White Sox ML', 'Lynx ML', 'Fxville Futures', 'Fxtown Settled') if mk in own}
        if key == 'wooder':
            return got | {mk for mk, _ in shared}
        if key == 'home':
            return got | {mk for mk in ('White Sox ML', 'Lynx ML') if any(mk in panel(page, h) for h in home_panels)} | {'FXDINGER'}
        return got | {mk for mk, ls in shared if key in ls}
    expect = {
        'home': {'White Sox ML', 'Lynx ML', 'FXDINGER'},
        'mlb': {'White Sox ML', 'FXMLBIDEA', 'FXDINGER'},
        'wnba': {'Lynx ML', 'FXWNBATICKET'},
        'nfl': {'FXNFLTICKET', 'FXMULTITICKET', 'FXNFLFUTURESIDEA', 'FXFIRSTTDNFL', 'Fxville Futures'},
        'ncaaf': {'FXNCAAFCARD'},
        'nhl': {'FXMULTITICKET'},
        'wooder': {'FXNFLTICKET', 'FXWNBATICKET', 'FXMULTITICKET', 'FXNOLEAGUETICKET', 'FXMLBIDEA', 'FXNFLFUTURESIDEA', 'FXNCAAFCARD',
                   'FXFIRSTTDNFL', 'FXFIRSTTDNONE', 'FXDINGER'},
    }
    for key, want_set in expect.items():
        got = holds(key)
        check(f'{tag}: {key} tab holds every source\'s picks for it, and nothing else', got == want_set, sorted(got ^ want_set))
    check(f'{tag}: a settled futures pick is in no league tab', all('Fxtown Settled' not in panel(page, k) for k in tabs))

    # 6. a malformed guest feed never stops the card: the page builds, the card's tabs stand, nothing is bound from it
    bad = dict(FEEDS, **{'wooder_tickets.json': [1, 2], 'wooder_combos.json': {'combos': {'x': 1}}, 'wooder_batch.json': {'date': TODAY, 'cards': 'x'}})
    rc2, page2, log2 = build(B, bad)
    m2 = re.search(r'window\.RP_TABS=(\[.*?\]);', page2)
    tabs2 = [t['key'] for t in json.loads(m2.group(1))] if m2 else []
    check(f'{tag}: malformed Wooder Ice feeds still build the card, its tabs and Trinity last',
          rc2 == 0 and tabs2[:3] == ['home', 'mlb', 'wnba'] and tabs2[-1:] == ['trinity'] and 'nhl' not in tabs2, (rc2, tabs2, log2[-300:]))

if failures:
    print('\nFAILED %d' % failures); sys.exit(1)
print('\nall checks passed')
