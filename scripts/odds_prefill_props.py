#!/usr/bin/env python3
"""Event-scoped player-props prefill pull from The Odds API (v4).

Usage: odds_prefill_props.py <sport_key> <event_id> [<event_id>...]
  e.g. odds_prefill_props.py americanfootball_nfl a512a48a58c4329048174217b2cc7ce0
       odds_prefill_props.py baseball_mlb <eid1> <eid2>

Endpoint (per event, verified against provider docs):
  GET https://api.the-odds-api.com/v4/sports/{sport}/events/{eventId}/odds
      ?apiKey=...&regions=us&markets=<csv>&oddsFormat=american
One pull per game window, no polling: caller supplies the event ids (from the
free /events listing or a prior /odds response) and runs this once per window.

Markets (verified against the-odds-api.com/sports-odds-data/betting-markets.html):
  NFL (americanfootball_nfl): player_pass_yds, player_pass_tds, player_rush_yds,
      player_reception_yds, player_receptions, player_anytime_td
  MLB (baseball_mlb): batter_home_runs, batter_hits, batter_total_bases,
      pitcher_strikeouts   (MLB prop keys are batter_*/pitcher_*, NOT player_*)

Credit cost (verified): quota charge = [unique markets RETURNED] x [regions].
We request 1 region (us) and N markets, so worst case per event is N credits;
if a market has no data it is not charged. Empty responses cost 0. Budget
guard logs the worst-case request size before the pull.

J-123 budget: every real pull passes core.budget.check_and_log BEFORE the API
call - cap refusal blocks the pull and nothing is fetched. API key comes from
the THE_ODDS_API_KEY environment variable only, read lazily for real pulls.

Writes ONLY slates/odds_prefill_props.json (repo-root-relative; override with
$ODDS_PREFILL_PROPS_OUT for tests). Atomic write via temp + replace.

$ODDS_PREFILL_PROPS_FIXTURE (tests only): canned API response JSON (single
event object); no key read, no budget call, no network.

$ODDS_PROPS_JOBS (default: slates/props_jobs.json next to the repo root):
engine-emitted per-league jobs file {"leagues": {"NFL": {"sport": ...,
"markets": [...]}}}. When present it drives the market set per sport;
when absent the built-in MARKETS_BY_SPORT below is used (self-derive).
Event ids always come from argv (caller derives them from the st pull).
"""
import json, os, re, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root - core/ import

OUT = os.environ.get(
    'ODDS_PREFILL_PROPS_OUT',
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'slates', 'odds_prefill_props.json'))
FIXTURE = os.environ.get('ODDS_PREFILL_PROPS_FIXTURE')

REGIONS = 'us'
MARKETS_BY_SPORT = {
    'americanfootball_nfl': ['player_pass_yds', 'player_pass_tds', 'player_rush_yds',
                             'player_reception_yds', 'player_receptions', 'player_anytime_td'],
    'baseball_mlb': ['batter_home_runs', 'batter_hits', 'batter_total_bases', 'pitcher_strikeouts'],
}
ALL_MARKETS = sorted({m for ms in MARKETS_BY_SPORT.values() for m in ms})

JOBS = os.environ.get(
    'ODDS_PROPS_JOBS',
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'slates', 'props_jobs.json'))
_JOBS_CACHE = 'unset'
def jobs_markets():
    """Engine-emitted jobs file -> {sport_key: markets}; None when absent/unreadable."""
    global _JOBS_CACHE
    if _JOBS_CACHE == 'unset':
        try:
            j = json.load(open(JOBS))
            m = {v['sport']: list(v['markets']) for v in j.get('leagues', {}).values()
                 if v.get('sport') and v.get('markets')}
            _JOBS_CACHE = m or None
        except Exception:
            _JOBS_CACHE = None
    return _JOBS_CACHE

_K = None
def api_key():
    global _K
    if _K is None:
        _K = os.environ.get('THE_ODDS_API_KEY')
        if not _K:
            raise RuntimeError('THE_ODDS_API_KEY env var is not set (props pull requires a real key)')
    return _K

from core.names import norm as norm_player  # single canonical normalizer (core/names.py)

def markets_for(sport):
    jm = jobs_markets()
    if jm is not None:
        return jm.get(sport, [])
    return MARKETS_BY_SPORT.get(sport, ALL_MARKETS)

def fetch_event(sport, event_id):
    """One real pull for one event. Budget-guarded before the request."""
    from core.budget import props_allowed, props_block_reason
    if not props_allowed():
        raise SystemExit(props_block_reason())
    from core import budget
    markets = markets_for(sport)
    if not markets:
        raise SystemExit(f'props jobs file present but lists no markets for {sport} - refusing pull (fail-closed)')
    # worst case = len(markets) credits (1 region); returned-empty markets are not charged
    budget.check_and_log(sport, ','.join(markets), len(markets))
    url = (f"https://api.the-odds-api.com/v4/sports/{sport}/events/{event_id}/odds"
           f"?apiKey={api_key()}&regions={REGIONS}&markets={','.join(markets)}&oddsFormat=american")
    req = urllib.request.Request(url, headers={'User-Agent': 'curl/8'})
    with urllib.request.urlopen(req, timeout=30) as r:
        last = r.headers.get('x-requests-last')
        rem = r.headers.get('x-requests-remaining')
        data = json.load(r)
    print(f"{sport}/{event_id}: credits used {last}, remaining {rem}", file=sys.stderr)
    return data

def parse_event(event):
    """Event odds object -> flat prop rows: one per (player, market, book).
    Over/Under (and Yes/No) prices land in fields named by the outcome name
    ('over'/'under'/'yes'/'no'); 'point' carries the line when present."""
    base = {k: event.get(k) for k in ('id', 'sport_key', 'commence_time', 'home_team', 'away_team')}
    rows = {}
    for b in event.get('bookmakers', []):
        for m in b.get('markets', []):
            for o in m.get('outcomes', []):
                player = o.get('description') or o.get('name')
                pkey = norm_player(player)
                if not pkey:
                    continue
                k = (pkey, m['key'], b['key'])
                row = rows.setdefault(k, {
                    'player': player, 'player_key': pkey, 'market': m['key'], 'book': b['key'],
                    'point': None, 'last_update': m.get('last_update'),
                })
                if o.get('point') is not None:
                    row['point'] = o['point']
                side = (o.get('name') or '').lower()
                if side:
                    row[side] = o.get('price')
    return [dict(base, **row) for row in rows.values()]

def main(argv):
    sport, event_ids = argv[0], argv[1:]
    if not event_ids:
        raise SystemExit('usage: odds_prefill_props.py <sport_key> <event_id> [<event_id>...]')
    props = []
    for eid in event_ids:
        if FIXTURE:
            event = json.load(open(FIXTURE))
        else:
            event = fetch_event(sport, eid)
        if not event:
            print(f"{sport}/{eid}: empty response (0 credits)", file=sys.stderr)
            continue
        rows = parse_event(event)
        for r in rows:
            r['provider_event_id'] = eid
        props.extend(rows)
        print(f"{sport}/{eid}: {len(rows)} prop rows", file=sys.stderr)
    try:
        existing = [r for r in json.load(open(OUT)).get('props', []) if r.get('sport_key') != sport]
    except Exception:
        existing = []
    payload = {'sport_key': sport, 'regions': REGIONS, 'markets': markets_for(sport), 'props': existing + props}
    os.makedirs(os.path.dirname(OUT) or '.', exist_ok=True)
    tmp = OUT + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(payload, f)
    os.replace(tmp, OUT)
    print(f"wrote {OUT} ({len(props)} props from {len(event_ids)} events)")
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
