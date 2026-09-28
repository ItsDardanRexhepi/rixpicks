#!/usr/bin/env python3
"""s/t FAIR MODEL (pipeline step 1, parent 16:05:56 assignment).
Devigged multi-book consensus fair for spread/total + Kalshi s/t anchor (P-EDGE-001 net).
IN : st prefill JSON (books carry spread_home_pts/spread_home_price/spread_away_price/
     total_pts/over_price/under_price). Path env ST_IN, default /tmp/odds_prefill_st.json,
     fallback repo URL once builder ships the GHA-side s/t pull.
OUT: JSONL rows: game, cls, side, consensus_line, fair_c, n_books, confidence,
     kalshi {ticker, ask, bid}, gross_c, fee_c, net_c. FAIL-LOUD on missing/bad input."""
import json, os, re, sys, urllib.request
from statistics import median

ST_URL = 'https://raw.githubusercontent.com/ItsDardanRexhepi/rixpicks/main/slates/odds_prefill_st.json'
KALSHI_SERIES = {
    'nfl':  {'spread': 'KXNFLSPREAD',  'total': 'KXNFLTOTAL'},
    'mlb':  {'spread': 'KXMLBSPREAD',  'total': 'KXMLBTOTAL'},
    'nba':  {'spread': 'KXNBASPREAD',  'total': 'KXNBATOTAL'},
    'wnba': {'spread': 'KXWNBASPREAD', 'total': 'KXWNBATOTAL'},
}
TEAM_ABBR = {  # full name -> Kalshi ticker abbr (extend fail-loud on miss)
 'Arizona Cardinals':'ARI','Atlanta Falcons':'ATL','Baltimore Ravens':'BAL','Buffalo Bills':'BUF',
 'Carolina Panthers':'CAR','Chicago Bears':'CHI','Cincinnati Bengals':'CIN','Cleveland Browns':'CLE',
 'Dallas Cowboys':'DAL','Denver Broncos':'DEN','Detroit Lions':'DET','Green Bay Packers':'GB',
 'Houston Texans':'HOU','Indianapolis Colts':'IND','Jacksonville Jaguars':'JAX','Kansas City Chiefs':'KC',
 'Las Vegas Raiders':'LV','Los Angeles Chargers':'LAC','Los Angeles Rams':'LAR','Miami Dolphins':'MIA',
 'Minnesota Vikings':'MIN','New England Patriots':'NE','New Orleans Saints':'NO','New York Giants':'NYG',
 'New York Jets':'NYJ','Philadelphia Eagles':'PHI','Pittsburgh Steelers':'PIT','San Francisco 49ers':'SF',
 'Seattle Seahawks':'SEA','Tampa Bay Buccaneers':'TB','Tennessee Titans':'TEN','Washington Commanders':'WAS',
}
def fee(ask): return 0.07 * ask * (1 - ask)
def a2p(a): return -a/(-a+100) if a < 0 else 100/(a+100)
def devig(home_a, away_a):
    ph, pa = a2p(home_a), a2p(away_a); s = ph + pa
    return ph/s, pa/s
def kalshi_markets(series):
    url = f'https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker={series}&limit=500'
    try:
        with urllib.request.urlopen(url, timeout=15) as r: return json.load(r).get('markets', [])
    except Exception as e:
        print(f'KALSHI-ERR {series}: {e}', file=sys.stderr); return []
def load_prefill():
    p = os.environ.get('ST_IN', '/tmp/odds_prefill_st.json')
    if os.path.exists(p):
        return json.load(open(p))
    try:
        with urllib.request.urlopen(ST_URL, timeout=20) as r: return json.load(r)
    except Exception as e:
        raise SystemExit(f'FAIL: st prefill unavailable (local {p} missing; {ST_URL}: {e}). '
                         's/t pull is GHA-side pending builder ship - no silent skip.')
def consensus_fair(games, cls):
    """Per game: consensus line (median) + devigged fair at consensus-line books.
    IN-GAME EXCLUSION: in-window refreshes carry live lines (verified 16:11 on ARI@SF:
    3 books, 3 different spreads mid-game). Fair requires PRE-GAME snapshots - skip
    commenced games loudly."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    rows = []
    for g in games:
        c = g.get('commence')
        if c:
            try:
                if datetime.fromisoformat(c.replace('Z', '+00:00')) < now:
                    rows.append({'match': f"{g.get('away')} @ {g.get('home')}", 'cls': cls,
                                 'confidence': 'IN_GAME', 'note': 'commenced - live lines excluded; needs pregame snapshot'})
                    continue
            except ValueError: pass
        books = g.get('books') or {}
        if cls == 'spread':
            obs = [(b['spread_home_pts'], b['spread_home_price'], b['spread_away_price'])
                   for b in books.values() if all(k in b for k in
                   ('spread_home_pts','spread_home_price','spread_away_price'))]
        else:
            obs = [(b['total_pts'], b['over_price'], b['under_price'])
                   for b in books.values() if all(k in b for k in
                   ('total_pts','over_price','under_price'))]
        if len(obs) < 2:
            rows.append({'match': f"{g.get('away')} @ {g.get('home')}", 'cls': cls,
                         'confidence': 'LOW', 'n_books': len(obs), 'note': 'fewer than 2 books - skipped'})
            continue
        lines = [o[0] for o in obs]; cons = median(lines)
        at = [o for o in obs if abs(o[0]-cons) <= 0.5]
        pool = at if len(at) >= 2 else obs  # widen only if consensus-line pool too thin (flag below)
        fa = [devig(o[1], o[2])[0] for o in pool]
        fair_home_or_over = median(fa)
        rows.append({'match': f"{g.get('away')} @ {g.get('home')}", 'away': g.get('away'),
                     'home': g.get('home'), 'sport': g.get('sport') or ('nfl' if g.get('away') in TEAM_ABBR and g.get('home') in TEAM_ABBR else 'unknown'), 'commence': g.get('commence'),
                     'cls': cls, 'consensus_line': cons, 'fair_home_or_over_c': round(fair_home_or_over*100, 1),
                     'n_books': len(pool), 'confidence': 'OK' if len(at) >= 2 else 'WIDENED'})
    return rows
def anchor_kalshi(row):
    """Find the Kalshi s/t market at the consensus line for home-cover (spread) or over (total)."""
    series = KALSHI_SERIES.get((row.get('sport') or '').lower(), {}).get(row['cls'])
    if not series: return row
    abbr_a, abbr_h = TEAM_ABBR.get(row.get('away')), TEAM_ABBR.get(row.get('home'))
    if not abbr_a or not abbr_h:
        row['kalshi'] = {'error': f"unmapped team abbr ({row.get('away')}/{row.get('home')})"}; return row
    cons = row['consensus_line']
    # SIDE-AWARE binding (16:12 fix): odds-api convention spread_home_pts > 0 = home GETS
    # points (underdog), < 0 = home favored. Kalshi spread markets are always quoted as
    # "X wins by over Y". Home-favored: match HOME-abbr market YES ask. Home-underdog:
    # home-cover = NO on "AWAY wins by over cons" -> no_ask = 1 - yes_bid.
    if cons == 0:
        row['kalshi'] = {'error': "pick'em line - spread anchor skipped (use ML class)"}; return row
    fav_abbr = abbr_h if cons < 0 else abbr_a
    best = None
    for m in kalshi_markets(series):
        ev = m.get('event_ticker', '')
        if abbr_a not in ev or abbr_h not in ev: continue
        t = m.get('title', '')
        if row['cls'] == 'total':
            mt = re.search(r'[Oo]ver ([\d.]+) (points|runs) scored', t)
            if not mt or abs(float(mt.group(1)) - cons) > 0.6: continue
            ask = m.get('yes_ask_dollars'); side = 'yes'
        else:
            mt = re.match(r'(\w+) .*wins by over ([\d.]+) points', t)
            if not mt or mt.group(1) != fav_abbr: continue
            if abs(float(mt.group(2)) - abs(cons)) > 0.6: continue
            if cons < 0:
                ask = m.get('yes_ask_dollars'); side = 'yes'
            else:
                bid = m.get('yes_bid_dollars')
                ask = (1 - float(bid)) if bid is not None else None; side = 'no'
        if ask is None: continue
        ask = float(ask)
        best = {'ticker': m['ticker'], 'side': side, 'ask': ask,
                'yes_bid': m.get('yes_bid_dollars'), 'yes_ask': m.get('yes_ask_dollars')}
        try:
            if abs(float(m['yes_ask_dollars']) - float(m['yes_bid_dollars'])) > 0.05:
                best['tag'] = 'WIDE-BOOK'
        except (TypeError, ValueError): pass
        # OPPOSITE SIDE (his 6:45:32 PM PT iMessage 9/27: 'Have it price away-cover and under'):
        # same contract, other direction. spread: home-cover YES <=> away-cover NO (and the
        # reverse when away is favored). total: over YES <=> under NO. Alt ask = 1 - yes_bid
        # for the NO side; devigged two-way fairs sum to 1, so alt fair = 1 - primary fair.
        alt = None
        try:
            yb = m.get('yes_bid_dollars'); ya = m.get('yes_ask_dollars')
            if yb is not None and ya is not None:
                if row['cls'] == 'total':
                    a_side, a_ask = 'no', 1 - float(yb)          # under = NO on the over contract
                elif cons < 0:
                    a_side, a_ask = 'no', 1 - float(yb)          # away-cover = NO on 'HOME wins by over Y'
                else:
                    a_side, a_ask = 'yes', float(ya)             # away-cover = YES on 'AWAY wins by over Y'
                alt = {'side': a_side, 'ask': a_ask}
                if best.get('tag'): alt['tag'] = best['tag']
        except (TypeError, ValueError):
            alt = None
        break
    if best:
        ask = best['ask']; fair = row['fair_home_or_over_c'] / 100
        row['kalshi'] = best; row['gross_c'] = round((fair - ask) * 100, 1)
        row['fee_c'] = round(fee(ask) * 100, 1)
        row['net_c'] = round(row['gross_c'] - row['fee_c'], 1)   # P-EDGE-001: net >= 2c
        if alt:
            afair = 1 - fair
            row['alt'] = {'kalshi': {'ticker': best['ticker'], **alt},
                          'fair_c': round(afair * 100, 1),
                          'gross_c': round((afair - alt['ask']) * 100, 1),
                          'fee_c': round(fee(alt['ask']) * 100, 1)}
            row['alt']['net_c'] = round(row['alt']['gross_c'] - row['alt']['fee_c'], 1)
    return row
def main():
    games = load_prefill()
    out = []
    for cls in ('spread', 'total'):
        for row in consensus_fair(games, cls):
            if 'consensus_line' in row: row = anchor_kalshi(row)
            out.append(row)
    print(json.dumps(out, indent=1))
if __name__ == '__main__': main()
