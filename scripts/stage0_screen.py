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
def _close(t1, t2, hours=6):
    from datetime import datetime as _dt
    try:
        a = _dt.fromisoformat(t1.replace('Z', '+00:00')); b = _dt.fromisoformat(t2.replace('Z', '+00:00'))
        return abs((a - b).total_seconds()) <= hours * 3600
    except Exception:
        return False
def join_slate(row, slate_rows):
    """Resolve the ESPN canonical competition ID: team-word match corroborated by commence
    time (<=6h). Ambiguous or uncorroborated -> None (fail closed, row stays screen-only)."""
    a, h = toks(row['away']), toks(row['home'])
    cands = [s for s in slate_rows if toks(s.get('away')) & a and toks(s.get('home')) & h]
    if not cands: return None
    timed = [s for s in cands if _close(row.get('commence', ''), s.get('commence_utc', ''))]
    if len(timed) == 1: return timed[0]
    return None  # 0 = no time corroboration; >1 = ambiguous - both fail closed
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
    for r in rows:
        s = join_slate(r, slate_rows)
        if s:
            r['event_id'] = s['instance_id']; r['away_abbr'] = s.get('away_abbr'); r['home_abbr'] = s.get('home_abbr')
    log = []
    out = pipeline.run_stage0(
        rows,
        lambda row, cls, side: kalshi_bind.bind_event(feed, row.get('event_id'), row.get('away_abbr'),
                                                      row.get('home_abbr'), cls, side),
        log_lines=log)
    dest = f'/tmp/stage0_gate_{date}.json'
    json.dump({'ts': datetime.now(timezone.utc).isoformat(), 'date': date, **out}, open(dest, 'w'), indent=1)
    for l in log: print(l)
    print(f'gate_passed (NOT carded): {len(out["gate_passed"])} | screen-only: {len(out["screen_only"])} -> {dest}')
if __name__ == '__main__': main()
