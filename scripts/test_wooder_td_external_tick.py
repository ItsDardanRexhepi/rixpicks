#!/usr/bin/env python3
"""wooder-td-tracker must also run on the CF dispatcher's external-tick (repository_dispatch).
Oct 5: the hosted */5 cron fired 0 times between 14:34 and 16:53 UTC; futures.json quotes (written only by
this workflow's futures_quotes step plus odds-refresh calls) went stale and the health gate raised
HOLD ALL PUBLISHES. Same starvation class as x-feed and odds-refresh. Fix: repository_dispatch
types [external-tick] (the 15-min CF tick keeps quotes inside the gate's 20-min window); the cron stays as backstop.
Run: python3 scripts/test_wooder_td_external_tick.py   (exit 1 on any failure)
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
        failures.append(label + (': ' + detail if detail else ''))
    print(f"{'OK  ' if ok else 'FAIL'} {label}" + ('' if ok else f'  [{detail}]'))

def load(name):
    d = yaml.safe_load(open(os.path.join(ROOT, '.github', 'workflows', name)))
    return d.get('on', d.get(True))

on = load('wooder_td.yml')
rd = (on.get('repository_dispatch') or {}).get('types') or []
check('wooder_td listens for external-tick', 'external-tick' in rd, str(rd))
check('wooder_td keeps the cron backstop', bool(on.get('schedule')))
check('wooder_td keeps workflow_dispatch', 'workflow_dispatch' in on)
# the dispatcher must still send external-tick (the time base this relies on)
src = open(os.path.join(ROOT, 'workers', 'gh-dispatcher', 'src', 'worker.js')).read()
check("dispatcher sends event_type 'external-tick'", "event_type: 'external-tick'" in src)
# odds-refresh uses the same tick, so the two lanes share one time base
check('odds_refresh also on external-tick', 'external-tick' in ((load('odds_refresh.yml').get('repository_dispatch') or {}).get('types') or []))
if failures:
    print('\nFAILED:\n - ' + '\n - '.join(failures)); sys.exit(1)
print('\nall checks passed')
