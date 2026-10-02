#!/usr/bin/env python3
"""incident-hook cannot feed itself through Pages, and never silently drops a note (ci review, loop).

incident.yml listens to pages-build-deployment, and every incident commit starts a Pages build
(Pages run 36962994684 was started by the incident-hook commit for nfl-scores-confirm run
36962967323). While Pages deploys fail, each failure would commit a note that starts the next
failing build. Now:
 - a failed Pages build whose head commit is an incident-hook or failure-watchdog commit is not
   captured (every other failure still is, an incident-hook commit's failure in any other
   workflow included). The guard knows a Pages run by its path, dynamic/pages/pages-build-deployment,
   or by either name: the workflow is "pages-build-deployment", but every run of it - the
   workflow_run.name the event carries - is "pages build and deployment" (run 36962994684 itself),
   so a guard on the workflow name alone never fired;
 - no capture is replaced by a later run: the concurrency group sits on the capture job, keyed
   by the failed run's id (a workflow-level group let a success-triggered run replace a pending
   failure capture), nothing cancelled;
 - the note's push retries with a rebase onto main, and fails loud when it cannot land (was
   `git push || true`, which dropped a racing note without a trace).
Runs the workflow's own step scripts in scratch repos, offline.
Run: python3 scripts/test_incident_hook.py   (exit 1 on any failure)
"""
import os, shutil, subprocess, sys, tempfile
try:
    import yaml
except ImportError:
    sys.exit('pyyaml required')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = yaml.safe_load(open(os.path.join(ROOT, '.github', 'workflows', 'incident.yml')))

failures = []
def check(label, ok, detail=''):
    if not ok:
        failures.append(label + (': ' + str(detail)[:400] if detail != '' else ''))
    print(f"{'OK  ' if ok else 'FAIL'} {label}" + ('' if ok or detail == '' else f'  [{str(detail)[:400]}]'))

job = (WF.get('jobs') or {}).get('capture') or {}
steps = job.get('steps') or []
guard = next((s for s in steps if s.get('id') == 'guard'), None)
commit = next((s for s in steps if 'git commit' in str(s.get('run') or '')), None)

# 1. the loop guard
check('capture runs on a failed run only', job.get('if') == "${{ github.event.workflow_run.conclusion == 'failure' }}", job.get('if'))
check('a loop-guard step runs first', bool(steps) and guard is steps[0], [s.get('name') for s in steps[:2]])
genv = (guard or {}).get('env') or {}
check('the guard reads the run name, its workflow path and its head commit author through env',
      genv.get('RUN_NAME') == '${{ github.event.workflow_run.name }}'
      and genv.get('RUN_PATH') == '${{ github.event.workflow_run.path }}'
      and genv.get('HEAD_AUTHOR') == '${{ github.event.workflow_run.head_commit.author.name }}', genv)
gated = [s.get('name') or s.get('uses') for s in steps[1:] if s.get('if') != "steps.guard.outputs.capture == 'true'"]
check('every later step runs only when the guard says capture', bool(steps[1:]) and gated == [], gated)

roots = []
def run_guard(run_name, author, path=''):
    root = tempfile.mkdtemp(prefix='rp-incident-guard-')
    roots.append(root)
    out = os.path.join(root, 'out')
    open(out, 'w').close()
    env = {'PATH': os.environ.get('PATH', ''), 'GITHUB_OUTPUT': out, 'RUN_NAME': run_name, 'RUN_PATH': path, 'HEAD_AUTHOR': author}
    r = subprocess.run(['bash', '-e', '-c', str((guard or {}).get('run') or 'exit 9')], env=env, capture_output=True, text=True, timeout=30)
    return r.returncode, open(out).read().splitlines()

PAGES_RUN, PAGES_PATH = 'pages build and deployment', 'dynamic/pages/pages-build-deployment'  # as run 36962994684 carries them
for run_name, author, path, want in (
        # a real Pages run: its name and its path, as the workflow_run event carries them
        (PAGES_RUN, 'incident-hook', PAGES_PATH, 'false'),
        (PAGES_RUN, 'failure-watchdog', PAGES_PATH, 'false'),
        (PAGES_RUN, 'RixPicks Bot', PAGES_PATH, 'true'),
        (PAGES_RUN, '', PAGES_PATH, 'true'),
        (PAGES_RUN, 'incident-hook2', PAGES_PATH, 'true'),
        # either alone still marks a Pages run: the run name with no path, the path under another name
        (PAGES_RUN, 'incident-hook', '', 'false'),
        ('pages-build-deployment', 'failure-watchdog', PAGES_PATH, 'false'),
        ('Pages build', 'incident-hook', PAGES_PATH, 'false'),
        # the workflow's own name, as the trigger list spells it
        ('pages-build-deployment', 'incident-hook', '', 'false'),
        ('pages-build-deployment', 'failure-watchdog', '', 'false'),
        ('pages-build-deployment', 'RixPicks Bot', '', 'true'),
        ('pages-build-deployment', '', '', 'true'),
        ('pages-build-deployment', 'incident-hook2', '', 'true'),
        # every other workflow is captured, an incident-hook or watchdog commit's failure included
        ('odds-refresh', 'incident-hook', '.github/workflows/odds_refresh.yml', 'true'),
        ('record-final', 'failure-watchdog', '.github/workflows/record_final.yml', 'true'),
        ('x-feed', 'incident-hook', '.github/workflows/x_feed.yml', 'true')):
    rc, lines = run_guard(run_name, author, path)
    check(f'guard: failed {run_name!r} ({path or "no path"}) at a commit by {author or "(none)"!r} -> capture={want}',
          rc == 0 and lines == ['capture=' + want], (rc, lines))

# 2. no capture is replaced: the group sits on the capture job (a success-triggered run, whose job
#    is skipped, never enters it), keyed by the failed run id, nothing cancelled
#    (scripts/test_failure_capture_concurrency.py checks failure-watchdog too)
conc = job.get('concurrency') or {}
check('incident.yml: no workflow-level group; the capture job\'s group is keyed by the failed run id, nothing cancelled',
      'concurrency' not in WF and isinstance(conc, dict) and str(conc.get('group', '')).startswith('incident-hook')
      and 'github.event.workflow_run.id' in str(conc.get('group', '')) and conc.get('cancel-in-progress') is False,
      (WF.get('concurrency'), conc))

# 3. the note's push: retry with a rebase onto main, loud when it cannot land
crun = str((commit or {}).get('run') or '')
check('the commit step takes the run name and id through env (no expression spliced into the script)',
      '${{' not in crun and ((commit or {}).get('env') or {}).get('RUN_ID') == '${{ github.event.workflow_run.id }}', crun[:200])
push_lines = [l.split('#', 1)[0] for l in crun.splitlines() if 'git push' in l.split('#', 1)[0]]
check('no push failure is swallowed (no `git push ... || ...`)', bool(push_lines) and not any('||' in l for l in push_lines), push_lines)

def git(cwd, *a):
    return subprocess.run(['git', *a], cwd=cwd, capture_output=True, text=True)

def push_case(race=False, reject=False):
    root = tempfile.mkdtemp(prefix='rp-incident-push-')
    roots.append(root)
    origin, work, other = (os.path.join(root, x) for x in ('origin.git', 'work', 'other'))
    genv = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    genv.update(HOME=root, GIT_CONFIG_NOSYSTEM='1')
    def g(cwd, *a):
        return subprocess.run(['git', *a], cwd=cwd, capture_output=True, text=True, env=genv)
    g(root, 'init', '-q', '--bare', '-b', 'main', origin)
    g(root, 'init', '-q', '-b', 'main', work)
    os.makedirs(os.path.join(work, 'incidents'))
    open(os.path.join(work, 'index.html'), 'w').write('<html>site</html>')
    g(work, 'add', '-A'); g(work, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'seed')
    g(work, 'remote', 'add', 'origin', origin); g(work, 'push', '-q', 'origin', 'main'); g(work, 'branch', '-q', '-u', 'origin/main')
    if race:  # a bot lands a commit on main after this run's checkout
        g(root, 'clone', '-q', origin, other)
        open(os.path.join(other, 'odds_moves.jsonl'), 'w').write('{"tick": 1}\n')
        g(other, 'add', '-A'); g(other, '-c', 'user.name=RixPicks Bot', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'odds refresh 10:15 PT (call 9 today)'); g(other, 'push', '-q', 'origin', 'main')
    if reject:
        hook = os.path.join(origin, 'hooks', 'pre-receive')
        open(hook, 'w').write('#!/bin/sh\necho "rejected for the fixture" >&2\nexit 1\n')
        os.chmod(hook, 0o755)
    open(os.path.join(work, 'incidents', '36962994684.md'), 'w').write('# FAILURE x-feed run 36962994684\n')
    env = dict(genv, RUN_NAME='x-feed', RUN_ID='36962994684')
    # render the expressions the way the runner would, so an older step that splices them still runs
    script = (crun or 'exit 9').replace('${{ github.event.workflow_run.name }}', 'x-feed').replace('${{ github.event.workflow_run.id }}', '36962994684')
    r = subprocess.run(['bash', '-e', '-c', script], cwd=work, env=env, capture_output=True, text=True, timeout=120)
    files = g(root, '--git-dir', origin, 'ls-tree', '-r', '--name-only', 'main').stdout.split()
    log = g(root, '--git-dir', origin, 'log', '--format=%an|%s', 'main').stdout.splitlines()
    return r.returncode, files, log, r.stdout + r.stderr

rc, files, log, out = push_case()
check('push: the note lands on main', rc == 0 and 'incidents/36962994684.md' in files, (rc, files, out[-300:]))
rc, files, log, out = push_case(race=True)
check('push race: main moved after checkout - the note still lands (rebased onto main)',
      rc == 0 and 'incidents/36962994684.md' in files, (rc, files, out[-400:]))
check('push race: the other commit is kept', 'odds_moves.jsonl' in files and any(l.startswith('RixPicks Bot|odds refresh') for l in log), (files, log))
check('push race: the note is committed as incident-hook with the run in its message',
      any(l == 'incident-hook|incident: x-feed run 36962994684 failure captured' for l in log), log)
rc, files, log, out = push_case(reject=True)
check('push rejected every time: the step fails loud (non-zero exit), never a silent drop', rc != 0 and 'incidents/36962994684.md' not in files, (rc, out[-300:]))

for r in roots:
    shutil.rmtree(r, ignore_errors=True)
if failures:
    print(f'INCIDENT HOOK: {len(failures)} FAILURES')
    sys.exit(1)
print('INCIDENT HOOK: ALL PASS')
