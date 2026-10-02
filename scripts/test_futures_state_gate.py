#!/usr/bin/env python3
"""Futures page state gate fixture (OS-07, Oct 1).

futures.html rendered tappable Polymarket chips to every visitor, including states where the
Polymarket arm is not live (NV MI AZ CT MD TN UT per the legality table), while Home gates every
offer by the visitor's verified state. The futures chips now use the same table and the same
state resolution as Home: hidden where the arm is not live for a fresh verified state, shown for
an unresolved state (prediction-market default set, as on Home). Runs the real gate script made
by each builder twin against a stub page.
Run: python3 scripts/test_futures_state_gate.py [builder.py ...]
"""
import ast, json, os, subprocess, sys, warnings
warnings.simplefilter('ignore', SyntaxWarning)  # the builder source carries pre-existing invalid escapes inside JS templates

SD = os.path.dirname(os.path.abspath(__file__))
BUILDERS = [os.path.abspath(a) for a in sys.argv[1:]] or [os.path.join(SD, 'build_gh_page_v2.py'), os.path.join(SD, '_build_nocanon_v2.py')]
failures = 0
def check(name, ok):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name)
    if not ok: failures += 1

STUB = r"""
var store=%s, now=Date.now();
var chips=[0,1].map(function(i){var w={children:[],style:{display:''}};var a={parentNode:w,style:{display:''},getAttribute:function(k){return k==='data-book'?'POLY':null;}};w.children.push(a);return a;});
var document={querySelectorAll:function(q){return q.indexOf('futpoly')>=0?chips:[];}};
var localStorage={getItem:function(k){return store.hasOwnProperty(k)?String(store[k]).replace('NOW',now).replace('OLD',now-13*3600*1000):null;}};
var window={addEventListener:function(){}};
%s
console.log(chips.every(function(a){return a.parentNode.style.display==='none';})?'hidden':(chips.every(function(a){return a.parentNode.style.display==='';})?'shown':'mixed'));
"""
def run(gate_html, store):
    js = gate_html.replace('<script>', '').replace('</script>', '')
    r = subprocess.run(['node', '-e', STUB % (json.dumps(store), js)], capture_output=True, text=True)
    return r.stdout.strip() or ('error: ' + r.stderr.strip()[:200])

for B in BUILDERS:
    tag = os.path.basename(B)
    tree = ast.parse(open(B).read())
    ns = {'json': json}
    gate = table = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == '_fut_gate_js':
            exec(compile(ast.Module(body=[node], type_ignores=[]), B, 'exec'), ns); gate = ns['_fut_gate_js']
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'TABLE' for t in node.targets):
            table = ast.literal_eval(node.value)
    check(f'{tag}: futures gate script present', gate is not None and table is not None)
    if gate is None or table is None: continue
    page_fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'build_futures_page'), None)
    wired = page_fn is not None and any(isinstance(c, ast.Call) and getattr(c.func, 'id', '') == '_fut_gate_js' for c in ast.walk(page_fn))
    check(f'{tag}: build_futures_page ships the gate on futures.html', wired)
    g = gate(table)
    fresh = lambda st: {'rp_state': st, 'rp_state_src': 'gps', 'rp_state_ts': 'NOW'}
    for st in ('NV', 'MI', 'AZ', 'CT', 'MD', 'TN', 'UT'):
        check(f'{tag}: Polymarket chip hidden for a verified {st} visitor', run(g, fresh(st)) == 'hidden')
    for st in ('CA', 'NY', 'TX'):
        check(f'{tag}: Polymarket chip shown for a verified {st} visitor', run(g, fresh(st)) == 'shown')
    check(f'{tag}: unresolved state gets the prediction-market default set (chip shown, as on Home)', run(g, {}) == 'shown')
    check(f'{tag}: an expired (13h) NV fix is unresolved, not NV', run(g, {'rp_state': 'NV', 'rp_state_src': 'gps', 'rp_state_ts': 'OLD'}) == 'shown')
    check(f'{tag}: a non-GPS saved state is never trusted', run(g, {'rp_state': 'NV', 'rp_state_src': 'manual', 'rp_state_ts': 'NOW'}) == 'shown')

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
