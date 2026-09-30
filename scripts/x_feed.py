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
import json, os, re, sys, time, urllib.request, urllib.parse, datetime

import x_wall

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
    r'freebie|free picks? on|model.{0,20}(is )?(live|cashed)|free signals?|vip[- ]?[0-9]* ?trades?|take[- ]?profits?|\btp[1-4]\b|stop[- ]?loss|(?:crypto|forex|trading) signals?|bitcoin|\b(?:btc|eth|xrp|doge|pepe|shib)\b|solana|memecoins?|altcoins?|binance|bybit|bitget|kucoin|\bokx\b|\bmexc\b|airdrops?|pump[ -]?fun|long setup|short setup|\b(?:50|100)x\b|\$(?:BTC|ETH|XRP|SOL|DOGE|ADA|PEPE|SHIB)\b', __import__('re').I)


def _payload(p):
    # guard 3+5 full-payload gate: text + author branding + url - a promo carried only in
    # the account name (the Brownstone Bets class) or a shortened link is still denied.
    return ' '.join([p.get('text') or '', str(p.get('author_name') or ''), str(p.get('author_username') or ''), str(p.get('url') or '')])


# feed guard 1 server mirror (Sep 29 zero-pair class): the shared pool admits genuine sports
# posts only - same four-tier test as client isSportsPost (kill list / strong / team /
# acronym-with-context / 2+ weak), byte-identical pattern text to index_v2.js. A poisoned pool
# (wall-recovery backfill pulled 93 percent non-sports spam) burns embed spend and starves
# every downstream gate; junk in the 24h carryover purges here on the next cycle.
NONSPORT_KILL_RE = __import__('re').compile(r'only ?fans|lingerie|\bnudes?\b|nsfw|18\+|spicy content|hookup|escort|sext(ing)?\b|election|ballot|\bpresident\b|congress|senate|democrat|republican|midterms?|campaign rally|polling|immigration|ceasefire|stock tips|nasdaq|s&p 500|passive income|\bfashion\b|runway|\bootd\b|makeup|skincare|weight loss|diet pills|essay (help|service)|homework help', __import__('re').I)
SPORT_ACRO_RE = __import__('re').compile(r'\b(nfl|nba|mlb|nhl|wnba|mls|nwsl|ncaa|cfb|ufc|mma|pga|atp|wta|nascar)\b', __import__('re').I)
SPORT_STRONG_RE = __import__('re').compile(r'\b(formula 1|football|basketball|baseball|hoops|hockey|soccer|tennis|golf|boxing|quarterback|touchdown|pitcher|pitching|home run|homer|goalie|playoffs?|super bowl|stanley cup|world series|march madness|heisman|grand slam|wimbledon|daytona|heavyweight|knockout|innings?|dugout|bullpen|buzzer beater|free throw|field goal|batting|\bpuck\b|rbi|strikeout|power play|penalty kick|slam dunk|fastball|curveball|faceoff|hat trick|slugger|halfcourt)\b', __import__('re').I)
SPORT_TEAMS_RE = __import__('re').compile(r'\b(yankees|red sox|dodgers|cubs|cardinals|braves|astros|mets|phillies|padres|rangers|orioles|blue jays|guardians|tigers|royals|twins|white sox|athletics|angels|mariners|marlins|nationals|pirates|\breds\b|brewers|diamondbacks|d-backs|rockies|lakers|celtics|warriors|knicks|\bnets\b|sixers|76ers|\bbulls\b|bucks|cavaliers|\bcavs\b|mavericks|\bmavs\b|nuggets|\bsuns\b|clippers|grizzlies|\bhawks\b|hornets|pacers|pistons|raptors|wizards|\bspurs\b|\bthunder\b|timberwolves|trail blazers|\bjazz\b|pelicans|rockets|chiefs|eagles|cowboys|packers|\bbears\b|lions|vikings|falcons|saints|buccaneers|\bbucs\b|\brams\b|seahawks|49ers|raiders|chargers|broncos|ravens|bengals|browns|steelers|\bcolts\b|jaguars|texans|titans|dolphins|patriots|commanders|bruins|maple leafs|canadiens|oilers|avalanche|golden knights|\bkraken\b|canucks|flames|predators|blackhawks|red wings|penguins|capitals|flyers|islanders|hurricanes|lightning|senators|sabres|blue jackets|\bgiants\b|\bjets\b|panthers|\bheat\b|timberwolves|\bwolves\b|\bkings\b|\bleafs\b|\bhabs\b|anaheim ducks|winnipeg|buffalo bills|seattle seahawks)\b', __import__('re').I)
SPORT_WEAK_RE = __import__('re').compile(r'\bgames?\b|\bwins?\b|\bloss(es)?\b|\bscored?\b|\btraded?\b|\binjur(y|ed|ies)\b|\bcoach(ed)?\b|\broster\b|\bdraft(ed)?\b|\bseason\b|\bopener\b|\bovertime\b|\bot\b|\bhalftime\b|\bstadium\b|\barena\b|\bcontract\b|\bextension\b|\bsuspension\b|\bejected\b|\brankings?\b|\bmvp\b|\bdebut\b|\bstreak\b|\bcomeback\b|\bupset\b|\brivalry\b|\bchampionship\b|\btournament\b|\bspread\b|\bparlay\b|\bprops\b|\bodds\b|\blineups?\b|\b\d{1,3}\s*[-–]\s*\d{1,3}\b', __import__('re').I)

def _sports_post(p):
    t = _payload(p)
    if NONSPORT_KILL_RE.search(t):
        return False
    # residual-leak fix (9/29, Emmagrace51 hashtag-stuffing + 'tech giants' classes): sports
    # evidence must come from the substantive BODY - author branding, URLs and hashtag tokens
    # never establish relevance, and a bare team word needs a second game signal.
    import re as _re, unicodedata as _ud
    body = _ud.normalize('NFKC', str(p.get('text') or ''))
    body = _re.sub(r'#\w+', ' ', _re.sub(r'https?://\S+', ' ', body))
    if SPORT_STRONG_RE.search(body):
        return True
    teams = len(SPORT_TEAMS_RE.findall(body))
    acro = len(SPORT_ACRO_RE.findall(body))
    weak = len(SPORT_WEAK_RE.findall(body))
    if acro >= 2 and weak == 0:
        return False  # bare-acronym stuffing is spam, not fandom
    return teams >= 2 or (teams >= 1 and acro + weak >= 1) or acro >= 1 or weak >= 2

def _banned(p):
    import re as _re, unicodedata
    t = unicodedata.normalize('NFKC', _payload(p))
    t = _re.sub(r'#\s+', '#', t)  # de-spaced hashtags: '# ad' is still '#ad' (guard 3 promo class)
    if TOUT_RE.search(t) or AD_RE.search(t) or PROMO2_RE.search(t) or _re.search(r'\bFREE (PICKS?|SIGNALS?)\b', t):
        return True
    # sportsbook/operator brands banned at author AND handle (guard 3 Betfair class)
    who = unicodedata.normalize('NFKC', str(p.get('author_name') or '') + ' ' + str(p.get('author_username') or ''))
    who = _re.sub(r'[^A-Za-z0-9]+', ' ', who)  # crypto-handle class: split separators so Cry_Fortress-style handles tokenize
    if _re.search(r'\b(bets|capper|cappers|handicapp|betfair|bet99|draftkings|fanduel|kalshi|betmgm|caesars|bet365|pointsbet|betrivers|unibet|betway|polymarket|sportsbook|cry|crypto|forex|btc|eth|xrp|solana|memecoin|altcoins?|defi|web3|signals)\b', who, _re.I):
        return True
    return not _sports_post(p)  # pool admits genuine sports posts only (feed guard 1 server mirror)
AD_RE = __import__('re').compile(
    r'tickets? (to see|for|available)|[0-9]x tickets|seats? (available|for sale)|get rid of|'
    r'price.{0,12}negotiable|send me a dm|dm if you|selling (my|[0-9])|face value|stubhub|'
    r'vivid ?seats|seatgeek|tickpick|ticketmaster|gametime|brought to you by|listen in now|'
    r'tune in (now|tonight)|happy hour|dine[ -]?in|drink specials?|food specials?|[0-9]{2,3}\.[0-9] ?fm|[0-9]{3,4} ?am\b|get-in (price|as)|best free|top [0-9]+ (player )?props|deposit (bonus|match|offer)|bonus bets?', __import__('re').I)

PROMO2_RE = __import__('re').compile(
    r'#\s*(ad|ads|sponsored|sponsorship)\b|#\w*sale\b|#giveaway\b|follow\s+(us|me|@\w+)\b.{0,40}(to win|to enter|for a chance|giveaway)|(secure|reserve|book)\s+(a\s+|your\s+)table|(arrive|get (there|here)|come)\s+early\b[^.!?]{0,50}(secure|reserve|grab|book)\s+(a\s+|your\s+)?(table|spot|seat)|free picks?\s*(up|here|today|tonight|now|below|thread|incoming|alert|inside|drop)', __import__('re').I)


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
    fail_codes = []
    st = load_state()
    since_id = st.get('since_id')
    newest = since_id
    # One bounded pass per workflow: a 13-minute burst blocked subsequent news
    # completions behind Actions concurrency and delayed publishing the feed.
    # The existing 15-minute workflow cadence owns the next pull.
    successful = 0
    if not queries:
        print('x_feed: no scoped queries; prior feed and timestamp preserved')
        return
    for _pass in range(1):
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
            successful += 1
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
            c = x_wall.http_code(e)
            if c: fail_codes.append(c)
      # end for q
      if not successful:
          # Owner billing/access wall: uniform 402/403 is paid access denied, not an
          # ingest bug. Skip the pull, preserve the frozen pool, and let the chain
          # build the map so matcher verification is not held hostage to billing.
          if x_wall.is_wall(fail_codes):
              x_wall.wall_skip('x_feed pull')
              return
          raise RuntimeError('X ingest stalled: no successful recent-search request; preserving prior feed timestamp and items')
      since_id = newest or since_id
      save_state({'since_id': since_id, 'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')})
      # Merge a completed paid pull into the feed; zero results are valid, zero successful calls are not.
      # cap 50->150 (owner 2:09 coverage push): this script and news_social.py share
      # slates/x_feed.json - a 50-cap here truncated the match pool back down between
      # chain runs and could evict a URF-paired post (1:38 flicker class). Pinned ids
      # (paired/admitted in the current soc_match map) are never evicted.
      # owner 2:49: the match horizon is the past 24 hours - posts older than 24h age out here.
      try:
          prev_doc = json.load(open(OUT))
          prev = prev_doc.get('items', [])
          prev_gen = prev_doc.get('generated_at')
      except Exception:
          prev = []
          prev_gen = None
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
      # X-wall companion (Sep 29): an emptied pool must NOT bump generated_at - the
      # client's rpMapFresh exact-matches x_generated_at, so a fresh stamp on an empty
      # feed re-mismatches the map between rebuilds. Preserve the prior stamp; the
      # identical-empty write is then a no-op for the commit layer too.
      gen = (prev_gen if not merged_items and prev_gen else
             datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'))
      out = {'generated_at': gen,
             'source': 'x_recent_search', 'window': bool(window), 'items': merged_items}
      json.dump(out, open(OUT, 'w'), indent=1)
    print(f'x_feed: {len(items)} new posts, {len(queries[:4])} queries ({len(terms)} slate terms), window={bool(window)} -> {OUT}')

if __name__ == '__main__':
    main()
