#!/usr/bin/env python3
"""J-120 TRIGGER (production): card an intraday gem/candidate through the full bar.
core.gems.card_gem enforces: J-122 verified Kalshi binding + 2 evidence checks with
captured artifacts (book convergence + availability) + resumable card->push->record chain.
EVIDENCE IS MANUAL UNTIL CAPTURE AUTOMATION EXISTS: the caller must pass real artifact
paths (book snapshot JSON, availability capture). No artifacts -> ValueError -> no card.
Usage: card_candidate.py <gate_json_idx or row json file> <conv_artifact1> <conv_artifact2> <avail_artifact1> <avail_artifact2>"""
import json, sys
sys.path.insert(0, '/home/sandbox/rix_tmp')
from core import gems, kalshi_bind
from core.checks import CheckEvidence
def main():
    row = json.load(open(sys.argv[1]))
    conv1, conv2, av1, av2 = sys.argv[2:6]
    feed = '/tmp/kalshi_open_by_league.json'
    cls = row.get('class', 'ml'); side = row.get('side', 'home')
    b = kalshi_bind.bind_event(feed, row.get('event_id'), row.get('away_abbr'), row.get('home_abbr'),
                               cls, side, commence_utc=row.get('commence'),
                               line_hint=row.get('consensus_home_spread') if cls == 'spread' else row.get('consensus_total')) if cls != 'ml' else None
    entry = {'instance_id': row['event_id'], 'match': row['match'], 'market_class': cls,
             'side': side, 'ask': (b.ask_c / 100 if b else 0)}
    c1 = CheckEvidence('book_convergence', [{'id': 'book-snapshot-1', 'artifact_path': conv1, 'snapshot_ts': _now()},
                                            {'id': 'book-snapshot-2', 'artifact_path': conv2, 'snapshot_ts': _now()}],
                       'book convergence captured - see artifacts', row['event_id'], cls)
    c2 = CheckEvidence('availability', [{'id': 'injury-page', 'artifact_path': av1, 'snapshot_ts': _now()},
                                        {'id': 'beat-wire', 'artifact_path': av2, 'snapshot_ts': _now()}],
                       'availability captured - see artifacts', row['event_id'], cls)
    res = gems.card_gem(entry, b, c1, c2,
                        card_append=lambda r: _mark('card_append_pending', r),
                        push=lambda r: _mark('push_needed', r),
                        record_chain=lambda r: _mark('record_chain_pending', r),
                        ledger_path='/home/sandbox/rps_tmp/kb/ledger/picks.jsonl')
    print(json.dumps(res['chain'], indent=1))
def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
def _mark(kind, rec):
    p = f'/home/sandbox/rps_tmp/kb/ledger/{kind}.jsonl'
    with open(p, 'a') as f: f.write(json.dumps(rec) + '\n')
    return f'{kind} written'
if __name__ == '__main__': main()
