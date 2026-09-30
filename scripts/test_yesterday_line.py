# K18 fixture (9/30 midnight QA): the home Yesterday line must follow the BUILD date and come
# from the canonical history.json ledger - a static manifest field lies after midnight.
# Bite-proof: fails against builders that render man['yesterday'] directly.
import json, os, re, subprocess, sys, tempfile
import datetime as _dtc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
failures = 0
def check(name, actual, expected):
    global failures
    ok = actual == expected
    print(('OK  ' if ok else 'FAIL'), name, '' if ok else f'(got {actual!r}, want {expected!r})')
    if not ok: failures += 1

for B in ('build_gh_page_v2.py', '_build_nocanon_v2.py'):
    src = open(os.path.join(ROOT, 'scripts', B)).read()
    i = src.find('def _hist_yesterday')
    check(f'{B}: _hist_yesterday helper exists', i >= 0, True)
    j = src.index('_hy = _hist_yesterday()')
    ns = {'json': json, 'os': os, '_dtc': _dtc, 'sys': sys}
    argv0 = sys.argv
    sys.argv = ['b', os.path.join(ROOT, 'manifest.json')]
    exec(src[i:j], ns)
    check(f'{B}: build-date 9/30 reads the Sep 29 ledger, not the stale manifest field',
          ns['_hist_yesterday']('2026-09-30'),
          '2-3 \u00b7 Braves ML W \u00b7 Yordan Alvarez over 1.5 hits L \u00b7 Loai Abushaar ML L \u00b7 Maple Leafs ML L \u00b7 Bruins ML W')
    check(f'{B}: build-date 9/29 honest zero (Sep 28 had no card)',
          ns['_hist_yesterday']('2026-09-29'), '0-0 - no official picks')
    check(f'{B}: build-date 9/24 reads Sep 23', ns['_hist_yesterday']('2026-09-24'),
          '2-0 \u00b7 Diamondbacks ML W \u00b7 Wings -10.5 W')
    sys.argv = argv0  # helper reads sys.argv[1] at CALL time - restore only after the calls
    check(f'{B}: home strip renders the computed line', '_hy or man[' in src, True)
    check(f'{B}: league strips hide on stale manifest', '_s=None if _mstale else _YBL.get(_tab)' in src, True)

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
