#!/usr/bin/env python3
"""Stage 0 spread/total DIVERGENCE screen (J-121). Rows carry provider_event_id through.
Every row is screen_only=True: a divergence flag is NEVER an evaluation and NEVER a card -
carding requires model fair + standards + the J-119/J-120 2-check bar downstream."""
import json, sys, datetime, statistics, os
games = json.load(open(os.environ.get('ST_IN', '/tmp/odds_prefill_st.json')))
rows = []
for g in games:
    hs = [(b, v['spread_home_pts']) for b, v in g['books'].items() if v.get('spread_home_pts') is not None]
    tt = [(b, v['total_pts']) for b, v in g['books'].items() if v.get('total_pts') is not None]
    flags = []
    if len(hs) >= 3:
        pts = [p for _, p in hs]
        if max(pts) - min(pts) >= 1.5: flags.append(f"spread divergence {min(pts)}..{max(pts)} across {len(hs)} books")
    if len(tt) >= 3:
        pts = [p for _, p in tt]
        if max(pts) - min(pts) >= 2.0: flags.append(f"total divergence {min(pts)}..{max(pts)} across {len(tt)} books")
    rows.append({'away': g['away'], 'home': g['home'], 'commence': g['commence'],
                 'provider_event_id': g.get('provider_event_id'),
                 'n_books': len(g['books']),
                 'consensus_home_spread': statistics.median([p for _, p in hs]) if hs else None,
                 'consensus_total': statistics.median([p for _, p in tt]) if tt else None,
                 'flags': flags, 'screen_only': True,
                 'note': 'divergence screen - no model fair; not an evaluation; never a card by itself'})
out = os.environ.get('ST_OUT', '/tmp/st_screen_' + datetime.date.today().isoformat() + '.json')
json.dump(rows, open(out, 'w'))
flagged = [r for r in rows if r['flags']]
print(f"{len(rows)} games screened -> {out}; {len(flagged)} flagged")
for r in flagged: print(' FLAG', r['away'], '@', r['home'], '|', '; '.join(r['flags']))
