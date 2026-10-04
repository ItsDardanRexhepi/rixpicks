#!/usr/bin/env python3
"""Fixture: record_correction.py applies one declared stake correction and nothing else, or refuses
and writes nothing. Built on the real Sep 25 shape (Orioles +105 5u W, Guardians -129 5u W, Astros
-172 stored 10u L; overall 21-11 +4.76u, exact anchor 4.761952343474163):
  - the 10u -> 6u fix moves the Astros stake, the Sep 25 day (-0.87u -> +3.13u), manifest units_pl,
    record_done.json's exact anchor (+4.0 exactly, which record_final.units_anchor then accepts),
    and the API mirror; W-L stays 21-11 everywhere; a corrections entry lands on the day row and
    one audit line in slates/record_corrections.jsonl; every other byte of every file is unchanged
  - re-running it writes nothing; a stored value that is not 'from', any field other than units, an
    unknown or missing key, an equal from/to, an ambiguous pick, a day whose units do not follow
    from its picks, a missing or disagreeing exact anchor, or a disagreeing API mirror each refuse
    with every file byte-identical
  - a win scales by the card price; a pick with a stored _delta has it recomputed, and a _delta that
    does not follow from its stake refuses
  - live repo: every line of slates/record_corrections.jsonl sits on its history.json row; the
    latest correction of a pick carries its value now, and an earlier one chains into the reversal
    that superseded it; an owner-ordered line+odds entry leaves its pick under the corrected name at
    the corrected odds, its delta following from that price."""
import copy, json, os, shutil, subprocess, sys, tempfile
from datetime import datetime, timezone
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import record_correction as rc  # noqa: E402
import record_final as rf  # noqa: E402

failures = 0
def check(name, cond, detail=''):
    global failures
    print(('OK  ' if cond else 'FAIL'), name, '' if cond else detail)
    if not cond:
        failures += 1

ANCHOR = '4.761952343474163'
HIST = {'days': [
    {'date': '2026-09-24', 'label': 'Thursday, Sep 24', 'record': '1-1', 'units': '-1.79u', 'brief': '',
     'picks': [{'name': 'Yankees ML', 'game': 'vs Rays', 'odds': '-156', 'units': '5u', 'result': 'W', 'score': 'NYY 6, TB 4'},
               {'name': 'Red Sox ML', 'game': 'vs Guardians', 'odds': '-131', 'units': '5u', 'result': 'L', 'score': 'CLE 1, BOS 0'}]},
    {'date': '2026-09-25', 'label': 'Friday, Sep 25', 'record': '2-1', 'units': '-0.87u', 'brief': 'b',
     'picks': [{'name': 'Orioles ML', 'game': 'at Yankees G1', 'odds': '+105', 'units': '5u', 'result': 'W', 'score': 'BAL 10, NYY 2', 'note': 'n1'},
               {'name': 'Guardians ML', 'game': 'at Royals', 'odds': '-129', 'units': '5u', 'result': 'W', 'score': 'CLE 12, KC 9', 'note': 'n2'},
               {'name': 'Astros ML', 'game': 'at Athletics', 'odds': '-172', 'units': '10u', 'result': 'L', 'score': 'ATH 6, HOU 5', 'note': 'n3'}]},
    {'date': '2026-09-30', 'label': 'Wednesday, Sep 30', 'record': '1-0', 'units': '+6.90u', 'brief': '',
     'picks': [{'name': 'White Sox ML', 'game': 'at Astros', 'odds': '+138', 'units': '5u', 'result': 'W', 'score': 'CHW 7, HOU 3', '_delta': '6.9'}]}]}
# fixture overall: 4-2 (the anchor is the real one; the fixture checks agreement, not a sum)
MAN = {'date': '2026-10-02', 'updated': 'Oct 2, 6:56 AM PT', 'record': '4-2', 'units_pl': '+4.76u', 'units_ledger': None, 'picks': []}
DONE = {'processed': ['401907897|ml|away'], 'at': '2026-10-01T00:32:08.798782+00:00'}
API = {'w': 4, 'l': 2, 'pct': 66.7, 'units': 4.76, 'updated': '2026-10-01T00:32:08.800592Z', 'graded_pick': 'g', 'source': 's'}
DECL = {'date': '2026-09-25', 'pick': 'Astros ML', 'field': 'units', 'from': '10u', 'to': '6u',
        'basis': 'published card carries 6u', 'approved': 'owner, in chat, 2026-10-02', 'units_exact_before': ANCHOR}
NOW = datetime(2026, 10, 2, 21, 45, tzinfo=timezone.utc)

def make(hist=HIST, man=MAN, done=DONE, api=API):
    d = tempfile.mkdtemp(prefix='reccorr_')
    os.makedirs(os.path.join(d, 'slates'))
    json.dump(hist, open(os.path.join(d, 'history.json'), 'w'), indent=2)
    json.dump(man, open(os.path.join(d, 'manifest.json'), 'w'), indent=1)
    json.dump(done, open(os.path.join(d, 'record_done.json'), 'w'), indent=2)
    json.dump(api, open(os.path.join(d, 'slates', 'api_record.json'), 'w'), indent=1)
    return d

FILES = ('history.json', 'manifest.json', 'record_done.json', os.path.join('slates', 'api_record.json'),
         os.path.join('slates', 'record_corrections.jsonl'))
def snap(d):
    return {f: (open(os.path.join(d, f), 'rb').read() if os.path.exists(os.path.join(d, f)) else None) for f in FILES}

def run(d, decl, check_only=False):
    try:
        return rc.apply(decl, d, check=check_only, now=NOW)
    except rc.Refuse as e:
        return 3, str(e)

def refuses(name, decl=DECL, why='', **files):
    d = make(**files)
    s0 = snap(d)
    code, msg = run(d, decl)
    check(f'refuses: {name}', code == 3 and snap(d) == s0 and why in msg, (code, msg))
    shutil.rmtree(d, ignore_errors=True)
    return msg

# 1. the Astros correction
d = make()
s0 = snap(d)
code, msg = run(d, DECL, check_only=True)
check('--check writes nothing', code == 0 and snap(d) == s0 and 'CHECK' in msg, msg)
code, msg = run(d, DECL)
h = json.load(open(os.path.join(d, 'history.json')))
m = json.load(open(os.path.join(d, 'manifest.json')))
dn = json.load(open(os.path.join(d, 'record_done.json')))
ap = json.load(open(os.path.join(d, 'slates', 'api_record.json')))
day = h['days'][1]
check('applied', code == 0 and 'CORRECTION APPLIED' in msg, msg)
check('Astros stake 6u, result/odds/score/note untouched',
      day['picks'][2] == {**HIST['days'][1]['picks'][2], 'units': '6u'}, day['picks'][2])
check('Sep 25 day units -0.87u -> +3.13u, record 2-1', day['units'] == '+3.13u' and day['record'] == '2-1', (day['units'], day['record']))
c = (day.get('corrections') or [{}])[0]
check('corrections entry on the day row', len(day.get('corrections') or []) == 1 and c.get('id') == '2026-09-25|Astros ML|units|10u->6u'
      and c.get('from') == '10u' and c.get('to') == '6u' and c.get('basis') and c.get('approved')
      and c.get('day_units_from') == '-0.87u' and c.get('day_units_to') == '+3.13u' and c.get('applied_at') == '2026-10-02T21:45:00Z', c)
other = copy.deepcopy(h); other['days'][1]['picks'][2]['units'] = '10u'; other['days'][1]['units'] = '-0.87u'; del other['days'][1]['corrections']
check('every other history value unchanged', other == HIST)
check('manifest units_pl +8.76u, record 4-2, updated stamped',
      m['units_pl'] == '+8.76u' and m['record'] == '4-2' and m['updated'] == 'Oct 2, 2:45 PM PT'
      and {k: v for k, v in m.items() if k not in ('units_pl', 'updated')} == {k: v for k, v in MAN.items() if k not in ('units_pl', 'updated')}, m)
check('exact anchor moves +4.0 exactly', Decimal(dn['units_after_exact']) - Decimal(ANCHOR) == Decimal('4')
      and dn['units_after_exact'] == '8.761952343474163' and dn['record_after'] == '4-2'
      and dn['processed'] == DONE['processed'] and dn['at'] == DONE['at'], dn)
check('record_final.units_anchor takes the new exact anchor', rf.units_anchor(m, dn) == (Decimal('8.761952343474163'), rf.EXACT))
check('API mirror units 8.76, W-L 4-2, nothing else but updated',
      ap['units'] == 8.76 and (ap['w'], ap['l'], ap['pct'], ap['graded_pick'], ap['source']) == (4, 2, 66.7, 'g', 's'), ap)
log = [json.loads(l) for l in open(os.path.join(d, 'slates', 'record_corrections.jsonl'))]
check('one audit line with the effects', len(log) == 1 and log[0]['id'] == c['id'] and log[0]['effects']['units_shift'] == '4'
      and log[0]['effects']['units_pl_from'] == '+4.76u' and log[0]['effects']['units_pl_to'] == '+8.76u'
      and log[0]['effects']['record'] == '4-2', log)
check('files keep their own format', open(os.path.join(d, 'manifest.json')).read() == json.dumps(m, indent=1)
      and open(os.path.join(d, 'history.json')).read() == json.dumps(h, indent=2))
s1 = snap(d)
code, msg = run(d, DECL)
check('re-run is a no-op', code == 0 and 'already applied' in msg and snap(d) == s1, msg)
d2 = make()
p = subprocess.run([sys.executable, os.path.join(HERE, 'record_correction.py'), '--root=' + d2, '/nonexistent.json'], capture_output=True, text=True)
check('CLI: unreadable declaration refuses (exit 3)', p.returncode == 3 and 'REFUSE' in p.stderr, p.stderr)
json.dump(DECL, open(os.path.join(d2, 'decl.json'), 'w'))
p = subprocess.run([sys.executable, os.path.join(HERE, 'record_correction.py'), '--root=' + d2, os.path.join(d2, 'decl.json')], capture_output=True, text=True)
check('CLI applies (exit 0)', p.returncode == 0 and 'CORRECTION APPLIED' in p.stdout, p.stdout + p.stderr)
shutil.rmtree(d, ignore_errors=True); shutil.rmtree(d2, ignore_errors=True)

# 2. refusals: nothing written
refuses('stored value is not from', {**DECL, 'from': '5u'}, why="not the declared from '5u'")
refuses('field other than units (result)', {**DECL, 'field': 'result', 'from': '10u', 'to': '6u'})
refuses('field other than units (odds)', {**DECL, 'field': 'odds'})
refuses('unknown key', {**DECL, 'result': 'W'})
refuses('missing basis', {k: v for k, v in DECL.items() if k != 'basis'})
refuses('empty approved', {**DECL, 'approved': ' '})
refuses('from == to', {**DECL, 'to': '10u'})
refuses('stake not in Nu form', {**DECL, 'to': '6'})
refuses('no such pick', {**DECL, 'pick': 'Astros RL'})
refuses('no such date', {**DECL, 'date': '2026-09-26'})
h2 = copy.deepcopy(HIST); h2['days'][1]['picks'].append(copy.deepcopy(h2['days'][1]['picks'][2]))
refuses('ambiguous pick', hist=h2)
h3 = copy.deepcopy(HIST); h3['days'][1]['units'] = '-0.80u'
refuses('day units do not follow from its picks', hist=h3)
refuses('no exact anchor and none declared', {k: v for k, v in DECL.items() if k != 'units_exact_before'})
refuses('declared anchor does not display as units_pl', {**DECL, 'units_exact_before': '4.70'})
refuses('record_done anchor disagrees with manifest', done={**DONE, 'record_after': '4-2', 'units_after_exact': '3.9'})
refuses('declared anchor != record_done anchor', done={**DONE, 'record_after': '4-2', 'units_after_exact': '4.7619'})
refuses('API mirror disagrees', api={**API, 'units': 4.75})
refuses('day records do not sum to manifest', man={**MAN, 'record': '5-2'}, api={**API, 'w': 5})

# the undeclared-change guard: a write path that touched anything else is refused, nothing written
_real = rc.day_exact
def _tamper(day):
    if day.get('corrections'):
        day['label'] = 'tampered'
    return _real(day)
rc.day_exact = _tamper
refuses('undeclared change to another field', why='undeclared change')
rc.day_exact = _real
check('diff sees nested, added, removed and retyped values',
      rc._diff({'a': {'b': [1, 2]}, 'c': 1}, {'a': {'b': [1, 3]}, 'c': 1.0, 'd': 0}) == ['/a/b/1', '/c', '/d']
      and rc._diff({'a': [1]}, {'a': [1, 2]}) == ['/a'] and rc._diff({'x': 1}, {}) == ['/x'])

# 3. anchor from record_done, a win scales by price, a stored _delta is recomputed
d = make(done={**DONE, 'record_after': '4-2', 'units_after_exact': ANCHOR})
code, msg = run(d, {k: v for k, v in DECL.items() if k != 'units_exact_before'} | {'pick': 'Orioles ML', 'from': '5u', 'to': '10u'})
h = json.load(open(os.path.join(d, 'history.json')))
dn = json.load(open(os.path.join(d, 'record_done.json')))
check('win: +105 5u -> 10u moves +5.25 exactly', code == 0 and Decimal(dn['units_after_exact']) - Decimal(ANCHOR) == Decimal('5.25')
      and h['days'][1]['units'] == '+4.38u', (msg, dn, h['days'][1]['units']))
shutil.rmtree(d, ignore_errors=True)
d = make()
code, msg = run(d, {**DECL, 'date': '2026-09-30', 'pick': 'White Sox ML', 'from': '5u', 'to': '10u'})
h = json.load(open(os.path.join(d, 'history.json')))
pk = h['days'][2]['picks'][0]
check('stored _delta recomputed (6.9 -> 13.8), day +13.80u', code == 0 and Decimal(pk['_delta']) == Decimal('13.8') and h['days'][2]['units'] == '+13.80u', (msg, pk))
shutil.rmtree(d, ignore_errors=True)
h4 = copy.deepcopy(HIST); h4['days'][2]['picks'][0]['_delta'] = '6.0'; h4['days'][2]['units'] = '+6.00u'
refuses('stored _delta does not follow from its stake', {**DECL, 'date': '2026-09-30', 'pick': 'White Sox ML', 'from': '5u', 'to': '10u'}, hist=h4)

# 4. live repo: the audit trail and the record agree
live_log = os.path.join(ROOT, 'slates', 'record_corrections.jsonl')
if os.path.exists(live_log):
    lh = json.load(open(os.path.join(ROOT, 'history.json')))
    entries = [json.loads(line) for line in open(live_log) if line.strip()]
    # A later correction of the same pick and field (a reversal) supersedes an earlier one: the
    # earlier entry must chain into it (its 'to' is the next one's 'from'), and only the latest
    # entry's value is what the pick carries now.
    for i, e in enumerate(entries):
        key = (e['id'].split('|')[0], e['pick'], e['field'])
        nxt = next((n for n in entries[i + 1:] if (n['id'].split('|')[0], n['pick'], n['field']) == key), None)
        row = next((x for x in lh['days'] if x.get('date') == key[0]), None)
        on_row = bool(row) and any(c.get('id') == e['id'] for c in row.get('corrections') or [])
        pk = next((p for p in (row or {}).get('picks') or [] if p.get('name') == e['pick']), None)
        last = bool(row) and (row.get('corrections') or [{}])[-1].get('id') == e['id']
        if nxt is None and e['field'] == 'line+odds':
            # an owner-ordered line+odds fix ('+2.5 -194' -> '+1.5 -122') renames the pick by its
            # line and reprices it: the row carries pick_to at the corrected odds and no longer the
            # published name, the pick's delta follows from its result at that price and stake, and
            # the day units follow from its picks
            (ln_from, _), (ln_to, odds_to) = e['from'].split(), e['to'].split()
            pk = next((p for p in (row or {}).get('picks') or [] if p.get('name') == e.get('pick_to')), None)
            check(f"live: {e['id']} on its history row, pick now {e.get('pick_to')} {odds_to}, day units follow from its picks",
                  on_row and pk is not None and e['pick'].rsplit(' ', 1)[-1] == ln_from
                  and e['pick_to'] == e['pick'].rsplit(' ', 1)[0] + ' ' + ln_to and pk.get('odds') == odds_to
                  and not any(p.get('name') == e['pick'] for p in row.get('picks') or [])
                  and abs(rc.pick_exact(pk) - rf.expected_delta(rc.RES[pk['result']], rf.american(odds_to), rf.stake_of(pk['units']))) <= rf.EXACT
                  and (not last or row.get('units') == e['day_units_to'])
                  and rf.fmt_units(rc.day_exact(row)) == row.get('units'), (row or {}).get('units'))
        elif nxt is None:
            check(f"live: {e['id']} on its history row, pick now {e['to']}, day units follow from its picks",
                  on_row and pk is not None and pk.get(e['field']) == e['to']
                  and (not last or row.get('units') == e['day_units_to'])
                  and rf.fmt_units(rc.day_exact(row)) == row.get('units'), (row or {}).get('units'))
        else:
            check(f"live: {e['id']} on its history row, superseded by {nxt['id']} (chains {e['to']})",
                  on_row and nxt['from'] == e['to'] and nxt.get('day_units_from') == e['day_units_to'],
                  nxt['id'])

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
