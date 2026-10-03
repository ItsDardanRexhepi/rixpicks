#!/usr/bin/env python3
"""futures-ws-listener: a run that waited in the concurrency group must listen from the CURRENT
main, not from the sha it was queued at. Scheduled run 36841505656 was queued at 09:15Z on
35b3a5a9, waited behind the live listener until 11:35Z, checked out that 2h20m-old sha, and all
238 tick pushes of its 340-min window failed (its rebase hit the previous listener's appended
ticks): no futures ticks 11:35Z-17:17Z. The listen job's checkout now takes ref: main.

Part 1 replays the mechanism with the listener's real git_push() in a scratch repo (stale base
fails, tip base pushes). Part 2 checks the workflow: listen checkout pinned to main, and the
listener mutex (one concurrency group, never cancel-in-progress) unchanged.
Run: python3 scripts/test_futures_ws_checkout.py   (exit 1 on any failure)
"""
import ast, os, subprocess, sys, tempfile
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

# ---------- 1. mechanism: the listener's own push against a stale vs a current base ----------
src = os.path.join(ROOT, 'scripts', 'futures_ws_listener.py')
tree = ast.parse(open(src).read())
fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('_git', 'git_push')]

def git(cwd, *a):
    return subprocess.run(['git', *a], cwd=cwd, capture_output=True, text=True)

def runner_push(work, base, git_timeout=45):
    """Clone, reset to `base` (what a checkout of that sha gives), append a tick, run git_push()."""
    r = os.path.join(work, 'runner_' + base[:7])
    git(work, 'clone', '-q', '-b', 'main', os.path.join(work, 'origin.git'), r)
    for k, v in (('user.email', 't@t'), ('user.name', 't')):
        git(r, 'config', k, v)
    git(r, 'reset', '-q', '--hard', base)
    with open(os.path.join(r, 'data', 'futures_ws_ticks.jsonl'), 'a') as f:
        f.write('{"ts":"queued run tick"}\n')
    ns = {'subprocess': subprocess, 'time': type('T', (), {'sleep': staticmethod(lambda s: None)}),
          'REPO': r, 'now_iso': lambda: '2026-10-01T11:37:14+00:00',
          'GIT_TIMEOUT': git_timeout, 'GIT_ENV': dict(os.environ), 'log': lambda *a: None}
    exec(compile(ast.Module(body=fns, type_ignores=[]), src, 'exec'), ns)
    return ns['git_push']()

with tempfile.TemporaryDirectory() as work:
    git(work, 'init', '-q', '--bare', '-b', 'main', 'origin.git')
    seed = os.path.join(work, 'seed')
    git(work, 'clone', '-q', os.path.join(work, 'origin.git'), seed)
    for k, v in (('user.email', 't@t'), ('user.name', 't')):
        git(seed, 'config', k, v)
    git(seed, 'checkout', '-q', '-b', 'main')
    os.makedirs(os.path.join(seed, 'data'))
    open(os.path.join(seed, 'data', 'futures_ws_ticks.jsonl'), 'w').write('{"ts":"t0"}\n')
    open(os.path.join(seed, 'data', 'futures_ws_heartbeat.json'), 'w').write('{}\n')
    git(seed, 'add', '-A'); git(seed, 'commit', '-qm', 'ticks t0'); git(seed, 'push', '-q', 'origin', 'main')
    queued_at = git(seed, 'rev-parse', 'HEAD').stdout.strip()
    for i in range(1, 4):   # the live listener keeps appending while the cron run waits in the queue
        with open(os.path.join(seed, 'data', 'futures_ws_ticks.jsonl'), 'a') as f:
            f.write('{"ts":"t%d"}\n' % i)
        git(seed, 'commit', '-qam', 'ticks t%d' % i); git(seed, 'push', '-q', 'origin', 'main')
    tip = git(seed, 'rev-parse', 'HEAD').stdout.strip()
    stale = runner_push(work, queued_at)
    check('replay: listener on the queued-at sha cannot push (run 36841505656 class)', stale.startswith('push-failed'), stale)
    fresh = runner_push(work, tip)
    check('replay: listener on the current tip pushes', fresh == 'pushed', fresh)

# ---------- 1b. hang guard: a git call that never returns must not freeze the pusher (Oct 3: no ticks 17:51Z on) ----------
import time as _t
with tempfile.TemporaryDirectory() as work:
    git(work, 'init', '-q', '--bare', '-b', 'main', 'origin.git')
    seed = os.path.join(work, 'seed')
    git(work, 'clone', '-q', os.path.join(work, 'origin.git'), seed)
    for k, v in (('user.email', 't@t'), ('user.name', 't')):
        git(seed, 'config', k, v)
    git(seed, 'checkout', '-q', '-b', 'main')
    os.makedirs(os.path.join(seed, 'data'))
    open(os.path.join(seed, 'data', 'futures_ws_ticks.jsonl'), 'w').write('{"ts":"t0"}\n')
    open(os.path.join(seed, 'data', 'futures_ws_heartbeat.json'), 'w').write('{}\n')
    git(seed, 'add', '-A'); git(seed, 'commit', '-qm', 't0'); git(seed, 'push', '-q', 'origin', 'main')
    base0 = git(seed, 'rev-parse', 'HEAD').stdout.strip()
    # a git wrapper whose pull/push hang forever (network stall class)
    real = subprocess.run(['which', 'git'], capture_output=True, text=True).stdout.strip()
    fake = os.path.join(work, 'fakebin'); os.makedirs(fake)
    open(os.path.join(fake, 'git'), 'w').write('#!/bin/sh\ncase "$1" in pull|push) sleep 30;; esac\nexec %s "$@"\n' % real)
    os.chmod(os.path.join(fake, 'git'), 0o755)
    old_path = os.environ['PATH']; os.environ['PATH'] = fake + os.pathsep + old_path
    try:
        t0 = _t.time(); hung = runner_push(work, base0, git_timeout=2); dt = _t.time() - t0
    finally:
        os.environ['PATH'] = old_path
    check('hang guard: stalled git pull/push returns within the timeout budget, not never', dt < 40 and hung.startswith('push-failed'), f'{hung} after {dt:.0f}s')

# ---------- 2. the workflow ----------
wf = yaml.safe_load(open(os.path.join(ROOT, '.github', 'workflows', 'futures_ws.yml')))
conc = wf.get('concurrency') or {}
check('listener mutex kept: one futures-ws-listener group', conc.get('group') == 'futures-ws-listener', repr(conc))
check('listener mutex kept: a running window is never cancelled', conc.get('cancel-in-progress') is False, repr(conc))
listen = (wf.get('jobs') or {}).get('listen') or {}
co = [s for s in listen.get('steps') or [] if str(s.get('uses', '')).startswith('actions/checkout')]
check('listen job checks out the repo once', len(co) == 1, f'{len(co)} checkout steps')
ref = ((co[0].get('with') or {}).get('ref') if co else None)
check('listen checkout takes the current main, not the queued-at sha', ref == 'main', f'ref={ref!r}')

if failures:
    print(f'FUTURES WS CHECKOUT: {len(failures)} FAILURES')
    sys.exit(1)
print('FUTURES WS CHECKOUT: ALL PASS')
