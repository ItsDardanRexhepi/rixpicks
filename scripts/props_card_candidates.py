#!/usr/bin/env python3
"""PROPS ADAPTER (props-on-card wiring 9/27, his 6:48:03 PM PT 'Include player props too'):
props engine verdict rows (/tmp/props_candidates.json 'rows') -> build_manifest candidates.
ONE FLOOR RULE (parent 6:48 relay): same governing sequence as the rest of the card - floored
first pass (P-EDGE-001 net >= 2c), floorless ONLY on the whole-card empty-slate fallback
(--no-floor here mirrors hunt_v2/st_card_candidates fallback passes).
Conventions: side='over' always (engine prices the over/YES side only); anytime TD normalizes
to line 0.5 over. ESPN identity comes from the engine's evmap (espn_id/match/commence on each
verdict row) - a row missing espn_id skips LOUD, never resolves by name guessing.
Markets: only finals_watch's verified gradeable map cards; anything else skips LOUD.
IN : path to verdict feed (default /tmp/props_candidates.json)
OUT: JSON list of build_manifest candidates."""
import json, sys
from datetime import datetime
from zoneinfo import ZoneInfo

CFG = json.load(open('/home/sandbox/rix_tmp/config_props.json'))['leagues']
# engine market -> gradeable market (finals_watch.PROP_STAT_KEYS + specials; keep in sync)
MARKET_MAP = {
    'player_pass_yds': 'passing_yards', 'player_pass_tds': 'pass_td',
    'player_rush_yds': 'rushing_yards', 'player_rush_attempts': 'rush_attempts',
    'player_reception_yds': 'receiving_yards', 'player_receptions': 'receptions',
    'player_reception_tds': 'reception_tds', 'player_rush_tds': 'rush_tds',
    'player_anytime_td': 'anytime_td',
    'player_points': 'points', 'player_rebounds': 'rebounds', 'player_assists': 'assists',
    'player_threes': 'threes',
    'player_goals': 'goals', 'player_shots_on_goal': 'shots_on_goal',
    'player_total_saves': 'saves', 'player_blocked_shots': 'blocked_shots',
    # MLB + soccer grading shipped 9/27 (his 6:54:23 PM PT). NOT mapped (ESPN boxscore has no
    # source -> loud skip): batter_total_bases (no 2B/3B keys), batter_stolen_bases (no SB key),
    # pitcher_record_a_win (no decision field), player_shots_on_target (no player tables).
    'batter_hits': 'bat_hits', 'batter_home_runs': 'bat_home_runs', 'batter_rbis': 'bat_rbis',
    'batter_runs_scored': 'bat_runs', 'batter_walks': 'bat_walks',
    'batter_strikeouts': 'bat_strikeouts', 'pitcher_strikeouts': 'pit_strikeouts',
    'pitcher_hits_allowed': 'pit_hits_allowed', 'pitcher_walks': 'pit_walks',
    'pitcher_outs': 'pit_outs', 'pitcher_earned_runs': 'pit_earned_runs',
    'player_goal_scorer_anytime': 'anytime_goal', 'player_goal_scorer_first': 'first_goal',
    'player_goal_scorer_last': 'last_goal'}
LABEL = {'passing_yards': 'passing yards', 'pass_td': 'passing TDs', 'rushing_yards': 'rushing yards',
         'rush_attempts': 'rush attempts', 'receiving_yards': 'receiving yards', 'receptions': 'receptions',
         'reception_tds': 'receiving TDs', 'rush_tds': 'rushing TDs', 'points': 'points',
         'rebounds': 'rebounds', 'assists': 'assists', 'threes': 'threes', 'goals': 'goals',
         'shots_on_goal': 'shots on goal', 'saves': 'saves', 'blocked_shots': 'blocked shots',
         'bat_hits': 'hits', 'bat_home_runs': 'home runs', 'bat_rbis': 'RBIs', 'bat_runs': 'runs',
         'bat_walks': 'walks', 'bat_strikeouts': 'strikeouts', 'pit_strikeouts': 'strikeouts',
         'pit_hits_allowed': 'hits allowed', 'pit_walks': 'walks allowed', 'pit_outs': 'outs',
         'pit_earned_runs': 'earned runs'}

def tier_eval(fair_c, gross_c):
    # J-096 ladder, same as ML/s-t
    if fair_c >= 90: return 100
    if 80 <= fair_c < 90: return 15
    if 70 <= fair_c < 80: return 10 if gross_c >= 3 else 5
    if 60 <= fair_c < 70: return 5
    return 0

def adapt(row, floor=True, now=None):
    now = now or datetime.now(ZoneInfo('UTC'))
    if row.get('net_c') is None: return None
    if floor and row['net_c'] < 2: return None
    market = MARKET_MAP.get(row.get('market'))
    if not market:
        print(f"SKIP (fail closed): ungradeable market {row.get('market')!r} for {row.get('player')}", file=sys.stderr)
        return None
    if not row.get('espn_id'):
        print(f"SKIP (fail closed): no ESPN id for {row.get('player')} {row.get('market')}", file=sys.stderr)
        return None
    lg = CFG.get(row.get('league') or '', {})
    if not lg.get('espn'):
        print(f"SKIP (fail closed): no ESPN league path for {row.get('league')!r}", file=sys.stderr)
        return None
    fair_c = row['fair_over_c']
    units = tier_eval(fair_c, row['gross_c'] if row.get('gross_c') is not None else row['net_c'])
    if units == 0: return None  # below J-096 card band
    SPECIAL_NAME = {'anytime_td': 'anytime TD', 'anytime_goal': 'anytime goal',
                    'first_goal': '1st goal', 'last_goal': 'last goal'}
    if market in SPECIAL_NAME:
        line = 0.5
        name = f"{row['player']} {SPECIAL_NAME[market]}"
        sub = f"{row.get('match')} - {SPECIAL_NAME[market]} - {row['n_books']} books"
    else:
        line = row.get('line')
        if line is None:
            print(f"SKIP (fail closed): no consensus line for {row.get('player')} {market}", file=sys.stderr)
            return None
        name = f"{row['player']} over {line:g} {LABEL.get(market, market)}"
        sub = f"{row.get('match')} - over {line:g} {LABEL.get(market, market)} - {row['n_books']} books"
    try:
        away, home = (row.get('match') or ' @ ').split(' @ ', 1)
    except ValueError:
        print(f"SKIP (fail closed): unparseable match {row.get('match')!r}", file=sys.stderr)
        return None
    # PRE-GAME ONLY (his 9/27 6:54:23 PM PT: no live/in-play props on the daily card; fail
    # closed on ambiguous commence state - parent relay 6:54:38)
    c_raw = row.get('commence')
    try:
        commence = datetime.fromisoformat(c_raw.replace('Z', '+00:00')) if c_raw else None
    except (ValueError, AttributeError):
        commence = None
    if commence is None:
        print(f"SKIP (fail closed): no/ambiguous commence for {row.get('player')} {row.get('market')}",
              file=sys.stderr)
        return None
    if now >= commence:
        print(f"SKIP (pre-game only): already started {row.get('player')} {row.get('market')} ({row.get('match')})",
              file=sys.stderr)
        return None
    k = row['kalshi']
    return {'date': commence.astimezone(ZoneInfo('America/Los_Angeles')).strftime('%Y-%m-%d'),
            'market_class': 'prop', 'name': name, 'side': 'over', 'line': line,
            'player': row['player'], 'market': market,
            'away': away, 'home': home, 'commence': row['commence'],
            'eid': str(row['espn_id']), 'espn_league': lg['espn'],
            'units': f'{units}u', 'model': fair_c,
            'gross_c': row.get('gross_c'), 'net_c': row['net_c'],
            'sub_context': sub + (' [WIDE-BOOK]' if k.get('tag') == 'WIDE-BOOK' else ''),
            'kalshi': {'cents': round(k['ask'] * 100), 'team': row['player'], 'ticker': k['ticker'],
                       'contract_side': 'yes'}}

def main():
    rows = json.load(open(sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--')
                         else '/tmp/props_candidates.json'))['rows']
    floor = '--no-floor' not in sys.argv
    now = None
    for a in sys.argv[1:]:
        if a.startswith('--now='):
            now = datetime.fromisoformat(a[6:])
            if now.tzinfo is None: now = now.replace(tzinfo=ZoneInfo('America/Los_Angeles'))
    out = [c for r in rows if (c := adapt(r, floor=floor, now=now))]
    print(json.dumps(out, indent=1))

if __name__ == '__main__': main()
