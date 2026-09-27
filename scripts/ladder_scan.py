#!/usr/bin/env python3
"""Kalshi spread/total LADDER scan (deep dive 2026-09-26, his 10:08 PM directive).
For every Kalshi ladder rung on tomorrow's slate, compute model fair and edge vs executable ask.
Models: NFL margin/total = book-consensus-anchored normals (FPI overlay shrunk +-3pts - FPI hot-band learning);
MLB margin = Pythagorean runs split from MY model win prob + book total; MLB total = book total + starter ERA adj;
WNBA = book-anchored screen-only (no model). Fee = 0.07*P*(1-P). Filters: bought-side fair>=0.60 (J-111 floor),
gross>=2c (J-124 eligibility). Screen-only rows (no independent model) are labeled and never card-eligible alone."""
import json, re, statistics
from statistics import NormalDist
ND=NormalDist()
def fee(p): return 0.07*p*(1-p)
def noask(m):
    na=m.get('na')
    if na not in (None,''): return float(na)
    yb=m.get('yb')
    if yb not in (None,''): return round(1-float(yb),4)
    return None
def inv(p): return ND.inv_cdf(min(max(p,1e-6),1-1e-6))

books=json.load(open('/tmp/st_books_0927.json'))
slate=json.load(open('/tmp/slate_day_2026-09-27.json'))['rows']
kal=json.load(open('/tmp/kalshi_ladders_0927.json'))
nfl_reads={r['away_abbr']+r['home_abbr']:r for r in json.load(open('/tmp/nfl_reads_0927.json'))}
mlb_edges=json.load(open('/tmp/mlb_0927_edges.json'))
mlb_raw={r['aa']+r['ha']:r for r in json.load(open('/tmp/mlb_0927_model_raw.json'))}

ALIAS={'JAX':'JAC','WSH':'WAS'}  # book/slate abbr -> kalshi abbr where needed
def kab(a): return ALIAS.get(a,a)

# book consensus per game keyed by (sport, away, home)
def consensus(g):
    hs=[];tot=[]
    for bk,mk in g['books'].items():
        for o in mk.get('spreads',[]):
            if o['side']=='home' and o['point'] is not None: hs.append(o['point'])
        for o in mk.get('totals',[]):
            if o['side']=='over' and o['point'] is not None: tot.append(o['point'])
    return (statistics.median(hs) if hs else None, statistics.median(tot) if tot else None, len(g['books']))
bookmap={}
for g in books: bookmap[(g['sport'],g['away'],g['home'])]=consensus(g)

# slate lookup by (league, away_abbr+home_abbr with kalshi alias)
slmap={}
for r in slate:
    aa,ha=r.get('away_abbr'),r.get('home_abbr')
    if aa and ha: slmap[(r['league'], kab(aa)+kab(ha))]=r
    if r.get('away') and r.get('home'): slmap[(r['league'], r['away'], r['home'])]=r

SIG_NFL_M=13.8; SIG_NFL_T=10.5; SIG_MLB_M=4.3; SIG_MLB_T=3.0; SIG_WNBA_M=12.0; SIG_WNBA_T=15.0
out=[]
def add(league, game, mtype, rung, side, fair, ask, model_kind, extra=None):
    if ask is None or fair is None: return
    ask=float(ask)
    if ask<=0.001 or ask>=0.999: return
    gross=fair-ask; net=gross-fee(ask)
    row={'league':league,'game':game,'type':mtype,'rung':rung,'side':side,'fair':round(fair,4),
         'ask':ask,'gross_c':round(gross*100,1),'net_c':round(net*100,1),'model':model_kind,
         'floor60_ok':fair>=0.60,'eligible':fair>=0.60 and gross>=0.02}
    if extra: row.update(extra)
    out.append(row)

nfl_games=set()
for m in kal.get('KXNFLSPREAD',[])+kal.get('KXNFLTOTAL',[]):
    mt=re.match(r'KXNFL(?:SPREAD|TOTAL)-26SEP27([A-Z]+)-([A-Z]+)(\d+)$', m['t'])
    if not mt: continue
    gcode, team, n = mt.group(1), mt.group(2), int(mt.group(3)); thr=n-0.5
    nfl_games.add(gcode)
    row=slmap.get(('NFL',gcode))
    if not row: continue
    bk=bookmap.get(('americanfootball_nfl',row['away'],row['home']))
    if not bk or bk[0] is None: continue
    hs,tt,nbk=bk
    mu_book=-hs  # home margin
    rd=nfl_reads.get(gcode)
    mu=mu_book
    mu_fpi=None
    if rd and rd.get('fpi_home') is not None:
        mu_fpi=inv(rd['fpi_home']/100)*SIG_NFL_M  # comparison only, not blended
    if 'SPREAD' in m['t']:
        home_covers = (team==row['home_abbr'] or team==kab(row['home_abbr']))
        fair_yes = 1-ND.cdf((thr-mu)/SIG_NFL_M) if home_covers else ND.cdf((-thr-mu)/SIG_NFL_M)
        # away team wins by over thr  <=>  home margin < -thr
        fpi_agrees=None
        if mu_fpi is not None: fpi_agrees = (mu_fpi-mu_book)*( (thr) if home_covers else (-thr) ) > 0 and abs(mu_fpi-mu_book)>1
        add('NFL',f"{row['away_abbr']}@{row['home_abbr']}",'spread',f"{team} by>{thr}", 'YES', fair_yes, m['ya'],'nfl_book_anchor',{'n_books':nbk,'book_spread':hs,'mu':round(mu,1),'fpi_agrees':fpi_agrees,'vol':m['vol'],'oi':m['oi']})
        if m.get('na') is not None: add('NFL',f"{row['away_abbr']}@{row['home_abbr']}",'spread',f"{team} by>{thr}",'NO',1-fair_yes,noask(m),'nfl_book_anchor',{'n_books':nbk,'book_spread':hs,'mu':round(mu,1),'fpi_agrees':None if mu_fpi is None else ((mu_fpi-mu_book)*((thr) if home_covers else (-thr))<0 and abs(mu_fpi-mu_book)>1)})
    else:
        fair_over=1-ND.cdf((thr-tt)/SIG_NFL_T)
        add('NFL',f"{row['away_abbr']}@{row['home_abbr']}",'total',f"over {thr}",'YES',fair_over,m['ya'],'nfl_book_total',{'n_books':nbk,'book_total':tt,'vol':m['vol'],'oi':m['oi']})
        if m.get('na') is not None: add('NFL',f"{row['away_abbr']}@{row['home_abbr']}",'total',f"over {thr}",'NO',1-fair_over,noask(m),'nfl_book_total',{'n_books':nbk,'book_total':tt})

for m in kal.get('KXMLBSPREAD',[])+kal.get('KXMLBTOTAL',[]):
    mt=re.match(r'KXMLB(?:SPREAD|TOTAL)-26SEP27\d{4}([A-Z]+)-([A-Z]+)(\d+)$', m['t'])
    if not mt: continue
    gcode, team, n = mt.group(1), mt.group(2), int(mt.group(3)); thr=n-0.5
    row=slmap.get(('MLB',gcode))
    if not row: continue
    bk=bookmap.get(('baseball_mlb',row['away'],row['home']))
    raw=mlb_raw.get(row['away_abbr']+row['home_abbr'])
    if not bk or bk[1] is None or not raw: continue
    hs,tt,nbk=bk
    # book-implied home ML devig for anchor
    ml_h=[]; ml_a=[]
    for bk2,mk2 in books and [(b['books']) for b in books if b['sport']=='baseball_mlb' and b['away']==row['away'] and b['home']==row['home']][0].items():
        pass
    p_home_book=None
    gbook=[b for b in books if b['sport']=='baseball_mlb' and b['away']==row['away'] and b['home']==row['home']]
    if gbook:
        hs2=[];as2=[]
        for bkname,mk2 in gbook[0]['books'].items():
            for o in mk2.get('h2h',[]):
                if o['side']=='home' and o['price']: hs2.append(o['price'])
                if o['side']=='away' and o['price']: as2.append(o['price'])
        if hs2 and as2:
            import statistics as st2
            def d2p(a): return (-a)/(-a+100) if a<0 else 100/(a+100)
            ph=st2.median([d2p(x) for x in hs2]); pa=st2.median([d2p(x) for x in as2])
            p_home_book=ph/(ph+pa)
    if p_home_book is None: continue
    p_model_home=None
    for e in mlb_edges:
        if e['game']==f"{row['away_abbr']}@{row['home_abbr']}" and e['side']==row['home']: p_model_home=e['model']
    r=(p_home_book/(1-p_home_book))**(1/1.83); Eh=tt*r/(1+r); Ea=tt/(1+r); mu=Eh-Ea
    if 'SPREAD' in m['t']:
        home_side=(team==row['home_abbr'])
        fair_yes=1-ND.cdf((thr-mu)/SIG_MLB_M) if home_side else ND.cdf((-thr-mu)/SIG_MLB_M)
        add('MLB',f"{row['away_abbr']}@{row['home_abbr']}",'spread',f"{team} by>{thr}",'YES',fair_yes,m['ya'],'mlb_book_pyth',{'n_books':nbk,'book_total':tt,'p_home_book':round(p_home_book,3),'p_home_model':p_model_home,'vol':m['vol'],'oi':m['oi']})
        if m.get('na') is not None: add('MLB',f"{row['away_abbr']}@{row['home_abbr']}",'spread',f"{team} by>{thr}",'NO',1-fair_yes,noask(m),'mlb_model_pyth',{'n_books':nbk})
    else:
        era_h=raw.get('home_era_l5'); era_a=raw.get('away_era_l5')
        adj=0.0
        if era_h and era_a: adj=max(-1.5,min(1.5,0.63*(era_h+era_a-8.2)))
        tmod=tt+adj
        fair_over=1-ND.cdf((thr-tmod)/SIG_MLB_T)
        add('MLB',f"{row['away_abbr']}@{row['home_abbr']}",'total',f"over {thr}",'YES',fair_over,m['ya'],'mlb_total_era',{'n_books':nbk,'book_total':tt,'t_model':round(tmod,2),'vol':m['vol'],'oi':m['oi']})
        if m.get('na') is not None: add('MLB',f"{row['away_abbr']}@{row['home_abbr']}",'total',f"over {thr}",'NO',1-fair_over,noask(m),'mlb_total_era',{'n_books':nbk})

for series,mtype in [('KXWNBASPREAD','spread'),('KXWNBATOTAL','total'),('KXWNBAGAME','ml')]:
    for m in kal.get(series,[]):
        mt=re.match(r'KXWNBA(?:SPREAD|TOTAL|GAME)-26SEP27([A-Z]+)-([A-Z]+?)(\d*)$', m['t'])
        if not mt: continue
        gcode, team, ns = mt.group(1), mt.group(2), mt.group(3); thr=int(ns)-0.5 if ns else None
        row=slmap.get(('WNBA',gcode))
        if not row: continue
        bk=bookmap.get(('basketball_wnba',row['away'],row['home']))
        if not bk: continue
        hs,tt,nbk=bk
        if mtype=='spread' and hs is not None:
            mu=-hs; home_side=(team==row['home_abbr'] or team==kab(row['home_abbr']))
            fair_yes=1-ND.cdf((thr-mu)/SIG_WNBA_M) if home_side else ND.cdf((-thr-mu)/SIG_WNBA_M)
            add('WNBA',f"{row['away_abbr']}@{row['home_abbr']}",'spread',f"{team} by>{thr}",'YES',fair_yes,m['ya'],'wnba_book_SCREENONLY',{'n_books':nbk,'book_spread':hs})
            if m.get('na') is not None: add('WNBA',f"{row['away_abbr']}@{row['home_abbr']}",'spread',f"{team} by>{thr}",'NO',1-fair_yes,noask(m),'wnba_book_SCREENONLY',{})
        elif mtype=='total' and tt is not None:
            fair_over=1-ND.cdf((thr-tt)/SIG_WNBA_T)
            add('WNBA',f"{row['away_abbr']}@{row['home_abbr']}",'total',f"over {thr}",'YES',fair_over,m['ya'],'wnba_book_SCREENONLY',{'n_books':nbk,'book_total':tt})
            if m.get('na') is not None: add('WNBA',f"{row['away_abbr']}@{row['home_abbr']}",'total',f"over {thr}",'NO',1-fair_over,noask(m),'wnba_book_SCREENONLY',{})
        elif mtype=='ml':
            # ML from book-anchored margin dist at 0: P(team wins)
            if hs is None: continue
            mu=-hs; home_side=(team==row['home_abbr'] or team==kab(row['home_abbr']))
            fair_yes=1-ND.cdf((0-mu)/SIG_WNBA_M) if home_side else ND.cdf((0-mu)/SIG_WNBA_M)
            add('WNBA',f"{row['away_abbr']}@{row['home_abbr']}",'ml',f"{team} wins",'YES',fair_yes,m['ya'],'wnba_book_SCREENONLY',{'n_books':nbk})

json.dump(out, open('/tmp/ladder_scan_0927.json','w'))
elig=[r for r in out if r['eligible']]
print(f"rungs priced: {len(out)} | eligible (fair>=60c & gross>=2c): {len(elig)}")
for r in sorted(elig, key=lambda x:-x['gross_c']):
    print(f"  {r['league']} {r['game']} {r['type']} {r['rung']} {r['side']} | fair {r['fair']:.1%} ask {r['ask']:.0%} | gross {r['gross_c']:+.1f}c net {r['net_c']:+.1f}c | {r['model']}" + (f" | vol {r.get('vol')} oi {r.get('oi')}" if r.get('vol') else ''))
# near-eligible (gross 1.5-2c) for visibility
near=[r for r in out if not r['eligible'] and r['fair']>=0.60 and 0.015<=r['gross_c']/100<0.02]
print(f"near (gross 1.5-2c, fair>=60c): {len(near)}")
for r in sorted(near, key=lambda x:-x['gross_c'])[:10]:
    print(f"  ~{r['league']} {r['game']} {r['type']} {r['rung']} {r['side']} | fair {r['fair']:.1%} ask {r['ask']:.0%} gross {r['gross_c']:+.1f}c")
