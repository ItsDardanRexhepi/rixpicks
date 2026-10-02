#!/usr/bin/env python3
"""failure-watchdog: diagnose a failed writer run from its logs + budgeted auto-redispatch.
Invoked by .github/workflows/watchdog.yml on workflow_run:completed with conclusion=failure.
Env: GH_TOKEN, RUN_ID, WF_NAME, WF_ID, HEAD_SHA, REPO(optional)."""
import json, os, re, subprocess, datetime, urllib.request, urllib.error, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from watchdog_diag import pick_failed_jobs, failing_steps, error_tail

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


_ESCAPES = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b[@-Z\\-_]|[\x00-\x08\x0b-\x1f\x7f]')


def strip_escapes(text):
    """Drop terminal escape sequences and control characters, keeping tabs and newlines."""
    return _ESCAPES.sub('', text)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def job_log(job_id, opener=None):
    """The job's plain-text log. The logs endpoint answers 302 to a signed download
    URL; the download is fetched without the token (a cross-host redirect must not
    carry it) and the text is stripped of terminal escape sequences. `gh api` refuses
    to print a body that contains them, which left every diagnosis without a tail."""
    opener = opener or urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(
        f'https://api.github.com/repos/{REPO}/actions/jobs/{job_id}/logs',
        headers={'Authorization': 'Bearer ' + os.environ.get('GH_TOKEN', ''),
                 'Accept': 'application/vnd.github+json',
                 'User-Agent': 'rixpicks-watchdog'})
    try:
        resp = opener.open(req)
        location = None
        body = resp.read()
    except urllib.error.HTTPError as e:
        if e.code not in (301, 302, 303, 307, 308):
            raise
        location = e.headers.get('Location')
        body = b''
    if location:
        body = opener.open(urllib.request.Request(location, headers={'User-Agent': 'rixpicks-watchdog'})).read()
    return strip_escapes(body.decode('utf-8', 'replace'))


BUDGET_COST = {'odds-refresh': 3, 'extras-sweep': 3, 'nfl-scores-confirm': 1}
SOFT_DAILY_TARGET = 100  # soft discipline target across consumers (main 12:11) - NOT a hard cap; audits: over-target runs are valid. Hard guardrail = provider x-requests-remaining floor.

def odds_spend_today():
    """Conservative daily Odds-API spend estimate (soft-target accounting only, main
    12:11 - NOT a hard cap; the provider x-requests-remaining floor is the hard gate).
    max(git commit counter, runs-based estimate). PT day boundary (PDT = UTC-7)."""
    import re as _re
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    pt = now_utc - datetime.timedelta(hours=7)
    pt_midnight_utc = pt.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(hours=7)
    since = pt_midnight_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
    git_max = 0
    try:
        log = subprocess.run(['git', 'log', '--since=' + pt_midnight_utc.isoformat(), '--format=%s'],
                             capture_output=True, text=True).stdout
        for m in _re.finditer(r'call (\d+)/(?:16|33)', log):
            git_max = max(git_max, int(m.group(1)) * 3)
    except Exception:
        pass
    est = 0
    for wfid, cost in ((367062180, 3), ('extras_sweep.yml', 3), ('nfl_scores.yml', 1)):
        try:
            rr = gh(f'repos/{REPO}/actions/workflows/{wfid}/runs?per_page=100')
            est += cost * sum(1 for x in rr.get('workflow_runs', []) if x.get('created_at', '') >= since)
        except Exception:
            pass
    return max(git_max, est)


# The provider's last credit reading is ops state, never site content: refresh.sh keeps it outside
# the checkout (every file in the repo is served) and the workflows carry it in the Actions cache.
QUOTA_FILE = os.path.join(os.environ.get('RP_OPS_STATE') or os.path.expanduser('~/.rixpicks-ops'), 'odds_quota.json')

def provider_remaining(path=QUOTA_FILE, now=None):
    """Authoritative provider quota: the odds-refresh lane's last x-requests-remaining reading
    ({'pt_date', 'last_remaining'} in the ops state file, the value refresh.sh's hard-cap tripwire
    reads). No served file carries the count (LS-22). None when unavailable or when the reading
    was not taken today (PT), so a stale reading never blocks a retry."""
    try:
        from zoneinfo import ZoneInfo
        d = json.load(open(path))
        now = now or datetime.datetime.now(datetime.timezone.utc)
        if d.get('pt_date') != now.astimezone(ZoneInfo('America/Los_Angeles')).strftime('%Y-%m-%d'):
            return None
        rem = d.get('last_remaining')
        return int(rem) if rem is not None else None
    except Exception:
        return None

# Every form a count can take in a log: the provider's headers (x-requests-used gives the count
# away as plan minus used), the lanes' 'credits remaining N' lines, JSON or dict keys (including
# this script's own printed provider_remaining), and refresh.sh's shell forms under a set -x
# trace (LASTREM=N, LASTREM_PRE=N, int('N')).
_CREDIT_RE = re.compile(r'(?i)(x-requests-(?:remaining|used):?\s*|credits? remaining:?\s*|credits used\s*\d+,\s*remaining\s*'
                        r'|["\']?(?:last_remaining|credits_remaining|provider_remaining)["\']?\s*[:=]\s*(?:int\(\s*["\']?)?'
                        r'|\bLASTREM(?:_PRE)?=["\']?|\bint\(\s*["\'])\d+')

def redact_credits(text):
    """The incident note is committed (served); the provider's credit count never goes there."""
    return _CREDIT_RE.sub(lambda m: m.group(1) + 'N', text or '')

run_id, wf, wf_id = os.environ['RUN_ID'], os.environ['WF_NAME'], os.environ['WF_ID']
sha = os.environ.get('HEAD_SHA', '')[:8]
now = datetime.datetime.now(datetime.timezone.utc)
diag = {'run_id': run_id, 'workflow': wf, 'head': sha, 'ts': now.isoformat()}

jobs = gh(f'repos/{REPO}/actions/runs/{run_id}/jobs')
failed_jobs = pick_failed_jobs(jobs.get('jobs'))
diag['failing_steps'] = failing_steps(failed_jobs)
diag['failed_jobs'] = [j.get('name', '?') for j in failed_jobs]
try:
    tails = []
    for j in failed_jobs[:2]:
        lines = job_log(j['id']).splitlines()
        tails.append(('[job: %s]\n' % j.get('name', '?')) + error_tail(lines))
    diag['error_tail'] = '\n'.join(tails)[:2400] or 'no failed job found'
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
if not skip:
    prem = provider_remaining()
    diag['provider_remaining'] = prem
    if prem is not None and prem < 100:
        skip.append('provider quota low: under 100 credits remaining (authoritative header)')  # the count stays in the run log
if wf in BUDGET_COST:
    spend = odds_spend_today()
    diag['odds_spend_today'] = spend
    # soft target only: recorded for accounting, never blocks a retry (main 12:11);
    # the provider floor above is the only hard budget gate.
    if spend + BUDGET_COST[wf] > SOFT_DAILY_TARGET:
        diag['budget_note'] = 'over soft daily target (%d/%d) - discipline only, not a violation' % (spend, SOFT_DAILY_TARGET)
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
    f.write('# watchdog diagnosis: %s run %s\n\n- head: %s\n- failed jobs: %s\n- failing steps: %s\n- decision: %s\n- url: https://github.com/%s/actions/runs/%s\n\n## error tail\n```\n%s\n```\n'
            % (wf, run_id, sha, ', '.join(diag['failed_jobs']) or 'unknown', ', '.join(diag['failing_steps']) or 'unknown', diag['decision'], REPO, run_id, redact_credits(diag['error_tail'])))
print(json.dumps(diag, indent=1))

