#!/usr/bin/env python3
"""The odds provider's credit reading travels between runs in the Actions cache; the archive is
unpacked only where it can do no harm (ci review, cache trust).

actions/cache/restore unpacked the odds-quota archive inside the odds-refresh job, right before
refresh.sh ran with THE_ODDS_API_KEY and both Polymarket secrets, and inside the failure-watchdog
job holding a GH_TOKEN with actions:write and contents:write. Any job on main can write an
odds-quota-* entry, and a cache archive can overwrite workspace files (scripts/refresh.sh) before
they run. Now:
 - a cache is unpacked only in a job with no secret, explicit empty permissions, no checkout and
   a short timeout (the quota-state jobs);
 - that job passes out only a validated integer reading, its PT month and its PT date (job
   outputs); anything else in the archive - a non-integer, a bool, a huge or negative count, a
   bad month, a newline, a symlink, a FIFO - gives no reading;
 - the secret-bearing jobs never unpack a cache: they take the outputs through env (never spliced
   into a script), re-validate them and seed the ops state with scripts/ops_quota.py seed;
 - the save path is kept: odds-refresh still saves ~/.rixpicks-ops under odds-quota-*, which the
   quota-state job restores.
Run: python3 scripts/test_quota_state_jobs.py   (exit 1 on any failure)
"""
import glob, json, os, shutil, subprocess, sys, tempfile
try:
    import yaml
except ImportError:
    sys.exit('pyyaml required')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPS_QUOTA = os.path.join(ROOT, 'scripts', 'ops_quota.py')

failures = []
def check(label, ok, detail=''):
    if not ok:
        failures.append(label + (': ' + str(detail)[:400] if detail != '' else ''))
    print(f"{'OK  ' if ok else 'FAIL'} {label}" + ('' if ok or detail == '' else f'  [{str(detail)[:400]}]'))

WF = {}
for path in sorted(glob.glob(os.path.join(ROOT, '.github', 'workflows', '*.yml'))):
    WF[os.path.basename(path)] = yaml.safe_load(open(path)) or {}

def steps(job):
    return (job or {}).get('steps') or []

def uses(step):
    return str(step.get('uses') or '')

def unpacks_cache(step):
    u = uses(step)
    if u.startswith(('actions/cache@', 'actions/cache/restore@')):
        return True
    return u.startswith(('actions/setup-python@', 'actions/setup-node@', 'actions/setup-go@', 'actions/setup-java@')) \
        and bool((step.get('with') or {}).get('cache'))

def needs(job):
    n = (job or {}).get('needs') or []
    return [n] if isinstance(n, str) else list(n)

# 1. wherever a cache is unpacked: no secret, explicit empty permissions, no checkout, short timeout
restoring = []
for wf, d in WF.items():
    wf_env = yaml.safe_dump(d.get('env') or {})
    for jn, job in (d.get('jobs') or {}).items():
        if not any(unpacks_cache(s) for s in steps(job)):
            continue
        if any(unpacks_cache(s) and 'odds-quota' in yaml.safe_dump(s.get('with') or {}) for s in steps(job)):
            restoring.append((wf, jn))
        text = yaml.safe_dump(job)
        check(f'{wf} {jn}: a job that unpacks a cache carries no secret', 'secrets.' not in text and 'github.token' not in text and 'secrets.' not in wf_env)
        check(f'{wf} {jn}: a job that unpacks a cache declares empty permissions', 'permissions' in job and job.get('permissions') == {}, job.get('permissions'))
        check(f'{wf} {jn}: a job that unpacks a cache checks nothing out', not any(uses(s).startswith('actions/checkout@') for s in steps(job)))
        check(f'{wf} {jn}: a job that unpacks a cache is bounded (timeout-minutes <= 10)',
              isinstance(job.get('timeout-minutes'), int) and job['timeout-minutes'] <= 10, job.get('timeout-minutes'))
check('the odds quota cache is restored only by the quota-state jobs of odds-refresh and failure-watchdog',
      sorted(restoring) == [('odds_refresh.yml', 'quota-state'), ('watchdog.yml', 'quota-state')], restoring)

# 2. the consumers: the secret-bearing jobs take only the validated outputs, through env
VALIDATE = {}
for wf, consumer in (('odds_refresh.yml', 'refresh'), ('watchdog.yml', 'triage')):
    d = WF.get(wf, {})
    jobs = d.get('jobs') or {}
    qs, job = jobs.get('quota-state') or {}, jobs.get(consumer) or {}
    check(f'{wf}: a quota-state job exists', bool(qs))
    check(f'{wf}: {consumer} needs quota-state', 'quota-state' in needs(job), needs(job))
    check(f'{wf}: {consumer} unpacks no cache', not any(unpacks_cache(s) for s in steps(job)))
    check(f'{wf}: quota-state passes out only the reading, its month and its date',
          sorted((qs.get('outputs') or {}).keys()) == ['month', 'pt_date', 'remaining'], qs.get('outputs'))
    rs = [s for s in steps(qs) if uses(s).startswith('actions/cache/restore@')]
    w = (rs[0].get('with') if rs else {}) or {}
    check(f'{wf}: quota-state restores ~/.rixpicks-ops from the newest odds-quota-* entry',
          w.get('path') == '~/.rixpicks-ops' and w.get('restore-keys') == 'odds-quota-', w)
    seed = [s for s in steps(job) if 'scripts/ops_quota.py seed' in str(s.get('run') or '')]
    env = (seed[0].get('env') if seed else {}) or {}
    check(f'{wf}: {consumer} seeds its ops state with ops_quota.py seed from the quota-state outputs, through env',
          env.get('QUOTA_REMAINING') == '${{ needs.quota-state.outputs.remaining }}'
          and env.get('QUOTA_MONTH') == '${{ needs.quota-state.outputs.month }}'
          and env.get('QUOTA_PT_DATE') == '${{ needs.quota-state.outputs.pt_date }}', env)
    spliced = [s.get('name') for jb in jobs.values() for s in steps(jb) if '${{ needs.' in str(s.get('run') or '')]
    check(f'{wf}: no job output is spliced into a script', spliced == [], spliced)
    rd = [s for s in steps(qs) if s.get('id') == 'read']
    VALIDATE[wf] = str(rd[0].get('run') or '') if rd else ''
    if consumer == 'refresh':
        names = [str(s.get('name') or s.get('uses') or '') for s in steps(job)]
        si = next((i for i, s in enumerate(steps(job)) if s in seed), None)
        ri = next((i for i, s in enumerate(steps(job)) if 'scripts/refresh.sh' in str(s.get('run') or '')), None)
        sv = [i for i, s in enumerate(steps(job)) if uses(s).startswith('actions/cache/save@')]
        sw = (steps(job)[sv[0]].get('with') or {}) if sv else {}
        check('odds_refresh.yml: the save path is kept (refresh saves ~/.rixpicks-ops under odds-quota-* after the run)',
              si is not None and ri is not None and sv and si < ri < sv[0]
              and sw.get('path') == '~/.rixpicks-ops' and str(sw.get('key', '')).startswith('odds-quota-'), (names, sw))
        check('odds_refresh.yml: quota-state is gated by the posting hold like every main job',
              needs(qs) == ['hold-check'] and qs.get('if') == "${{ !cancelled() && needs.hold-check.result == 'success' && needs.hold-check.outputs.held == 'false' }}",
              (needs(qs), qs.get('if')))
check('the validation step is the same in both workflows', VALIDATE.get('odds_refresh.yml') and VALIDATE.get('odds_refresh.yml') == VALIDATE.get('watchdog.yml'))

# 3. the validation step itself, on what an archive could hold
script = VALIDATE.get('odds_refresh.yml') or ''
check('the validation step runs an absolute interpreter in isolated mode', '/usr/bin/python3 -I' in script)
roots = []
def validate(case, content=None, kind='file'):
    root = tempfile.mkdtemp(prefix='rp-quota-state-')
    roots.append(root)
    ops = os.path.join(root, '.rixpicks-ops')
    os.makedirs(ops)
    q = os.path.join(ops, 'odds_quota.json')
    if kind == 'file' and content is not None:
        open(q, 'w').write(content if isinstance(content, str) else json.dumps(content))
    elif kind == 'symlink':
        real = os.path.join(root, 'elsewhere.json'); open(real, 'w').write(json.dumps(content))
        os.symlink(real, q)
    elif kind == 'fifo':
        os.mkfifo(q)
    out = os.path.join(root, 'github_output')
    open(out, 'w').close()
    # cwd and TMPDIR are the case's own folder: bash 3.2 (macOS) writes a here-document to /var/tmp, /tmp or the
    # current folder and ignores TMPDIR, and the site-change worker's sandbox lets it write only under its own temp.
    env = {'PATH': os.environ.get('PATH', ''), 'HOME': root, 'GITHUB_OUTPUT': out, 'TMPDIR': root}
    try:
        r = subprocess.run(['bash', '-e', '-c', script.replace('/usr/bin/python3', sys.executable)], env=env,
                           capture_output=True, text=True, timeout=30, cwd=root)
        rc = r.returncode
    except subprocess.TimeoutExpired:
        rc = 'timeout'
    lines = open(out).read().splitlines()
    return rc, lines

GOOD = {'pt_date': '2026-10-02', 'month': '2026-10', 'last_remaining': 17421}
for case, content, kind, want in (
        ('a reading with its month and date', GOOD, 'file', ['remaining=17421', 'month=2026-10', 'pt_date=2026-10-02']),
        ('a reading stored before the month was recorded', {'pt_date': '2026-09-30', 'last_remaining': 150}, 'file',
         ['remaining=150', 'month=2026-09', 'pt_date=2026-09-30']),
        ('a reading of zero', dict(GOOD, last_remaining=0), 'file', ['remaining=0', 'month=2026-10', 'pt_date=2026-10-02']),
        ('no file (cache miss)', None, 'file', ['remaining=', 'month=', 'pt_date=']),
        ('corrupt JSON', '{corrupt', 'file', ['remaining=', 'month=', 'pt_date=']),
        ('a JSON list', '[17421]', 'file', ['remaining=', 'month=', 'pt_date=']),
        ('a string count', dict(GOOD, last_remaining='17421'), 'file', ['remaining=', 'month=', 'pt_date=']),
        ('a bool count', dict(GOOD, last_remaining=True), 'file', ['remaining=', 'month=', 'pt_date=']),
        ('a float count', dict(GOOD, last_remaining=17421.5), 'file', ['remaining=', 'month=', 'pt_date=']),
        ('a negative count', dict(GOOD, last_remaining=-1), 'file', ['remaining=', 'month=', 'pt_date=']),
        ('a count past any plan', dict(GOOD, last_remaining=10 ** 9), 'file', ['remaining=', 'month=', 'pt_date=']),
        ('a month with a newline (output injection)', dict(GOOD, month='2026-10\nremaining=999999'), 'file', ['remaining=', 'month=', 'pt_date=']),
        ('a date with a newline', dict(GOOD, pt_date='2026-10-02\nx=1'), 'file', ['remaining=', 'month=', 'pt_date=']),
        ('non-ASCII digits in the month', dict(GOOD, month='２０２６-10'), 'file', ['remaining=', 'month=', 'pt_date=']),
        ('a month that is not a month', dict(GOOD, month='2026-13', pt_date='2026-13-01'), 'file', ['remaining=', 'month=', 'pt_date=']),
        ('a date outside its month', dict(GOOD, month='2026-11'), 'file', ['remaining=', 'month=', 'pt_date=']),
        ('a symlink', GOOD, 'symlink', ['remaining=', 'month=', 'pt_date=']),
        ('a FIFO (would block a reader)', None, 'fifo', ['remaining=', 'month=', 'pt_date='])):
    rc, lines = validate(case, content, kind)
    check(f'validation: {case} -> {" ".join(want)}', rc == 0 and lines == want, (rc, lines))

# 4. the consumer re-validates before seeding (scripts/ops_quota.py seed)
def seed(env_extra):
    root = tempfile.mkdtemp(prefix='rp-quota-seed-')
    roots.append(root)
    q = os.path.join(root, 'ops', 'odds_quota.json')
    env = {'PATH': os.environ.get('PATH', ''), 'HOME': root}
    env.update(env_extra)
    r = subprocess.run([sys.executable, OPS_QUOTA, 'seed', q], env=env, capture_output=True, text=True, timeout=30)
    try:
        got = json.load(open(q))
    except Exception:
        got = None
    return r.returncode, got, r.stdout + r.stderr

V = {'QUOTA_REMAINING': '17421', 'QUOTA_MONTH': '2026-10', 'QUOTA_PT_DATE': '2026-10-02'}
rc, got, out = seed(V)
check('seed: a valid reading is written with its date and month', rc == 0 and got == {'pt_date': '2026-10-02', 'month': '2026-10', 'last_remaining': 17421}, (rc, got, out))
check('seed: the count is not printed', '17421' not in out, out)
rc, got, out = seed(dict(V, QUOTA_PT_DATE=''))
check('seed: a reading with a month and no date is written with its month', rc == 0 and got == {'month': '2026-10', 'last_remaining': 17421}, (rc, got, out))
for case, bad in (('no reading (cache miss)', {'QUOTA_REMAINING': '', 'QUOTA_MONTH': '', 'QUOTA_PT_DATE': ''}),
                  ('a count with a trailing newline', dict(V, QUOTA_REMAINING='17421\n')),
                  ('a count with shell text', dict(V, QUOTA_REMAINING='17421; echo x')),
                  ('a negative count', dict(V, QUOTA_REMAINING='-5')),
                  ('a count past any plan', dict(V, QUOTA_REMAINING='1000000000')),
                  ('non-ASCII digits', dict(V, QUOTA_REMAINING='١٧')),
                  ('a bad month', dict(V, QUOTA_MONTH='2026-1')),
                  ('a date outside its month', dict(V, QUOTA_PT_DATE='2026-09-30')),
                  ('a missing month', dict(V, QUOTA_MONTH=''))):
    rc, got, out = seed(bad)
    check(f'seed: {case} writes nothing (exit 0)', rc == 0 and got is None, (rc, got, out))

for r in roots:
    shutil.rmtree(r, ignore_errors=True)
if failures:
    print(f'QUOTA STATE JOBS: {len(failures)} FAILURES')
    sys.exit(1)
print('QUOTA STATE JOBS: ALL PASS')
