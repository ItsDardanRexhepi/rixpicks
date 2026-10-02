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
    # CP-06 (Oct 1): the Home line links yesterday.html only while that page shows the line's day -
    # yesterday.html is rebuilt by record-final alone, so after midnight it still shows an older day
    d = tempfile.mkdtemp(prefix='rp-yline-')
    json.dump({'days': [
        {'date': '2026-09-29', 'label': 'Tuesday, Sep 29', 'record': '2-3', 'picks': [{'name': 'Braves ML', 'result': 'W'}]},
        {'date': '2026-09-30', 'label': 'Wednesday, Sep 30', 'record': '1-0', 'picks': [{'name': 'White Sox ML', 'result': 'W'}]}]},
        open(os.path.join(d, 'history.json'), 'w'))
    open(os.path.join(d, 'yesterday.html'), 'w').write('<div class="status">Yesterday - Wednesday, Sep 30</div>')
    sys.argv = ['b', os.path.join(d, 'manifest.json')]
    yh = ns.get('_yesterday_href') or (lambda t=None: 'missing')
    check(f'{B}: Oct 1 build links yesterday.html (it shows Sep 30)', yh('2026-10-01'), 'yesterday.html')
    check(f'{B}: Oct 2 build (no Oct 1 row) links the full record, never the Sep 30 page', yh('2026-10-02'), 'record.html')
    check(f'{B}: Sep 30 build (line is Sep 29, page shows Sep 30) links the full record', yh('2026-09-30'), 'record.html')
    sys.argv = argv0  # helper reads sys.argv[1] at CALL time - restore only after the calls
    check(f'{B}: home strip renders the computed line', '_hy or man[' in src, True)
    check(f'{B}: home strip link is computed, not fixed to yesterday.html', '<a class="yesrec home-yes" href="\'+_yesterday_href()+\'">' in src, True)
    check(f'{B}: league strips hide on stale manifest', '_s=None if _mstale else _YBL.get(_tab)' in src, True)

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
