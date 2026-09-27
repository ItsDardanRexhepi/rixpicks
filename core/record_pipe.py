"""J-118 (verbatim 9/26 8:29 PM): record tab updates INSTANTLY at the final -
grade + write + POST /record/update + GET value-verify. 11:30 PM = reconciliation only.
ROW CONTENT RULE: grade + basis ONLY; append-only, no edits.
STAGED + RESUMABLE: append and POST are separate stages tracked in a sidecar state file;
a rejected POST leaves the run resumable (retry completes the POST) instead of
skipped-duplicate-forever. The grade row itself stays idempotent on grade_id."""
import json, os, urllib.request
from datetime import datetime, timezone
from core.units import display_units
ALLOWED_ROW_KEYS = {'grade_id', 'date', 'record', 'win_pct', 'units', 'units_exact', 'basis'}
SITE_URL = 'https://api.rix-picks.com/record/update'
SITE_GET = 'https://api.rix-picks.com/record'
def build_record_row(grade_id, date, record, win_pct, units_exact, basis):
    row = {'grade_id': grade_id, 'date': date, 'record': record, 'win_pct': win_pct,
           'units': display_units(units_exact), 'units_exact': str(units_exact), 'basis': basis}
    extra = set(row) - ALLOWED_ROW_KEYS
    if extra: raise ValueError(f'row-content rule violation: {extra}')
    return row
def append_row(ledger_path, row):
    """Append-only, idempotent on grade_id."""
    os.makedirs(os.path.dirname(ledger_path) or '.', exist_ok=True)
    try:
        for line in open(ledger_path):
            if json.loads(line).get('grade_id') == row['grade_id']:
                return {'appended': False, 'reason': f"grade_id {row['grade_id']} already recorded"}
    except FileNotFoundError: pass
    with open(ledger_path, 'a') as f: f.write(json.dumps(row) + '\n')
    return {'appended': True}
def _sp(ledger_path): return ledger_path + '.state.json'
def _load_state(ledger_path):
    try: return json.load(open(_sp(ledger_path)))
    except FileNotFoundError: return {}
def _save_state(ledger_path, st):
    json.dump(st, open(_sp(ledger_path, ), 'w'))
def post_record_update(payload, token, expected=None, dry_run=True):
    """POST then GET and VALUE-COMPARE expected fields. dry_run skips network (tests)."""
    if dry_run:
        return {'dry_run': True, 'would_post': payload, 'would_verify': expected, 'url': SITE_URL,
                'post_status': 'dry', 'verified': True}
    req = urllib.request.Request(SITE_URL, data=json.dumps(payload).encode(),
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=20) as r:
        post_status = r.status
    with urllib.request.urlopen(SITE_GET, timeout=20) as r:
        live = json.load(r)
    mismatches = {k: {'expected': v, 'live': live.get(k)} for k, v in (expected or {}).items()
                  if str(live.get(k)) != str(v)}
    return {'post_status': post_status, 'verified': not mismatches, 'mismatches': mismatches}
def on_final(event_id, final_home, final_away, grade_id, date, record, win_pct, units_exact, basis,
             ledger_path, token, dry_run=True):
    """The J-118 chain, staged and resumable: grade row append -> site POST -> value-verify."""
    state = _load_state(ledger_path)
    g = state.get(grade_id, {})
    row = build_record_row(grade_id, date, record, win_pct, units_exact, basis)
    if not g.get('appended'):
        app = append_row(ledger_path, row)
        if not app['appended'] and not g.get('appended'):
            # row exists from a crashed earlier run whose state file was lost - recover
            g['appended'] = True
        else:
            g['appended'] = True
        state[grade_id] = g; _save_state(ledger_path, state)
    result = {'grade_id': grade_id, 'event_id': event_id, 'final': f'{final_home}-{final_away}',
              'ts': datetime.now(timezone.utc).isoformat(), 'stages': {'append': 'done'}}
    if not g.get('posted'):
        payload = {'record': record, 'win_pct': win_pct, 'units': row['units']}
        post = post_record_update(payload, token, expected=payload, dry_run=dry_run)
        result['stages']['post'] = post
        if dry_run or (post.get('post_status') and str(post.get('post_status')).startswith('2')):
            g['posted'] = True
            g['verified'] = post.get('verified', False)
            state[grade_id] = g; _save_state(ledger_path, state)
            result['chain'] = 'complete' if g['verified'] else 'posted-unverified'
            if not g['verified']: result['mismatches'] = post.get('mismatches')
        else:
            # POST rejected: NOT marked posted -> next fire retries the POST (resumable)
            result['chain'] = 'posted-failed-resumable'
        return result
    result['chain'] = 'complete' if g.get('verified') else 'posted-unverified'
    result['resumed'] = True
    return result
