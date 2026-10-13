#!/usr/bin/env python3
"""No bankroll unit-basis line anywhere on the site (owner, Oct 13): the line '1u = $5 per $1,000 in
bankroll' that sat in the nav record popover (#rpRecPop .unitmath) and in the Home page head
(#rpUnitBasis, Oct 2 design) is removed from every page and template - the elements, not just the text.

Builds an empty card and a one-pick card with each builder twin in a throwaway tree (network blocked
through a dead proxy) and checks the built index.html and futures.html:
- no text node (hidden or not) names a bankroll or a per-$1,000 unit basis;
- no #rpUnitBasis element, no .unitbasis class, no .unitmath element inside the record popover;
- the nav record strip and the popover still carry the record exactly as the manifest gives it;
- PAST_HIDE_MONEY stays on for the Past Tickets render (unchanged rule, kept under watch here);
- the builder sources, the stylesheet and trinity/ carry no copy of the wording and no dead
  .unitbasis rule.
Run: python3 scripts/test_unit_basis_removed.py [builder.py ...]   (default: both twins; no side effects)"""
import copy, html.parser, json, os, re, shutil, subprocess, sys, tempfile

from fixtures.card_contract import stamped, market, published_snapshot

SD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SD)
BUILDERS = [os.path.abspath(a) for a in sys.argv[1:]] or [os.path.join(SD, 'build_gh_page_v2.py'), os.path.join(SD, '_build_nocanon_v2.py')]
WORDING = re.compile(r'bankroll|per \$1,000|1u\s*=\s*\$', re.I)
failures = 0
def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or not detail else '  [%s]' % (detail,)))
    if not ok: failures += 1

DEAD = 'http://127.0.0.1:9'
def build(builder, manifest):
    d = tempfile.mkdtemp(prefix='rp-nounitbasis-')
    try:
        os.makedirs(os.path.join(d, 'scripts')); os.makedirs(os.path.join(d, 'slates'))
        bsrc = os.path.dirname(builder)
        shutil.copy(builder, os.path.join(d, 'scripts', 'build_gh_page_v2.py'))
        for f in ('index_v2.js', 'index_v2.css', 'game_page_template.html', 'team_page_template.html', 'poly_us.py'):
            shutil.copy(os.path.join(bsrc if os.path.exists(os.path.join(bsrc, f)) else SD, f), os.path.join(d, 'scripts', f))
        for f in ('feed_arbiter.js', 'feed_registry.json', 'config_leagues.json'):
            shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
        manifest=dict(manifest,picks=[market(p) for p in manifest.get('picks',[])])
        manifest=stamped(builder,manifest)
        json.dump(manifest, open(os.path.join(d, 'manifest.json'), 'w'), indent=1)
        published_snapshot(d,builder,manifest)
        json.dump([], open(os.path.join(d, 'slates', 'odds_prefill.json'), 'w'))
        env = dict(os.environ, RP_REFRESH='1', http_proxy=DEAD, https_proxy=DEAD, HTTP_PROXY=DEAD, HTTPS_PROXY=DEAD)
        r = subprocess.run([sys.executable, os.path.join(d, 'scripts', 'build_gh_page_v2.py'), 'manifest.json', 'index.html'],
                           cwd=d, env=env, capture_output=True, text=True, timeout=600)
        pages = {}
        for n in ('index.html', 'futures.html'):
            p = os.path.join(d, n)
            pages[n] = open(p).read() if os.path.exists(p) else ''
        return r.returncode, pages, r.stderr
    finally:
        shutil.rmtree(d, ignore_errors=True)

VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}
class Tree(html.parser.HTMLParser):
    """Element stack per text node: [(tag, attrs-dict), ...] from <html> down. Script and style text is skipped."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.texts, self.elements = [], [], []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.elements.append((tag, a, list(self.stack)))
        if tag not in VOID:
            self.stack.append((tag, a))
    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
    def handle_data(self, data):
        if data.strip() and not any(t in ('script', 'style') for t, _ in self.stack):
            self.texts.append((data, list(self.stack)))

def classes(a): return set((a.get('class') or '').split())

BASE = {'date': '2099-10-01', 'date_label': 'Thursday, Oct 1', 'updated': 'Oct 1, 8:42 AM PT', 'record': '21-11',
        'units_pl': '+4.76u', 'units_ledger': None, 'yesterday': '', 'status_note': '', 'preview': False, 'parlay': None}
DEVILS = {'num': 1, 'name': 'Devils ML', 'market_class': 'ml', 'sub': 'PHI @ NJ - model 66.0', 'odds': '-162', 'units': '5u', 'side': 'home',
          'game': {'away': 'Philadelphia Flyers', 'home': 'New Jersey Devils', 'commence': '2099-10-01T23:00Z', 'eid': ''},
          'espn_league': 'hockey/nhl', 'league': 'NHL', 'best_book': 'DraftKings'}
CARDS = {'empty card': dict(copy.deepcopy(BASE), picks=[]), 'one-pick card': dict(copy.deepcopy(BASE), picks=[copy.deepcopy(DEVILS)])}

for B in BUILDERS:
    bn = os.path.basename(B)
    for label, man in CARDS.items():
        rc, pages, err = build(B, man)
        page = pages['index.html']
        check('%s %s: builds' % (bn, label), rc == 0 and len(page) > 10000, err[-300:])
        if not page:
            continue
        for name, pg in pages.items():
            if not pg:
                continue
            t = Tree(); t.feed(pg)
            hits = [txt.strip()[:60] for txt, _ in t.texts if WORDING.search(txt)]
            check('%s %s %s: no text names a bankroll or a per-$1,000 unit basis (hidden or shown)' % (bn, label, name), not hits, hits[:3])
            ids = [a.get('id') for _, a, _ in t.elements if a.get('id') == 'rpUnitBasis']
            check('%s %s %s: no #rpUnitBasis element' % (bn, label, name), not ids)
            ub = [tg for tg, a, _ in t.elements if 'unitbasis' in classes(a)]
            check('%s %s %s: no .unitbasis element' % (bn, label, name), not ub, ub[:3])
        t = Tree(); t.feed(page)
        inpop = [tg for tg, a, ch in t.elements if 'unitmath' in classes(a) and any(x.get('id') == 'rpRecPop' for _, x in ch)]
        check('%s %s: the record popover carries no .unitmath line' % (bn, label), not inpop, inpop[:3])
        check('%s %s: the nav record strip still carries the record' % (bn, label), 'id="rpNavRecW">21<' in page and 'id="rpNavRecL">11<' in page)
        check('%s %s: the popover still states the overall record' % (bn, label), 'RixPicks Overall Record: 21-11' in page)
        check('%s %s: the popover still carries the units P/L' % (bn, label), 'id="rpUnits"' in page and 'Units: +4.76u' in page)
    src = open(B).read()
    check('%s: PAST_HIDE_MONEY stays on for the Past Tickets render' % bn, bool(re.search(r'^\s*PAST_HIDE_MONEY\s*=\s*True\b', src, re.M)))
    check('%s: the builder source carries no copy of the wording' % bn, not re.search(r'per \$1,000|1u = \$', src))

for rel in ('scripts/index_v2.css', 'trinity/trinity.js', 'scripts/build_gh_page.py'):
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        continue
    src = open(p).read()
    check('%s: no copy of the wording' % rel, not re.search(r'per \$1,000|1u = \$', src))
    check('%s: no dead .unitbasis selector' % rel, 'unitbasis' not in src)

print('FAILURES: %d' % failures if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
