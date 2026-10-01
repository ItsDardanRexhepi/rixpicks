#!/usr/bin/env python3
"""Fixture: the watchdog diagnosis must quote the job that FAILED, not jobs[0].
--legacy runs the old jobs[0] selection to prove the fixture bites."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from watchdog_diag import pick_failed_jobs, failing_steps, error_tail
legacy = '--legacy' in sys.argv
def pick(jobs):
    return jobs[:1] if legacy else pick_failed_jobs(jobs)
fails = []
jobs = [{'name': 'hold-check', 'id': 1, 'conclusion': 'success', 'steps': [{'name': 'Run hold-check', 'conclusion': 'success'}]},
        {'name': 'scores', 'id': 2, 'conclusion': 'failure', 'steps': [{'name': 'validate', 'conclusion': 'success'}, {'name': 'confirm NFL scores (self-gated)', 'conclusion': 'failure'}]}]
got = pick(jobs)
if [j['name'] for j in got] != ['scores']: fails.append('picked %s, expected scores' % [j['name'] for j in got])
if failing_steps(got) != ['scores / confirm NFL scores (self-gated)']: fails.append('failing steps wrong: %s' % failing_steps(got))
if [j['name'] for j in pick_failed_jobs([{'name': 'hold-check', 'conclusion': 'failure', 'steps': []}, {'name': 'scores', 'conclusion': 'skipped', 'steps': []}])] != ['hold-check']: fails.append('hold-check-only failure not picked')
if [j['name'] for j in pick_failed_jobs([{'name': 'a', 'conclusion': 'success'}, {'name': 'b', 'conclusion': 'cancelled'}])] != ['b']: fails.append('cancelled fallback wrong')
lines = ['setup noise'] * 30 + ['run step', 'no changes', 'REBASE GUARD: race touched lane-shipped content () - fail loud', '##[error]Process completed with exit code 1.', '##[group]Run mkdir -p incidents', 'later noise error fail']
t = error_tail(lines)
if 'REBASE GUARD' not in t or '##[error]' not in t or 'later noise' in t: fails.append('error_tail did not quote the failing step: %r' % t)
if fails:
    print('FAIL: ' + '; '.join(fails)); sys.exit(1)
print('PASS watchdog diag (failed job picked, step named, tail quotes the failing step)')
