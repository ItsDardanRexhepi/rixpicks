#!/usr/bin/env python3
"""C-4.4 and C-4.5: the state (geo) gate on the index and game pages.
 C-4.4 the visitor's position goes to the third-party reverse geocoder rounded to 2 decimals (about 1 km), never
       at full device precision, in both lookups (Share my location, and the silent re-verify when permission is
       already granted). Two decimals, not one: a 0.1-degree cell (about 11 km) moves a visitor across a state
       line in border metros (Vancouver WA into Oregon), and the gate's whole job is the state.
 C-4.5 with no fresh shared state a market chip carries no venue address in its href: rpTapify sets href="#" and
       keeps the destination aside (data-href, data-dest); the real href is set only once a state has resolved
       (rpTapify with a state, or rpGo when a tap with a fresh state opens it), so a long-press, copy-link or
       middle-click cannot route around the gate. The page's rebuild refresh follows the same rule.
Real functions from pages built by each builder twin (throwaway tree, network sent to a dead proxy), run in node
against a small stub DOM. Run: python3 scripts/test_c44_c45_geo.py [builder.py ...]   (default: both twins)"""
import copy, json, os, re, shutil, subprocess, sys, tempfile

from fixtures.card_contract import stamped, market, published_snapshot

SD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SD)
BUILDERS = [os.path.abspath(a) for a in sys.argv[1:]] or [os.path.join(SD, 'build_gh_page_v2.py'), os.path.join(SD, '_build_nocanon_v2.py')]
DEAD = 'http://127.0.0.1:9'
failures = 0

def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or detail == '' else '  [' + str(detail)[-500:] + ']'))
    if not ok:
        failures += 1

def build(builder, manifest):
    d = tempfile.mkdtemp(prefix='rp-c4-')
    try:
        os.makedirs(os.path.join(d, 'scripts')); os.makedirs(os.path.join(d, 'slates'))
        bsrc = os.path.dirname(builder)
        shutil.copy(builder, os.path.join(d, 'scripts', 'build_gh_page_v2.py'))
        for f in ('index_v2.js', 'index_v2.css', 'game_page_template.html', 'team_page_template.html', 'poly_us.py'):
            shutil.copy(os.path.join(bsrc if os.path.exists(os.path.join(bsrc, f)) else SD, f), os.path.join(d, 'scripts', f))
        for f in ('feed_arbiter.js', 'feed_registry.json', 'config_leagues.json'):
            shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
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
        pages = {f: open(os.path.join(d, f), encoding='utf-8').read() for f in os.listdir(d) if f.endswith('.html')}
        return r.returncode, r.stdout + r.stderr, pages
    finally:
        shutil.rmtree(d, ignore_errors=True)

def js_fn(src, name):
    i = src.find('function ' + name + '(')
    if i < 0:
        return ''
    d = 0
    for k in range(src.find('{', i), len(src)):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if not d:
                return src[i:k + 1]
    return ''

def node(code):
    r = subprocess.run(['node', '-e', code], capture_output=True, text=True, timeout=60)
    try:
        return json.loads(r.stdout.strip().split('\n')[-1])
    except (ValueError, IndexError):
        return {'error': (r.stdout + r.stderr)[-800:]}

STUB = r'''
function El(tag,attrs){this.tagName=tag;this._a=Object.assign({},attrs||{});this.innerHTML='KAL -150';this.style={};
 var self=this;this.classList={add:function(){},remove:function(){}};
 this.dataset=new Proxy({},{get:function(t,k){var v=self._a['data-'+String(k).replace(/[A-Z]/g,function(m){return '-'+m.toLowerCase();})];return v===undefined?undefined:v;},
  set:function(t,k,v){self._a['data-'+String(k).replace(/[A-Z]/g,function(m){return '-'+m.toLowerCase();})]=String(v);return true;},
  deleteProperty:function(t,k){delete self._a['data-'+String(k).replace(/[A-Z]/g,function(m){return '-'+m.toLowerCase();})];return true;}});}
El.prototype.getAttribute=function(n){return Object.prototype.hasOwnProperty.call(this._a,n)?this._a[n]:null;};
El.prototype.setAttribute=function(n,v){this._a[n]=String(v);};
El.prototype.removeAttribute=function(n){delete this._a[n];};
El.prototype.hasAttribute=function(n){return Object.prototype.hasOwnProperty.call(this._a,n);};
Object.defineProperty(El.prototype,'attributes',{get:function(){var a=this._a;return Object.keys(a).map(function(k){return {name:k,value:a[k]};});}});
El.prototype.closest=function(){return null;};El.prototype.replaceWith=function(){};
var document={createElement:function(t){return new El(t.toUpperCase());},getElementById:function(){return {style:{}};},querySelectorAll:function(){return [];}};
var window={};var opened=[];function rpOpen(u){opened.push(u);}
const RP_MOB=false;const RP_PM_DEFAULT=['KAL','POLY','DKP','FDP'];
const RP_LEGAL_STATE={"CA":["KAL","POLY"],"NJ":["KAL","POLY","DK","FD"]};
'''

def tapify_case(page):
    fns = ''.join(js_fn(page, n) + '\n' for n in ('rpBookLive', 'rpPm', 'rpHrefOf', 'rpDest', 'rpGo', 'rpTapify'))
    code = STUB + fns + r'''
var out={};var U='https://kalshi.com/markets/kxfix/kxfix-99';
var a=new El('A',{'data-book':'KAL','href':U});
rpTapify(a,'');out.none=a.getAttribute('href');out.noneKeeps=JSON.stringify(a._a).indexOf(U)>=0;
rpTapify(a,'CA');out.ca=a.getAttribute('href');
rpTapify(a,'');out.cleared=a.getAttribute('href');
rpGo(a,'CA');out.opened=opened.slice();
var t=new El('A',{'data-book':'DK','href':'https://sportsbook.example/','data-sbt':'https://sportsbook.example/{state}/event/1'});
rpTapify(t,'NJ');out.tmpl=t.getAttribute('href');
var p=new El('A',{'data-book':'POLY','href':'https://polymarket.com/event/x'});
rpTapify(p,'');out.poly=p.getAttribute('href');opened.length=0;rpGo(p,'NJ');out.polyOpened=opened.slice();
console.log(JSON.stringify(out));'''
    return node(code)

def geo_case(page, storage):
    fns = js_fn(page, 'rpShareLoc') + '\n' + js_fn(page, 'rpResolveState') + '\n'
    store = 'var _ls={};var localStorage={getItem:function(k){return k in _ls?_ls[k]:null;},setItem:function(k,v){_ls[k]=String(v);},removeItem:function(k){delete _ls[k];}};' if storage else ''
    code = r'''
var fetched=[];function fetch(u){fetched.push(String(u));return Promise.resolve({json:function(){return Promise.resolve({principalSubdivisionCode:'US-WA'});}});}
Object.defineProperty(globalThis,'navigator',{configurable:true,writable:true,value:{geolocation:{getCurrentPosition:function(ok){ok({coords:{latitude:45.638749,longitude:-122.661453}});}},
  permissions:{query:function(){return Promise.resolve({state:'granted'});}}}});
var document={getElementById:function(){return {style:{}};}};var window={};
function rpNote(){}function rpLSSet(){}function rpLSGet(){return null;}function rpLSDel(){}function rpLabel(){}function rpGo(){}function rpMaybeA2HS(){}
const RP_CODES=['WA','OR'];''' + store + fns + r'''
rpShareLoc();rpResolveState();
setTimeout(function(){console.log(JSON.stringify({fetched:fetched}));},80);'''
    return node(code)

BASE = {'date': '2099-10-04', 'date_label': 'Sunday, Oct 4', 'updated': 'fixture', 'record': '21-11', 'units_pl': '+4.76u',
        'units_ledger': None, 'yesterday': '', 'status_note': '', 'preview': False, 'parlay': None, 'posted_at': '2099-10-04T15:00:00Z'}
PICK = {'num': 1, 'name': 'Bills ML', 'market_class': 'ml', 'sub': 'fixture - model 66.0', 'odds': '-150', 'card_american': -150,
        'units': '5u', 'side': 'home',
        'game': {'away': 'New England Patriots', 'home': 'Buffalo Bills', 'commence': '2099-10-04T20:25:00Z', 'eid': '401999999'},
        'espn_league': 'football/nfl', 'league': 'NFL', 'best_book': 'Kalshi', 'card_source': 'Kalshi ask at lock'}
RAW = re.compile(r"pos\.coords\.(?:latitude|longitude)(?!\.toFixed\(2\))")

legacy = [os.path.join(SD, 'build_gh_page.py'), os.path.join(ROOT, 'previews', 'overlay', 'scripts', 'build_gh_page.py'), os.path.join(SD, 'game_page_template.html')]
for f in legacy:
    if os.path.exists(f):
        check(f'C-4.4 {os.path.relpath(f, ROOT)} sends no full-precision position to the geocoder', not RAW.search(open(f, encoding='utf-8').read()))

for B in BUILDERS:
    tag = os.path.basename(B)
    check(f'{tag}: C-4.4 the builder sends no full-precision position to the geocoder', not RAW.search(open(B, encoding='utf-8').read()))
    m = copy.deepcopy(BASE); m['picks'] = [copy.deepcopy(PICK)]
    rc, out, pages = build(B, m)
    check(f'{tag}: the card builds', rc == 0 and 'index.html' in pages, out[-400:])
    for name, page, storage in [('index.html', pages.get('index.html', ''), False)] + [(k, v, True) for k, v in sorted(pages.items()) if k.startswith('game-')][:1]:
        g = geo_case(page, storage)
        urls = g.get('fetched') or []
        check(f'{tag}: C-4.4 {name}: both lookups ran', len(urls) == 2, g)
        check(f'{tag}: C-4.4 {name}: the geocoder gets 45.64,-122.66 (2 decimals), never 45.638749,-122.661453',
              bool(urls) and all('latitude=45.64&longitude=-122.66&' in u and '45.6387' not in u and '122.6614' not in u for u in urls), urls)
        t = tapify_case(page)
        U = 'https://kalshi.com/markets/kxfix/kxfix-99'
        check(f'{tag}: C-4.5 {name}: with no state a live chip\'s href is "#" (got {t.get("none")!r})', t.get('none') == '#', t)
        check(f'{tag}: C-4.5 {name}: the destination is kept aside on the chip', t.get('noneKeeps') is True, t)
        check(f'{tag}: C-4.5 {name}: once a state resolves the chip carries its real href', t.get('ca') == U, t)
        check(f'{tag}: C-4.5 {name}: a state that goes away takes the href back to "#"', t.get('cleared') == '#', t)
        check(f'{tag}: C-4.5 {name}: a tap with a fresh state still opens the real destination', t.get('opened') == [U], t)
        check(f'{tag}: C-4.5 {name}: a state template route fills its state', t.get('tmpl') == 'https://sportsbook.example/nj/event/1', t)
        check(f'{tag}: C-4.5 {name}: POLY with no state is "#" and opens its market once a state is fresh',
              t.get('poly') == '#' and t.get('polyOpened') == ['https://polymarket.com/event/x'], t)
    ix = pages.get('index.html', '')
    check(f'{tag}: C-4.5 the rebuild refresh never writes a venue href without a state',
          '&&na.href)a.href=na.href' not in ix and '&&ns.href)s.href=ns.href' not in ix)

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
