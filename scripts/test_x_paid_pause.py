#!/usr/bin/env python3
"""X paid-pull pause switch (x-spend safety, Oct 2). The repo variable X_PAID_PULLS=off (also OFF,
false, 0, no, pause, paused) stops every paid X request - x_feed.py pull and verify, news_social.py
pull and trial, and the workflow's spend gate skips every paid step - while the news bridge, the
matcher and the commits keep running. Unset or any other value leaves pulls on.
Every X call is a scripted fake (scripts/fixtures/x_fake.py); none can reach the network.
Run: python3 scripts/test_x_paid_pause.py   (exit 1 on any failure)
"""
import json, os, shutil, subprocess, sys, tempfile
try:
    import yaml
except ImportError:
    sys.exit('pyyaml required')

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, 'fixtures'))
import x_fake  # noqa: E402

failures = []
scratch_dirs = []


def check(label, ok, detail=''):
    if not ok:
        failures.append(label)
    print(f"{'OK  ' if ok else 'FAIL'} {label}" + ('' if ok or detail == '' else f'  [{str(detail)[:300]}]'))


def snapshot(d):
    sl = os.path.join(d, 'slates')
    return {f: open(os.path.join(sl, f)).read() for f in sorted(os.listdir(sl))}


def paused_run(script, argv, value='off'):
    d = x_fake.scratch(headlines=20); scratch_dirs.append(d)
    before = snapshot(d)
    rc, out, calls = x_fake.run(d, script, argv=argv, plan={'default': {'posts': 10}}, env={'X_PAID_PULLS': value})
    return rc, out, calls, before == snapshot(d)


# 1. the scripts make no paid request while paused -------------------------------------------------
for script, argv in [('x_feed', ('pull',)), ('x_feed', ('verify',)), ('news_social', ('pull',)), ('news_social', ('trial',))]:
    rc, out, calls, same = paused_run(script, argv)
    check(f'{script} {argv[0]}: X_PAID_PULLS=off -> no X request', rc == 0 and len(calls) == 0, (rc, len(calls), out[-300:]))
    check(f'{script} {argv[0]}: paused run says so', 'X_PAID_PULLS' in out and 'paused' in out.lower(), out[-300:])
    check(f'{script} {argv[0]}: paused run leaves ledger, feed, state and trials untouched', same)

for value in ('OFF', ' Off ', 'false', '0', 'paused'):
    rc, out, calls, same = paused_run('x_feed', ('pull',), value)
    check(f'X_PAID_PULLS={value!r} pauses too', rc == 0 and len(calls) == 0, (rc, len(calls)))
for value in ('', 'on', 'true'):
    d = x_fake.scratch(); scratch_dirs.append(d)
    rc, out, calls = x_fake.run(d, 'x_feed', plan={'default': {'posts': 10}}, env={'X_PAID_PULLS': value})
    check(f'X_PAID_PULLS={value!r} leaves pulls on', rc == 0 and len(calls) == 4, (rc, len(calls), out[-300:]))

# 2. the spend gate skips every paid step while paused, budget or not ------------------------------
d = x_fake.scratch(); scratch_dirs.append(d)
genv = os.path.join(d, 'github_env'); open(genv, 'w').close()
env = {k: v for k, v in os.environ.items() if not k.startswith('X_')}
env.update({'GITHUB_ENV': genv, 'X_PAID_PULLS': 'off'})
r = subprocess.run([sys.executable, os.path.join(HERE, 'x_budget.py'), 'gate'], cwd=d, env=env, capture_output=True, text=True, timeout=60)
check('gate: X_PAID_PULLS=off with a full budget -> SKIP_X_PULL=1', r.returncode == 0 and 'SKIP_X_PULL=1' in open(genv).read(),
      (r.returncode, open(genv).read(), (r.stdout + r.stderr)[-300:]))
check('gate: the pause reason is printed', 'X_PAID_PULLS' in r.stdout, r.stdout[-300:])
open(genv, 'w').close(); env['X_PAID_PULLS'] = ''
r = subprocess.run([sys.executable, os.path.join(HERE, 'x_budget.py'), 'gate'], cwd=d, env=env, capture_output=True, text=True, timeout=60)
check('gate: unset switch with a full budget -> pulls on', r.returncode == 0 and 'SKIP_X_PULL' not in open(genv).read(), open(genv).read())

# 3. workflow wiring: the switch reaches every X step; news and everything else are not gated on it --
wf = yaml.safe_load(open(os.path.join(ROOT, '.github', 'workflows', 'x_feed.yml')))
job = wf['jobs']['feed']
steps = job.get('steps') or []
runs = lambda s: str(s.get('run') or '')
named = lambda frag: next((i for i, s in enumerate(steps) if frag in runs(s) or frag in str(s.get('name') or '')), -1)
check('job env carries X_PAID_PULLS from the repo variable, paused (off) when unset', (job.get('env') or {}).get('X_PAID_PULLS') == "${{ vars.X_PAID_PULLS || 'off' }}", job.get('env'))
check('X_PAID_PULLS is set in one place (job env key + its vars value)', json.dumps(wf).count('X_PAID_PULLS') == 2, json.dumps(wf).count('X_PAID_PULLS'))
i_bridge, i_gate = named('bridge_worker_news.py'), named('scripts/x_budget.py gate')
i_x, i_ns, i_pub = named('scripts/x_feed.py'), named('scripts/news_social.py'), named('publish X feed')
check('news bridge is the first work step and unconditional', i_bridge == 2 and 'if' not in steps[i_bridge], (i_bridge, steps[i_bridge] if i_bridge >= 0 else None))
check('gate precedes every paid step', 0 <= i_gate < min(i_x, i_ns, i_pub), (i_gate, i_x, i_ns, i_pub))
for i in (i_x, i_ns, i_pub):
    check(f'paid step {steps[i].get("name")!r} is skipped by SKIP_X_PULL', "env.SKIP_X_PULL != '1'" in str(steps[i].get('if') or ''), steps[i].get('if'))
for frag in ('soc_match.py', 'commit feed + burn ledger', 'bridge safety commit'):
    i = named(frag)
    check(f'{frag!r} keeps running when paid pulls are off', i > i_ns and 'SKIP_X_PULL' not in str(steps[i].get('if') or ''), (i, steps[i].get('if') if i >= 0 else None))

# 4. the matcher step keeps working while paused: soc_fixtures.py (run inside it) checks ingest with
# its own fake X and must not read the owner's switch, or the pause would abort the chain.
env = {k: v for k, v in os.environ.items() if not k.startswith('X_')}
env['X_PAID_PULLS'] = 'off'
r = subprocess.run([sys.executable, os.path.join(HERE, 'soc_fixtures.py')], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
check('soc_fixtures (matcher step) still passes with X_PAID_PULLS=off', r.returncode == 0, (r.returncode, (r.stdout + r.stderr)[-400:]))

for p in scratch_dirs:
    shutil.rmtree(p, ignore_errors=True)
print('x paid-pull pause: ' + ('OK' if not failures else f'{len(failures)} FAIL'))
sys.exit(1 if failures else 0)
