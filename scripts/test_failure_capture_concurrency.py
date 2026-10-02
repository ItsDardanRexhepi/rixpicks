#!/usr/bin/env python3
"""A failure capture is never replaced by a run that a success started (r3 ci review).

incident-hook and failure-watchdog run on every completion of the workflows they watch, success
included; only their jobs are gated on a failure. GitHub keeps at most one running and one pending
run per concurrency group and replaces the pending one when another arrives, whatever
cancel-in-progress says. With the group at workflow level, every success-triggered run entered it
(Pages completes about once a minute; kalshi-quotes and wooder-td every 5 minutes), so a pending
failure capture could be replaced by a later success-triggered run whose job is then skipped, and
that failure's note was dropped. Now:
 - incident.yml has no workflow-level group; its capture job carries one keyed by the failed run's
   id, so no capture ever waits behind or replaces another (each note is its own file, and its
   push retries with a rebase onto main);
 - failure-watchdog has no workflow-level group; its triage job, which runs only for a failure,
   carries the failure-watchdog group (triage stays one at a time: it reads and writes
   watchdog_state.json, the 30-minute retry budget), so a success-triggered run never enters it;
 - nothing is cancelled in progress.
Run: python3 scripts/test_failure_capture_concurrency.py   (exit 1 on any failure)
"""
import os, sys
try:
    import yaml
except ImportError:
    sys.exit('pyyaml required')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
failures = []
def check(label, ok, detail=''):
    if not ok:
        failures.append(label + (': ' + str(detail)[:400] if detail != '' else ''))
    print(f"{'OK  ' if ok else 'FAIL'} {label}" + ('' if ok or detail == '' else f'  [{str(detail)[:400]}]'))

def load(name):
    return yaml.safe_load(open(os.path.join(ROOT, '.github', 'workflows', name))) or {}

FAIL_IF = "${{ github.event.workflow_run.conclusion == 'failure' }}"

# incident-hook
inc = load('incident.yml')
check('incident.yml: no workflow-level concurrency group (every success-triggered run entered it)',
      'concurrency' not in inc, inc.get('concurrency'))
cap = (inc.get('jobs') or {}).get('capture') or {}
check('incident.yml: the capture job runs only for a failure', cap.get('if') == FAIL_IF, cap.get('if'))
cc = cap.get('concurrency') or {}
check('incident.yml: the capture job carries the group, keyed by the failed run id, nothing cancelled',
      isinstance(cc, dict) and str(cc.get('group', '')).startswith('incident-hook')
      and 'github.event.workflow_run.id' in str(cc.get('group', ''))
      and 'workflow_run.name' not in str(cc.get('group', '')) and cc.get('cancel-in-progress') is False, cc)
others = [n for n, j in (inc.get('jobs') or {}).items() if n != 'capture' and (j or {}).get('concurrency')]
check('incident.yml: no other job holds a group', others == [], others)

# failure-watchdog
wd = load('watchdog.yml')
check('watchdog.yml: no workflow-level concurrency group (every success-triggered run entered it)',
      'concurrency' not in wd, wd.get('concurrency'))
jobs = wd.get('jobs') or {}
tri = jobs.get('triage') or {}
tc = tri.get('concurrency') or {}
check('watchdog.yml: the triage job runs only for a failure', 'github.event.workflow_run.conclusion == \'failure\'' in str(tri.get('if', '')),
      tri.get('if'))
check('watchdog.yml: the triage job carries the failure-watchdog group (one triage at a time), nothing cancelled',
      isinstance(tc, dict) and tc.get('group') == 'failure-watchdog' and tc.get('cancel-in-progress') is False, tc)
qs = jobs.get('quota-state') or {}
check('watchdog.yml: the read-only quota-state job runs only for a failure and holds no group',
      qs.get('if') == FAIL_IF and 'concurrency' not in qs, (qs.get('if'), qs.get('concurrency')))
others = [n for n, j in jobs.items() if n not in ('triage',) and (j or {}).get('concurrency')]
check('watchdog.yml: no other job holds a group', others == [], others)

if failures:
    print(f'FAILURE CAPTURE CONCURRENCY: {len(failures)} FAILURES')
    sys.exit(1)
print('FAILURE CAPTURE CONCURRENCY: ALL PASS')
