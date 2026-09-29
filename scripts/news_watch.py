"""News wire watch: ESPN per-league news + Google News RSS, diffed against seen state.
State: /home/sandbox/rps_tmp/kb/news_seen.json {id: first_seen_iso}
Usage: python3 news_watch.py --report   (first run seeds baseline silently)
"""
import json, os, re, sys, time, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# all-13 standard (lane 6, 2026-09-29): every league bucket of the owner's 13 with a live ESPN
# news endpoint (each verified 2026-09-29: returns articles). NASCAR's racing/nascar-premier
# endpoint resolves but carries zero articles - left out rather than wired dead; Boxing has no
# ESPN API surface at all (config_leagues.json espn:null).
ESPN_LEAGUES = ['football/nfl','baseball/mlb','basketball/nba','basketball/wnba','hockey/nhl',
                'football/college-football','basketball/mens-college-basketball',
                'soccer/usa.1','soccer/usa.nwsl','golf/pga','tennis/atp','tennis/wta','mma/ufc']
GN_QUERIES = ['NFL injury OR trade OR signing','NBA injury OR trade','MLB injury OR trade',
              'NHL injury OR trade','College football injury OR suspension',
              'MLS injury OR transfer','NWSL injury OR trade']
STATE = '/home/sandbox/rps_tmp/kb/news_seen.json'
KEEP = 4000

def fetch(url, as_json=True):
    req = urllib.request.Request(url, headers={'User-Agent':'python-urllib/3'})
    raw = urllib.request.urlopen(req, timeout=20).read()
    return json.loads(raw) if as_json else raw

def espn_items():
    out = []
    for lg in ESPN_LEAGUES:
        try:
            d = fetch(f'https://site.api.espn.com/apis/site/v2/sports/{lg}/news?limit=25')
            for a in d.get('articles', []):
                aid = str(a.get('id') or '')
                if not aid: continue
                out.append({'id': f'espn-{aid}', 'source': f'ESPN/{lg}',
                            'title': a.get('headline',''), 'published': a.get('published',''),
                            'link': (a.get('links',{}).get('web',{}).get('href') or '')})
        except Exception as ex:
            out.append({'id': f'err-{lg}', 'error': str(ex)})
        time.sleep(0.3)
    return out

def gnews_items():
    out = []
    for q in GN_QUERIES:
        try:
            url = 'https://news.google.com/rss/search?q=' + urllib.parse.quote(q) + '&hl=en-US&gl=US&ceid=US:en'
            root = ET.fromstring(fetch(url, as_json=False))
            for it in root.iter('item'):
                link = (it.findtext('link') or '').strip()
                if not link: continue
                src = it.find('source')
                out.append({'id': 'gn-' + re.sub(r'\W','',link)[-64:], 'source': src.text if src is not None else 'GNews',
                            'title': (it.findtext('title') or '').strip(), 'published': it.findtext('pubDate') or '',
                            'link': link})
        except Exception as ex:
            out.append({'id': f'err-gn-{q[:12]}', 'error': str(ex)})
        time.sleep(0.3)
    return out

def main():
    import urllib.parse
    seen = {}
    if os.path.exists(STATE):
        try: seen = json.load(open(STATE))
        except Exception: seen = {}
    items = espn_items() + gnews_items()
    new, errors = [], []
    now = datetime.now(timezone.utc).isoformat()
    for it in items:
        if 'error' in it:
            errors.append(it); continue
        if it['id'] not in seen:
            seen[it['id']] = now
            new.append(it)
    # prune
    if len(seen) > KEEP:
        seen = dict(sorted(seen.items(), key=lambda kv: kv[1])[-KEEP:])
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(seen, open(STATE,'w'))
    if '--report' in sys.argv:
        for e in errors: print(f"NEWS SOURCE ERR {e['id']}: {e['error']}")
        if not seen or (len(new) == len(items) - len(errors) and new):
            print(f"BASELINE seeded: {len(seen)} items")
        for it in new[:30]:
            print(f"NEW [{it['source']}] {it['title']} | {it['published']} | {it['link']}")
        if not new and not errors:
            print("no new items")

if __name__ == '__main__':
    main()
