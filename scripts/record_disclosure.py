#!/usr/bin/env python3
"""record_disclosure.py - carry the late-post disclosure a published card already carries onto a
graded history.json row that was written without it, auditably, or refuse and write nothing.

record_final.py copies added_after_kickoff / added_after_final from the card onto the row at grading.
Rows graded before it did (the Oct 2 owner-override picks Under 3.5, Over 43.5 and Under 54.5, carded
after their finals) were written without the flags, and record_final never grades a row twice, so
record.html, yesterday.html and the Home learnings panel showed no tag for them. This is the declared
path that brings such a row in line with its card:

  python3 scripts/record_disclosure.py [--root=DIR] [--check]

Nothing is typed in: the flags come only from the published card. For each pick on a published card
(manifests/ snapshots and the live manifest.json) that carries a flag, record_final's own rules find
the card it belongs to (card_rows: the card's date, every published copy) and the disclosure those
copies make (disclosure_of). Its row is the one pick on that card date's history.json day with the
card pick's name at the card price, and its grade key must be in record_done.json. A pick not graded
yet is left to record_final, which copies the flags when it grades it.

Rules (any failure -> exit 3, nothing written):
  - the card's copies must agree (disclosure_of): a flag that is not true/false, copies that
    contradict each other, or after-the-final without after-kickoff is refused;
  - a graded pick's row must be found exactly once; a flag already on that row must be a JSON boolean
    equal to the card's (a row that says false where the card says true, or claims a flag its card
    does not, is refused and never overwritten);
  - only JSON true flags are added, only to those rows; nothing else in history.json moves (checked),
    and history.json is rewritten in its own stored format or not at all;
  - an MMA pick, or a pick with no grade key, that carries a flag is refused: it is not bound here.
Writes: the added flags, and one line per row in slates/record_disclosures.jsonl (id, card date,
pick, grade key, flags added, the card copies that carry them, applied_at). Re-running once every row
carries its card's disclosure is a no-op (exit 0). --check prints what would change and writes nothing.
W-L, units, results, prices, names and scores never move here.
"""
import copy, glob, json, os, sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import record_final as rf  # noqa: E402  the grading rules, not a copy
from record_correction import Refuse, _diff, _read, _write  # noqa: E402  same format-preserving IO

FLAGS = rf.DISCLOSURE_FIELDS
LOG = os.path.join('slates', 'record_disclosures.jsonl')


def _card_price(p):
    """record_final's card price: card_american when the card carries one, else its odds."""
    return rf.american(p.get('card_american')) if p.get('card_american') is not None else rf.american(p.get('odds'))


def _snapshots(root):
    return sorted(glob.glob(os.path.join(root, 'manifests', 'manifest-*.json'))) + [os.path.join(root, 'manifest.json')]


def _flagged_picks(root):
    """{grade key: card pick} for every published pick that carries a late-post flag (true or not)."""
    out = {}
    for path in _snapshots(root):
        try:
            snap = json.load(open(path))
        except (OSError, ValueError):
            continue
        for p in snap.get('picks') or []:
            if not isinstance(p, dict) or not any(f in p for f in FLAGS):
                continue
            if str(p.get('espn_league') or '').startswith('mma/'):
                raise Refuse(f"MMA pick {p.get('name')!r} in {os.path.relpath(path, root)} carries a late-post flag - "
                             'MMA rows are not bound by grade key, so it is not carried here')
            key = rf.card_key(p)
            if key is None:
                raise Refuse(f"pick {p.get('name')!r} in {os.path.relpath(path, root)} carries a late-post flag but no "
                             'grade key (event id and market class) - it cannot be bound to a row')
            out.setdefault(key, p)
    return out


def _sources(root, key, day):
    """Card copies (relative paths) of this pick on its card date that carry a true flag."""
    out = []
    for path in _snapshots(root):
        try:
            snap = json.load(open(path))
        except (OSError, ValueError):
            continue
        if rf.card_date_of(snap) != day or snap.get('date') != day:
            continue
        if any(isinstance(p, dict) and rf.card_key(p) == key and any(p.get(f) is True for f in FLAGS)
               for p in snap.get('picks') or []):
            out.append(os.path.relpath(path, root))
    return out


def plan(root):
    """(history, its stored format, [planned additions], [pending notes]). Raises Refuse."""
    rf.MAN = os.path.join(root, 'manifest.json')
    rf.MANIFESTS = os.path.join(root, 'manifests')
    hist, fmt = _read(os.path.join(root, 'history.json'))
    done = json.load(open(os.path.join(root, 'record_done.json')))
    processed = set(done.get('processed') or [])
    adds, pending = [], []
    for key, p0 in sorted(_flagged_picks(root).items()):
        day, rows = rf.card_rows({'grade_id': key, 'league': p0.get('espn_league'), 'pick': p0.get('name')})
        if day is None:
            if key in processed:
                raise Refuse(f'{key} ({p0.get("name")!r}) is graded but its card cannot be told: {rows}')
            pending.append(f'{key} ({p0.get("name")!r}): {rows} - not graded, nothing to carry')
            continue
        cp = rows[0]
        try:
            want = rf.disclosure_of(rows)
        except ValueError as e:
            raise Refuse(f'the {day} card pick {cp.get("name")!r} carries a malformed late-post disclosure: {e}')
        if key not in processed:
            pending.append(f'{day} {cp.get("name")!r} ({key}): not graded yet - record_final carries the flags at grading')
            continue
        price = _card_price(cp)
        days = [d for d in hist.get('days') or [] if d.get('date') == day]
        hits = [(di, pi) for di, d in enumerate(hist.get('days') or []) if d.get('date') == day
                for pi, r in enumerate(d.get('picks') or [])
                if isinstance(r, dict) and r.get('name') == cp.get('name') and price is not None and rf.american(r.get('odds')) == price]
        if len(days) != 1 or len(hits) != 1:
            raise Refuse(f'{day} {cp.get("name")!r} ({key}) is graded but {len(hits)} row(s) on {len(days)} {day} day(s) '
                         'carry its name at the card price - need exactly one')
        di, pi = hits[0]
        row = hist['days'][di]['picks'][pi]
        added = {}
        for f in FLAGS:
            card_says = want.get(f, False)
            if f in row:
                if not isinstance(row[f], bool):
                    raise Refuse(f'{day} {cp.get("name")!r}: the row carries a malformed {f} ({row[f]!r}) - never overwritten')
                if row[f] is not card_says:
                    raise Refuse(f'{day} {cp.get("name")!r}: the row says {f}={row[f]!r}, the card says {card_says!r} - '
                                 'never overwritten')
            elif card_says:
                added[f] = True
        if added:
            adds.append({'di': di, 'pi': pi, 'date': day, 'pick': cp.get('name'), 'grade_id': key, 'added': added,
                         'source': _sources(root, key, day)})
    adds.sort(key=lambda a: (a['di'], a['pi']))  # history order: the day, then the row's place on it
    return hist, fmt, adds, pending


def apply(root, check=False, now=None):
    """Returns (rc, message). rc 0 applied or nothing to carry, 3 refused (nothing written)."""
    now = now or datetime.now(timezone.utc)
    hist, fmt, adds, pending = plan(root)
    notes = ''.join(f'\n  pending: {n}' for n in pending)
    if not adds:
        return 0, 'nothing to carry: every graded row carries its card\'s late-post disclosure' + notes
    log_path = os.path.join(root, LOG)
    logged = set()
    if os.path.exists(log_path):
        logged = {json.loads(l).get('id') for l in open(log_path) if l.strip()}
    before = copy.deepcopy(hist)
    applied_at = now.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    entries, allowed = [], set()
    for a in adds:
        eid = f"{a['date']}|{a['pick']}|late-post disclosure"
        if eid in logged:
            raise Refuse(f'{eid} is on the audit trail but the row no longer carries {sorted(a["added"])} - refused')
        row = hist['days'][a['di']]['picks'][a['pi']]
        row.update(a['added'])
        allowed |= {f"/days/{a['di']}/picks/{a['pi']}/{f}" for f in a['added']}
        entries.append({'id': eid, 'date': a['date'], 'pick': a['pick'], 'grade_id': a['grade_id'], 'added': a['added'],
                        'source': a['source'], 'basis': 'Copied from the published card, which carries this disclosure; '
                        'the row was graded before record_final copied it. W-L, units, result, price and score unchanged.',
                        'applied_at': applied_at})
    # checked last, right before the write: only the declared flags moved
    moved = _diff(before, hist)
    extra = [p for p in moved if p not in allowed]
    missing = sorted(allowed - set(moved))
    if extra or missing:
        raise Refuse(f'undeclared change(s) {extra} / missing {missing} - refused')
    summary = ''.join(f"\n  {e['date']} {e['pick']}: + {', '.join(sorted(e['added']))} (from {', '.join(e['source'])})"
                      for e in entries)
    if check:
        return 0, f'CHECK (nothing written): {len(entries)} row(s) would carry their card\'s disclosure' + summary + notes
    _write(os.path.join(root, 'history.json'), hist, fmt)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'a') as f:
        for e in entries:
            f.write(json.dumps(e) + '\n')
    return 0, f'DISCLOSURE CARRIED: {len(entries)} row(s)' + summary + notes


def main(argv):
    root = os.path.join(HERE, '..')
    for a in argv[1:]:
        if a.startswith('--root='):
            root = a.split('=', 1)[1]
        elif a != '--check':
            print(__doc__.split('\n\n')[2], file=sys.stderr)
            return 2
    try:
        rc, msg = apply(root, check='--check' in argv)
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
