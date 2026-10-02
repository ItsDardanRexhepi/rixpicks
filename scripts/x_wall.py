"""Shared X API billing/access wall detector (main 9:05 class fix: every X-calling
step skips-and-continues on the owner-side wall so chain verification is not
hostage to billing; anything else fails loud).

Wall = EVERY observed failure is a uniform owner-side access/billing denial:
402 (payment required / credits exhausted) or 403 (plan access denied).
401 (token), 429 (backoff), network errors, and mixed codes stay loud.

Sustained-wall alert (Oct 2): the skip path ends the run green, so a wall that lasts
(402 on every request from 9/30 01:39Z, about 68 h) reached no alert. Each pull now records
its run outcome (record_outcome -> $X_RUN_OUTCOME), and the x-feed 'X wall streak' step
(python3 scripts/x_wall.py streak) counts consecutive due runs on which X denied EVERY
request (401/402/403) in WALL_STATE. One success resets the count; a run that made no
request, or that saw other failures, leaves it as it was. At WALL_ALERT_RUNS in a row it
writes X_WALL_ALERT=1 to $GITHUB_ENV and the run's last step fails the run (incident-hook
records it) after news and the commits have run; while the wall lasts it alerts again every
WALL_REALERT_HOURS, not every run.
"""
import datetime, json, os, re, sys

WALL_CODES = {'402', '403'}
DENIED_CODES = {'401', '402', '403'}   # streak class: token, credits/billing, plan access
WALL_ALERT_RUNS = 4
WALL_REALERT_HOURS = 6
WALL_STATE = 'slates/x_wall_state.json'
UTC = datetime.timezone.utc


def http_code(err):
    m = re.search(r'HTTP Error (\d+)', str(err))
    return m.group(1) if m else None


def is_wall(codes):
    return bool(codes) and set(codes) <= WALL_CODES


def wall_skip(step):
    print(f'X billing/access wall (uniform 402/403) at {step}: pull skipped, prior artifacts preserved; chain continues on frozen pool')


def record_outcome(script, attempted, ok, codes):
    """Append one script's request outcome to this run's outcome file ($X_RUN_OUTCOME).
    codes = one entry per failed request: its HTTP code, or 'error' when it had none."""
    path = os.environ.get('X_RUN_OUTCOME')
    if not path or not attempted:
        return
    try:
        with open(path, 'a') as f:
            f.write(json.dumps({'script': script, 'attempted': int(attempted), 'ok': int(ok),
                                'codes': [str(c) for c in codes]}) + '\n')
    except OSError as e:  # the pull itself must never fail on its bookkeeping
        print(f'X wall streak: run outcome not recorded ({e}) - this run cannot advance the streak')


def run_verdict(records):
    """'ok' (some request succeeded), 'denied' (every request 401/402/403),
    'none' (no request made) or 'mixed' (failures that are not all denials)."""
    attempted = sum(int(r.get('attempted') or 0) for r in records)
    if not attempted:
        return 'none'
    if any(int(r.get('ok') or 0) > 0 for r in records):
        return 'ok'
    codes = [c for r in records for c in (r.get('codes') or [])]
    if len(codes) == attempted and set(codes) <= DENIED_CODES:
        return 'denied'
    return 'mixed'


def _ts(v):
    try:
        dt = datetime.datetime.fromisoformat(str(v).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def advance(state, verdict, codes, now):
    """New wall state for one due run. Returns (state, alert message or None, log line)."""
    st = dict(state) if isinstance(state, dict) else {}
    n = st.get('streak') if isinstance(st.get('streak'), int) and st.get('streak') >= 0 else 0
    stamp = now.isoformat(timespec='seconds')
    if verdict == 'ok':
        note = (f'X wall cleared: a request succeeded after {n} walled runs (since {st.get("first_denied_at")})'
                if n else 'X wall streak: requests succeeding')
        return {'streak': 0, 'threshold': WALL_ALERT_RUNS, 'last_ok_at': stamp}, None, note
    if verdict != 'denied':
        return st, None, f'X wall streak unchanged at {n} ({verdict}: no request made, or failures other than 401/402/403)'
    n += 1
    st.update({'streak': n, 'threshold': WALL_ALERT_RUNS, 'last_denied_at': stamp,
               'codes': sorted(set(codes))})
    if n == 1 or not st.get('first_denied_at'):
        st['first_denied_at'] = stamp
    shown = '/'.join(sorted(set(codes)))
    if n < WALL_ALERT_RUNS:
        return st, None, f'X wall: every request denied (HTTP {shown}) - {n} of {WALL_ALERT_RUNS} due runs before the alert'
    last = _ts(st.get('last_alert_at'))
    if last is not None and now - last < datetime.timedelta(hours=WALL_REALERT_HOURS):
        return st, None, (f'X wall: every request denied (HTTP {shown}) on {n} due runs in a row since '
                          f'{st["first_denied_at"]}; alerted {st["last_alert_at"]}, next alert after {WALL_REALERT_HOURS}h')
    st['last_alert_at'] = stamp
    msg = (f'X API denied every request (HTTP {shown}) on {n} due runs in a row since {st["first_denied_at"]} - '
           f'paid X pulls are failing (credits/billing, plan access or token); news publishing continues. '
           f'Repeats every {WALL_REALERT_HOURS}h while the wall lasts.')
    return st, msg, 'X WALL ALERT: ' + msg


def _alert_env(msg):
    if os.environ.get('GITHUB_ENV'):
        with open(os.environ['GITHUB_ENV'], 'a') as f:
            f.write('X_WALL_ALERT=1\n')
            f.write('X_WALL_MSG=' + msg.replace('\n', ' ') + '\n')


def streak_main():
    """x-feed 'X wall streak' step. Never fails the step; the alert is the run's last step."""
    path = os.environ.get('X_RUN_OUTCOME') or ''
    records = []
    try:
        with open(path) as f:
            for ln in f:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if isinstance(r, dict):
                    records.append(r)
    except OSError:
        pass
    try:
        with open(WALL_STATE) as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {}
    verdict = run_verdict(records)
    codes = [str(c) for r in records for c in (r.get('codes') or [])]
    state, alert, note = advance(state, verdict, codes, datetime.datetime.now(UTC))
    print(note)
    if verdict == 'denied' and not alert and os.environ.get('GITHUB_ACTIONS') == 'true':
        print('::warning title=X API wall::' + note)
    os.makedirs(os.path.dirname(WALL_STATE), exist_ok=True)
    with open(WALL_STATE, 'w') as f:
        json.dump(state, f, indent=1)
        f.write('\n')
    if alert:
        _alert_env(alert)
    return 0


if __name__ == '__main__':
    if sys.argv[1:2] != ['streak']:
        sys.exit('usage: x_wall.py streak')
    try:
        sys.exit(streak_main())
    except Exception as e:  # never break the chain here; fail the run loudly at its end instead
        print(f'X wall streak step error: {type(e).__name__}: {e}')
        _alert_env(f'X wall streak step error ({type(e).__name__}: {str(e)[:200]}) - the wall alert is not being tracked')
        sys.exit(0)
