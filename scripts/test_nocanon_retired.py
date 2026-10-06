#!/usr/bin/env python3
"""index_nocanon.html is retired (Oct 2): it was an orphaned second copy of the homepage, served
publicly at /index_nocanon.html, read by nothing but the health gate, and rewritten whenever a twin
build was pointed at it. It stays a URL that resolves, as a fixed notice that tells crawlers not to
index it, names the homepage as canonical and sends visitors there.

- each builder twin, asked to write index_nocanon.html, writes that notice (noindex, canonical
  https://rix-picks.com/, an instant hop and a link to ./, no homepage markup or script), the same
  bytes on every build and from both twins; a build of index.html in the same tree is still the full
  homepage and leaves the notice alone;
- the tracked index_nocanon.html is exactly the notice the builder writes, and sitemap.xml does not
  list it;
- the health gate no longer needs a homepage there: with the notice, or with the file absent, it
  reports nothing about index_nocanon.html; a full homepage copied back there is a FAIL that names it.
Builds run in throwaway trees with the network blocked (dead proxy); the gate runs in a throwaway
copy of this checkout. No side effects.
Run: python3 scripts/test_nocanon_retired.py"""
import json, os, re, shutil, subprocess, sys, tempfile

from fixtures.card_contract import stamped

SD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SD)
TWINS = [os.path.join(SD, 'build_gh_page_v2.py'), os.path.join(SD, '_build_nocanon_v2.py')]
failures = 0
def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or not detail else '  [%s]' % (detail,)))
    if not ok: failures += 1

DEAD = 'http://127.0.0.1:9'
ENV = dict(os.environ, RP_REFRESH='1', http_proxy=DEAD, https_proxy=DEAD, HTTP_PROXY=DEAD, HTTPS_PROXY=DEAD)
MAN = {'date': '2099-10-01', 'date_label': 'Thursday, Oct 1', 'updated': 'Oct 1, 8:42 AM PT', 'record': '21-11',
       'units_pl': '+4.76u', 'units_ledger': None, 'yesterday': '', 'status_note': '', 'preview': False, 'parlay': None, 'picks': []}

def tree(builder):
    d = tempfile.mkdtemp(prefix='rp-nocanon-')
    os.makedirs(os.path.join(d, 'scripts')); os.makedirs(os.path.join(d, 'slates'))
    shutil.copy(builder, os.path.join(d, 'scripts', 'build_gh_page_v2.py'))
    for f in ('index_v2.js', 'index_v2.css', 'game_page_template.html', 'team_page_template.html', 'poly_us.py'):
        shutil.copy(os.path.join(SD, f), os.path.join(d, 'scripts', f))
    for f in ('feed_arbiter.js', 'feed_registry.json', 'config_leagues.json'):
        shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
    json.dump(stamped(builder,MAN), open(os.path.join(d, 'manifest.json'), 'w'), indent=1)
    json.dump([], open(os.path.join(d, 'slates', 'odds_prefill.json'), 'w'))
    return d
def build(d, out):
    r = subprocess.run([sys.executable, os.path.join(d, 'scripts', 'build_gh_page_v2.py'), 'manifest.json', out],
                       cwd=d, env=ENV, capture_output=True, text=True, timeout=600)
    p = os.path.join(d, out)
    return r.returncode, (open(p, 'rb').read() if os.path.exists(p) else b''), r.stderr

def is_notice(b):
    s = b.decode('utf-8', 'replace')
    return {
        'noindex': '<meta name="robots" content="noindex">' in s,
        'canonical to https://rix-picks.com/': '<link rel="canonical" href="https://rix-picks.com/">' in s,
        'instant hop to ./': re.search(r'<meta http-equiv="refresh" content="0; ?url=\./">', s) is not None,
        'link to ./': '<a href="./">' in s,
        'no script': '<script' not in s.lower(),
        'no homepage modules': 'rpCmbGo' not in s and 'rpNavRec' not in s,
        'small': 0 < len(b) < 4000,
    }

notices = {}
for B in TWINS:
    bn = os.path.basename(B)
    d = tree(B)
    try:
        rc, b1, err = build(d, 'index_nocanon.html')
        check('%s: a build aimed at index_nocanon.html runs' % bn, rc == 0, err[-300:])
        props = is_notice(b1)
        for k, v in props.items():
            check('%s: index_nocanon.html is the retired notice - %s' % (bn, k), v, '%d bytes' % len(b1))
        rc, b2, _ = build(d, 'index_nocanon.html')
        check('%s: the notice is byte-stable across builds' % bn, rc == 0 and b1 == b2)
        rc, home, err = build(d, 'index.html')
        check('%s: index.html in the same tree is still the full homepage' % bn, rc == 0 and b'rpCmbGo' in home and b'rpNavRec' in home, err[-300:])
        check('%s: the index.html build leaves the notice alone' % bn, open(os.path.join(d, 'index_nocanon.html'), 'rb').read() == b1)
        notices[bn] = b1
    finally:
        shutil.rmtree(d, ignore_errors=True)
vals = list(notices.values())
check('both twins write the same notice', len(vals) == 2 and vals[0] == vals[1])
tracked = open(os.path.join(ROOT, 'index_nocanon.html'), 'rb').read() if os.path.exists(os.path.join(ROOT, 'index_nocanon.html')) else b''
check('the tracked index_nocanon.html is exactly the notice the builder writes', bool(vals) and tracked == vals[0],
      '%d bytes tracked' % len(tracked))
check('sitemap.xml does not list index_nocanon.html', 'index_nocanon' not in open(os.path.join(ROOT, 'sitemap.xml')).read())

# the health gate, in a throwaway copy of this checkout
g = tempfile.mkdtemp(prefix='rp-nocanon-gate-')
try:
    shutil.copytree(ROOT, os.path.join(g, 'r'), ignore=shutil.ignore_patterns('.git', '__pycache__', 'node_modules'))
    r = os.path.join(g, 'r')
    def gate():
        p = subprocess.run(['node', 'scripts/health_gate.js'], cwd=r, capture_output=True, text=True, timeout=600)
        return [l for l in (p.stdout + p.stderr).split('\n') if 'index_nocanon' in l]
    nc = os.path.join(r, 'index_nocanon.html')
    if vals: open(nc, 'wb').write(vals[0])
    lines = gate()
    check('gate with the notice: no FAIL about index_nocanon.html', not any(l.startswith('FAIL') for l in lines), lines)
    os.remove(nc)
    lines = gate()
    check('gate with the file absent: no FAIL about index_nocanon.html', not any(l.startswith('FAIL') for l in lines), lines)
    shutil.copy(os.path.join(r, 'index.html'), nc)
    lines = gate()
    check('gate with a full homepage back at index_nocanon.html: a FAIL names it', any(l.startswith('FAIL') for l in lines), lines)
finally:
    shutil.rmtree(g, ignore_errors=True)

print('FAILURES: %d' % failures if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
