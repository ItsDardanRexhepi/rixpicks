#!/usr/bin/env python3
"""Stage 0 (J-121 EVERYTHING scope): spreads + totals prefill from The Odds API free tier.
Usage: odds_prefill_st.py <sport_key>...   e.g. odds_prefill_st.py americanfootball_ncaaf americanfootball_nfl baseball_mlb
Writes /tmp/odds_prefill_st.json: [{away,home,commence,books:{bk:{spread_home_pts,spread_home_price,spread_away_price,total_pts,over_price,under_price}}}]
Credit cost: 2 markets x 1 region per sport (2 credits/sport/pull). Free tier only; paid tier is his purchase.
"""
import json,sys,urllib.request,os
K=(os.environ.get('THE_ODDS_API_KEY') or open('/home/sandbox/.odds_api_key').read()).strip()
out={}
OUT=os.environ.get('ODDS_PREFILL_ST_OUT','/tmp/odds_prefill_st.json')
FIXTURE=os.environ.get('ODDS_PREFILL_ST_FIXTURE')  # e2e only: path to a canned API response
for sport in sys.argv[1:]:
    if FIXTURE:
        data=json.load(open(FIXTURE)); rem='fixture'
    else:
        url=(f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?apiKey={K}"
             "&regions=us&markets=spreads,totals&oddsFormat=american"
             "&bookmakers=fanduel,draftkings,betmgm,betrivers,espnbet,hardrockbet")
        req=urllib.request.Request(url,headers={'User-Agent':'curl/8'})
        with urllib.request.urlopen(req,timeout=30) as r:
            rem=r.headers.get('x-requests-remaining'); data=json.load(r)
    print(f"{sport}: {len(data)} events, credits remaining {rem}",file=sys.stderr)
    for e in data:
        key=(e['away_team'],e['home_team'],e.get('commence_time'))
        rec=out.setdefault(key,{})
        for b in e.get('bookmakers',[]):
            ent={}
            for m in b.get('markets',[]):
                if m['key']=='spreads':
                    for o in m.get('outcomes',[]):
                        if o['name']==e['home_team']: ent['spread_home_pts']=o.get('point'); ent['spread_home_price']=o.get('price')
                        elif o['name']==e['away_team']: ent['spread_away_price']=o.get('price')
                elif m['key']=='totals':
                    for o in m.get('outcomes',[]):
                        if o['name']=='Over': ent['total_pts']=o.get('point'); ent['over_price']=o.get('price')
                        elif o['name']=='Under': ent['under_price']=o.get('price')
            if ent: rec[b['key']]=ent
json.dump([{'away':k[0],'home':k[1],'commence':k[2],'books':v} for k,v in out.items()],open(OUT,'w'))
print(f'wrote {OUT} ({len(out)} games)')
