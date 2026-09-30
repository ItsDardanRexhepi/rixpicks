#!/usr/bin/env python3
# Standing fixture for the odds_prefill_sp demote patch (Sep 30, parent 10:00 AM).
# No refresh-chain producer ever wrote odds_prefill_sp.json, so the builder's PREFILL
# WARNING fired every run as noise; the Sep 29 manifest books_sp seam makes it harmless.
# The patch demotes the warning to info ONLY when the manifest covers books_sp for all
# non-prop picks AND the file is absent. Partial coverage and corrupt files stay loud.
# Bite-proof: run against the pre-patch builder (arg) and it must FAIL (no demote kwarg).
import ast, io, json, os, sys, tempfile
from contextlib import redirect_stderr

def extract(path):
    src = open(path).read()
    tree = ast.parse(src)
    out = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in ('_load_prefill', '_sp_covered'):
            out[node.name] = ast.get_source_segment(src, node)
    return out

def ns_of(fns):
    ns = {'json': json, 'sys': sys, 'os': os, '_rawurl': lambda x: x}
    for s in fns.values():
        exec(s, ns)
    return ns

MISSING = '/tmp/definitely_missing_odds_prefill_sp_fixture.json'
COVERED = {'picks': [{'market_class': 'game', 'game': {'away': 'A', 'home': 'B'}, 'books_sp': {'dk': {'p': 1}}},
                     {'market_class': 'prop', 'game': None}]}
UNCOVERED = {'picks': [{'market_class': 'game', 'game': {'away': 'A', 'home': 'B'}}]}

def run(fns):
    fails = []
    ns = ns_of(fns)
    if '_sp_covered' not in fns:
        return ['FAIL: _sp_covered missing (pre-patch builder)']
    lp, cov = ns['_load_prefill'], ns['_sp_covered']
    if not cov(COVERED): fails.append('FAIL: _sp_covered false on covered manifest')
    if cov(UNCOVERED): fails.append('FAIL: _sp_covered true on uncovered manifest')
    buf = io.StringIO()
    try:
        with redirect_stderr(buf):
            lp(MISSING, wrap=True, demote=True)
    except TypeError as e:
        return ['FAIL: demote kwarg rejected (pre-patch builder): %s' % e]
    err = buf.getvalue()
    if 'prefill info' not in err or 'PREFILL WARNING' in err:
        fails.append('FAIL: demoted missing-file load must print info, not WARNING: %r' % err)
    buf = io.StringIO()
    with redirect_stderr(buf):
        lp(MISSING, wrap=True, demote=False)
    if 'PREFILL WARNING' not in buf.getvalue():
        fails.append('FAIL: uncovered missing-file load must stay loud')
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
        f.write('{corrupt')
        bad = f.name
    try:
        buf = io.StringIO()
        with redirect_stderr(buf):
            lp(bad, wrap=True, demote=False)
        if 'PREFILL WARNING' not in buf.getvalue():
            fails.append('FAIL: corrupt file must stay loud')
    finally:
        os.unlink(bad)
    return fails

twin_a = extract('scripts/build_gh_page_v2.py')
twin_b = extract('scripts/_build_nocanon_v2.py')
fails = []
if twin_a != twin_b:
    fails.append('FAIL: twin builders drifted on _load_prefill/_sp_covered')
fails += run(twin_a)
print('\n'.join(fails) if fails else 'PASS prefill sp demote (twins parity + info/warning behavior)')
sys.exit(1 if fails else 0)
