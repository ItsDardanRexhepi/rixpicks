#!/usr/bin/env python3
"""finals_watch record-request fixture (sweep CP-05 producer side, F1 card date).
finals_watch queues the record write that record_final.py checks against the published card:
 - grade() returns W | L | PUSH and a push must travel as PUSH (it was queued as LOST, which the
   fail-closed record write refuses, stalling the in-order queue at the first push)
 - market_class and line ride along for the card cross-check
 - card_date is the date of the card the pick was graded from (the manifest's date), never the
   game's own PT date: a game starting after midnight PT belongs to the card it was published on
   (record_final files it under the builder's _card_date_of)
Offline; writes only into a temp folder. Run: python3 scripts/test_finals_watch_queue.py"""
import importlib.util, json, os, re, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
failures = 0

def check(name, actual, expected):
    global failures
    ok = actual == expected
    print(('OK  ' if ok else 'FAIL'), name, '' if ok else f'(got {actual!r}, want {expected!r})')
    if not ok:
        failures += 1

sys.path.insert(0, ROOT)  # core/ from this checkout (finals_watch also adds the analysis-side path)
os.environ.setdefault('RIX_UNIT_DOLLARS', '1')  # placeholder: only matters where units read the size
spec = importlib.util.spec_from_file_location('finals_watch_under_test', os.path.join(HERE, 'finals_watch.py'))
fw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fw)

tmp = tempfile.mkdtemp(prefix='fw_queue_')
try:
    os.makedirs(os.path.join(tmp, 'scripts'))
    fw.HERE = os.path.join(tmp, 'scripts')
    REQ = os.path.join(tmp, 'record_request.json')

    def queue(p, result, card_date, pkey, pnl):
        if os.path.exists(REQ):
            os.remove(REQ)
        fw._queue_record_request(p, p['game']['eid'], pkey, result, {'away_score': 1, 'home_score': 4}, '22-11', 7.0,
                                 pnl, {'source': 'fixture'}, '2026-10-02 00:30 PDT', card_date=card_date)
        return json.load(open(REQ))['requests'][-1]

    # published on the Oct 1 card; puck drop 12:05 AM PT Oct 2
    late = {'name': 'Kraken ML', 'espn_league': 'hockey/nhl', 'side': 'home', 'market_class': 'ml', 'odds': '-140', 'units': '5u',
            'game': {'away': 'Vancouver Canucks', 'home': 'Seattle Kraken', 'commence': '2026-10-02T07:05Z', 'eid': '401891900'}}
    r = queue(late, 'W', '2026-10-01', '401891900|ml|home', 0)
    check('W travels as WON', r['result'], 'WON')
    check("card_date is the card's date (2026-10-01), not the late game's own PT date", r['card_date'], '2026-10-01')
    check('a moneyline carries market_class ml and no line', (r['market_class'], r['line']), ('ml', None))

    spread = {'name': 'Aces -11', 'espn_league': 'basketball/wnba', 'side': 'home', 'market_class': 'spread', 'line': -11,
              'odds': '-110', 'units': '5u',
              'game': {'away': 'Indiana Fever', 'home': 'Las Vegas Aces', 'commence': '2026-10-02T02:00Z', 'eid': '401918022'}}
    r = queue(spread, 'PUSH', '2026-10-01', '401918022|spread|home|-11', 0)
    check('a spread push travels as PUSH (never LOST)', r['result'], 'PUSH')
    check('the push is labeled P in graded_pick', ' P: ' in r['graded_pick'], True)
    check('spread carries market_class and line', (r['market_class'], r['line']), ('spread', -11))
    r = queue(spread, 'L', '2026-10-01', '401918022|spread|home|-11', 0)
    check('L travels as LOST', r['result'], 'LOST')
    r = queue(spread, 'W', None, '401918022|spread|home|-11', 0)
    check('no card date given: record_final derives it from the published card', r['card_date'], None)

    src = open(os.path.join(HERE, 'finals_watch.py')).read()
    check("main() passes the manifest's card date", bool(re.search(r"_queue_record_request\([^)]*card_date=m\.get\('date'\)\)", src)), True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
