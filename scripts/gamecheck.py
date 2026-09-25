#!/usr/bin/env python3
"""J-094 doubleheader preflight: for every manifest pick on a multi-game matchup,
verify Kalshi chip targets by EVENT TITLE (Game N) and flag Polymarket targets for
live-page verification (gamma desc/startDate go stale - J-093/J-094). Exit 2 on a
Kalshi instance mismatch so the build cannot ship an unverified doubleheader."""
import json,sys,urllib.request,re
man=json.load(open(sys.argv[1] if len(sys.argv)>1 else 'manifest.json'))
def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    return json.load(urllib.request.urlopen(req,timeout=15))
fail=0
matchups={}
for p in man.get('picks',[]):
    g=p.get('game') or {}
    matchups.setdefault((g.get('away'),g.get('home')),[]).append(p)
for (away,home),picks in matchups.items():
    if not away: continue
    for p in picks:
        inst=''
        m=re.search(r'\(Game (\d)\)', p.get('sub',''))
        if m: inst=f"Game {m.group(1)}"
        if not inst: continue  # single-game pick, nothing to verify
        k=p.get('kalshi')
        if k:
            tick=k['url'].rstrip('/').split('/')[-1].upper()
            try:
                ev=get(f'https://api.elections.kalshi.com/trade-api/v2/events/{tick}')
                title=((ev.get('event') or {}).get('sub_title') or '')
                if inst.lower() not in title.lower():
                    print(f"KALSHI MISMATCH: {p['name']} wants {inst}, event {tick} subtitle '{title}'",file=sys.stderr); fail=2
                else:
                    print(f"OK kalshi {tick} -> {inst} ({title})")
            except Exception as e:
                print(f"KALSHI CHECK FAILED {tick}: {e}",file=sys.stderr); fail=2
        if p.get('polymarket'):
            print(f"MANUAL: live-verify polymarket {p['polymarket']['url']} shows {inst} start time (gamma desc can be stale)")
sys.exit(fail)
