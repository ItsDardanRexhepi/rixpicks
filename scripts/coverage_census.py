#!/usr/bin/env python3
"""Same-run 13-league event-instance coverage census, reconciled row-by-row against hunt_v2.py output.

Closes the audit HIGH (2026-09-27 closeout): coverage of the daily slate may never be certified
without a complete same-run census reconciled to canonical hunt_v2.py row-by-row. Run in the SAME
pipeline invocation as hunt_v2.py, immediately after it, on the same two artifacts:

    python3 scripts/coverage_census.py /tmp/slate_day_<date>.json /tmp/hunt_v2_<date>.jsonl slates/coverage_census.json

Same-run evidence: every slate ROW must appear exactly once in the hunt log and the log must
carry no other rows. The row identity is the triple (instance_id, league, commence_utc), not the
bare instance_id: a golf tournament id recurs per tee-time row (distinct commence_utc) and the
grouped tennis tours share an event id across ATP and WTA rows (distinct league). Bare-id
uniqueness false-failed on both (2026-09-28 local replication). Any break in the triple
correspondence = FAIL LOUD (exit 2, nothing written) - a census from mismatched runs is worse
than none.

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
    # Row identity = (instance_id, league, commence_utc). Multiset correspondence, 1:1: each
    # slate row's triple exactly once in the hunt log, no extras, no duplicates either side.
    def _key(instance_id, league, commence):
        return (str(instance_id), league or '', commence or '')
    slate_keys = []
    for r in rows:
        if not r.get('instance_id'):
            _fail('slate row without instance_id - every event instance must be identifiable')
        slate_keys.append(_key(r['instance_id'], r.get('league'), r.get('commence_utc')))
    hunt_keys = [_key(e.get('instance_id'), e.get('league'), e.get('commence_utc')) for e in hunt]
    slate_ctr, hunt_ctr = collections.Counter(slate_keys), collections.Counter(hunt_keys)
    dup_slate = [k for k, c in slate_ctr.items() if c > 1]
    dup_hunt = [k for k, c in hunt_ctr.items() if c > 1]
    missing = [k for k in slate_ctr if k not in hunt_ctr]
    extra = [k for k in hunt_ctr if k not in slate_ctr]
    if dup_slate or dup_hunt or missing or extra:
        _fail('hunt log is not this slate run: '
              f'dup_slate={dup_slate[:3]} dup_hunt={dup_hunt[:3]} missing_in_hunt={missing[:3]} extra_in_hunt={extra[:3]}')
    hunt_by_key = {_key(e.get('instance_id'), e.get('league'), e.get('commence_utc')): e for e in hunt}

    # ---- per-league census ----
    leagues = {}
    for r in rows:
        lg = r['league']
        e = hunt_by_key[_key(r['instance_id'], r.get('league'), r.get('commence_utc'))]
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
                           'rule': 'every slate row (instance_id+league+commence_utc) appears exactly once in the same-run hunt_v2 log; no extras, no duplicates'},
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
                  'verdict': hunt_by_key[_key(r['instance_id'], r.get('league'), r.get('commence_utc'))].get('verdict'),
                  'class': _reason_class(hunt_by_key[_key(r['instance_id'], r.get('league'), r.get('commence_utc'))])}
                 for r in rows],
    }
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    json.dump(census, open(out_path, 'w'), indent=1)
    print(f"census: {len(rows)} instances across {len(leagues)} leagues reconciled row-by-row against {len(hunt)} hunt rows")
    print(f"certified: {census['coverage']['certified']}" +
          ('' if census['coverage']['certified'] else ' - blockers: ' + '; '.join(census['coverage']['certification_blockers'])))

if __name__ == '__main__':
    main()
