#!/usr/bin/env python3
"""polymarket_feed.py - fill manifest picks' polymarket slots from gamma-api.

Contract (consumed by build_gh_page.py chips()):
  p['polymarket'] = {'url': 'https://polymarket.com/event/<slug>', 'cents': <pick-side int>}  # cents = fallback snapshot
  p['polycents']  = <pick-side int>  # legacy fallback key the page also reads

Slug: <lg>-<awayabbr>-<homeabbr>-<YYYY-MM-DD> (ET game date). Every slug is gamma-verified:
event must exist AND its title must contain both teams' last names. Fail-closed: no verified
event -> slot stays null, no chip (never a guessed URL on the page).
Moneyline market = market whose sportsMarketType=='moneyline' (fallback: question has 'vs.'
and outcomes match team names). Pick side matched against outcome names.
"""
import json, sys, urllib.request, re, datetime
from zoneinfo import ZoneInfo

GAMMA = "https://gamma-api.polymarket.com/events?slug="

# full team name -> polymarket slug abbreviation (verified live Sep 27, 2026)
ABBR = {
 # NFL
 "new york jets":"nyj","detroit lions":"det","cincinnati bengals":"cin","pittsburgh steelers":"pit",
 "buffalo bills":"buf","miami dolphins":"mia","new england patriots":"ne","baltimore ravens":"bal",
 "cleveland browns":"cle","houston texans":"hou","indianapolis colts":"ind","jacksonville jaguars":"jax",
 "tennessee titans":"ten","denver broncos":"den","kansas city chiefs":"kc","las vegas raiders":"lv",
 "los angeles chargers":"lac","dallas cowboys":"dal","new york giants":"nyg","philadelphia eagles":"phi",
 "washington commanders":"wsh","chicago bears":"chi","green bay packers":"gb","minnesota vikings":"min",
 "atlanta falcons":"atl","carolina panthers":"car","new orleans saints":"no","tampa bay buccaneers":"tb",
 "arizona cardinals":"ari","los angeles rams":"lar","san francisco 49ers":"sf","seattle seahawks":"sea",
 # WNBA
 "new york liberty":"nyl","minnesota lynx":"min","washington mystics":"wsh","atlanta dream":"atl",
 "las vegas aces":"lv","phoenix mercury":"phx","seattle storm":"sea","connecticut sun":"conn",
 "indiana fever":"ind","chicago sky":"chi","dallas wings":"dal","los angeles sparks":"la",
 "golden state valkyries":"gs",
 # MLB
 "tampa bay rays":"tb","philadelphia phillies":"phi","los angeles dodgers":"lad","san francisco giants":"sf",
 "st. louis cardinals":"stl","milwaukee brewers":"mil","new york yankees":"nyy","new york mets":"nym",
 "boston red sox":"bos","baltimore orioles":"bal","toronto blue jays":"tor","cleveland guardians":"cle",
 "detroit tigers":"det","kansas city royals":"kc","minnesota twins":"min","chicago white sox":"cws",
 "houston astros":"hou","los angeles angels":"laa","athletics":"ath","seattle mariners":"sea",
 "texas rangers":"tex","atlanta braves":"atl","miami marlins":"mia","washington nationals":"wsh",
 "chicago cubs":"chc","cincinnati reds":"cin","pittsburgh pirates":"pit","arizona diamondbacks":"ari",
 "colorado rockies":"col","san diego padres":"sd",
}
LEAGUE_SLUG = {"football/nfl":"nfl","basketball/wnba":"wnba","baseball/mlb":"mlb",
               "football/college-football":"cfb","basketball/nba":"nba","hockey/nhl":"nhl"}

def last_name(full):
    return full.split()[-1].lower().rstrip('.')

def gamma(url):
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
    return json.load(urllib.request.urlopen(req, timeout=12))

def moneyline_market(ev, away_last, home_last):
    mkts = ev.get('markets') or []
    for m in mkts:
        if (m.get('sportsMarketType') or '').lower() == 'moneyline':
            return m
    for m in mkts:  # fallback: question lists both teams
        qn = (m.get('question') or '').lower()
        if away_last in qn and home_last in qn:
            oc = [o.lower() for o in json.loads(m.get('outcomes') or '[]')]
            if away_last in oc and home_last in oc:
                return m
    return None

# --- polymarket.us resolution (owner ruling Sep 27 8:25 AM: chips keep .us, never .com) ---
# .us event pages are client-rendered shells that soft-404 (HTTP 200 + generic shell on bogus slugs),
# so an event URL alone proves NOTHING. Verification = the .us league hub (server-rendered):
# the pick's matchup must appear in the hub's embedded event list for TODAY, matched by city names.
# Fail-closed: no hub-verified .us URL -> polymarket keys dropped from the pick (chip drops).
US_HUB = "https://polymarket.us/sports/"
US_SLUG_LG = {"football/nfl":"nfl","basketball/wnba":"wnba","baseball/mlb":"mlb",
              "football/college-football":"cfb","basketball/nba":"nba","hockey/nhl":"nhl"}

def us_hub_events(lg):
    """slug -> {'title', 'prices':[{label, prob}]} from the .us league hub (server-rendered RSC JSON).
    The hub is the ONLY curl-verifiable .us surface: event pages are client shells that soft-404."""
    req = urllib.request.Request(US_HUB+lg, headers={'User-Agent':'Mozilla/5.0'})
    html = urllib.request.urlopen(req, timeout=15).read().decode('utf-8','replace')
    out = {}
    for m in re.finditer(r'\\"title\\":\\"([^"\\]+)\\".*?\\"href\\":\\"/sports/'+re.escape(lg)+r'/('+re.escape(lg)+r'-[a-z0-9-]+)\\"(.*?)(?=\\"cell\\"|$)', html, re.S):
        title, slug, rest = m.group(1), m.group(2), m.group(3)
        prices = re.findall(r'\\"label\\":\\"([^"\\]+)\\".*?\\"probability\\":([0-9.]+)', rest, re.S)
        out[slug] = {'title': title, 'prices': [{'label': l, 'prob': float(p)} for l, p in prices[:2]]}
    return out

def city(full):  # team full name -> city part ("New York Jets" -> "new york", "St. Louis Cardinals" -> "st. louis")
    return ' '.join(full.split()[:-1]).lower()

def resolve_us(pick, hub):
    """-> (us_url, pick_side_cents) or (None, None). Venue-correct .us quote from the hub cell."""
    g = pick.get('game') or {}
    away, home = g.get('away',''), g.get('home','')
    a_toks = {away.split()[-1].lower(), city(away)}
    h_toks = {home.split()[-1].lower(), city(home)}
    want = home if pick.get('side')=='home' else away
    w_toks = {want.split()[-1].lower(), city(want)}
    for slug, ev in hub.items():
        if not slug.endswith('-'+pick['_etdate']): continue
        hay = (ev['title']+' '+slug.replace('-',' ')).lower()
        if not (any(t in hay for t in a_toks if t) and any(t in hay for t in h_toks if t)):
            continue
        url = "https://polymarket.us/sports/"+slug.split('-',1)[0]+"/"+slug
        cents = None
        for pr in ev['prices']:
            lbl = pr['label'].lower()
            if any(t and t in lbl for t in w_toks):
                cents = round(pr['prob']*100); break
        return url, cents
    return None, None

def feed(manifest_path, write=True):
    man = json.load(open(manifest_path))
    n_ok = 0
    hubs = {}
    for p in man['picks']:
        ulg = US_SLUG_LG.get(p.get('espn_league',''))
        if ulg and ulg not in hubs:
            try: hubs[ulg] = us_hub_events(ulg)
            except Exception as ex:
                print(f"HUB ERR {ulg}: {ex}", file=sys.stderr); hubs[ulg] = {}
        g = p.get('game') or {}
        away, home, commence = g.get('away',''), g.get('home',''), g.get('commence','')
        lg = LEAGUE_SLUG.get(p.get('espn_league',''))
        a_abbr, h_abbr = ABBR.get(away.lower()), ABBR.get(home.lower())
        if not (lg and a_abbr and h_abbr and commence):
            print(f"SKIP {p.get('name')}: missing lg/abbr/date", file=sys.stderr); continue
        d = datetime.datetime.fromisoformat(commence.replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York'))
        p['_etdate'] = f"{d:%Y-%m-%d}"
        slug = f"{lg}-{a_abbr}-{h_abbr}-{d:%Y-%m-%d}"
        try:
            evs = gamma(GAMMA + slug)
        except Exception as ex:
            print(f"ERR {p.get('name')}: {ex}", file=sys.stderr); p.pop('_etdate',None); continue
        if not evs:
            print(f"NOEVENT {p.get('name')}: {slug}", file=sys.stderr); p.pop('_etdate',None); continue
        ev = evs[0]
        title = (ev.get('title') or '').lower()
        if not (last_name(away) in title and last_name(home) in title):
            print(f"MISMATCH {p.get('name')}: {slug} -> {ev.get('title')}", file=sys.stderr); p.pop('_etdate',None); continue
        m = moneyline_market(ev, last_name(away), last_name(home))
        if not m:
            print(f"NOML {p.get('name')}: {slug}", file=sys.stderr); p.pop('_etdate',None); continue
        outcomes = json.loads(m.get('outcomes') or '[]')
        prices = json.loads(m.get('outcomePrices') or '[]')
        cands=[(p.get('kalshi') or {}).get('team'), re.sub(r'\s+(ML|[+-]?[\d.]+.*)$','',p.get('name','')),
               (home if p.get('side')=='home' else away)]
        idx=None
        for w in [c for c in cands if c]:
            idx=next((i for i,o in enumerate(outcomes) if last_name(w) in o.lower() or last_name(o) in last_name(w)), None)
            if idx is not None: break
        if idx is None or idx >= len(prices):
            print(f"NOSIDE {p.get('name')}: outcomes={outcomes}", file=sys.stderr); p.pop('_etdate',None); continue
        cents = round(float(prices[idx]) * 100)
        url = f"https://polymarket.com/event/{slug}"
        us_url, us_cents = resolve_us(p, hubs.get(ulg) or {})
        if write:
            if us_url and us_cents is not None:
                p['polymarket'] = {'url': url, 'cents': cents}
                p['polymarket_us'] = {'url': us_url, 'cents': us_cents, 'verified': True}
                p['polycents'] = cents
            else:
                # chip requires hub-verified .us URL AND pick-side .us quote (Sep 27 .us ruling + price fix);
                # a chip never shows a .com price on a .us link - fail-closed, chip drops
                p['polymarket'] = None; p.pop('polymarket_us', None); p.pop('polycents', None)
                print(f"US-UNVERIFIED {p.get('name')}: url={bool(us_url)} cents={us_cents} - chip dropped", file=sys.stderr)
        p.pop('_etdate', None)
        n_ok += 1
        print(f"OK {p.get('name')}: {url} pick-side {cents}c gamma | .us {us_cents}c")
    if write:
        json.dump(man, open(manifest_path,'w'), indent=1)
    print(f"fed {n_ok}/{len(man['picks'])} picks", file=sys.stderr)

if __name__ == '__main__':
    args=[a for a in sys.argv[1:] if not a.startswith('--')]; feed(args[0] if args else 'manifest.json', write='--check' not in sys.argv)
