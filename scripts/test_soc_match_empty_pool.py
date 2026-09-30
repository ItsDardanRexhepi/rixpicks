#!/usr/bin/env python3
"""Stalled-map regression (Sep 29 X-credits-wall class): when the X pool is EMPTY but news
keeps advancing, soc_match must BUILD an honest generation-matched zero-pair map (degraded
marker, post_count 0, zero NIM spend) instead of raising and holding the prior map - a held
stale generation blanks both paired carousels on cold clients (rpMapFresh exact-match).
News-empty must still hard-raise (never an empty news map).

Run: python3 scripts/test_soc_match_empty_pool.py
"""
import json, os, subprocess, sys, tempfile

SOC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'soc_match.py')

def run_case(news_items, x_items, x_gen):
    with tempfile.TemporaryDirectory() as d:
        sl = os.path.join(d, 'slates'); os.makedirs(sl)
        json.dump({'generated_at': '2026-09-29T23:20:03+00:00', 'latest': news_items}, open(os.path.join(sl, 'news.json'), 'w'))
        json.dump({'generated_at': x_gen, 'source': 'x_recent_search', 'window': False, 'items': x_items}, open(os.path.join(sl, 'x_feed.json'), 'w'))
        json.dump({'build': 1790723400}, open(os.path.join(sl, 'build.json'), 'w'))
        env = dict(os.environ); env.pop('NVIDIA_API_KEY', None); env.pop('NIM_API_KEY', None)
        r = subprocess.run([sys.executable, SOC], cwd=d, env=env, capture_output=True, text=True, timeout=120)
        m = None
        mp = os.path.join(sl, 'soc_match.json')
        if os.path.exists(mp):
            m = json.load(open(mp))
        return r, m

fails = 0
def check(label, cond):
    global fails
    print(('OK   ' if cond else 'FAIL ') + label)
    if not cond: fails += 1

news = [{'headline': 'Braves take wild card game', 'link': 'https://ex.com/s1', 'blurb': 'Atlanta advances',
         'league': 'baseball/mlb', 'published': '2026-09-29T22:00:00Z', 'source': 'ESPN'}]

# Case 1: empty X pool, fresh news -> honest zero-pair map, exit 0, no NIM (no keys in env)
r, m = run_case(news, [], '2026-09-29T23:20:20+00:00')
check('empty pool exits 0 (no raise, no NIM needed)', r.returncode == 0)
check('map written', m is not None)
if m:
    check('generation-matched news stamp', m.get('news_generated_at') == '2026-09-29T23:20:03+00:00')
    check('generation-matched x stamp', m.get('x_generated_at') == '2026-09-29T23:20:20+00:00')
    check('zero pairs/more/nearest/latest', not m.get('pairs') and not m.get('more') and not m.get('nearest') and not m.get('latest'))
    check('post_count 0', m.get('post_count') == 0)
    check('degraded marker', m.get('degraded') == 'x_feed_empty')
    check('zero probes', (m.get('audit') or {}).get('probes_used') == 0)
    check('admit empty', m.get('admit') == [])

# Case 2: empty NEWS still hard-raises (map not written)
r, m = run_case([], [], '2026-09-29T23:20:20+00:00')
check('empty news raises (nonzero exit)', r.returncode != 0)
check('empty news writes no map', m is None)

print('PASS' if fails == 0 else f'{fails} FAILURES')
sys.exit(1 if fails else 0)
