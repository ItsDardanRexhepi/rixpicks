#!/usr/bin/env python3
"""Player-props FAIR MODEL (props pipeline step 2, mirrors st_fair.py) - canonical schema:
consumes the GHA-side odds_prefill_props payload {sport_key, markets, props[]} (Julian-side
producer, accepted 16:14). Rows: player/player_key/market/book/point + over/under OR yes/no
(anytime_td is yes/no, no line). MLB keys are batter_*/pitcher_* per provider docs.
Per player+market: consensus line (median), two-way devig at each book's own line, fair =
median devigged prob among books at consensus line (WIDENED flag if <2), Kalshi player-prop
anchor (core.names normalized both sides), P-EDGE-001 net.
IN : slates URL or /tmp/odds_prefill_props.json (env PROPS_IN)   OUT: JSON rows to stdout."""
import json, os, re, sys, urllib.request
from statistics import median
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.names import norm
KALSHI_PROP_SERIES = {
 'americanfootball_nfl': {'player_pass_yds':'KXNFLPASSYDS','player_pass_tds':'KXNFLPASSTDS',
   'player_rush_yds':'KXNFLRSHYDS','player_reception_yds':'KXNFLRECYDS','player_receptions':'KXNFLREC',
   'player_anytime_td':'KXNFLTD'},
 'baseball_mlb': {'batter_home_runs':'KXMLBHR','batter_hits':'KXMLBHIT',
   'batter_total_bases':'KXMLBTB','pitcher_strikeouts':'KXMLBKS'},
 'basketball_nba': {'player_points':'KXNBAPTS','player_rebounds':'KXNBAREB',
   'player_assists':'KXNBAAST','player_threes':'KXNBA3PT'},
 'basketball_wnba': {'player_points':'KXWNBAPTS','player_rebounds':'KXWNBAREB',
   'player_assists':'KXWNBAAST','player_threes':'KXWNBA3PT'},
 'icehockey_nhl': {'player_goals':'KXNHLANYGOAL','player_points':'KXNHLPTS',
   'player_total_saves':'KXNHLSAVES'},
 'soccer_usa_mls': {'player_goal_scorer_anytime':'KXMLSGOAL'},
}
PROPS_URL = 'https://raw.githubusercontent.com/ItsDardanRexhepi/rixpicks/main/slates/odds_prefill_props.json'
def fee(ask): return 0.07 * ask * (1 - ask)
def a2p(a): return -a/(-a+100) if a < 0 else 100/(a+100)
def load_rows():
    p = os.environ.get('PROPS_IN', '/tmp/odds_prefill_props.json')
    if os.path.exists(p): d = json.load(open(p))
    else:
        try:
            with urllib.request.urlopen(PROPS_URL, timeout=20) as r: d = json.load(r)
        except Exception as e:
            raise SystemExit(f'FAIL: props prefill unavailable ({p} missing; repo URL: {e}) - no silent skip')
    if isinstance(d, dict): return d.get('props', [])
    return d  # tolerate legacy flat-list fixtures
def kalshi_markets(series):
    out, cursor = [], None
    try:
        for _ in range(6):  # up to 6000 markets
            url = f'https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker={series}&limit=1000'
            if cursor: url += f'&cursor={cursor}'
            with urllib.request.urlopen(url, timeout=15) as r:
                d = json.load(r)
            out += d.get('markets', [])
            cursor = d.get('cursor')
            if not cursor: break
        return out
    except Exception as e:
        print(f'KALSHI-ERR {series}: {e}', file=sys.stderr); return out
_obcache = {}
def kalshi_ask_bid(ticker):
    """(ask_dollars, bid_dollars) via orderbook top-of-book; None,null on failure."""
    if ticker in _obcache: return _obcache[ticker]
    try:
        with urllib.request.urlopen(f'https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}/orderbook', timeout=15) as r:
            ob = json.load(r).get('orderbook', {})
        yes_bids = [float(p)/100.0 for p, _ in (ob.get('yes_dollars') or ob.get('yes') or [])]
        no_bids = [float(p)/100.0 for p, _ in (ob.get('no_dollars') or ob.get('no') or [])]
        ask = (1.0 - max(no_bids)) if no_bids else None
        bid = max(yes_bids) if yes_bids else None
        _obcache[ticker] = (ask, bid)
    except Exception:
        _obcache[ticker] = (None, None)
    return _obcache[ticker]

def calibrate_margins(rows):
    # MODELED-FAIR margin model for yes-only markets (anytime_td): books return yes-only at all
    # 8 books (verified 17:08), so no measured devig exists. Calibrate each book's prop overround
    # from its two-sided prop rows in the SAME feed; assumed margin = that book's p90 (conservative
    # high quantile). Book needs >=MIN_CAL two-sided pairs else its yes-only rows are excluded
    # (fail-closed). Whole model fails loud if the feed carries <MIN_CAL_TOTAL pairs.
    pairs = {}
    for r in rows:
        if r.get('over') is None or r.get('under') is None: continue
        pairs.setdefault(r['book'], []).append(a2p(r['over']) + a2p(r['under']) - 1)
    total = sum(len(v) for v in pairs.values())
    if total < 30: raise SystemExit(f'FAIL: only {total} two-sided calibration pairs - margin model cannot run, no silent skip')
    cal = {}
    for b, v in pairs.items():
        if len(v) < 10: continue
        v = sorted(v); cal[b] = v[min(len(v)-1, int(0.9*len(v)))]
    return cal

def main():
    rows = load_rows()
    if not rows: raise SystemExit('FAIL: empty props prefill - no silent skip')
    margin_cal = calibrate_margins(rows)
    groups = {}
    for r in rows:
        sport = r.get('sport_key') or r.get('sport')
        groups.setdefault((r.get('provider_event_id') or r.get('event_id'), sport,
                           r['market'], r['player']), []).append(r)
    out = []; kcache = {}
    for (ev, sport, mkt, player), obs in groups.items():
        yn = all(o.get('point') is None for o in obs)  # yes/no market (anytime_td)
        modeled = False
        if yn:
            both = [o for o in obs if o.get('yes') and o.get('no')]
            if len(both) >= 2: obs = both
            else:
                # yes-only at every book -> MODELED-FAIR: fair_yes = implied_yes/(1+m_book_p90).
                # Needs >=3 calibrated books (divergence kill still applies downstream).
                obs = [o for o in obs if o.get('yes') and o.get('book') in margin_cal]
                modeled = True
        else: obs = [o for o in obs if o.get('point') is not None and o.get('over') and o.get('under')]
        min_books = 3 if modeled else 2
        if len(obs) < min_books:
            out.append({'player': player, 'market': mkt, 'event_id': ev, 'confidence': 'LOW',
                        'n_books': len(obs), 'note': f'fewer than {min_books} books - skipped'}); continue
        if yn:
            cons = None; pool = obs; conf = 'OK'
            if modeled:
                fa = [a2p(o['yes'])/(1+margin_cal[o['book']]) for o in pool]
            else:
                fa = [a2p(o['yes'])/(a2p(o['yes'])+a2p(o['no'])) for o in pool]
        else:
            cons = median(o['point'] for o in obs)
            at = [o for o in obs if abs(o['point']-cons) <= 0.5]
            pool = at if len(at) >= 2 else obs; conf = 'OK' if len(at) >= 2 else 'WIDENED'
            fa = [a2p(o['over'])/(a2p(o['over'])+a2p(o['under'])) for o in pool]
        fair = median(fa)
        row = {'player': player, 'market': mkt, 'event_id': ev, 'sport': sport,
               'consensus_line': cons, 'fair_over_c': round(fair*100, 1), 'n_books': len(pool),
               'confidence': conf, 'side': 'yes' if yn else 'over',
               'book_fairs_c': [round(x*100, 1) for x in fa]}
        if modeled:
            row['basis'] = 'MODELED_FAIR'
            row['margin_model'] = {'assumed_overround_p90': {o['book']: round(margin_cal[o['book']],4) for o in pool}}
        series = KALSHI_PROP_SERIES.get(sport or '', {}).get(mkt)
        if series:
            if series not in kcache: kcache[series] = kalshi_markets(series)
            np_ = norm(player)
            for m in kcache[series]:
                if m.get('status') != 'active': continue  # never bind finalized/inactive markets
                t = m.get('title', '')
                if np_ not in norm(t): continue
                if yn:
                    # anytime = the '1+ <stat>' rung of the ladder (books' anytime_td == 1+).
                    mr = re.search(r'(\d+(?:\.\d+)?)\+', t)
                    if mr and abs(float(mr.group(1)) - 1.0) > 0.01: continue
                if not yn:
                    # Kalshi ladder rungs read 'N+ <stat>' = book over (N-0.5). Match the rung
                    # whose implied line equals the book consensus (rung N == cons+0.5).
                    mt = re.search(r'(\d+(?:\.\d+)?)\+', t)
                    if not mt or abs(float(mt.group(1)) - (cons + 0.5)) > 0.6: continue
                ask = m.get('yes_ask_dollars')
                bid = m.get('yes_bid_dollars')
                if ask is None:
                    ask, bid = kalshi_ask_bid(m['ticker'])  # null quote fields unauthenticated
                if ask is None: continue
                ask = float(ask)
                row['kalshi'] = {'ticker': m['ticker'], 'ask': ask, 'bid': bid}
                try:
                    if abs(float(m['yes_ask_dollars']) - float(m['yes_bid_dollars'])) > 0.05:
                        row['kalshi']['tag'] = 'WIDE-BOOK'
                except (TypeError, ValueError): pass
                row['gross_c'] = round((fair-ask)*100, 1)
                row['fee_c'] = round(fee(ask)*100, 1)
                row['net_c'] = round(row['gross_c']-row['fee_c'], 1)
                break
        out.append(row)
    print(json.dumps(out, indent=1))
if __name__ == '__main__': main()
