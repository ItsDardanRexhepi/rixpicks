#!/usr/bin/env python3
"""Stage 0 spread/total DIVERGENCE screen (J-121). No model fair yet for totals; spreads get
book-consensus divergence only unless a model margin exists upstream. Output: /tmp/st_screen_<date>.json
Flags: book-vs-book spread disagreement >=1.5pt or total >=2.0pt across the 6 books; price outliers.
Every row labeled screen_only=True (divergence screen, NOT an evaluation - J-112 semantics)."""
import json,sys,datetime,statistics
import os
games=json.load(open(os.environ.get('ST_IN','/tmp/odds_prefill_st.json')))
rows=[]
for g in games:
    hs=[(b,v['spread_home_pts']) for b,v in g['books'].items() if v.get('spread_home_pts') is not None]
    tt=[(b,v['total_pts']) for b,v in g['books'].items() if v.get('total_pts') is not None]
    flags=[]
    if len(hs)>=3:
        pts=[p for _,p in hs]
        if max(pts)-min(pts)>=1.5: flags.append(f"spread divergence {min(pts)}..{max(pts)} across {len(hs)} books")
    if len(tt)>=3:
        pts=[p for _,p in tt]
        if max(pts)-min(pts)>=2.0: flags.append(f"total divergence {min(pts)}..{max(pts)} across {len(tt)} books")
    med_spread=statistics.median([p for _,p in hs]) if hs else None
    med_total=statistics.median([p for _,p in tt]) if tt else None
    rows.append({'away':g['away'],'home':g['home'],'commence':g['commence'],
                 'n_books':len(g['books']),'consensus_home_spread':med_spread,'consensus_total':med_total,
                 'flags':flags,'screen_only':True,'note':'divergence screen - no model fair; not an evaluation'})
out=os.environ.get('ST_OUT','/tmp/st_screen_'+datetime.date.today().isoformat()+'.json')
json.dump(rows,open(out,'w'))
flagged=[r for r in rows if r['flags']]
print(f"{len(rows)} games screened -> {out}; {len(flagged)} flagged")
for r in flagged: print(' FLAG', r['away'],'@',r['home'],'|', '; '.join(r['flags']))
