#!/usr/bin/env python3
"""Every workflow_run trigger must name a workflow that exists, and the failure hooks must watch
every site-critical writer. incident.yml listened for "pages build and deployment", a name no
workflow carries (GitHub's dynamic Pages workflow is "pages-build-deployment"), so Pages deploy
failures 36667637766 and 36758537436 produced no incident; x-feed and record-final were watched
by neither incident-hook nor failure-watchdog.
Run: python3 scripts/test_workflow_run_names.py   (exit 1 on any failure)
"""
import glob, os, sys
try:
    import yaml
except ImportError:
    sys.exit('pyyaml required')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# GitHub-managed workflows that have no .yml file in this repo but do fire workflow_run.
DYNAMIC = {'pages-build-deployment'}
# Site-critical writers whose failure must be captured by incident-hook or failure-watchdog.
MUST_WATCH = {'odds-refresh', 'publish-card', 'pages-build-deployment', 'record-final', 'x-feed',
              'nfl-scores-confirm', 'wooder-td-tracker', 'kalshi-quotes', 'extras-sweep'}

failures = []
def check(label, ok, detail=''):
    if not ok:
        failures.append(label + (': ' + detail if detail else ''))
    print(f"{'OK  ' if ok else 'FAIL'} {label}" + ('' if ok else f'  [{detail}]'))

docs = {}
for path in sorted(glob.glob(os.path.join(ROOT, '.github', 'workflows', '*.yml'))):
    d = yaml.safe_load(open(path)) or {}
    docs[os.path.basename(path)] = d
names = {d.get('name') for d in docs.values() if d.get('name')}
known = names | DYNAMIC

watched = {}
for fname, d in docs.items():
    on = d.get('on', d.get(True)) or {}   # PyYAML reads the bare key `on` as True
    wr = on.get('workflow_run') if isinstance(on, dict) else None
    if not wr:
        continue
    for w in wr.get('workflows') or []:
        check(f'{fname}: workflow_run name {w!r} resolves to a workflow', w in known,
              'no workflow is named this (known: ' + ', '.join(sorted(known)) + ')')
    watched[d.get('name')] = set(wr.get('workflows') or [])

hooks = watched.get('incident-hook', set()) | watched.get('failure-watchdog', set())
for w in sorted(MUST_WATCH):
    check(f'{w} failures are captured by incident-hook or failure-watchdog', w in hooks)
check('x-feed is captured, not auto-redispatched (it is dispatched every few minutes anyway)',
      'x-feed' not in watched.get('failure-watchdog', set()))

if failures:
    print(f'WORKFLOW RUN NAMES: {len(failures)} FAILURES')
    sys.exit(1)
print('WORKFLOW RUN NAMES: ALL PASS')
