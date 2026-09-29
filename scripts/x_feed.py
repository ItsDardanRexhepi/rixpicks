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

TOUT_RE = __import__('re').compile(
    r'discord|telegram|dubclub|patreon|link in bio|dm (me|us) for|vip (picks|plays|access)|'
    r'picks package|premium picks|paywall|subscribe for|promo code|join my|tap in with|'
    r'free (play|pick)s? (today|daily)|lock of the day|guaranteed (winner|play)|'
    r'freebie|free picks? on|model.{0,20}(is )?(live|cashed)', __import__('re').I)


def _payload(p):
    # guard 3+5 full-payload gate: text + author branding + url - a promo carried only in
    # the account name (the Brownstone Bets class) or a shortened link is still denied.
    return ' '.join([p.get('text') or '', str(p.get('author_name') or ''), str(p.get('author_username') or ''), str(p.get('url') or '')])


def _banned(p):
    import re as _re, unicodedata
    t = unicodedata.normalize('NFKC', _payload(p))
    if TOUT_RE.search(t) or AD_RE.search(t):
        return True
    # sportsbook/operator brands banned at author AND handle (guard 3 Betfair class)
    who = unicodedata.normalize('NFKC', str(p.get('author_name') or '') + ' ' + str(p.get('author_username') or ''))
    return bool(_re.search(r'\b(bets|capper|cappers|handicapp|betfair|bet99|draftkings|fanduel|kalshi|betmgm|caesars|bet365|pointsbet|betrivers|unibet|betway|polymarket|sportsbook)\b', who, _re.I))
AD_RE = __import__('re').compile(
    r'tickets? (to see|for|available)|[0-9]x tickets|seats? (available|for sale)|get rid of|'
    r'price.{0,12}negotiable|send me a dm|dm if you|selling (my|[0-9])|face value|stubhub|'
    r'vivid ?seats|seatgeek|tickpick|ticketmaster|gametime|brought to you by|listen in now|'
    r'tune in (now|tonight)|happy hour|dine[ -]?in|drink specials?|food specials?|[0-9]{2,3}\.[0-9] ?fm|[0-9]{3,4} ?am\b|get-in (price|as)|best free|top [0-9]+ (player )?props|deposit (bonus|match|offer)|bonus bets?', __import__('re').I)

def within_24h(ts):
    """owner 2:49 match horizon: the past 24 hours of X conversation is matchable.
    Posts we cannot age are kept (fail-open on missing data, never on a known-old post)."""
    if not ts:
        return True
    try:
        dt = datetime.datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return (datetime.datetime.now(datetime.timezone.utc) - dt) <= datetime.timedelta(hours=24)
    except Exception:
        return True

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
    """True when a slate game is live now or commences within 60 min (drives the 2-min burst).
    Fail-closed on stale input - the burst spends money, so it needs fresh truth:
    live_games.json older than 2h, or a stuck 'in' game (commence >8h ago), is NOT a window.
    (10:47 bug: stale Sep 22/26 tennis stuck at status 'in' opened a false burst window.)"""
    try:
        lg = json.load(open(LIVE_GAMES))
        now = datetime.datetime.now(datetime.timezone.utc)
        try:
            gen = datetime.datetime.fromisoformat(lg.get('generated_at', '').replace('Z', '+00:00'))
            if (now - gen) > datetime.timedelta(hours=2):
                print(f'game_window: live_games.json stale (generated {lg.get("generated_at")}) - no window')
                return False
        except Exception:
            print('game_window: generated_at unreadable - no window')
            return False
        for league in lg.get('leagues', []):
            for g in league.get('games', []):
                try:
                    ct = datetime.datetime.strptime(g.get('commence', ''), '%Y-%m-%dT%H:%MZ').replace(tzinfo=datetime.timezone.utc)
                except Exception:
                    continue
                if abs((ct - now).total_seconds()) > GAME_WINDOW_H * 3600:
                    continue
                if g.get('status') == 'in' and ct >= now - datetime.timedelta(hours=8):
                    return True
                if g.get('status') == 'pre' and datetime.timedelta(0) <= (ct - now) <= datetime.timedelta(minutes=60):
                    return True
    except Exception:
        pass
    # mirrored time-bounded fallback (same expiry as slate_terms): MNF tonight while the
    # census chain lacks NFL - 4:15-9:30 PM PT Sep 28 covers commence-60min through game end.
    now_pt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-7)))
    if now_pt.date() == datetime.date(2026, 9, 28):
        mins = now_pt.hour * 60 + now_pt.minute
        if 16 * 60 + 15 <= mins <= 21 * 60 + 30:
            return True
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
        queries = [f'({ors}) (injury OR inactive OR scratch OR lineup OR ruled out) lang:en -is:retweet -is:reply']
    else:
        queries = [f'"{t}" (injury OR inactive OR scratch OR lineup OR ruled out) lang:en -is:retweet -is:reply'
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
      # merge this pass into the feed file so the site sees posts mid-burst.
      # cap 50->150 (owner 2:09 coverage push): this script and news_social.py share
      # slates/x_feed.json - a 50-cap here truncated the match pool back down between
      # chain runs and could evict a URF-paired post (1:38 flicker class). Pinned ids
      # (paired/admitted in the current soc_match map) are never evicted.
      # owner 2:49: the match horizon is the past 24 hours - posts older than 24h age out here.
      try:
          prev = json.load(open(OUT)).get('items', [])
      except Exception:
          prev = []
      # owner 1:39 (QA audit 2): tout/sales pitches must never enter the shared pool from
      # THIS path either - news_social.py already filters its own pull; same regex, same rule.
      items = [pp for pp in items if not _banned(pp)]
      # owner 5:28 default-deny is STRUCTURAL: the 24h carryover (prev) passes the same gate -
      # a promotional post can never persist in the pool, so no downstream stage can pair or render one.
      prev = [pp for pp in prev if not _banned(pp)]
      merged = {str(p.get('id')): p for p in (items + prev) if p.get('id')}
      merged_items = sorted(merged.values(), key=lambda p: str(p.get('created_at', '')), reverse=True)
      merged_items = [pp for pp in merged_items if within_24h(pp.get('created_at'))]
      try:
          mm = json.load(open('slates/soc_match.json'))
          keep_ids = {str(v['post_id']) for v in (mm.get('pairs') or {}).values() if (v or {}).get('post_id')}
          keep_ids |= {str(e.get('post_id')) for lst in (mm.get('more') or {}).values() for e in (lst or [])}
          keep_ids |= {str(x) for x in (mm.get('admit') or [])}
      except Exception:
          keep_ids = set()
      pinned = [pp for pp in merged_items if str(pp.get('id')) in keep_ids]
      rest = [pp for pp in merged_items if str(pp.get('id')) not in keep_ids]
      merged_items = (pinned + rest)[:150]
      out = {'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
             'source': 'x_recent_search', 'window': bool(window), 'items': merged_items}
      json.dump(out, open(OUT, 'w'), indent=1)
      if window and time.time() < deadline:
          print(f'burst pass: {len(items)} new, feed carries {len(merged_items)}; next pull in 120s')
          time.sleep(120)
    print(f'x_feed: {len(items)} new posts, {len(queries[:4])} queries ({len(terms)} slate terms), window={bool(window)} -> {OUT}')

if __name__ == '__main__':
    main()
