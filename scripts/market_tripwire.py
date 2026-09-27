"""Market tripwire: Kalshi futures/outright markets that moved 3c+ in one cycle.
Basis = orderbook-top mid (yes_bid/yes_ask), never last_price. No bid/ask = NO QUOTE, skipped.
State: /home/sandbox/rps_tmp/kb/tripwire_state.json {ticker: mid_c}
Usage: python3 market_tripwire.py --report
"""
import json, os, sys, time, urllib.request

SERIES = ['KXSB','KXNFLAFCWEST','KXNFLNFCWEST','KXNFLNFCEAST','KXNFLNFCNORTH',
          'KXNFLAFCCHAMP','KXNFLNFCCHAMP','KXWNBA','KXNFLMVP','KXNFLROY']
STATE = '/home/sandbox/rps_tmp/kb/tripwire_state.json'
TRIP_C = 3

def get(url):
    req = urllib.request.Request(url, headers={'User-Agent':'rix/1.0'})
    return json.load(urllib.request.urlopen(req, timeout=20))

def pull_series(series):
    out, cursor = {}, None
    for _ in range(5):
        url = f"https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker={series}&status=open&limit=200"
        if cursor: url += f"&cursor={cursor}"
        d = get(url)
        for m in d.get('markets', []):
            out[m['ticker']] = m
        cursor = d.get('cursor')
        if not cursor: break
        time.sleep(0.3)
    return out

def main():
    report = '--report' in sys.argv
    prev = {}
    if os.path.exists(STATE):
        try: prev = json.load(open(STATE))
        except Exception: prev = {}
    now, errors = {}, []
    for s in SERIES:
        try: mkts = pull_series(s)
        except Exception as ex:
            errors.append(f"{s}: {ex}"); time.sleep(1); continue
        for t, m in mkts.items():
            if m.get('status') != 'active': continue
            b, a = m.get('yes_bid_dollars'), m.get('yes_ask_dollars')
            if not b or not a: continue  # thin book = NO QUOTE
            now[t] = round((float(b)+float(a))*50)
        time.sleep(0.4)
    trips = []
    if prev:
        for t, mid in now.items():
            if t in prev and abs(mid - prev[t]) >= TRIP_C:
                trips.append((t, prev[t], mid))
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(now, open(STATE,'w'))
    if report:
        if errors:
            for e in errors: print(f"TRIPWIRE SERIES ERR {e}")
        if not prev:
            print(f"BASELINE seeded: {len(now)} active tickers across {len(SERIES)} series")
        elif trips:
            for t, old, new in sorted(trips, key=lambda x: -abs(x[2]-x[1])):
                print(f"TRIP {t}: {old}c -> {new}c ({'+' if new>old else ''}{new-old}c)")
        else:
            print(f"no trips ({len(now)} tickers checked)")

if __name__ == '__main__':
    main()
