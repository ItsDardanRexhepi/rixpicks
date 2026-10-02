#!/usr/bin/env python3
"""X API daily spend ceiling, shared by scripts/x_feed.py, scripts/news_social.py and the x-feed
workflow's spend gate step.

Why: the X API is pay-per-use. The signed-off burn is about $3/day (x_feed.yml cron note), but at
news_social's 18 x 100-post settings the burn ledger shows $3.25-$4.45 per 15-minute cycle, and
nothing in code capped a day.

Ceiling: X_DAILY_CAP_USD (repo variable); DEFAULT_DAILY_CAP_USD, the signed-off $3.00, when it is
unset or unreadable. This module only reads the ceiling: an unreadable value falls back to $3.00,
never to a larger number, and unused budget does not carry over.

Spend: burn-ledger rows (slates/x_burn.jsonl, one per billed request) from the trailing 24 hours,
each priced at the code's measured rates: COST_PER_REQUEST plus COST_PER_POST per post returned.
A trailing window keeps every calendar day (UTC or PT) under the ceiling. A row that cannot be
dated counts as today; a row that cannot be sized counts as a full 100-post request.

Projection: before a pull, its worst case (every request returns max_results posts) is set against
what is left. A pull that would cross the ceiling is shrunk (fewer requests; when not even one full
request fits, one request with fewer posts) or skipped, and the log says why. Every request is
checked again just before it is sent. All arithmetic is in whole mills (1/1000 USD), so rounding
can never let a request through.

CLI (the x-feed workflow's spend gate step):
  python3 scripts/x_budget.py gate [--main-ledger PATH]
adds the rows of main's newest ledger that this checkout lacks (a run that checked out before the
previous run published its ledger would otherwise neither see nor keep that spend), then writes
SKIP_X_PULL=1 to $GITHUB_ENV when not even the smallest request fits. It never fails the run.
"""
import collections, datetime, decimal, json, os, re, sys

LEDGER = 'slates/x_burn.jsonl'
# MEASURED pricing (X console, Sep 28 9:22 AM PT: 190 events / $0.97 / 29 requests over 30d):
COST_PER_REQUEST = 0.033
COST_PER_POST = 0.005
REQ_MILLS = round(COST_PER_REQUEST * 1000)
POST_MILLS = round(COST_PER_POST * 1000)
DEFAULT_DAILY_CAP_USD = '3.00'  # the signed-off figure; X_DAILY_CAP_USD replaces it, nothing raises it
MIN_RESULTS = 10                # X recent search takes max_results 10..100
MAX_RESULTS = 100
WINDOW = datetime.timedelta(hours=24)
UTC = datetime.timezone.utc
_AMOUNT = re.compile(r'^\$?\s*(\d+(?:\.\d*)?|\.\d+)$')


def usd(mills):
    return ('-' if mills < 0 else '') + '$%d.%03d' % divmod(abs(int(mills)), 1000)


def cap_mills(env=None):
    """The daily ceiling in mills: X_DAILY_CAP_USD rounded down, or the $3.00 default."""
    env = os.environ if env is None else env
    default = int(decimal.Decimal(DEFAULT_DAILY_CAP_USD) * 1000)
    raw = (env.get('X_DAILY_CAP_USD') or '').strip()
    if not raw:
        return default
    m = _AMOUNT.match(raw)
    if not m:
        print(f'X budget: X_DAILY_CAP_USD={raw[:40]!r} is not a dollar amount - using the {usd(default)} default')
        return default
    return int((decimal.Decimal(m.group(1)) * 1000).to_integral_value(rounding=decimal.ROUND_FLOOR))


def _ts(v):
    try:
        dt = datetime.datetime.fromisoformat(str(v).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def row_mills(row):
    r = row.get('results')
    if isinstance(r, bool) or not isinstance(r, int) or r < 0:
        r = MAX_RESULTS
    return REQ_MILLS + POST_MILLS * r


def _lines(path):
    try:
        with open(path) as f:
            return [ln.strip() for ln in f if ln.strip()]
    except FileNotFoundError:
        return []


def read_rows(path=LEDGER):
    rows = []
    for ln in _lines(path):
        try:
            row = json.loads(ln)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def spent_mills(rows, now=None):
    """Spend in the trailing 24 hours at the code's rates."""
    now = now or datetime.datetime.now(UTC)
    total = 0
    for row in rows:
        ts = _ts(row.get('ts'))
        if ts is not None and now - ts >= WINDOW:
            continue
        total += row_mills(row)
    return total


def _say(msg, warn=False):
    print(msg)
    if warn and os.environ.get('GITHUB_ACTIONS') == 'true':
        print('::warning title=X daily spend cap::' + msg)


class Budget:
    def __init__(self, cap, spent):
        self.cap, self.spent = cap, spent

    @classmethod
    def load(cls, ledger=LEDGER, now=None, env=None):
        return cls(cap_mills(env), spent_mills(read_rows(ledger), now))

    @staticmethod
    def worst(max_results):
        return REQ_MILLS + POST_MILLS * max_results

    def left(self):
        return self.cap - self.spent

    def fits(self, max_results):
        return self.spent + self.worst(max_results) <= self.cap

    def charge(self, results):
        self.spent += REQ_MILLS + POST_MILLS * max(0, int(results or 0))

    def status(self):
        return f'{usd(self.spent)} spent in the last 24h, {usd(max(0, self.left()))} left of the {usd(self.cap)} daily cap'

    def plan(self, label, n, max_results):
        """(requests, max_results) this pull may make without crossing the ceiling at worst case."""
        n = max(0, int(n))
        if not n:
            return 0, max_results
        w = self.worst(max_results)
        fit = max(0, self.left()) // w
        if fit >= n:
            _say(f'X budget [{label}]: {n} requests x {max_results} posts, worst case {usd(n * w)} - {self.status()}')
            return n, max_results
        if fit >= 1:
            _say(f'X budget [{label}]: SHRUNK {n} -> {fit} requests - worst case {usd(n * w)} would pass the daily cap; '
                 f'{self.status()}', warn=True)
            return fit, max_results
        fewer = min(max_results, (self.left() - REQ_MILLS) // POST_MILLS)
        if fewer >= MIN_RESULTS:
            _say(f'X budget [{label}]: SHRUNK {n} -> 1 request x {fewer} posts (was {max_results}) - one full request '
                 f'(worst case {usd(w)}) would pass the daily cap; {self.status()}', warn=True)
            return 1, fewer
        _say(f'X budget [{label}]: SKIPPED - the smallest request (worst case {usd(self.worst(MIN_RESULTS))}) would pass '
             f'the daily cap; {self.status()}', warn=True)
        return 0, max_results

    def stop(self, label, made, max_results):
        _say(f'X budget [{label}]: STOPPED after {made} requests - the next one (worst case {usd(self.worst(max_results))}) '
             f'would pass the daily cap; {self.status()}', warn=True)


def merge_ledger(local=LEDGER, main=None):
    """Add main's ledger rows that this checkout lacks (multiset: a row main holds twice and the
    checkout once is added once). Main's order first, then rows only this checkout has. Returns the
    number of rows added."""
    main_lines = _lines(main) if main else []
    if not main_lines:
        return 0
    local_lines = _lines(local)
    left = collections.Counter(local_lines)
    merged = []
    for ln in main_lines:
        merged.append(ln)
        if left[ln]:
            left[ln] -= 1
    for ln in local_lines:
        if left[ln]:
            merged.append(ln)
            left[ln] -= 1
    added = len(merged) - len(local_lines)
    if added:
        os.makedirs(os.path.dirname(local) or '.', exist_ok=True)
        with open(local, 'w') as f:
            f.write('\n'.join(merged) + '\n')
    return added


def _skip(reason):
    print('X spend gate: paid X pulls SKIPPED this run - ' + reason)
    genv = os.environ.get('GITHUB_ENV')
    if genv:
        with open(genv, 'a') as f:
            f.write('SKIP_X_PULL=1\n')


def gate(argv):
    main = argv[argv.index('--main-ledger') + 1] if '--main-ledger' in argv[:-1] else None
    if main:
        print(f'X spend gate: ledger synced with main (+{merge_ledger(LEDGER, main)} rows this checkout lacked)')
    b = Budget.load(LEDGER)
    if not b.fits(MIN_RESULTS):
        _skip(f'daily cap reached, the smallest request costs up to {usd(b.worst(MIN_RESULTS))}; {b.status()}')
        return 0
    print('X spend gate: pulls allowed - ' + b.status())
    return 0


if __name__ == '__main__':
    if sys.argv[1:2] == ['gate']:
        sys.exit(gate(sys.argv[2:]))
    sys.exit('usage: x_budget.py gate [--main-ledger PATH]')
