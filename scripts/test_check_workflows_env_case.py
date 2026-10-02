#!/usr/bin/env python3
"""Fixture for scripts/check_workflows.py: an env map whose keys collide case-insensitively is
flagged before push. GitHub reads env names case-insensitively, so a map carrying both http_proxy
and HTTP_PROXY makes the whole workflow file invalid and the run never starts (tests.yml, Oct 2);
the file still parses as YAML, so a parse-only check passed it. Every env map is covered (workflow,
job, step, container, service), exact duplicates too (YAML loaders keep only the last silently),
and distinct names or the same name in two different maps stay clean. The live workflows must pass.
Run: python3 scripts/test_check_workflows_env_case.py   (exit 1 on any failure; no side effects)"""
import os, shutil, subprocess, sys, tempfile
try:
    import yaml  # noqa: F401  check_workflows.py needs it
except ImportError:
    sys.exit('pyyaml required')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.path.join(ROOT, 'scripts', 'check_workflows.py')
failures = 0
def check(name, cond, detail=''):
    global failures
    print(('OK  ' if cond else 'FAIL'), name, '' if cond else detail)
    if not cond: failures += 1

def run(workflows):
    d = tempfile.mkdtemp(prefix='wfenv_')
    try:
        os.makedirs(os.path.join(d, '.github', 'workflows'))
        for name, text in workflows.items():
            open(os.path.join(d, '.github', 'workflows', name), 'w').write(text)
        p = subprocess.run([sys.executable, CHECK], cwd=d, capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr
    finally:
        shutil.rmtree(d, ignore_errors=True)

HEAD = 'name: t\non:\n  workflow_dispatch:\n'
STEP_PAIR = HEAD + '''jobs:
  fixtures:
    runs-on: ubuntu-latest
    steps:
      - name: "blocked network"
        env:
          http_proxy: 'http://127.0.0.1:9'
          HTTP_PROXY: 'http://127.0.0.1:9'
        run: echo ok
'''
rc, out = run({'step.yml': STEP_PAIR})
check('step env http_proxy + HTTP_PROXY is flagged (exit 1)', rc == 1, out)
check('the report names the file, the map and both keys',
      'step.yml' in out and 'jobs.fixtures.steps[0].env' in out and 'http_proxy' in out and 'HTTP_PROXY' in out, out)
check('the report gives the line of the colliding key', 'step.yml:11:' in out, out)

JOB = HEAD + '''jobs:
  a:
    runs-on: ubuntu-latest
    env:
      Rix_Mode: one
      RIX_MODE: two
    steps:
      - run: echo ok
'''
rc, out = run({'job.yml': JOB})
check('job-level env collision is flagged', rc == 1 and 'jobs.a.env' in out and 'RIX_MODE' in out, out)

TOP = HEAD + '''env:
  no_proxy: ''
  NO_PROXY: ''
jobs:
  a:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
'''
rc, out = run({'top.yml': TOP})
check('workflow-level env collision is flagged', rc == 1 and 'top.yml' in out and 'no_proxy' in out.lower(), out)

NESTED = HEAD + '''jobs:
  a:
    runs-on: ubuntu-latest
    container:
      image: python:3.12
      env:
        Token_Path: /a
        token_path: /b
    services:
      db:
        image: postgres
        env:
          PGUSER: x
          pguser: y
    steps:
      - run: echo ok
'''
rc, out = run({'nested.yml': NESTED})
check('container env collision is flagged', rc == 1 and 'jobs.a.container.env' in out, out)
check('service env collision is flagged', 'jobs.a.services.db.env' in out, out)

DUP = HEAD + '''jobs:
  a:
    runs-on: ubuntu-latest
    steps:
      - env:
          HTTPS_PROXY: 'http://127.0.0.1:9'
          HTTPS_PROXY: 'http://127.0.0.1:9'
        run: echo ok
'''
rc, out = run({'dup.yml': DUP})
check('an exact duplicate env key is flagged (the loader would keep only the last)', rc == 1 and 'HTTPS_PROXY' in out, out)

CLEAN = HEAD + '''env:
  http_proxy: 'http://127.0.0.1:9'
jobs:
  a:
    runs-on: ubuntu-latest
    env:
      HTTP_PROXY: 'http://127.0.0.1:9'
      HTTPS_PROXY: 'http://127.0.0.1:9'
    steps:
      - name: "lowercase in env, uppercase exported (the tests.yml fix)"
        env:
          https_proxy: 'http://127.0.0.1:9'
          no_proxy: ''
        run: export HTTPS_PROXY="$https_proxy" NO_PROXY="$no_proxy"
      - env: ${{ fromJSON('{}') }}
        run: echo expression env is not a map
'''
rc, out = run({'clean.yml': CLEAN})
check('distinct names, the same name in different maps and an expression env all pass', rc == 0, out)

rc, out = run({'step.yml': STEP_PAIR, 'clean.yml': CLEAN})
check('only the colliding file is reported', rc == 1 and 'step.yml' in out and 'clean.yml:' not in out, out)

p = subprocess.run([sys.executable, CHECK], cwd=ROOT, capture_output=True, text=True)
check('the live workflows have no env collisions', p.returncode == 0, (p.stdout + p.stderr)[-400:])

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
