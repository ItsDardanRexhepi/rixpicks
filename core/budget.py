"""J-123: free-tier triage until he buys the paid tier (~9/30). J-123a (verbatim):
props fully gated on paid tier - no scrape path, no book-only props screens.
Credit discipline: 16 credits/day, USER-local day (America/Los_Angeles).
check_and_log is atomic across processes: exclusive flock held over read-check-write."""
import json, os, fcntl
from datetime import datetime
from zoneinfo import ZoneInfo
PAID_TIER = True   # his verbatim word via main 2026-09-27: iMessage 08:53 PT signup + 09:03 checkout; provider x-requests-remaining 19,905 confirms the 20K plan live
DAILY_CAP = None   # REMOVED on his verbatim word (main 9/27 4:23 PT): "Make it so there's no cap if you can." Ledger below still logs every pull - telemetry, not a limit.
# STANDING RULE (his verbatim word, main 9/27 4:24 PT, made standing by him): "no cap unless we hit a hard cap ever."
# No daily/self-imposed cap - the only tripwire is the API plan's own 20,000 credits/month hard limit.
# If the ledger projects a monthly breach, fail loud instead of silently burning into overage.
MONTHLY_PLAN_LIMIT = 20000
TZ = ZoneInfo('America/Los_Angeles')
LEDGER = os.environ.get('ODDS_CREDITS_LEDGER', '/home/sandbox/rps_tmp/kb/ledger/odds_credits.jsonl')
def props_allowed(): return PAID_TIER
def props_block_reason():
    return 'player props gated on paid odds tier (J-123a, verbatim 9/26 9:09 PM); no scrape path'
def _today(): return datetime.now(TZ).date().isoformat()
def _month(): return datetime.now(TZ).strftime('%Y-%m')
def _used_month_from_lines(lines):
    n = 0
    m = _month()
    for line in lines:
        try: d = json.loads(line)
        except Exception: continue
        if str(d.get('local_date','')).startswith(m): n += d['credits']
    return n
def credits_this_month():
    try:
        with open(LEDGER) as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try: return _used_month_from_lines(f.readlines())
            finally: fcntl.flock(f, fcntl.LOCK_UN)
    except FileNotFoundError: return 0
def _used_from_lines(lines):
    n = 0
    for line in lines:
        try: d = json.loads(line)
        except Exception: continue
        if d.get('local_date') == _today(): n += d['credits']
    return n
def credits_today():
    try:
        with open(LEDGER) as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try: return _used_from_lines(f.readlines())
            finally: fcntl.flock(f, fcntl.LOCK_UN)
    except FileNotFoundError: return 0
def check_and_log(sport, markets, credits):
    """Atomic across processes: validate -> flock(LOCK_EX) -> recount -> cap-check -> append."""
    if not isinstance(credits, int) or credits <= 0:
        raise ValueError(f'credits must be a positive int, got {credits!r}')
    os.makedirs(os.path.dirname(LEDGER) or '.', exist_ok=True)
    with open(LEDGER, 'a+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            lines = f.readlines()
            used = _used_from_lines(lines)
            if DAILY_CAP is not None and used + credits > DAILY_CAP:
                raise ValueError(f'credit cap: {used}+{credits} > {DAILY_CAP}/day (J-123)')
            month_used = _used_month_from_lines(lines)
            if month_used + credits > MONTHLY_PLAN_LIMIT:
                raise ValueError(f'credit cap: monthly {month_used}+{credits} would exceed plan hard limit {MONTHLY_PLAN_LIMIT}/mo (standing rule 9/27)')
            f.write(json.dumps({'ts': datetime.now(TZ).isoformat(), 'local_date': _today(),
                                'sport': sport, 'markets': markets, 'credits': credits}) + '\n')
            f.flush(); os.fsync(f.fileno())
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return {'used_after': credits_today(), 'month_used': credits_this_month(), 'cap': DAILY_CAP, 'monthly_limit': MONTHLY_PLAN_LIMIT}  # cap None = telemetry only
