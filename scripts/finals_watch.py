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
- tie = PUSH: 0 pnl, no W/L.
- seen[pick_key] written ONLY on a verified chain; dry-run touches NO production state.
Usage: finals_watch.py [--dry-run]"""
import json, os, re, sys, urllib.request
sys.path.insert(0, '/home/sandbox/rix_tmp')
from datetime import datetime
from decimal import Decimal
from core import record_pipe, units, budget
HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, '..', 'manifest.json')
STATE = '/home/sandbox/rps_tmp/kb/ledger/finals_seen.json'
LEDGER = '/home/sandbox/rps_tmp/kb/ledger/record_rows.jsonl'
TOKEN_PATH = '/tmp/.push_token'

def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
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
    for x in c.get('competitors', []):
        s2 = _deref(x.get('score', {}))
        v = s2.get('value') if isinstance(s2, dict) else None
        sc[x.get('homeAway')] = int(float(v)) if v is not None else None
        team = _deref(x.get('team', {}))
        names[x.get('homeAway')] = team.get('displayName') or team.get('name') or ''
    if sc.get('home') is None or sc.get('away') is None:
        return None
    return {'home': names.get('home', ''), 'away': names.get('away', ''),
            'home_score': sc['home'], 'away_score': sc['away']}

CBS_SLUG = {'football/college-football': 'college-football', 'football/nfl': 'nfl',
            'basketball/nba': 'nba', 'basketball/ncaab': 'college-basketball',
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
        data = _get(url, timeout=10)
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
                  'basketball/ncaab': 'basketball_ncaab', 'baseball/mlb': 'baseball_mlb',
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

def second_source(pick, primary, commence):
    """Parent's order: CBS (independent) -> ESPN site (fallback, weaker independence).
    Both are unreachable from this sandbox (CBS JS-only/no JSON endpoint; ESPN site API
    403s this IP), so the-odds-api scores is the third leg that actually fires today."""
    return (cbs_final(pick, primary, commence)
            or espn_site_final(pick, primary, commence)
            or odds_api_final(pick, primary, commence))

def two_source_ok(primary, secondary):
    """J-115: SAME team identities AND same ORDERED (away, home) scores. Reversed
    score pairs do NOT pass (swamp 9:25)."""
    return (secondary is not None
            and secondary.get('home_id') == primary.get('home')
            and secondary.get('away_id') == primary.get('away')
            and secondary.get('home_score') == primary.get('home_score')
            and secondary.get('away_score') == primary.get('away_score'))

def grade(pick, primary):
    if primary['home_score'] == primary['away_score']:
        return 'PUSH', Decimal('0')
    won = (pick['side'] == 'home') == (primary['home_score'] > primary['away_score'])
    cents = (pick.get('kalshi') or {}).get('cents')
    u = Decimal(str(pick.get('units', '0u')).rstrip('u'))
    if not cents or not u:
        raise ValueError('missing price/units in manifest - grade manually')
    stake = u * Decimal(15)  # exact from the first multiplication
    return ('W' if won else 'L'), (units.stake_pnl(stake, cents) if won else -stake)

def _parse_ts(s):
    return datetime.fromisoformat(str(s).replace('Z', '+00:00'))

def load_seen():
    try: return json.load(open(STATE))
    except Exception: return {}

def main():
    dry = '--dry-run' in sys.argv
    m = json.load(open(MANIFEST))
    seen = load_seen()
    stamp = datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')
    token = open(TOKEN_PATH).read().strip() if os.path.exists(TOKEN_PATH) else ''
    date_label = m.get('date_label', '')
    if not dry:
        # swamp 9:28: resume unfinished pending grades (appended, POST/GET not verified)
        # with their EXACT saved rows BEFORE any successor is graded or state is read.
        resumed = record_pipe.resume_pending(LEDGER, token)
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
        pkey = f"{eid}|ml|{p['side']}"  # extend when spread/total picks card
        if pkey in seen:
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
        except ValueError as e:
            print(f'{stamp} WARN: {pkey} {e} - chain STOPS')
            break
        w2, l2 = W + (result == 'W'), L + (result == 'L')
        u2 = U + units.pnl_to_units(pnl)
        rec = f'{w2}-{l2}'
        pct = f'{100*w2/(w2+l2):.2f}%' if (w2 + l2) else '0.00%'
        if dry:
            print(f'{stamp} FINAL-CHAIN(dry) {pkey} {g.get("away")}@{g.get("home")} '
                  f'{primary["away_score"]}-{primary["home_score"]} -> {result} {rec} / {u2}u '
                  f'src={secondary["source"]}')
        else:
            res = record_pipe.on_final(eid, primary['home_score'], primary['away_score'],
                                       pkey, date_label, rec, pct, str(u2), LEDGER, token,
                                       dry_run=False)
            if res['chain'] != 'complete':
                print(f'{stamp} WARN: {pkey} chain {res["chain"]} - NOT marked seen; chain STOPS, retry next fire')
                break
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
