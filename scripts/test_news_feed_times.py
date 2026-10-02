#!/usr/bin/env python3
"""News producer time + blurb fixture (Oct 1 sweep, LS-06 / OS-13) for scripts/news_feed.py.

ESPN RSS stamps many items with the feed's refresh time, labelled EST while Eastern is on EDT:
stories landed 30-60 min after generated_at and the page showed them as '1m ago NEW', sorted
first. Some ESPN RSS items carry the literal description 'null', which rendered as a blurb.
Rules under test (main() end to end, network mocked, real clock):
- an RSS item whose ESPN story id is also in the ESPN API lane carries the API publish time
- an item whose time is still more than 5 min ahead of the run is blank (unknown), never future
- a 'null' blurb is no blurb; real blurbs and honest past times are untouched
"""
import importlib.util, json, os, sys, tempfile
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('news_feed', os.path.join(HERE, 'news_feed.py'))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

NOW = datetime.now(timezone.utc)
Z = lambda d: d.strftime('%Y-%m-%dT%H:%M:%SZ')
def espn_est(real_utc):
    """ESPN RSS shape: Eastern wall clock (EDT) written with an 'EST' label."""
    return (real_utc - timedelta(hours=4)).strftime('%a, %d %b %Y %H:%M:%S EST')

REFRESH = NOW - timedelta(minutes=25)           # feed refresh 25 min ago -> parses ~35 min ahead
API_TIME = NOW - timedelta(minutes=50)          # the story's real publish time (API lane)
OLD = NOW - timedelta(hours=5)
API = {'articles': [
    {'headline': "Rangers' Igor Shesterkin becomes 18th NHL goalie to score", 'published': Z(API_TIME),
     'description': 'Igor Shesterkin of the Rangers became the 18th goalie to score.',
     'links': {'web': {'href': 'https://www.espn.com/nhl/story/_/id/50081336/rangers-igor-shesterkin-becomes-18th-nhl-goal'}}},
    {'headline': 'Guenther has 2 power-play goals in the Mammoth win', 'published': Z(NOW - timedelta(minutes=20)),
     'description': 'Dylan Guenther scored two power-play goals.',
     'links': {'web': {'href': 'http://www.espn.com/nhl/recap?gameId=401891828'}}},
]}
RSS = ('<?xml version="1.0"?><rss><channel>'
       '<item><title><![CDATA[Goalie Shesterkin notches empty-netter in Rangers victory]]></title>'
       '<link><![CDATA[https://www.espn.com/nhl/story/_/id/50081336/rangers-igor-shesterkin-becomes-18th]]></link>'
       '<pubDate>%s</pubDate><description><![CDATA[null]]></description></item>'
       '<item><title><![CDATA[Bettman eyes no-trade clauses in NHL deals]]></title>'
       '<link><![CDATA[https://www.espn.com/nhl/story/_/id/50079472/nhl-gary-bettman-monitoring]]></link>'
       '<pubDate>%s</pubDate><description><![CDATA[Bettman is watching how the clauses are used.]]></description></item>'
       '<item><title><![CDATA[Kraken recap from the other game]]></title>'
       '<link><![CDATA[http://www.espn.com/nhl/recap?gameId=401891777]]></link>'
       '<pubDate>%s</pubDate><description><![CDATA[Vince Dunn had a goal and two assists.]]></description></item>'
       '</channel></rss>') % (espn_est(REFRESH), espn_est(REFRESH), espn_est(OLD))

def fake_get(url, timeout=12):
    if 'site.api.espn.com' in url and '/news' in url:
        return json.dumps(API).encode()
    if 'espn.com/espn/rss/nhl/news' in url:
        return RSS.encode()
    raise OSError('lane offline in fixture: ' + url)

checks = []
def check(name, ok):
    checks.append((name, bool(ok)))

tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, 'slates'))
json.dump({'leagues': {'NHL': {'espn': 'hockey/nhl'}}}, open(os.path.join(tmp, 'config_leagues.json'), 'w'))
M.get = fake_get
M.enrich_images = lambda latest: None
M.validate_images = lambda arts: None
cwd = os.getcwd()
os.chdir(tmp)
try:
    M.main()
    out = json.load(open('slates/news.json'))
finally:
    os.chdir(cwd)

gen = datetime.fromisoformat(out['generated_at'].replace('Z', '+00:00')).timestamp()
arts = out['latest'] + [a for v in out['leagues'].values() for a in v]
by = lambda word: [a for a in arts if word in a['headline']]
ts = lambda a: M.ts_of(a)
check('no item is dated more than 5 min after generated_at', all(ts(a) <= gen + 300 for a in arts))
she = by('Goalie Shesterkin')
check('RSS copy of an API story carries the API publish time', she and all(a['published'] == Z(API_TIME) for a in she))
bet = by('Bettman')
check('RSS-only story with a future stamp has no time (unknown, not new)', bet and all(a['published'] == '' for a in bet))
check("'null' RSS blurb is no blurb", she and all(a.get('blurb') == '' for a in she))
check('real blurbs are kept', any(a.get('blurb') == 'Bettman is watching how the clauses are used.' for a in arts))
krk = by('Kraken recap')
check('honest past RSS time untouched (recap links do not borrow another game time)',
      krk and all(abs(ts(a) - (OLD.timestamp() + 3600)) < 2 for a in krk))
gue = by('Guenther')
check('API lane time untouched', gue and all(a['published'] == Z(NOW - timedelta(minutes=20)) for a in gue))
check('real-time stories sort ahead of the undated one in latest',
      [a['headline'].split()[0] for a in out['latest']][-1] == 'Bettman')
sk = getattr(M, 'story_key', None)
check('story key: ESPN id joins slug variants', sk and sk('https://www.espn.com/nhl/story/_/id/5/a-b') == sk('https://www.espn.com/nhl/story/_/id/5/a-b-c-d'))
check('story key: recap links keep their gameId', sk and sk('http://www.espn.com/nhl/recap?gameId=1') != sk('http://www.espn.com/nhl/recap?gameId=2'))

for name, ok in checks:
    print(('PASS ' if ok else 'FAIL ') + name)
failed = [n for n, ok in checks if not ok]
if failed:
    print('\n%d FAIL' % len(failed)); sys.exit(1)
print('\nall %d PASS' % len(checks))
