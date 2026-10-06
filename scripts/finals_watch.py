#!/usr/bin/env python3
"""J-118 TRIGGER: detect FINALs on today's card, grade in commence order with running cumulative
record/units from the canonical ledger, fire the instant record chain.
Guards (swamp 9:23-9:25 PM):
- cumulative state = LAST ledger row (record_pipe.current_state); empty ledger REFUSES.
- in-order processing: the chain STOPS at the first ungraded/unverified final so the
  public record can never regress or skip; later finals wait for the next fire.
- two-source final verification (J-115) BEFORE grading: the second source must be another
  company (CBS scoreboard, theScore, MLB statsapi, the-odds-api); ESPN's own site API never counts.
  Stable team identities + ORDERED (away, home) scores.
- tie = PUSH: 0 pnl, no W/L - except soccer, which grades on regulation time as Kalshi settles
  (core/soccer_result.py): a draw after 90 minutes is LOST for either side's moneyline, and
  totals/spreads count regulation goals only (never extra time or a shootout).
- seen[pick_key] written ONLY on a verified chain; a dry run touches NO production state.

DRY RUN BY DEFAULT. Production writes (ledger row, seen state, record_request.json) happen only
with --live. A dry run prints each grade; --requests-out PATH also writes the record write
requests a live run would queue to PATH (never to the checkout's record_request.json).

Paths and secrets come from the environment or a config file - never from a fixed checkout:
  RIX_REPO   the rixpicks checkout to read (manifest.json, core/, record_request.json);
             default: the checkout this script is in.
  RPS_KB     the private knowledge-base folder; its ledger/ holds record_rows.jsonl (the J-118
             record ledger), finals_seen.json, picks.jsonl, positions.jsonl and odds_credits.jsonl.
             No default: unset, the run refuses before grading.
  RIX_FINALS_CONFIG  optional JSON file {"RIX_REPO": ..., "RPS_KB": ...}; the environment wins.
  Secrets (record POST token RIX_RECORD_TOKEN, odds key THE_ODDS_API_KEY) come from the
  environment variable of that name, else the macOS login keychain item whose service is that
  name. They are never printed. A dry run never reads the record token.
Usage: finals_watch.py [--dry-run | --live] [--requests-out PATH]"""
import json, os, re, subprocess, sys, unicodedata, urllib.request

def _config():
    path = os.environ.get('RIX_FINALS_CONFIG')
    if not path:
        return {}
    try:
        cfg = json.load(open(os.path.expanduser(path)))
    except (OSError, ValueError) as e:
        raise SystemExit(f'FAIL-CLOSED: RIX_FINALS_CONFIG {path!r} unreadable ({type(e).__name__}) - refusing to run')
    if not isinstance(cfg, dict):
        raise SystemExit(f'FAIL-CLOSED: RIX_FINALS_CONFIG {path!r} is not a JSON object - refusing to run')
    return cfg

_CFG = _config()

def _setting(name):
    v = os.environ.get(name) or _CFG.get(name)
    return os.path.abspath(os.path.expanduser(str(v))) if v else None

ROOT = _setting('RIX_REPO') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)  # core/ from the checkout being graded
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from core import record_pipe, units, budget, fill_leak, soccer_result
from core.accepted_entry import accepted_entry, entry_delta
HERE = os.path.join(ROOT, 'scripts')  # record_request.json lands at HERE/../record_request.json
MANIFEST = os.path.join(ROOT, 'manifest.json')
RPS_KB = _setting('RPS_KB')
_KB_LEDGER = os.path.join(RPS_KB, 'ledger') if RPS_KB else None
STATE = os.path.join(_KB_LEDGER, 'finals_seen.json') if _KB_LEDGER else None
LEDGER = os.path.join(_KB_LEDGER, 'record_rows.jsonl') if _KB_LEDGER else None
PICKS_LEDGER = os.path.join(_KB_LEDGER, 'picks.jsonl') if _KB_LEDGER else None
POSITIONS_LEDGER = os.path.join(_KB_LEDGER, 'positions.jsonl') if _KB_LEDGER else None
if _KB_LEDGER and not os.environ.get('ODDS_CREDITS_LEDGER'):
    budget.LEDGER = os.path.join(_KB_LEDGER, 'odds_credits.jsonl')  # odds-api pulls log beside the other ledgers
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

def _card_price(pick):
    # the private picks ledger lives under RPS_KB on the grading host
    return fill_leak.card_price(pick) if PICKS_LEDGER is None else fill_leak.card_price(pick, picks_path=PICKS_LEDGER)

def _fill_divergence(pick):
    return (fill_leak.fill_divergence(pick) if POSITIONS_LEDGER is None
            else fill_leak.fill_divergence(pick, positions_path=POSITIONS_LEDGER))

def _get(url, timeout=20, ua='Mozilla/5.0'):
    req = urllib.request.Request(url, headers={'User-Agent': ua})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def _deref(node):
    return _get(node['$ref']) if isinstance(node, dict) and '$ref' in node else node

def espn_final(league, eid):
    """Primary: ESPN core. Returns {'home','away','home_score','away_score'} when final."""
    lg = league.replace('/', '/leagues/')
    base = f'https://sports.core.api.espn.com/v2/sports/{lg}/events/{eid}/competitions/{eid}'
    c = _get(base)
    st = _deref(c.get('status', {})).get('type', {})
    if not st.get('completed'):
        return None
    sc = {}
    names = {}
    abbrs = {}
    for x in c.get('competitors', []):
        s2 = _deref(x.get('score', {}))
        v = s2.get('value') if isinstance(s2, dict) else None
        sc[x.get('homeAway')] = int(float(v)) if v is not None else None
        team = _deref(x.get('team', {}))
        names[x.get('homeAway')] = team.get('displayName') or team.get('name') or ''
        abbrs[x.get('homeAway')] = team.get('abbreviation') or ''
    if sc.get('home') is None or sc.get('away') is None:
        return None
    return {'home': names.get('home', ''), 'away': names.get('away', ''),
            'home_abbr': abbrs.get('home', ''), 'away_abbr': abbrs.get('away', ''),
            'home_score': sc['home'], 'away_score': sc['away']}

def score_text(primary):
    """The record write's score: '<AWAY> <n> @ <HOME> <n>' in ESPN's team abbreviations, the exact
    format record_final.py parses (2-4 capital letters a side). Full team names were queued before and
    record_final refused every one as unparseable, stopping the in-order record write. Raises
    ValueError when an abbreviation cannot be put in that format (fail closed: never queued)."""
    ab = {}
    for side in ('away', 'home'):
        a = re.sub(r'[^A-Z]', '', str(primary.get(f'{side}_abbr') or '').upper())  # 'TA&M' -> 'TAM'
        if not 2 <= len(a) <= 4:
            raise ValueError(f"no usable ESPN abbreviation for the {side} team ({primary.get(f'{side}_abbr')!r}) - "
                             'REFUSING to queue a score record_final cannot parse (fail closed)')
        ab[side] = a
    return f"{ab['away']} {primary['away_score']} @ {ab['home']} {primary['home_score']}"

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

# --- PLAYER PROPS (props-on-card wiring 9/27, his 6:48:03 PM PT "Include player props too") ---
# Verified ESPN boxscore keys only (same machinery as the Wooder leg graders, verified vs real
# boxscores 9/27). A market outside this map is UNGRADEABLE - the adapter refuses to card it and
# grade() refuses to grade it, both fail closed.
PROP_STAT_KEYS = {
    'passing_yards': ('passingYards',), 'pass_td': ('passingTouchdowns',),
    'rushing_yards': ('rushingYards',), 'rush_attempts': ('rushingAttempts',),
    'receiving_yards': ('receivingYards',), 'receptions': ('receptions',),
    'reception_tds': ('receivingTouchdowns',), 'rush_tds': ('rushingTouchdowns',),
    'points': ('points',), 'rebounds': ('rebounds',), 'assists': ('assists',),
    'threes': ('threePointFieldGoalsMade-threePointFieldGoalsAttempted',),
    'goals': ('goals',), 'shots_on_goal': ('shotsTotal',),
    'saves': ('saves',), 'blocked_shots': ('blockedShots',)}
# specials: 'anytime_td' = rushing+receiving TDs; 'hockey_points' = goals+assists.
# MLB (9/27, his 6:54:23 PM PT 'Finish MLB and soccer prop markets grading'): batting keys
# ('hits','runs','walks','strikeouts','homeRuns','RBIs') also appear in the PITCHING group, so
# every MLB market scopes to its group by marker key - grounded in a live ESPN MLB boxscore.
# ESPN batting carries NO stolen-bases and NO doubles/triples keys: batter_stolen_bases,
# batter_total_bases and pitcher_record_a_win stay UNGRADEABLE (adapter loud-skips, here REFUSE).
PROP_GROUP_SCOPED = {  # market -> (group marker key, stat keys)
    'bat_hits':         ('atBats', ('hits',)),
    'bat_home_runs':    ('atBats', ('homeRuns',)),
    'bat_rbis':         ('atBats', ('RBIs',)),
    'bat_runs':         ('atBats', ('runs',)),
    'bat_walks':        ('atBats', ('walks',)),
    'bat_strikeouts':   ('atBats', ('strikeouts',)),
    'pit_strikeouts':   ('earnedRuns', ('strikeouts',)),
    'pit_hits_allowed': ('earnedRuns', ('hits',)),
    'pit_walks':        ('earnedRuns', ('walks',)),
    'pit_earned_runs':  ('earnedRuns', ('earnedRuns',)),
    'pit_outs':         ('earnedRuns', ('fullInnings.partInnings',)),  # 6.1 -> 19 outs
}
# Soccer (MLS): ESPN soccer summary has NO player stat tables (boxscore.teams only) - scorer
# markets grade off keyEvents scoringPlay==True goal events, resolved against the ROSTER
# athlete map (strict identity, own goals never credit, periods 1-2 only, shootout excluded).
# shots_on_target has no player source -> UNGRADEABLE (adapter loud-skips, here REFUSE).
SOCCER_SCORER_MARKETS = ('anytime_goal', 'first_goal', 'last_goal')
_PROP_BOX = {}  # per-run boxscore cache keyed by (league, eid)

def _norm_name(x):
    return re.sub(r'[^a-z0-9]', '', (x or '').lower())

def _fold_name(x):
    # _norm_name with accents folded first ('Tomás Ostrák' -> 'tomasostrak'): ESPN spells one player
    # both ways across its rosters and goal text, and a card name may differ from both. Used only to
    # match soccer scorer names (same rule as record_final.py); grade keys keep _norm_name.
    x = unicodedata.normalize('NFKD', str(x or '')).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]', '', x.lower())

def _prop_boxscore(league, eid):
    key = (league, str(eid))
    if key not in _PROP_BOX:
        url = f'https://site.api.espn.com/apis/site/v2/sports/{league}/summary?event={eid}'
        _PROP_BOX[key] = _get(url, ua='python-urllib/3.10')  # Mozilla 403s from this IP
    return _PROP_BOX[key]

def _resolve_player(d, player):
    # Strict identity (learning #3 + fail-closed bar): normalized full-name match, deduped by
    # athlete id across stat groups; 0 or >1 distinct athletes = REFUSE, never guess.
    want = _norm_name(player)
    if not want:
        raise ValueError('prop pick missing player name - REFUSING to grade (fail closed)')
    seen = {}
    for team in d.get('boxscore', {}).get('players', []):
        for grp in team.get('statistics', []):
            for ath in grp.get('athletes', []):
                a = ath.get('athlete', {})
                nm = _norm_name(a.get('displayName', ''))
                if nm and (nm == want or want in nm or nm in want):
                    seen[a.get('id') or a.get('displayName')] = a.get('displayName')
    if len(seen) != 1:
        raise ValueError(f'player identity ambiguous/unresolved ({len(seen)} matches for '
                         f'{player!r}) - REFUSING to grade (fail closed)')
    return next(iter(seen.values()))

def _prop_stat(pick):
    market = pick.get('market')
    line = pick.get('line')
    if pick.get('side') not in ('over', 'under'):
        raise ValueError(f"prop pick side {pick.get('side')!r} - must be over|under (fail closed)")
    if line is None:
        raise ValueError('prop pick missing line - REFUSING to grade (fail closed)')
    d = _prop_boxscore(pick.get('espn_league'), pick['game']['eid'])
    # soccer scorer markets resolve identity against ROSTERS (no boxscore player tables);
    # everything else resolves against boxscore stat groups (strict, deduped by athlete id)
    if market in SOCCER_SCORER_MARKETS:
        return _soccer_scorer_stat(d, pick.get('player'), market)
    resolved = _resolve_player(d, pick.get('player'))
    rn = _norm_name(resolved)

    def stat_from(keys_wanted, marker=None):
        for team in d.get('boxscore', {}).get('players', []):
            for grp in team.get('statistics', []):
                keys = grp.get('keys', [])
                if marker and marker not in keys: continue  # group scoping (MLB bat vs pit)
                for w in keys_wanted:
                    if w not in keys: continue
                    yi = keys.index(w)
                    for ath in grp.get('athletes', []):
                        if _norm_name(ath.get('athlete', {}).get('displayName', '')) != rn: continue
                        v = ath.get('stats', [])[yi] if yi < len(ath.get('stats', [])) else None
                        try:
                            return float(str(v).split('-')[0])  # compound made-attempted -> made
                        except (TypeError, ValueError):
                            raise ValueError(f'stat line unparsable ({v!r}) for {resolved} {market} - fail closed')
        raise ValueError(f'stat line missing for {resolved} {market} (DNP or group absent) - fail closed')

    if market == 'anytime_td':
        val = 0.0; found = 0
        for keys_wanted in (('rushingTouchdowns',), ('receivingTouchdowns',)):
            try: val += stat_from(keys_wanted); found += 1
            except ValueError: pass  # no carries/no targets group = 0 TDs there, not a miss
        if not found:
            raise ValueError(f'no rushing/receiving groups for {resolved} - fail closed')
    elif market == 'hockey_points':
        val = stat_from(('goals',)) + stat_from(('assists',))
    elif market in PROP_GROUP_SCOPED:
        marker, keys_wanted = PROP_GROUP_SCOPED[market]
        if market == 'pit_outs':
            raw = None
            for team in d.get('boxscore', {}).get('players', []):
                for grp in team.get('statistics', []):
                    keys = grp.get('keys', [])
                    if marker not in keys: continue
                    yi = keys.index('fullInnings.partInnings')
                    for ath in grp.get('athletes', []):
                        if _norm_name(ath.get('athlete', {}).get('displayName', '')) != rn: continue
                        raw = ath.get('stats', [])[yi] if yi < len(ath.get('stats', [])) else None
            if raw is None:
                raise ValueError(f'stat line missing for {resolved} {market} (DNP or group absent) - fail closed')
            parts = str(raw).split('.')
            try:
                full = int(parts[0]); part = int(parts[1]) if len(parts) > 1 else 0
            except ValueError:
                raise ValueError(f'innings line unparsable ({raw!r}) for {resolved} - fail closed')
            if part not in (0, 1, 2):
                raise ValueError(f'innings line invalid ({raw!r}) for {resolved} - fail closed')
            val = float(full * 3 + part)
        else:
            val = stat_from(keys_wanted, marker=marker)
    elif market in PROP_STAT_KEYS:
        val = stat_from(PROP_STAT_KEYS[market])
    else:
        raise ValueError(f'prop market {market!r} not in the verified gradeable map - REFUSING to grade (fail closed)')
    return val

_GOAL_NAME = re.compile(r'^(?:Own Goal by )?(.+?) \(([^()]*)\)')
_SCORELINE_END = re.compile(r'(?<=\d)\. ')  # the '. ' after the away score, never one inside a team name
_OWN_GOAL_TEXT = re.compile(r'\s*own goal\b', re.I)

def _roster_alias_map(d):
    # accent-folded name alias -> athlete id (as str), over both teams' rosters
    m = {}
    for r in d.get('rosters', []) or []:
        for e in r.get('roster', []) or []:
            a = e.get('athlete', {})
            aid = str(a.get('id') or '')
            if not aid: continue
            for nm in (a.get('displayName'), a.get('fullName'), a.get('shortName')):
                n = _fold_name(nm)
                if n: m.setdefault(n, set()).add(aid)
    return m

def _goal_scorer_id(p, aliases, rostered):
    # Scorer of one goal event: ESPN's own participants[0] athlete id, which must be on a roster
    # (same rule as record_final.py). The goal text's name (after the scoreline, 'Goal! <home> <n>,
    # <away> <n>. <Scorer> (<Team>) ...' - the first '. ' can fall inside 'D.C. United' or 'St. Louis
    # City SC') only cross-checks it: a name that resolves on the rosters to anyone else refuses, a
    # name the rosters spell differently ('Guilherme' for Guilherme Augusto, 'Luighi' for Luighi
    # Hanri) leaves the id standing. With no participant id the name must resolve to one player.
    text = p.get('text') or ''
    if _OWN_GOAL_TEXT.match(text):
        raise ValueError(f'goal event text names an own goal ({text[:80]!r}) - REFUSING to grade (fail closed)')
    parts = p.get('participants')
    first = parts[0] if isinstance(parts, list) and parts and isinstance(parts[0], dict) else {}
    ath = first.get('athlete') if isinstance(first.get('athlete'), dict) else {}
    sid = str(ath.get('id') or '')
    mm = _GOAL_NAME.search(_SCORELINE_END.split(text, maxsplit=1)[-1])
    named = aliases.get(_fold_name(mm.group(1)), set()) if mm else set()
    if sid:
        if sid not in rostered:
            raise ValueError(f'goal scorer id {sid} not on the rosters - REFUSING to grade (fail closed)')
        if named and sid not in named:
            raise ValueError(f'goal scorer id {sid} is not the goal text\'s {mm.group(1)!r} - REFUSING to grade (fail closed)')
        return sid
    if not mm:
        raise ValueError(f'goal event text unparsable ({text[:80]!r}) - REFUSING to grade (fail closed)')
    if len(named) != 1:
        raise ValueError(f'goal scorer {mm.group(1)!r} unresolved/ambiguous on rosters '
                         f'({len(named)} matches) - REFUSING to grade (fail closed)')
    return next(iter(named))

def _soccer_scorer_stat(d, player, market):
    aliases = _roster_alias_map(d)
    want = _fold_name(player)
    if not want:
        raise ValueError('prop pick missing player name - REFUSING to grade (fail closed)')
    ids = {aid for alias, aids in aliases.items()
           if alias == want or want in alias or alias in want for aid in aids}
    if len(ids) != 1:
        raise ValueError(f'player identity ambiguous/unresolved ({len(ids)} roster matches for '
                         f'{player!r}) - REFUSING to grade (fail closed)')
    pid = next(iter(ids))
    rostered = {str((e.get('athlete') or {}).get('id') or '') for r in d.get('rosters', []) or []
                for e in r.get('roster', []) or []} - {''}
    goals = []  # (clock_seconds, athlete_id) credit events; own goals + shootout excluded
    for p in d.get('keyEvents', []) or []:
        if p.get('scoringPlay') is not True: continue
        if p.get('type', {}).get('type') == 'own-goal': continue
        if (p.get('period', {}) or {}).get('number') not in (1, 2): continue  # no shootout/ET
        goals.append(((p.get('clock', {}) or {}).get('value', 0.0), _goal_scorer_id(p, aliases, rostered)))
    if market == 'anytime_goal':
        return float(sum(1 for _, aid in goals if aid == pid))
    if not goals:
        return 0.0  # no credited goals: first/last scorer props lose
    key = min if market == 'first_goal' else max
    edge = key(v[0] for v in goals)
    if sum(1 for v in goals if v[0] == edge) > 1:
        raise ValueError(f'{market} ordering ambiguous (tied clock) - REFUSING to grade (fail closed)')
    return float(1.0 if any(v[0] == edge and v[1] == pid for v in goals) else 0.0)

def _soccer_regulation(pick, primary):
    """The checked regulation score of a soccer final (core/soccer_result.regulation_score), read from
    ESPN's summary; its final must equal the two-source-verified final. Raises ValueError (fail closed)."""
    try:
        d = _prop_boxscore(pick.get('espn_league'), pick['game']['eid'])
    except Exception as e:
        raise ValueError(f'ESPN summary unavailable ({type(e).__name__}) - REFUSING to grade soccer '
                         'without its regulation score (fail closed)') from None
    try:
        reg = soccer_result.regulation_score(d)
    except ValueError as e:
        raise ValueError(f'soccer regulation score not established ({e}) - REFUSING to grade (fail closed)') from None
    if (reg['final_away'], reg['final_home']) != (primary['away_score'], primary['home_score']):
        raise ValueError(f"summary final {reg['final_away']}-{reg['final_home']} != verified final "
                         f"{primary['away_score']}-{primary['home_score']} - REFUSING to grade (fail closed)")
    return reg

def result_of(pick, primary):
    """W | L | PUSH of one card pick on the verified final - the result alone, before any price or
    stake is read (grade() adds those). Soccer grades on regulation time (module header).
    Raises ValueError when the pick cannot be graded (fail closed)."""
    mc = pick.get('market_class', 'ml')
    hs, as_ = primary['home_score'], primary['away_score']
    if mc == 'prop':
        # graded off the player stat line AFTER the two-source final verification above;
        # equality with the line = PUSH (0 pnl, no W/L), same as spread/total.
        val = _prop_stat(pick)
        line = Decimal(str(pick['line']))
        v = Decimal(str(val))
        if v == line:
            return 'PUSH'
        won = (pick['side'] == 'over') == (v > line)
    elif soccer_result.is_soccer(pick.get('espn_league')):
        # three-way regulation markets: 90 minutes plus stoppage, a draw loses either side's moneyline
        if mc not in ('ml', 'spread', 'total'):
            raise ValueError(f'soccer market class {mc!r} has no grading rule here - REFUSING to grade (fail closed)')
        if mc != 'ml' and pick.get('line') is None:
            raise ValueError(f'{mc} pick missing line - REFUSING to grade (fail closed)')
        res = soccer_result.outcome(_soccer_regulation(pick, primary), pick.get('side'), mc, pick.get('line'))
        if res is None:
            raise ValueError(f"soccer {mc} side {pick.get('side')!r} line {pick.get('line')!r} cannot be graded "
                             'from a score - REFUSING to grade (fail closed)')
        return {'WON': 'W', 'LOST': 'L', 'PUSH': 'PUSH'}[res]
    elif mc == 'spread':
        # pick['line'] = HOME spread (negative when home favored); side home|away.
        if pick.get('line') is None:
            raise ValueError('spread pick missing line - REFUSING to grade (fail closed)')
        line = Decimal(str(pick['line']))
        diff = Decimal(str(hs)) + line - Decimal(str(as_))  # >0 home covers, <0 away covers
        if diff == 0:
            return 'PUSH'
        won = (pick['side'] == 'home') == (diff > 0)
    elif mc == 'total':
        # pick['line'] = game total; side over|under.
        if pick.get('line') is None:
            raise ValueError('total pick missing line - REFUSING to grade (fail closed)')
        line = Decimal(str(pick['line']))
        tot = Decimal(str(hs)) + Decimal(str(as_))
        if tot == line:
            return 'PUSH'
        won = (pick['side'] == 'over') == (tot > line)
    else:
        if hs == as_:
            return 'PUSH'  # a tie (NFL, ...) refunds; soccer never reaches here
        won = (pick['side'] == 'home') == (hs > as_)
    return 'W' if won else 'L'

def grade(pick, primary):
    result = result_of(pick, primary)
    if result == 'PUSH':
        return 'PUSH', Decimal('0')
    won = result == 'W'
    accepted = accepted_entry(pick)
    cents = accepted['entry_c'] if accepted is not None else (pick.get('kalshi') or {}).get('cents')
    # FILL-LEAK GUARD: manifest price must equal the picks-ledger card entry;
    # positions fills differing from the card price warn but never block.
    card_c, card_row, n_card = _card_price(pick)
    if accepted is not None and card_row != accepted:
        raise ValueError('accepted-entry provenance mismatch - REFUSING to grade')
    if n_card != 1:
        raise ValueError(f'card record missing or ambiguous (n={n_card}) for '
                         f"{pick['game']['eid']}|{pick.get('market_class', 'ml')}|{pick['side']} - REFUSING to grade (fail closed)")
    def _valid_price(v):
        # strict integer cents (swamp nit 9:41): 63.9 float, bools, non-digit
        # strings all refuse - only a true int or an all-digit string passes.
        if isinstance(v, bool):
            return False
        if isinstance(v, int):
            return 1 <= v <= 99
        if isinstance(v, str):
            return v.isdigit() and 1 <= int(v) <= 99
        return False
    # swamp 9:40: BOTH prices must be present and valid before grade - a null
    # card price must never wave the manifest price through.
    if not _valid_price(card_c):
        raise ValueError(f'card entry price missing/invalid ({card_c!r}) - REFUSING to grade (fail closed)')
    if not _valid_price(cents):
        raise ValueError(f'manifest price missing/invalid ({cents!r}) - REFUSING to grade (fail closed)')
    if int(card_c) != int(cents):
        raise ValueError(f'card-price fork: manifest {cents}c != picks-ledger {card_c}c - REFUSING to grade')
    for dv in _fill_divergence(pick):
        if cents is not None and dv['fill_c'] is not None and int(dv['fill_c']) != int(cents):
            print(f"WARN: fill divergence {dv['id']} {dv['venue']} {dv['fill_c']}c vs card {cents}c - "
                  'grade uses CARD price, fill stays in positions ledger')
    # CARD-PRICE GRADING (his word 9:43 PM, uniform convention): P&L is computed from
    # the published CARD American price, sourced from the picks-ledger card entry and
    # asserted identical against the published card (manifest odds). Exchange cents
    # above stay an exchange-consistency check only - never the grading basis,
    # except the explicitly accepted exact-cents entry below (-138 is rounded).
    def _parse_american(v):
        if isinstance(v, bool):
            return None
        if isinstance(v, int):
            a = v
        elif isinstance(v, str) and re.fullmatch(r'[+-]?\d+', v.strip()):
            a = int(v.strip())
        else:
            return None
        return a if (a >= 100 or a <= -101) else None
    manifest_am = _parse_american(pick.get('odds'))
    card_am = _parse_american(card_row.get('card_american'))
    if manifest_am is None:
        raise ValueError(f"manifest published price missing/invalid ({pick.get('odds')!r}) - REFUSING to grade (fail closed)")
    if card_am is None:
        raise ValueError(f"picks-ledger card entry lacks a valid card_american ({card_row.get('card_american')!r}) - "
                         'REFUSING to grade (fail closed)')
    if card_am != manifest_am:
        raise ValueError(f'published-price fork: manifest {manifest_am} != picks-ledger {card_am} - REFUSING to grade')
    u = Decimal(str(pick.get('units', '0u')).rstrip('u'))
    if not u:
        raise ValueError('missing units in manifest - grade manually')
    stake = u * units.unit_dollars()  # exact from the first multiplication; 1u dollar size from env (private, fail closed)
    if accepted is not None:
        return ('W' if won else 'L'), entry_delta('W' if won else 'L', stake, accepted)
    return ('W' if won else 'L'), (units.stake_pnl_american(stake, card_am) if won else -stake)

def _parse_ts(s):
    return datetime.fromisoformat(str(s).replace('Z', '+00:00'))

def load_seen():
    try: return json.load(open(STATE))
    except Exception: return {}


def _queue_record_request(p, eid, pkey, result, primary, rec, u2, pnl, secondary, stamp, card_date=None, path=None):
    """Append the builder-consumed record write request (same cycle as the grade).
    This + the instant parent relay is the write path while the direct POST token is dead.
    path: where to append; default the checkout's record_request.json (a dry run passes its
    --requests-out file instead and never touches the checkout's queue)."""
    path = path or os.path.join(HERE, '..', 'record_request.json')
    try: d = json.load(open(path))
    except Exception: d = {'requests': []}
    if any(r.get('grade_id') == pkey for r in d.get('requests', [])):
        return False
    # grade() returns W | L | PUSH; a push must travel as PUSH (record_final derives the result
    # from the verified final and refuses a push labeled LOST). market_class/line/card_date let
    # record_final cross-check the request against the published card pick. card_date is the date
    # of the card the pick was graded from (the manifest's date), not the game's own PT date: a
    # game starting after midnight PT still belongs to the card it was published on. None lets
    # record_final derive it from the published card.
    d.setdefault('requests', []).append({
        'grade_id': pkey, 'event_id': eid, 'league': p.get('espn_league', ''),
        'pick': p.get('name', ''), 'side': p.get('side', ''),
        'market_class': p.get('market_class') or 'ml', 'line': p.get('line'),
        'card_date': card_date,
        'result': {'W': 'WON', 'L': 'LOST', 'PUSH': 'PUSH'}[result],
        'score': score_text(primary),
        'stake_units': p.get('units', '?'), 'locked_american': p.get('odds', '?'),
        'delta_units_exact': float(units.pnl_to_units(pnl)),
        'record_after': rec, 'units_after_exact': float(u2),
        'two_source': ['espn_core completed', secondary['source']],
        # the same ESPN-abbreviation score as 'score' ('Penguins ML L: WPG 3 @ PIT 2 (published-card
        # basis)'), the format every graded row on the record carries - never the card's full team names
        'graded_pick': (f"{p.get('name','')} {({'W': 'W', 'L': 'L', 'PUSH': 'P'})[result]}: "
                        f"{score_text(primary)} (published-card basis)"),
        'source': 'finals_watch J-118 live chain',
        'queued_at': stamp})
    accepted = accepted_entry(p)
    if accepted is not None:
        d['requests'][-1]['accepted_entry'] = {k: accepted[k] for k in ('accepted_entry_id', 'card_venue', 'entry_c', 'entry_basis')}
    json.dump(d, open(path, 'w'), indent=1)
    return True

def _api_live_record():
    try:
        req = urllib.request.Request(record_pipe.SITE_GET, headers={'User-Agent': 'python-urllib/3'})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except Exception:
        return None

def _repo_mirror_record():
    """Builder-owned mirror (slates/api_record.json), emitted on every apply - a relayed
    row counts as landed when EITHER the worker GET or this mirror shows its record."""
    try:
        req = urllib.request.Request(
            'https://raw.githubusercontent.com/ItsDardanRexhepi/rixpicks/main/slates/api_record.json',
            headers={'User-Agent': 'python-urllib/3'})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except Exception:
        return None

RECORD_TOKEN_NAME = 'RIX_RECORD_TOKEN'  # env var or keychain service of the record POST token (_secret)

def _live_blockers():
    """Why a --live run cannot write from this checkout ([] = it can). The live chain relays through
    core/record_pipe with resume_pending(skip=) and on_final(no_post=); a record_pipe without them
    would crash mid-chain, so the run refuses before it starts instead."""
    import inspect
    out = []
    for fn, kw in ((record_pipe.resume_pending, 'skip'), (record_pipe.on_final, 'no_post')):
        ps = inspect.signature(fn).parameters
        if kw not in ps and not any(x.kind == x.VAR_KEYWORD for x in ps.values()):
            out.append(f'core/record_pipe.{fn.__name__}() takes no {kw}=')
    return out

def _mode(argv):
    """(dry, requests_out) from the command line. Dry unless --live; exits 2 on a bad combination."""
    live = '--live' in argv
    if live and '--dry-run' in argv:
        print('REFUSED: --live and --dry-run together - pick one', file=sys.stderr)
        sys.exit(2)
    out = None
    if '--requests-out' in argv:
        i = argv.index('--requests-out')
        if live or i + 1 >= len(argv) or argv[i + 1].startswith('--'):
            print('REFUSED: --requests-out PATH is a dry-run option and needs a path', file=sys.stderr)
            sys.exit(2)
        out = os.path.abspath(argv[i + 1])
        # a dry run writes no production state: never into the checkout (its queue, manifest, public
        # files) or the knowledge base (ledgers, seen state) - the preview goes somewhere else
        real = os.path.realpath(out)
        for root in (ROOT, RPS_KB):
            r = os.path.realpath(root) if root else None
            if r and (real == r or real.startswith(r + os.sep)):
                print(f'REFUSED: --requests-out {out!r} is inside {r!r}; a dry run writes no production state - '
                      'pick a path outside the checkout and RPS_KB', file=sys.stderr)
                sys.exit(2)
        if os.path.isdir(real):
            print(f'REFUSED: --requests-out {out!r} is a directory', file=sys.stderr)
            sys.exit(2)
    return not live, out

def main():
    dry, requests_out = _mode(sys.argv)
    if LEDGER is None or STATE is None:
        print('REFUSED: RPS_KB is not set (environment or RIX_FINALS_CONFIG). The record ledger '
              '(ledger/record_rows.jsonl) and the seen state live under it - nothing graded.', file=sys.stderr)
        sys.exit(5)
    if not dry:
        blockers = _live_blockers()
        if blockers:
            print('LIVE REFUSED: ' + '; '.join(blockers) + ' - the live record chain is not wired on this checkout. '
                  'Nothing written; run without --live for a dry run.', file=sys.stderr)
            sys.exit(7)
    m = json.load(open(MANIFEST))
    # STALE-MANIFEST TRIPWIRE (Sep 29 incident: grader read a 2-day-old rix_tmp manifest and
    # today's finals nearly went ungraded): the card date must be today or yesterday (PT) -
    # yesterday tolerates post-midnight stragglers; anything older is the wrong card. Fail closed.
    _today_pt = datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d')
    try:
        from zoneinfo import ZoneInfo as _ZI
        _today_pt = datetime.now(_ZI('America/Los_Angeles')).strftime('%Y-%m-%d')
    except Exception: pass
    _yday_pt = (datetime.strptime(_today_pt, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
    if m.get('date') not in (_today_pt, _yday_pt):
        print(f"STALE MANIFEST REFUSED: {MANIFEST} carries card date {m.get('date')!r}, expected {_today_pt} or {_yday_pt} - "
              f"the daily build did not refresh this clone's manifest (see build_manifest.py prod mirror). Refusing to grade.", file=sys.stderr)
        sys.exit(6)
    seen = load_seen()
    # swamp 9:30: reconstruct seen from ledger/sidecar-verified rows - a crash between
    # on_final verify and the seen write must not regrade (resume-mismatch deadlock).
    for gid in record_pipe.verified_grade_ids(LEDGER):
        if gid not in seen:
            seen[gid] = {'reconstructed_from_ledger': True}
    stamp = datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')
    date_label = m.get('date_label', '')
    if requests_out:
        json.dump({'requests': []}, open(requests_out, 'w'), indent=1)  # this run's preview only
    if not dry:
        token = _secret(RECORD_TOKEN_NAME)  # live only: a dry run never reads the token
        # swamp 9:28: resume unfinished pending grades (appended, POST/GET not verified)
        # with their EXACT saved rows BEFORE any successor is graded or state is read.
        # Relayed rows (direct-POST dead, write gone via record_request + builder) are
        # verified by the api GET sweep below, not by re-POST - skip them here.
        relayed = {gid for gid, ent in seen.items() if ent.get('unverified')}
        resumed = record_pipe.resume_pending(LEDGER, token, skip=relayed)
        # api GET sweep: a relayed row is verified once the live api shows its record
        live = _api_live_record()
        mirror = _repo_mirror_record()
        landed = [src for src in (('worker', live), ('repo-mirror', mirror))
                  if src[1] and f"{src[1].get('w')}-{src[1].get('l')}" is not None]
        dirty = False
        for gid, ent in list(seen.items()):
            if not ent.get('unverified'):
                continue
            match = next((name for name, src in (('worker', live), ('repo-mirror', mirror))
                          if src and f"{src.get('w')}-{src.get('l')}" == ent.get('record')), None)
            if match:
                seen[gid] = {'verified_at': stamp, 'result': ent.get('result'),
                             'record': ent.get('record'), 'verified_via': f'{match} sweep'}
                st = record_pipe._load_state(LEDGER)
                st.setdefault(gid, {})['verified'] = True
                st[gid]['appended'] = True
                record_pipe._save_state(LEDGER, st)
                dirty = True
                print(f'{stamp} FINAL-CHAIN VERIFIED-VIA-{match.upper()} {gid} -> {ent.get("record")}')
        if dirty:
            os.makedirs(os.path.dirname(STATE), exist_ok=True)
            json.dump(seen, open(STATE, 'w'))
        for r in resumed:
            if r['chain'] == 'complete':
                seen[r['grade_id']] = {'verified_at': stamp, 'resumed': True}
                os.makedirs(os.path.dirname(STATE), exist_ok=True)
                json.dump(seen, open(STATE, 'w'))
                print(f'{stamp} FINAL-CHAIN RESUMED+VERIFIED {r["grade_id"]}')
            else:
                print(f'{stamp} WARN: pending grade {r["grade_id"]} still {r["chain"]} - chain STOPS, nothing new graded')
                return
    W, L, U = record_pipe.current_state(LEDGER)
    picks = sorted([p for p in m.get('picks', []) if p.get('game', {}).get('eid')],
                   key=lambda p: p['game'].get('commence', ''))
    fired = []
    for p in picks:
        g = p['game']
        eid = g['eid']
        _mc = p.get('market_class', 'ml')
        if _mc == 'prop':
            pkey = f"{eid}|prop|{_norm_name(p.get('player'))}|{p.get('market')}|{p['side']}|{p.get('line')}"
        elif _mc in ('spread', 'total'):
            pkey = f"{eid}|{_mc}|{p['side']}|{p.get('line')}"
        else:
            pkey = f"{eid}|{_mc}|{p['side']}"  # ml | spread+line | total+line | prop (s/t+props wired 9/27)
        if pkey in seen:
            continue
        if p.get('espn_league') == 'mma/ufc':
            # K19 guard (2026-09-30): espn_final's events/{eid}/competitions/{eid} shape 404s for
            # MMA (only events/{ceid}/competitions/{fight_id} resolves), and a primary-fetch
            # exception STOPS the grading chain (order guard). MMA grading runs through the record
            # lane's own verified two-source path (tonight's G-20260929-UFC-01); skip here so an
            # MMA pick with a ceid can never halt team-sport grading.
            continue
        try:
            primary = espn_final(p.get('espn_league', 'football/college-football'), eid)
        except Exception as e:
            print(f'{stamp} WARN: primary status fetch failed for {eid}: {e} - chain STOPS (order guard)')
            break
        if not primary:
            continue  # not final yet
        secondary = second_source(p, primary, _parse_ts(g.get('commence', date_label)))
        if not two_source_ok(primary, secondary):
            src = secondary['source'] if secondary else 'none'
            print(f'{stamp} WARN: {pkey} second-source check FAILED (src={src}) - NOT grading (J-115); chain STOPS')
            break  # order guard: later finals wait
        try:
            result, pnl = grade(p, primary)
            score_text(primary)  # the queued score must parse in record_final - checked before any write
            # a push grades to 0 dollars before any size is read; its units still need the private
            # 1u size, so an unset size stops the chain here with the same WARN as a W/L grade
            du = units.pnl_to_units(pnl)
        except ValueError as e:
            print(f'{stamp} WARN: {pkey} {e} - chain STOPS')
            break
        w2, l2 = W + (result == 'W'), L + (result == 'L')
        u2 = U + du
        rec = f'{w2}-{l2}'
        pct = f'{100*w2/(w2+l2):.2f}%' if (w2 + l2) else '0.00%'
        if dry:
            print(f'{stamp} FINAL-CHAIN(dry) {pkey} {g.get("away")}@{g.get("home")} '
                  f'{primary["away_score"]}-{primary["home_score"]} -> {result} {rec} / {u2}u '
                  f'src={secondary["source"]}')
            if requests_out:  # the request a live run would queue, into the preview file only
                _queue_record_request(p, eid, pkey, result, primary, rec, u2, pnl, secondary, stamp,
                                      card_date=m.get('date'), path=requests_out)
        else:
            res = record_pipe.on_final(eid, primary['home_score'], primary['away_score'],
                                       pkey, date_label, rec, pct, str(u2), LEDGER, token,
                                       dry_run=False, no_post=True,
                                       graded_pick=f"{p.get('name', '')} {result}: "
                                                   f"{p.get('game', {}).get('away', 'away')} {primary['away_score']} @ "
                                                   f"{p.get('game', {}).get('home', 'home')} {primary['home_score']} "
                                                   f"({('+' if pnl >= 0 else '')}{units.display_units(units.pnl_to_units(pnl))}u on "
                                                   f"{p.get('units', '?')} @{p.get('odds', '?')}, published-card basis)",
                                       source='finals_watch J-118 live chain')
            if res['chain'] != 'complete':
                # direct POST dead/degraded: ledger row is appended (resumable), so queue
                # the builder-consumed write + relay INSTANTLY, mark unverified, CONTINUE.
                _queue_record_request(p, eid, pkey, result, primary, rec, u2, pnl, secondary, stamp, card_date=m.get('date'))
                seen[pkey] = {'unverified': True, 'relayed_at': stamp, 'result': result, 'record': rec,
                              'post_status': res.get('stages', {}).get('post')}
                os.makedirs(os.path.dirname(STATE), exist_ok=True)
                json.dump(seen, open(STATE, 'w'))
                print(f'{stamp} FINAL-RELAY {pkey} -> {result} {rec} / {u2}u '
                      f'(grade+ledger+record_request done; POST degraded: '
                      f'{res.get("stages", {}).get("post")}; builder write + api verify pending)')
            else:
                seen[pkey] = {'verified_at': stamp, 'result': result, 'record': rec}
                os.makedirs(os.path.dirname(STATE), exist_ok=True)
                json.dump(seen, open(STATE, 'w'))
                print(f'{stamp} FINAL-CHAIN VERIFIED {pkey} -> {result} {rec} / {u2}u')
        W, L, U = w2, l2, u2
        fired.append(pkey)
    if dry:
        print(f'finals_watch: {len(fired)} final(s) [DRY RUN - no production state touched'
              + (f'; would-queue requests in {requests_out}]' if requests_out else ']'))
    elif not fired:
        pass

if __name__ == '__main__':
    main()
