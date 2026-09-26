#!/usr/bin/env python3
"""Fetch outcome-level PREFILL betslip links from The Odds API (J-049A key) for the day's slate.
Usage: odds_prefill.py <sport_key> [<sport_key>...]   e.g. odds_prefill.py baseball_mlb americanfootball_ncaaf
Writes /tmp/odds_prefill.json: {(away,home): {'fanduel': {'away':link,'home':link,'away_ml':int,'home_ml':int,'event':link}, 'draftkings': {...}}}
Only FD + DK produce clean universal prefill links; betmgm/betrivers carry {state} templates (kept in 'state_templates').
Credit discipline: 1 credit per market per region per sport (h2h only). ~16/day max (standing J-049A).
"""
import json,sys,urllib.request,os
import os as _os
K=(_os.environ.get('THE_ODDS_API_KEY') or open('/home/sandbox/.odds_api_key').read()).strip()
SPORT_MAP={'baseball_mlb':('MLB',)}
out={}
for sport in sys.argv[1:]:
    url=(f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?apiKey={K}"
         "&regions=us&markets=h2h&oddsFormat=american&includeLinks=true&includeSids=true"
         "&bookmakers=fanduel,draftkings,betmgm,betrivers,espnbet,hardrockbet")
    req=urllib.request.Request(url,headers={'User-Agent':'curl/8'})
    with urllib.request.urlopen(req,timeout=20) as r:
        rem=r.headers.get('x-requests-remaining')
        data=json.load(r)
    print(f"{sport}: {len(data)} events, credits remaining {rem}",file=sys.stderr)
    for e in data:
        key=(e['away_team'],e['home_team'],e.get('commence_time'))  # J-090: game instance, not matchup - doubleheaders must never collide
        rec=out.setdefault(key,{})
        for b in e.get('bookmakers',[]):
            bk=b['key']
            oc=(b.get('markets') or [{}])[0].get('outcomes') or []
            links={}
            mls={}
            for o in oc:
                if o['name']==e['away_team']: side='away'
                elif o['name']==e['home_team']: side='home'
                else: continue  # 3-way sports (soccer Draw) - never mislabel as home (J-099)

                if o.get('link'): links[side]=o['link']
                if o.get('price') is not None: mls[side]=o['price']
            entry={'event':b.get('link'),**{f'{s}_link':l for s,l in links.items()},**{f'{s}_ml':m for s,m in mls.items()}}
            if bk in ('fanduel','draftkings','espnbet','hardrockbet'):
                rec[bk]=entry
            elif bk in ('betmgm','betrivers'):
                rec.setdefault('state_templates',{})[bk]=entry
json.dump([{'away':k[0],'home':k[1],'commence':k[2],'books':v} for k,v in out.items()],open('/tmp/odds_prefill.json','w'))
print(f"wrote /tmp/odds_prefill.json ({len(out)} games)")
