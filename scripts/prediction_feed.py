#!/usr/bin/env python3
"""prediction_feed.py - fill manifest picks' dkp slots from slates/prediction_markets.json.

The sidecar is harvested off-runner (browser; predictions.draftkings.com Akamai-blocks
datacenter IPs) and committed. This matcher runs in refresh.sh before the build:
team-name + ET-date match, moneyline picks only (prop picks never inherit a game ML
link - wrong market is a failure, abstain is not). Fail-closed: no confident row match
-> slot stays null, no chip. Re-stamps pick_content_hash (mirror of the builder gate).
"""
import json, sys, re, datetime
from zoneinfo import ZoneInfo
import hashlib as _hl

def _pick_content_hash(m):
    # EXACT MIRROR of build_gh_page_v2.py _pick_content_hash (drift fails closed at the builder).
    _EXCL_TOP={'num','result','_final','polycents','card_ts','line_shop','books','books_sp','prop_books'}
    def _canon(p):
        c={k:v for k,v in p.items() if k not in _EXCL_TOP}
        if isinstance(c.get('kalshi'),dict):
            c['kalshi']={k:v for k,v in c['kalshi'].items() if k!='cents'}
        c.pop('dkp_note',None)
        if isinstance(c.get('dkp'),dict):
            c['dkp']={k:v for k,v in c['dkp'].items() if k not in ('team_cents','home_cents','away_cents','derived','harvested')}
            if not c['dkp']: c.pop('dkp')
        return c
    rows=sorted(json.dumps(_canon(p),sort_keys=True) for p in m.get('picks',[]))
    return _hl.sha256('\n'.join(rows).encode()).hexdigest()

def _last(name): return (name or '').split()[-1].lower()

def main():
    manifest_path=sys.argv[1] if len(sys.argv)>1 else 'manifest.json'
    sidecar_path=sys.argv[2] if len(sys.argv)>2 else 'slates/prediction_markets.json'
    man=json.load(open(manifest_path))
    try: side=json.load(open(sidecar_path))
    except FileNotFoundError:
        print('prediction_feed: no sidecar - slots untouched', file=sys.stderr); return
    rows=side.get('rows') or []
    et_today=datetime.datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    n=0
    for p in man['picks']:
        if p.get('side') not in ('home','away'): continue  # moneyline-only (prop guard)
        g=p.get('game') or {}
        away, home = g.get('away',''), g.get('home','')
        if not away or not home: continue
        commence=g.get('commence','')
        try: d=datetime.datetime.fromisoformat(commence.replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).date().isoformat()
        except Exception: d=''
        for r in rows:
            if r.get('venue')!='dkp': continue
            if r.get('date') not in (d, et_today): continue
            if _last(r.get('away'))!=_last(away) or _last(r.get('home'))!=_last(home): continue
            cents=r.get('home_cents') if p['side']=='home' else r.get('away_cents')
            if cents is None: break
            p['dkp']={'url':r['url'],'team_cents':cents,'home_cents':r.get('home_cents'),'away_cents':r.get('away_cents'),'harvested':side.get('updated')}
            n+=1
            print(f"OK {p.get('name')}: {r['url']} pick-side {cents}c dkp")
            break
    if n:
        man['pick_content_hash']=_pick_content_hash(man)
        json.dump(man,open(manifest_path,'w'),indent=1)
    print(f"dkp-fed {n}/{len(man['picks'])} picks", file=sys.stderr)

main()
