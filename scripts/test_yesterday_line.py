# K18 fixture (9/30 midnight QA): the home Yesterday line must follow the BUILD date and come
# from the canonical history.json ledger - a static manifest field lies after midnight.
# Bite-proof: fails against builders that render man['yesterday'] directly.
import json, os, re, shutil, subprocess, sys, tempfile
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
    # yesterday.html as build_history.py now writes it: the latest graded days as data-date blocks,
    # the viewer's PT yesterday picked at view time (static heading 'Last graded day - ...')
    d2 = tempfile.mkdtemp(prefix='rp-yline-bh-')
    _row = lambda n: {'name': n, 'game': 'at Astros', 'odds': '+138', 'units': '5u', 'result': 'W', 'score': 'CHW 7, HOU 3'}
    _days = [{'date': '2026-09-29', 'label': 'Tuesday, Sep 29', 'record': '1-0', 'units': '+6.90u', 'brief': '', 'picks': [_row('Braves ML')]},
             {'date': '2026-09-30', 'label': 'Wednesday, Sep 30', 'record': '1-0', 'units': '+6.90u', 'brief': '', 'picks': [_row('White Sox ML')]}]
    json.dump({'days': _days}, open(os.path.join(d2, 'history.json'), 'w'))
    subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'build_history.py'), 'history.json'], cwd=d2,
                   capture_output=True, text=True, check=True)
    sys.argv = ['b', os.path.join(d2, 'manifest.json')]
    check(f'{B}: Oct 1 build links the view-time yesterday.html (it carries Sep 30)', yh('2026-10-01'), 'yesterday.html')
    check(f'{B}: Sep 30 build links the view-time yesterday.html (it carries Sep 29)', yh('2026-09-30'), 'yesterday.html')
    check(f'{B}: Oct 2 build (no Oct 1 row) still links the full record', yh('2026-10-02'), 'record.html')
    # F2: an Oct 1 row lands, but the page was rebuilt before history (old record-final order)
    _days.append({'date': '2026-10-01', 'label': 'Thursday, Oct 1', 'record': '1-0', 'units': '+3.09u', 'brief': '', 'picks': [_row('Devils ML')]})
    json.dump({'days': _days}, open(os.path.join(d2, 'history.json'), 'w'))
    check(f'{B}: a yesterday.html without the line\'s day (Oct 1) links the full record', yh('2026-10-02'), 'record.html')
    # Oct 2 review: no history row for yesterday is not proof of 'no official picks' - when the
    # manifest is still yesterday's card and it carries picks, they are ungraded: results pending
    d3 = tempfile.mkdtemp(prefix='rp-yline-pend-')
    json.dump({'days': _days[:2]}, open(os.path.join(d3, 'history.json'), 'w'))  # Sep 29, Sep 30; no Oct 1 row
    sys.argv = ['b', os.path.join(d3, 'manifest.json')]
    for mdate, mpicks, want, why in [('2026-10-01', [{'name': 'Devils ML'}], 'results pending', "manifest is Oct 1's card with picks"),
                                     ('2026-10-01', [], '0-0 - no official picks', "manifest is Oct 1's card with no picks"),
                                     ('2026-10-02', [{'name': 'Rangers ML'}], '0-0 - no official picks', "manifest is already Oct 2's card")]:
        json.dump({'date': mdate, 'picks': mpicks}, open(os.path.join(d3, 'manifest.json'), 'w'))
        check(f'{B}: Oct 2 build, no Oct 1 row, {why}', ns['_hist_yesterday']('2026-10-02'), want)
    json.dump({'date': '2026-10-01', 'picks': [{'name': 'Devils ML'}]}, open(os.path.join(d3, 'manifest.json'), 'w'))
    check(f'{B}: a graded yesterday row still reads from the ledger', ns['_hist_yesterday']('2026-10-01'),
          '1-0 \u00b7 White Sox ML W')
    shutil.rmtree(d3, ignore_errors=True)
    shutil.rmtree(d2, ignore_errors=True)
    shutil.rmtree(d, ignore_errors=True)
    sys.argv = argv0  # helper reads sys.argv[1] at CALL time - restore only after the calls
    check(f'{B}: home strip renders the computed line', '_hy or man[' in src, True)
    check(f'{B}: home strip link is computed, not fixed to yesterday.html', '<a class="yesrec home-yes" href="\'+_yesterday_href()+\'">' in src, True)
    check(f'{B}: league strips hide on stale manifest', '_s=None if _mstale else _YBL.get(_tab)' in src, True)

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
