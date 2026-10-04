#!/usr/bin/env python3
"""Record pages fixture (sweep LS-03/OS-06/DI-03, LS-16/OS-09/DI-14, DI-M2, DI-12/CP-06):
build_history.py must
  - list EVERY graded day on record.html whatever the build clock says (the e6059dd1 build ran at
    Sep 30 17:32 PT, dropped Sep 30 as 'today', and nothing rebuilt it after midnight: the day
    list summed to 20-11 under a 21-11 header) - static blocks add up to the Overall line;
  - never render an empty 'What the system learned' box: a filed brief shows, an unfiled one
    says so plainly, nothing is invented;
  - render a pick's display-only 'learning' text (escaped) under the pick;
  - never title a stale day 'Yesterday' in static HTML: yesterday.html reads 'Last graded day'
    and carries the last two graded days for the view-time selector (behaviour in
    test_record_pages.js).
Bite-proof: red on the pre-fix build_history.py.
Run: python3 scripts/test_build_history.py"""
import contextlib, datetime, importlib.util, io, json, os, re, shutil, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__))
failures = 0

def check(name, actual, expected):
    global failures
    ok = actual == expected
    print(('OK  ' if ok else 'FAIL'), name, '' if ok else f'(got {actual!r}, want {expected!r})')
    if not ok:
        failures += 1

def pk(name, res, score, **x):
    p = {'name': name, 'game': 'vs Somebody', 'odds': '-110', 'units': '5u', 'result': res, 'score': score}
    p.update(x)
    return p

HIST = {'days': [
    {'date': '2026-09-27', 'label': 'Sunday, Sep 27', 'record': '1-1', 'units': '+0.50u',
     'brief': 'Two picks, one lesson: the close moved against the loser.',
     'picks': [pk('Lions ML', 'W', 'NYJ 10, DET 27', note='Controlled from the first drive.'), pk('Bengals ML', 'L', 'CIN 17, PIT 20')]},
    {'date': '2026-09-29', 'label': 'Tuesday, Sep 29', 'record': '1-1', 'units': '+0.00u', 'brief': '',
     'picks': [pk('Bruins ML', 'W', 'NYR 0, BOS 3', learning='Owner-carded <override> class: one data point.'),
               pk('Maple Leafs ML', 'L', 'MTL 3, TOR 2')]},
    {'date': '2026-09-30', 'label': 'Wednesday, Sep 30', 'record': '1-0', 'units': '+6.90u', 'brief': '',
     'picks': [pk('White Sox ML', 'W', 'CHW 7, HOU 3')]}]}

def build(at):
    """Run build_history.main with the wall clock pinned to `at` (PT); return (record, yesterday)."""
    spec = importlib.util.spec_from_file_location('build_history_under_test', os.path.join(HERE, 'build_history.py'))
    bh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bh)
    class Clock(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return at.astimezone(tz) if tz else at
    bh.datetime = types.SimpleNamespace(datetime=Clock, date=datetime.date, timedelta=datetime.timedelta)
    tmp = tempfile.mkdtemp(prefix='bh_test_')
    cwd = os.getcwd()
    try:
        os.chdir(tmp)
        json.dump(HIST, open('history.json', 'w'))
        with contextlib.redirect_stdout(io.StringIO()):
            bh.main('history.json')
        return open('record.html').read(), open('yesterday.html').read()
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)

from zoneinfo import ZoneInfo
PT = ZoneInfo('America/Los_Angeles')
rec, yes = build(datetime.datetime(2026, 9, 30, 17, 32, tzinfo=PT))      # graded the same PT evening
rec2, yes2 = build(datetime.datetime(2026, 10, 1, 21, 0, tzinfo=PT))     # a day later, no rebuild between

# LS-03 / OS-06 / DI-03: every graded day listed, and the static day blocks sum to the Overall line
labels = re.findall(r'<div class="dayhead"><span class="d">([^<]+)</span><span class="r">(\d+)-(\d+)</span>', rec)
days = [(l, int(w), int(lo)) for l, w, lo in labels if l != 'Overall']
check('record.html lists Sep 30 even when built on Sep 30 PT', 'Wednesday, Sep 30' in [d[0] for d in days], True)
check('record.html lists every graded day, newest first', [d[0] for d in days],
      ['Wednesday, Sep 30', 'Tuesday, Sep 29', 'Sunday, Sep 27'])
overall = re.search(r'id="rpOverall">(\d+)-(\d+)<', rec)
check('static day blocks add up to the Overall line', (sum(d[1] for d in days), sum(d[2] for d in days)),
      (int(overall.group(1)), int(overall.group(2))) if overall else None)
check('record.html does not depend on the build clock', rec == rec2, True)
check('each day block carries its date for the live Today section', re.findall(r'class="rpday" data-date="([^"]+)"', rec),
      ['2026-09-30', '2026-09-29', '2026-09-27'])

# LS-16 / OS-09 / DI-14: no empty learned box; unfiled briefs said plainly; filed briefs intact
EMPTY = '<span class="bt">What the system learned</span></div>'
check('record.html has no empty learned box', EMPTY in rec, False)
check('yesterday.html has no empty learned box', EMPTY in yes, False)
check('unfiled briefs say so plainly (Sep 29, Sep 30)', rec.count('No brief filed for this day.'), 2)
check('filed brief still renders', 'Two picks, one lesson: the close moved against the loser.' in rec, True)

# DI-M2: per-pick learning rendered, escaped
check('per-pick learning is internal: never rendered on the record page (Oct 3 rule)', 'one data point' in rec, False)
check('per-pick learning never raw HTML', '<override>' in rec, False)
check('pick note still renders', 'Controlled from the first drive.' in rec, True)

# DI-12 / CP-06: static yesterday.html never calls a stale day 'Yesterday'
check('yesterday.html static title is Last graded day', re.search(r'<title>([^<]+)</title>', yes).group(1),
      "Last graded day: 1-0 - 'RixPicks")
check('yesterday.html static status is Last graded day', re.search(r'<div class="status">([^<]+)</div>', yes).group(1),
      'Last graded day - Wednesday, Sep 30')
check('yesterday.html carries the last two graded days, older hidden',
      re.findall(r'class="rpday" data-date="([^"]+)"[^>]*?( hidden)?>', yes), [('2026-09-30', ''), ('2026-09-29', ' hidden')])
check('yesterday.html carries the view-time selector', 'no official picks' in yes and 'rpYdNone' in yes, True)
check('yesterday.html does not depend on the build clock', yes == yes2, True)

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
