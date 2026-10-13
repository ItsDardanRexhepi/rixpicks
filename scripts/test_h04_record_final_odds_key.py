#!/usr/bin/env python3
"""Hardening H-04 (follow-up, 2026-10-13): the GitHub Actions record write must be able to read the odds-api
second source. CBS's dated college-football page carries no game cards and its MLS page is gone, so on Actions a
college-football or MLS final is confirmed only by the odds-api scores reader - which skips when the job has no
THE_ODDS_API_KEY. Without the key every such final is refused (exit 3) and every later final waits behind it.
Pinned here:
 - the record_final step in .github/workflows/record_final.yml gets THE_ODDS_API_KEY from the repo secret;
 - the odds-api reader asks for the widest window the endpoint serves (daysFrom=3), so a final the grader sends a
   day or two late is still confirmable;
 - with the key present, a college-football and an MLS final are confirmed through that reader (fixtures, offline).
Run: python3 scripts/test_h04_record_final_odds_key.py"""
import os, re, sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
failures = 0


def check(name, actual, expected):
    global failures
    ok = actual == expected
    print(('OK  ' if ok else 'FAIL'), name, '' if ok else f'(got {actual!r}, want {expected!r})')
    if not ok:
        failures += 1


def record_step(text):
    """The workflow step whose run line is `python3 scripts/record_final.py`, as its own text block."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if re.search(r'run:\s*python3 scripts/record_final\.py\s*$', ln):
            start = i
            while start > 0 and not lines[start].lstrip().startswith('- name:'):
                start -= 1
            end = i + 1
            while end < len(lines) and not lines[end].lstrip().startswith('- name:'):
                end += 1
            return '\n'.join(lines[start:end])
    return ''


wf = open(os.path.join(ROOT, '.github/workflows/record_final.yml')).read()
step = record_step(wf)
check('h04: the record_final step exists in the workflow', bool(step), True)
check('h04: the record_final step is given THE_ODDS_API_KEY from the repo secret',
      bool(re.search(r'^\s*env:\s*$', step, re.M)) and
      bool(re.search(r'^\s*THE_ODDS_API_KEY:\s*\$\{\{\s*secrets\.THE_ODDS_API_KEY\s*\}\}\s*$', step, re.M)), True)

sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import second_source as ss  # noqa: E402

src = open(os.path.join(HERE, 'second_source.py')).read()
check('h04: the odds-api scores read asks for daysFrom=3 (the widest window it serves)',
      'daysFrom=3' in src and 'daysFrom=2' not in src, True)

GAMES = {
    'americanfootball_ncaaf': [{'home_team': 'Oklahoma Sooners', 'away_team': 'Texas Longhorns', 'completed': True,
                                'scores': [{'name': 'Texas Longhorns', 'score': '24'},
                                           {'name': 'Oklahoma Sooners', 'score': '27'}]}],
    'soccer_usa_mls': [{'home_team': 'St. Louis City SC', 'away_team': 'LA Galaxy', 'completed': True,
                        'scores': [{'name': 'LA Galaxy', 'score': '2'}, {'name': 'St. Louis City SC', 'score': '6'}]}],
}
seen = []


def fake_get(url, timeout=20, ua=None):
    seen.append(url)
    sport = url.split('/sports/')[1].split('/')[0]
    return GAMES.get(sport, [])


ss._get = fake_get
ss._odds_cache.clear()
ss.budget.check_and_log = lambda *a, **k: None
os.environ['THE_ODDS_API_KEY'] = 'fixture-not-a-key'
when = datetime(2026, 10, 11, 19, 30, tzinfo=timezone.utc)
cfb = ss.odds_api_final({'espn_league': 'football/college-football'},
                        {'home': 'Oklahoma Sooners', 'away': 'Texas Longhorns'}, when)
check('h04: with the key, a college-football final is confirmed by the odds-api',
      (cfb or {}).get('away_score'), 24)
check('h04: ... home score', (cfb or {}).get('home_score'), 27)
mls = ss.odds_api_final({'espn_league': 'soccer/usa.1'}, {'home': 'St. Louis City SC', 'away': 'LA Galaxy'}, when)
check('h04: with the key, an MLS final is confirmed by the odds-api', ((mls or {}).get('away_score'),
      (mls or {}).get('home_score')), (2, 6))
check('h04: every odds-api read used daysFrom=3', all('daysFrom=3' in u for u in seen) and len(seen) == 2, True)

print('h04 odds key:', 'FAIL' if failures else 'PASS', failures)
sys.exit(1 if failures else 0)
