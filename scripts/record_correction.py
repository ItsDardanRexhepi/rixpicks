#!/usr/bin/env python3
"""record_correction.py - apply ONE declared, owner-approved correction to a stored stake on the
record, auditably, or refuse and write nothing.

The record is append-only: grades land through record_final.py and are never edited. The single
exception is a stored stake that disagrees with the card as published (Sep 25: Astros ML stored at
10u, the published card and the ledger carry 6u). Such a fix is declared, approved by the owner,
applied by this script only, and leaves a trail:

  python3 scripts/record_correction.py CORRECTION.json [--root=DIR] [--check]

CORRECTION.json (every key below, no others):
  {"date": "2026-09-25", "pick": "Astros ML", "field": "units", "from": "10u", "to": "6u",
   "basis": "<why the stored value is wrong, with its source>",
   "approved": "<who approved it, where, when>",
   "units_exact_before": "<exact running units now>"}   <- only when record_done.json carries no
                                                           exact anchor (see units_anchor below)

Rules (any failure -> exit 3, nothing written):
  - field must be 'units'. A result, an odds price, a pick name, a score or a date is never
    corrected here: W-L cannot move, and no other stored field changes.
  - the day row for 'date' must hold exactly one pick named 'pick', and its stored units must equal
    'from' exactly; 'to' is a positive stake in the same 'Nu' form.
  - the pick's exact delta is recomputed with record_final's own card-price rule (expected_delta) at
    the stored odds and result, for both stakes; a stored _delta must equal the 'from' delta.
  - the day row's units must follow from its picks before the fix (fmt_units of the exact sum) and
    are rewritten from them after it; the overall units move by exactly the pick's delta change:
    manifest.json units_pl, record_done.json's exact anchor (units_after_exact + record_after, read
    by record_final.units_anchor) and slates/api_record.json units all agree before and after.
  - after the fix every day record, the overall record and the W-L in manifest.json and the API
    mirror are unchanged, and nothing but the declared paths differs in any file (checked).
Writes: the pick's units (and _delta when it has one), the day's units, a 'corrections' entry on
the day row, manifest units_pl + updated stamp, record_done.json's anchor, the API mirror's units +
updated, and one appended line in slates/record_corrections.jsonl. Re-running an applied correction
is a no-op (exit 0). --check validates and prints the effects without writing.
"""
import copy, json, os, re, sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from record_final import EXACT, american, expected_delta, fmt_units, stake_of  # noqa: E402  the grading rules, not a copy

REQUIRED = ('date', 'pick', 'field', 'from', 'to', 'basis', 'approved')
OPTIONAL = ('units_exact_before',)
FIELDS = ('units',)  # the only correctable field
RES = {'W': 'WON', 'L': 'LOST', 'P': 'PUSH'}
STAKE_RE = re.compile(r'^\d+(?:\.\d+)?u$')


class Refuse(Exception):
    pass


def _read(path):
    """(object, text) of a JSON file, with the dump options that reproduce its exact bytes - a file
    is rewritten in its own format or not at all."""
    text = open(path).read()
    obj = json.loads(text)
    for indent in (2, 1, None):
        for nl in ('', '\n'):
            if json.dumps(obj, indent=indent) + nl == text:
                return obj, {'indent': indent, 'nl': nl}
    raise Refuse(f'{os.path.basename(path)}: cannot reproduce its stored format - not rewritten')


def _write(path, obj, fmt):
    with open(path, 'w') as f:
        f.write(json.dumps(obj, indent=fmt['indent']) + fmt['nl'])


def _num(s, what):
    try:
        return Decimal(str(s).strip().rstrip('u'))
    except (InvalidOperation, ValueError):
        raise Refuse(f'{what} {s!r} unparsable')


def pick_exact(p):
    """Exact unit delta of one graded pick: its stored _delta, else the card-price rule at its stored
    odds, stake and result (record_final.expected_delta)."""
    if '_delta' in p:
        return _num(p['_delta'], f"{p.get('name')!r} _delta")
    res, price, stake = RES.get(p.get('result')), american(p.get('odds')), stake_of(p.get('units'))
    if res is None or price is None or stake is None:
        raise Refuse(f"pick {p.get('name')!r}: result/odds/units {p.get('result')!r} {p.get('odds')!r} "
                     f"{p.get('units')!r} cannot be graded")
    return expected_delta(res, price, stake)


def day_exact(day):
    return sum((pick_exact(p) for p in day.get('picks') or []), Decimal(0))


def day_record(day):
    ps = day.get('picks') or []
    return f"{sum(1 for p in ps if p.get('result') == 'W')}-{sum(1 for p in ps if p.get('result') == 'L')}"


def _diff(a, b, path=''):
    """Paths whose values differ between two JSON values."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append(f'{path}/{k}')
            else:
                out += _diff(a[k], b[k], f'{path}/{k}')
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in _diff(x, y, f'{path}/{i}')]
    return [] if a == b and type(a) is type(b) else [path or '/']


def correction_id(decl):
    return f"{decl['date']}|{decl['pick']}|{decl['field']}|{decl['from']}->{decl['to']}"


def validate(decl):
    if not isinstance(decl, dict):
        raise Refuse('correction must be a JSON object')
    unknown = sorted(set(decl) - set(REQUIRED) - set(OPTIONAL))
    if unknown:
        raise Refuse(f'unknown key(s) {unknown} - a correction declares only {list(REQUIRED + OPTIONAL)}')
    missing = [k for k in REQUIRED if not (isinstance(decl.get(k), str) and decl[k].strip())]
    if missing:
        raise Refuse(f'missing or empty: {missing}')
    if decl['field'] not in FIELDS:
        raise Refuse(f"field {decl['field']!r} is not correctable - only {list(FIELDS)}; a result, price, "
                     f"name, score or date on the record is never edited")
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', decl['date']):
        raise Refuse(f"date {decl['date']!r} is not YYYY-MM-DD")
    for k in ('from', 'to'):
        if not STAKE_RE.match(decl[k]) or stake_of(decl[k]) is None:
            raise Refuse(f"{k} {decl[k]!r} is not a positive stake like '6u'")
    if stake_of(decl['from']) == stake_of(decl['to']):
        raise Refuse('from and to are the same stake - nothing to correct')


def apply(decl, root, check=False, now=None):
    """Returns (rc, message). rc 0 applied or already applied, 3 refused (nothing written)."""
    now = now or datetime.now(timezone.utc)
    validate(decl)
    cid = correction_id(decl)
    P = {k: os.path.join(root, v) for k, v in (('hist', 'history.json'), ('man', 'manifest.json'),
                                                ('done', 'record_done.json'), ('api', os.path.join('slates', 'api_record.json')))}
    log_path = os.path.join(root, 'slates', 'record_corrections.jsonl')
    data, fmt = {}, {}
    for k, path in P.items():
        if not os.path.exists(path):
            raise Refuse(f'{os.path.relpath(path, root)} missing')
        data[k], fmt[k] = _read(path)
    before = copy.deepcopy(data)
    hist, man, done, api = data['hist'], data['man'], data['done'], data['api']

    rows = [d for d in hist.get('days') or [] if d.get('date') == decl['date']]
    if len(rows) != 1:
        raise Refuse(f"{len(rows)} history rows dated {decl['date']} - need exactly one")
    day = rows[0]
    picks = [p for p in day.get('picks') or [] if p.get('name') == decl['pick']]
    if len(picks) != 1:
        raise Refuse(f"{len(picks)} picks named {decl['pick']!r} on {decl['date']} - need exactly one")
    pk = picks[0]
    logged = []
    if os.path.exists(log_path):
        logged = [json.loads(l) for l in open(log_path) if l.strip()]
    if any(c.get('id') == cid for c in day.get('corrections') or []) or any(c.get('id') == cid for c in logged):
        if pk.get(decl['field']) == decl['to']:
            return 0, f'already applied: {cid} - nothing written'
        raise Refuse(f"{cid} is on the audit trail but the stored value is {pk.get(decl['field'])!r}, not {decl['to']!r}")
    if pk.get('units') != decl['from']:
        raise Refuse(f"stored {decl['pick']} units on {decl['date']} are {pk.get('units')!r}, not the declared "
                     f"from {decl['from']!r} - nothing changed")

    res, price = RES.get(pk.get('result')), american(pk.get('odds'))
    if res is None or price is None:
        raise Refuse(f"{decl['pick']}: stored result/odds {pk.get('result')!r} {pk.get('odds')!r} cannot be graded")
    d_from = expected_delta(res, price, stake_of(decl['from']))
    d_to = expected_delta(res, price, stake_of(decl['to']))
    if '_delta' in pk and abs(_num(pk['_delta'], '_delta') - d_from) > EXACT:
        raise Refuse(f"stored _delta {pk['_delta']} does not follow from {res} at {price:+d} on {decl['from']}")
    shift = d_to - d_from

    day_before = day_exact(day)
    if fmt_units(day_before) != day.get('units'):
        raise Refuse(f"{decl['date']} row units {day.get('units')!r} do not follow from its picks "
                     f"({fmt_units(day_before)}) - not rewritten")
    if day_record(day) != day.get('record'):
        raise Refuse(f"{decl['date']} row record {day.get('record')!r} does not follow from its picks ({day_record(day)})")

    # overall exact anchor (record_final.units_anchor reads record_done.json while the manifest shows it)
    shown = _num(man.get('units_pl'), 'manifest units_pl')
    ex = done.get('units_after_exact')
    declared = decl.get('units_exact_before')
    if ex is not None:
        anchor = _num(ex, 'record_done units_after_exact')
        if done.get('record_after') != man.get('record') or fmt_units(anchor) != fmt_units(shown):
            raise Refuse(f"record_done.json anchor {done.get('record_after')} {ex} disagrees with manifest "
                         f"{man.get('record')} {man.get('units_pl')}")
        if declared is not None and _num(declared, 'units_exact_before') != anchor:
            raise Refuse(f'declared units_exact_before {declared} != record_done.json anchor {ex}')
    else:
        if declared is None:
            raise Refuse('record_done.json carries no exact units anchor - declare units_exact_before '
                         '(the last record write\'s units_after_exact)')
        anchor = _num(declared, 'units_exact_before')
        if fmt_units(anchor) != fmt_units(shown):
            raise Refuse(f'declared units_exact_before {declared} does not display as manifest units_pl {man.get("units_pl")!r}')
    rw, rl = [int(x) for x in str(man.get('record')).split('-')[:2]]
    if (api.get('w'), api.get('l')) != (rw, rl) or Decimal(str(api.get('units'))) != Decimal(fmt_units(shown)[:-1]):
        raise Refuse(f"slates/api_record.json {api.get('w')}-{api.get('l')} {api.get('units')} disagrees with "
                     f"manifest {man.get('record')} {man.get('units_pl')}")
    if sum(int(d['record'].split('-')[0]) for d in hist['days']) != rw or \
            sum(int(d['record'].split('-')[1]) for d in hist['days']) != rl:
        raise Refuse(f"history.json day records do not sum to manifest {man.get('record')}")

    after = anchor + shift
    stamp_pt = now.astimezone(ZoneInfo('America/Los_Angeles'))
    applied_at = now.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    effects = {'pick_delta_from': str(d_from), 'pick_delta_to': str(d_to), 'units_shift': str(shift),
               'day_units_from': day['units'], 'day_units_to': fmt_units(day_before + shift),
               'units_exact_from': str(anchor), 'units_exact_to': str(after),
               'units_pl_from': man['units_pl'], 'units_pl_to': fmt_units(after),
               'record': man['record'], 'day_record': day['record']}
    entry = {'id': cid, 'pick': decl['pick'], 'field': decl['field'], 'from': decl['from'], 'to': decl['to'],
             'basis': decl['basis'], 'approved': decl['approved'], 'applied_at': applied_at,
             'day_units_from': effects['day_units_from'], 'day_units_to': effects['day_units_to']}
    pk['units'] = decl['to']
    if '_delta' in pk:
        pk['_delta'] = str(d_to)
    day['units'] = fmt_units(day_exact(day))
    day.setdefault('corrections', []).append(entry)
    man['units_pl'] = fmt_units(after)
    # freshness truth (record_final's rule): a write that moves manifest state stamps `updated`
    man['updated'] = re.sub(r'(\d), 0', r'\1, ', stamp_pt.strftime('%b %d, %I:%M %p PT').replace(' 0', ' '))
    done['record_after'] = man['record']
    done['units_after_exact'] = str(after)
    api['units'] = float(fmt_units(after)[:-1])
    api['updated'] = now.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')

    # post-conditions: the day follows from its corrected picks, W-L is untouched everywhere, and -
    # checked last, right before the write - only the declared paths moved
    if fmt_units(day_exact(day)) != effects['day_units_to']:
        raise Refuse('day units do not follow from the corrected picks')
    if day_record(day) != before['hist']['days'][hist['days'].index(day)]['record'] or man['record'] != before['man']['record'] \
            or (api['w'], api['l']) != (before['api']['w'], before['api']['l']):
        raise Refuse('W-L moved - refused')
    di = hist['days'].index(day)
    pi = day['picks'].index(pk)
    prior = before['hist']['days'][di].get('corrections') or []
    if day['corrections'][:len(prior)] != prior or len(day['corrections']) != len(prior) + 1:
        raise Refuse('the corrections trail is append-only - refused')
    allowed = {
        'hist': {f'/days/{di}/picks/{pi}/units', f'/days/{di}/picks/{pi}/_delta', f'/days/{di}/units', f'/days/{di}/corrections'},
        'man': {'/units_pl', '/updated'},
        'done': {'/record_after', '/units_after_exact'},
        'api': {'/units', '/updated'}}
    for k in data:
        extra = [p for p in _diff(before[k], data[k]) if p not in allowed[k]]
        if extra:
            raise Refuse(f'{k}: undeclared change(s) {extra} - refused')

    if check:
        return 0, 'CHECK (nothing written): ' + json.dumps({'id': cid, **effects})
    for k, path in P.items():
        _write(path, data[k], fmt[k])
    with open(log_path, 'a') as f:
        f.write(json.dumps({**entry, 'effects': effects}) + '\n')
    return 0, ('CORRECTION APPLIED: ' + cid + f" | {decl['date']} {effects['day_units_from']} -> {effects['day_units_to']}"
               f" | overall {effects['units_pl_from']} -> {effects['units_pl_to']} (exact {anchor} -> {after})"
               f" | record {man['record']} unchanged")


def main(argv):
    args = [a for a in argv[1:] if not a.startswith('--')]
    root = os.path.join(HERE, '..')
    for a in argv[1:]:
        if a.startswith('--root='):
            root = a.split('=', 1)[1]
    if len(args) != 1:
        print(__doc__.split('\n\n')[2], file=sys.stderr)
        return 2
    try:
        decl = json.load(open(args[0]))
        rc, msg = apply(decl, root, check='--check' in argv)
    except Refuse as e:
        print(f'REFUSE: {e}', file=sys.stderr)
        return 3
    except (OSError, ValueError) as e:
        print(f'REFUSE: {type(e).__name__}: {e}', file=sys.stderr)
        return 3
    print(msg)
    return rc


if __name__ == '__main__':
    sys.exit(main(sys.argv))
