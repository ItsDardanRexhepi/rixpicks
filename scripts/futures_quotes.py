"""Futures live-quote feed - Kalshi series-level pull (8 requests, one per series).
No CORS header on api.elections.kalshi.com -> NOT pullable client-side from the site;
pull at GHA build/refresh time (GitHub egress IPs, separate rate bucket) and write quotes
inline into futures.json. Worker-IP 429 risk is on MY workspace egress; GHA is clean.
Usage: python3 futures_quotes.py <futures.json> [--write]
"""
import json, sys, time, urllib.request, datetime

# carded market -> (kalshi series, ticker suffix abbr) ; abbr = Kalshi team code
MAP = {
 'Super Bowl LXI Champion': ('KXSB', {'sf':'SF','kc':'KC','sea':'SEA'}),
 'AFC West Champion':       ('KXNFLAFCWEST', {'kc':'KC'}),
 'NFC West Champion':       ('KXNFLNFCWEST', {'sf':'SF'}),
 'NFC East Champion':       ('KXNFLNFCEAST', {'phi':'PHI'}),
 'NFC North Champion':      ('KXNFLNFCNORTH',{'min':'MIN'}),
 'AFC Champion':            ('KXNFLAFCCHAMP',{'buf':'BUF'}),
 'NFC Champion':            ('KXNFLNFCCHAMP',{'sf':'SF'}),
 'WNBA Championship':       ('KXWNBA',      {'min':'MIN'}),
}
SEASON = {'KXSB':'27','KXNFLAFCWEST':'27','KXNFLNFCWEST':'27','KXNFLNFCEAST':'27',
          'KXNFLNFCNORTH':'27','KXNFLAFCCHAMP':'27','KXNFLNFCCHAMP':'27','KXWNBA':'26'}

def get(url):
    req = urllib.request.Request(url, headers={'User-Agent':'rix/1.0'})
    return json.load(urllib.request.urlopen(req, timeout=20))

def pull_series(series):
    out = {}
    cursor = None
    for _ in range(4):
        url = f"https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker={series}&limit=200"
        if cursor: url += f"&cursor={cursor}"
        d = get(url)
        for m in d.get('markets', []):
            out[m['ticker']] = m
        cursor = d.get('cursor')
        if not cursor: break
        time.sleep(0.3)
    return out

def main(path, write=False):
    rows = json.load(open(path))
    cache = {}
    for r in rows:
        mkt, abbr = r.get('market'), r.get('abbr')
        ent = MAP.get(mkt)
        if not ent or abbr not in ent[1]:
            r['kalshi_quote'] = None
            print(f"UNMAPPED {mkt}/{abbr}", file=sys.stderr); continue
        series, teammap = ent
        ticker = f"{series}-{SEASON[series]}-{teammap[abbr]}"
        if series not in cache:
            try: cache[series] = pull_series(series)
            except Exception as ex:
                print(f"SERIES ERR {series}: {ex}", file=sys.stderr); cache[series] = {}
            time.sleep(0.4)
        m = cache[series].get(ticker)
        if not m or m.get('status') != 'active':
            r['kalshi_quote'] = None
            print(f"INACTIVE/MISSING {ticker}", file=sys.stderr); continue
        bid = m.get('yes_bid_dollars'); ask = m.get('yes_ask_dollars')
        mid = round((float(bid)+float(ask))*50) if bid and ask else None  # cents
        r['kalshi_quote'] = {'ticker': ticker, 'bid_c': round(float(bid)*100) if bid else None,
                             'ask_c': round(float(ask)*100) if ask else None, 'mid_c': mid,
                             'status': m['status'], 'quoted_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')}
        print(f"OK {ticker}: {r['kalshi_quote']['bid_c']}/{r['kalshi_quote']['ask_c']} mid {mid}c")
    if write:
        json.dump(rows, open(path,'w'), indent=1)

if __name__ == '__main__':
    main(sys.argv[1], '--write' in sys.argv)
