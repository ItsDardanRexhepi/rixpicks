#!/usr/bin/env python3
"""CLV ledger fixture (scripts/clv_report.py), on synthetic snapshots committed into a scratch git repo
with fixed author times. Checks:
  - the close is the LAST snapshot before the card's commence: an earlier one is not used, a snapshot
    after the commence (live prices) is never used, nor one whose own listing says the game had begun,
    nor one more than 180 minutes old (no close at all then);
  - each book is de-vigged multiplicatively on its own two-way market and the close is the median across
    at least 3 books (fewer -> no close, with the reason); books under state_templates count;
  - spreads use the card's HOME-basis line: only books whose spread_home_pts equals the pick's line, at
    the picked side's price; totals only at the pick's total;
  - locked cents: the accepted entry's cents, else Kalshi cents that are the card price, else the whole
    cents behind the card's American price, else its implied cents; clv_c = close*100 - locked;
  - grades queued in record_request.json are listed and marked (left out with --no-queued); props, a
    row whose odds differ from the card, and a pick on no card get no close, with the reason;
  - it never touches grading: history.json, manifest.json, record_done.json, record_request.json and
    manifests/ are byte-identical after a run, it writes only slates/clv_ledger.json, the same input gives
    the same bytes, record_final.py and no workflow call it, and no public page reads the ledger.
Offline; writes only into a temp folder. Bite-proof: red without scripts/clv_report.py.
Run: python3 scripts/test_clv_report.py"""
import hashlib, json, os, shutil, statistics, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(HERE, 'clv_report.py')
failures = 0

def check(name, actual, expected):
    global failures
    ok = actual == expected
    print(('OK  ' if ok else 'FAIL'), name, '' if ok else f'(got {actual!r}, want {expected!r})')
    if not ok:
        failures += 1

def ip(a):
    return 100 / (a + 100) if a > 0 else -a / (-a + 100)

def nv(mine, other):
    return ip(mine) / (ip(mine) + ip(other))

C = '2026-10-05T23:00Z'      # card commence for every synthetic game (4:00 PM PT, Oct 5)
C_LATE = '2026-10-05T23:30Z'  # the Penguins-style game
FLYERS = {  # exactly the accepted entry's scope (core/accepted_entry.py)
    'name': 'Flyers +1.5', 'market_class': 'spread', 'line': -1.5, 'odds': '-138', 'units': '5u', 'side': 'away',
    'game': {'away': 'Philadelphia Flyers', 'home': 'Tampa Bay Lightning', 'commence': '2026-10-05T23:00Z', 'eid': '401892445'},
    'espn_league': 'hockey/nhl', 'card_american': -138, 'card_source': 'best ask at lock: Polymarket 58c',
    'card_ts': '2026-10-05T09:30:11-07:00'}
def pick(name, mc, side, odds, away, home, eid, commence=C, line=None, **extra):
    p = {'name': name, 'market_class': mc, 'side': side, 'odds': odds, 'card_american': int(odds), 'units': '5u',
         'espn_league': 'hockey/nhl', 'game': {'away': away, 'home': home, 'commence': commence, 'eid': eid}}
    if line is not None:
        p['line'] = line
    p.update(extra)
    return p
PENS = pick('Penguins ML', 'ml', 'home', '-163', 'Winnipeg Jets', 'Pittsburgh Penguins', '401892447', C_LATE,
            kalshi={'cents': 63, 'team': 'PIT'})  # Kalshi 63c is NOT the card price (-163 = 62c)
DEVILS = pick('Devils ML', 'ml', 'away', '-133', 'New Jersey Devils', 'New York Rangers', '401892450', kalshi={'cents': 57})
UNDER = pick('Under 6.5', 'total', 'under', '-110', 'St. Louis Blues', 'Dallas Stars', '401892451', line=6.5)
THIN = pick('Kings ML', 'ml', 'home', '+120', 'Anaheim Ducks', 'Los Angeles Kings', '401892452')
STALE = pick('Sharks ML', 'ml', 'home', '+150', 'Utah Mammoth', 'San Jose Sharks', '401892453')
PROP = pick('Kucherov over 0.5 points', 'prop', 'over', '-150', 'Philadelphia Flyers', 'Tampa Bay Lightning', '401892445',
            line=0.5, player='Nikita Kucherov', market='hockey_points')
CARD = {'date': '2026-10-05', 'record': '30-15', 'units_pl': '+20.00u', 'picks': [FLYERS, PENS, DEVILS, UNDER, THIN, STALE, PROP]}

def row(name, odds, result='W'):
    return {'name': name, 'game': 'g', 'odds': odds, 'units': '5u', 'result': result, 'score': 'A 1, B 2', '_delta': '1'}
HIST = {'days': [{'date': '2026-10-05', 'label': 'Monday, Oct 5', 'record': '5-1', 'units': '+5.00u', 'brief': '', 'picks': [
    row('Penguins ML', '-163', 'L'), row('Devils ML', '-133'), row('Under 6.5', '-110'), row('Kings ML', '+120'),
    row('Sharks ML', '+150'), row('Kucherov over 0.5 points', '-150'), row('Ghost ML', '-120')]},
    {'date': '2026-10-06', 'label': 'Tuesday, Oct 6', 'record': '1-0', 'units': '+1.00u', 'brief': '', 'picks': [row('Odd ML', '-140')]}]}
REQ = {'requests': [{'grade_id': '401892445|spread|away|-1.5', 'event_id': '401892445', 'league': 'hockey/nhl', 'pick': 'Flyers +1.5',
                     'side': 'away', 'market_class': 'spread', 'card_date': '2026-10-05', 'result': 'LOST', 'locked_american': '-138'},
                    # already on the record: listed once, from history
                    {'grade_id': '401892450|ml|away', 'event_id': '401892450', 'league': 'hockey/nhl', 'pick': 'Devils ML',
                     'side': 'away', 'card_date': '2026-10-05', 'result': 'WON', 'locked_american': '-133'}]}
DONE = {'processed': [], 'at': None}
ODD = pick('Odd ML', 'ml', 'home', '-150', 'Boston Bruins', 'Buffalo Sabres', '401892460', '2026-10-06T23:00Z')
CARD6 = {'date': '2026-10-06', 'record': '31-15', 'units_pl': '+21.00u', 'picks': [ODD]}  # row says -140: no close

def ml(h, a):
    return {'home_ml': h, 'away_ml': a, 'home_link': 'x', 'away_link': 'x'}
def st(pts, hp, ap, tot=None, over=None, under=None):
    b = {'spread_home_pts': pts, 'spread_home_price': hp, 'spread_away_price': ap}
    if tot is not None:
        b.update({'total_pts': tot, 'over_price': over, 'under_price': under})
    return b
def game(away, home, commence, books):
    return {'away': away, 'home': home, 'commence': commence, 'books': books}

# --- moneyline snapshots ---
PENS_CLOSE = {'draftkings': ml(-180, 150), 'fanduel': ml(-182, 150), 'hardrockbet': ml(-175, 145), 'espnbet': ml(-170, 145),
              'state_templates': {'betmgm': ml(-180, 150), 'betrivers': ml(-186, 155)}}
DEV_CLOSE = {'draftkings': ml(-140, 120), 'fanduel': ml(-150, 125), 'betmgm': ml(-135, 115)}  # Devils are AWAY
KINGS_THIN = {'draftkings': ml(-130, 110), 'fanduel': ml(-128, 108), 'caesars': ml(-125, 105)}  # caesars is no listed book
def ml_snap(pens, dev, kings, pens_listed='2026-10-05T23:40:00Z'):
    return [game('Winnipeg Jets', 'Pittsburgh Penguins', pens_listed, pens),
            game('New Jersey Devils', 'New York Rangers', '2026-10-05T23:00:00Z', dev),
            game('Anaheim Ducks', 'Los Angeles Kings', '2026-10-05T23:00:00Z', kings)]
SHARKS_OLD = [game('Utah Mammoth', 'San Jose Sharks', '2026-10-05T23:00:00Z', {b: ml(-120, 100) for b in ('draftkings', 'fanduel', 'betmgm')})]
SKEW = {b: ml(-400, 300) for b in ('draftkings', 'fanduel', 'hardrockbet', 'espnbet', 'betmgm')}
# --- spread/total snapshots ---
FLY_CLOSE = {'draftkings': st(-1.5, 114, -135, 5.5, -122, 102), 'fanduel': st(-1.5, 104, -128, 5.5, -128, 104),
             'betrivers': st(-1.5, 120, -148), 'hardrockbet': st(-1.5, 105, -130), 'espnbet': st(-1.5, 115, -135),
             'betmgm': st(1.5, -200, 165)}  # betmgm at the OTHER side's line: never matched to a home -1.5 card line
UNDER_CLOSE = {'draftkings': st(-1.5, 150, -180, 6.5, -105, -115), 'fanduel': st(-1.5, 150, -180, 6.5, -108, -112),
               'espnbet': st(-1.5, 150, -180, 6.5, 100, -120), 'betmgm': st(-1.5, 150, -180, 6.0, -120, 100)}
def st_snap(fly, under, fly_listed='2026-10-05T23:10:00Z'):
    return [game('Philadelphia Flyers', 'Tampa Bay Lightning', fly_listed, fly), game('St. Louis Blues', 'Dallas Stars', '2026-10-05T23:00:00Z', under)]

def scratch():
    tmp = tempfile.mkdtemp(prefix='clv_fixture_')
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
    def git(*a, at=None):
        e = dict(env)
        if at:
            e.update(GIT_AUTHOR_DATE=at, GIT_COMMITTER_DATE=at)
        subprocess.run(['git', *a], cwd=tmp, env=e, check=True, capture_output=True)
    def put(rel, obj):
        os.makedirs(os.path.dirname(os.path.join(tmp, rel)) or tmp, exist_ok=True)
        json.dump(obj, open(os.path.join(tmp, rel), 'w'), indent=1)
    def commit(at, msg, **files):
        for rel, obj in files.items():
            put(rel.replace('__', '/'), obj)
        git('add', '-A')
        git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', msg, at=at)
    git('init', '-q')
    commit('2026-10-05T10:00:00Z', 'card', **{'history.json': HIST, 'manifest.json': CARD6, 'record_done.json': DONE,
                                              'record_request.json': REQ, 'manifests__manifest-aaaaaaaaaaaa.json': CARD,
                                              'slates__odds_prefill.json': SHARKS_OLD, 'slates__odds_prefill_st.json': []})
    # 2.5 h before: earlier prices (not the close). Sharks are no longer listed after this.
    commit('2026-10-05T20:30:00Z', 'odds refresh early', **{'slates__odds_prefill.json': ml_snap(SKEW, SKEW, SKEW), 'slates__odds_prefill_st.json': st_snap(
               {b: st(-1.5, 300, -400) for b in ('draftkings', 'fanduel', 'espnbet')}, {})})
    # 10 min before the 23:00 commence: THE CLOSE for the 23:00 games
    commit('2026-10-05T22:50:00Z', 'odds refresh close', **{'slates__odds_prefill.json': ml_snap(PENS_CLOSE, DEV_CLOSE, KINGS_THIN),
                                                            'slates__odds_prefill_st.json': st_snap(FLY_CLOSE, UNDER_CLOSE)})
    # after 23:00: live for the 23:00 games, still pre-game for the Penguins (card 23:30) - but this
    # snapshot itself lists the Penguins game at 23:05, so it is live there too; Penguins close stays 22:50
    commit('2026-10-05T23:10:00Z', 'odds refresh live', **{'slates__odds_prefill.json': ml_snap(SKEW, SKEW, SKEW, '2026-10-05T23:05:00Z'),
                                                           'slates__odds_prefill_st.json': st_snap({b: st(-1.5, -400, 300) for b in ('draftkings', 'fanduel', 'espnbet')}, {})})
    return tmp, git

def run(tmp, *args):
    r = subprocess.run([sys.executable, SCRIPT, '--root', tmp, *args], capture_output=True, text=True)
    out = os.path.join(tmp, 'slates', 'clv_ledger.json')
    led = json.load(open(out)) if os.path.exists(out) else None
    return r.returncode, led, r.stdout + r.stderr

def digest(tmp):
    h = {}
    for rel in ('history.json', 'manifest.json', 'record_done.json', 'record_request.json', 'manifests/manifest-aaaaaaaaaaaa.json',
                'slates/odds_prefill.json', 'slates/odds_prefill_st.json'):
        h[rel] = hashlib.sha256(open(os.path.join(tmp, rel), 'rb').read()).hexdigest()
    return h

if not os.path.exists(SCRIPT):
    check('scripts/clv_report.py exists', False, True)
    sys.exit(1)

tmp, git = scratch()
try:
    before = digest(tmp)
    code, led, out = run(tmp)
    check('clv_report exits 0', code, 0)
    rows = {r['name']: r for r in (led or {}).get('rows', [])}

    # Penguins: ML home, median of 6 (4 top-level + betmgm/betrivers under state_templates), 62c from -163
    pens = rows.get('Penguins ML', {})
    want = statistics.median([nv(-180, 150), nv(-182, 150), nv(-175, 145), nv(-170, 145), nv(-180, 150), nv(-186, 155)])
    check('Penguins: close is the 22:50 snapshot (the 23:10 one lists the game as begun)', pens.get('close_ts'), '2026-10-05T22:50:00Z')
    check('Penguins: 6 books, state_templates included', (pens.get('n_books'), sorted(pens.get('close_books', {}))),
          (6, sorted(['draftkings', 'fanduel', 'hardrockbet', 'espnbet', 'betmgm', 'betrivers'])))
    check('Penguins: close_novig = median multiplicative no-vig', pens.get('close_novig'), round(want, 4))
    check('Penguins: locked 62c - whole cents behind -163 (Kalshi 63c is not the card price)',
          (pens.get('locked_c'), pens.get('locked_basis')), (62.0, 'card_cents'))
    check('Penguins: clv_c = close*100 - locked', pens.get('clv_c'), round(round(want, 4) * 100 - 62, 2))
    check('Penguins: age 40 min before the card commence', pens.get('close_age_min'), 40)

    # Flyers +1.5 (queued grade): HOME-basis line -1.5, away price; betmgm's +1.5 line is not matched
    fly = rows.get('Flyers +1.5', {})
    wantf = statistics.median([nv(-135, 114), nv(-128, 104), nv(-148, 120), nv(-130, 105), nv(-135, 115)])
    check('Flyers: queued grade listed and marked', fly.get('source'), 'record_request (queued, not yet on the record)')
    check('Flyers: only books at spread_home_pts == -1.5 (betmgm at +1.5 left out)', sorted(fly.get('close_books', {})),
          sorted(['draftkings', 'fanduel', 'betrivers', 'hardrockbet', 'espnbet']))
    check('Flyers: close = median of the AWAY side no-vig', fly.get('close_novig'), round(wantf, 4))
    check('Flyers: never the 23:10 live snapshot or the 20:30 one', fly.get('close_ts'), '2026-10-05T22:50:00Z')
    check('Flyers: locked 58c from the accepted entry', (fly.get('locked_c'), fly.get('locked_basis')), (58.0, 'accepted_entry'))
    check('Flyers: clv_c', fly.get('clv_c'), round(round(wantf, 4) * 100 - 58, 2))

    # Devils: AWAY moneyline, Kalshi 57c IS the card price (-133)
    dev = rows.get('Devils ML', {})
    wantd = statistics.median([nv(120, -140), nv(125, -150), nv(115, -135)])
    check('Devils: away side de-vigged, 3 books', (dev.get('close_novig'), dev.get('n_books')), (round(wantd, 4), 3))
    check('Devils: locked = Kalshi cents that are the card price', (dev.get('locked_c'), dev.get('locked_basis')), (57.0, 'kalshi_cents'))
    check('Devils: listed once (history), not again from the queue', [r['name'] for r in led['rows']].count('Devils ML'), 1)

    # Under 6.5: only books at total 6.5 (betmgm at 6.0 left out), under price; -110 -> implied cents
    und = rows.get('Under 6.5', {})
    wantu = statistics.median([nv(-115, -105), nv(-112, -108), nv(-120, 100)])
    check('Under 6.5: books at total 6.5 only', sorted(und.get('close_books', {})), ['draftkings', 'espnbet', 'fanduel'])
    check('Under 6.5: close = median under no-vig', und.get('close_novig'), round(wantu, 4))
    check('Under 6.5: -110 has no whole-cent price behind it: implied cents', (und.get('locked_c'), und.get('locked_basis')),
          (52.38, 'card_american_implied'))

    # no close, each with its reason
    def why(name):
        r = rows.get(name, {})
        return r.get('status'), r.get('reason', '')
    st_, rs = why('Kings ML')
    check('Kings: 2 listed books (caesars is not one) -> no close', (st_, '2 book(s)' in rs and 'need 3' in rs), ('no_close', True))
    st_, rs = why('Sharks ML')
    check('Sharks: only listing is 13 h old -> no close (stale)', (st_, 'over the 180 min limit' in rs), ('no_close', True))
    st_, rs = why('Kucherov over 0.5 points')
    check('prop -> no close (no book snapshot file)', (st_, "'prop'" in rs), ('no_close', True))
    st_, rs = why('Ghost ML')
    check('row on no published card -> no close', (st_, 'not on a published 2026-10-05 card' in rs), ('no_close', True))
    st_, rs = why('Odd ML')
    check('row odds that differ from the card -> no close', (st_, 'differ from the card price' in rs), ('no_close', True))
    check('summary counts', (led or {}).get('summary', {}).get('with_close'), 4)

    # never touches grading
    check('record files and snapshots byte-identical after a run', digest(tmp), before)
    status = subprocess.run(['git', 'status', '--porcelain'], cwd=tmp, capture_output=True, text=True).stdout.split('\n')
    check('the only change in the repo is the ledger', [s for s in status if s], ['?? slates/clv_ledger.json'])
    first = open(os.path.join(tmp, 'slates', 'clv_ledger.json'), 'rb').read()
    run(tmp)
    check('same input -> same bytes (no wall-clock stamp)', open(os.path.join(tmp, 'slates', 'clv_ledger.json'), 'rb').read(), first)
    code, led2, _ = run(tmp, '--no-queued')
    check('--no-queued leaves the queued Flyers grade out', 'Flyers +1.5' in [r['name'] for r in led2['rows']], False)
    code, led3, _ = run(tmp, '--date', '2026-10-06')
    check('--date keeps that card date only', [r['name'] for r in led3['rows']], ['Odd ML'])
    alt = os.path.join(tmp, 'alt.json')
    code, _, _ = run(tmp, '--out', alt)
    check('--out writes the ledger there', os.path.exists(alt), True)
    empty = tempfile.mkdtemp(prefix='clv_norepo_')
    code, _, msg = run(empty)
    shutil.rmtree(empty, ignore_errors=True)
    check('a folder that is no git repo fails loudly (exit 2)', code, 2)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# not wired into grading, not rendered on any page
src_rf = open(os.path.join(HERE, 'record_final.py')).read()
check('record_final.py does not call the CLV report', 'clv_report' in src_rf or 'clv_ledger' in src_rf, False)
wf_dir = os.path.join(ROOT, '.github', 'workflows')
wired = [f for f in sorted(os.listdir(wf_dir)) if 'clv_report' in open(os.path.join(wf_dir, f)).read()]
check('no workflow runs the CLV report (it is not part of grading or publishing)', wired, [])
tracked = subprocess.run(['git', '-C', ROOT, 'ls-files', '*.html', '*.js'], capture_output=True, text=True).stdout.split()
readers = [f for f in tracked if 'clv_ledger' in open(os.path.join(ROOT, f), errors='replace').read() and not f.startswith('scripts/test_')]
check('no public page or page script reads the ledger', readers, [])

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
