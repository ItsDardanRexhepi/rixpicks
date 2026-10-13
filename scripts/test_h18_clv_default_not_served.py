#!/usr/bin/env python3
"""H-18: scripts/clv_report.py writes an internal ledger (per-pick locked price, de-vigged close and CLV) that
no page renders. The site repository is public and Pages serves every tracked file, so the ledger's DEFAULT
place is outside the repository: $RIXPICKS_CLV_LEDGER when set, else ~/.rixpicks/clv/clv_ledger.json. --out
still writes anywhere it is told to. slates/clv_ledger.json, the old default, is git-ignored so a bulk add can
never publish an old copy.
Runs the real script on a scratch repository with HOME pointed at a scratch folder. Offline, no side effects.
Run: python3 scripts/test_h18_clv_default_not_served.py"""
import json, os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, 'scripts', 'clv_report.py')
failures = 0

def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or detail == '' else '  [' + str(detail)[-400:] + ']'))
    if not ok:
        failures += 1

tmp = tempfile.mkdtemp(prefix='h18_clv_')
try:
    repo, home = os.path.join(tmp, 'repo'), os.path.join(tmp, 'home')
    os.makedirs(os.path.join(repo, 'slates')); os.makedirs(home)
    env = dict(os.environ, HOME=home, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
    env.pop('RIXPICKS_CLV_LEDGER', None)
    for rel, obj in (('history.json', {'days': []}), ('record_request.json', {'requests': []}), ('record_done.json', {})):
        json.dump(obj, open(os.path.join(repo, rel), 'w'))
    for a in (['init', '-q'], ['add', '-A'], ['-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'base']):
        subprocess.run(['git', *a], cwd=repo, env=env, check=True, capture_output=True)

    r = subprocess.run([sys.executable, SCRIPT, '--root', repo], cwd=repo, env=env, capture_output=True, text=True)
    want = os.path.join(home, '.rixpicks', 'clv', 'clv_ledger.json')
    check('H-18 a default run exits 0', r.returncode == 0, r.stdout + r.stderr)
    check('H-18 a default run writes nothing under the served slates/ folder', not os.path.exists(os.path.join(repo, 'slates', 'clv_ledger.json')))
    st = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=repo, env=env, capture_output=True, text=True).stdout.strip()
    check('H-18 a default run leaves the repository unchanged', st == '', st)
    check('H-18 the default ledger is ~/.rixpicks/clv/clv_ledger.json', os.path.exists(want), os.listdir(home))

    alt = os.path.join(tmp, 'alt', 'ledger.json')
    r = subprocess.run([sys.executable, SCRIPT, '--root', repo], cwd=repo, env=dict(env, RIXPICKS_CLV_LEDGER=alt), capture_output=True, text=True)
    check('H-18 RIXPICKS_CLV_LEDGER moves the default', r.returncode == 0 and os.path.exists(alt), r.stdout + r.stderr)
    out = os.path.join(tmp, 'out.json')
    r = subprocess.run([sys.executable, SCRIPT, '--root', repo, '--out', out], cwd=repo, env=env, capture_output=True, text=True)
    check('H-18 --out still writes where it is told', r.returncode == 0 and os.path.exists(out), r.stdout + r.stderr)

    src = open(SCRIPT, encoding='utf-8').read()
    check('H-18 the script no longer names slates/clv_ledger.json as its default', 'default slates/clv_ledger.json' not in src and "'slates', 'clv_ledger.json'" not in src)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

ig = subprocess.run(['git', '-C', ROOT, 'check-ignore', '-q', 'slates/clv_ledger.json'])
check('H-18 slates/clv_ledger.json is git-ignored', ig.returncode == 0)

print('FAILURES: %d' % failures if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
