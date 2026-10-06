#!/usr/bin/env python3
"""record_disclosure.py fixture: a late-post disclosure the published card carries reaches a graded
row that was written without it (the Oct 2 owner-override picks Under 3.5, Over 43.5 and Under 54.5
were graded before record_final copied added_after_kickoff / added_after_final, and record_final never
grades a row twice, so record.html showed no tag for them).
record_disclosure.py must:
  - add exactly the card's true flags to exactly those graded rows, nothing else in history.json,
    in history.json's own stored format, with one audit line per row;
  - leave a pick carded before its game, and a disclosed pick not graded yet, alone;
  - be a no-op on a re-run, and write nothing under --check;
  - REFUSE (exit 3, nothing written) a row that says false or carries a malformed flag, a row that
    claims a disclosure the card does not make, copies that contradict each other, a malformed card
    flag, after-the-final without after-kickoff, a graded pick whose row is missing or doubled, an
    MMA pick carrying a flag, and an audit line whose row lost its flags.
Offline: no network; every write goes into temp folders. Red before record_disclosure.py.
Run: python3 scripts/test_record_disclosure.py"""
import copy, json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOL = os.path.join(HERE, 'record_disclosure.py')
failures = 0

def check(name, actual, expected):
    global failures
    ok = actual == expected
    print(('OK  ' if ok else 'FAIL'), name, '' if ok else f'(got {actual!r}, want {expected!r})')
    if not ok:
        failures += 1

def total(name, eid, league, away, home, odds, side, line, **extra):
    p = {'name': name, 'market_class': 'total', 'side': side, 'line': line, 'odds': odds, 'card_american': int(odds),
         'units': '5u', 'espn_league': league,
         'game': {'away': away, 'home': home, 'commence': '2026-10-03T00:00Z', 'eid': eid}}
    p.update(extra)
    return p

BLUES = total('Under 6.5', '401890001', 'hockey/nhl', 'St. Louis Blues', 'Dallas Stars', '-133', 'under', 6.5)
WAVE = total('Under 3.5', '401854015', 'soccer/usa.nwsl', 'San Diego Wave FC', 'Orlando Pride', '-170', 'under', 3.5,
             added_after_kickoff=True, added_after_final=True)
PSU = total('Over 43.5', '401858476', 'football/college-football', 'Penn State Nittany Lions', 'Northwestern Wildcats',
            '-138', 'over', 43.5, added_after_kickoff=True)
PITT = total('Under 54.5', '401858245', 'football/college-football', 'Pittsburgh Panthers', 'Virginia Tech Hokies',
             '-104', 'under', 54.5, added_after_kickoff=True, added_after_final=True)
KEY = {p['name']: f"{p['game']['eid']}|total|{p['side']}|{p['line']}" for p in (BLUES, WAVE, PSU, PITT)}
FLAGS = ('added_after_kickoff', 'added_after_final')

def card(*picks, date='2026-10-02'):
    return {'date': date, 'record': '13-5', 'units_pl': '+2.00u', 'picks': [copy.deepcopy(p) for p in picks]}

def row(name, odds, result='W', **kw):
    return dict({'name': name, 'game': 'G', 'odds': odds, 'units': '5u', 'result': result, 'score': 'A 1, B 2',
                 '_delta': '1', 'learning': f'{name} lesson.'}, **kw)

def hist(*oct2):
    return {'days': [{'date': '2026-10-01', 'label': 'Thursday, Oct 1', 'record': '1-0', 'units': '+2.00u', 'brief': '',
                      'picks': [row('Devils ML', '-162')]},
                     {'date': '2026-10-02', 'label': 'Friday, Oct 2', 'record': '3-0', 'units': '+3.00u', 'brief': 'Brief.',
                      'picks': list(oct2) or [row('Under 6.5', '-133'), row('Under 3.5', '-170'), row('Over 43.5', '-138')]}]}

LIVE = {'date': '2026-10-03', 'record': '13-5', 'units_pl': '+2.00u', 'picks': []}
DONE = {'processed': [KEY['Under 6.5'], KEY['Under 3.5'], KEY['Over 43.5']], 'at': None, 'record_after': '13-5',
        'units_after_exact': '2'}
SNAP = {'manifests/manifest-02aaaaaaaaaa.json': card(BLUES, WAVE, PSU)}

def scene(h=None, snaps=None, done=None, log=None):
    tmp = tempfile.mkdtemp(prefix='rdisc_')
    os.makedirs(os.path.join(tmp, 'manifests'))
    os.makedirs(os.path.join(tmp, 'slates'))
    files = {'manifest.json': LIVE, 'record_done.json': done or DONE}
    files.update(SNAP if snaps is None else snaps)
    for rel, obj in files.items():
        json.dump(obj, open(os.path.join(tmp, rel), 'w'), indent=2)
    open(os.path.join(tmp, 'history.json'), 'w').write(json.dumps(h or hist(), indent=2) + '\n')
    if log is not None:
        open(os.path.join(tmp, 'slates', 'record_disclosures.jsonl'), 'w').write(log)
    return tmp

def run(tmp, *args):
    r = subprocess.run([sys.executable, TOOL, f'--root={tmp}', *args], capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr

def raw(tmp, rel='history.json'):
    p = os.path.join(tmp, rel)
    return open(p).read() if os.path.exists(p) else None

def log_lines(tmp):
    t = raw(tmp, os.path.join('slates', 'record_disclosures.jsonl'))
    return [json.loads(l) for l in (t or '').splitlines() if l.strip()]

def oct2(tmp):
    d = next(d for d in json.loads(raw(tmp))['days'] if d['date'] == '2026-10-02')
    return {p['name']: {k: p[k] for k in FLAGS if k in p} for p in d['picks']}

def expected_hist(**flags_by_name):
    h = hist()
    for p in h['days'][1]['picks']:
        p.update(flags_by_name.get(p['name'], {}))
    return json.dumps(h, indent=2) + '\n'

tmps = []
try:
    # 1. the card's flags reach the graded rows, and nothing else moves
    t = scene(); tmps.append(t)
    code, out, err = run(t)
    check('carry: exit 0', code, 0)
    check('carry: Under 3.5 (carded after the final) carries both flags, Over 43.5 after kickoff, Under 6.5 none',
          oct2(t), {'Under 6.5': {}, 'Under 3.5': {'added_after_kickoff': True, 'added_after_final': True},
                    'Over 43.5': {'added_after_kickoff': True}})
    check('carry: history.json is exactly the old file plus those flags, in its own format',
          raw(t), expected_hist(**{'Under 3.5': {'added_after_kickoff': True, 'added_after_final': True},
                                   'Over 43.5': {'added_after_kickoff': True}}))
    check('carry: record_done.json and manifest.json untouched',
          (json.loads(raw(t, 'record_done.json')), json.loads(raw(t, 'manifest.json'))), (DONE, LIVE))
    lines = log_lines(t)
    check('carry: one audit line per row, naming the card copy it came from',
          [(l['id'], l['grade_id'], l['added'], l['source']) for l in lines],
          [('2026-10-02|Under 3.5|late-post disclosure', KEY['Under 3.5'], {'added_after_kickoff': True, 'added_after_final': True},
            ['manifests/manifest-02aaaaaaaaaa.json']),
           ('2026-10-02|Over 43.5|late-post disclosure', KEY['Over 43.5'], {'added_after_kickoff': True},
            ['manifests/manifest-02aaaaaaaaaa.json'])])
    check('carry: says what it carried', ('DISCLOSURE CARRIED: 2 row(s)' in out, 'Under 3.5' in out, 'Over 43.5' in out), (True, True, True))
    before, before_log = raw(t), raw(t, os.path.join('slates', 'record_disclosures.jsonl'))
    code, out, err = run(t)
    check('re-run: a no-op (exit 0, nothing to carry)', (code, 'nothing to carry' in out), (0, True))
    check('re-run: history.json and the audit trail byte-identical',
          (raw(t) == before, raw(t, os.path.join('slates', 'record_disclosures.jsonl')) == before_log), (True, True))

    # the pages say it: record.html and yesterday.html built from the carried rows
    r = subprocess.run([sys.executable, os.path.join(HERE, 'build_history.py'), 'history.json'], cwd=t, capture_output=True, text=True)
    page = raw(t, 'record.html') or ''
    check('pages: build_history builds from the carried rows (exit 0)', r.returncode, 0)
    check('pages: record.html labels Under 3.5 after the final and Over 43.5 after kickoff, nothing else',
          re.findall(r'<span class="nm">([^<]*)</span>(?:(?!<div class="pk">).)*?<div class="late">([^<]*)</div>', page, re.S),
          [('Under 3.5', 'Added after the final'), ('Over 43.5', 'Added after kickoff')])

    # 2. --check writes nothing
    t = scene(); tmps.append(t)
    code, out, err = run(t, '--check')
    check('--check: exit 0, says what would change', (code, 'CHECK (nothing written): 2 row(s)' in out), (0, True))
    check('--check: history.json untouched, no audit trail', (raw(t), raw(t, os.path.join('slates', 'record_disclosures.jsonl'))),
          (json.dumps(hist(), indent=2) + '\n', None))

    # 3. a disclosed pick not graded yet is left to record_final
    t = scene(snaps={'manifests/manifest-02aaaaaaaaaa.json': card(BLUES, WAVE, PSU, PITT)}); tmps.append(t)
    code, out, err = run(t)
    check('pending: the graded rows are carried (exit 0)', (code, 'DISCLOSURE CARRIED: 2 row(s)' in out), (0, True))
    check('pending: the ungraded Under 54.5 is named pending and gets no row', ('pending:' in out and 'Under 54.5' in out,
          'Under 54.5' in oct2(t)), (True, False))

    # 4. refusals: exit 3, history.json byte-identical, no audit line
    def refused(name, why, h=None, snaps=None, done=None, log=None):
        t = scene(h=h, snaps=snaps, done=done, log=log); tmps.append(t)
        b0, l0 = raw(t), raw(t, os.path.join('slates', 'record_disclosures.jsonl'))
        code, out, err = run(t)
        check(f'{name}: refused (exit 3)', code, 3)
        check(f'{name}: refused for the right reason ({why})', why in err, True)
        check(f'{name}: history.json and the audit trail untouched',
              (raw(t) == b0, raw(t, os.path.join('slates', 'record_disclosures.jsonl')) == l0), (True, True))

    std = lambda **kw: [row('Under 6.5', '-133'), row('Under 3.5', '-170', **kw), row('Over 43.5', '-138')]
    refused('row says added_after_kickoff false, card says true', 'never overwritten', h=hist(*std(added_after_kickoff=False)))
    refused('row carries a string "true" flag', 'malformed added_after_kickoff', h=hist(*std(added_after_kickoff='true')))
    refused('row claims after-the-final, card says after kickoff only', "the row says added_after_final=True, the card says False",
            h=hist(row('Under 6.5', '-133'), row('Under 3.5', '-170'),
                   row('Over 43.5', '-138', added_after_kickoff=True, added_after_final=True)))
    refused('row claims a disclosure on a pick the card flags false', "the card says False",
            h=hist(row('Under 6.5', '-133', added_after_kickoff=True), row('Under 3.5', '-170'), row('Over 43.5', '-138')),
            snaps={'manifests/manifest-02aaaaaaaaaa.json': card(dict(BLUES, added_after_kickoff=False), WAVE, PSU)})
    no_flags = {k: v for k, v in WAVE.items() if k not in FLAGS}
    refused('card copies contradict', 'disagree on added_after_kickoff',
            snaps={'manifests/manifest-02aaaaaaaaaa.json': card(BLUES, WAVE, PSU),
                   'manifests/manifest-02bbbbbbbbbb.json': card(BLUES, dict(no_flags, added_after_kickoff=False, added_after_final=False), PSU)})
    refused('card flag malformed', 'must be true or false',
            snaps={'manifests/manifest-02aaaaaaaaaa.json': card(BLUES, dict(no_flags, added_after_kickoff='yes'), PSU)})
    refused('card says after the final without after kickoff', 'added_after_final without added_after_kickoff',
            snaps={'manifests/manifest-02aaaaaaaaaa.json': card(BLUES, dict(no_flags, added_after_final=True), PSU)})
    refused('graded pick with no row of its name at the card price', '0 row(s)',
            h=hist(row('Under 6.5', '-133'), row('Under 3.5', '-150'), row('Over 43.5', '-138')))
    refused('graded pick with two rows of its name at the card price', '2 row(s)',
            h=hist(row('Under 6.5', '-133'), row('Under 3.5', '-170'), row('Under 3.5', '-170'), row('Over 43.5', '-138')))
    ufc = {'name': 'Staines ML', 'odds': '-150', 'card_american': -150, 'units': '5u', 'espn_league': 'mma/ufc', 'side': 'home',
           'game': {'commence': '2026-10-03T00:00Z', 'eid': '600000001'}, 'added_after_kickoff': True}
    refused('MMA pick carrying a flag', 'MMA pick', snaps={'manifests/manifest-02aaaaaaaaaa.json': card(BLUES, WAVE, PSU, ufc)})
    refused('audit line on file but the row lost its flags', 'on the audit trail',
            log=json.dumps({'id': '2026-10-02|Under 3.5|late-post disclosure'}) + '\n')

finally:
    for t in tmps:
        shutil.rmtree(t, ignore_errors=True)

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
