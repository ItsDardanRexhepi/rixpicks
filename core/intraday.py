"""J-120 (verbatim 9/26 8:33 PM): intraday adds permanent; standards + 2 evidence checks
(J-119 8:32 PM) + J-122 gate, THEN the chain executes card -> push -> record.
RESUMABLE per-stage state: the intent row and each completed stage are separate ledger rows;
a crash between stages resumes the missing stages on retry instead of double-claiming or
stranding the pick. Dedupe: fully-chained pick_id refuses; partial chain resumes."""
import json, os
from datetime import datetime, timezone
from core.checks import two_checks
PICKS = '/home/sandbox/rps_tmp/kb/ledger/picks.jsonl'
STAGES = ('card', 'push', 'record')
def pick_id(pick):
    return f"{pick['event_id']}|{pick['market_class']}|{pick['side']}"
def _rows(ledger_path):
    try:
        with open(ledger_path) as f: return [json.loads(l) for l in f if l.strip()]
    except FileNotFoundError: return []
def chain_state(pid, ledger_path=PICKS):
    intent = any(r.get('kind') == 'pick-add' and r.get('pick_id') == pid for r in _rows(ledger_path))
    done = {r['stage'] for r in _rows(ledger_path)
            if r.get('kind') == 'pick-stage' and r.get('pick_id') == pid and r.get('status') == 'done'}
    return intent, done
def _append(ledger_path, rec):
    os.makedirs(os.path.dirname(ledger_path) or '.', exist_ok=True)
    with open(ledger_path, 'a') as f: f.write(json.dumps(rec) + '\n')
def _readback_stage(ledger_path, pid, stage):
    _, done = chain_state(pid, ledger_path)
    if stage not in done: raise IOError(f'stage {stage} write did not read back for {pid}')
def add_pick(pick, gate, check1, check2, card_append, push, record_chain, ledger_path=PICKS):
    eligible, why = gate
    if not eligible: raise ValueError(f'J-122: not card-eligible - {why}')
    ok, why = two_checks(check1, check2)
    if not ok: raise ValueError(f'J-119/J-120 check bar: {why}')
    pid = pick_id(pick)
    intent, done = chain_state(pid, ledger_path)
    if done == set(STAGES):
        raise ValueError(f'duplicate: {pid} fully chained already')
    rec = {'kind': 'pick-add', 'pick_id': pid, 'intraday': True,
           'ts': datetime.now(timezone.utc).isoformat(), **pick,
           'checks': [{'kind': c.kind, 'sources': c.sources, 'detail': c.detail} for c in (check1, check2)]}
    if not intent:
        _append(ledger_path, rec)
    fns = {'card': card_append, 'push': push, 'record': record_chain}
    results = {}
    for st in STAGES:
        if st in done:
            results[st] = 'resumed-skip (already done)'
            continue
        res = fns[st](rec)                      # exception here leaves stage unrecorded -> resumable
        _append(ledger_path, {'kind': 'pick-stage', 'pick_id': pid, 'stage': st, 'status': 'done',
                              'ts': datetime.now(timezone.utc).isoformat(), 'result': str(res)})
        _readback_stage(ledger_path, pid, st)   # readback verification per stage
        results[st] = res
    return {'added': rec, 'chain': results, 'resumed': sorted(done)} if done else {'added': rec, 'chain': results}
