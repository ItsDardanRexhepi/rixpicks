#!/usr/bin/env python3
"""Daily slate gatherer for the 6:45 AM card build - registry-driven (config_leagues.json).
Usage: league_slate.py LEAGUE [LEAGUE...] [--date YYYYMMDD] [--odds] [--json]
Per league: ESPN schedule+meta (team sports via competitions, tennis via groupings),
Kalshi open-market match per event, and (only with --odds, spends credits) odds-API h2h.
Output: JSON list of slate entries {league, away, home, commence, status, espn_id, kalshi:[{ticker,title,yes_bid,yes_ask}], odds?}
Credit discipline: --odds only when building a card that will use it (J-049A)."""
import json,sys,urllib.request,datetime,os,re
UA={'User-Agent':'python-urllib/3.10'}
def get(u,t=20):
    return json.load(urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=t))
def name_of(c):
    t=c.get('team') or c.get('athlete') or {}
    return t.get('displayName') or t.get('fullName') or ''
def main():
    args=[a for a in sys.argv[1:] if not a.startswith('--')]
    use_odds='--odds' in sys.argv
    dt=None
    if '--date' in sys.argv: dt=sys.argv[sys.argv.index('--date')+1]
    if not dt: dt=datetime.datetime.now().strftime('%Y%m%d')
    reg=json.load(open(os.path.join(os.path.dirname(__file__),'..','config_leagues.json')))['leagues']
    slate=[]
    for lgname in args:
        cfg=reg.get(lgname)
        if not cfg: print(f"unknown league {lgname}",file=sys.stderr); continue
        events=[]
        if cfg.get('espn'):
            prm='&'+cfg['espn_params'] if cfg.get('espn_params') else ''
            try:
                sb=get(f"https://site.api.espn.com/apis/site/v2/sports/{cfg['espn']}/scoreboard?dates={dt}&limit=200{prm}")
                for ev in sb.get('events',[]):
                    if ev.get('competitions'):
                        for comp in ev['competitions']:
                            cs=comp.get('competitors') or []
                            if len(cs)>=2:
                                away=next((c for c in cs if c.get('homeAway')=='away'),cs[0])
                                home=next((c for c in cs if c.get('homeAway')=='home'),cs[-1])
                                events.append({'espn_id':ev.get('id'),'away':name_of(away),'home':name_of(home),
                                    'commence':comp.get('date') or ev.get('date'),
                                    'status':(comp.get('status') or {}).get('type',{}).get('name','?'),
                                    'away_abbr':(away.get('team') or {}).get('abbreviation',''),
                                    'home_abbr':(home.get('team') or {}).get('abbreviation','')})
                    for g in ev.get('groupings',[]):  # tennis
                        for comp in g.get('competitions',[]):
                            cs=comp.get('competitors') or []
                            if len(cs)>=2:
                                events.append({'espn_id':comp.get('id'),'away':name_of(cs[0]),'home':name_of(cs[1]),
                                    'commence':comp.get('date') or ev.get('date'),
                                    'status':(comp.get('status') or {}).get('type',{}).get('name','?'),
                                    'away_abbr':'','home_abbr':''})
                if not events and lgname in ('NASCAR','PGA'):  # field events: race/tournament, not h2h
                    for ev in sb.get('events',[]):
                        events.append({'espn_id':ev.get('id'),'away':ev.get('name',''),'home':'(field)',
                            'commence':ev.get('date'),'status':(ev.get('status') or {}).get('type',{}).get('name','?'),
                            'away_abbr':'','home_abbr':''})
            except Exception as e:
                print(f"{lgname}: espn fetch failed {e}",file=sys.stderr)
        # Kalshi match
        km=[]
        for ser in cfg.get('kalshi') or []:
            try:
                km+=get(f"https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker={ser}&status=open&limit=200").get('markets',[])
            except Exception as e:
                print(f"{lgname}: kalshi {ser} failed {e}",file=sys.stderr)
        seen=set(); dedup=[]
        for ev in events:
            k=(ev['away'],ev['home'],ev['commence'])
            if k in seen: continue
            seen.add(k); dedup.append(ev)
        events=dedup
        for ev in events:
            mk=[]
            blob=f"{ev['away']} {ev['home']} {ev.get('away_abbr','')} {ev.get('home_abbr','')}".lower()
            for m in km:
                hay=f"{m.get('title','')} {m.get('ticker','')} {m.get('subtitle','')}".lower()
                toks=[t for t in re.split(r'\W+',blob) if len(t)>2]
                if sum(1 for t in set(toks) if t in hay)>=2:
                    mk.append({'ticker':m['ticker'],'title':m.get('title',''),
                        'yes_bid':m.get('yes_bid_dollars'),'yes_ask':m.get('yes_ask_dollars')})
            ev['kalshi']=mk[:4]
            ev['league']=lgname
            slate.append(ev)
    print(json.dumps(slate,indent=1))
if __name__=='__main__': main()
