#!/usr/bin/env python3
"""PRODUCTION Stage 0 call site (J-121/J-122): odds_prefill_st.py -> st_screen.py ->
slate join (event identity + abbrs) -> canonical Kalshi bind -> J-122 gate.
Usage: stage0_screen.py [kalshi_feed] [slate_json]
Defaults: /tmp/kalshi_open_by_league.json, /tmp/slate_day_<today>.json."""
import json, os, re, subprocess, sys
from datetime import datetime, timezone
sys.path.insert(0, '/home/sandbox/rix_tmp')
from core import pipeline, kalshi_bind
def toks(name): return {w for w in re.findall(r'[A-Za-z]+', (name or '').upper()) if len(w) >= 4}
def _close(t1, t2, hours=1.5):
    from datetime import datetime as _dt
    try:
        a = _dt.fromisoformat(t1.replace('Z', '+00:00')); b = _dt.fromisoformat(t2.replace('Z', '+00:00'))
        return abs((a - b).total_seconds()) <= hours * 3600
    except Exception:
        return False
CROSSWALK = '/tmp/provider_espn_crosswalk.json'
def _load_cw():
    try: return json.load(open(CROSSWALK))
    except Exception: return {}
def join_slate(row, slate_rows, crosswalk):
    """Resolve the ESPN canonical competition ID. Requires: provider_event_id present,
    team-word match, commence corroboration (<=90min), and crosswalk consistency - a
    provider ID already mapped to a DIFFERENT ESPN id is a conflict and fails closed.
    Returns (slate_row, status)."""
    pid = row.get('provider_event_id')
    if not pid: return None, 'missing provider_event_id'
    a, h = toks(row['away']), toks(row['home'])
    cands = [s for s in slate_rows if toks(s.get('away')) & a and toks(s.get('home')) & h]
    timed = [s for s in cands if _close(row.get('commence', ''), s.get('commence_utc', ''))]
    if len(timed) != 1:
        return None, f'{len(timed)} corroborated candidates (need exactly 1)'
    espn_id = timed[0]['instance_id']
    prev = crosswalk.get(pid)
    if prev and prev != espn_id:
        return None, f'crosswalk conflict: provider {pid} mapped {prev}, now {espn_id}'
    crosswalk[pid] = espn_id
    return timed[0], 'ok'
def main():
    date = datetime.now().strftime('%Y-%m-%d')
    feed = sys.argv[1] if len(sys.argv) > 1 else '/tmp/kalshi_open_by_league.json'
    slate_path = sys.argv[2] if len(sys.argv) > 2 else f'/tmp/slate_day_{date}.json'
    env = dict(os.environ)
    here = os.path.dirname(__file__)
    subprocess.run([sys.executable, os.path.join(here, 'odds_prefill_st.py'),
                    'americanfootball_ncaaf', 'americanfootball_nfl', 'baseball_mlb'], check=True, env=env)
    subprocess.run([sys.executable, os.path.join(here, 'st_screen.py')], check=True, env=env)
    screen = os.environ.get('ST_OUT', f'/tmp/st_screen_{date}.json')
    rows = json.load(open(screen))
    try: slate_rows = json.load(open(slate_path))['rows']
    except Exception as e:
        slate_rows = []
        print(f'WARN: slate {slate_path} unavailable ({e}) - all rows screen-only (no event identity)')
    crosswalk = _load_cw()
    for r in rows:
        s2, why = join_slate(r, slate_rows, crosswalk)
        if s2:
            r['event_id'] = s2['instance_id']; r['away_abbr'] = s2.get('away_abbr'); r['home_abbr'] = s2.get('home_abbr')
        else:
            r['join_rejected'] = why
    json.dump(crosswalk, open(CROSSWALK, 'w'))
    log = []
    out = pipeline.run_stage0(
        rows,
        lambda row, cls, side: kalshi_bind.bind_event(
            feed, row.get('event_id'), row.get('away_abbr'), row.get('home_abbr'), cls, side,
            commence_utc=row.get('commence'),
            line_hint=(row.get('consensus_home_spread') if cls == 'spread' else row.get('consensus_total')),
            line_tol=1.5 if cls == 'spread' else 2.5),
        log_lines=log)
    dest = f'/tmp/stage0_gate_{date}.json'
    json.dump({'ts': datetime.now(timezone.utc).isoformat(), 'date': date, **out}, open(dest, 'w'), indent=1)
    for l in log: print(l)
    print(f'gate_passed (NOT carded): {len(out["gate_passed"])} | screen-only: {len(out["screen_only"])} -> {dest}')
if __name__ == '__main__': main()
