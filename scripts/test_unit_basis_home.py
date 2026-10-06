#!/usr/bin/env python3
"""Unit basis line on Home (owner design, Oct 2): '1u = $5 per $1,000 in bankroll' must be visible on
the Home page next to the record line. It lived only in the record popover (#rpRecPop), which nothing
opens any more (the record chip taps through to record.html), so no visitor ever saw it.

Builds an empty card and a one-pick card with each builder twin in a throwaway tree (network blocked
through a dead proxy) and checks the built index.html:
- the line is rendered outside every hidden container, as the first line of the page head right
  under the nav record strip (above the Yesterday line and the date);
- it is Home-only: it carries .home-only, the stylesheet shows .home-only on body.tab-home alone,
  and no rule hides the line itself on Home;
- PAST_HIDE_MONEY stays scoped to Past Tickets: off the Home tab no bankroll wording is visible
  anywhere in the static page (every occurrence sits in a hidden container or a Home-only element),
  so the Past Tickets view shows none; the Past Tickets client keeps its own render-time hide.
Run: python3 scripts/test_unit_basis_home.py [builder.py ...]   (default: both twins; no side effects)"""
import copy, html.parser, json, os, re, shutil, subprocess, sys, tempfile

from fixtures.card_contract import stamped, market, published_snapshot

SD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SD)
BUILDERS = [os.path.abspath(a) for a in sys.argv[1:]] or [os.path.join(SD, 'build_gh_page_v2.py'), os.path.join(SD, '_build_nocanon_v2.py')]
LINE = '1u = $5 per $1,000 in bankroll'
failures = 0
def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or not detail else '  [%s]' % (detail,)))
    if not ok: failures += 1

DEAD = 'http://127.0.0.1:9'
def build(builder, manifest):
    d = tempfile.mkdtemp(prefix='rp-unitbasis-')
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
        p = os.path.join(d, 'index.html')
        return r.returncode, (open(p).read() if os.path.exists(p) else ''), r.stderr
    finally:
        shutil.rmtree(d, ignore_errors=True)

VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}
class Tree(html.parser.HTMLParser):
    """Element stack per text node: [(tag, attrs-dict), ...] from <html> down. Script and style text is skipped."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.texts, self.first_child, self.keep = [], [], {}, []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.keep.append(a)  # ids stay unique while the tree lives
        if self.stack:
            self.first_child.setdefault(id(self.stack[-1][1]), (tag, a))
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
def hidden(chain): return any('hidden' in a for _, a in chain)
def home_only(chain): return any('home-only' in classes(a) for _, a in chain)

def css_rules(page):
    css = '\n'.join(re.findall(r'<style>([\s\S]*?)</style>', page))
    css = re.sub(r'/\*[\s\S]*?\*/', '', css)
    return [(m.group(1).strip(), m.group(2)) for m in re.finditer(r'([^{}@]+)\{([^{}]*)\}', css)]

BASE = {'date': '2099-10-01', 'date_label': 'Thursday, Oct 1', 'updated': 'Oct 1, 8:42 AM PT', 'record': '21-11',
        'units_pl': '+4.76u', 'units_ledger': None, 'yesterday': '', 'status_note': '', 'preview': False, 'parlay': None}
DEVILS = {'num': 1, 'name': 'Devils ML', 'market_class': 'ml', 'sub': 'PHI @ NJ - model 66.0', 'odds': '-162', 'units': '5u', 'side': 'home',
          'game': {'away': 'Philadelphia Flyers', 'home': 'New Jersey Devils', 'commence': '2099-10-01T23:00Z', 'eid': ''},
          'espn_league': 'hockey/nhl', 'league': 'NHL', 'best_book': 'DraftKings'}
CARDS = {'empty card': dict(copy.deepcopy(BASE), picks=[]), 'one-pick card': dict(copy.deepcopy(BASE), picks=[copy.deepcopy(DEVILS)])}

for B in BUILDERS:
    bn = os.path.basename(B)
    for label, man in CARDS.items():
        rc, page, err = build(B, man)
        check('%s %s: builds' % (bn, label), rc == 0 and len(page) > 10000, err[-300:])
        if not page:
            continue
        t = Tree(); t.feed(page)
        hits = [(txt, ch) for txt, ch in t.texts if LINE in txt]
        shown = [ch for _, ch in hits if not hidden(ch)]
        check('%s %s: "%s" rendered outside every hidden container' % (bn, label, LINE), bool(shown),
              'only inside hidden ' + ', '.join('#' + str(next((a.get('id') for _, a in ch if 'hidden' in a), '?')) for _, ch in hits))
        if not shown:
            continue
        ch = shown[0]
        el_tag, el = ch[-1]
        head = next(((tg, a) for tg, a in ch if 'rphead' in classes(a)), None)
        check('%s %s: it sits in the page head right under the nav record strip' % (bn, label), head is not None)
        if head is not None:
            first = t.first_child.get(id(head[1]))
            check('%s %s: it is the first line of the head (above Yesterday and the date)' % (bn, label),
                  first is not None and first[1] is el, first and (first[0], first[1].get('class')))
        check('%s %s: it is Home-only' % (bn, label), 'home-only' in classes(el), el.get('class'))
        rules = css_rules(page)
        check('%s %s: .home-only is hidden by default' % (bn, label),
              any(s == '.home-only' and re.search(r'display\s*:\s*none', d) for s, d in rules))
        check('%s %s: .home-only is shown on body.tab-home' % (bn, label),
              any('body.tab-home .home-only' in [x.strip() for x in s.split(',')] and re.search(r'display\s*:\s*block', d) for s, d in rules))
        reshow = [s for s, d in rules if '.home-only' in s and re.search(r'display\s*:\s*(?!none)', d)
                  and not all(x.strip().startswith('body.tab-home') for x in s.split(','))]
        check('%s %s: no rule shows .home-only on another tab' % (bn, label), not reshow, reshow[:3])
        own = ['#' + el['id']] if el.get('id') else []
        own += ['.' + c for c in classes(el) if c != 'home-only']
        hiders = [s for s, d in rules if re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', d)
                  and any(re.search(re.escape(o) + r'(?![\w-])', s) for o in own)
                  and not re.search(r'body\.tab-(?!home)', s) and '.recpop' not in s]
        check('%s %s: no rule hides the line itself on Home' % (bn, label), not hiders, hiders[:3])
        check('%s %s: the nav record strip still carries the record' % (bn, label), 'id="rpNavRecW">21<' in page and 'id="rpNavRecL">11<' in page)
        leaks = [txt.strip()[:60] for txt, c in t.texts if re.search(r'bankroll', txt, re.I) and not hidden(c) and not home_only(c)]
        check('%s %s: off the Home tab no bankroll wording is visible (Past Tickets shows none)' % (bn, label), not leaks, leaks[:3])
    src = open(B).read()
    check('%s: PAST_HIDE_MONEY stays on for the Past Tickets render' % bn, bool(re.search(r'^\s*PAST_HIDE_MONEY\s*=\s*True\b', src, re.M)))

print('FAILURES: %d' % failures if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
