#!/usr/bin/env python3
"""Durable Kalshi spread/total/ML ladder board fetch (deep-dive capability).
Fetches fresh quotes and STAMPS fetched_at - ladder_scan refuses stale boards.
Records event_ticker + title + status per market for exact binding downstream.
Usage: ladder_board.py <YYYY-MM-DD local slate date> -> /tmp/kalshi_ladders_<date>.json"""
import urllib.request, json, sys, datetime, re
def kget(path, params=''):
    url=f"https://api.elections.kalshi.com/trade-api/v2{path}?{params}"
    req=urllib.request.Request(url, headers={'User-Agent':'python-urllib/3.10'})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)
def daycode(d):
    dt=datetime.date.fromisoformat(d)
    return dt.strftime('%y%b%d').upper()
SERIES={'NFL':['KXNFLSPREAD','KXNFLTOTAL'],'MLB':['KXMLBSPREAD','KXMLBTOTAL'],
        'WNBA':['KXWNBAGAME','KXWNBASPREAD','KXWNBATOTAL']}
def main():
    date=sys.argv[1]; dc='26'+datetime.date.fromisoformat(date).strftime('%b%d').upper() if not date.startswith('20') else daycode(date)
    dc=daycode(date)
    board={'fetched_at':datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
           'slate_date':date,'daycode':dc,'series':{},'errors':{}}
    for lg,ss in SERIES.items():
        for s in ss:
            try:
                mk=[];cursor=''
                for _ in range(15):
                    d=kget('/markets',f'series_ticker={s}&status=open&limit=200'+(f'&cursor={cursor}' if cursor else ''))
                    mk+=d.get('markets',[]);cursor=d.get('cursor') or ''
                    if not cursor: break
                day=[m for m in mk if dc in m.get('ticker','')]
                board['series'][s]=[{'t':m['ticker'],'event_ticker':m.get('event_ticker'),'title':m.get('title'),
                    'status':m.get('status'),'yb':m.get('yes_bid_dollars'),'ya':m.get('yes_ask_dollars'),
                    'nb':m.get('no_bid_dollars'),'na':m.get('no_ask_dollars'),
                    'vol':m.get('volume_fp') or m.get('volume'),'liq':m.get('liquidity_dollars') or m.get('liquidity'),
                    'oi':m.get('open_interest_fp') or m.get('open_interest')} for m in day]
                print(s, len(day), 'markets')
            except Exception as e:
                board['errors'][s]=str(e); print(s,'ERROR',e)
    out=f'/tmp/kalshi_ladders_{date}.json'
    json.dump(board, open(out,'w'))
    print('wrote', out, 'fetched_at', board['fetched_at'])
if __name__=='__main__': main()
