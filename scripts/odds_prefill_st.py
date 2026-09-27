#!/usr/bin/env python3
"""Stage 0 (J-121 EVERYTHING scope): spreads + totals prefill from The Odds API free tier.
Usage: odds_prefill_st.py <sport_key>...
Writes $ODDS_PREFILL_ST_OUT (default /tmp/odds_prefill_st.json): rows carry provider_event_id
(the Odds API event id) for downstream canonical identity resolution.
J-123 budget: every real pull passes core.budget.check_and_log (2 credits/sport) BEFORE the
API call - cap refusal blocks the pull. API key read lazily, only for real pulls.
$ODDS_PREFILL_ST_FIXTURE (e2e only): canned API response; no key read, no budget, no network."""
import json, sys, urllib.request, urllib.error, os
sys.path.insert(0, '/home/sandbox/rix_tmp')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root - core/ import on GHA runners
OUT = os.environ.get('ODDS_PREFILL_ST_OUT', '/tmp/odds_prefill_st.json')
FIXTURE = os.environ.get('ODDS_PREFILL_ST_FIXTURE')
_K = None
def api_key():
    global _K
    if _K is None:
        _K = (os.environ.get('THE_ODDS_API_KEY') or open('/home/sandbox/.odds_api_key').read()).strip()
    return _K
out = {}
for sport in sys.argv[1:]:
    if FIXTURE:
        data = json.load(open(FIXTURE)); rem = 'fixture'
    else:
        from core import budget
        budget.check_and_log(sport, 'spreads,totals', 2)   # J-123: cap refusal stops the pull
        url = (f"https://api.the-odds-api.com/v4/sports/{sport}/odds/?apiKey={api_key()}"
               "&regions=us&markets=spreads,totals&oddsFormat=american"
               "&bookmakers=fanduel,draftkings,betmgm,betrivers,espnbet,hardrockbet")
        req = urllib.request.Request(url, headers={'User-Agent': 'curl/8'})
        with urllib.request.urlopen(req, timeout=30) as r:
            rem = r.headers.get('x-requests-remaining'); data = json.load(r)
    print(f"{sport}: {len(data)} events, credits remaining {rem}", file=sys.stderr)
    for e in data:
        key = (e['away_team'], e['home_team'], e.get('commence_time'))
        rec = out.setdefault(key, {'provider_event_id': e.get('id'), 'sport': sport, 'books': {}})
        for b in e.get('bookmakers', []):
            ent = {}
            for m in b.get('markets', []):
                if m['key'] == 'spreads':
                    for o in m.get('outcomes', []):
                        if o['name'] == e['home_team']: ent['spread_home_pts'] = o.get('point'); ent['spread_home_price'] = o.get('price')
                        elif o['name'] == e['away_team']: ent['spread_away_price'] = o.get('price')
                elif m['key'] == 'totals':
                    for o in m.get('outcomes', []):
                        if o['name'] == 'Over': ent['total_pts'] = o.get('point'); ent['over_price'] = o.get('price')
                        elif o['name'] == 'Under': ent['under_price'] = o.get('price')
            if ent: rec['books'][b['key']] = ent
rows = [{'away': k[0], 'home': k[1], 'commence': k[2], 'sport': v['sport'],
         'provider_event_id': v['provider_event_id'], 'books': v['books']} for k, v in out.items()]
json.dump(rows, open(OUT, 'w'))
# Pregame snapshot (fair-model input): first pull BEFORE a game's commence freezes its lines
# forever; in-window refreshes carry live lines (grading fodder) and never touch the snapshot.
SNAP = os.environ.get('ODDS_PREFILL_ST_SNAPSHOT')
if SNAP:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    try: snap_list = json.load(open(SNAP))
    except Exception: snap_list = []
    snap = {}
    for r0 in snap_list:
        gk0 = '|'.join([r0.get('sport', ''), r0['away'], r0['home'], r0.get('commence') or ''])
        snap[gk0] = r0
    for r in rows:
        gk = '|'.join([r['sport'], r['away'], r['home'], r['commence'] or ''])
        if gk in snap: continue
        try:
            ct = datetime.fromisoformat((r['commence'] or '').replace('Z', '+00:00'))
        except Exception:
            continue
        if ct > now:
            snap[gk] = {**r, 'snapshot_at': now.isoformat()}
    json.dump(list(snap.values()), open(SNAP, 'w'))
    print(f"snapshot: {len(snap)} frozen pregame games -> {SNAP}", file=sys.stderr)
print(f"wrote {OUT} ({len(out)} games)")
