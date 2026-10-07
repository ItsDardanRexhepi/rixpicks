#!/usr/bin/env python3
"""Fixture for robots.txt: internal source, ops notes, incident records and run logs on rix-picks.com
are disallowed for crawlers, while every site page and every same-origin file a page loads (scripts,
feeds, icons, sitemap URLs) stays allowed. Rules are evaluated the RFC 9309 way (longest match wins,
Allow wins a tie, * and $ patterns) and, for plain prefix rules, with Python's first-match
robotparser too, so older crawlers read it the same. Page resources are read from the tracked pages
themselves, so a new script a page starts loading is checked automatically. No side effects."""
import os, re, subprocess, sys, urllib.robotparser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
failures = 0
def check(name, cond, detail=''):
    global failures
    print(('OK  ' if cond else 'FAIL'), name, '' if cond else detail)
    if not cond: failures += 1

lines = open(os.path.join(ROOT, 'robots.txt')).read().split('\n')
rules, star = [], False
for raw in lines:
    l = raw.split('#', 1)[0].strip()
    if ':' not in l: continue
    k, v = (x.strip() for x in l.split(':', 1))
    k = k.lower()
    if k == 'user-agent': star = (v == '*')
    elif star and k in ('allow', 'disallow') and v:
        rx = '^' + re.escape(v[:-1] if v.endswith('$') else v).replace(r'\*', '.*') + ('$' if v.endswith('$') else '')
        rules.append((k == 'allow', len(v), re.compile(rx), v))
def allowed(path):
    best = None
    for allow, n, rx, _ in rules:
        if rx.match(path) and (best is None or n > best[1] or (n == best[1] and allow)):
            best = (allow, n)
    return True if best is None else best[0]
rp = urllib.robotparser.RobotFileParser(); rp.parse(lines); rp.modified()
def legacy_ok(path):
    return rp.can_fetch('*', 'https://rix-picks.com' + path)

tracked = [f for f in subprocess.run(['git', '-C', ROOT, 'ls-files'], capture_output=True, text=True).stdout.split('\n') if f]
INTERNAL_DIRS = ('.github/', 'core/', 'docs/', 'incidents/', 'previews/', 'scripts/', 'tests/', 'workers/')
INTERNAL_EXT = ('.py', '.pyc', '.md', '.sh', '.jsonl')

# 1. internal paths named in the finding, plus every tracked internal file
named = ['/incidents/36390649045.md', '/docs/feed_bug_ledger.md', '/previews/overlay/scripts/build_gh_page.py',
         '/core/record_pipe.py', '/core/units.py', '/core/__pycache__/units.cpython-310.pyc',
         '/scripts/build_gh_page_v2.py', '/scripts/health_gate.js', '/tests/run_tests.py',
         '/.github/workflows/x_feed.yml', '/odds_moves.jsonl', '/price_history.jsonl']
for p in named:
    check('disallowed: %s' % p, not allowed(p))
# Scripts the pages load from /scripts/ are page resources, allowed by name in robots.txt; the rest of /scripts/ is source.
PAGE_SCRIPTS = ('scripts/record_today.js',)
internal = [f for f in tracked if (f.startswith(INTERNAL_DIRS) or f.endswith(INTERNAL_EXT)) and f not in PAGE_SCRIPTS]
leaks = [f for f in internal if allowed('/' + f)]
check('every tracked internal file disallowed (%d files)' % len(internal), not leaks, leaks[:5])
legacy = [f for f in internal if f.startswith(INTERNAL_DIRS) and legacy_ok('/' + f)]
check('first-match crawlers also skip the internal directories', not legacy, legacy[:5])

# 2. every page and every same-origin resource a page loads stays allowed
pages = [f for f in tracked if f.endswith('.html') and '/' not in f]
need = {'/', '/robots.txt', '/sitemap.xml'} | {'/' + p for p in pages}
REF = re.compile(r"""(?:fetch\(|src=|href=|importScripts\()["']([^"'#?]+)""")
for f in pages + ['myprofile.js', 'ticket-feed.js', 'feed_arbiter.js', 'OneSignalSDKWorker.js'] + list(PAGE_SCRIPTS):
    fp = os.path.join(ROOT, f)
    if not os.path.exists(fp): continue
    for ref in REF.findall(open(fp, encoding='utf-8', errors='ignore').read()):
        if re.match(r'^(?:[a-z]+:|//|\+|\.?/?$)', ref) or ' ' in ref: continue
        need.add('/' + ref.lstrip('./'))
for m in re.findall(r'"src"\s*:\s*"([^"?]+)', open(os.path.join(ROOT, 'site.webmanifest')).read()):
    need.add('/' + m.lstrip('/'))
for loc in re.findall(r'<loc>https://rix-picks\.com(/[^<]*)</loc>', open(os.path.join(ROOT, 'sitemap.xml')).read()):
    need.add(loc)
need |= {'/' + f for f in tracked if f.startswith('slates/') and f.endswith('.json')}
blocked = sorted(p for p in need if not allowed(p))
check('every page and page-loaded resource allowed (%d paths)' % len(need), not blocked, blocked[:8])
plain = sorted(p for p in need if not legacy_ok(p))
check('first-match crawlers allow them too', not plain, plain[:8])
check('page script under /scripts/ allowed', allowed('/scripts/record_today.js') and legacy_ok('/scripts/record_today.js'))
check('sitemap declared', any(l.lower().startswith('sitemap: https://rix-picks.com/sitemap.xml') for l in lines))

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
