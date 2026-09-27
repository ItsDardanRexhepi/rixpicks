#!/usr/bin/env python3
"""news_feed.py - multi-source sports news aggregator -> slates/news.json (9/27 Dardan:
"instant and live and tapped into all live sports news sources").
Lanes per league: ESPN site API (all registry leagues with an espn path) + ESPN RSS +
CBS RSS (outlet-distinct second lane). Every lane fail-closed; a dead lane never blocks
the file. Dedup by normalized headline; blank beats wrong (empty list, no fabricated
items). Client reads this one file instead of fanning out per-league."""
import json, re, sys, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) RixPicks/1.0'}

ESPN_RSS = {'NFL':'nfl','NBA':'nba','MLB':'mlb','NHL':'nhl','CFB':'ncf','NCAAB':'ncb',
            'WNBA':'wnba','MLS':'soccer','PGA':'golf','ATP':'tennis','WTA':'tennis',
            'NASCAR':'racing','UFC':'mma','NWSL':'soccer','Boxing':'boxing'}
CBS_RSS = {'NFL':'nfl','NBA':'nba','MLB':'mlb','NHL':'nhl','CFB':'college-football',
           'NCAAB':'college-basketball','WNBA':'wnba','MLS':'soccer','PGA':'golf',
           'ATP':'tennis','WTA':'tennis','UFC':'mma','Boxing':'boxing'}
YAHOO_RSS = {'NFL':'nfl','NBA':'nba','MLB':'mlb','NHL':'nhl','CFB':'college-football',
             'NCAAB':'college-basketball','WNBA':'wnba','MLS':'soccer','NWSL':'soccer',
             'PGA':'golf','ATP':'tennis','WTA':'tennis','NASCAR':'nascar','UFC':'mma',
             'Boxing':'boxing'}

def get(url, timeout=12):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def norm(h):
    return re.sub(r'[^a-z0-9]+', ' ', (h or '').lower()).strip()

def iso(p):
    if not p: return ''
    try:
        return parsedate_to_datetime(p).astimezone(timezone.utc).isoformat()
    except Exception:
        return ''

def espn_api(path):
    out = []
    try:
        j = json.loads(get('https://site.api.espn.com/apis/site/v2/sports/%s/news?limit=10' % path))
        for a in j.get('articles', []):
            out.append({'headline': a.get('headline', ''),
                        'link': ((a.get('links') or {}).get('web') or {}).get('href', ''),
                        'published': a.get('published', ''), 'source': 'ESPN'})
    except Exception as e:
        print('  lane espn-api %s: %s' % (path, e), file=sys.stderr)
    return out

ATOM = '{http://www.w3.org/2005/Atom}'

def rss(url, source):
    out = []
    try:
        root = ET.fromstring(get(url))
        for it in root.iter('item'):
            out.append({'headline': (it.findtext('title') or '').strip(),
                        'link': (it.findtext('link') or '').strip(),
                        'published': iso(it.findtext('pubDate') or ''), 'source': source})
        for en in root.iter(ATOM + 'entry'):
            lk = ''
            for l in en.findall(ATOM + 'link'):
                if l.get('href'): lk = l.get('href'); break
            p = en.findtext(ATOM + 'published') or en.findtext(ATOM + 'updated') or ''
            out.append({'headline': (en.findtext(ATOM + 'title') or '').strip(),
                        'link': lk, 'published': p, 'source': source})
    except Exception as e:
        print('  lane rss %s: %s' % (url, e), file=sys.stderr)
    return out

def ts_of(a):
    try:
        return datetime.fromisoformat((a.get('published') or '').replace('Z', '+00:00')).timestamp()
    except Exception:
        return 0

def main():
    cfg = json.load(open('config_leagues.json'))['leagues']
    leagues, latest = {}, []
    for key, v in cfg.items():
        path = v.get('espn')
        jkey = path or key.lower()
        items = []
        if path: items += espn_api(path)
        if key in ESPN_RSS: items += rss('https://www.espn.com/espn/rss/%s/news' % ESPN_RSS[key], 'ESPN')
        if key in CBS_RSS: items += rss('https://www.cbssports.com/rss/headlines/%s/' % CBS_RSS[key], 'CBS')
        if key in YAHOO_RSS: items += rss('https://sports.yahoo.com/%s/rss.xml' % YAHOO_RSS[key], 'YAHOO')
        seen, ded = set(), []
        for a in sorted(items, key=ts_of, reverse=True):
            n = norm(a['headline'])
            if not n or n in seen: continue
            seen.add(n)
            a['league'] = key
            ded.append(a)
        # interleave sources so one fast outlet can't crowd the rest out of a bucket
        by_src = {}
        for a in ded: by_src.setdefault(a['source'], []).append(a)
        mixed = []
        i = 0
        while len(mixed) < 10 and by_src:
            for src in list(by_src):
                lst = by_src[src]
                if i < len(lst): mixed.append(lst[i])
                else: del by_src[src]
            i += 1
        leagues[jkey] = mixed[:10]
        latest += mixed[:6]
    latest.sort(key=ts_of, reverse=True)
    out = {'generated_at': datetime.now(timezone.utc).isoformat(),
           'leagues': leagues, 'latest': latest[:40]}
    with open('slates/news.json', 'w') as f:
        json.dump(out, f, indent=1)
    counts = {k: len(v) for k, v in leagues.items()}
    print('news.json: %d league buckets, %d latest, generated_at %s' % (len(leagues), len(out['latest']), out['generated_at']))
    print(json.dumps(counts))

if __name__ == '__main__':
    main()
