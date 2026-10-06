#!/usr/bin/env python3
"""J-118 TRIGGER (production, DRY-RUN until swamp certification + parent's word):
detect FINALs on today's card, grade in commence order with running cumulative
record/units from the canonical ledger, fire the instant record chain.
Guards (swamp 9:23-9:25 PM):
- cumulative state = LAST ledger row (record_pipe.current_state); empty ledger REFUSES.
- in-order processing: the chain STOPS at the first ungraded/unverified final so the
  public record can never regress or skip; later finals wait for the next fire.
- two-source final verification (J-115) BEFORE grading: CBS scoreboard (independent),
  ESPN site API as fallback only (same company as ESPN core - weaker independence,
  source label says so). Stable team-ID mapping + ORDERED (away, home) scores.
- tie = PUSH: 0 pnl, no W/L - except soccer, which grades on regulation time as Kalshi settles
  (core/soccer_result.py): a draw after 90 minutes is LOST for either side's moneyline, and
  totals/spreads count regulation goals only (never extra time or a shootout).
- seen[pick_key] written ONLY on a verified chain; dry-run touches NO production state.
Usage: finals_watch.py [--dry-run]"""
import json, os, re, sys, unicodedata, urllib.request
sys.path.insert(0, '/home/sandbox/rix_tmp')
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from core import record_pipe, units, budget, fill_leak, soccer_result
from core.accepted_entry import accepted_entry, entry_delta
HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, '..', 'manifest.json')
STATE = '/home/sandbox/rps_tmp/kb/ledger/finals_seen.json'
LEDGER = '/home/sandbox/rps_tmp/kb/ledger/record_rows.jsonl'
TOKEN_PATH = ('/home/sandbox/.push_token' if os.path.exists('/home/sandbox/.push_token') else '/tmp/.push_token')

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
            'basketball/nba': 'nba', 'basketball/ncaab': 'college-basketball', 'basketball/wnba': 'wnba',
            'baseball/mlb': 'mlb', 'hockey/nhl': 'nhl', 'soccer/usa.1': 'mls'}
SITE_LEAGUE = {'basketball/ncaab': 'basketball/mens-college-basketball'}

def _norm(s):
    return re.sub(r'[^a-z]', '', (s or '').lower())

def cbs_final(pick, primary, commence):
    """Second source #1: CBS scoreboard (independent company). Strict parse only:
    both normalized team names adjacent in document order (away first, home second)
    each followed by an integer score. Returns ordered dict or None."""
    slug = CBS_SLUG.get(pick.get('espn_league', 'football/college-football'))
    if slug is None:
        return None
    try:
        url = f"https://www.cbssports.com/{slug}/scoreboard/{commence.strftime('%Y%m%d')}/"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8', 'ignore')
    except Exception:
        return None
    hn, an = _norm(primary['home']), _norm(primary['away'])
    pairs = [(_norm(t), int(s)) for t, s in
             re.findall(r"(?is)([A-Za-z.''& ]{2,30})\s*(\d{1,3})\s*<", html)]
    for i in range(len(pairs) - 1):
        (t1, s1), (t2, s2) = pairs[i], pairs[i + 1]
        if t1 == an and t2 == hn:
            return {'source': 'cbs', 'away_id': primary['away'], 'home_id': primary['home'],
                    'away_score': s1, 'home_score': s2}
    return None


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
    league = SITE_LEAGUE.get(league, league)
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
                  'basketball/ncaab': 'basketball_ncaab', 'basketball/wnba': 'basketball_wnba', 'baseball/mlb': 'baseball_mlb',
                  'hockey/nhl': 'icehockey_nhl', 'soccer/usa.1': 'soccer_usa_mls'}
ODDS_KEY_PATH = '/home/sandbox/.odds_api_key'
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
        try:
            budget.check_and_log(sport, 'scores', 1)
        except ValueError as e:
            print(f'WARN: odds-api scores pull blocked by budget: {e}')
            _odds_cache[ckey] = None
            return None
        try:
            key = open(ODDS_KEY_PATH).read().strip()
            url = f'https://api.the-odds-api.com/v4/sports/{sport}/scores/?apiKey={key}&daysFrom=2'
            _odds_cache[ckey] = _get(url, timeout=12)
        except Exception as e:
            print(f'WARN: odds-api scores fetch failed: {e}')
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
    """Second source: official MLB statsapi (free, no key). Schedule by date,
    match both team names, require abstractGameState Final."""
    if pick.get('espn_league') != 'baseball/mlb':
        return None
    try:
        d = _get(f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={commence.strftime('%Y-%m-%d')}&hydrate=linescore")
        away_last = primary['away'].split()[-1].lower()
        home_last = primary['home'].split()[-1].lower()
        for day in d.get('dates', []):
            for g in day.get('games', []):
                an = g['teams']['away']['team'].get('name','').lower()
                hn = g['teams']['home']['team'].get('name','').lower()
                if away_last in an and home_last in hn:
                    if g.get('status',{}).get('abstractGameState') != 'Final':
                        return None
                    return {'source': 'mlb-statsapi (official)',
                            'away_id': primary['away'], 'home_id': primary['home'],
                            'away_score': g['teams']['away'].get('score'),
                            'home_score': g['teams']['home'].get('score')}
    except Exception as e:
        print(f'WARN: mlb statsapi fetch failed: {e}')
    return None

def second_source(pick, primary, commence):
    """CBS -> ESPN site -> repo nfl_scores (the-odds-api, GHA-side) -> direct odds-api (needs local key)."""
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
    card_c, card_row, n_card = fill_leak.card_price(pick)
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
    for dv in fill_leak.fill_divergence(pick):
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


def _queue_record_request(p, eid, pkey, result, primary, rec, u2, pnl, secondary, stamp, card_date=None):
    """Append the builder-consumed record write request (same cycle as the grade).
    This + the instant parent relay is the write path while the direct POST token is dead."""
    path = os.path.join(HERE, '..', 'record_request.json')
    try: d = json.load(open(path))
    except Exception: d = {'requests': []}
    if any(r.get('grade_id') == pkey for r in d.get('requests', [])):
        return False
    g = p.get('game', {})
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
        'graded_pick': (f"{p.get('name','')} {({'W': 'W', 'L': 'L', 'PUSH': 'P'})[result]}: "
                        f"{g.get('away','away')} {primary['away_score']} @ {g.get('home','home')} {primary['home_score']} "
                        f"(published-card basis)"),
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

def main():
    dry = '--dry-run' in sys.argv
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
    token = open(TOKEN_PATH).read().strip() if os.path.exists(TOKEN_PATH) else ''
    date_label = m.get('date_label', '')
    if not dry:
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
        print(f'finals_watch: {len(fired)} final(s) [DRY RUN - no production state touched]')
    elif not fired:
        pass

if __name__ == '__main__':
    main()
