#!/usr/bin/env python3
"""C-2: every "today" the page builder and the page itself compare is the America/Los_Angeles calendar date, never
the machine's or the viewer's own date.
 C-2.1 the shipped ledger's card-lock entry (__card__ in shipped_books.json) is written by a publish build of the
       current card wherever the build runs. Before, the gate compared the card date with date.today(): on a
       machine whose own date is ahead of the Pacific date (a UTC runner after 17:00 PT; here a UTC+14 zone, ahead
       from about 03:00 PT on) the current card read as past and the entry was silently not written. Now one
       _pt_today() decides, and a publish build of a current card with a known lock that would still leave the
       ledger without an entry for its date holds (exit 3) instead of skipping quietly.
 C-2.2 a card with no game date falls back to the Pacific date (the date header's data-date), not the machine's.
 C-2.3 the page's ptDate() (Dingers Only and the NFL ideas modules) returns '' when the browser cannot give the
       Pacific date, and both modules then hide instead of comparing the file's date with the viewer's own date.
Builds real cards with each builder twin in a throwaway tree, network sent to a dead proxy; the page modules run
in node with a stub DOM. Run: python3 scripts/test_c2_pt_today.py [builder.py ...]   (default: both twins)"""
import copy, datetime, json, os, re, shutil, subprocess, sys, tempfile
from zoneinfo import ZoneInfo

from fixtures.card_contract import stamped, market, published_snapshot

SD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SD)
BUILDERS = [os.path.abspath(a) for a in sys.argv[1:]] or [os.path.join(SD, 'build_gh_page_v2.py'), os.path.join(SD, '_build_nocanon_v2.py')]
DEAD = 'http://127.0.0.1:9'
AHEAD = 'Etc/GMT-14'  # UTC+14: its calendar date is past the Pacific date from about 03:00 PT on
failures = 0

def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or detail == '' else '  [' + str(detail)[-400:] + ']'))
    if not ok:
        failures += 1

def build(builder, manifest, tz, seed=None, publish=False):
    d = tempfile.mkdtemp(prefix='rp-c2-')
    try:
        os.makedirs(os.path.join(d, 'scripts')); os.makedirs(os.path.join(d, 'slates'))
        bsrc = os.path.dirname(builder)
        shutil.copy(builder, os.path.join(d, 'scripts', 'build_gh_page_v2.py'))
        for f in ('index_v2.js', 'index_v2.css', 'game_page_template.html', 'team_page_template.html', 'poly_us.py'):
            shutil.copy(os.path.join(bsrc if os.path.exists(os.path.join(bsrc, f)) else SD, f), os.path.join(d, 'scripts', f))
        for f in ('feed_arbiter.js', 'feed_registry.json', 'config_leagues.json'):
            shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
        for rel, text in (seed or {}).items():
            open(os.path.join(d, rel), 'w', encoding='utf-8').write(text)
        manifest = dict(manifest, picks=[market(p) for p in manifest.get('picks', [])])
        manifest = stamped(builder, manifest)
        json.dump(manifest, open(os.path.join(d, 'manifest.json'), 'w'), indent=1)
        published_snapshot(d, builder, manifest)
        json.dump([], open(os.path.join(d, 'slates', 'odds_prefill.json'), 'w'))
        env = dict(os.environ, RP_REFRESH='1', http_proxy=DEAD, https_proxy=DEAD, HTTP_PROXY=DEAD, HTTPS_PROXY=DEAD,
                   NO_PROXY='', no_proxy='', TZ=tz)
        env.pop('RP_PUBLISH', None)
        if publish:
            env['RP_PUBLISH'] = '1'
        r = subprocess.run([sys.executable, os.path.join(d, 'scripts', 'build_gh_page_v2.py'), 'manifest.json', 'index.html'],
                           cwd=d, env=env, capture_output=True, text=True, timeout=600)
        ix = os.path.join(d, 'index.html')
        index = open(ix, encoding='utf-8').read() if os.path.exists(ix) else ''
        sb = os.path.join(d, 'shipped_books.json')
        shipped = json.load(open(sb)) if os.path.exists(sb) else None
        return r.returncode, r.stdout + r.stderr, index, shipped
    finally:
        shutil.rmtree(d, ignore_errors=True)

PT = ZoneInfo('America/Los_Angeles')
now_pt = datetime.datetime.now(PT)
TODAY = now_pt.date().isoformat()
# tonight 23:30 PT, as UTC with an explicit offset; posted 5 minutes ago (a known lock)
COMMENCE = now_pt.replace(hour=23, minute=30, second=0, microsecond=0).astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
POSTED = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ')
ahead_now = datetime.datetime.now(ZoneInfo(AHEAD)).date().isoformat()

BASE = {'date': TODAY, 'date_label': now_pt.strftime('%A, %b ') + str(now_pt.day), 'updated': 'fixture', 'record': '21-11',
        'units_pl': '+4.76u', 'units_ledger': None, 'yesterday': '', 'status_note': '', 'preview': False, 'parlay': None}
PICK = {'num': 1, 'name': 'Bills ML', 'market_class': 'ml', 'sub': 'fixture - model 66.0', 'odds': '-150', 'card_american': -150,
        'units': '5u', 'side': 'home',
        'game': {'away': 'New England Patriots', 'home': 'Buffalo Bills', 'commence': COMMENCE, 'eid': 'WRONG-EID-123'},
        'espn_league': 'football/nfl', 'league': 'NFL', 'best_book': 'Kalshi', 'card_source': 'Kalshi ask at lock'}

def card(picks, drop=(), **kw):
    m = copy.deepcopy(BASE); m['picks'] = copy.deepcopy(picks); m.update(kw)
    for k in drop:
        m.pop(k, None)
    return m

def rpdate(index):
    mo = re.search(r'class="rpdate" data-date="([^"]*)"', index)
    return mo.group(1) if mo else None

def module(index, marker):
    """The inline <script> block that hydrates one module (found by its box id)."""
    for mo in re.finditer(r'<script>(\(function\(\)\{[\s\S]*?\}\)\(\);)</script>', index):
        if marker in mo.group(1)[:200]:
            return mo.group(1)
    return ''

def run_module(js, payload, intl_ok):
    """Run a module block in node: fetch returns `payload`; the browser's Pacific-date call throws unless intl_ok.
    Returns {hidden, html} of the module box."""
    code = '\n'.join([
        'var box={innerHTML:"",parentNode:{parentNode:{style:{}}}};var tab={style:{}};',
        'var document={getElementById:function(id){return id==="rpNflTab"?tab:box;},querySelectorAll:function(){return [];}};',
        'var window={rpLg:{markKind:function(){}}};function setInterval(){}',
        'if(!%s){Date.prototype.toLocaleDateString=function(){throw new RangeError("no Intl");};}' % ('true' if intl_ok else 'false'),
        'var P=%s;function fetch(){return Promise.resolve({ok:true,json:function(){return Promise.resolve(P);}});}' % json.dumps(payload),
        js,
        'setTimeout(function(){console.log(JSON.stringify({hidden:box.parentNode.parentNode.style.display==="none",html:box.innerHTML}));},50);'])
    r = subprocess.run(['node', '-e', code], capture_output=True, text=True, timeout=60)
    try: return json.loads(r.stdout)
    except ValueError: return {'error': r.stderr[-600:]}

def local_date():
    d = datetime.date.today()
    return '%04d-%02d-%02d' % (d.year, d.month, d.day)

for B in BUILDERS:
    tag = os.path.basename(B)
    src = open(B, encoding='utf-8').read()
    check(f'{tag}: C-2.1/C-2.2 no bare date.today() left in the builder', not re.search(r'\bdate\.today\(\)', src),
          [m.start() for m in re.finditer(r'\bdate\.today\(\)', src)])

    # C-2.1: the lock entry is written for today's card on a machine whose own date is ahead of the Pacific date
    rc, out, index, shipped = build(B, card([PICK], posted_at=POSTED), AHEAD, publish=True)
    entry = (shipped or {}).get('__card__') or {}
    check(f'{tag}: C-2.1 [{AHEAD}, machine date {ahead_now}, PT {TODAY}] a publish build of today\'s card exits 0', rc == 0, out[-600:])
    check(f'{tag}: C-2.1 [{AHEAD}] the shipped ledger carries the card-lock entry for {TODAY}', entry.get('date') == TODAY and bool(entry.get('picks_sha')),
          (entry, out[-300:]))
    rc, out, index, shipped = build(B, card([PICK], posted_at=POSTED), 'America/Los_Angeles', publish=True)
    check(f'{tag}: C-2.1 [Pacific] the same build writes the same entry', rc == 0 and ((shipped or {}).get('__card__') or {}).get('date') == TODAY, out[-300:])
    # C-2.1 hold: a builder whose lock write is skipped (a mutant with the write disabled) holds a publish build
    mut = os.path.join(tempfile.mkdtemp(prefix='rp-c2-mut-'), 'build_gh_page_v2.py')
    msrc = src.replace("NEWSHIPPED['__card__']={'date':_CARD_DATE", "_c21_skipped={'date':_CARD_DATE", 1)
    open(mut, 'w', encoding='utf-8').write(msrc)
    for f in ('index_v2.js', 'index_v2.css', 'game_page_template.html', 'team_page_template.html', 'poly_us.py'):
        shutil.copy(os.path.join(SD, f), os.path.join(os.path.dirname(mut), f))
    rc, out, index_m, shipped = build(mut, card([PICK], posted_at=POSTED), 'America/Los_Angeles', publish=True)
    check(f'{tag}: C-2.1 a publish build whose lock write is skipped holds (exit 3), nothing written',
          msrc != src and rc == 3 and 'BUILD FAILED: card-lock entry' in out and not index_m and shipped is None, (rc, out[-300:]))
    rc, out, index_m, shipped = build(mut, card([PICK], posted_at=POSTED), 'America/Los_Angeles')
    check(f'{tag}: C-2.1 a candidate (non-publish) build never writes the ledger and is not held by it', rc == 0, out[-300:])
    shutil.rmtree(os.path.dirname(mut), ignore_errors=True)

    # C-2.2: a card with no game date falls back to the Pacific date
    rc, out, index, _ = build(B, card([], drop=('date',)), AHEAD)
    check(f'{tag}: C-2.2 [{AHEAD}] a gameless card with no manifest date is dated the Pacific date {TODAY} (got {rpdate(index)})',
          rc == 0 and rpdate(index) == TODAY, out[-400:])

    # C-2.3: the page modules never fall back to the viewer's own date
    if not index:
        rc, out, index, _ = build(B, card([PICK], posted_at=POSTED), 'America/Los_Angeles')
    ding, nfl = module(index, 'rpDing'), module(index, 'rpNflIdeas')
    check(f'{tag}: C-2.3 the Dingers Only and NFL ideas modules are on the page', bool(ding) and bool(nfl))
    dpick = {'player': 'A Batter', 'team': 'NYY', 'matchup': 'NYY at BOS', 'time': '4:05 PM', 'market': 'To hit a HR', 'links': []}
    ncard = {'title': 'Idea', 'legs': [{'player': 'A Receiver', 'market': '60+ yards', 'links': []}]}
    for name, js, payload, shown in (
            ('Dingers Only', ding, {'date': local_date(), 'picks': [dpick]}, lambda t: not t.get('hidden') and 'A Batter' in t.get('html', '')),
            ('NFL ideas', nfl, {'date': local_date(), 'cards': [ncard]}, lambda t: 'No NFL ideas today' not in t.get('html', '') and bool(t.get('html')))):
        if not js:
            continue
        t = run_module(js, payload, intl_ok=False)
        check(f'{tag}: C-2.3 {name}: with no Pacific date available the module does not show a file dated the viewer\'s own date', not shown(t) and 'error' not in t, t)
        t = run_module(js, dict(payload, date=TODAY), intl_ok=True)
        check(f'{tag}: C-2.3 {name}: with the Pacific date available a file dated {TODAY} still shows', shown(t), t)

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
