#!/usr/bin/env python3
"""CLV capture: annotate history.json picks with closing line + CLV.
close = last price_history.jsonl snapshot strictly before game start (manifest commence).
CLV>0 means we beat the close (paid a better price than the market's final number)."""
import json,sys,datetime

def ip(a):
    a=float(a)
    return 100.0/(a+100) if a>0 else (-a)/((-a)+100.0)

def parse_odds(s):
    try: return int(str(s).replace('+',''))
    except: return None

def main(date, history_path='history.json', ph_path='price_history.jsonl', man_path='manifest.json'):
    H=json.load(open(history_path))
    man=json.load(open(man_path))
    # game -> commence, side team names
    commence={}
    for p in man.get('picks',[]):
        g=p.get('game') or {}
        if g.get('commence'): commence[(g.get('away'),g.get('home'))]=g['commence']
    snaps={}
    for line in open(ph_path):
        try: r=json.loads(line)
        except: continue
        key=(r.get('away'),r.get('home'))
        snaps.setdefault(key,[]).append(r)
    for k in snaps: snaps[k].sort(key=lambda r:r['ts'])
    day=next((d for d in H['days'] if d['date']==date),None)
    if not day: print('no day',date); return 1
    out=[]
    for p in day.get('picks',[]):
        # match pick to a game via note/game text -> use manifest picks by name
        mp=next((x for x in man.get('picks',[]) if x['name']==p['name']),None)
        if not mp or not mp.get('game'): continue
        g=mp['game']; key=(g['away'],g['home'])
        com=g.get('commence')
        if not com or key not in snaps: continue
        prior=[s for s in snaps[key] if s['ts']<com]
        if not prior: continue
        close_snap=prior[-1]
        side=mp.get('side','away')
        suf='a' if side=='away' else 'h'
        entry=parse_odds(p.get('odds'))
        dk_close=close_snap.get('dk_'+suf)
        # consensus close: mean implied prob across available books
        ips=[]
        for bk in ('dk','fd','espn','hr','mgm','br'):
            v=close_snap.get(bk+'_'+suf)
            if v is not None: ips.append(ip(v))
        cons=sum(ips)/len(ips) if ips else None
        if entry is None: continue
        clv_dk=(ip(dk_close)-ip(entry))*100 if dk_close is not None else None
        clv_cons=(cons-ip(entry))*100 if cons is not None else None
        p['close']=dk_close
        p['close_ts']=close_snap['ts']
        if clv_dk is not None: p['clv']=round(clv_dk,1)
        if clv_cons is not None: p['clv_cons']=round(clv_cons,1)
        out.append((p['name'],entry,dk_close,p.get('clv'),p.get('clv_cons')))
    json.dump(H,open(history_path,'w'),indent=1)
    for o in out: print(o)
    return 0

if __name__=='__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv)>1 else datetime.date.today().isoformat()))
