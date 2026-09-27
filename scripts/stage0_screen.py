#!/usr/bin/env python3
"""PRODUCTION Stage 0 call site (J-121/J-122): runs the real chain for today's majors:
odds_prefill_st.py (books spreads+totals) -> st_screen.py (divergence) -> J-122 Kalshi gate
via core.pipeline + core.kalshi_bind against the captured open-markets feed.
Usage: stage0_screen.py [kalshi_feed_path]   (default /tmp/kalshi_open_by_league.json)
Writes /tmp/stage0_gate_<date>.json + prints gate decisions. Screen-only unless gated."""
import json, os, subprocess, sys
from datetime import datetime, timezone
sys.path.insert(0, '/home/sandbox/rix_tmp')
from core import pipeline, kalshi_bind
def main():
    date = datetime.now().strftime('%Y-%m-%d')
    prefill = '/tmp/odds_prefill_st.json'; screen = f'/tmp/st_screen_{date}.json'
    env = dict(os.environ)
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), 'odds_prefill_st.py'),
                    'americanfootball_ncaaf', 'americanfootball_nfl', 'baseball_mlb'],
                   check=True, env=env)
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), 'st_screen.py')],
                   check=True, env=env)
    rows = json.load(open(screen))
    feed = sys.argv[1] if len(sys.argv) > 1 else '/tmp/kalshi_open_by_league.json'
    log = []
    out = pipeline.run_stage0(rows, lambda a, h, cls: kalshi_bind.bind_from_feed(feed, a, h, '', cls, 'home' if cls == 'spread' else 'over'), log_lines=log)
    res = {'ts': datetime.now(timezone.utc).isoformat(), 'date': date, **out}
    dest = f'/tmp/stage0_gate_{date}.json'
    json.dump(res, open(dest, 'w'), indent=1)
    for l in log: print(l)
    print(f'cardable: {len(out["cardable"])} | screen-only: {len(out["screen_only"])} -> {dest}')
if __name__ == '__main__': main()
