#!/usr/bin/env python3
"""X daily spend ceiling (x-spend safety, Oct 2). The X API is pay-per-use; the signed-off burn is
about $3/day (x_feed.yml cron note), but the committed burn ledger shows $3.25-$4.45 per 15-minute
cycle (19 requests, 525-765 posts) and nothing in code capped a day. Now:
 - X_DAILY_CAP_USD (repo variable) is the ceiling, $3.00 when unset or unreadable; the code only
   reads it, never raises it (a malformed value falls back to $3.00, never to more);
 - spend = the burn ledger's entries in the trailing 24 hours priced at the code's own rates
   ($0.033 a request + $0.005 a post), so the ceiling holds for any calendar day;
 - before each pull the worst case (every request returns max_results posts) is projected; a pull
   that would cross the ceiling is shrunk (fewer requests, then fewer posts) or skipped, with a log
   line saying why; x_feed.py and news_social.py share the one ledger, so together they stay under;
 - the workflow's spend gate syncs this checkout's ledger with main's newest one first (a run that
   checked out before the previous run published its ledger would not see that spend) and skips
   every paid step once not even the smallest request fits.
Every X call is a scripted fake (scripts/fixtures/x_fake.py); none can reach the network.
Run: python3 scripts/test_x_daily_cap.py   (exit 1 on any failure)
"""
import datetime, json, os, shutil, subprocess, sys, tempfile
try:
    import yaml
except ImportError:
    sys.exit('pyyaml required')

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, 'fixtures'))
sys.path.insert(0, HERE)
import x_fake  # noqa: E402

UTC = datetime.timezone.utc
failures = []
scratch_dirs = []


def check(label, ok, detail=''):
    if not ok:
        failures.append(label)
    print(f"{'OK  ' if ok else 'FAIL'} {label}" + ('' if ok or detail == '' else f'  [{str(detail)[:300]}]'))


def scen(ledger=(), script='x_feed', plan=None, env=None, headlines=8, games=4):
    d = x_fake.scratch(ledger=ledger, headlines=headlines, games=games)
    scratch_dirs.append(d)
    rc, out, calls = x_fake.run(d, script, plan=plan, env=env)
    return d, rc, out, calls


# 1. the ceiling's own arithmetic -----------------------------------------------------------------
try:
    import x_budget
except ImportError as e:
    x_budget = None
    check('scripts/x_budget.py exists (shared spend ceiling)', False, e)
if x_budget:
    for raw, want in [(None, 3000), ('', 3000), ('5', 5000), ('2.5', 2500), (' 4 ', 4000), ('$4', 4000),
                      ('0', 0), ('3.0009', 3000), ('abc', 3000), ('-1', 3000), ('nan', 3000), ('inf', 3000),
                      ('1e999', 3000)]:
        env = {} if raw is None else {'X_DAILY_CAP_USD': raw}
        got = x_budget.cap_mills(env)
        check(f'X_DAILY_CAP_USD={raw!r} -> ${want / 1000:.3f} ceiling', got == want, got)
    now = datetime.datetime.now(UTC)
    rows = [x_fake.ledger_row(1, 10, now), x_fake.ledger_row(23.9, 100, now), x_fake.ledger_row(25, 100, now),
            {'ts': 'not-a-time', 'endpoint': 'x', 'query': 'q', 'results': 0},
            {'ts': x_fake.iso(now - datetime.timedelta(hours=2)), 'endpoint': 'x', 'query': 'q', 'results': 'n/a'}]
    got = x_budget.spent_mills(rows, now)
    # 83 + 533 (inside 24h) + 0 (25h old) + 33 (undatable: counted) + 533 (unknown size: priced at 100 posts)
    check('24h spend uses the code rates, ages out >24h rows, fails closed on bad rows', got == 83 + 533 + 33 + 533, got)
    check('code rates are the ledger rates (0.033/request, 0.005/post)',
          (x_budget.COST_PER_REQUEST, x_budget.COST_PER_POST) == (0.033, 0.005))

# 2. x_feed.py: projection shrinks or skips before any request ---------------------------------------
d, rc, out, calls = scen(x_fake.rows_costing(2.80), 'x_feed', {'default': {'posts': 10}})
check('x_feed: $2.80 spent today, $3.00 default cap -> 4 planned requests shrink to 2', rc == 0 and len(calls) == 2, (rc, len(calls), out[-600:]))
check('x_feed: the shrink is logged with its reason', '4 -> 2' in out and 'daily cap' in out, out[-600:])
check('x_feed: 24h spend stays under $3.00 after the pull', x_fake.spend_24h(d) <= 3.0, x_fake.spend_24h(d))

d, rc, out, calls = scen(x_fake.rows_costing(2.95), 'x_feed', {'default': {'posts': 10}})
feed_after = json.load(open(os.path.join(d, 'slates', 'x_feed.json')))
check('x_feed: $2.95 spent -> $0.05 left < smallest request ($0.083) -> no request', rc == 0 and len(calls) == 0, (rc, len(calls), out[-600:]))
check('x_feed: the skip is logged with its reason', 'SKIPPED' in out and 'daily cap' in out, out[-600:])
check('x_feed: skipped pull leaves the feed untouched (prior stamp, prior items)',
      feed_after.get('generated_at') == '2026-10-01T01:02:02+00:00' and feed_after.get('items') == [],
      (feed_after.get('generated_at'), len(feed_after.get('items') or [])))

d, rc, out, calls = scen([x_fake.ledger_row(25, 100) for _ in range(20)], 'x_feed', {'default': {'posts': 10}})
check('x_feed: spend older than 24h does not count against today', rc == 0 and len(calls) == 4, (rc, len(calls)))

d = x_fake.scratch(ledger=x_fake.rows_costing(2.98)); scratch_dirs.append(d)
rc, out, calls = x_fake.run(d, 'x_feed', argv=('verify',), plan={'default': {'posts': 0}})
check('x_feed verify: $0.02 left < one request ($0.033) -> the token check is not billed', rc == 0 and len(calls) == 0, (rc, len(calls), out[-300:]))

# 3. news_social.py: 18 x 100-post requests can never run past the ceiling ----------------------------
d, rc, out, calls = scen([], 'news_social', {'default': {'posts': 100}}, headlines=20)
check('news_social: empty ledger, $3.00 cap, worst case $0.533/request -> 18 shrink to 5', rc == 0 and len(calls) == 5, (rc, len(calls), out[-600:]))
check('news_social: shrink logged', '18 -> 5' in out and 'daily cap' in out, out[-600:])
check('news_social: 24h spend <= $3.00', x_fake.spend_24h(d) <= 3.0, x_fake.spend_24h(d))

d, rc, out, calls = scen([], 'news_social', {'default': {'posts': 100}}, env={'X_DAILY_CAP_USD': '0.30'}, headlines=20)
mr = [int(c['params'].get('max_results', 0)) for c in calls]
check('news_social: $0.30 cap -> one request with fewer posts (max_results 53)', rc == 0 and mr == [53], (rc, mr, out[-600:]))
check('news_social: $0.30 cap respected', x_fake.spend_24h(d) <= 0.30, x_fake.spend_24h(d))

d, rc, out, calls = scen([], 'news_social', {'default': {'posts': 100}}, env={'X_DAILY_CAP_USD': '10'}, headlines=20)
check('news_social: the owner can raise the ceiling (X_DAILY_CAP_USD=10 -> all 18 fit)', rc == 0 and len(calls) == 18, (rc, len(calls)))

d, rc, out, calls = scen([], 'news_social', {'default': {'posts': 100}}, env={'X_DAILY_CAP_USD': 'lots'}, headlines=20)
check('news_social: an unreadable X_DAILY_CAP_USD means $3.00, not more', rc == 0 and len(calls) == 5, (rc, len(calls)))

d, rc, out, calls = scen(x_fake.rows_costing(2.95), 'news_social', {'default': {'posts': 100}}, headlines=20)
check('news_social: $0.05 left -> no request, feed preserved', rc == 0 and len(calls) == 0, (rc, len(calls), out[-400:]))

# 4. both pulls in one run share the ledger ------------------------------------------------------------
d = x_fake.scratch(headlines=20); scratch_dirs.append(d)
cap = {'X_DAILY_CAP_USD': '1.00'}
rc1, out1, c1 = x_fake.run(d, 'x_feed', plan={'default': {'posts': 10}}, env=cap)
rc2, out2, c2 = x_fake.run(d, 'news_social', plan={'default': {'posts': 100}}, env=cap)
check('one run (x_feed then news_social) stays under a $1.00 ceiling together',
      rc1 == 0 and rc2 == 0 and len(c1) == 4 and len(c2) == 1 and x_fake.spend_24h(d) <= 1.0,
      (rc1, rc2, len(c1), len(c2), x_fake.spend_24h(d)))

# 5. workflow wiring --------------------------------------------------------------------------------
wf_text = open(os.path.join(ROOT, '.github', 'workflows', 'x_feed.yml')).read()
wf = yaml.safe_load(wf_text)
job = wf['jobs']['feed']
steps = job.get('steps') or []
def idx(pred):
    for i, s in enumerate(steps):
        if pred(s):
            return i
    return -1
runs = lambda s: str(s.get('run') or '')
i_bridge = idx(lambda s: 'bridge_worker_news.py' in runs(s))
i_gate = idx(lambda s: 'scripts/x_budget.py gate' in runs(s))
i_floor = idx(lambda s: 'X pull due' in runs(s))
i_xpull = idx(lambda s: 'scripts/x_feed.py' in runs(s))
i_news = idx(lambda s: 'scripts/news_social.py' in runs(s))
check('job env carries the ceiling from the repo variable only',
      (job.get('env') or {}).get('X_DAILY_CAP_USD') == '${{ vars.X_DAILY_CAP_USD }}', job.get('env'))
wf_values = json.dumps(wf)  # parsed workflow: comments excluded
# two mentions = the job env key and its ${{ vars.X_DAILY_CAP_USD }} value; any other is an override
check('X_DAILY_CAP_USD is set in one place (no step overrides or exports it)', wf_values.count('X_DAILY_CAP_USD') == 2,
      wf_values.count('X_DAILY_CAP_USD'))
check('spend gate step exists, unconditional', i_gate >= 0 and 'if' not in steps[i_gate], i_gate)
check('news bridge still runs first, ahead of the gate', 0 <= i_bridge < i_gate, (i_bridge, i_gate))
check('gate runs before the 15-minute floor and both paid pulls', 0 <= i_gate < i_floor < i_xpull < i_news,
      (i_gate, i_floor, i_xpull, i_news))

# 6. the gate step itself, in scratch repos: main's newer ledger is synced in, then the ceiling decides
def git(cwd, *a):
    return subprocess.run(['git', '-c', 'user.name=fixture', '-c', 'user.email=f@example.com', *a], cwd=cwd,
                          capture_output=True, text=True, timeout=60)

def gate_case(main_spend):
    root = tempfile.mkdtemp(prefix='rp-xgate-'); scratch_dirs.append(root)
    origin = os.path.join(root, 'origin.git'); a = os.path.join(root, 'a'); b = os.path.join(root, 'b')
    git(root, 'init', '-q', '--bare', '-b', 'main', origin)
    git(root, 'clone', '-q', origin, a)
    os.makedirs(os.path.join(a, 'slates')); os.makedirs(os.path.join(a, 'scripts'))
    if x_budget:
        shutil.copy(os.path.join(HERE, 'x_budget.py'), os.path.join(a, 'scripts', 'x_budget.py'))
    old = [x_fake.ledger_row(30, 100)]
    with open(os.path.join(a, 'slates', 'x_burn.jsonl'), 'w') as f:
        f.writelines(json.dumps(r) + '\n' for r in old)
    git(a, 'add', '-A'); git(a, 'commit', '-q', '-m', 'seed'); git(a, 'push', '-q', 'origin', 'HEAD:main')
    git(root, 'clone', '-q', origin, b)
    with open(os.path.join(b, 'slates', 'x_burn.jsonl'), 'a') as f:
        f.writelines(json.dumps(r) + '\n' for r in x_fake.rows_costing(main_spend))
    git(b, 'commit', '-q', '-am', 'previous run ledger'); git(b, 'push', '-q', 'origin', 'HEAD:main')
    genv = os.path.join(root, 'github_env'); open(genv, 'w').close()
    tmp = os.path.join(root, 'runner_temp'); os.makedirs(tmp)
    env = {k: v for k, v in os.environ.items() if not k.startswith('X_')}  # keeps any dead-proxy settings
    env.update({'GITHUB_ENV': genv, 'RUNNER_TEMP': tmp, 'X_DAILY_CAP_USD': '', 'X_PAID_PULLS': ''})
    r = subprocess.run(['bash', '-e', '-c', runs(steps[i_gate]) if i_gate >= 0 else 'exit 9'], cwd=a, env=env,
                       capture_output=True, text=True, timeout=120)
    local = [json.loads(l) for l in open(os.path.join(a, 'slates', 'x_burn.jsonl')) if l.strip()]
    return r, local, open(genv).read()

r, local, genv = gate_case(2.95)
check('gate: stale checkout picks up main\'s newer ledger rows', r.returncode == 0 and len(local) == 1 + len(x_fake.rows_costing(2.95)),
      (r.returncode, len(local), (r.stdout + r.stderr)[-400:]))
check('gate: $2.95 already spent on main -> every paid step skipped (SKIP_X_PULL=1)', 'SKIP_X_PULL=1' in genv, genv)
r, local, genv = gate_case(1.00)
check('gate: $1.00 spent -> pulls stay on', r.returncode == 0 and 'SKIP_X_PULL=1' not in genv, (r.returncode, genv, (r.stdout + r.stderr)[-400:]))

# 7. the matcher step's ingest fixtures do not depend on the day's spend --------------------------------
# soc_fixtures.py runs x_feed.main() inside the x-feed matcher step; if it read the real ledger and the
# run's ceiling, a spent day would make it fail and abort the chain before the map is built.
env = {k: v for k, v in os.environ.items() if not k.startswith('X_')}
env['X_DAILY_CAP_USD'] = '0'
r = subprocess.run([sys.executable, os.path.join(HERE, 'soc_fixtures.py')], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
check('soc_fixtures (matcher step) still passes when the daily cap leaves nothing (X_DAILY_CAP_USD=0)',
      r.returncode == 0, (r.returncode, (r.stdout + r.stderr)[-400:]))

for p in scratch_dirs:
    shutil.rmtree(p, ignore_errors=True)
print('x daily cap: ' + ('OK' if not failures else f'{len(failures)} FAIL'))
sys.exit(1 if failures else 0)
