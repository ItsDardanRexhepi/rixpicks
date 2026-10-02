#!/usr/bin/env python3
"""Wooder Rolling Record render fixture (live-site M1 / OS-14 / LS-14, Oct 1).

slates/wooder_record.json grades picks with status won/lost/void, but the row pill knew only the
keys w/l/p, so all 90 graded rows read "pending" under a "41-47 0 pending" header. 37 prices are
strings like "74c/None" (a Python None leaking from the feed writer) and showed as such. The record
also stops at Mon Sep 28 while Past Tickets carries later graded Dingers, with nothing on the card
saying which picks it covers. Checks, against the real script text in each builder twin:
graded rows show W / L / P / Void, only truly pending rows read pending, a missing price part is
dropped, and the card states the last day it covers.
Run: python3 scripts/test_wooder_record_render.py [builder.py ...]
"""
import ast, json, os, re, subprocess, sys, warnings
warnings.simplefilter('ignore', SyntaxWarning)  # the builder source carries pre-existing invalid escapes inside JS templates

SD = os.path.dirname(os.path.abspath(__file__))
BUILDERS = [os.path.abspath(a) for a in sys.argv[1:]] or [os.path.join(SD, 'build_gh_page_v2.py'), os.path.join(SD, '_build_nocanon_v2.py')]
failures = 0
def check(name, ok):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name)
    if not ok: failures += 1

def module_text(path):
    for node in ast.walk(ast.parse(open(path).read())):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and 'id="rpWRec"' in node.value and 'function paint(' in node.value:
            return node.value
    return ''

def fn(js, name):
    i = js.find('function ' + name + '(')
    if i < 0: return ''
    d = 0
    for k in range(js.index('{', i), len(js)):
        if js[k] == '{': d += 1
        elif js[k] == '}':
            d -= 1
            if not d: return js[i:k + 1]
    return ''

J = {'record': {'wins': 2, 'losses': 2, 'pushes': 1, 'pending': 1},
     'picks': [
         {'label': 'Juan Soto', 'market': 'home_run', 'matchup': 'NYM at WSH', 'venue': 'DKP', 'price': '74c/None', 'status': 'lost', 'window': 'dingers-2026-09-27', 'received': '2026-09-27'},
         {'label': 'Pete Alonso', 'market': 'home_run', 'venue': 'DKP', 'price': None, 'status': 'void', 'window': 'dingers-2026-09-27', 'received': '2026-09-27'},
         {'label': 'Saquon Barkley', 'market': 'anytime_td', 'venue': 'KAL', 'price': '68c/-213', 'status': 'won', 'window': 'mon-night', 'received': '2026-09-28T11:18:00-07:00'},
         {'label': 'A J Brown', 'market': 'receptions', 'venue': 'DK', 'price': '+120', 'status': 'lost', 'window': 'mon-night', 'received': '2026-09-28T11:18:00-07:00'},
         {'label': 'Legacy W', 'market': 'ml', 'status': 'w', 'window': 'mon-night', 'received': '2026-09-28'},
         {'label': 'Graded Push', 'market': 'total_over', 'line': 44.5, 'status': 'push', 'window': 'mon-night', 'received': '2026-09-28'},
         {'label': 'Still Open', 'market': 'anytime_td', 'status': 'pending', 'window': 'mon-night', 'received': '2026-09-28'}]}

for B in BUILDERS:
    tag = os.path.basename(B)
    js = module_text(B)
    check(f'{tag}: Rolling Record module found', bool(js))
    if not js: continue
    mm = re.search(r'var MM=\{[^;]*\};', js)
    parts = [mm.group(0) if mm else 'var MM={};'] + [fn(js, n) for n in ('esc', 'wlabel', 'pill', 'thru', 'paint')]
    prog = '\n'.join(parts) + '\nvar box={innerHTML:""};paint(' + json.dumps(J) + ');console.log(JSON.stringify(box.innerHTML));'
    r = subprocess.run(['node', '-e', prog], capture_output=True, text=True)
    out = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else ''
    check(f'{tag}: record renders', bool(out))
    rows = re.findall(r'<b>([^<]*)</b> <span style="color:#8a8f98">.*?</span></span><span style="white-space:nowrap">(.*?)</span></div>', out)
    pill = {lbl: re.sub(r'<[^>]+>', ' ', tail).split()[-1] if tail else '' for lbl, tail in rows}
    check(f'{tag}: lost row shows L (not pending)', pill.get('Juan Soto') == 'L' and pill.get('A J Brown') == 'L')
    check(f'{tag}: won row shows W', pill.get('Saquon Barkley') == 'W')
    check(f'{tag}: void row shows Void', pill.get('Pete Alonso') == 'Void')
    check(f'{tag}: push row shows P', pill.get('Graded Push') == 'P')
    check(f'{tag}: legacy w/l/p keys still render', pill.get('Legacy W') == 'W')
    check(f'{tag}: only the still-open pick row reads pending', out.count('>pending<') == 1 and pill.get('Still Open') == 'pending')
    check(f'{tag}: no Python None leaks into a price', 'None' not in out and '74c' in out and '68c/-213' in out)
    check(f'{tag}: card states the last day it covers (Mon, Sep 28)', 'Covers picks through Mon, Sep 28' in out)

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
