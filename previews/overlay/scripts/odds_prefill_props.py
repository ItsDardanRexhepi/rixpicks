#!/usr/bin/env python3
"""Player-props prefill (props pipeline step 1). Event-scoped pulls, screen-flagged games ONLY
(parent 16:09 spec): /v4/sports/{sport}/events/{event_id}/odds?markets=<props>&regions=us.
Cost per official docs: 1 credit per market per region PER EVENT. Every pull passes
core.budget.check_and_log BEFORE request (J-123); props_allowed() gate (J-123a verbatim).
IN : JSON list on argv[1]: [{"sport":"americanfootball_nfl","event_id":"...",
     "markets":["player_rush_yds",...]}, ...]  (screen-flagged games from hunt/st_hunt)
OUT: /tmp/odds_prefill_props.json - rows in the props_fair.py schema:
     two-sided: {sport,event_id,book,player,market,point,over,under}
     anytime_td yes/no: {sport,event_id,book,player,market,point:None,yes[,no]}
     (9/27 v4 bug: producer emitted over_price/under_price/line and dropped yes-only rows;
     props_fair reads over/under/point -> 0 calibration pairs -> fail-close.)"""
import json, os, sys, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.budget import check_and_log, props_allowed, props_block_reason, odds_key
BASE = 'https://api.the-odds-api.com/v4/sports'
def pull(sport, event_id, markets):
    m = ','.join(markets)
    credits = len(markets) * 1  # 1 region (us)
    check_and_log(sport, m, credits)  # raises on cap breach - no request fires
    url = f'{BASE}/{sport}/events/{event_id}/odds?markets={m}&regions=us&oddsFormat=american&apiKey={odds_key()}'
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)
def main(jobs_path):
    jobs = json.load(open(jobs_path))
    out = []
    for job in jobs:
        d = pull(job['sport'], job['event_id'], job['markets'])
        for bk in d.get('bookmakers', []):
            for mk in bk.get('markets', []):
                # group outcomes by player+point: over/under sides
                pairs = {}
                for o in mk.get('outcomes', []):
                    key = (o.get('description'), o.get('point'))
                    pairs.setdefault(key, {})[o.get('name')] = o.get('price')
                yn_market = mk.get('key') == 'player_anytime_td'
                for (player, point), sides in pairs.items():
                    base = {'sport': job['sport'], 'event_id': job['event_id'],
                            'book': bk.get('key'), 'player': player, 'market': mk.get('key')}
                    if yn_market:
                        # books post anytime_td as Over 0.5 (yes); fair model wants point=None yes/no
                        if 'Over' not in sides: continue
                        r = dict(base); r['point'] = None; r['yes'] = sides['Over']
                        if 'Under' in sides: r['no'] = sides['Under']
                        out.append(r)
                    else:
                        if 'Over' not in sides or 'Under' not in sides: continue
                        r = dict(base); r['point'] = point
                        r['over'] = sides['Over']; r['under'] = sides['Under']
                        out.append(r)
    outp = '/tmp/odds_prefill_props.json'
    json.dump(out, open(outp, 'w'), indent=1)
    print(f'{len(out)} prop rows -> {outp}')
if __name__ == '__main__':
    if not props_allowed():
        raise SystemExit('FAIL: ' + props_block_reason())
    if len(sys.argv) < 2: raise SystemExit('usage: odds_prefill_props.py <jobs.json>')
    main(sys.argv[1])
