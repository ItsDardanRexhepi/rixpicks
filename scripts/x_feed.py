#!/usr/bin/env python3
"""X API feed for the SENSE stage (main 9:25 handoff from analysis; spec engine/x_feed_spec.md).

Modes:
  verify  - GET /2/users/me; 200 = live token. Prints the @handle.
  pull    - recent-search on slate-relevant queries (injury/scratch/lineup + watched teams),
            writes slates/x_feed.json (consumer: news_watch + prediction loop via SENSE spine).

BURN LEDGER: every request appends {ts, endpoint, query, results} to slates/x_burn.jsonl and the
run prints cumulative count + estimated spend vs the $9.04 credit balance he reported 9/27.
Estimates are UNVERIFIED until a post-midnight dashboard check (per-use pricing assumed below);
estimated remaining < $1.50 => ALERT line (fail loud, never silent overspend).
"""
import json, os, sys, urllib.request, urllib.parse, datetime

BASE = 'https://api.x.com/2'
TOKEN = os.environ.get('X_BEARER_TOKEN', '')
LEDGER = 'slates/x_burn.jsonl'
OUT = 'slates/x_feed.json'
CREDITS = 9.04          # his reported balance 9/27 9:25 PM PT
ALERT_FLOOR = 1.50      # alert when estimated remaining drops below this
# ASSUMED unverified per-use pricing (post-midnight dashboard check owns the true rates):
COST_PER_REQUEST = 0.01
COST_PER_POST = 0.005
MAX_RESULTS = 10        # tight per handoff

def req(path, params=None):
    url = BASE + path + (('?' + urllib.parse.urlencode(params)) if params else '')
    r = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + TOKEN,
                                             'User-Agent': 'rixpicks-x-feed/1.0'})
    with urllib.request.urlopen(r, timeout=30) as resp:
        return resp.status, json.load(resp)

def log_burn(endpoint, query, results):
    now = datetime.datetime.now(datetime.timezone.utc)
    row = {'ts': now.isoformat(timespec='seconds'), 'endpoint': endpoint,
           'query': query, 'results': results}
    with open(LEDGER, 'a') as f:
        f.write(json.dumps(row) + '\n')
    n = 0; posts = 0
    try:
        for line in open(LEDGER):
            if line.strip():
                n += 1
                posts += json.loads(line).get('results', 0)
    except FileNotFoundError:
        pass
    est = n * COST_PER_REQUEST + posts * COST_PER_POST
    remaining = CREDITS - est
    print(f'BURN: {n} requests / {posts} posts | est spend ${est:.2f} (ASSUMED rates, unverified) | est remaining ${remaining:.2f} of ${CREDITS:.2f}')
    if remaining < ALERT_FLOOR:
        print(f'ALERT: estimated remaining ${remaining:.2f} < ${ALERT_FLOOR:.2f} floor - STOP WIDENING, dashboard check due')

def main():
    if not TOKEN:
        print('X_BEARER_TOKEN secret not set - feed dormant (fill pending midnight browser window)')
        return
    mode = sys.argv[1] if len(sys.argv) > 1 else 'pull'
    if mode == 'verify':
        status, body = req('/users/me')
        print(f'verify: HTTP {status}', json.dumps(body.get('data', {}))[:200])
        log_burn('/users/me', 'verify', 0)
        return
    # pull: slate-relevant queries from tomorrow's slate + standing watch
    queries = []
    try:
        slate = json.load(open('/tmp/slate_day.json')) if os.path.exists('/tmp/slate_day.json') else []
    except Exception:
        slate = []
    # MNF + any live/imminent slate teams
    teams = set()
    for r in slate if isinstance(slate, list) else []:
        for k in ('away', 'home'):
            if r.get(k): teams.add(r[k])
    if not teams:
        teams = {'Philadelphia Eagles', 'Chicago Bears'}  # MNF fallback, current slate
    for t in sorted(teams):
        queries.append(f'"{t}" (injury OR inactive OR scratch OR lineup OR ruled out) lang:en -is:retweet')
    items = []
    for q in queries[:4]:  # hard cap per cycle: burn discipline, 1 pull set/15min
        try:
            status, body = req('/tweets/search/recent', {
                'query': q, 'max_results': MAX_RESULTS,
                'tweet.fields': 'created_at,author_id,public_metrics'})
            data = body.get('data') or []
            log_burn('/tweets/search/recent', q, len(data))
            for tw in data:
                items.append({'query': q, 'id': tw.get('id'), 'created_at': tw.get('created_at'),
                              'text': tw.get('text')})
        except Exception as e:
            print(f'pull FAIL ({q[:40]}...): {e}')
    out = {'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
           'source': 'x_recent_search', 'items': items}
    json.dump(out, open(OUT, 'w'), indent=1)
    print(f'x_feed: {len(items)} posts across {len(queries[:4])} queries -> {OUT}')

if __name__ == '__main__':
    main()
