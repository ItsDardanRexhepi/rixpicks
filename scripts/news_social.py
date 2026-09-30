#!/usr/bin/env python3
"""news_social.py - news-driven social pull (owner 1:09/1:11/1:15 PT: the X API is the tap the
algo uses to pull the social side; ONLY URF-verified matched stories render; UltRix runs
sentient integration trials until it finds a working path itself; it never accepts no - it
routes around failures: alternate queries, alternate phrasings, exhaustive rotation; the one
boundary is zero-mismatch).

Modes:
  trial - run query strategies S1..S4 against current news, log every attempt + result to
          slates/soc_trials.json (what it tried, what failed, what succeeded). Posts pulled
          merge into x_feed.json tagged via=strategy so soc_match gating attributes pairs
          back to the strategy that surfaced them. A strategy WINS when pairs it surfaced
          pass the full six-gate loop (evaluated on the next soc_match build; winner read
          back from soc_match.json verdicts).
  pull  - standing mode: winning strategy (or S3 default before the first trial verdict),
          freshest headlines only, per-query since_id, merges into x_feed.json.

Burn discipline: same ledger + measured rates as x_feed.py; NEWS_QUERIES_PER_RUN hard cap;
per-query since_id so only NEW posts bill. Every failure rotates (route-around), never aborts
the run: simplify -> reorder -> league fallback. Route log written to the trial file.
"""
import json, os, re, sys, time, urllib.request, urllib.parse, datetime

import x_wall

BASE = 'https://api.x.com/2'
TOKEN = os.environ.get('X_BEARER_TOKEN', '')
LEDGER = 'slates/x_burn.jsonl'
OUT = 'slates/x_feed.json'
NEWS = 'slates/news.json'
STATE = 'slates/x_feed_state.json'
TRIALS = 'slates/soc_trials.json'
CREDITS = 9.04
ALERT_FLOOR = 2.00
COST_PER_REQUEST = 0.033
COST_PER_POST = 0.005
MAX_RESULTS = 100      # 10->100 (owner 2:09/2:49 coverage): same request count, up to 10x posts per query - burn is per REQUEST
NEWS_QUERIES_PER_RUN = 18      # hard cap per run (burn discipline; 12->18 owner 2:09 coverage push)
MAX_HEADLINE_AGE_H = 18       # only fresh headlines drive pulls

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
ROUTE_ATTEMPTS = 3            # route-around rotations per headline before conceding

STOP = set('the a an and or of to in on for with after before over under from at by is are was were be been being has have had will would could should may might can do does did not no yes it its his her their our your my we you they he she them us this that these those as if than then so such more most other some any each few all both few own same into about against between through during without within new just says report reports rumored rumors per sources source watch latest breaking video photos monday tuesday wednesday thursday friday saturday sunday january february march april may june july august september october november december silver squarely sterling golden bronze major minor prime central northern southern eastern western upper lower inner outer daily weekly nightly morning afternoon evening midnight noon night tonight tomorrow yesterday'.split())

def req(path, params=None):
    url = BASE + path + (('?' + urllib.parse.urlencode(params)) if params else '')
    r = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + TOKEN,
                                             'User-Agent': 'rixpicks-news-social/1.0'})
    with urllib.request.urlopen(r, timeout=30) as resp:
        return resp.status, json.load(resp)

def log_burn(endpoint, query, results):
    now = datetime.datetime.now(datetime.timezone.utc)
    with open(LEDGER, 'a') as f:
        f.write(json.dumps({'ts': now.isoformat(timespec='seconds'), 'endpoint': endpoint,
                            'query': query, 'results': results}) + '\n')
    n = posts = 0
    try:
        for line in open(LEDGER):
            if line.strip():
                n += 1; posts += json.loads(line).get('results', 0)
    except FileNotFoundError:
        pass
    est = n * COST_PER_REQUEST + posts * COST_PER_POST
    remaining = CREDITS - est
    print(f'BURN: {n} requests / {posts} posts | est spend ${est:.2f} | est remaining ${remaining:.2f}')
    if remaining < ALERT_FLOOR:
        print(f'ALERT: est remaining ${remaining:.2f} < ${ALERT_FLOOR:.2f} floor - relay to main')

def headline_key(it):
    return (it.get('link') or '') or it.get('headline', '')

def entities(headline):
    """Capitalized multi-word sequences (players/teams/events), stopword-filtered."""
    toks = re.findall(r"[A-Z][a-zA-Z'.-]+(?:\s+(?:[A-Z][a-zA-Z'.-]+|of|the|de|van|von))*", headline or '')
    out = []
    for t in toks:
        t = t.strip()
        if not t or t.lower() in STOP or len(t) < 3:
            continue
        words = [w for w in t.split() if w.lower() not in STOP]
        if words:
            out.append(' '.join(words))
    seen = set(); ded = []
    for e in out:
        if e.lower() not in seen:
            seen.add(e.lower()); ded.append(e)
    return ded[:4]

TOPIC_KW = {'trade':'trade','traded':'trade','injury':'injury','injured':'injury','ruled out':'injury',
            'sign':'contract','extension':'contract','contract':'contract','waiver':'waiver wire',
            'ranking':'rankings','ranked':'rankings','prediction':'prediction','predictions':'prediction',
            'playoff':'playoffs','playoffs':'playoffs','suspended':'suspension','ejected':'ejection',
            'fired':'firing','hire':'hiring','retire':'retirement','record':'record','win':'win',
            'loss':'loss','upset':'upset','draft':'draft','mvp':'MVP','starter':'starting lineup',
            'bench':'benched','quarterback':'QB','touchdown':'touchdown'}

def topic_kw(headline):
    h = (headline or '').lower()
    for k, v in TOPIC_KW.items():
        if k in h:
            return v
    return ''

def phrase(headline):
    """3-content-word quoted phrase, distinctive middle of the headline."""
    words = [w for w in re.findall(r"[A-Za-z0-9']+", headline or '') if w.lower() not in STOP and len(w) > 2]
    if len(words) >= 3:
        return ' '.join(words[:3])
    return ' '.join(words) if words else ''

def build_queries(it, strategy):
    h = it.get('headline', '')
    ents = entities(h)
    kw = topic_kw(h)
    ph = phrase(h)
    qs = []
    if strategy == 'S1' and ph:
        qs.append(f'"{ph}" lang:en -is:retweet -is:reply')
    elif strategy == 'S2' and ents and kw:
        ors = ' OR '.join(f'"{e}"' for e in ents[:2])
        qs.append(f'({ors}) ({kw}) lang:en -is:retweet -is:reply')
    elif strategy == 'S3' and ents:
        ors = ' OR '.join(f'"{e}"' for e in ents[:3])
        qs.append(f'({ors}) lang:en -is:retweet -is:reply')
    elif strategy == 'S4':
        league = it.get('league') or it.get('sport') or ''
        if league:
            base = (league + ' ' + kw).strip()
        elif ents:
            base = (ents[0] + ' ' + kw).strip()
        else:
            base = ''
        if base:
            qs.append(f'"{base}" lang:en -is:retweet -is:reply')
    return [q for q in qs if len(q) <= 500]

def route_arounds(it, strategy):
    """Never accepts no: ordered alternates when the primary query fails or returns nothing."""
    h = it.get('headline', '')
    ents = entities(h)
    ph = phrase(h)
    alts = []
    if strategy != 'S3' and ents:
        alts.append(('S3-rotate', f'({" OR ".join(chr(34)+e+chr(34) for e in ents[:3])}) lang:en -is:retweet -is:reply'))
    if ph:
        words = ph.split()
        if len(words) >= 2:
            alts.append(('loose-phrase', f'"{words[0]} {words[-1]}" lang:en -is:retweet -is:reply'))
    if len(ents) >= 2:
        alts.append(('swap-order', f'("{ents[1]}" OR "{ents[0]}") lang:en -is:retweet -is:reply'))
    if ents:
        alts.append(('bare-entity', f'"{ents[0]}" lang:en -is:retweet -is:reply'))
    return [(tag, q) for tag, q in alts if len(q) <= 500]

def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}

def save_state(st):
    json.dump(st, open(STATE, 'w'), indent=1)

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


COMMERCIAL_CTA_RE = __import__('re').compile(
    r'\bjoin up\b|link in\b[^.!?\n]{0,12}\bbio\b|\bfree ?(?:play|pick)s?\b|\bpotd\b|\bplay of the day\b|boosted (?:odds|parlays?)|@playbook\b', __import__('re').I)
COMMERCIAL_FREE_RE = __import__('re').compile(
    r'\b(?:mlb|nfl|nba|nhl|wnba|cfb|ncaa|ufc|mls)\b[^.!?\n]{0,16}\bfree(?![- ](?:agent|agency|throws?|kicks?|transfer))\b|\bfree(?![- ](?:agent|agency|throws?|kicks?|transfer))\b[^.!?\n]{0,16}\b(?:mlb|nfl|nba|nhl|wnba|cfb|ncaa|ufc|mls)\b', __import__('re').I)
COMMERCIAL_ODDS_RE = __import__('re').compile(r'[-+]\d{3}\b')


COMMERCIAL_TAG_RE = __import__('re').compile(
    r'#\s*(?:gamblingtwitter|gamblingx|prizepicks|freepicks?|sportsbetting|draftkings|fanduel|betmgm|bettingtips?|gambling)\b', __import__('re').I)


def _commercial(p):
    """commercial-publishability predicate (promo-sentinel 9/29 7:07 class): betting tout /
    acquisition posts must never enter the shared pool. Text-plus-author CTA rules
    (free-play/POTD, join-up, link-in-bio variants, boosted-odds, @Playbook mentions) and a
    destination rule (acquisition gambling hashtags + an outbound link in the post text).
    Fail-closed: a genuine post wrongly rejected is a blank, never a wrong render.
    Mirrors: index_v2.js isPublishablePost (RP_COMM_CTA/RP_COMM_TAG) and the news_social.py
    copy - byte-identical pattern text across all three."""
    import re as _re, unicodedata as _ud
    t = _ud.normalize('NFKC', _payload(p))
    t = _re.sub(r'#\s+', '#', t)
    if COMMERCIAL_CTA_RE.search(t):
        return True
    if COMMERCIAL_TAG_RE.search(t) and _re.search(r'https?://', str(p.get('text') or '')):
        return True
    # free betting-sheet class (sentinel 9/29 7:38: "Today's Early MLB Free" + priced lines +
    # acquisition links, no pick/play wording): sport-near-free AND >=2 concrete prices AND an
    # outbound link. Ordinary "free" stays publishable: free-agent/free-throw/free-kick/
    # free-transfer are whitelisted, and commentary without a priced sheet fails the odds leg.
    txt = str(p.get('text') or '')
    if (COMMERCIAL_FREE_RE.search(t) and len(COMMERCIAL_ODDS_RE.findall(txt)) >= 2
            and _re.search(r'https?://', txt)):
        return True
    return False

def _banned(p):
    import re as _re, unicodedata
    t = unicodedata.normalize('NFKC', _payload(p))
    t = _re.sub(r'#\s+', '#', t)  # de-spaced hashtags: '# ad' is still '#ad' (guard 3 promo class)
    if TOUT_RE.search(t) or AD_RE.search(t) or PROMO2_RE.search(t) or _re.search(r'\bFREE (PICKS?|SIGNALS?)\b', t):
        return True
    if _commercial(p):
        return True  # promo-sentinel 9/29 class: tout/acquisition posts never enter the pool
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


def quality_ok(p):
    """anti-junk floor (main 1:29: random replies / low-content posts must not drive anything):
    queries already exclude replies server-side; here, a post needs real engagement OR
    substantive text. public_metrics ride the pull response (same request, no extra burn)."""
    # owner 1:39 + 5:27/5:28: NO touts/selling-access/ads/promos on the feed, ever -
    # default deny at intake; the only exception path is his explicit per-item approval
    if _banned(p):
        return False
    m = p.get('public_metrics') or {}
    eng = sum(int(m.get(k) or 0) for k in ('like_count', 'retweet_count', 'reply_count', 'quote_count'))
    return eng >= 2 or len((p.get('text') or '')) >= 100

def merge_feed(new_items):
    dropped = [p for p in new_items if not quality_ok(p)]
    if dropped:
        print(f'quality floor: dropped {len(dropped)} low-engagement/short posts')
    new_items = [p for p in new_items if quality_ok(p)]
    try:
        prev_doc = json.load(open(OUT))
        prev = prev_doc.get('items', [])
    except Exception:
        prev = []
        prev_gen = None
    else:
        prev_gen = prev_doc.get('generated_at')
    # owner 5:28 structural default-deny: carryover items pass the same gate (see x_feed.py)
    prev = [pp for pp in prev if not _banned(pp)]
    merged = {str(p.get('id')): p for p in (new_items + prev) if p.get('id')}
    items = sorted(merged.values(), key=lambda p: str(p.get('created_at', '')), reverse=True)
    # owner 2:49: the match horizon is the past 24 hours - posts older than 24h age out of the pool
    items = [pp for pp in items if within_24h(pp.get('created_at'))]
    # pair-flicker fix (1:38 regression): the 50-cap evicted a post holding a verified pair,
    # regressing the served map to 0 pairs. Posts the matcher has paired or admitted are
    # preserved across merges regardless of cap.
    try:
        mm = json.load(open('slates/soc_match.json'))
        keep_ids = {str(v['post_id']) for v in (mm.get('pairs') or {}).values() if (v or {}).get('post_id')}
        keep_ids |= {str(e.get('post_id')) for lst in (mm.get('more') or {}).values() for e in (lst or [])}
        keep_ids |= {str(x) for x in (mm.get('admit') or [])}
    except Exception:
        keep_ids = set()
    pinned = [p for p in items if str(p.get('id')) in keep_ids]
    rest = [p for p in items if str(p.get('id')) not in keep_ids]
    items = (pinned + rest)[:150]  # pool 50->150 (owner 2:09 coverage push): more candidates
    # per story = more honest verified-pair chances; pinned ids still never evicted
    # X-wall companion (Sep 29): an emptied pool must NOT bump generated_at - the
    # client's rpMapFresh exact-matches x_generated_at, so a fresh stamp on an empty
    # feed re-mismatches the map between rebuilds. Preserve the prior stamp.
    gen = (prev_gen if not items and prev_gen else
           datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'))
    out = {'generated_at': gen,
           'source': 'x_recent_search', 'window': False, 'items': items}
    json.dump(out, open(OUT, 'w'), indent=1)
    return len(items)

def pull_query(q, since_id=None):
    params = {'query': q, 'max_results': MAX_RESULTS,
              'tweet.fields': 'created_at,author_id,public_metrics',
              'expansions': 'author_id', 'user.fields': 'username,name'}
    if since_id:
        params['since_id'] = since_id
    status, body = req('/tweets/search/recent', params)
    data = body.get('data') or []
    users = {u.get('id'): u for u in ((body.get('includes') or {}).get('users') or [])}
    log_burn('/tweets/search/recent', 'news:' + q[:180], len(data))
    items = []
    for tw in data:
        u = users.get(tw.get('author_id')) or {}
        uname = u.get('username')
        items.append({'query': q, 'id': tw.get('id'), 'created_at': tw.get('created_at'),
                      'text': tw.get('text'), 'author_username': uname,
                      'author_name': u.get('name'),
                      'public_metrics': tw.get('public_metrics') or {},
                      'url': f'https://x.com/{uname}/status/{tw.get("id")}' if uname else None})
    newest = ((body.get('meta') or {}).get('newest_id')) or since_id
    return items, newest

def fresh_headlines(limit):
    news = json.load(open(NEWS))
    now = datetime.datetime.now(datetime.timezone.utc)
    out = []
    for it in news.get('latest', []):
        try:
            pub = datetime.datetime.fromisoformat((it.get('published') or '').replace('Z', '+00:00'))
        except Exception:
            continue
        if (now - pub) > datetime.timedelta(hours=MAX_HEADLINE_AGE_H):
            continue
        out.append(it)
        if len(out) >= limit:
            break
    return out

BACKFILL = False   # set by main when the pool does not span the full 24h horizon (owner 2:49)

def run_strategies(headlines, strategies, requests_cap, trial_log=None):
    """Core pull loop with route-around. Returns (items, requests_used)."""
    st = load_state()
    since = st.get('news_since', {})
    items = []
    used = 0
    successful = 0
    fail_codes = []
    for it in headlines:
        if used >= requests_cap:
            break
        nk = headline_key(it)
        placed = False
        for strategy in strategies:
            if placed or used >= requests_cap:
                break
            qs = build_queries(it, strategy)
            if not qs:
                continue
            q = qs[0]
            attempts = [(strategy, q)] + route_arounds(it, strategy)
            for tag, aq in attempts[:ROUTE_ATTEMPTS]:
                if used >= requests_cap:
                    break
                try:
                    got, newest = pull_query(aq, None if BACKFILL else since.get(aq))  # backfill: no since_id so the full 24h window is matchable
                    used += 1
                    successful += 1
                    if newest:
                        since[aq] = newest
                    for g in got:
                        g['via'] = 'news:' + tag
                        g['nk'] = nk
                    if got:
                        items.extend(got)
                        if trial_log is not None:
                            trial_log.append({'headline': it.get('headline', '')[:100], 'nk': nk,
                                              'strategy': tag, 'query': aq, 'results': len(got),
                                              'routed': tag != strategy})
                        placed = True
                        break
                    if trial_log is not None:
                        trial_log.append({'headline': it.get('headline', '')[:100], 'nk': nk,
                                          'strategy': tag, 'query': aq, 'results': 0,
                                          'routed': tag != strategy, 'note': 'zero results - rotating'})
                except Exception as e:
                    used += 1
                    c = x_wall.http_code(e)
                    if c: fail_codes.append(c)
                    if trial_log is not None:
                        trial_log.append({'headline': it.get('headline', '')[:100], 'nk': nk,
                                          'strategy': tag, 'query': aq, 'error': str(e)[:160],
                                          'note': 'request failed - rotating'})
    st['news_since'] = since
    save_state(st)
    if used and not successful:
        if x_wall.is_wall(fail_codes):
            x_wall.wall_skip('news_social pull')
            return [], used
        raise RuntimeError('news-driven X ingest stalled: no successful recent-search request; preserving feed')
    return items, used

def main():
    if not TOKEN:
        print('X_BEARER_TOKEN secret not set - dormant')
        return
    mode = sys.argv[1] if len(sys.argv) > 1 else 'pull'
    if mode == 'trial':
        # sentient integration trials (owner 1:15): every strategy gets its shot on live data,
        # every failure routes around, everything logged. Winner decided by soc_match verdicts.
        trial_log = []
        headlines = fresh_headlines(6)
        items, used = run_strategies(headlines, ['S1', 'S2', 'S3', 'S4'],
                                     NEWS_QUERIES_PER_RUN + 4, trial_log)
        total = merge_feed(items)
        rec = {'ran_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
               'mode': 'trial', 'headlines': len(headlines), 'requests': used,
               'posts_pulled': len(items), 'feed_total': total, 'attempts': trial_log,
               'winner': None,
               'note': 'winner decided after soc_match gating attributes verified pairs to via=strategy tags'}
        # attribute back from the existing match map when present
        try:
            mm = json.load(open('slates/soc_match.json'))
            feed = {str(p.get('id')): p for p in json.load(open(OUT)).get('items', [])}
            scores = {}
            for k, v in (mm.get('pairs') or {}).items():
                pid = str((v or {}).get('post_id') or '')
                if pid and pid in feed:
                    via = feed[pid].get('via', 'untagged')
                    scores[via] = scores.get(via, 0) + 1
            if scores:
                rec['winner'] = max(scores, key=scores.get)
                rec['winner_pairs'] = scores
        except Exception as e:
            rec['attribution_error'] = str(e)[:120]
        json.dump(rec, open(TRIALS, 'w'), indent=1)
        print(f'trial: {used} requests, {len(items)} posts, attempts={len(trial_log)}, winner={rec["winner"]}')
        return
    # pull: standing mode on the winning strategy (default S3 until first trial verdict)
    winner = None
    try:
        winner = (json.load(open(TRIALS)) or {}).get('winner')
    except Exception:
        pass
    strategy = (winner or 'news:S1').replace('news:', '')
    if strategy not in ('S1', 'S2', 'S3', 'S4'):
        strategy = 'S1'
    # A news generation ID does not prove X has not received a newer post.
    # The workflow controls paid-pull cadence via the shared burn ledger.
    # owner 2:49: if the pooled posts do not yet span 24h, run this pull as a backfill
    # (since_id suppressed) until the horizon is covered.
    try:
        _pool = json.load(open(OUT)).get('items', [])
        _oldest = min((str(pp.get('created_at') or '') for pp in _pool), default='')
        _age_h = 999
        if _oldest:
            _dt = datetime.datetime.fromisoformat(_oldest.replace('Z', '+00:00'))
            _age_h = (datetime.datetime.now(datetime.timezone.utc) - _dt).total_seconds() / 3600.0
        globals()['BACKFILL'] = (not _pool) or (_age_h < 23.0)  # span short of the 24h horizon -> backfill
        if BACKFILL:
            print('backfill: pool does not span 24h - pulling without since_id this run')
    except Exception:
        globals()['BACKFILL'] = False
    headlines = fresh_headlines(NEWS_QUERIES_PER_RUN)
    items, used = run_strategies(headlines, [strategy, 'S2', 'S3'], NEWS_QUERIES_PER_RUN)
    if used:
        total = merge_feed(items)
    else:
        try: total = len(json.load(open(OUT)).get('items', []))
        except (FileNotFoundError, ValueError): total = 0
    print(f'pull[{strategy}]: {used} requests, {len(items)} new posts, feed carries {total}')

if __name__ == '__main__':
    main()
