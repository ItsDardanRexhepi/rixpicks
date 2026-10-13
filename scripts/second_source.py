# The cross-company SECOND SOURCE for a final (J-115): the readers that confirm ESPN core's final from another
# company - CBS scoreboards, theScore (WNBA), MLB statsapi, the repo's nfl_scores.json and the odds-api scores - plus
# the ESPN site fallback, which is the same company and labelled so. One definition, used in two places:
#   - scripts/finals_watch.py (the grading host) runs this file in its own namespace, so the readers use that
#     module's _get, _get_text and _secret, and whatever a fixture puts there;
#   - scripts/record_final.py (the GitHub Actions record write) imports it, to read a second source itself before it
#     writes anything (hardening H-04) - it never takes the request's word for one.
# Nothing here reads the private unit size: grading money stays in finals_watch, on the grading host.
import json, os, re, subprocess, sys, urllib.request
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

if 'core' not in sys.modules:  # imported standalone: core/ from this checkout (an importer that has one keeps it)
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import budget

ET = ZoneInfo('America/New_York')
PT = ZoneInfo('America/Los_Angeles')

def _secret(name):
    """A secret by name: the environment variable, else the macOS login keychain item whose service
    is that name (security find-generic-password -s <name> -w). '' when neither has it. The value
    is returned to the caller only - never printed or logged."""
    v = os.environ.get(name)
    if v:
        return v.strip()
    try:
        r = subprocess.run(['security', 'find-generic-password', '-s', name, '-w'],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ''
    return r.stdout.strip() if r.returncode == 0 else ''

def _get(url, timeout=20, ua='Mozilla/5.0'):
    req = urllib.request.Request(url, headers={'User-Agent': ua})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

CBS_SLUG = {'football/college-football': 'college-football', 'football/nfl': 'nfl',
            'basketball/nba': 'nba', 'basketball/mens-college-basketball': 'college-basketball',
            'basketball/wnba': 'wnba', 'baseball/mlb': 'mlb', 'hockey/nhl': 'nhl', 'soccer/usa.1': 'mls'}

def _norm(s):
    return re.sub(r'[^a-z]', '', (s or '').lower())

def _get_text(url, timeout=10, ua='Mozilla/5.0'):
    req = urllib.request.Request(url, headers={'User-Agent': ua})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'ignore')

def _local_dates(commence):
    """The calendar dates a US scoreboard can file a game under: its Eastern date, then its Pacific
    date when that differs (a game starting after 9 PM PT). Never the UTC date - a 7:30 PM ET start is
    already the next day in UTC, where the scoreboard holds a different game."""
    out = []
    for tz in (ET, PT):
        d = commence.astimezone(tz).date()
        if d not in out:
            out.append(d)
    return out

def _nfl_week(pick):
    """(season, CBS season-type path, week) of an NFL event from ESPN core's own week link, or None.
    CBS keys NFL scoreboards by week - a date page shows the current week, not that date."""
    try:
        ev = _get(f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{pick['game']['eid']}")
        m = re.search(r'/seasons/(\d{4})/types/(\d+)/weeks/(\d+)', str((ev.get('week') or {}).get('$ref') or ''))
    except Exception:
        return None
    if not m or m.group(2) != '2':
        return None  # only the regular season's CBS week pages are verified here
    return m.group(1), 'regular', m.group(3)

_CBS_CARD = re.compile(r'<div id="game-\d+"[^>]*?\sdata-abbrev="([A-Z]+)_(\d{8})_([A-Z0-9]+)@([A-Z0-9]+)"'
                       r'[^>]*?\sclass="single-score-card\b([^"]*)"')

def _cbs_cards(html, slug):
    """Every final game card on a CBS scoreboard page: (card date, ordered rows). Strict parse of one
    card at a time: the status must read final, there must be exactly two team rows, and the rows'
    team links must be the card's own AWAY@HOME in that order. Each row is
    (CBS team url slug, total score)."""
    out = []
    starts = list(_CBS_CARD.finditer(html))
    for i, m in enumerate(starts):
        seg = html[m.start():starts[i + 1].start() if i + 1 < len(starts) else len(html)]
        cut = seg.find('class="bottom-bar"')
        seg = seg[:cut] if cut > 0 else seg[:20000]
        st = re.search(r'<div class="game-status ([a-z -]+)"><div>([^<]*)</div>', seg)
        if 'postgame' not in m.group(5).split() or not st or 'postgame' not in st.group(1).split() \
                or not st.group(2).strip().lower().startswith('final'):
            continue
        rows = re.findall(r'<a href="/' + re.escape(slug) + r'/teams/([A-Z0-9]+)/([a-z0-9-]+)/" class="team-name-link">[^<]*</a>'
                          r'.*?<td class="total">(\d{1,3})</td>', seg, re.S)
        if len(rows) != 2 or (rows[0][0], rows[1][0]) != (m.group(3), m.group(4)):
            continue
        out.append((m.group(2), [(r[1], int(r[2])) for r in rows]))
    return out

def cbs_final(pick, primary, commence):
    """Second source #1: CBS scoreboard (independent company). One page per local game date (NFL: the
    game's week page). A card counts only when it is final, filed under that date, and its two team
    rows are the game's away and home teams in that order - matched by CBS's team url name
    ('pittsburgh-steelers') against ESPN's full team name, never a nickname or position. Matching
    cards that disagree (a doubleheader) are ambiguous: None. Returns ordered dict or None."""
    slug = CBS_SLUG.get(pick.get('espn_league', 'football/college-football'))
    if slug is None:
        return None
    hn, an = _norm(primary['home']), _norm(primary['away'])
    dates = _local_dates(commence)
    if slug == 'nfl':
        wk = _nfl_week(pick)
        if wk is None:
            return None
        pages = [f'https://www.cbssports.com/nfl/scoreboard/all/{wk[0]}/{wk[1]}/{wk[2]}/']
    else:
        pages = [f"https://www.cbssports.com/{slug}/scoreboard/{d.strftime('%Y%m%d')}/" for d in dates]
    want = {d.strftime('%Y%m%d') for d in dates}
    hits = []
    for url in pages:
        try:
            html = _get_text(url)
        except Exception:
            continue
        for day, rows in _cbs_cards(html, slug):
            (a_slug, a_sc), (h_slug, h_sc) = rows
            if day in want and _norm(a_slug) == an and _norm(h_slug) == hn:
                hits.append((day, a_sc, h_sc))
    if len(set(hits)) != 1:
        return None  # no final card, or matching cards that disagree (a doubleheader): no attestation
    day, a_sc, h_sc = hits[0]
    return {'source': f'cbs scoreboard (independent; final, {day})', 'away_id': primary['away'],
            'home_id': primary['home'], 'away_score': a_sc, 'home_score': h_sc}


TSCORE_LEAGUE = {'basketball/wnba': 'wnba'}
TSCORE_CITY = {'WSH': 'washington', 'WAS': 'washington', 'ATL': 'atlanta', 'NYL': 'new york',
               'MIN': 'minnesota', 'CHI': 'chicago', 'LVA': 'las vegas', 'LV': 'las vegas',
               'PHX': 'phoenix', 'LA': 'los angeles', 'DAL': 'dallas', 'SEA': 'seattle',
               'IND': 'indiana', 'CON': 'connecticut', 'GSV': 'golden state', 'GS': 'golden state'}

def thescore_final(pick, primary, commence):
    """Second source #1b: thescore events page (independent company), WNBA only.
    Fetches commence date AND UTC today/yesterday (rollover-safe). Matches both teams
    by city word against abbreviations; scores ordered home/away from the page payload."""
    lg = TSCORE_LEAGUE.get(pick.get('espn_league', ''))
    if lg is None:
        return None
    dates = {commence.strftime('%Y-%m-%d'),
             datetime.now(timezone.utc).strftime('%Y-%m-%d'),
             (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d')}
    for d in sorted(dates):
        try:
            url = f'https://www.thescore.com/{lg}/events/{d}'
            req = urllib.request.Request(url, headers={'User-Agent': 'python-urllib/3'})
            html = urllib.request.urlopen(req, timeout=15).read().decode('utf-8', 'ignore')
        except Exception:
            continue
        for bm in re.finditer(r'boxScore', html):
            seg = html[max(0, bm.start()-3000):bm.start()]
            ht = list(re.finditer(r'homeTeam.{0,400}?abbreviation\\":\\"([A-Z]{2,3})\\"', seg))
            at = list(re.finditer(r'awayTeam.{0,400}?abbreviation\\":\\"([A-Z]{2,3})\\"', seg))
            sc = re.search(r'homeScore\\":(\d+),\\"awayScore\\":(\d+)', html[bm.start():bm.start()+400])
            fin = re.search(r'description\\":\\"(Final)\\"', html[bm.start():bm.start()+400])
            if not (sc and ht and at):
                continue
            home_abbr, away_abbr = ht[-1].group(1), at[-1].group(1)
            hc, ac = TSCORE_CITY.get(home_abbr, ''), TSCORE_CITY.get(away_abbr, '')
            if not hc or not ac:
                continue
            if hc in primary['home'].lower() and ac in primary['away'].lower():
                if not fin:
                    continue  # not final on this source - keep looking
                return {'source': f'thescore (independent; Final confirmed, {d})',
                        'away_id': primary['away'], 'home_id': primary['home'],
                        'away_score': int(sc.group(2)), 'home_score': int(sc.group(1))}
    return None

def espn_site_final(pick, primary, commence):
    """Second source #2 (FALLBACK ONLY): ESPN site API - same company as the primary
    ESPN core feed, so independence is WEAKER; the source label carries that disclosure.
    Matches by exact displayName for BOTH teams + completed status; scores ordered by
    the competitors' homeAway field (never by array position)."""
    league = pick.get('espn_league', 'football/college-football')
    try:
        url = (f'https://site.api.espn.com/apis/site/v2/sports/{league}/scoreboard'
               f'?dates={commence.strftime("%Y%m%d")}')
        # UA 'Mozilla/5.0' is 403d by ESPN from this IP; python-urllib passes (9/27)
        data = _get(url, timeout=10, ua='python-urllib/3')
    except Exception:
        return None
    for ev in (data or {}).get('events') or []:
        comps = (ev.get('competitions') or [{}])[0].get('competitors') or []
        home = next((c for c in comps if c.get('homeAway') == 'home'), None)
        away = next((c for c in comps if c.get('homeAway') == 'away'), None)
        if home is None or away is None:
            continue
        if ((home.get('team') or {}).get('displayName') != primary['home']
                or (away.get('team') or {}).get('displayName') != primary['away']):
            continue
        if not ((ev.get('status') or {}).get('type') or {}).get('completed'):
            return None
        try:
            hs, as_ = int(home.get('score')), int(away.get('score'))
        except (TypeError, ValueError):
            return None
        return {'source': 'espn_site (SAME COMPANY as primary - weaker independence)',
                'away_id': primary['away'], 'home_id': primary['home'],
                'away_score': as_, 'home_score': hs}
    return None

ODDS_API_SPORT = {'football/college-football': 'americanfootball_ncaaf',
                  'football/nfl': 'americanfootball_nfl', 'basketball/nba': 'basketball_nba',
                  'basketball/mens-college-basketball': 'basketball_ncaab', 'basketball/wnba': 'basketball_wnba', 'baseball/mlb': 'baseball_mlb',
                  'hockey/nhl': 'icehockey_nhl', 'soccer/usa.1': 'soccer_usa_mls'}
ODDS_KEY_NAME = 'THE_ODDS_API_KEY'  # env var or keychain service holding the key (_secret)
_odds_cache = {}

def odds_api_final(pick, primary, commence):
    """Second source #3: the-odds-api scores endpoint (independent company).
    Budget-guarded (J-123): budget.check_and_log before every real pull; cached per
    (sport, date) within the run. Scores matched by TEAM NAME (never array position)
    into ordered (away, home) ints."""
    sport = ODDS_API_SPORT.get(pick.get('espn_league', 'football/college-football'))
    if sport is None:
        return None
    ckey = (sport, commence.strftime('%Y%m%d'))
    if ckey not in _odds_cache:
        key = _secret(ODDS_KEY_NAME)
        if not key:
            print(f'WARN: odds-api scores skipped: no {ODDS_KEY_NAME} in the environment or keychain')
            _odds_cache[ckey] = None
            return None
        try:
            budget.check_and_log(sport, 'scores', 1)
        except ValueError as e:
            print(f'WARN: odds-api scores pull blocked by budget: {e}')
            _odds_cache[ckey] = None
            return None
        try:
            url = f'https://api.the-odds-api.com/v4/sports/{sport}/scores/?apiKey={key}&daysFrom=2'
            _odds_cache[ckey] = _get(url, timeout=12)
        except Exception as e:
            print(f'WARN: odds-api scores fetch failed: {type(e).__name__}')  # never the url: it carries the key
            _odds_cache[ckey] = None
    games = _odds_cache[ckey]
    if not games:
        return None
    for g in games:
        if g.get('home_team') != primary['home'] or g.get('away_team') != primary['away']:
            continue
        if not g.get('completed'):
            return None
        by_name = {s2.get('name'): s2.get('score') for s2 in g.get('scores') or []}
        try:
            hs = int(by_name[primary['home']])
            as_ = int(by_name[primary['away']])
        except (KeyError, TypeError, ValueError):
            return None
        return {'source': 'the-odds-api (independent)',
                'away_id': primary['away'], 'home_id': primary['home'],
                'away_score': as_, 'home_score': hs}
    return None

REPO_NFL_SCORES = 'https://raw.githubusercontent.com/ItsDardanRexhepi/rixpicks/main/nfl_scores.json'
_repo_cache = {}

def repo_nfl_scores_final(pick, primary, commence):
    """Second source: repo nfl_scores.json (the-odds-api pulled GHA-side; builder committed
    9/27 13:12). Freshness-gated on pulled_at_utc <= 20 min."""
    if pick.get('espn_league') != 'football/nfl':
        return None
    try:
        d = _repo_cache.get('d')
        if d is None:
            d = _get(REPO_NFL_SCORES, timeout=12)
            _repo_cache['d'] = d
        from datetime import datetime, timezone, timedelta
        pulled = datetime.fromisoformat(d['pulled_at_utc'].replace('Z','+00:00'))
        if datetime.now(timezone.utc) - pulled > timedelta(minutes=20):
            print(f"WARN: repo nfl_scores.json stale ({d['pulled_at_utc']})")
            return None
        for g in d.get('games', []):
            if g.get('home_team') != primary['home'] or g.get('away_team') != primary['away']:
                continue
            if not g.get('completed'):
                return None
            by_name = {s2.get('name'): s2.get('score') for s2 in g.get('scores') or []}
            try:
                hs = int(by_name[primary['home']]); as_ = int(by_name[primary['away']])
            except (KeyError, TypeError, ValueError):
                return None
            return {'source': 'the-odds-api via repo (independent)',
                    'away_id': primary['away'], 'home_id': primary['home'],
                    'away_score': as_, 'home_score': hs}
    except Exception as e:
        print(f'WARN: repo nfl_scores fetch failed: {e}')
    return None


def mlb_statsapi_final(pick, primary, commence):
    """Second source: official MLB statsapi (free, no key). The schedule of the game's own local
    date (statsapi files a game under its officialDate - a 5:30 PM PT start is the next day in UTC,
    where the same two teams can have played again). A game counts only with both full team names
    equal to ESPN's and a scheduled start within 6 hours of the card's commence; exactly one such
    game, and it must be abstractGameState Final."""
    if pick.get('espn_league') != 'baseball/mlb':
        return None
    try:
        hits = []
        for day_d in _local_dates(commence):
            d = _get(f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={day_d.isoformat()}&hydrate=linescore")
            for day in d.get('dates', []):
                for g in day.get('games', []):
                    if (_norm(g['teams']['away']['team'].get('name')) != _norm(primary['away'])
                            or _norm(g['teams']['home']['team'].get('name')) != _norm(primary['home'])):
                        continue
                    start = datetime.fromisoformat(str(g.get('gameDate')).replace('Z', '+00:00'))
                    if abs(start - commence) <= timedelta(hours=6) and g.get('gamePk') not in [h.get('gamePk') for h in hits]:
                        hits.append(g)
        if len(hits) != 1:
            return None
        g = hits[0]
        if g.get('status', {}).get('abstractGameState') != 'Final':
            return None
        return {'source': 'mlb-statsapi (official)',
                'away_id': primary['away'], 'home_id': primary['home'],
                'away_score': g['teams']['away'].get('score'),
                'home_score': g['teams']['home'].get('score')}
    except Exception as e:
        print(f'WARN: mlb statsapi fetch failed: {type(e).__name__}: {e}')
    return None

def second_source(pick, primary, commence):
    """CBS -> theScore (WNBA) -> MLB statsapi -> repo nfl_scores (the-odds-api, GHA-side) -> direct
    odds-api (key from the environment or keychain)."""
    # frame guard (standing): the independent second source must be CROSS-COMPANY.
    # espn_site is same-company as the espn_core primary - never sufficient for grading.
    return (cbs_final(pick, primary, commence)
            or thescore_final(pick, primary, commence)
            or mlb_statsapi_final(pick, primary, commence)
            or repo_nfl_scores_final(pick, primary, commence)
            or odds_api_final(pick, primary, commence))

def two_source_ok(primary, secondary):
    """J-115: SAME team identities AND same ORDERED (away, home) scores. Reversed
    score pairs do NOT pass (swamp 9:25)."""
    return (secondary is not None
            and secondary.get('home_id') == primary.get('home')
            and secondary.get('away_id') == primary.get('away')
            and secondary.get('home_score') == primary.get('home_score')
            and secondary.get('away_score') == primary.get('away_score'))
