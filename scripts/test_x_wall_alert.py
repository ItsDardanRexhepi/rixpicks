#!/usr/bin/env python3
"""Sustained X wall alert (x-spend safety, Oct 2). From 9/30 01:39Z every X request returned 402,
but x_wall.py's skip-and-continue path ends the run 'success', so incident-hook (which fires only on
a failed run) saw nothing for about 68 hours. Now:
 - x_feed.py and news_social.py record each run's request outcome (attempted, ok, HTTP codes) to
   the run's outcome file ($X_RUN_OUTCOME);
 - the x-feed 'X wall streak' step counts consecutive due runs on which X denied EVERY request
   (401/402/403) in slates/x_wall_state.json: one success resets it; a run with no request, or with
   other failures mixed in, leaves it as it was;
 - at 4 such runs in a row the last step of the run fails it on purpose (incident-hook records it),
   after the news bridge and every commit step have run; while the wall lasts it fails again every
   6 hours, not every run, so the alert does not turn into a note every five minutes.
Every X call is a scripted fake (scripts/fixtures/x_fake.py); none can reach the network.
Run: python3 scripts/test_x_wall_alert.py   (exit 1 on any failure)
"""
import datetime, json, os, shutil, subprocess, sys
try:
    import yaml
except ImportError:
    sys.exit('pyyaml required')

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, 'fixtures'))
import x_fake  # noqa: E402

UTC = datetime.timezone.utc
failures = []
scratch_dirs = []


def check(label, ok, detail=''):
    if not ok:
        failures.append(label)
    print(f"{'OK  ' if ok else 'FAIL'} {label}" + ('' if ok or detail == '' else f'  [{str(detail)[:300]}]'))


def outcomes(path):
    return [json.loads(l) for l in open(path) if l.strip()] if os.path.exists(path) else []


WALL = {'default': {'error': 402}}

# 1. each script records its run outcome ------------------------------------------------------------
d = x_fake.scratch(headlines=20); scratch_dirs.append(d)
oc = os.path.join(d, 'outcome.jsonl')
rc, out, calls = x_fake.run(d, 'x_feed', plan=WALL, env={'X_RUN_OUTCOME': oc})
got = outcomes(oc)
check('x_feed: walled pull still exits 0 (chain continues on the frozen pool)', rc == 0, (rc, out[-300:]))
check('x_feed: records attempted/ok/codes for the run', got[-1:] and got[-1].get('script') == 'x_feed'
      and got[-1].get('attempted') == 4 and got[-1].get('ok') == 0 and got[-1].get('codes') == ['402'] * 4, got)
rc, out, calls = x_fake.run(d, 'news_social', plan=WALL, env={'X_RUN_OUTCOME': oc})
got = outcomes(oc)
check('news_social: records its run outcome too', rc == 0 and len(got) == 2 and got[1].get('script') == 'news_social'
      and got[1].get('attempted') == len(calls) > 0 and got[1].get('ok') == 0 and set(got[1].get('codes') or []) == {'402'}, (rc, got))
d2 = x_fake.scratch(); scratch_dirs.append(d2)
oc2 = os.path.join(d2, 'outcome.jsonl')
rc, out, calls = x_fake.run(d2, 'x_feed', plan={'seq': [{'error': 402}], 'default': {'posts': 10}}, env={'X_RUN_OUTCOME': oc2})
got = outcomes(oc2)
check('x_feed: a partly successful run records its successes', got and got[-1].get('ok') == 3 and got[-1].get('codes') == ['402'], got)


# 2. the streak step ----------------------------------------------------------------------------------
sd = x_fake.scratch(); scratch_dirs.append(sd)
STATE = os.path.join(sd, 'slates', 'x_wall_state.json')


def streak(records):
    """One due run's streak step: records -> (GITHUB_ENV text, stdout, state)."""
    ocp = os.path.join(sd, 'run_outcome.jsonl')
    if os.path.exists(ocp):
        os.remove(ocp)
    if records is not None:
        with open(ocp, 'w') as f:
            f.writelines(json.dumps(r) + '\n' for r in records)
    genv = os.path.join(sd, 'github_env'); open(genv, 'w').close()
    env = {k: v for k, v in os.environ.items() if not k.startswith('X_')}
    env.update({'GITHUB_ENV': genv, 'X_RUN_OUTCOME': ocp})
    r = subprocess.run([sys.executable, os.path.join(HERE, 'x_wall.py'), 'streak'], cwd=sd, env=env,
                       capture_output=True, text=True, timeout=60)
    try:
        st = json.load(open(STATE))
    except (OSError, ValueError):
        st = {}
    return r.returncode, open(genv).read(), r.stdout + r.stderr, st


den = lambda code='402', n=4: [{'script': 'x_feed', 'attempted': n, 'ok': 0, 'codes': [code] * n},
                               {'script': 'news_social', 'attempted': 5, 'ok': 0, 'codes': [code] * 5}]
ok_run = [{'script': 'x_feed', 'attempted': 4, 'ok': 4, 'codes': []}, {'script': 'news_social', 'attempted': 5, 'ok': 0, 'codes': ['402'] * 5}]

for i in (1, 2, 3):
    rc, genv, out, st = streak(den())
    check(f'denied run {i}: counted, no alert yet', rc == 0 and st.get('streak') == i and 'X_WALL_ALERT' not in genv, (rc, st, genv, out[-300:]))
rc, genv, out, st = streak(den())
check('denied run 4 in a row: alert raised for the run (X_WALL_ALERT=1)', rc == 0 and st.get('streak') == 4 and 'X_WALL_ALERT=1' in genv, (rc, st, genv, out[-300:]))
check('alert message names the streak and the code', 'X_WALL_MSG=' in genv and '4' in genv and '402' in genv, genv)
rc, genv, out, st = streak(den())
check('denied run 5: counted, no repeat alert inside 6 hours', st.get('streak') == 5 and 'X_WALL_ALERT' not in genv, (st, genv))
rc, genv, out, st = streak(None)
check('a run with no X request (skipped/paused/no queries) leaves the streak alone', st.get('streak') == 5 and 'X_WALL_ALERT' not in genv, (st, genv))
rc, genv, out, st = streak([{'script': 'x_feed', 'attempted': 4, 'ok': 0, 'codes': ['402', '402', '429', '402']}])
check('a run with other failures mixed in leaves the streak alone', st.get('streak') == 5, st)
rc, genv, out, st = streak(den('403'))
rc, genv, out, st = streak(den('401'))
check('403 and 401 (every request denied) count as walled runs', st.get('streak') == 7, st)
state = json.load(open(STATE)) if os.path.exists(STATE) else {}
state['last_alert_at'] = (datetime.datetime.now(UTC) - datetime.timedelta(hours=7)).isoformat(timespec='seconds')
json.dump(state, open(STATE, 'w'))
rc, genv, out, st = streak(den())
check('while the wall lasts the alert repeats after 6 hours', st.get('streak') == 8 and 'X_WALL_ALERT=1' in genv, (st, genv))
rc, genv, out, st = streak(ok_run)
check('one successful request resets the streak', st.get('streak') == 0 and 'X_WALL_ALERT' not in genv, (st, genv))
check('recovery is logged', 'cleared' in out.lower(), out[-300:])
for i in (1, 2, 3):
    rc, genv, out, st = streak(den())
check('after recovery a new wall needs 4 runs again', st.get('streak') == 3 and 'X_WALL_ALERT' not in genv, (st, genv))
rc, genv, out, st = streak(den())
check('... and alerts on the 4th', 'X_WALL_ALERT=1' in genv, genv)
with open(STATE, 'w') as f:
    f.write('{not json')
rc, genv, out, st = streak(den())
check('an unreadable state file restarts the count instead of crashing', rc == 0 and st.get('streak') == 1, (rc, st, out[-300:]))

# the alert machinery never breaks the chain, and never fails quietly
bad = x_fake.scratch(); scratch_dirs.append(bad)
rc, out, calls = x_fake.run(bad, 'x_feed', plan={'default': {'posts': 10}}, env={'X_RUN_OUTCOME': os.path.join(bad, 'no-such-dir', 'o.jsonl')})
check('an unwritable outcome file never breaks the pull itself', rc == 0 and len(calls) == 4, (rc, len(calls), out[-300:]))
shutil.rmtree(os.path.join(bad, 'slates'))
open(os.path.join(bad, 'slates'), 'w').close()  # the state file cannot be written
genv = os.path.join(bad, 'github_env'); open(genv, 'w').close()
env = {k: v for k, v in os.environ.items() if not k.startswith('X_')}
env.update({'GITHUB_ENV': genv, 'X_RUN_OUTCOME': os.path.join(bad, 'none.jsonl')})
r = subprocess.run([sys.executable, os.path.join(HERE, 'x_wall.py'), 'streak'], cwd=bad, env=env, capture_output=True, text=True, timeout=60)
check('a broken streak step does not fail its step (news and the commits still run) ...', r.returncode == 0, (r.returncode, (r.stdout + r.stderr)[-300:]))
check('... and raises the end-of-run alert instead of failing quietly', 'X_WALL_ALERT=1' in open(genv).read() and 'streak step error' in open(genv).read(), open(genv).read())

# 3. end to end: four walled runs of the real scripts -> the fourth alerts; nothing billed ------------
e2e = x_fake.scratch(headlines=20); scratch_dirs.append(e2e)
ledger0 = x_fake.ledger_rows(e2e)
alerts = []
for i in range(4):
    ocp = os.path.join(e2e, f'outcome{i}.jsonl')
    x_fake.run(e2e, 'x_feed', plan=WALL, env={'X_RUN_OUTCOME': ocp})
    x_fake.run(e2e, 'news_social', plan=WALL, env={'X_RUN_OUTCOME': ocp})
    genv = os.path.join(e2e, f'genv{i}'); open(genv, 'w').close()
    env = {k: v for k, v in os.environ.items() if not k.startswith('X_')}
    env.update({'GITHUB_ENV': genv, 'X_RUN_OUTCOME': ocp})
    subprocess.run([sys.executable, os.path.join(HERE, 'x_wall.py'), 'streak'], cwd=e2e, env=env, capture_output=True, text=True, timeout=60)
    alerts.append('X_WALL_ALERT=1' in open(genv).read())
check('end to end: runs 1-3 stay green, run 4 alerts', alerts == [False, False, False, True], alerts)
check('end to end: denied requests are not billed to the ledger', x_fake.ledger_rows(e2e) == ledger0)

# 4. workflow wiring ------------------------------------------------------------------------------
wf = yaml.safe_load(open(os.path.join(ROOT, '.github', 'workflows', 'x_feed.yml')))
steps = wf['jobs']['feed'].get('steps') or []
runs = lambda s: str(s.get('run') or '')
named = lambda frag: next((i for i, s in enumerate(steps) if frag in runs(s) or frag in str(s.get('name') or '')), -1)
i_bridge, i_x, i_ns = named('bridge_worker_news.py'), named('scripts/x_feed.py'), named('scripts/news_social.py')
i_streak, i_pub = named('scripts/x_wall.py streak'), named('publish X feed')
i_commit, i_safety = named('commit feed + burn ledger'), named('bridge safety commit')
OC = '${{ runner.temp }}/x_run_outcome.jsonl'
check('both pulls and the streak step share one outcome file', i_streak >= 0 and all(
    (steps[i].get('env') or {}).get('X_RUN_OUTCOME') == OC for i in (i_x, i_ns, i_streak)), [(steps[i].get('env') or {}).get('X_RUN_OUTCOME') for i in (i_x, i_ns, i_streak)])
check('streak step runs after both pulls, before the ingest publish', 0 <= i_ns < i_streak < i_pub, (i_ns, i_streak, i_pub))
check('streak step runs on every due pull run, even after a failed pull',
      i_streak >= 0 and steps[i_streak].get('if') == "${{ !cancelled() && env.SKIP_X_PULL != '1' && !inputs.verify_only }}",
      steps[i_streak].get('if') if i_streak >= 0 else None)
last = steps[-1]
check('the alert is the last step of the run', "env.X_WALL_ALERT == '1'" in str(last.get('if') or '') and '!cancelled()' in str(last.get('if') or ''), last.get('if'))
check('the alert step fails the run', 'exit 1' in runs(last), runs(last))
check('news bridge is still the first work step, unconditional', i_bridge == 2 and 'if' not in steps[i_bridge], i_bridge)
check('feed commit and news safety commit both run before the alert', 0 <= i_commit < len(steps) - 1 and 0 <= i_safety < len(steps) - 1, (i_commit, i_safety, len(steps)))
cr = runs(steps[i_commit]) if i_commit >= 0 else ''
guarded = [l for l in cr.splitlines() if 'x_wall_state.json' in l]
check('the feed commit adds the wall state with its own guarded add (a missing file never drops the feed commit)',
      len(guarded) == 1 and 'exit 0' not in guarded[0] and 'if [ -f slates/x_wall_state.json ]' in guarded[0], guarded)

# 5. the alert step itself --------------------------------------------------------------------------
# executed only when the last step IS the alert step (never runs another step's script by mistake)
if "env.X_WALL_ALERT == '1'" in str(last.get('if') or ''):
    env = {k: v for k, v in os.environ.items() if not k.startswith('X_')}
    env['X_WALL_MSG'] = 'X API denied every request (HTTP 402) on 4 due runs in a row'
    r = subprocess.run(['bash', '-e', '-c', runs(last)], env=env, capture_output=True, text=True, timeout=30)
    check('alert step exits non-zero and prints the message', r.returncode == 1 and 'HTTP 402' in r.stdout, (r.returncode, r.stdout[-300:]))
else:
    check('alert step exits non-zero and prints the message', False, 'no alert step to run')

for p in scratch_dirs:
    shutil.rmtree(p, ignore_errors=True)
print('x wall alert: ' + ('OK' if not failures else f'{len(failures)} FAIL'))
sys.exit(1 if failures else 0)
