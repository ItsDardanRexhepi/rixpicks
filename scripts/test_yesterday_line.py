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
    # r3 review (yday-1): once the next card replaces manifest.json, an ungraded yesterday read
    # '0-0 - no official picks' again. The card dates that carried picks come from the manifests/
    # snapshots (each one's card date by the builder's rule: the most common PT date across its picks'
    # commence) plus the live manifest; such a date with no graded row reads 'results pending'.
    d4 = tempfile.mkdtemp(prefix='rp-yline-snap-')
    os.makedirs(os.path.join(d4, 'manifests'))
    json.dump({'days': _days[:2]}, open(os.path.join(d4, 'history.json'), 'w'))  # Sep 29, Sep 30 graded
    _pk = lambda n, c: {'name': n, 'game': {'commence': c}}
    def snap(name, m):
        json.dump(m, open(os.path.join(d4, 'manifests', name), 'w'))
    # the Oct 2 card (puck drop after PT midnight on one pick: still the Oct 2 card), no Oct 2 row
    snap('manifest-0c02aaaaaaaa.json', {'date': '2026-10-02', 'picks': [_pk('Devils ML', '2026-10-02T23:00Z'), _pk('Under 38.5', '2026-10-03T00:15Z'),
                                                                        _pk('Kraken ML', '2026-10-03T07:05Z')]})
    snap('manifest-0c01bbbbbbbb.json', {'date': '2026-10-01', 'picks': []})        # Oct 1: an empty card
    snap('manifest-0c04cccccccc.json', {'date': '2026-10-04', 'preview': True,     # a preview is no official card
                                        'picks': [_pk('Jets ML', '2026-10-04T17:00Z')]})
    snap('manifest-0c05dddddddd.json', {'date': '2026-10-06', 'picks': [_pk('Rams ML', '2026-10-06T00:15Z')]})  # dated by its picks: Oct 5 PT
    snap('manifest-broken00000.json', {'date': '2026-10-07'})                       # no picks key at all
    open(os.path.join(d4, 'manifests', 'manifest-notjson00000.json'), 'w').write('{not json')
    json.dump({'date': '2026-10-03', 'picks': [_pk('Rangers ML', '2026-10-03T23:00Z')]}, open(os.path.join(d4, 'manifest.json'), 'w'))
    sys.argv = ['b', os.path.join(d4, 'manifest.json')]
    hy = ns['_hist_yesterday']
    check(f'{B}: Oct 3 build, the Oct 3 card live, Oct 2 snapshot with picks and no Oct 2 row: results pending', hy('2026-10-03'), 'results pending')
    check(f'{B}: Oct 2 build, Oct 1 had only an empty card: 0-0', hy('2026-10-02'), '0-0 - no official picks')
    check(f'{B}: Oct 4 build, the live Oct 3 card has no row yet: results pending', hy('2026-10-04'), 'results pending')
    check(f'{B}: Oct 5 build, Oct 4 had only a preview: 0-0', hy('2026-10-05'), '0-0 - no official picks')
    check(f'{B}: Oct 6 build, the snapshot dated Oct 6 is the Oct 5 card by its picks: results pending', hy('2026-10-06'), 'results pending')
    check(f'{B}: Oct 7 build, Oct 6 carried no card by the builder\'s rule: 0-0', hy('2026-10-07'), '0-0 - no official picks')
    check(f'{B}: Oct 1 build, a graded Sep 30 row still reads from the ledger', hy('2026-10-01'), '1-0 \u00b7 White Sox ML W')
    yp = ns.get('_yesterday_pending') or (lambda: 'missing')
    check(f'{B}: pending card dates: carded (snapshots + live card), no graded row', yp(), ['2026-10-02', '2026-10-03', '2026-10-05'])
    ya = ns.get('_home_yes_attrs') or (lambda t=None: 'missing')
    check(f'{B}: the Home line carries its date and the pending card dates for the view-time recompute', ya('2026-10-03'),
          ' data-ydate="2026-10-02" data-pending="2026-10-02 2026-10-03 2026-10-05"')
    shutil.rmtree(d4, ignore_errors=True)
    shutil.rmtree(d3, ignore_errors=True)
    shutil.rmtree(d2, ignore_errors=True)
    shutil.rmtree(d, ignore_errors=True)
    sys.argv = argv0  # helper reads sys.argv[1] at CALL time - restore only after the calls
    check(f'{B}: home strip renders the computed line', '_hy or man[' in src, True)
    check(f'{B}: home strip link is computed, not fixed to yesterday.html', '<a class="yesrec home-yes" href="\'+_yesterday_href()+\'"' in src, True)
    check(f'{B}: home strip carries its date and the pending card dates (view-time recompute)',
          '<a class="yesrec home-yes" href="\'+_yesterday_href()+\'"\'+_home_yes_attrs()+\'>' in src, True)
    check(f'{B}: league strips hide on stale manifest', '_s=None if _mstale else _YBL.get(_tab)' in src, True)

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
