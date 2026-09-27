#!/usr/bin/env python3
"""Kalshi live-quote writer for guest NFL chips (URF: main Sep-27 10:57 directive).

Pulls per-ticker quotes from the public Kalshi market API and writes
slates/nfl_kalshi_quotes.json:

  {"quoted_at": <UTC ISO>, "quotes": {ticker: {"status": str, "yes_bid": int|cents|null, "yes_ask": int|null}}}

The site rewrites a chip label ONLY from this file when it is fresh
(<=10 min old) and the market status is "active"; anything else falls back
to the carded price with its explicit as-of. Stale never wears LIVE.
Fail-closed: any fetch/parse problem = no write; the last-good file stays.
"""
import json, os, sys, urllib.request
from datetime import datetime, timezone

SLATE = 'slates/nfl_chips.json'
OUT = 'slates/nfl_kalshi_quotes.json'
API = 'https://api.elections.kalshi.com/trade-api/v2/markets?tickers=%s&limit=100'


def cents(v):
    """Kalshi *_dollars string ("0.4900") -> cents int (49). 1..100 valid."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f <= 0:
        return None
    c = int(round(f * 100)) if f <= 1.0 else int(round(f))
    return c if 1 <= c <= 100 else None


def main():
    try:
        slate = json.load(open(SLATE))
    except Exception as e:
        print('no slate readable (%s) - nothing to do' % e)
        return 0
    tickers = []
    for leg in slate.get('legs') or []:
        kal = leg.get('kalshi') or {}
        t = kal.get('ticker')
        if isinstance(t, str) and t and t not in tickers:
            tickers.append(t)
    if not tickers:
        # No active slate: only clear an existing non-empty quotes file.
        try:
            old = json.load(open(OUT))
            if not old.get('quotes'):
                print('no tickers, quotes already empty - no write')
                return 0
        except Exception:
            print('no tickers, no quotes file - no write')
            return 0
        payload = {'quoted_at': datetime.now(timezone.utc).isoformat(), 'quotes': {}}
        atomic_write(payload)
        print('cleared quotes (no active slate)')
        return 0

    req = urllib.request.Request(API % ','.join(tickers),
                                 headers={'User-Agent': 'rixpicks-quotes/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print('FAIL-CLOSED: kalshi fetch failed (%s) - keeping last-good file' % e)
        return 1
    markets = data.get('markets')
    if not isinstance(markets, list):
        print('FAIL-CLOSED: unexpected payload - keeping last-good file')
        return 1

    quotes = {}
    for m in markets:
        t = m.get('ticker')
        if not t:
            continue
        quotes[t] = {
            'status': m.get('status'),
            'yes_bid': cents(m.get('yes_bid_dollars')),
            'yes_ask': cents(m.get('yes_ask_dollars')),
            'quoted_at': m.get('updated_time'),
        }
    payload = {'quoted_at': datetime.now(timezone.utc).isoformat(), 'quotes': quotes}
    atomic_write(payload)
    print('quotes written: %d tickers, %d markets -> %s' % (len(tickers), len(quotes), OUT))
    for t in tickers:
        q = quotes.get(t)
        print('  %s %s' % (t, q if q else 'MISSING'))
    return 0


def atomic_write(payload):
    tmp = OUT + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(payload, f, separators=(',', ':'))
        f.write('\n')
    os.replace(tmp, OUT)


if __name__ == '__main__':
    sys.exit(main())
