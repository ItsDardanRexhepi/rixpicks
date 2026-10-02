#!/usr/bin/env python3
"""Timestamp-only churn regression (live-site M2, Oct 2): 52 of 200 'x feed' commits changed
nothing but soc_match.json built_at (e.g. 975e299b), so every x-feed run pushed a commit, rebuilt
Pages and moved main under the other lanes. soc_match.py now keeps the served map when the only
difference is built_at and that built_at is younger than the heartbeat; a real change (news or X
generation, client build, pairs) or an aging built_at still rewrites it. The heartbeat keeps the
client's rpMapFresh 2h built_at window (index_v2.js) satisfied.

Run: python3 scripts/test_soc_match_heartbeat.py   (exit 1 on any failure)
"""
import json, os, subprocess, sys, tempfile
from datetime import datetime, timedelta, timezone

SOC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'soc_match.py')

fails = 0
def check(label, cond):
    global fails
    print(('OK   ' if cond else 'FAIL ') + label)
    if not cond:
        fails += 1

NEWS = [{'headline': 'Braves take wild card game', 'link': 'https://ex.com/s1', 'blurb': 'Atlanta advances',
         'league': 'baseball/mlb', 'published': '2026-09-29T22:00:00Z', 'source': 'ESPN'}]

def seed(d, news_gen='2026-09-29T23:20:03+00:00', x_gen='2026-09-29T23:20:20+00:00', build=1790723400):
    sl = os.path.join(d, 'slates'); os.makedirs(sl, exist_ok=True)
    json.dump({'generated_at': news_gen, 'latest': NEWS}, open(os.path.join(sl, 'news.json'), 'w'))
    json.dump({'generated_at': x_gen, 'source': 'x_recent_search', 'window': False, 'items': []}, open(os.path.join(sl, 'x_feed.json'), 'w'))
    json.dump({'build': build}, open(os.path.join(sl, 'build.json'), 'w'))

def build(d):
    env = dict(os.environ); env.pop('NVIDIA_API_KEY', None); env.pop('NIM_API_KEY', None)
    r = subprocess.run([sys.executable, SOC], cwd=d, env=env, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print(r.stdout[-400:], r.stderr[-400:])
    return r.returncode, open(os.path.join(d, 'slates', 'soc_match.json')).read()

def age_built_at(d, minutes):
    p = os.path.join(d, 'slates', 'soc_match.json')
    m = json.load(open(p))
    m['built_at'] = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    json.dump(m, open(p, 'w'))
    return open(p).read()

with tempfile.TemporaryDirectory() as d:
    seed(d)
    rc1, first = build(d)
    check('first build writes a map', rc1 == 0 and json.loads(first).get('built_at'))
    rc2, second = build(d)
    check('rebuild with nothing changed keeps the served map byte-identical (no timestamp-only commit)', rc2 == 0 and second == first)

    aged = age_built_at(d, 5)
    _, third = build(d)
    check('a 5-min-old identical map is kept', third == aged)

    age_built_at(d, 40)
    _, fourth = build(d)
    fresh = datetime.fromisoformat(json.loads(fourth)['built_at'])
    check('a map older than the heartbeat is refreshed (client 2h window never lapses)',
          datetime.now(timezone.utc) - fresh < timedelta(minutes=2))

    seed(d, news_gen='2026-09-29T23:35:03+00:00')
    _, fifth = build(d)
    check('a new news generation rewrites the map', json.loads(fifth)['news_generated_at'] == '2026-09-29T23:35:03+00:00')

    seed(d, news_gen='2026-09-29T23:35:03+00:00', build=1790723999)
    _, sixth = build(d)
    check('a new client build rewrites the map', json.loads(sixth).get('client_build') == 1790723999)

with tempfile.TemporaryDirectory() as d:
    seed(d)
    os.makedirs(os.path.join(d, 'slates'), exist_ok=True)
    open(os.path.join(d, 'slates', 'soc_match.json'), 'w').write('{corrupt')
    rc, out = build(d)
    check('an unreadable served map is replaced', rc == 0 and json.loads(out).get('built_at'))

if fails:
    print(f'SOC MATCH HEARTBEAT: {fails} FAILURES')
    sys.exit(1)
print('SOC MATCH HEARTBEAT: ALL PASS')
