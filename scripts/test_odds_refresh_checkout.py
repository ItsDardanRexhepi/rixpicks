#!/usr/bin/env python3
"""odds-refresh: the refresh job must build from the CURRENT tip of main, not the sha that queued it.
Run 37225011789 (Oct 4, 11:36 PT): the run waited in the odds-refresh concurrency group behind the
previous tick, checked out its queued-at sha c1166324 (before that tick's 9410a4c56 manifest push),
regenerated manifest.json on the stale base, and push_with_guard.sh correctly failed loud
(REBASE GUARD: upstream moved manifest.json). Nothing was published; one tick lost.
Fix: the refresh job checkout takes ref: main (same class as futures_ws, scripts/test_futures_ws_checkout.py).
Part 1 replays it with the real push_with_guard.sh in a scratch repo: stale base fails loud and resets,
tip base pushes. Part 2 checks the workflow: refresh checkout pinned to main, mutex unchanged.
Run: python3 scripts/test_odds_refresh_checkout.py   (exit 1 on any failure)
"""
import os, subprocess, sys, tempfile
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
def git(cwd, *a):
    return subprocess.run(['git', *a], cwd=cwd, capture_output=True, text=True)

guard = os.path.join(ROOT, 'scripts', 'push_with_guard.sh')
def runner(work, base_ref):
    r = os.path.join(work, 'r_' + base_ref.replace('~', '_'))
    git(work, 'clone', '-q', os.path.join(work, 'origin.git'), r)
    for k, v in (('user.email', 't@t'), ('user.name', 't')):
        git(r, 'config', k, v)
    git(r, 'checkout', '-q', '-B', 'main', base_ref)
    git(r, 'branch', '-q', '--set-upstream-to=origin/main', 'main')
    with open(os.path.join(r, 'manifest.json'), 'w') as f:
        f.write('{"run":"%s"}\n' % base_ref)
    git(r, 'commit', '-qam', 'odds refresh')
    p = subprocess.run(['bash', guard], cwd=r, capture_output=True, text=True)
    return p.returncode, git(r, 'rev-parse', 'HEAD').stdout.strip(), git(r, 'rev-parse', 'origin/main').stdout.strip()

with tempfile.TemporaryDirectory() as work:
    git(work, 'init', '-q', '--bare', '-b', 'main', 'origin.git')
    seed = os.path.join(work, 'seed')
    git(work, 'clone', '-q', os.path.join(work, 'origin.git'), seed)
    for k, v in (('user.email', 't@t'), ('user.name', 't')):
        git(seed, 'config', k, v)
    git(seed, 'checkout', '-q', '-B', 'main')
    open(os.path.join(seed, 'manifest.json'), 'w').write('{"v":0}\n')
    git(seed, 'add', '.'); git(seed, 'commit', '-qm', 'base'); git(seed, 'push', '-q', 'origin', 'main')
    stale = git(seed, 'rev-parse', 'HEAD').stdout.strip()
    open(os.path.join(seed, 'manifest.json'), 'w').write('{"v":1}\n')
    git(seed, 'commit', '-qam', 'previous tick odds refresh'); git(seed, 'push', '-q', 'origin', 'main')
    tip = git(seed, 'rev-parse', 'HEAD').stdout.strip()
    rc, head, origin = runner(work, stale)
    check('stale queued-at base: guard fails loud (the Oct 4 failure)', rc != 0, 'rc=%s' % rc)
    check('stale base: nothing stale published (origin stays on the previous tick)', origin == tip, origin[:7])
    rc, head, origin = runner(work, tip)
    check('current tip base: the refresh pushes clean', rc == 0 and origin == head, 'rc=%s' % rc)

wf = yaml.safe_load(open(os.path.join(ROOT, '.github', 'workflows', 'odds_refresh.yml')))
steps = wf['jobs']['refresh']['steps']
co = [s for s in steps if str(s.get('uses', '')).startswith('actions/checkout')]
check('refresh job has one checkout', len(co) == 1)
check('refresh checkout pinned to ref: main', bool(co) and (co[0].get('with') or {}).get('ref') == 'main')
check('concurrency mutex unchanged (group odds-refresh, no cancel)',
      wf['concurrency'] == {'group': 'odds-refresh', 'cancel-in-progress': False}, str(wf.get('concurrency')))
print('\nODDS REFRESH CHECKOUT: ' + ('ALL PASS' if not failures else 'FAILURES: ' + '; '.join(failures)))
sys.exit(1 if failures else 0)
