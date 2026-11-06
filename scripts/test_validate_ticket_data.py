#!/usr/bin/env python3
"""Fixture: scripts/validate_ticket_data.py passes the real files, passes a valid edit (archive a ticket),
and blocks the Nov 2 class of bad data (truncated/malformed JSON) plus structural and append-only breaks.
Each negative case is a copy of the real files with one defect; the validator must exit 1 on it."""
import json, os, shutil, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = os.path.join(ROOT, 'scripts', 'validate_ticket_data.py')
FILES = ['past_tickets', 'wooder_tickets', 'wooder_combos', 'wooder_dingers', 'wooder_first_td', 'ultrix_record']
bad = 0
def check(name, cond):
    global bad
    print(('OK  ' if cond else 'FAIL'), name)
    bad += (not cond)
def fresh():
    d = tempfile.mkdtemp(prefix='tvd_'); os.makedirs(d + '/slates')
    for f in FILES: shutil.copy(f'{ROOT}/slates/{f}.json', f'{d}/slates/{f}.json')
    return d
def run(d, *extra):
    r = subprocess.run([sys.executable, V, '--root', d, *extra], capture_output=True, text=True)
    return r.returncode, r.stdout
def load(d, f): return json.load(open(f'{d}/slates/{f}.json'))
def save(d, f, o): json.dump(o, open(f'{d}/slates/{f}.json', 'w'), indent=1)
def raw(d, f, fn):
    p = f'{d}/slates/{f}.json'; t = open(p, 'rb').read(); open(p, 'wb').write(fn(t))

d = fresh(); rc, out = run(d); check('positive: real files pass', rc == 0 and 'TICKET DATA OK' in out)
# positive: a valid archive move (active ticket -> past entry) passes, also with the append-only base check
d = fresh(); subprocess.run(['git', 'init', '-q', d]); subprocess.run(['git', '-C', d, 'add', '-A'], capture_output=True)
subprocess.run(['git', '-C', d, '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'base'], capture_output=True)
w = load(d, 'wooder_tickets'); p = load(d, 'past_tickets'); t = w['tickets'].pop()
p['entries'].append({'id': t['id'], 'kind': 'ticket', 'title': t['title'], 'result': 'lost', 'legs': t['legs'], 'archived_at': '2026-11-06T10:00:00-08:00'})
save(d, 'wooder_tickets', w); save(d, 'past_tickets', p)
rc, out = run(d, '--base', 'HEAD'); check('positive: valid archive edit passes vs base', rc == 0)
# negative cases
def neg(name, f, fn, *extra, setup=None):
    d = fresh()
    if setup: setup(d)
    raw(d, f, fn); rc, out = run(d, *extra); check('negative blocked: ' + name, rc == 1 and 'FAIL' in out)
neg('truncated wooder_tickets JSON (Nov 2 class)', 'wooder_tickets', lambda b: b[:len(b) // 2])
neg('trailing comma / bad separator', 'wooder_tickets', lambda b: b.replace(b'}\n  ]', b'},\n  ]', 1) if b'}\n  ]' in b else b.rstrip()[:-1] + b',}')
neg('empty file', 'past_tickets', lambda b: b'')
neg('BOM', 'past_tickets', lambda b: b'\xef\xbb\xbf' + b)
neg('NaN value', 'wooder_tickets', lambda b: b.replace(b'"generated_at"', b'"x": NaN, "generated_at"', 1))
neg('duplicate key', 'wooder_tickets', lambda b: b.replace(b'"version"', b'"version": 1, "version"', 1))
for name, f, fn in [
    ('ticket without legs', 'wooder_tickets', lambda o: o['tickets'][0].update(legs=[])),
    ('duplicate ticket id', 'wooder_tickets', lambda o: o['tickets'].append(dict(o['tickets'][0]))),
    ('ticket missing title', 'wooder_tickets', lambda o: o['tickets'][0].pop('title')),
    ('dollar amount on active ticket', 'wooder_tickets', lambda o: o['tickets'][0].update(placement_note='paid $5.00')),
    ('tickets not a list', 'wooder_tickets', lambda o: o.update(tickets={})),
    ('bad archive result', 'past_tickets', lambda o: o['entries'][0].update(result='maybe')),
    ('bad archived_at', 'past_tickets', lambda o: o['entries'][0].update(archived_at='yesterday')),
    ('entries not a list', 'past_tickets', lambda o: o.update(entries=None)),
    ('id both active and archived', 'past_tickets', lambda o: o['entries'].append({'id': json.load(open(f'{ROOT}/slates/wooder_tickets.json'))['tickets'][0]['id'], 'title': 'x', 'result': 'lost'})),
]:
    d = fresh(); o = load(d, f); fn(o); save(d, f, o); rc, out = run(d); check('negative blocked: ' + name, rc == 1)
# append-only: dropping an archived entry vs a committed base
d = fresh(); subprocess.run(['git', 'init', '-q', d]); subprocess.run(['git', '-C', d, 'add', '-A'], capture_output=True)
subprocess.run(['git', '-C', d, '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'base'], capture_output=True)
p = load(d, 'past_tickets'); p['entries'].pop(0); save(d, 'past_tickets', p)
rc, out = run(d, '--base', 'HEAD'); check('negative blocked: archived entry deleted vs base', rc == 1 and 'disappeared' in out)
d = fresh(); subprocess.run(['git', 'init', '-q', d]); subprocess.run(['git', '-C', d, 'add', '-A'], capture_output=True)
subprocess.run(['git', '-C', d, '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'base'], capture_output=True)
p = load(d, 'past_tickets'); p['entries'].append({'id': 'new-x', 'title': 't', 'result': 'lost', 'detail': 'cost $4.00'}); save(d, 'past_tickets', p)
rc, out = run(d, '--base', 'HEAD'); check('negative blocked: new archive entry with dollars', rc == 1)
print('ALL OK' if not bad else f'{bad} FAIL'); sys.exit(1 if bad else 0)
