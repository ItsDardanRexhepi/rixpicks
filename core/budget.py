"""J-123: free-tier triage until he buys the paid tier (~9/30). J-123a (verbatim):
props fully gated on paid tier - no scrape path, no book-only props screens.
Credit discipline: 16 credits/day, USER-local day (America/Los_Angeles).
check_and_log is atomic across processes: exclusive flock held over read-check-write."""
import json, os, fcntl
from datetime import datetime
from zoneinfo import ZoneInfo
PAID_TIER = True   # his verbatim word via main 2026-09-27: iMessage 08:53 PT signup + 09:03 checkout; provider x-requests-remaining 19,905 confirms the 20K plan live
DAILY_CAP = None   # REMOVED on his verbatim word (main 9/27 4:23 PT): "Make it so there's no cap if you can." Ledger below still logs every pull - telemetry, not a limit.
TZ = ZoneInfo('America/Los_Angeles')
LEDGER = os.environ.get('ODDS_CREDITS_LEDGER', '/home/sandbox/rps_tmp/kb/ledger/odds_credits.jsonl')
def props_allowed(): return PAID_TIER
def props_block_reason():
    return 'player props gated on paid odds tier (J-123a, verbatim 9/26 9:09 PM); no scrape path'
def _today(): return datetime.now(TZ).date().isoformat()
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
            used = _used_from_lines(f.readlines())
            if DAILY_CAP is not None and used + credits > DAILY_CAP:
                raise ValueError(f'credit cap: {used}+{credits} > {DAILY_CAP}/day (J-123)')
            f.write(json.dumps({'ts': datetime.now(TZ).isoformat(), 'local_date': _today(),
                                'sport': sport, 'markets': markets, 'credits': credits}) + '\n')
            f.flush(); os.fsync(f.fileno())
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return {'used_after': credits_today(), 'cap': DAILY_CAP}  # cap None = telemetry only
