#!/usr/bin/env python3
"""Same-run 13-league event-instance coverage census, reconciled row-by-row against hunt_v2.py output.

Closes the audit HIGH (2026-09-27 closeout): coverage of the daily slate may never be certified
without a complete same-run census reconciled to canonical hunt_v2.py row-by-row. Run in the SAME
pipeline invocation as hunt_v2.py, immediately after it, on the same two artifacts:

    python3 scripts/coverage_census.py /tmp/slate_day_<date>.json /tmp/hunt_v2_<date>.jsonl slates/coverage_census.json

Same-run evidence: every slate row's instance_id must appear exactly once in the hunt log with
matching league + commence_utc, and the log must carry no other ids. Any break = FAIL LOUD
(exit 2, nothing written) - a census from mismatched runs is worse than none.

13-league completeness: canonical league keys are read from config_leagues.json (single source of
truth; ATP/WTA and UFC/Boxing are the grouped tennis and fight leagues of the owner's 13). A
canonical league with zero rows in the slate is a coverage gap UNLESS the slate builder attests
"no events today" via an optional top-level "leagues_empty": ["NWSL", ...] marker. Uncertified
days still publish the artifact (certified:false + blockers) so the gap is visible on-site;
reconciliation failures publish nothing.

Served at https://rix-picks.com/slates/coverage_census.json for independent audit.
"""
import json, sys, os, hashlib, datetime, collections

CANON_CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config_leagues.json')

def _sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()

def _fail(msg):
    print('FAIL LOUD: coverage census: ' + msg, file=sys.stderr)
    sys.exit(2)

def _reason_class(entry):
    v = entry.get('verdict')
    r = entry.get('reason', '') or ''
    if v == 'excluded': return 'standing_rule'
    if v == 'not hunted': return 'not_hunted'
    if v == 'not_evaluable': return 'capability_gap'
    if v == 'cut':
        if r.startswith('genuine evaluation'): return 'genuine_evaluation'
        return 'defect'  # e.g. JOIN DEFECT - a cut that is not a genuine evaluation must stay visible
    if v == 'CANDIDATE': return 'candidate'
    return 'unknown'

def main():
    if len(sys.argv) != 4:
        _fail('usage: coverage_census.py <slate_json> <hunt_log_json> <out_json>')
    slate_path, hunt_path, out_path = sys.argv[1:4]
    for p in (slate_path, hunt_path, CANON_CFG):
        if not os.path.exists(p):
            _fail(f'missing input: {p}')
    slate = json.load(open(slate_path))
    hunt = json.load(open(hunt_path))
    canon = sorted(json.load(open(CANON_CFG))['leagues'].keys())

    rows = slate.get('rows')
    if not isinstance(rows, list):
        _fail('slate has no rows array - not a slate_day artifact')
    if not isinstance(hunt, list):
        _fail('hunt output is not a row array - not a hunt_v2 log')

    # ---- row-by-row reconciliation (the same-run binding) ----
    slate_ids = [r.get('instance_id') for r in rows]
    if any(not i for i in slate_ids):
        _fail('slate row without instance_id - every event instance must be identifiable')
    dup_slate = [i for i, c in collections.Counter(slate_ids).items() if c > 1]
    if dup_slate:
        _fail(f'duplicate instance_id in slate: {dup_slate[:5]}')
    hunt_by_id = {}
    dup_hunt = []
    for e in hunt:
        i = e.get('instance_id')
        if i in hunt_by_id: dup_hunt.append(i)
        hunt_by_id[i] = e
    missing = [i for i in slate_ids if i not in hunt_by_id]
    extra = [i for i in hunt_by_id if i not in set(slate_ids)]
    field_mismatch = []
    for r in rows:
        e = hunt_by_id.get(r['instance_id'])
        if not e: continue
        if e.get('league') != r.get('league') or e.get('commence_utc') != r.get('commence_utc'):
            field_mismatch.append(r['instance_id'])
    if dup_hunt or missing or extra or field_mismatch:
        _fail('hunt log is not this slate run: '
              f'duplicates={dup_hunt[:3]} missing_in_hunt={missing[:3]} extra_in_hunt={extra[:3]} field_mismatch={field_mismatch[:3]}')

    # ---- per-league census ----
    leagues = {}
    for r in rows:
        lg = r['league']
        e = hunt_by_id[r['instance_id']]
        L = leagues.setdefault(lg, {'instances': 0, 'by_status': collections.Counter(),
                                    'by_verdict': collections.Counter(), 'by_class': collections.Counter()})
        L['instances'] += 1
        L['by_status'][r.get('status', 'unknown')] += 1
        L['by_verdict'][e.get('verdict', 'unknown')] += 1
        L['by_class'][_reason_class(e)] += 1
    empty_attested = [lg for lg in (slate.get('leagues_empty') or []) if lg in canon]
    uncovered = [lg for lg in canon if lg not in leagues and lg not in empty_attested]
    unknown_leagues = [lg for lg in leagues if lg not in canon]

    # ---- verdict totals (hunt_v2's own summary vocabulary, recomputed from rows) ----
    totals = collections.Counter()
    classes = collections.Counter()
    for e in hunt:
        totals[e.get('verdict', 'unknown')] += 1
        classes[_reason_class(e)] += 1

    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-7)))
    census = {
        'version': 1,
        'generated_at': now.isoformat(),
        'slate': {'path': os.path.basename(slate_path), 'sha256': _sha(slate_path),
                  'date': slate.get('date') or slate.get('slate_date'), 'rows': len(rows)},
        'hunt': {'path': os.path.basename(hunt_path), 'sha256': _sha(hunt_path), 'rows': len(hunt)},
        'reconciliation': {'ok': True, 'matched_rows': len(rows),
                           'rule': 'every slate instance_id appears exactly once in the same-run hunt_v2 log with matching league+commence_utc; no extras, no duplicates'},
        'canonical_leagues': canon,
        'leagues': {lg: {'instances': L['instances'],
                         'by_status': dict(L['by_status']),
                         'by_verdict': dict(L['by_verdict']),
                         'by_class': dict(L['by_class'])}
                    for lg, L in sorted(leagues.items())},
        'leagues_empty_attested': empty_attested,
        'leagues_uncovered': uncovered,
        'leagues_unknown': unknown_leagues,
        'totals': {'by_verdict': dict(totals), 'by_class': dict(classes)},
        'coverage': {
            'leagues_present': len(leagues),
            'leagues_canonical': len(canon),
            'certified': not uncovered and not unknown_leagues,
            'certification_blockers': (
                [f'canonical league absent from slate with no empty-day attestation: {lg}' for lg in uncovered]
                + [f'slate carries league outside canonical config: {lg}' for lg in unknown_leagues]),
            'certification_rule': 'reconciliation ok AND every canonical league either has >=1 event instance in this run or an explicit leagues_empty attestation from the slate builder'},
        'rows': [{'instance_id': r['instance_id'], 'league': r['league'],
                  'match': r.get('match') or f"{r.get('away')} @ {r.get('home')}",
                  'commence_utc': r['commence_utc'], 'status': r['status'],
                  'verdict': hunt_by_id[r['instance_id']].get('verdict'),
                  'class': _reason_class(hunt_by_id[r['instance_id']])}
                 for r in rows],
    }
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    json.dump(census, open(out_path, 'w'), indent=1)
    print(f"census: {len(rows)} instances across {len(leagues)} leagues reconciled row-by-row against {len(hunt)} hunt rows")
    print(f"certified: {census['coverage']['certified']}" +
          ('' if census['coverage']['certified'] else ' - blockers: ' + '; '.join(census['coverage']['certification_blockers'])))

if __name__ == '__main__':
    main()
