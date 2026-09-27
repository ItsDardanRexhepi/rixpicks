#!/usr/bin/env python3
"""failure-watchdog: diagnose a failed writer run from its logs + budgeted auto-redispatch.
Invoked by .github/workflows/watchdog.yml on workflow_run:completed with conclusion=failure.
Env: GH_TOKEN, RUN_ID, WF_NAME, WF_ID, HEAD_SHA, REPO(optional)."""
import json, os, subprocess, datetime

REPO = os.environ.get('REPO', 'ItsDardanRexhepi/rixpicks')
RETRY_BUDGET_S = 1800  # one auto-retry per workflow per 30 min

def gh(path, method='GET', fields=None, raw=False):
    cmd = ['gh', 'api', path, '-X', method]
    for f in (fields or []):
        cmd += ['-f', f]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError('gh ' + path + ': ' + r.stderr[:300])
    return r.stdout if raw else (json.loads(r.stdout) if r.stdout.strip() else {})


BUDGET_COST = {'odds-refresh': 1, 'extras-sweep': 3, 'nfl-scores-confirm': 1}
BUDGET_CAP = 16

def odds_spend_today():
    """Conservative daily Odds-API spend across all consumers: max(git commit counter,
    runs-based estimate). PT day boundary (PDT = UTC-7)."""
    import re as _re
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    pt = now_utc - datetime.timedelta(hours=7)
    pt_midnight_utc = pt.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(hours=7)
    since = pt_midnight_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
    git_max = 0
    try:
        log = subprocess.run(['git', 'log', '--since=' + pt_midnight_utc.isoformat(), '--format=%s'],
                             capture_output=True, text=True).stdout
        for m in _re.finditer(r'call (\d+)/16', log):
            git_max = max(git_max, int(m.group(1)))
    except Exception:
        pass
    est = 0
    for wfid, cost in ((367062180, 1), ('extras_sweep.yml', 3), ('nfl_scores.yml', 1)):
        try:
            rr = gh(f'repos/{REPO}/actions/workflows/{wfid}/runs?per_page=100')
            est += cost * sum(1 for x in rr.get('workflow_runs', []) if x.get('created_at', '') >= since)
        except Exception:
            pass
    return max(git_max, est)

run_id, wf, wf_id = os.environ['RUN_ID'], os.environ['WF_NAME'], os.environ['WF_ID']
sha = os.environ.get('HEAD_SHA', '')[:8]
now = datetime.datetime.now(datetime.timezone.utc)
diag = {'run_id': run_id, 'workflow': wf, 'head': sha, 'ts': now.isoformat()}

jobs = gh(f'repos/{REPO}/actions/runs/{run_id}/jobs')
job = (jobs.get('jobs') or [{}])[0]
diag['failing_steps'] = [s['name'] for s in job.get('steps', []) if s.get('conclusion') == 'failure']
try:
    log = gh(f'repos/{REPO}/actions/jobs/{job["id"]}/logs', raw=True)
    lines = log.splitlines()
    hits = [l for l in lines if any(k in l.lower() for k in ('error', 'fail', 'conflict', 'fatal', 'traceback', 'refus'))]
    diag['error_tail'] = '\n'.join((hits[-6:] or lines[-6:]))[:1200]
except Exception as e:
    diag['error_tail'] = 'log fetch failed: ' + str(e)[:200]

try:
    state = json.load(open('watchdog_state.json'))
except Exception:
    state = {}
rec = state.get(wf, {})
skip = []
last = rec.get('last_retry_at')
if last and (now - datetime.datetime.fromisoformat(last)).total_seconds() < RETRY_BUDGET_S:
    skip.append('already auto-retried within 30 min')
runs = gh(f'repos/{REPO}/actions/workflows/{wf_id}/runs?per_page=3')
failed_started = next((x.get('run_started_at') for x in runs.get('workflow_runs', []) if str(x['id']) == str(run_id)), None)
if failed_started and any(x.get('run_started_at', '') > failed_started for x in runs.get('workflow_runs', [])):
    skip.append('newer run exists - superseded')
if not skip and wf in BUDGET_COST:
    spend = odds_spend_today()
    diag['odds_spend_today'] = spend
    if spend + BUDGET_COST[wf] > BUDGET_CAP:
        skip.append('Odds-API daily budget: %d/%d spent, retry costs %d' % (spend, BUDGET_CAP, BUDGET_COST[wf]))
if skip:
    diag['decision'] = 'no auto-retry: ' + ', '.join(skip)
else:
    try:
        gh(f'repos/{REPO}/actions/workflows/{wf_id}/dispatches', 'POST', ['ref=main'])
        diag['decision'] = 'auto-redispatched once (30-min budget)'
        state[wf] = {'last_retry_at': now.isoformat()}
    except Exception as e:
        diag['decision'] = 'retry dispatch failed: ' + str(e)[:200]

json.dump(state, open('watchdog_state.json', 'w'), indent=1)
os.makedirs('incidents', exist_ok=True)
with open(f'incidents/{run_id}-diag.md', 'w') as f:
    f.write('# watchdog diagnosis: %s run %s\n\n- head: %s\n- failing steps: %s\n- decision: %s\n- url: https://github.com/%s/actions/runs/%s\n\n## error tail\n```\n%s\n```\n'
            % (wf, run_id, sha, ', '.join(diag['failing_steps']) or 'unknown', diag['decision'], REPO, run_id, diag['error_tail']))
print(json.dumps(diag, indent=1))
