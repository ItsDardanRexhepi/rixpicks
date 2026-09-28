"""J-123: free-tier triage until he buys the paid tier (~9/30). J-123a (verbatim):
props fully gated on paid tier - no scrape path, no book-only props screens.
Credit discipline: 16 credits/day, USER-local day (America/Los_Angeles).
check_and_log is atomic across processes: exclusive flock held over read-check-write."""
import json, os, fcntl
from datetime import datetime
from zoneinfo import ZoneInfo
PAID_TIER = True   # J-123 satisfied: his verbatim iMessage 2026-09-27 08:53:04 PT 'Let's sign up for that $30 odds API now then so we can have it' (verified in observations), relayed by main 16:07:38 with 09:03 checkout completion; 19,905-credit provider reading corroborates
DAILY_CAP = None  # NO daily cap - his word 2026-09-27 16:23 PT via main: 'Make it so there's no cap if you can.' Ledger logging stays as telemetry (check_and_log still records every pull)
PLAN_MONTH_CAP = 20000   # hard provider plan limit (20K/mo)
PLAN_TRIPWIRE = 18000    # his 16:24 refinement via main: no cap UNLESS the plan cap is at risk - one fail-loud tripwire near the plan limit. Provider x-requests-remaining header is authoritative when present; this local tally is the floor.
TZ = ZoneInfo('America/Los_Angeles')
LEDGER = '/home/sandbox/rps_tmp/kb/ledger/odds_credits.jsonl'
def odds_key():
    k = os.environ.get('THE_ODDS_API_KEY')
    if k: return k.strip()
    with open('/home/sandbox/.odds_api_key') as f: return f.read().strip()

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
            lines = f.readlines()
            used = _used_from_lines(lines)
            if DAILY_CAP is not None and used + credits > DAILY_CAP:
                raise ValueError(f'credit cap: {used}+{credits} > {DAILY_CAP}/day (J-123)')
            month = sum(d['credits'] for d in
                        (json.loads(l) for l in lines if l.strip())
                        if isinstance(d, dict) and str(d.get('local_date','')).startswith(_today()[:7]))
            if month + credits > PLAN_TRIPWIRE:
                raise ValueError(f'PLAN TRIPWIRE: {month}+{credits} > {PLAN_TRIPWIRE}/mo of {PLAN_MONTH_CAP} (fail-loud per his 16:24 word)')
            f.write(json.dumps({'ts': datetime.now(TZ).isoformat(), 'local_date': _today(),
                                'sport': sport, 'markets': markets, 'credits': credits}) + '\n')
            f.flush(); os.fsync(f.fileno())
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return {'used_after': credits_today(), 'cap': DAILY_CAP}
