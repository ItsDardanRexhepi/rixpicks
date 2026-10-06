#!/usr/bin/env python3
"""Late-post disclosure fixture (Oct 2 owner override: Wave-Pride Under 3.5, PSU-NW Over 43.5 and
Pitt-VT Under 54.5 were carded after kickoff - after their finals - and labeled so on the card with
added_after_kickoff / added_after_final; record_final.py wrote their history.json rows without the
flags, so record.html and yesterday.html lost the disclosure once the card was gone).
record_final.py must:
  - copy added_after_kickoff (and added_after_final) from the published card pick onto the row,
    and add nothing to a pick carded before its game;
  - keep a disclosure any published copy carries when another copy omits it (never dropped);
  - REFUSE (exit 3, nothing written) a flag that is not a JSON true/false, copies that contradict
    each other, after-the-final without after-kickoff, or a request that states another disclosure.
build_history.py must say it on the row (record.html and yesterday.html): 'Added after the final'
or 'Added after kickoff', nothing on other rows, and stop (no page written) on a malformed flag.
Offline: every ESPN read is served from the fixtures below; writes only into temp folders.
Bite-proof: red on the pre-fix record_final.py / build_history.py.
Run: python3 scripts/test_late_disclosure.py"""
import contextlib, copy, importlib.util, io, json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
failures = 0

def check(name, actual, expected):
    global failures
    ok = actual == expected
    print(('OK  ' if ok else 'FAIL'), name, '' if ok else f'(got {actual!r}, want {expected!r})')
    if not ok:
        failures += 1

CORE = 'https://sports.core.api.espn.com/v2/sports/{lg}/events/{e}/competitions/{e}'

def core(away, a_sc, home, h_sc):
    return {'status': {'type': {'completed': True, 'name': 'STATUS_FINAL'}},
            'competitors': [{'homeAway': 'home', 'team': {'displayName': home}, 'score': {'value': float(h_sc)}},
                            {'homeAway': 'away', 'team': {'displayName': away}, 'score': {'value': float(a_sc)}}]}

FIX = {
    CORE.format(lg='hockey/leagues/nhl', e='401890001'): core('St. Louis Blues', 4, 'Dallas Stars', 0),
    CORE.format(lg='soccer/leagues/usa.nwsl', e='401854015'): core('San Diego Wave FC', 2, 'Orlando Pride', 1),
    CORE.format(lg='football/leagues/college-football', e='401858476'): core('Penn State Nittany Lions', 13, 'Northwestern Wildcats', 34),
    # soccer grades on regulation time: record_final reads the match's ESPN summary (recorded, trimmed)
    'https://site.api.espn.com/apis/site/v2/sports/soccer/usa.nwsl/summary?event=401854015':
        json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tests', 'fixtures', 'soccer', 'summary_401854015.json'))),
}

def fake_get(url, *a, **k):
    if url not in FIX:
        raise OSError(f'offline fixture missing {url}')
    return copy.deepcopy(FIX[url])

def total(name, eid, league, away, home, commence, odds, side, line, **extra):
    p = {'name': name, 'market_class': 'total', 'side': side, 'line': line, 'odds': odds, 'card_american': int(odds),
         'units': '5u', 'espn_league': league, 'game': {'away': away, 'home': home, 'commence': commence, 'eid': eid}}
    p.update(extra)
    return p

BLUES = total('Under 6.5', '401890001', 'hockey/nhl', 'St. Louis Blues', 'Dallas Stars', '2026-10-03T01:00Z', '-133', 'under', 6.5)
WAVE = total('Under 3.5', '401854015', 'soccer/usa.nwsl', 'San Diego Wave FC', 'Orlando Pride', '2026-10-03T00:00Z', '-170', 'under', 3.5,
             added_after_kickoff=True, added_after_final=True)
PSU = total('Over 43.5', '401858476', 'football/college-football', 'Penn State Nittany Lions', 'Northwestern Wildcats',
            '2026-10-03T00:00Z', '-138', 'over', 43.5, added_after_kickoff=True)

def card(*picks):
    return {'date': '2026-10-02', 'record': '10-5', 'units_pl': '+2.00u', 'picks': [copy.deepcopy(p) for p in picks]}

LIVE = {'date': '2026-10-03', 'record': '10-5', 'units_pl': '+2.00u', 'picks': []}
HIST = {'days': [{'date': '2026-10-01', 'label': 'Thursday, Oct 1', 'record': '1-0', 'units': '+2.00u', 'brief': '',
                  'picks': [{'name': 'Devils ML', 'game': 'vs Flyers', 'odds': '-162', 'units': '5u', 'result': 'W',
                             'score': 'PHI 2, NJ 3', '_delta': '2'}]}]}
DONE = {'processed': [], 'at': None, 'record_after': '10-5', 'units_after_exact': '2'}

def req(p, result, score, delta, rec, ua, **extra):
    r = {'grade_id': f"{p['game']['eid']}|total|{p['side']}|{p['line']}", 'event_id': p['game']['eid'],
         'league': p['espn_league'], 'pick': p['name'], 'side': p['side'], 'result': result, 'score': score,
         'stake_units': '5u', 'locked_american': p['odds'], 'delta_units_exact': delta,
         'record_after': rec, 'units_after_exact': ua}
    r.update(extra)
    return r

D_BLUES, D_WAVE, D_PSU = 5 * 100 / 133, 5 * 100 / 170, 5 * 100 / 138
def r_blues(rec='11-5', ua=2 + D_BLUES, **x):
    return req(BLUES, 'WON', 'STL 4 @ DAL 0', D_BLUES, rec, ua, **x)
def r_wave(rec='12-5', ua=2 + D_BLUES + D_WAVE, **x):
    return req(WAVE, 'WON', 'SD 2 @ ORL 1', D_WAVE, rec, ua, **x)
def r_psu(rec='13-5', ua=2 + D_BLUES + D_WAVE + D_PSU, **x):
    return req(PSU, 'WON', 'PSU 13 @ NU 34', D_PSU, rec, ua, **x)

def load():
    spec = importlib.util.spec_from_file_location('record_final_late_disclosure', os.path.join(HERE, 'record_final.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def run(reqs, snaps):
    tmp = tempfile.mkdtemp(prefix='rf_late_')
    try:
        os.makedirs(os.path.join(tmp, 'manifests'))
        os.makedirs(os.path.join(tmp, 'slates'))
        files = {'manifest.json': LIVE, 'history.json': HIST, 'record_done.json': DONE, 'record_request.json': {'requests': reqs}}
        files.update(snaps)
        for rel, obj in files.items():
            json.dump(obj, open(os.path.join(tmp, rel), 'w'), indent=2)
        rf = load()
        rf.ROOT = tmp
        rf.REQ, rf.MAN, rf.HIST, rf.DONE = (os.path.join(tmp, f) for f in
                                            ('record_request.json', 'manifest.json', 'history.json', 'record_done.json'))
        rf.MANIFESTS = os.path.join(tmp, 'manifests')
        rf._get = fake_get
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = rf.main()
            except Exception as e:  # a crash is not a refusal
                code = f'raised {type(e).__name__}: {e}'
        state = {f: json.load(open(os.path.join(tmp, f))) for f in ('manifest.json', 'history.json', 'record_done.json', 'record_request.json')}
        return code, state, err.getvalue()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def rows(st, date='2026-10-02'):
    d = next((d for d in st['history.json']['days'] if d['date'] == date), None)
    return {p['name']: p for p in (d or {}).get('picks', [])}

FLAGS = ('added_after_kickoff', 'added_after_final')
def flags(row):
    return {k: row[k] for k in FLAGS if k in row}

SNAP = {'manifests/manifest-02aaaaaaaaaa.json': card(BLUES, WAVE, PSU)}

# 1. the card's flags travel onto the rows; a pre-game pick gets none
code, st, err = run([r_blues(), r_wave(), r_psu()], SNAP)
check('three grades on the Oct 2 card land (exit 0)', code, 0)
rw = rows(st)
check('Under 6.5 (carded before its game): no disclosure on the row', flags(rw.get('Under 6.5', {})), {})
check('Under 3.5 (carded after the final): both flags on the row',
      flags(rw.get('Under 3.5', {})), {'added_after_kickoff': True, 'added_after_final': True})
check('Over 43.5 (carded after kickoff): added_after_kickoff on the row', flags(rw.get('Over 43.5', {})), {'added_after_kickoff': True})
check('W-L and units still move exactly', (st['manifest.json']['record'], st['manifest.json']['units_pl']), ('13-5', '+12.32u'))

# 2. a copy that omits the flag makes no claim: the disclosure on any published copy is kept
bare = copy.deepcopy(WAVE)
for f in FLAGS:
    bare.pop(f)
code, st, err = run([r_blues(), r_wave()], {'manifests/manifest-02aaaaaaaaaa.json': card(BLUES, WAVE),
                                            'manifests/manifest-02bbbbbbbbbb.json': card(BLUES, bare)})
check('a later copy without the flags: grade lands', code, 0)
check('a later copy without the flags: the disclosure is kept, never dropped',
      flags(rows(st).get('Under 3.5', {})), {'added_after_kickoff': True, 'added_after_final': True})

# 3. fail-closed: malformed flags, contradicting copies, a request that disagrees with the card
def refused(name, reqs, snaps, why):
    code, st, err = run(reqs, snaps)
    check(f'{name}: refused (exit 3)', code, 3)
    check(f'{name}: refused for the right reason ({why})', why in err, True)
    check(f'{name}: history.json untouched', st['history.json'], HIST)
    check(f'{name}: manifest record untouched', st['manifest.json']['record'], LIVE['record'])

def flagged(**kw):
    p = copy.deepcopy(WAVE)
    for f in FLAGS:
        p.pop(f)
    p.update(kw)
    return p

refused('string "true" flag', [r_wave(rec='11-5', ua=2 + D_WAVE)],
        {'manifests/manifest-02aaaaaaaaaa.json': card(BLUES, flagged(added_after_kickoff='true'))}, 'malformed')
refused('null flag', [r_wave(rec='11-5', ua=2 + D_WAVE)],
        {'manifests/manifest-02aaaaaaaaaa.json': card(BLUES, flagged(added_after_kickoff=None))}, 'malformed')
refused('numeric 1 flag', [r_wave(rec='11-5', ua=2 + D_WAVE)],
        {'manifests/manifest-02aaaaaaaaaa.json': card(BLUES, flagged(added_after_kickoff=1))}, 'malformed')
refused('after the final without after kickoff', [r_wave(rec='11-5', ua=2 + D_WAVE)],
        {'manifests/manifest-02aaaaaaaaaa.json': card(BLUES, flagged(added_after_final=True))}, 'added_after_final without added_after_kickoff')
refused('copies contradict (true on one, false on another)', [r_wave(rec='11-5', ua=2 + D_WAVE)],
        {'manifests/manifest-02aaaaaaaaaa.json': card(BLUES, WAVE),
         'manifests/manifest-02bbbbbbbbbb.json': card(BLUES, flagged(added_after_kickoff=False, added_after_final=False))},
        'disagree on added_after_kickoff')
refused('request says not late, card says late', [r_wave(rec='11-5', ua=2 + D_WAVE, added_after_kickoff=False)], SNAP,
        'request added_after_kickoff=False disagrees')
refused('request says late, card says not', [r_blues(added_after_kickoff=True)], SNAP, 'request added_after_kickoff=True disagrees')
code, st, err = run([r_wave(rec='11-5', ua=2 + D_WAVE, added_after_kickoff=True, added_after_final=True)], SNAP)
check('a request that states the card\'s own disclosure lands', (code, flags(rows(st).get('Under 3.5', {}))),
      (0, {'added_after_kickoff': True, 'added_after_final': True}))

# 4. build_history.py says it on the row, on record.html and yesterday.html
def build(days):
    tmp = tempfile.mkdtemp(prefix='bh_late_')
    try:
        json.dump({'days': days}, open(os.path.join(tmp, 'history.json'), 'w'))
        r = subprocess.run([sys.executable, os.path.join(HERE, 'build_history.py'), 'history.json'], cwd=tmp,
                           capture_output=True, text=True)
        pages = {f: (open(os.path.join(tmp, f)).read() if os.path.exists(os.path.join(tmp, f)) else None)
                 for f in ('record.html', 'yesterday.html')}
        return r.returncode, pages, r.stderr
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def pk_block(page, name):
    # the .pk block of one pick, up to the next pick or the day's brief
    m = re.search(r'<div class="pk">\n<div class="pk-top">.*?<span class="nm">' + re.escape(name) + r'</span>(.*?)(?=<div class="pk">|<div class="brief">)', page, re.S)
    return m.group(1) if m else ''

ROW = lambda name, **kw: dict({'name': name, 'game': 'G', 'odds': '-110', 'units': '5u', 'result': 'W', 'score': 'A 1, B 2', '_delta': '1'}, **kw)
DAYS = [HIST['days'][0], {'date': '2026-10-02', 'label': 'Friday, Oct 2', 'record': '3-0', 'units': '+5.00u', 'brief': '',
                          'picks': [ROW('Under 6.5'), ROW('Under 3.5', added_after_kickoff=True, added_after_final=True),
                                    ROW('Over 43.5', added_after_kickoff=True)]}]
code, pages, err = build(DAYS)
check('build_history: built (exit 0)', code, 0)
for page in ('record.html', 'yesterday.html'):
    pg = pages[page] or ''
    check(f'{page}: Under 3.5 says Added after the final', '<div class="late">Added after the final</div>' in pk_block(pg, 'Under 3.5'), True)
    check(f'{page}: Over 43.5 says Added after kickoff', '<div class="late">Added after kickoff</div>' in pk_block(pg, 'Over 43.5'), True)
    check(f'{page}: Under 6.5 carries no disclosure', 'class="late"' in pk_block(pg, 'Under 6.5'), False)
    check(f'{page}: exactly two disclosures on the page', len(re.findall(r'<div class="late">', pg)), 2)
    check(f'{page}: the disclosure is styled (light and dark)', len(re.findall(r'\.late\{', pg)), 2)
bad = copy.deepcopy(DAYS)
bad[0]['picks'][0]['added_after_kickoff'] = 'yes'  # the OLDER day: neither page may be written
code, pages, err = build(bad)
check('build_history: malformed flag fails the build loudly', (code != 0, 'malformed added_after_kickoff' in err), (True, True))
check('build_history: malformed flag writes no page at all', pages, {'record.html': None, 'yesterday.html': None})

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
