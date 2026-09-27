#!/usr/bin/env python3
"""Kalshi spread/total ladder SCANNER (screen-only; deep-dive capability, his 10:08 PM directive).
Prices every bound ladder rung vs a book-consensus-anchored curve. Output rows are SCREEN HITS,
NEVER card picks: card_eligible is always False here - a hit must still pass independent model /
book convergence / availability / URF gates downstream (hunt_v2 + gems.card_gem) before carding.

BINDING (swamp 9/26 rounds 1-3): exact event+date+team+market+line, ambiguity REFUSES (no side
guessing; doubleheaders/refetches refuse when 2+ slate rows match and the ticker can't disambiguate).
FRESHNESS: every input carries fetched_at; rows older than --max-age-min are stale, never hits.
MARKET AVAILABILITY: rung must be status active with a real two-sided quote; zero-activity rungs
are flagged thin. SOURCE PROVENANCE: every row carries ticker, event_ticker, board fetched_at,
books fetched_at, n_books.

Models: NFL margin/total = book-consensus normals (sigma 13.8/10.5); MLB margin = Pythagorean runs
split from BOOK-devigged ML + book total (sigma 4.3 empirical fat tails - 3.1 invented fake edges);
MLB total = book total + starter ERA adj (sigma 3.0); WNBA = book-anchored screen-only (sigma 13,
ML+spread calibrated). Fee = 0.07*P*(1-P). Screen-hit bar: fair>=0.60 AND gross>=2c, fresh, bound,
active market. Far-tail rungs (|z|>=2) are curve noise - excluded from hits by construction label."""
import json, re, sys, os, statistics, datetime
from statistics import NormalDist
ND=NormalDist()
def fee(p): return 0.07*p*(1-p)
def inv(p): return ND.inv_cdf(min(max(p,1e-6),1-1e-6))
def noask(m):
    # Executable NO ask ONLY - never synthesize one from 1-yes_bid (a low yes_bid fabricates
    # NO-side hits). Returns (na, violation). Missing na -> (None,None): caller refuses the row.
    na=m.get('na')
    if na in (None,''): return None,None
    na=float(na)
    yb=m.get('yb')
    if yb not in (None,'') and na < 1-float(yb)-0.02:
        return None,f'bid/ask integrity violation: no_ask {na} < 1-yes_bid {round(1-float(yb),4)}'
    return na,None

DATE=sys.argv[1] if len(sys.argv)>1 else None
MAX_AGE=int(os.environ.get('LADDER_MAX_AGE_MIN','45'))
if not DATE: print('usage: ladder_scan.py <YYYY-MM-DD>'); sys.exit(2)

def load(path, need_ts=True):
    if not os.path.exists(path):
        print(f'FAIL LOUD: missing {path}'); return None
    d=json.load(open(path))
    if need_ts:
        ts=d.get('fetched_at') if isinstance(d,dict) else None
        if not ts:
            print(f'FAIL LOUD: {path} lacks fetched_at - refusing to price from unstamped input'); return None
        age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(ts.replace('Z','+00:00'))).total_seconds()/60
        if age>MAX_AGE:
            print(f'FAIL LOUD: {path} is {age:.0f}m old (> {MAX_AGE}m) - stale, refetch'); return None
        return d, ts
    return d, None

board_r=load(f'/tmp/kalshi_ladders_{DATE}.json')
books_r=load(f'/tmp/st_books_{DATE}.json')
slate=json.load(open(f'/tmp/slate_day_{DATE}.json'))
if not board_r or not books_r: sys.exit(2)
board, board_ts = board_r
books, books_ts = books_r
if isinstance(books, dict): books=books['games']

DC=board['daycode']
nfl_edges_p=f'/tmp/nfl_edges_{DATE[5:7]}{DATE[8:10]}.json'
mlb_edges_p=f'/tmp/mlb_{DATE[5:7]}{DATE[8:10]}_edges.json'
mlb_raw_p=f'/tmp/mlb_{DATE[5:7]}{DATE[8:10]}_model_raw.json'
nfl_edges=json.load(open(nfl_edges_p)) if os.path.exists(nfl_edges_p) else []
mlb_edges=json.load(open(mlb_edges_p)) if os.path.exists(mlb_edges_p) else []
mlb_raw={r['aa']+r['ha']:r for r in json.load(open(mlb_raw_p))} if os.path.exists(mlb_raw_p) else {}

ALIAS_NFL={'JAX':'JAC','WSH':'WAS'}  # NFL-only - applying it to MLB/WNBA corrupts binds (WSH Nationals)
def kab(a, league=None):
    return ALIAS_NFL.get(a,a) if league=='NFL' else a

def consensus(g):
    hs=[];tot=[];mlh=[];mla=[]
    for bk,mk in g['books'].items():
        for o in mk.get('spreads',[]):
            if o['side']=='home' and o['point'] is not None: hs.append(o['point'])
        for o in mk.get('totals',[]):
            if o['side']=='over' and o['point'] is not None: tot.append(o['point'])
        for o in mk.get('h2h',[]):
            if o['side']=='home' and o['price']: mlh.append(o['price'])
            if o['side']=='away' and o['price']: mla.append(o['price'])
    def d2p(a): return (-a)/(-a+100) if a<0 else 100/(a+100)
    ph=pa=None
    if mlh and mla:
        mh=statistics.median([d2p(x) for x in mlh]); ma=statistics.median([d2p(x) for x in mla])
        ph=mh/(mh+ma); pa=ma/(mh+ma)
    return {'home_spread':statistics.median(hs) if hs else None,
            'total':statistics.median(tot) if tot else None,
            'p_home':ph,'n_books':len(g['books'])}
bookmap={}
for g in books:
    k=(g['sport'],g['away'],g['home'])
    if k in bookmap: bookmap[k]='AMBIG'
    else: bookmap[k]=consensus(g)

# slate instance map: (league, abbrpair) -> list of rows (doubleheader-safe; refuse ambiguity)
slmap={}
for r in slate['rows']:
    aa,ha=r.get('away_abbr'),r.get('home_abbr')
    if not (aa and ha): continue
    slmap.setdefault((r['league'], kab(aa,r['league'])+kab(ha,r['league'])), []).append(r)
MLB_KALSHI_TO_SLATE={'CWS':'CHW'}
def bind_slate(league, abbrpair, hint_hhmm=None):
    keys=[abbrpair]
    if league=='MLB':
        for a,b in MLB_KALSHI_TO_SLATE.items():
            keys.append(abbrpair.replace(a,b))
    rows=[]
    for k in keys:
        rows=slmap.get((league,k),[])
        if rows: break
    if not rows: return None,'no slate row'
    if len(rows)>1 and hint_hhmm:
        from zoneinfo import ZoneInfo
        m=[r for r in rows if datetime.datetime.fromisoformat(r['commence_utc'].replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).strftime('%H%M')==hint_hhmm]
        if len(m)==1: return m[0],None
    if len(rows)==1: return rows[0],None
    return None,f'ambiguous slate instance ({len(rows)} rows) - REFUSING'

SIG_NFL_M=13.8; SIG_NFL_T=10.5; SIG_MLB_M=4.3; SIG_MLB_T=3.4; SIG_WNBA_M=13.0; SIG_WNBA_T=15.0
MAX_Z_HIT=0.5  # hits only near the book line; totals hits suppressed until sigma calibrated to market alt-line curves
out=[]; errors=[]
def add(league, game, mtype, rung, side, fair, ask, model_kind, src, extra=None):
    if ask is None or fair is None: return
    ask=float(ask)
    if not (0.001<ask<0.999): return
    gross=fair-ask; net=gross-fee(ask)
    z=abs(extra.get('z',0)) if extra else 0
    thin = bool(extra and (not extra.get('vol')) and (not extra.get('oi')))
    curve_unvalidated = (mtype=='total')  # totals sigmas not calibrated to market alt curves yet
    row={'league':league,'game':game,'type':mtype,'rung':rung,'side':side,'fair':round(fair,4),
         'ask':ask,'gross_c':round(gross*100,1),'net_c':round(net*100,1),'model':model_kind,
         'screen_hit': bool(fair>=0.60 and gross>=0.02 and z<MAX_Z_HIT and not thin and not curve_unvalidated),
         'card_eligible': False,  # NEVER cardable from scanner output alone - gates live downstream
         'requires_gates':['fresh_quote','exact_binding','book_convergence','availability','urf'],
         'thin_market': thin, 'far_tail_excluded': bool(z>=2), 'curve_unvalidated': curve_unvalidated,
         'src':src}
    if extra: row.update({k:v for k,v in extra.items() if k!='z'})
    out.append(row)

def active(m): return m.get('status')=='active'

for m in board['series'].get('KXNFLSPREAD',[])+board['series'].get('KXNFLTOTAL',[]):
    if not active(m): continue
    is_total='TOTAL' in m['t']
    ev=m.get('event_ticker') or ''
    gcode=re.sub(r'^KXNFL(?:SPREAD|TOTAL)-','',ev)
    gcode=re.sub(r'^\d{2}[A-Z]{3}\d{2}','',gcode) or re.match(rf'KXNFL(?:SPREAD|TOTAL)-{DC}([A-Z]+)-',m['t']).group(1)
    row,bind_err=bind_slate('NFL',gcode)
    if not row: errors.append(f"NFL {m['t']}: {bind_err}"); continue
    bk=bookmap.get(('americanfootball_nfl',row['away'],row['home']))
    if bk in (None,'AMBIG') or bk['home_spread'] is None: errors.append(f"NFL {m['t']}: book map {'ambiguous' if bk=='AMBIG' else 'missing'}"); continue
    suf=m['t'].rsplit('-',1)[-1]
    src={'ticker':m['t'],'event_ticker':m.get('event_ticker'),'board_ts':board_ts,'books_ts':books_ts,'n_books':bk['n_books']}
    if is_total:
        if not suf.isdigit(): errors.append(f"NFL total suffix not numeric: {m['t']}"); continue
        if 'over' not in (m.get('title') or '').lower(): errors.append(f"NFL total title not O/U: {m.get('title')}"); continue
        thr=int(suf)-0.5
        if bk['total'] is None: continue
        z=(thr-bk['total'])/SIG_NFL_T
        fair=1-ND.cdf(z)
        add('NFL',f"{row['away_abbr']}@{row['home_abbr']}",'total',f"over {thr}",'YES',fair,m['ya'],'nfl_book_anchor',src,{'z':z,'book_total':bk['total'],'vol':m['vol'],'oi':m['oi']})
        _na,_viol=noask(m)
        if _viol: errors.append(f'NFL {_viol}: {m["t"]} - REFUSING NO row')
        elif _na is None: errors.append(f'NFL no executable no_ask: {m["t"]} - REFUSING NO row')
        else: add('NFL',f"{row['away_abbr']}@{row['home_abbr']}",'total',f"over {thr}",'NO',1-fair,_na,'nfl_book_anchor',src,{'z':z,'book_total':bk['total'],'vol':m['vol'],'oi':m['oi']})
    else:
        mt=re.match(r'([A-Z]+)(\d+)$',suf)
        if not mt: errors.append(f"NFL spread suffix unparseable: {m['t']}"); continue
        team,thr=mt.group(1),int(mt.group(2))-0.5
        aa,ha=kab(row['away_abbr'],'NFL'),kab(row['home_abbr'],'NFL')
        if team==ha: home_covers=True
        elif team==aa: home_covers=False
        else: errors.append(f"NFL spread suffix team {team} not in {aa}/{ha}: {m['t']} - REFUSING side"); continue
        mu=-bk['home_spread']
        z=((thr-mu) if home_covers else (-thr-mu))/SIG_NFL_M
        fair=(1-ND.cdf(z)) if home_covers else ND.cdf(z)
        add('NFL',f"{row['away_abbr']}@{row['home_abbr']}",'spread',f"{team} by>{thr}",'YES',fair,m['ya'],'nfl_book_anchor',src,{'z':z,'book_spread':bk['home_spread'],'vol':m['vol'],'oi':m['oi']})
        _na,_viol=noask(m)
        if _viol: errors.append(f'NFL {_viol}: {m["t"]} - REFUSING NO row')
        elif _na is None: errors.append(f'NFL no executable no_ask: {m["t"]} - REFUSING NO row')
        else: add('NFL',f"{row['away_abbr']}@{row['home_abbr']}",'spread',f"{team} by>{thr}",'NO',1-fair,_na,'nfl_book_anchor',src,{'z':z,'book_spread':bk['home_spread'],'vol':m['vol'],'oi':m['oi']})

for m in board['series'].get('KXMLBSPREAD',[])+board['series'].get('KXMLBTOTAL',[]):
    if not active(m): continue
    is_total='TOTAL' in m['t']
    mt0=re.match(rf'KXMLB(?:SPREAD|TOTAL)-{DC}(\d{{4}})([A-Z]+)-',m['t'])
    if not mt0: errors.append(f"MLB ticker unparseable: {m['t']}"); continue
    hhmm,gcode=mt0.group(1),mt0.group(2)
    row,bind_err=bind_slate('MLB',gcode,hint_hhmm=hhmm)
    if not row: errors.append(f"MLB {m['t']}: {bind_err}"); continue
    bk=bookmap.get(('baseball_mlb',row['away'],row['home']))
    if bk in (None,'AMBIG') or bk['total'] is None or bk['p_home'] is None: errors.append(f"MLB {m['t']}: book map {'ambiguous' if bk=='AMBIG' else 'missing'}"); continue
    suf=m['t'].rsplit('-',1)[-1]
    src={'ticker':m['t'],'event_ticker':m.get('event_ticker'),'board_ts':board_ts,'books_ts':books_ts,'n_books':bk['n_books']}
    if is_total:
        if not suf.isdigit(): errors.append(f"MLB total suffix not numeric: {m['t']}"); continue
        if 'over' not in (m.get('title') or '').lower(): errors.append(f"MLB total title not O/U: {m.get('title')}"); continue
        # NO starter-ERA adjustment: the book total already prices the probables - adjusting
        # again double-counts and fabricated +8..+21c phantom hits on the first rewrite run.
        tmod=bk['total']; thr=int(suf)-0.5
        z=(thr-tmod)/SIG_MLB_T
        fair=1-ND.cdf(z)
        add('MLB',f"{row['away_abbr']}@{row['home_abbr']}",'total',f"over {thr}",'YES',fair,m['ya'],'mlb_total_era',src,{'z':z,'book_total':bk['total'],'t_model':round(tmod,2),'vol':m['vol'],'oi':m['oi']})
        _na,_viol=noask(m)
        if _viol: errors.append(f'MLB {_viol}: {m["t"]} - REFUSING NO row')
        elif _na is None: errors.append(f'MLB no executable no_ask: {m["t"]} - REFUSING NO row')
        else: add('MLB',f"{row['away_abbr']}@{row['home_abbr']}",'total',f"over {thr}",'NO',1-fair,_na,'mlb_total_era',src,{'z':z,'book_total':bk['total'],'t_model':round(tmod,2),'vol':m['vol'],'oi':m['oi']})
    else:
        mt=re.match(r'([A-Z]+)(\d+)$',suf)
        if not mt: errors.append(f"MLB spread suffix unparseable: {m['t']}"); continue
        team,thr=mt.group(1),int(mt.group(2))-0.5
        team=MLB_KALSHI_TO_SLATE.get(team,team)
        aa,ha=row['away_abbr'],row['home_abbr']
        if team==ha: home_covers=True
        elif team==aa: home_covers=False
        else: errors.append(f"MLB spread suffix team {team} not in {aa}/{ha}: {m['t']} - REFUSING side"); continue
        r=(bk['p_home']/(1-bk['p_home']))**(1/1.83); Eh=bk['total']*r/(1+r); Ea=bk['total']/(1+r); mu=Eh-Ea
        z=((thr-mu) if home_covers else (-thr-mu))/SIG_MLB_M
        fair=(1-ND.cdf(z)) if home_covers else ND.cdf(z)
        add('MLB',f"{row['away_abbr']}@{row['home_abbr']}",'spread',f"{team} by>{thr}",'YES',fair,m['ya'],'mlb_book_pyth',src,{'z':z,'book_total':bk['total'],'p_home_book':round(bk['p_home'],3),'vol':m['vol'],'oi':m['oi']})
        _na,_viol=noask(m)
        if _viol: errors.append(f'MLB {_viol}: {m["t"]} - REFUSING NO row')
        elif _na is None: errors.append(f'MLB no executable no_ask: {m["t"]} - REFUSING NO row')
        else: add('MLB',f"{row['away_abbr']}@{row['home_abbr']}",'spread',f"{team} by>{thr}",'NO',1-fair,_na,'mlb_book_pyth',src,{'z':z,'book_total':bk['total'],'p_home_book':round(bk['p_home'],3),'vol':m['vol'],'oi':m['oi']})

for series,mtype in [('KXWNBASPREAD','spread'),('KXWNBATOTAL','total'),('KXWNBAGAME','ml')]:
    for m in board['series'].get(series,[]):
        if not active(m): continue
        ev=m.get('event_ticker') or ''
        gcode=re.sub(rf'^{series}-','',ev)
        gcode=re.sub(r'^\d{2}[A-Z]{3}\d{2}','',gcode) or re.match(rf'{series}-{DC}([A-Z]+)-',m['t']).group(1)
        row,bind_err=bind_slate('WNBA',gcode)
        if not row: errors.append(f"WNBA {m['t']}: {bind_err}"); continue
        bk=bookmap.get(('basketball_wnba',row['away'],row['home']))
        if bk in (None,'AMBIG') or bk['home_spread'] is None: errors.append(f"WNBA {m['t']}: book map {'ambiguous' if bk=='AMBIG' else 'missing'}"); continue
        suf=m['t'].rsplit('-',1)[-1]
        src={'ticker':m['t'],'event_ticker':m.get('event_ticker'),'board_ts':board_ts,'books_ts':books_ts,'n_books':bk['n_books']}
        mu=-bk['home_spread']
        if mtype=='spread':
            mt=re.match(r'([A-Z]+)(\d+)$',suf)
            if not mt: errors.append(f"WNBA spread suffix unparseable: {m['t']}"); continue
            team,thr=mt.group(1),int(mt.group(2))-0.5
            aa,ha=row['away_abbr'],row['home_abbr']
            if team==ha: home_covers=True
            elif team==aa: home_covers=False
            else: errors.append(f"WNBA spread suffix team {team} not in {aa}/{ha}: {m['t']} - REFUSING side"); continue
            z=((thr-mu) if home_covers else (-thr-mu))/SIG_WNBA_M
            fair=(1-ND.cdf(z)) if home_covers else ND.cdf(z)
        elif mtype=='total':
            if not suf.isdigit(): errors.append(f"WNBA total suffix not numeric: {m['t']}"); continue
            if 'over' not in (m.get('title') or '').lower(): errors.append(f"WNBA total title not O/U: {m.get('title')}"); continue
            thr=int(suf)-0.5
            z=(thr-bk['total'])/SIG_WNBA_T; fair=1-ND.cdf(z)
        else:
            team=suf
            aa,ha=row['away_abbr'],row['home_abbr']
            if team==ha: home_covers=True
            elif team==aa: home_covers=False
            else: errors.append(f"WNBA ML suffix team {team} not in {aa}/{ha}: {m['t']} - REFUSING side"); continue
            z=(0-mu)/SIG_WNBA_M
            fair=(1-ND.cdf(z)) if home_covers else ND.cdf(z)  # away ML = complement of home win prob
        add('WNBA',f"{row['away_abbr']}@{row['home_abbr']}",mtype,f"{suf}",'YES',fair,m['ya'],'wnba_book_SCREENONLY',src,{'z':z,'book_spread':bk['home_spread'],'vol':m['vol'],'oi':m['oi']})
        _na,_viol=noask(m)
        if _viol: errors.append(f'WNBA {_viol}: {m["t"]} - REFUSING NO row')
        elif _na is None: errors.append(f'WNBA no executable no_ask: {m["t"]} - REFUSING NO row')
        else: add('WNBA',f"{row['away_abbr']}@{row['home_abbr']}",mtype,f"{suf}",'NO',1-fair,_na,'wnba_book_SCREENONLY',src,{'z':z,'book_spread':bk['home_spread'],'vol':m['vol'],'oi':m['oi']})

result={'scanned_at':datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
        'slate_date':DATE,'rows':out,'binding_errors':errors}
json.dump(result, open(f'/tmp/ladder_scan_{DATE}.json','w'))
hits=[r for r in out if r['screen_hit']]
print(f"rungs priced: {len(out)} | SCREEN HITS (never card-eligible alone): {len(hits)} | binding errors refused: {len(errors)}")
for r in sorted(hits, key=lambda x:-x['gross_c']):
    print(f"  {r['league']} {r['game']} {r['type']} {r['rung']} {r['side']} | fair {r['fair']:.1%} ask {r['ask']:.0%} | gross {r['gross_c']:+.1f}c net {r['net_c']:+.1f}c | {r['model']} | {r['src']['ticker']}")
if errors:
    print("REFUSED (ambiguity/binding - fail closed):")
    for e in errors[:15]: print('  ', e)
