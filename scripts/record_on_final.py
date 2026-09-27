#!/usr/bin/env python3
"""PRODUCTION J-118 call site: instant record write at a FINAL. Wraps core.record_pipe.on_final
(staged + resumable + value-verified). Usage:
record_on_final.py <event_id> <home_score> <away_score> <grade_id> <date> <record> <win_pct> <units_exact> <basis...>
Token from /tmp/.push_token. Live POST (not dry-run) - this IS the production entry."""
import sys
sys.path.insert(0, '/home/sandbox/rix_tmp')
from decimal import Decimal
from core import record_pipe
LEDGER = '/home/sandbox/rps_tmp/kb/ledger/record_rows.jsonl'
def main():
    a = sys.argv[1:]
    token = open('/tmp/.push_token').read().strip()
    res = record_pipe.on_final(a[0], int(a[1]), int(a[2]), a[3], a[4], a[5], a[6],
                               Decimal(a[7]), ' '.join(a[8:]), LEDGER, token, dry_run=False)
    print(res['chain'], res.get('stages', {}).get('post'))
if __name__ == '__main__': main()
