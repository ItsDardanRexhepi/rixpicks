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
ALLOWED_ROW_KEYS = {'grade_id', 'date', 'record', 'win_pct', 'units', 'units_exact', 'basis'}
SITE_URL = 'https://api.rix-picks.com/record/update'
SITE_GET = 'https://api.rix-picks.com/record'
BASIS = 'card stake at locked price, $15/u'

def build_record_row(grade_id, date, record, win_pct, units_exact, basis):
    row = {'grade_id': grade_id, 'date': date, 'record': record, 'win_pct': win_pct,
           'units': display_units(units_exact), 'units_exact': str(units_exact), 'basis': basis}
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
    if not rows[0].get('grade_id', '').startswith('G-BASELINE-'):
        raise SystemExit(f"FAIL-CLOSED: first ledger row is {rows[0].get('grade_id')!r}, "
                         'not the canonical G-BASELINE-* row - refusing to grade')
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
        payload = {'record': r['record'], 'win_pct': r['win_pct'], 'units': r['units']}
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

def post_record_update(payload, token, expected=None, dry_run=True, attempts=3, sleep_s=5):
    """POST then GET and VALUE-COMPARE expected fields, up to `attempts` rounds
    (a re-POST each round). Verified only when the GET matches. dry_run: no network."""
    if dry_run:
        return {'dry_run': True, 'would_post': payload, 'would_verify': expected,
                'url': SITE_URL, 'post_status': 'dry', 'verified': True}
    last = {'post_status': None, 'verified': False}
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(SITE_URL, data=json.dumps(payload).encode(),
                headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=20) as r:
                post_status = r.status
            if not str(post_status).startswith('2'):
                last = {'post_status': post_status, 'verified': False, 'attempt': attempt}
                continue
            with urllib.request.urlopen(SITE_GET, timeout=20) as r:
                live = json.load(r)
            mismatches = {k: {'expected': v, 'live': live.get(k)} for k, v in (expected or {}).items()
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
             ledger_path, token, basis=BASIS, dry_run=True):
    """The J-118 chain, staged and resumable: grade row append -> site POST -> value-verify.
    Resume rule (swamp): if grade_id already has a saved row, it MUST equal the freshly
    computed row - a mismatch fails loud, never silently reuses a stale row."""
    row = build_record_row(grade_id, date, record, win_pct, units_exact, basis)
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
        payload = {'record': record, 'win_pct': win_pct, 'units': row['units']}
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
