#!/usr/bin/env python3
# Real platform price history for game-page charts (user, Sep 25 1:14 PM):
# KAL/POLY lines must match their own platforms' graphs. Books publish no
# history, so they stay out of the chart (live prices remain in the table).
import json,urllib.request,re,glob,os,time
def get(u):
    req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
    return json.load(urllib.request.urlopen(req,timeout=20))
NOW=int(time.time())
START=NOW-36*3600
for f in sorted(glob.glob('game-*.html')):
    n=re.search(r'game-(\d+)\.html',f).group(1)
    h=open(f).read()
    out={}
    kt=re.search(r'data-kalticker="([^"]+)"',h)
    ks=re.search(r'data-kalside="([^"]+)"',h)
    if kt and ks:
        evt,side=kt.group(1),ks.group(1)
        try:
            d=get(f'https://api.elections.kalshi.com/trade-api/v2/series/{evt.split("-")[0]}/markets/{evt}-{side}/candlesticks?start_ts={START}&end_ts={NOW}&period_interval=1')
            pts=[[c['end_period_ts'],round(float(c['price']['close_dollars'])*100,1)] for c in d.get('candlesticks',[]) if c.get('price') and c['price'].get('close_dollars')]
            if pts: out['kal']=pts
        except Exception as e: print(f,'kal ERR',e)
    ps=re.search(r'data-polyslug="([^"]+)"',h)
    kw=re.search(r'data-polykw="([^"]+)"',h)
    if ps:
        try:
            ev=get('https://gamma-api.polymarket.com/events?slug='+ps.group(1))
            mk=None
            for m in ev[0].get('markets',[]):
                if m.get('clobTokenIds') and 'vs' in (m.get('question') or '').lower() or (m.get('question') or '').count('@'):
                    mk=m; break
            if not mk:
                for m in ev[0].get('markets',[]):
                    if m.get('clobTokenIds'): mk=m; break
            if mk:
                outs=json.loads(mk['outcomes']) if isinstance(mk.get('outcomes'),str) else mk.get('outcomes',[])
                toks=json.loads(mk['clobTokenIds']) if isinstance(mk.get('clobTokenIds'),str) else mk['clobTokenIds']
                kword=(kw.group(1) if kw else '').lower()
                ti=0
                for i,o in enumerate(outs):
                    if kword and kword in str(o).lower(): ti=i; break
                d=get(f'https://clob.polymarket.com/prices-history?market={toks[ti]}&startTs={START}&endTs={NOW}&fidelity=5')
                pts=[[p['t'],round(p['p']*100,1)] for p in d.get('history',[])]
                if pts: out['poly']=pts
        except Exception as e: print(f,'poly ERR',e)
    if out:
        json.dump(out,open(f'hist-{n}.json','w'))
        print(f,'->',{k:len(v) for k,v in out.items()})
