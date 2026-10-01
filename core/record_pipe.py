"""J-118 (verbatim 9/26 8:29 PM): record tab updates INSTANTLY at the final -
grade + write + POST /record/update + GET value-verify. 11:30 PM = reconciliation only.
ROW CONTENT RULE: grade + basis ONLY; append-only, no edits.
STAGED + RESUMABLE: append and POST are separate stages tracked in a sidecar state file.
Swamp fixes (9:25 PM): POST/GET retry loop with re-post (never stranded posted-unverified);
resume asserts an existing grade_id's saved row EQUALS the freshly computed row, fail loud
on mismatch; current_state() replays the ledger by construction (last row IS cumulative);
dry_run performs NO writes (ledger, sidecar, or seen)."""
import json, os, time, urllib.request
from datetime import datetime, timezone
from core.units import display_units
ALLOWED_ROW_KEYS = {'grade_id', 'date', 'record', 'win_pct', 'units', 'units_exact', 'basis', 'graded_pick', 'source'}
SITE_URL = 'https://api.rix-picks.com/record/update'
SITE_GET = 'https://api.rix-picks.com/record'
BASIS = 'units: card stake at locked price, 1u = $1,000 bankroll'

def build_record_row(grade_id, date, record, win_pct, units_exact, basis, graded_pick=None, source=None):
    row = {'grade_id': grade_id, 'date': date, 'record': record, 'win_pct': win_pct,
           'units': display_units(units_exact), 'units_exact': str(units_exact), 'basis': basis}
    if graded_pick is not None:
        row['graded_pick'] = graded_pick
    if source is not None:
        row['source'] = source
    extra = set(row) - ALLOWED_ROW_KEYS
    if extra:
        raise ValueError(f'row-content rule violation: {extra}')
    return row

def read_rows(ledger_path):
    try:
        return [json.loads(l) for l in open(ledger_path) if l.strip()]
    except FileNotFoundError:
        return []

def _is_verified(row, state):
    """A row counts toward the cumulative ONLY if verified: the canonical baseline
    (grade_id G-BASELINE-*) or the sidecar marks its POST/GET chain verified."""
    gid = row.get('grade_id', '')
    return gid.startswith('G-BASELINE-') or bool(state.get(gid, {}).get('verified'))

def current_state(ledger_path):
    """(w, l, units_exact) from the last VERIFIED ledger row. Swamp 9:28: the canonical
    G-BASELINE-* row must exist explicitly, and unverified rows (appended but POST/GET
    not yet confirmed) must NOT seed the next grade - that deadlock rejects the retry
    as a resume mismatch forever."""
    from decimal import Decimal
    import re
    rows = read_rows(ledger_path)
    if not rows:
        raise SystemExit('FAIL-CLOSED: record ledger empty (no baseline row) - refusing to grade')
    baselines = [r for r in rows if str(r.get('grade_id', '')).startswith('G-BASELINE-')]
    if not rows[0].get('grade_id', '').startswith('G-BASELINE-'):
        raise SystemExit(f"FAIL-CLOSED: first ledger row is {rows[0].get('grade_id')!r}, "
                         'not the canonical G-BASELINE-* row - refusing to grade')
    # swamp 9:29: the baseline must be the EXACT canonical 0926 row, unique -
    # prefix alone is spoofable.
    from decimal import Decimal as _D
    if len(baselines) != 1:
        raise SystemExit(f'FAIL-CLOSED: {len(baselines)} baseline rows, expected exactly 1')
    b = baselines[0]
    if not (b.get('grade_id') == 'G-BASELINE-0926' and b.get('record') == '13-6'
            and _D(str(b.get('units_exact', 'NaN'))) == _D('3.8937')
            and b.get('date') == '2026-09-26'):
        raise SystemExit(f"FAIL-CLOSED: baseline row does not match canonical values "
                         f"(G-BASELINE-0926 / 13-6 / +3.8937 / 2026-09-26, card-price "
                         f"convention per his word 9/26 9:43 PM): {b}")
    state = _load_state(ledger_path)
    last_verified = None
    for r in rows:
        if _is_verified(r, state):
            last_verified = r
    if last_verified is None:
        raise SystemExit('FAIL-CLOSED: no verified ledger rows (baseline missing sidecar-independent status)')
    m = re.match(r'^(\d+)-(\d+)', last_verified.get('record', ''))
    if not m:
        raise SystemExit(f"FAIL-CLOSED: verified row record {last_verified.get('record')!r} unparseable")
    return int(m.group(1)), int(m.group(2)), Decimal(last_verified['units_exact'])

def verified_grade_ids(ledger_path):
    """All non-baseline grade_ids with a completed (verified) chain - the crash-safe
    seen set. The watcher can die between sidecar verify and its seen write; the ledger
    + sidecar are the durable record, so 'seen' is reconstructible from them (swamp 9:30)."""
    state = _load_state(ledger_path)
    return {r['grade_id'] for r in read_rows(ledger_path) if _is_verified(r, state)
            and not str(r.get('grade_id', '')).startswith('G-BASELINE-')}

def resume_pending(ledger_path, token):
    """Complete the POST/GET chain for every ledger row that is appended but not yet
    verified (sidecar missing or verified=false), in ledger order, BEFORE any successor
    is graded. Returns list of {grade_id, chain}; caller MUST stop if any chain != complete."""
    out = []
    state = _load_state(ledger_path)
    for r in read_rows(ledger_path):
        gid = r.get('grade_id', '')
        if gid.startswith('G-BASELINE-') or state.get(gid, {}).get('verified'):
            continue
        # labels REQUIRED for POST (swamp 9:46): a sparse POST blanks graded_pick/source
        # on the worker, so they live in the durable row and a row without them never POSTs.
        if not r.get('graded_pick') or not r.get('source'):
            out.append({'grade_id': gid, 'chain': 'blocked-missing-labels',
                        'mismatches': None})
            break  # order guard: fail closed, resume nothing after it
        payload = {'record': r['record'], 'win_pct': r['win_pct'], 'units': r['units'],
                   'graded_pick': r['graded_pick'], 'source': r['source']}
        post = post_record_update(payload, token, expected=payload, dry_run=False)
        g = state.get(gid, {})
        g['appended'] = True
        if post.get('post_status') and str(post.get('post_status')).startswith('2'):
            g['posted'] = True
        g['verified'] = bool(post.get('verified'))
        state[gid] = g
        _save_state(ledger_path, state)
        chain = 'complete' if g['verified'] else (
            'posted-unverified-resumable' if g.get('posted') else 'post-failed-resumable')
        out.append({'grade_id': gid, 'chain': chain, 'mismatches': post.get('mismatches')})
        if chain != 'complete':
            break  # order guard: never resume a successor while an earlier grade is unfinished
    return out

def append_row(ledger_path, row):
    """Append-only, idempotent on grade_id."""
    os.makedirs(os.path.dirname(ledger_path) or '.', exist_ok=True)
    for r in read_rows(ledger_path):
        if r.get('grade_id') == row['grade_id']:
            return {'appended': False, 'reason': f"grade_id {row['grade_id']} already recorded"}
    with open(ledger_path, 'a') as f:
        f.write(json.dumps(row) + '\n')
    return {'appended': True}

def _sp(ledger_path): return ledger_path + '.state.json'
def _load_state(ledger_path):
    try: return json.load(open(_sp(ledger_path)))
    except FileNotFoundError: return {}
def _save_state(ledger_path, st):
    json.dump(st, open(_sp(ledger_path), 'w'))

UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}

def _wire_payload(record, win_pct, units_display, graded_pick=None, source=None):
    """The record worker's live schema (discovered 9/26 9:44 PM: {record,win_pct,units}
    gets HTTP 400 'numeric w+l required'; python-urllib UA gets CF 1010 403)."""
    w, l = (int(x) for x in record.split('-')[:2])
    body = {'w': w, 'l': l, 'pct': float(str(win_pct).rstrip('%')),
            'units': float(units_display)}
    if graded_pick is not None:
        body['graded_pick'] = graded_pick
    if source is not None:
        body['source'] = source
    return body

def post_record_update(payload, token, expected=None, dry_run=True, attempts=3, sleep_s=5):
    """POST then GET and VALUE-COMPARE expected fields, up to `attempts` rounds
    (a re-POST each round). Verified only when the GET matches. dry_run: no network.
    `payload` carries logical fields {record, win_pct, units, graded_pick?, source?};
    the wire body is the worker schema {w,l,pct,units,...}."""
    if dry_run:
        return {'dry_run': True, 'would_post': payload, 'would_verify': expected,
                'url': SITE_URL, 'post_status': 'dry', 'verified': True}
    body = _wire_payload(payload['record'], payload['win_pct'], payload['units'],
                         payload.get('graded_pick'), payload.get('source'))
    expect_wire = {'w': body['w'], 'l': body['l'], 'pct': body['pct'], 'units': body['units']}
    # swamp 9:50: labels are publication-bearing - a worker blank/miswrite of
    # graded_pick/source must FAIL the verify, not mark the chain complete.
    for lbl in ('graded_pick', 'source'):
        if lbl in body:
            expect_wire[lbl] = body[lbl]
    last = {'post_status': None, 'verified': False}
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(SITE_URL, data=json.dumps(body).encode(),
                headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json', **UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                post_status = r.status
            if not str(post_status).startswith('2'):
                last = {'post_status': post_status, 'verified': False, 'attempt': attempt}
                continue
            req2 = urllib.request.Request(SITE_GET, headers=UA)
            with urllib.request.urlopen(req2, timeout=20) as r:
                live = json.load(r)
            mismatches = {k: {'expected': v, 'live': live.get(k)} for k, v in expect_wire.items()
                          if str(live.get(k)) != str(v)}
            last = {'post_status': post_status, 'verified': not mismatches,
                    'mismatches': mismatches, 'attempt': attempt}
            if not mismatches:
                return last
        except Exception as e:
            last = {'post_status': None, 'verified': False, 'error': str(e), 'attempt': attempt}
        if attempt < attempts:
            time.sleep(sleep_s)
    return last

def on_final(event_id, final_home, final_away, grade_id, date, record, win_pct, units_exact,
             ledger_path, token, basis=BASIS, dry_run=True, graded_pick=None, source=None):
    """The J-118 chain, staged and resumable: grade row append -> site POST -> value-verify.
    Resume rule (swamp): if grade_id already has a saved row, it MUST equal the freshly
    computed row - a mismatch fails loud, never silently reuses a stale row."""
    row = build_record_row(grade_id, date, record, win_pct, units_exact, basis,
                           graded_pick=graded_pick, source=source)
    existing = [r for r in read_rows(ledger_path) if r.get('grade_id') == grade_id]
    if existing and existing[0] != row:
        raise SystemExit(f'FAIL-CLOSED: resume mismatch for {grade_id}: saved {existing[0]} != fresh {row}')
    if dry_run:
        # NO writes of any kind - ledger, sidecar, and seen stay untouched.
        return {'grade_id': grade_id, 'event_id': event_id,
                'final': f'{final_home}-{final_away}', 'dry_run': True,
                'stages': {'append': 'dry', 'post': {'dry_run': True, 'would_post':
                            {'record': record, 'win_pct': win_pct, 'units': row['units']}}},
                'chain': 'complete'}
    # labels REQUIRED before any write (swamp 9:50): a row that can never POST must
    # never be appended - a label-less pending row would block resume_pending forever.
    if not row.get('graded_pick') or not row.get('source'):
        raise SystemExit(f'FAIL-CLOSED: grade row for {grade_id} lacks graded_pick/source - '
                         'refusing to append or POST (a sparse POST would blank the site fields)')
    state = _load_state(ledger_path)
    g = state.get(grade_id, {})
    if not g.get('appended'):
        append_row(ledger_path, row)  # idempotent; equality already asserted above
        g['appended'] = True
        state[grade_id] = g
        _save_state(ledger_path, state)
    result = {'grade_id': grade_id, 'event_id': event_id, 'final': f'{final_home}-{final_away}',
              'ts': datetime.now(timezone.utc).isoformat(), 'stages': {'append': 'done'}}
    if not g.get('verified'):
        payload = {'record': record, 'win_pct': win_pct, 'units': row['units'],
                   'graded_pick': row['graded_pick'], 'source': row['source']}
        post = post_record_update(payload, token, expected=payload, dry_run=False)
        result['stages']['post'] = post
        if post.get('post_status') and str(post.get('post_status'), ).startswith('2'):
            g['posted'] = True
        g['verified'] = bool(post.get('verified'))
        state[grade_id] = g
        _save_state(ledger_path, state)
        result['chain'] = 'complete' if g['verified'] else (
            'posted-unverified-resumable' if g.get('posted') else 'post-failed-resumable')
        if not g['verified']:
            result['mismatches'] = post.get('mismatches')
        return result
    result['chain'] = 'complete'
    result['resumed'] = True
    return result
