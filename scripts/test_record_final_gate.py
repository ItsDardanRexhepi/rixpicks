#!/usr/bin/env python3
"""record-final 'nothing pending check' fixture (sweep OS-09/DI-14 code cause): the gate must
report changed=true for ANY apply-step write. An eod_day_close brief fill writes history.json
(plus record_done/record_request) and leaves manifest.json alone; the old gate
(`A && B || git diff --quiet -- manifest.json`) read that as nothing pending, so the brief was
never rebuilt into the record pages nor committed and 'What the system learned' stayed empty.
Runs the gate step's own shell from the workflow in a scratch git repo.
Bite-proof: red on the pre-fix gate. Run: python3 scripts/test_record_final_gate.py"""
import os, shutil, subprocess, sys, tempfile, yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
failures = 0

def check(name, actual, expected):
    global failures
    ok = actual == expected
    print(('OK  ' if ok else 'FAIL'), name, '' if ok else f'(got {actual!r}, want {expected!r})')
    if not ok:
        failures += 1

wf = yaml.safe_load(open(os.path.join(ROOT, '.github', 'workflows', 'record_final.yml')))
steps = wf['jobs']['write']['steps']
gate = next((s for s in steps if s.get('id') == 'gate'), None)
check('gate step present', gate is not None, True)
FILES = ('manifest.json', 'history.json', 'record_request.json', 'record_done.json')

def gate_says(changes, force=''):
    tmp = tempfile.mkdtemp(prefix='rf_gate_')
    try:
        git = lambda *a: subprocess.run(['git', *a], cwd=tmp, capture_output=True, text=True, check=True)
        git('init', '-q')
        for f in FILES:
            open(os.path.join(tmp, f), 'w').write('{"v": 0}\n')
        git('add', '.')
        git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'base')
        for f in changes:
            open(os.path.join(tmp, f), 'w').write('{"v": 1}\n')
        out = os.path.join(tmp, '.gh_output')
        script = gate['run'].replace('${{ inputs.force_rebuild }}', force)
        subprocess.run(['bash', '-e', '-c', script], cwd=tmp, env=dict(os.environ, GITHUB_OUTPUT=out), check=True)
        return open(out).read().strip()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

if gate:
    check('eod_day_close brief fill (history + done + request, manifest untouched) -> rebuild + commit',
          gate_says(['history.json', 'record_done.json', 'record_request.json']), 'changed=true')
    check('history.json alone -> changed', gate_says(['history.json']), 'changed=true')
    check('graded finals (manifest + history + done + request) -> changed', gate_says(list(FILES)), 'changed=true')
    check('nothing written -> no rebuild, no commit', gate_says([]), 'changed=false')
    check('force_rebuild dispatch with nothing written -> changed', gate_says([], 'true'), 'changed=true')

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
