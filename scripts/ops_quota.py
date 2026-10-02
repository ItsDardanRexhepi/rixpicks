#!/usr/bin/env python3
"""The odds provider's credit reading (the-odds-api x-requests-remaining) as ops state.

The reading is never site content: every file in the checkout is served (Pages + the Cloudflare
mirror), so it lives outside it ($RP_OPS_STATE/odds_quota.json, default ~/.rixpicks-ops) and
odds_refresh.yml carries it between runs in the Actions cache (LS-22). Each reading is stored with
its PT date and PT month, {"pt_date": "YYYY-MM-DD", "month": "YYYY-MM", "last_remaining": N}:
the provider resets usage credits on the first of every month, so a reading from an earlier month
says nothing about this one and is ignored (that is also how a tripped hard cap clears after the
reset). PT is the latest of the plausible reset clocks, so a reading labelled with this PT month
is never one taken before the reset.

  ops_quota.py reading <quota.json> [<legacy counter>]
      print this PT month's reading, or nothing: the ops state first, then the legacy
      last_remaining in the served run counter (.odds_refresh_count.json, whose month is that of
      its latest counted day; the next counted run drops it)
  ops_quota.py record <quota.json> <N>
      store a reading taken now, with its PT date and month
  ops_quota.py header <headers file>
      print the x-requests-remaining value of a curl -D header dump, or nothing
  ops_quota.py seed <quota.json>
      store the reading a workflow's quota-state job passed out (env QUOTA_REMAINING, QUOTA_MONTH,
      QUOTA_PT_DATE). That job unpacked the Actions cache with no secrets; nothing from it is
      trusted here, so every value is validated again and anything malformed seeds nothing.

Every command exits 0 on a missing or malformed reading (it gives no reading); refresh.sh
decides what no reading means. A count is never printed except as the bare value refresh.sh reads.
"""
import json, os, re, sys
from datetime import datetime
from zoneinfo import ZoneInfo

PT = ZoneInfo('America/Los_Angeles')
MAX_CREDITS = 999_999_999          # above the largest plan (15M credits a month)
_INT = re.compile(r'[0-9]{1,9}')
_MONTH = re.compile(r'20[0-9]{2}-(0[1-9]|1[0-2])')
_DATE = re.compile(r'20[0-9]{2}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])')


def _now_pt(now=None):
    return (now or datetime.now(PT)).astimezone(PT)


def valid_count(v):
    return type(v) is int and 0 <= v <= MAX_CREDITS


def _month_of(d):
    """A stored reading's PT month: its own month, else that of its PT date (stored before the
    month was recorded). None when neither is well formed or they disagree."""
    m, p = d.get('month'), d.get('pt_date')
    if p is not None and not (isinstance(p, str) and _DATE.fullmatch(p)):
        return None
    if m is None:
        return p[:7] if p else None
    if not (isinstance(m, str) and _MONTH.fullmatch(m)) or (p and p[:7] != m):
        return None
    return m


def reading(quota_path, counter_path=None, now=None):
    month = _now_pt(now).strftime('%Y-%m')
    try:
        d = json.load(open(quota_path))
        if isinstance(d, dict) and valid_count(d.get('last_remaining')) and _month_of(d) == month:
            return d['last_remaining']
    except Exception:
        pass
    if counter_path:
        try:
            c = json.load(open(counter_path))
            days = [k for k in c if isinstance(k, str) and _DATE.fullmatch(k)] if isinstance(c, dict) else []
            if days and valid_count(c.get('last_remaining')) and max(days)[:7] == month:
                return c['last_remaining']
        except Exception:
            pass
    return None


def _write(path, rec):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(rec, f)
    os.replace(tmp, path)


def record(path, n, now=None):
    if not valid_count(n):
        raise ValueError('not a credit count')
    day = _now_pt(now).strftime('%Y-%m-%d')
    _write(path, {'pt_date': day, 'month': day[:7], 'last_remaining': n})


def header_remaining(text):
    """x-requests-remaining from a header dump (the last one wins: curl -D writes every response
    of a redirect chain). The provider sends an integer; a decimal form is cut to its integer."""
    val = None
    for line in (text or '').splitlines():
        k, sep, v = line.partition(':')
        if sep and k.strip().lower() == 'x-requests-remaining':
            val = v.strip()
    if val is None:
        return None
    m = re.fullmatch(r'([0-9]{1,9})(\.[0-9]+)?', val)
    return int(m.group(1)) if m else None


def seed(path, env=None):
    env = os.environ if env is None else env
    rem, month, day = env.get('QUOTA_REMAINING', ''), env.get('QUOTA_MONTH', ''), env.get('QUOTA_PT_DATE', '')
    if not rem and not month and not day:
        print('ops quota: no reading from the quota-state job (cache miss) - none seeded')
        return False
    ok = (_INT.fullmatch(rem) is not None and int(rem) <= MAX_CREDITS and _MONTH.fullmatch(month) is not None
          and (day == '' or (_DATE.fullmatch(day) is not None and day[:7] == month)))
    if not ok:
        print('ops quota: the quota-state job passed a malformed reading - none seeded', file=sys.stderr)
        return False
    rec = {'pt_date': day, 'month': month, 'last_remaining': int(rem)} if day else {'month': month, 'last_remaining': int(rem)}
    _write(path, rec)
    print('ops quota: seeded the reading for %s from the quota-state job' % month)
    return True


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    cmd, path = argv[0], argv[1]
    if cmd == 'reading':
        n = reading(path, argv[2] if len(argv) > 2 else None)
        if n is not None:
            print(n)
    elif cmd == 'record':
        try:
            record(path, int(argv[2]) if len(argv) > 2 and _INT.fullmatch(argv[2]) else -1)
        except ValueError:
            print('ops quota: not a credit count - nothing recorded', file=sys.stderr)
            sys.exit(2)
    elif cmd == 'header':
        try:
            n = header_remaining(open(path, errors='replace').read())
        except OSError:
            n = None
        if n is not None:
            print(n)
    elif cmd == 'seed':
        seed(path)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
