#!/usr/bin/env python3
"""C-4.1: the publish workflow's card-ready push to every subscriber never goes out for a card whose card_note carries
the owner-directed / sub-bar disclosure (the only way a card holding a waived numeric bar can build). The rule lives
in scripts/push_gate.py (exit 0 = push, 1 = withheld, 2 = manifest unreadable, also withheld) and publish.yml runs it
before the send; the api.rix-picks.com worker's new-pick push applies the same rule on its side.
Run: python3 scripts/test_c41_push_gate.py"""
import json, os, re, subprocess, sys, tempfile

SD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SD)
GATE = os.path.join(SD, 'push_gate.py')
failures = 0

def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or detail == '' else '  [' + str(detail)[-400:] + ']'))
    if not ok:
        failures += 1

def gate(manifest):
    d = tempfile.mkdtemp(prefix='c41_')
    p = os.path.join(d, 'manifest.json')
    if manifest is not None:
        open(p, 'w').write(manifest if isinstance(manifest, str) else json.dumps(manifest))
    r = subprocess.run([sys.executable, GATE, p], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr

check('C-4.1 scripts/push_gate.py exists', os.path.exists(GATE))
if os.path.exists(GATE):
    for note, want in (('', 0), ('Two picks today.', 0), ('Odds checked at 8:40 AM PT.', 0),
                       ('Owner-directed picks; both sit under the sub-bar floor.', 1), ('owner directive - sub-bar', 1),
                       ('These are owner directives.', 1), ('Sub-bars apply to one pick.', 1),
                       ('Not owner-directed.', 1)):
        rc, out = gate({'card_note': note, 'picks': []})
        check(f'C-4.1 card_note {note!r}: exit {want} ({"push" if want == 0 else "withheld"})', rc == want, (rc, out))
    rc, out = gate({'picks': []})
    check('C-4.1 a card with no card_note pushes', rc == 0, (rc, out))
    rc, out = gate(None)
    check('C-4.1 a missing manifest withholds (exit 2)', rc == 2, (rc, out))
    rc, out = gate('{not json')
    check('C-4.1 an unreadable manifest withholds (exit 2)', rc == 2, (rc, out))

wf = open(os.path.join(ROOT, '.github', 'workflows', 'publish.yml'), encoding='utf-8').read()
m = re.search(r'- name: card-ready push.*?(?=\n      - name: |\Z)', wf, re.S)
step = m.group(0) if m else ''
check('C-4.1 publish.yml has the card-ready push step', bool(step))
gi, si = step.find('scripts/push_gate.py'), step.find('onesignal.com/api')
check('C-4.1 the card-ready push step runs scripts/push_gate.py on manifest.json before the OneSignal send',
      gi >= 0 and si >= 0 and gi < si and 'push_gate.py manifest.json' in step, step[:600])

print('FAILURES: %d' % failures if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
