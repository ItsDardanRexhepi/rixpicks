#!/usr/bin/env python3
"""X API feed for the SENSE stage (main 9:25 handoff from analysis; spec engine/x_feed_spec.md).

Modes:
  verify  - GET /2/users/by/username/XDevelopers (app-only bearer compatible); 200 = live token + read access.
  pull    - recent-search on slate-relevant queries (injury/scratch/lineup + watched teams),
            writes slates/x_feed.json (consumer: Home news section + news_watch + prediction loop).

BURN LEDGER: every request appends {ts, endpoint, query, results} to slates/x_burn.jsonl and the
run prints cumulative count + estimated spend vs the $9.04 credit balance he reported 9/27.
Estimates are UNVERIFIED until a post-midnight dashboard check (measured rates below);
estimated remaining < $2.00 => ALERT line + exit 1 (fail loud = balance-watch signal to main).

Item contract (Home agent 9:38): each item carries author_username/author_name/url from the
search response itself (expansions=author_id - same single request, no extra burn). Consumers
must render text as plain escaped text (untrusted third-party posts, labeled X-sourced - these
are PUBLIC posts matching slate queries, never the user's own posts).
"""
import json, os, sys, time, urllib.request, urllib.parse, datetime

BASE = 'https://api.x.com/2'
TOKEN = os.environ.get('X_BEARER_TOKEN', '')
LEDGER = 'slates/x_burn.jsonl'
OUT = 'slates/x_feed.json'
LIVE_GAMES = 'slates/live_games.json'
STATE = 'slates/x_feed_state.json'
CREDITS = 9.04          # his reported balance 9/27 9:25 PM PT
ALERT_FLOOR = 2.00      # main 9:25 balance-watch: alert main before free credits run out
# MEASURED pricing (X console, Sep 28 9:22 AM PT: 190 events / $0.97 / 29 requests over 30d):
COST_PER_REQUEST = 0.033
COST_PER_POST = 0.005
MAX_RESULTS = 10        # tight per handoff
GAME_WINDOW_H = 36      # slate-relevant = commences within +/-36h

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
    print(f'BURN: {n} requests / {posts} posts | est spend ${est:.2f} (measured rates) | est remaining ${remaining:.2f} of ${CREDITS:.2f}')
    if remaining < ALERT_FLOOR:
        print(f'ALERT: estimated remaining ${remaining:.2f} < ${ALERT_FLOOR:.2f} floor - FREE CREDIT EXHAUSTED, meter now billing (owner 10:31: alert-only, no hard stop) - relay to main with realized burn')

def slate_terms():
    """Teams/players from slates/live_games.json (in-repo, refreshed by the census chain).
    Only games commencing within +/-36h count; 'post'/final games are excluded.
    GHA has no /tmp/slate_day.json (that path was analysis-sandbox-only) - this is the fix."""
    terms = set()
    try:
        lg = json.load(open(LIVE_GAMES))
        now = datetime.datetime.now(datetime.timezone.utc)
        for league in lg.get('leagues', []):
            for g in league.get('games', []):
                try:
                    ct = datetime.datetime.strptime(g.get('commence', ''), '%Y-%m-%dT%H:%MZ').replace(tzinfo=datetime.timezone.utc)
                except Exception:
                    continue
                if abs((ct - now).total_seconds()) > GAME_WINDOW_H * 3600:
                    continue
                if g.get('status') not in ('pre', 'in'):
                    continue
                for part in str(g.get('matchup', '')).split(' @ '):
                    part = part.strip()
                    if part:
                        terms.add(part)
    except Exception as e:
        print(f'slate_terms: {LIVE_GAMES} unreadable ({e}) - no queries this cycle')
    # time-bounded fallback: MNF tonight (Eagles @ Bears 5:15 PM PT) while the census chain
    # catches up on NFL; expires after 2026-09-29 PT. No standing hardcoded teams.
    today_pt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-7))).date()
    if not terms and today_pt <= datetime.date(2026, 9, 29):
        terms = {'Philadelphia Eagles', 'Chicago Bears'}
    return sorted(terms)


def game_window():
    """True when a slate game is live now or commences within 60 min (drives the 2-min burst)."""
    try:
        lg = json.load(open(LIVE_GAMES))
        now = datetime.datetime.now(datetime.timezone.utc)
        for league in lg.get('leagues', []):
            for g in league.get('games', []):
                if g.get('status') == 'in':
                    return True
                try:
                    ct = datetime.datetime.strptime(g.get('commence', ''), '%Y-%m-%dT%H:%MZ').replace(tzinfo=datetime.timezone.utc)
                except Exception:
                    continue
                if g.get('status') == 'pre' and datetime.timedelta(0) <= (ct - now) <= datetime.timedelta(minutes=60):
                    return True
    except Exception:
        pass
    return False

def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}

def save_state(st):
    json.dump(st, open(STATE, 'w'), indent=1)

def main():
    if not TOKEN:
        print('X_BEARER_TOKEN secret not set - feed dormant')
        return
    mode = sys.argv[1] if len(sys.argv) > 1 else 'pull'
    if mode == 'verify':
        try:
            status, body = req('/users/by/username/XDevelopers')
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:300]
            print(f'verify: HTTP {e.code} body: {detail}')
            log_burn('/users/by/username', 'verify', 0)
            sys.exit(1)
        print(f'verify: HTTP {status}', json.dumps(body.get('data', {}))[:200])
        log_burn('/users/by/username', 'verify', 0)
        return
    # pull: slate-relevant queries from live_games.json (injury/scratch/lineup + slate teams)
    terms = slate_terms()
    # owner 10:22: real-time pulls, SCOPED to relevant info only. Game windows (game live or
    # starting within 60 min) switch to a 2-min burst loop with ONE combined query; off-window
    # stays per-team on the 15-min cron. Owner 10:31: $2.00 floor is ALERT-ONLY, meter runs.
    window = game_window()
    if window and terms:
        ors = ' OR '.join(f'"{t}"' for t in terms[:4])
        queries = [f'({ors}) (injury OR inactive OR scratch OR lineup OR ruled out) lang:en -is:retweet']
    else:
        queries = [f'"{t}" (injury OR inactive OR scratch OR lineup OR ruled out) lang:en -is:retweet'
                   for t in terms]
    items = []
    seen = set()
    st = load_state()
    since_id = st.get('since_id')
    newest = since_id
    deadline = time.time() + (13 * 60 if window else 0)  # burst: keep pulling inside one run
    first_pass = True
    while first_pass or (window and time.time() < deadline):
      first_pass = False
      for q in queries[:4]:  # hard cap per cycle: burn discipline
        try:
            params = {'query': q, 'max_results': MAX_RESULTS,
                      'tweet.fields': 'created_at,author_id,public_metrics',
                      'expansions': 'author_id', 'user.fields': 'username,name'}
            if since_id:
                params['since_id'] = since_id  # incremental: only NEW posts billed
            status, body = req('/tweets/search/recent', params)
            data = body.get('data') or []
            users = {u.get('id'): u for u in ((body.get('includes') or {}).get('users') or [])}
            log_burn('/tweets/search/recent', q, len(data))
            for tw in data:
                tid = tw.get('id')
                if not tid or tid in seen:
                    continue
                seen.add(tid)
                u = users.get(tw.get('author_id')) or {}
                uname = u.get('username')
                items.append({'query': q, 'id': tid, 'created_at': tw.get('created_at'),
                              'text': tw.get('text'),
                              'author_username': uname,
                              'author_name': u.get('name'),
                              'url': f'https://x.com/{uname}/status/{tid}' if uname else None})
            meta = body.get('meta') or {}
            if meta.get('newest_id'):
                newest = meta['newest_id']
        except Exception as e:
            print(f'pull FAIL ({q[:40]}...): {e}')
      # end for q
      since_id = newest or since_id
      save_state({'since_id': since_id, 'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')})
      # merge this pass into the feed file (newest first, cap 50) so the site sees posts mid-burst
      try:
          prev = json.load(open(OUT)).get('items', [])
      except Exception:
          prev = []
      merged = {str(p.get('id')): p for p in (items + prev) if p.get('id')}
      merged_items = sorted(merged.values(), key=lambda p: str(p.get('created_at', '')), reverse=True)[:50]
      out = {'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
             'source': 'x_recent_search', 'window': bool(window), 'items': merged_items}
      json.dump(out, open(OUT, 'w'), indent=1)
      if window and time.time() < deadline:
          print(f'burst pass: {len(items)} new, feed carries {len(merged_items)}; next pull in 120s')
          time.sleep(120)
    print(f'x_feed: {len(items)} new posts, {len(queries[:4])} queries ({len(terms)} slate terms), window={bool(window)} -> {OUT}')

if __name__ == '__main__':
    main()
