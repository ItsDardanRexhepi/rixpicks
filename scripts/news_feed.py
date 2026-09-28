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

# swamp 9/27 1:02 PT (main escalation): generic-sport RSS lanes cross-contaminate league
# buckets (Euro men's soccer in NWSL/MLS, men's tennis in WTA). League-unique lanes only;
# MLS/NWSL/ATP/WTA ride the per-league ESPN API lane (fail-closed beats misleading).
ESPN_RSS = {'NFL':'nfl','NBA':'nba','MLB':'mlb','NHL':'nhl','CFB':'ncf','NCAAB':'ncb',
            'WNBA':'wnba','PGA':'golf',
            'NASCAR':'racing','UFC':'mma','Boxing':'boxing'}
CBS_RSS = {'NFL':'nfl','NBA':'nba','MLB':'mlb','NHL':'nhl','CFB':'college-football',
           'NCAAB':'college-basketball','WNBA':'wnba','PGA':'golf',
           'UFC':'mma','Boxing':'boxing'}
YAHOO_RSS = {'NFL':'nfl','NBA':'nba','MLB':'mlb','NHL':'nhl','CFB':'college-football',
             'NCAAB':'college-basketball','WNBA':'wnba',
             'PGA':'golf','NASCAR':'nascar','UFC':'mma',
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
            imgs = a.get('images') or []
            out.append({'headline': a.get('headline', ''),
                        'link': ((a.get('links') or {}).get('web') or {}).get('href', ''),
                        'published': a.get('published', ''), 'source': 'ESPN',
                        'image': (imgs[0].get('url', '') if imgs else ''),
                        'blurb': a.get('description', '')})
    except Exception as e:
        print('  lane espn-api %s: %s' % (path, e), file=sys.stderr)
    return out

ATOM = '{http://www.w3.org/2005/Atom}'

MEDIA = '{http://search.yahoo.com/mrss/}'

def item_image(it, atom=False):
    """Best-effort article image from RSS/Atom: media:content, media:thumbnail, or
    image enclosure. Fail-closed: '' when absent - the carousel hides the art slot."""
    for tag in (MEDIA + 'content', MEDIA + 'thumbnail'):
        for m in it.findall(tag):
            u = m.get('url', '')
            if u:
                return u
    for enc in it.findall('enclosure'):
        if (enc.get('type') or '').startswith('image') and enc.get('url'):
            return enc.get('url')
    return ''

def item_blurb(it, atom=False):
    d = (it.findtext(ATOM + 'summary') if atom else it.findtext('description')) or ''
    d = re.sub(r'<[^>]+>', ' ', d)
    return re.sub(r'\s+', ' ', d).strip()[:280]

def rss(url, source):
    out = []
    try:
        root = ET.fromstring(get(url))
        for it in root.iter('item'):
            out.append({'headline': (it.findtext('title') or '').strip(),
                        'link': (it.findtext('link') or '').strip(),
                        'published': iso(it.findtext('pubDate') or ''), 'source': source,
                        'image': item_image(it), 'blurb': item_blurb(it)})
        for en in root.iter(ATOM + 'entry'):
            lk = ''
            for l in en.findall(ATOM + 'link'):
                if l.get('href'): lk = l.get('href'); break
            p = en.findtext(ATOM + 'published') or en.findtext(ATOM + 'updated') or ''
            out.append({'headline': (en.findtext(ATOM + 'title') or '').strip(),
                        'link': lk, 'published': p, 'source': source,
                        'image': item_image(en, atom=True), 'blurb': item_blurb(en, atom=True)})
    except Exception as e:
        print('  lane rss %s: %s' % (url, e), file=sys.stderr)
    return out

# Cross-sport guard (swamp 9/27 1:08): outlet league feeds carry roundup stories from other
# sports (NFL injury roundup in the UFC bucket, MLB/WNBA roundup in PGA). Two rules per bucket:
# (1) a headline naming another league's strong markers is rejected from this bucket;
# (2) niche buckets (golf/tennis/mma/boxing/nascar/soccer) must name a league keyword at all.
FOREIGN = {
 'NFL': [],  # nfl is the contaminant, never the contaminated marker set
}
LEAGUE_KEYWORDS = {
 'NFL': ['nfl','football','super bowl','quarterback','touchdown'],
 'NBA': ['nba','basketball'],
 'MLB': ['mlb','baseball','world series','pitcher','home run'],
 'NHL': ['nhl','hockey','stanley cup'],
 'CFB': ['college football','ncaa football','cfb','quarterback','touchdown','heisman'],
 'NCAAB': ['college basketball','ncaa','march madness','basketball'],
 'WNBA': ['wnba','basketball'],
 'MLS': ['mls','soccer','major league soccer'],
 'NWSL': ['nwsl','soccer'],
 'PGA': ['golf','pga','masters','ryder','open championship','tour championship','birdie','eagle'],
 'ATP': ['tennis','atp','grand slam','wimbledon','us open','australian open','french open'],
 'WTA': ['tennis','wta','grand slam','wimbledon','us open','australian open','french open'],
 'NASCAR': ['nascar','racing','daytona','cup series'],
 'UFC': ['ufc'],  # swamp 1:14: promotion, not the sport - generic MMA/boxing falls out
 'Boxing': ['boxing','heavyweight','title bout'],
}
STRONG_MARKERS = {  # sport-owning tokens: presence in a foreign bucket => reject
 'NFL': ['nfl','super bowl','quarterback','touchdown'],
 'NBA': ['nba'],
 'MLB': ['mlb','world series','home run'],
 'NHL': ['nhl','stanley cup'],
 'WNBA': ['wnba'],
}
SPORT_OF = {'NFL':'NFL','CFB':'NFL','NBA':'NBA','NCAAB':'NBA','WNBA':'WNBA','MLB':'MLB','NHL':'NHL'}

def relevant(key, headline):
    h = ' ' + (headline or '').lower() + ' '
    def has(tok): return tok in h
    my_sport = SPORT_OF.get(key)
    for sport, marks in STRONG_MARKERS.items():
        if sport == my_sport: continue
        if any(has(m) for m in marks):
            return False
    kws = LEAGUE_KEYWORDS.get(key)
    if key in ('MLS','NWSL','PGA','ATP','WTA','NASCAR','UFC','Boxing'):
        if not kws: return False
        # roundup guard: the league keyword must lead, not trail - a multi-sport roundup
        # that opens on another sport and tags this league at the end is rejected.
        cut = max(20, int(len(h) * 0.6))
        return any(k in h[:cut] for k in kws)
    return True

def ts_of(a):
    try:
        return datetime.fromisoformat((a.get('published') or '').replace('Z', '+00:00')).timestamp()
    except Exception:
        return 0


IMG_CACHE = 'slates/news_images.json'
OG_RE = re.compile(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)["\']', re.I)
OG_RE2 = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\']', re.I)

def enrich_images(latest):
    """og:image pass for articles whose lane carried no art (carousel contract 10:51:
    per-article image URLs). Bounded: cache by link so a 5-min cron never re-fetches,
    max 12 fresh fetches per run, 6s timeout. Fail-closed: '' hides the art slot."""
    try:
        cache = json.load(open(IMG_CACHE))
    except Exception:
        cache = {}
    fresh = 0
    for a in latest:
        if a.get('image'):
            continue
        link = a.get('link', '')
        if not link:
            continue
        if link in cache:
            a['image'] = cache[link]
            continue
        if fresh >= 12:
            continue
        fresh += 1
        img = ''
        try:
            html = get(link, timeout=6).decode('utf-8', 'ignore')[:200000]
            m = OG_RE.search(html) or OG_RE2.search(html)
            if m and m.group(1).startswith('http'):
                img = m.group(1)
        except Exception as e:
            print('  og:image %s: %s' % (link[:60], e), file=sys.stderr)
        cache[link] = img
        a['image'] = img
    if len(cache) > 300:
        cache = dict(list(cache.items())[-300:])
    try:
        json.dump(cache, open(IMG_CACHE, 'w'), indent=0)
    except Exception as e:
        print('  img cache write: %s' % e, file=sys.stderr)


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
            if not relevant(key, a['headline']): continue
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
    latest = latest[:40]
    enrich_images(latest)
    out = {'generated_at': datetime.now(timezone.utc).isoformat(),
           'leagues': leagues, 'latest': latest}
    with open('slates/news.json', 'w') as f:
        json.dump(out, f, indent=1)
    counts = {k: len(v) for k, v in leagues.items()}
    print('news.json: %d league buckets, %d latest, generated_at %s' % (len(leagues), len(out['latest']), out['generated_at']))
    print(json.dumps(counts))

if __name__ == '__main__':
    main()
