#!/usr/bin/env python3
"""RixPicks news<->social semantic matcher (owner directive 12:37 PT) on URF loop discipline (12:41).

Pipeline per refresh:
  embed (NIM nemotron-3-embed-1b via ultrix-core /nim, passage mode)
  -> cosine candidates per news item
  -> six-gate decide() per candidate (authority/evidence/value/risk/conflict/reversibility)
       ALGO-ONLY VERIFICATION (owner 9/28 6:06, verbatim via main): 'verified' status is
       conferred EXCLUSIVELY by the UltRix probe's own EXECUTE verdict - no static gate,
       keyword list, cosine score, or side-channel check ever grants it. Static filters
       (RP_AD/RP_TOUT/publishability) are default-DENY only: they can kill a candidate,
       never bless one. pins, nearest and more[] are built ONLY from probe-EXECUTE candidates.
       evidence gate: every candidate >= PROBE_FLOOR takes the smallest falsifying test
       (language-mode verify: is this post about THIS story?) -> confirm or reject-and-step
  -> verdict log per candidate (gate + reason); rejected candidates recorded (what-we-missed mining)
  -> abstain never forced: low-confidence items pair nothing, client falls back chronologically
  -> slates/soc_match.json (cached; client never calls the endpoint per pageview)

Public headlines/posts only (trial terms). Token from /tmp/.nim_client_token, never logged.
Fail closed: any endpoint/credit failure leaves the previous soc_match.json untouched and
writes status=fallback to slates/soc_match_status.json (client token-matches when map is stale).
"""
import json, math, os, sys, time, hashlib, urllib.request, datetime, re

# no tout/selling-access posts, ever (owner 1:39) - server mirror of the client RP_TOUT_KW filter
RP_AD = re.compile(r'happy hour|dine[ -]?in|grab a (table|seat|cold one)|tall domestics|half rack|drink specials?|food specials?|come watch|watch party|patio|\$\d+(\.\d+)? (tall|pint|wing|slice|pitcher)|reservation|book a table|now open|grand opening|tickets? (to see|for|available)|[0-9]x tickets|seats? (available|for sale)|get rid of|price.{0,12}negotiable|send me a dm|dm if you|selling (my|[0-9])|face value|stubhub|vivid ?seats|seatgeek|tickpick|ticketmaster|gametime|freebie|free picks? on|model.{0,20}(is )?(live|cashed)|cashed some|brought to you by|listen in now|tune in (now|tonight)|[0-9]{2,3}\.[0-9] ?fm|[0-9]{3,4} ?am\b|get-in (price|as)|best free|top [0-9]+ (player )?props|deposit (bonus|match|offer)|bonus bets?', re.I)
RP_AD2 = re.compile(r'#\s*(ad|ads|sponsored|sponsorship)\b|#\w*sale\b|#giveaway\b|follow\s+(us|me|@\w+)\b.{0,40}(to win|to enter|for a chance|giveaway)|(secure|reserve|book)\s+(a\s+|your\s+)table|(arrive|get (there|here)|come)\s+early\b[^.!?]{0,50}(secure|reserve|grab|book)\s+(a\s+|your\s+)?(table|spot|seat)|free picks?\s*(up|here|today|tonight|now|below|thread|incoming|alert|inside|drop)', re.I)
RP_PROMO_CAPS = re.compile(r'\bFREE PICKS?\b')
RP_TOUT = re.compile(r'discord|telegram|dubclub|patreon|link in bio|dm (me|us) for|vip (picks|plays|access)|picks package|premium picks|paywall|subscribe for|promo code|join my|tap in with|free (play|pick)s? (today|daily)|lock of the day|guaranteed (winner|play)|freebie|free picks? on|model.{0,20}(is )?(live|cashed)', re.I)

NIM_URL = 'https://ultrix-core.itsdardanr.workers.dev/nim'
EMBED_MODEL = 'nvidia/nemotron-3-embed-1b'
VERIFY_MODEL = 'meta/llama-3.2-11b-vision-instruct'  # only live language model on this NIM account (probed 3:26 - 70b/405b/qwen/deepseek all 404/410)
REQUESTER = 'rixpicks-socmatch'
AUTO_ACCEPT = 0.62      # evidence gate passes outright
PROBE_FLOOR = 0.48      # band [FLOOR, ACCEPT): PROBE via LLM verify
MORE_FLOOR = 0.42       # "View more posts" list inclusion
MAX_PROBES = 120        # per-run LLM verify budget (trial credits) - more[] verification costs probes now
MAX_ONS_PROBES = 90     # per-run on-story probe budget for the never-empty latest tier
TOP_CANDIDATES = 10
MORE_CAP = 20

# ---------------------------------------------------------------------------
# Deterministic ENTITY-CONFLICT pre-gate (owner 6:58 + guard 2 incident, 9/28 ~7 PM):
# the small probe model collapses broad thematic relation (Warriors-injuries story vs a
# Ja Morant trade post; Clark Game-2 story vs a Steph-White history post), so a hard
# entity check vets every candidate BEFORE cache/probe. It can only DENY - the badge is
# still conferred exclusively by the probe's EXECUTE (owner 6:06:54, static gates never grant).
# Layers: (1) a post must carry at least min(2,N) of the headline's distinctive entities
# (person surnames from capitalized bigrams, capitalized tokens >=4 chars minus headline
# boilerplate); (2) a post whose text introduces a foreign principal person (capitalized
# bigram surname absent from the headline's entities, place/org words excluded) conflicts.
# No extractable entities -> gate silent, probe decides. Latest tier uses layer 1 at need=1.
ENTITY_GATE_VERSION = 'eg5'  # cache salt: freshness and reason-integrity checks
ENTITY_STOP = set('game games report reports season seasons preview previews recap recap watch video highlight highlights rumor rumors update updates news trade trades injury injuries week daily today tonight tomorrow yesterday best worst ranking rankings power draft pick picks odds line lines spread spreads over under win wins loss losses versus the after before says said new why how what who live score scores final first last early late big top free agent agents coach coaches team teams player players star stars fans fan take takes make makes get gets back down into with from will would could should must still just more most ever every next league playoff playoffs postseason championship title titles night match matches fight fights career future futures ready leads lead leading recalls sent check throws college football basketball baseball hockey soccer monday tuesday wednesday thursday friday saturday sunday january february march april may june july august september october november december chat discussion eve face home road looks remain unbeaten factor charge go years year state count counts props prop expert experts bets bet betting booed'.split())
POST_PERSON_STOP = ENTITY_STOP | set('field stadium arena center centre park garden dome coliseum bowl classic series cup showdown invitational open masters nationals united city club fc sc ac cf real sporting athletics university kings queens islanders'.split())

def title_entities(title):
    toks = re.findall(r"[A-Za-z][A-Za-z'\-]*", title or '')
    persons = set()
    ents = set()
    for a, b in zip(toks, toks[1:]):
        if a[:1].isupper() and b[:1].isupper() and len(b) >= 3 and a.lower() not in ENTITY_STOP:
            persons.add(b.lower().strip("'-"))
    for t in toks:
        tl = t.lower().strip("'-")
        if t[:1].isupper() and len(t) >= 4 and tl not in ENTITY_STOP and tl not in persons:
            ents.add(tl)
    return ents | persons

def entity_hits(ents, text):
    p = ' ' + re.sub(r'[^a-z0-9 ]', ' ', (text or '').lower()) + ' '
    return sum(1 for e in ents if (' ' + e + ' ') in p)

def entity_conflict(ents, text, need):
    """layer 1: too few of the story's distinctive entities present."""
    return bool(ents) and entity_hits(ents, text) < min(need, len(ents))

def post_persons(text, title_ents):
    """layer 2: a foreign principal person in SUBJECT position (first 100 chars) - the
    false-pair signature (Josh Hokit vs Rosas story, Steph White vs Clark Game-2 story).
    Subject-position only: people quoted deeper in a genuinely on-story post stay eligible.
    ALL-CAPS bigrams are team/league shouts (EAGLES @ BEARS), never person names."""
    toks = re.findall(r"[A-Za-z][A-Za-z'\-]*", (text or '')[:100])
    out = set()
    for a, b in zip(toks, toks[1:]):
        if a[:1].isupper() and b[:1].isupper() and not a.isupper() and not b.isupper():
            la, lb = a.lower().strip("'-"), b.lower().strip("'-")
            if len(lb) < 3 or la in POST_PERSON_STOP or lb in POST_PERSON_STOP:
                continue
            if la in title_ents or lb in title_ents:
                continue
            out.add(lb)
    return out

# Story-type compatibility gates (guards 2+3, 9/28 ~7:10 PM - TruGrit bare-odds pin reversal):
# R1 a picks/props/best-bets/odds article verifies ONLY against a post carrying evidence of
#    the article's OWN chosen line or pick (player prop, expert claim, named pick) - a generic
#    team-odds snapshot (Bears -122, Eagles +100) is game overlap, NEVER article-level.
# R2 a betting-slip post (units, +/- lines, prop parlays) NEVER pairs a non-picks story.
# R3 a historically-framed post (since 2021, career, all-time) NEVER pairs a breaking-event
#    story (injury, trade, signing) - same person, different era = different story.
PICKS_ARTICLE = re.compile(r'\b(picks?|props?|best bets|expert|parlay|bets|betting)\b', re.I)
PICK_EVIDENCE = re.compile(r"\b((?:over|under)\s*\d|yards?|yds|td|touchdown|receptions?|rushing|passing|receiving|interceptions?|ints?|sacks?|strikeouts?|anytime|scorer|prop|best bet|lock|taking the|picking the|picked the|my pick|i like the|give me|pick:|play:)\b", re.I)
# Latest-tier picks stories need a declared selection, not merely football stats.
# This is a DENY gate only; a passing post still needs the on-story probe.
DECLARED_PICK = re.compile(r"\b(i(?:\s*am|['’]m)?\s+(?:picking|taking|betting|playing)|my\s+(?:pick|bet|play)|(?:our|the)\s+(?:best\s+)?pick\s*(?::|is)|pick\s*:\s*|play\s*:\s*|best\s+bet\s*(?::|is)|(?:over|under)\s+\d+(?:\.\d+)?|(?:[+-]\d+(?:\.\d+)?)\s*(?:spread|moneyline)|\b(?:anytime|first)\s+(?:td|touchdown)\s+scorer)\b", re.I)

def latest_pick_gate(title, post):
    if PICKS_ARTICLE.search(title or '') and not DECLARED_PICK.search(post or ''):
        return 'expert-picks article: post makes no concrete selection (generic breakdown is not a pick)'
    return None

BET_SLIP_POST = re.compile(r'\[\d+(\.\d+)?u\]|[+-]\d{3,}[^.\n]{0,40}[+-]\d{3,}', re.I)
HISTORICAL_POST = re.compile(r'\b(since (19|20)\d\d|career|all[- ]time|histor(?:y|ical)|last season|retrospective|looking back|this offseason|offseason|recruiting)\b', re.I)
# R4-R8 action + temporal classes (guard 2 story-audit 9/28 7:59): entity overlap is not an
# event match. The article's ACTION + TEMPORAL STATUS must match the post's - postgame recap
# vs pregame hype, game thread vs sales CTA, availability update vs offseason interview,
# preview analysis vs transaction report, editorial analysis vs trivia, betting content vs
# non-betting story.
RECAP_ARTICLE = re.compile(r"\b(second|third|fourth|game-winning|walk-?off)\b.{0,25}\b(td|touchdown|goal|shot|home run|pass)\b|\b(td|touchdown) pass\b|holding .{0,15}lead|\bfinal\b|recap|postgame", re.I)
PREGAME_POST = re.compile(r"\b(tonight|my pick|i'?m picking|could be a|the script|pregame|tailgate|first start .{0,30}in \d+ years|hasn'?t .{0,30}(all season|yet|since \d+))\b", re.I)
PREVIEW_ARTICLE = re.compile(r'\b(preview|looks to|how to watch|keys to|storylines)\b', re.I)
TRANSACTION_POST = re.compile(r'\b(officially inactive|inactive for|placed on|activated from|listed as (out|doubtful|questionable)|waived|signed to)\b', re.I)
CTA_POST = re.compile(r"\b(here are (the|our|my|your).{0,40}(picks|predictions)|tune in(to)?|listen (live|to)|promo code|bonus code|use code|link in (bio|comments)|sign up (and|to))\b", re.I)
PROMO_ARTICLE = re.compile(r'\b(promo code|bonus code|bonus bets?|sign[- ]up (offer|bonus)|sportsbook (offer|promo))\b', re.I)
TRIVIA_POST = re.compile(r'\b(jersey number|rock #|wear #|uniform number|new number)\b', re.I)
ANALYSIS_ARTICLE = re.compile(r"\b(make sense|winners and losers|execs|coaches.{0,25}(explain|poll|rank)|breakdown|film study)\b", re.I)
BETTING_CONTENT = re.compile(r'\b(ATS|against the spread|cover the|moneyline|over/under|betting trend|units? won)\b', re.I)

BREAKING_ARTICLE = re.compile(r'\b(leaves|sent|injured|injury|injuries|ready to go|cleared|ruled out|exits?|carted|concussion|traded|trade|signs|signed|released|breaks|sidelined|questionable|doubtful|scratched|activated|waived|recalled)\b', re.I)


def foreign_person_vs_title(title, text):
    """eg3 hole kill (9/28 7:46, Fever/CC false pin 2104679415208698214): when title_entities
    finds no entities the layer-2 check was SKIPPED - an unrecognized-entity story was an
    unguarded surface, and a post about a different person paired freely. Fallback bar: a
    subject-position person bigram whose surname appears nowhere in the headline text is a
    foreign principal, whatever the entity extractor managed to recognize."""
    t = (title or '').lower()
    toks = re.findall(r"[A-Za-z][A-Za-z'\-]*", (text or '')[:100])
    out = set()
    for a, b in zip(toks, toks[1:]):
        if a[:1].isupper() and b[:1].isupper() and not a.isupper() and not b.isupper():
            la, lb = a.lower().strip("'-"), b.lower().strip("'-")
            if len(lb) < 3 or la in POST_PERSON_STOP or lb in POST_PERSON_STOP:
                continue
            if la in t or lb in t:
                continue
            out.add(lb)
    return out

def story_type_gate(title, post):
    t, p = title or '', post or ''
    picks_art = bool(PICKS_ARTICLE.search(t))
    if picks_art and not PICK_EVIDENCE.search(p):
        return 'picks-type article: no article-pick evidence in post (generic odds/news is game overlap)'
    if not picks_art and BET_SLIP_POST.search(p):
        return 'betting-slip post on a non-picks story'
    if HISTORICAL_POST.search(p) and BREAKING_ARTICLE.search(t):
        return 'historical framing vs breaking-event story'
    # R4 postgame/live recap story vs pregame-framed post (Keenum 2nd-TD vs Barkley bet/hype)
    if RECAP_ARTICLE.search(t) and PREGAME_POST.search(p):
        return 'pregame/hype post vs postgame recap story (temporal mismatch, guard 2)'
    # R5 preview/analysis story vs transaction/inactive report (CBS preview vs Caleb inactive)
    if PREVIEW_ARTICLE.search(t) and TRANSACTION_POST.search(p):
        return 'transaction report vs preview-analysis story (action mismatch, guard 2)'
    # R6 sales/promo CTA post vs non-promo story (picks CTA vs game thread; radio tune-in)
    if CTA_POST.search(p) and not PROMO_ARTICLE.search(t):
        return 'sales/promo CTA post vs non-promo story (guard 2)'
    # R7 trivia (jersey/uniform numbers) vs analysis article (Giants trade analysis)
    if ANALYSIS_ARTICLE.search(t) and TRIVIA_POST.search(p):
        return 'trivia post vs analysis article (action mismatch, guard 2)'
    # R8 betting-market content (ATS/trends) vs non-betting story
    if BETTING_CONTENT.search(p) and not PICKS_ARTICLE.search(t):
        return 'betting-market content vs non-betting story (guard 2)'
    return None


def probe_predeny(story, post):
    """guard 3 kill (9/28 7:51, TruGrit 2104707827759473125 vs CBS expert-props): the
    article-level test must demand a POSITIVE match to the article's concrete picks/props/
    expert claim. Noncontradiction, same-event, or shared odds vocabulary is NEVER a match.
    A picks-type article paired with a post declaring no concrete pick evidence is a
    deterministic REJECT before the judge ever sees it. Default-DENY only (6:06:54): this
    gate never grants - every EXECUTE still comes from the judge."""
    head = (story or '')[:200]
    if PICKS_ARTICLE.search(head) and not PICK_EVIDENCE.search(post or ''):
        return ('REJECT', 'picks-type article, post declares no concrete pick/prop: same-event odds language is not a match (deterministic, guard 3)')
    return None

def enforce_uniqueness(log):
    """guard 2 (9/28 7:59): any post ID maps to at most ONE story across pins/more/nearest/
    latest; repetition INSIDE one story is fine (the pin is its own story's nearest etc).
    Priority pin > nearest > more > latest: first claim keeps the post, later tiers drop it.
    Returns the violations stripped (also recorded into log['audit'])."""
    seen = {}
    viol = []
    def claim(pid, nk, tier):
        pid = str(pid)
        if pid in seen and seen[pid] != nk:
            viol.append({'post_id': pid, 'tier': tier, 'kept_story': seen[pid][:80], 'dropped_story': (nk or '')[:80]})
            return False
        seen.setdefault(pid, nk)
        return True
    for nk, pr in (log.get('pairs') or {}).items():
        if pr.get('post_id'):
            claim(pr['post_id'], nk, 'pin')
    for nk in list((log.get('nearest') or {}).keys()):
        v = log['nearest'][nk]
        if v.get('post_id') and not claim(v['post_id'], nk, 'nearest'):
            del log['nearest'][nk]
    for nk in list((log.get('more') or {}).keys()):
        log['more'][nk] = [x for x in log['more'][nk] if claim(x.get('post_id'), nk, 'more')]
    for nk in list((log.get('latest') or {}).keys()):
        v = log['latest'][nk]
        if v.get('post_id') and not claim(v['post_id'], nk, 'latest'):
            del log['latest'][nk]
    if viol:
        log.setdefault('audit', {})['uniqueness_stripped'] = viol
    return viol

# Equivocal-YES abstain (guard 2, same incident): a YES whose own reasoning admits a
# conflict ("YES - Different team.") is the model collapsing, not confirming. The parser
# reads the whole response; an equivocal YES abstains - never cached, never badged.
EQUIVOCAL = re.compile(r'\b(different (team|teams|player|players|game|story|stories|event|sport|fight|match|matchup|league)|not the same|unrelated|no overlap|does not (mention|discuss|cover)|not about|other (team|player|game)|main subject differs)\b', re.I)

# A YES is admissible only when its final line gives an actual action supported by
# both inputs. The model's rationale is evidence to check, never evidence by itself.
GENERIC_REASON = re.compile(r'\b(same (?:event|game|story|topic|subject|health status)|related to|about the same|both (?:mention|discuss|refer to)|shares? (?:the )?(?:name|team|player)|no contradiction|does not contradict|exact quote of (?:the )?(?:story.s )?headline|headline quote|same person)\b', re.I)
ACTION_WORDS = set('score scores scored scoring wins won loses lost leads led beats beat signs signed signing trades traded trading injured injury cleared clears clearing ruled inactive activates activated returns returned returning starts started starting exits exited breaks broke throws threw thrown passes passed passing hits hit homers homered shoots shot retires retired retirement cuts cut waived waive suspended suspends drafts drafted fired hired hiring extends extended extension announces announced announce reports reported report confirms confirmed files filed qualifies qualified advances advanced predicts predicted predicts prediction recommends recommended picks picked picking bets bet betting changes changed updates updated update discusses discussed explains explained analyzes analysed analysis'.split())
STOP_REASON = set('the and for with from into over under after before this that they their his her its are was were about story news post article social both same main team player game event match matching headline quote exact says mentions discussion directly specific concrete shared action because as also has have had'.split())

def _reason_tokens(s):
    return set(re.findall(r"[a-z0-9]+", (s or '').lower())) - STOP_REASON

def reason_integrity(reason, story='', post=''):
    """Default-deny incomplete, tautological and unsupported YES rationales."""
    r = (reason or '').strip()
    if len(r) < 18 or len(r.split()) < 4 or r.endswith(('...', '…', ':', '-', ',')) or GENERIC_REASON.search(r):
        return False
    # Quote claims are falsifiable: text in quotation marks must actually occur in
    # both the story and post, not merely be asserted by the judge.
    quotes = re.findall(r'["“]([^"”]{4,})["”]', r)
    if quotes and (not story or not post or any(q.lower() not in story.lower() or q.lower() not in post.lower() for q in quotes)):
        return False
    if story and post:
        # Proper-name and number claims cannot be supplied by the model alone.
        names = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', r)
        if any(n.lower() not in story.lower() or n.lower() not in post.lower() for n in names):
            return False
        if any(n not in story or n not in post for n in re.findall(r'\b\d+(?:st|nd|rd|th)?\b', r, re.I)):
            return False
        rt = _reason_tokens(r); st = _reason_tokens(story); pt = _reason_tokens(post)
        # Names alone are never proof. At least an action in the reason must be
        # supported by each input. A conservative abstain is safer than a false badge.
        if not (rt & st & pt & ACTION_WORDS):
            return False
        if len(rt & st & pt) < 2:
            return False
    return bool(_reason_tokens(r) & ACTION_WORDS)

def parse_verification(text, story='', post=''):
    """tri-state: EXECUTE / REJECT / ABSTAIN; only an evidenced final YES executes."""
    lines = [l.strip() for l in (text or '').splitlines() if l.strip()]
    verdict_line = ''
    for l in reversed(lines):
        if re.match(r'^(YES|NO)\b', l, re.I):
            verdict_line = l
            break
    if not verdict_line:
        return 'ABSTAIN', ('probe gave no final YES/NO: ' + (lines[-1] if lines else 'empty'))[:160]
    if re.match(r'^YES\b', verdict_line, re.I):
        if EQUIVOCAL.search(text or ''):
            return 'ABSTAIN', ('equivocal YES: ' + verdict_line)[:160]
        reason = re.sub(r'^YES\b[\s:.-]*', '', verdict_line, flags=re.I)
        if not reason_integrity(reason, story, post):
            return 'ABSTAIN', ('unsupported YES reason: ' + verdict_line)[:160]
        return 'EXECUTE', verdict_line[:160]
    return 'REJECT', verdict_line[:160]


def timestamp(value):
    try:
        dt = datetime.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt if dt.tzinfo else None
    except (ValueError, TypeError):
        return None


def freshness_gate(story, post):
    """Article-to-post parity: unknown clocks never grant a pair.

    The 24h matching horizon is distinct from the tighter article-time parity.
    A post before a new story by hours cannot pass just because both are within 24h.
    """
    published = timestamp(story.get('published'))
    posted = timestamp(post.get('created_at') or post.get('ts'))
    now = datetime.datetime.now(datetime.timezone.utc)
    if not published or not posted:
        return 'unknown article/post timestamp'
    if posted > now + datetime.timedelta(minutes=5) or published > now + datetime.timedelta(minutes=5):
        return 'future article/post timestamp'
    if now - posted > datetime.timedelta(hours=24):
        return 'post outside 24h window'
    article_age = now - published
    allowed = datetime.timedelta(hours=2 if article_age < datetime.timedelta(hours=6) else 6)
    if published - posted > allowed:
        return 'post predates article beyond freshness parity'
    return None


def candidate_order(scored, posts):
    """Final candidate set: high similarity plus recent qualified posts, then newest first."""
    eligible = [(score, j) for score, j in scored if score >= PROBE_FLOOR]
    recent = sorted(eligible, key=lambda sj: posts[sj[1]].get('created_at') or posts[sj[1]].get('ts') or '', reverse=True)
    chosen = {j for _, j in eligible[:TOP_CANDIDATES]}
    chosen.update(j for _, j in recent[:TOP_CANDIDATES])
    return [sj for sj in recent if sj[1] in chosen]

# owner 1:26: the social feed itself renders sports-relevant, topic-matching posts only -
# never a raw firehose. Relevance is decided by the SAME semantic layer (evidence gate):
# each post is cosined against fixed league anchor phrases; below every anchor threshold =>
# flagged off_topic in the map and the client excludes it from the social carousel. Client
# falls back to its own keyword check only when no fresh map exists (stale beats raw).
LEAGUE_ANCHORS = {
    'NFL': 'NFL football news, teams, players, scores, injuries, trades',
    'NBA': 'NBA basketball news, teams, players, scores, trades',
    'MLB': 'MLB baseball news, teams, players, scores, playoffs',
    'NHL': 'NHL hockey news, teams, players, scores',
    'CFB': 'college football news, teams, players, scores, rankings',
    'NCAAB': 'college basketball news, teams, players, scores',
    'WNBA': 'WNBA basketball news, teams, players, scores',
    'MLS': 'MLS soccer news, teams, players, scores',
    'NWSL': 'NWSL soccer news, teams, players, scores',
    'PGA': 'PGA golf news, players, tournaments, leaderboard',
    'NASCAR': 'NASCAR racing news, drivers, race results',
    'UFC': 'UFC MMA fight news, fighters, cards, results',
    'Boxing': 'boxing news, fighters, bouts, results',
    'ATP': 'tennis news, players, tournaments, results',
    'SPORTS_GENERIC': 'sports talk, game analysis, fantasy sports, betting picks, sports debate',
}
RELEVANCE_FLOOR = 0.40   # below every anchor = off_topic (calibration: unrelated non-sports ~0.30-0.36)

def token():
    with open('/tmp/.nim_client_token') as f:
        return f.read().strip()

def nim(payload, timeout=60):
    req = urllib.request.Request(NIM_URL, data=json.dumps(payload).encode(),
        headers={'x-nim-key': token(), 'content-type': 'application/json',
                 # Cloudflare bot-fight 403s the default Python-urllib UA on this zone (verified 12:48)
                 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read().decode())
    if not out.get('ok'):
        raise RuntimeError('nim error: ' + str(out.get('error')))
    return out

def embed_all(texts):
    vecs = []
    for i in range(0, len(texts), 32):
        out = nim({'requester': REQUESTER, 'mode': 'embed', 'input': texts[i:i+32],
                   'model': EMBED_MODEL, 'input_type': 'passage'}, timeout=120)
        vecs.extend(out['embeddings'])
    return vecs

VECS = 'slates/soc_vecs.json'
VERD = 'slates/soc_verdicts.json'
PROMPT_VERSION = 'v9-reason-freshness'  # probe wording is decision-changing: version MUST salt the verdict cache
SALT = '|'.join([str(AUTO_ACCEPT), str(PROBE_FLOOR), str(MORE_FLOOR), EMBED_MODEL, VERIFY_MODEL, PROMPT_VERSION, ENTITY_GATE_VERSION])

def thash(t):
    return hashlib.sha1(t.encode('utf-8')).hexdigest()

def embed_cached(texts):
    """owner 2:48 (six gates must be instant): embeddings are deterministic per model+text, so
    cache by content hash and bill NIM only for NEW texts. A steady-state cycle (no new stories,
    no new posts) makes zero embed calls; the matcher becomes CPU-only over cached vectors."""
    try:
        cache = json.load(open(VECS))
    except Exception:
        cache = {}
    missing = [t for t in dict.fromkeys(texts) if thash(t) not in cache]
    if missing:
        for v, t in zip(embed_all(missing), missing):
            cache[thash(t)] = v
        print(f'embed cache: {len(missing)} new texts embedded, {len(texts) - len(missing)} reused')
    keep = {thash(t) for t in texts}
    cache = {h: v for h, v in cache.items() if h in keep}
    json.dump(cache, open(VECS, 'w'))
    return [cache[thash(t)] for t in texts]

def cos(a, b):
    dot = sum(x*y for x, y in zip(a, b))
    na = math.sqrt(sum(x*x for x in a)); nb = math.sqrt(sum(x*x for x in b))
    return dot / (na * nb) if na and nb else 0.0

def verify(story, post):
    """PROBE: smallest falsifying test - does this post talk about this story?"""
    pre = probe_predeny(story, post)
    if pre:
        return pre
    st = story_type_gate((story or '')[:200], post or '')
    if st:
        return ('REJECT', 'story-type gate: ' + st)
    # probe calibration (1:30): the product rule is "matching social posts ABOUT the story"
    # (owner 1:11). Round 1's wording ("same specific story") over-abstained - it rejected a
    # fan's "My OFFICIAL 2026 MLB Playoff Predictions" against "2026 MLB playoff predictions:
    # Expert picks", which IS the same topic. Boundary unchanged: different player/team/game/
    # storyline is still a mismatch (adversarial: Jets injury post vs Bills injury story = NO).
    # v3 structured (owner 3:16 hardening): force entity extraction BEFORE the verdict so the
    # small judge can't pattern-match on a side-mentioned name (the Jameis Winston false-reject:
    # the blurb named him but the story's subject was the McCarthy trade). Same bar, better aim.
    prompt = ('You verify content pairings for a sports site. Work in two steps.\n'
              'NEWS STORY: ' + story[:600] + '\n'
              'SOCIAL POST: ' + post[:600] + '\n'
              'Step 1: In one line each, name the story' + chr(39) + 's specific event or action AND the team or person it '
              'affects, then the post' + chr(39) + 's main subject. Ignore side mentions.\n'
              'Step 2: The primary relationship must be the article' + chr(39) + 's claim, offering, analysis angle, or '
              'event - never merely the same game or the same sport. Rules:\n'
              '- Cause and consequence of the SAME event are the same story (a player cleared to play AND his '
              'team entering the rankings because of it): YES.\n'
              '- A matching headline quote is not proof without the post sharing its concrete action.\n'
              '- A promo/bonus-bet article matches ONLY posts identifying THAT brand and THAT offer; other '
              'sportsbooks, deposit bonuses, or game commentary: NO.\n'
              '- A betting preview or picks article matches ONLY posts discussing THAT specific pick or odds '
              'line; an unrelated pick or a sales CTA: NO.\n'
              '- Radio plugs, station kickoff promos, venue promotions, ticket resale, food or drink specials, '
              'viewing schedules, and sales CTAs are NEVER about the news story: NO.\n'
              '- A different player, team, game, or storyline as the MAIN subject is NOT a match.\n'
              '- Sharing a named person is NOT enough: if the post is about the same person but a\n'
              '  DIFFERENT event, timeframe, or situation than the story' + chr(39) + 's specific event: NO.\n'
              '- A generic odds, spread, moneyline, or totals post with no named expert pick NEVER\n'
              '  matches an expert-picks, best-bets, or player-props article: NO.\n'              '- POSITIVE-match demand (guard 3): an expert-picks, best-bets, or player-props\n'
              '  article matches ONLY a post that affirmatively states its own concrete pick, prop,\n'
              '  or best bet AND that pick agrees with a concrete pick, prop, or line the article\n'
              '  itself recommends. Same event, same sport, shared odds vocabulary, or the absence\n'
              '  of contradiction is NEVER a match: NO.\n'
              '- Personal fan plans, attendance, travel, or watch-party posts are NEVER about the story: NO.\n'
              '- ACTION + TIMELINE proof (guard 2): name the story\'s action and where it sits in the\n'
              '  event timeline (pregame preview, live thread, postgame play/recap, roster/injury update,\n'
              '  offseason feature), then the post\'s. YES only when BOTH action and timeline match. A\n'
              '  pregame pick or hype NEVER matches a postgame play or recap; an inactive/transaction\n'
              '  report NEVER matches a game preview; an offseason interview NEVER matches an in-season\n'
              '  availability update.\n'
              '- The YES reason MUST name the single concrete shared event/action it proves.\n'
              '  \'same event\', \'same game\', \'same health status\', or \'does not contradict\' are NOT proof.\n'              '- Start the final line with YES only when every rule above passes; on ANY doubt start\n'
              '  with NO and name the doubt.\n'
              'Answer: two Step-1 lines, then a final line starting with exactly YES or NO and one short reason.')
    out = nim({'requester': REQUESTER, 'mode': 'language', 'model': VERIFY_MODEL,
               'prompt': prompt, 'max_tokens': 200}, timeout=90)
    return parse_verification(out.get('text', '').strip(), story, post)


def onstory(story, post):
    """ON-STORY probe (owner 9/28 6:08 via main): the looser algo judgment behind the
    'Latest from the feed' tier - is this post genuinely ABOUT this story's subject?
    Same NIM judge, same two-step shape, lower bar than the pairing verdict. This is
    the algo's call, never a keyword/score shortcut (algo-only verification 6:06)."""
    prompt = ('You check whether a social post is genuinely about a specific sports news story. Work in two steps.\n'
              'NEWS STORY: ' + story[:500] + '\n'
              'SOCIAL POST: ' + post[:500] + '\n'
              'Step 1: In one line each, name the story' + chr(39) + 's main subject and the post' + chr(39) + 's main subject. '
              'Ignore side mentions.\n'
              'Step 2: Answer YES only if the post' + chr(39) + 's main subject is genuinely this story' + chr(39) + 's subject - '
              'the same specific event, claim, or analysis angle, or a direct reaction to it. A different player, team, game, '
              'or storyline as the main subject: NO. Any ad, promo, ticket, viewing-schedule, or sales CTA: NO.\n'
              'The YES reason must name the concrete shared action from both inputs, not just a person or game.\n'
              'Answer: two Step-1 lines, then a final line starting with exactly YES or NO and one short reason.')
    out = nim({'requester': REQUESTER, 'mode': 'language', 'model': VERIFY_MODEL,
               'prompt': prompt, 'max_tokens': 160}, timeout=90)
    return parse_verification(out.get('text', '').strip(), story, post)

def key_news(it):
    # client resolvable: the exact link (or headline) string is the key - no hashing needed in JS
    return (it.get('link') or '') or it.get('headline', '')

def operator_author(author_name, author_username):
    import unicodedata
    who = unicodedata.normalize('NFKC', str(author_name or '') + ' ' + str(author_username or ''))
    return bool(re.search(r'\b(bets|capper|cappers|handicapp|betfair|bet99|draftkings|fanduel|kalshi|betmgm|caesars|bet365|pointsbet|betrivers|unibet|betway|polymarket|sportsbook)\b', who, re.I))

def main():
    # sync-at-all-times (user 4:27 class kill): match against the LIVE served news window,
    # not the minutes-old checkout snapshot - a stale snapshot pairs stories that have already
    # rotated out of the visible feed (0 verified slides observed 4:46 with a 52s-old map).
    news = None
    try:
        req = urllib.request.Request('https://rix-picks.com/slates/news.json?cb=' + str(int(datetime.datetime.now().timestamp())),
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36'})
        with urllib.request.urlopen(req, timeout=20) as r:
            news = json.loads(r.read().decode())
    except Exception as e:
        raise RuntimeError('live news fetch failed; keeping prior match map unchanged: ' + str(e)[:80])
    if not isinstance(news, dict) or not news.get('latest') or not news.get('generated_at'):
        raise RuntimeError('live news snapshot invalid or empty; keeping prior match map unchanged')
    x = json.load(open('slates/x_feed.json'))
    news_gen = news.get('generated_at')  # guard 5 coherence: stamp the exact news snapshot every verdict covers
    items = news.get('latest', [])
    posts = x.get('items', []) if isinstance(x, dict) else x
    # canonical publishability at generation (guard 5): the map never references a post the intake
    # gate would deny - full payload (text + author branding + url), so even a stale client holding
    # an old map cannot render an ad/promo from it. Client guards are defense-in-depth, not the gate.
    def _pub(p):
        import unicodedata
        t = unicodedata.normalize('NFKC', ' '.join([p.get('text') or '', str(p.get('author_name') or ''), str(p.get('author_username') or ''), str(p.get('url') or '')]))
        if RP_AD.search(t) or RP_TOUT.search(t):
            return False
        # sportsbook/operator brands banned at author AND handle (guard 3 Betfair class):
        # operator-authored posts are operator content by construction, whatever the text says
        return not operator_author(p.get('author_name'), p.get('author_username'))
    _pre = len(posts)
    posts = [p for p in posts if _pub(p)]
    if len(posts) != _pre:
        print('publishability vet: dropped %d ad/promo posts at generation' % (_pre - len(posts)))
    log = {'built_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'model': EMBED_MODEL, 'framework': 'urf-six-gate',
           'news_count': len(items), 'post_count': len(posts),
           'news_generated_at': news_gen, 'x_generated_at': x.get('generated_at') if isinstance(x, dict) else None,
           'pairs': {}, 'more': {}, 'nearest': {}, 'rejected': [], 'audit': {}}
    if not items or not posts:
        raise RuntimeError('empty served news or X feed; keeping prior match map unchanged')

    ntexts = [(it.get('headline', '') + ' - ' + (it.get('blurb') or ''))[:1800] for it in items]
    ptexts = [p.get('text', '')[:1800] for p in posts]
    anchors = list(LEAGUE_ANCHORS.items())
    vecs = embed_cached(ntexts + ptexts + [a[1] for a in anchors])
    # verdict cache (owner 2:48): a decided (story, post) pair never re-probes - decisions are
    # deterministic per pair, so reuse is not loosening. DEFERs are never cached (not decisions).
    try:
        vcache = json.load(open(VERD))
    except Exception:
        vcache = {}
    nv, pv = vecs[:len(ntexts)], vecs[len(ntexts):len(ntexts)+len(ptexts)]
    av = vecs[len(ntexts)+len(ptexts):]
    # relevance pass: best anchor score per post
    relevance = {}
    for j, p in enumerate(posts):
        best_league, best_score = '', 0.0
        for k, (lname, _) in enumerate(anchors):
            sc = cos(pv[j], av[k])
            if sc > best_score:
                best_league, best_score = lname, sc
        relevance[str(p.get('id'))] = {'league': best_league, 'score': round(best_score, 4),
                                       'on_topic': best_score >= RELEVANCE_FLOOR}
    log['relevance'] = relevance
    log['audit']['off_topic'] = sum(1 for r in relevance.values() if not r['on_topic'])

    probes = 0
    ons_probes = 0
    used_posts = set()  # one post = one story: a post already pinned/listed for a story is out of every other story's candidates
    latest = {}   # per story: newest ON-STORY-probe-YES post when nothing fully confirms (never-empty ruling 6:08)
    nearest = {}  # owner 5:09 (no scan placeholders): per story, the best-cosine post NOT probe-rejected -
               # the client's muted-label fallback when no verified pair exists for a visible story
    stats = {'paired': 0, 'auto': 0, 'probe_confirmed': 0, 'abstained': 0, 'probe_rejected': 0, 'latest_filled': 0}
    for i, it in enumerate(items):
        nk = key_news(it)
        t_ents = title_entities(it.get('headline') or '')
        scored = sorted(((cos(nv[i], pv[j]), j) for j in range(len(posts))), reverse=True)
        # league-first funnel (owner 3:09 architecture, all 13 leagues): matching happens WITHIN
        # the story's league. A candidate is excluded only on a KNOWN league mismatch (both sides
        # tagged, different, non-generic) - anchor uncertainty can never kill a true pair; the
        # probe remains the decider for everything that passes.
        slg = str(it.get('league') or '').upper()
        if slg and slg != 'SPORTS_GENERIC':
            scored = [(sc, j) for sc, j in scored
                      if (relevance.get(str(posts[j].get('id'))) or {}).get('league', '')
                         in ('', slg, 'SPORTS_GENERIC')]
        best = None
        verdicts = []
        confirmed = []  # every probe-confirmed candidate, score-ranked; [0] = pin, rest = verified more[]
        for score, j in candidate_order(scored, posts):
            if str(posts[j].get('id')) in used_posts:
                continue
            stale = freshness_gate(it, posts[j])
            if stale:
                verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                                 'verdict': 'REJECT', 'gate': 'freshness', 'reason': stale})
                continue
            if (RP_AD.search(ptexts[j]) or RP_AD2.search(ptexts[j]) or RP_PROMO_CAPS.search(ptexts[j])):
                verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                                 'verdict': 'REJECT', 'gate': 'scope', 'reason': 'commercial/venue ad - never a news pair (QA 5:21 false-green class)'})
                continue
            # deterministic pre-gates (eg2, owner 6:58 + guards 2/3): can only DENY
            st_reason = story_type_gate(it.get('headline') or '', ptexts[j])
            if st_reason:
                verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                                 'verdict': 'REJECT', 'gate': 'scope', 'reason': 'story-type gate (eg2): ' + st_reason})
                stats['story_type_conflicts'] = stats.get('story_type_conflicts', 0) + 1
                continue
            if t_ents and (entity_conflict(t_ents, ptexts[j], 2) or post_persons(ptexts[j], t_ents)):
                verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                                 'verdict': 'REJECT', 'gate': 'conflict',
                                 'reason': 'entity conflict (deterministic eg1): story principals absent or foreign principal in post'})
                stats['entity_conflicts'] = stats.get('entity_conflicts', 0) + 1
                continue
            if not t_ents and foreign_person_vs_title(it.get('headline') or '', ptexts[j]):
                verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                                 'verdict': 'REJECT', 'gate': 'conflict',
                                 'reason': 'foreign principal vs headline text (deterministic eg3): entity extraction found no story principals, post subject person absent from headline'})
                stats['entity_conflicts'] = stats.get('entity_conflicts', 0) + 1
                continue
            # six-gate decide() - owner 1:00/1:01 hard rule: EVERY link passes the full loop.
            # Cosine alone NEVER pairs (adversarial proof 1:03: different-team same-injury-pattern
            # scored 0.628 > old 0.62 auto-accept). Every candidate >= floor takes the LLM probe
            # (conflict gate); only probe-confirmed pairs may render.
            if score < PROBE_FLOOR:
                verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                                 'verdict': 'ABSTAIN', 'gate': 'evidence', 'reason': 'below probe floor'})
                continue
            vk = SALT + '|' + nk + '|' + str(posts[j].get('id'))
            prior = vcache.get(vk)
            if prior:
                if prior.get('verdict') == 'EXECUTE' and not reason_integrity(re.sub(r'^YES\b[\s:.-]*', '', prior.get('reason', ''), flags=re.I), ntexts[i], ptexts[j]):
                    prior = None
                    vcache.pop(vk, None)
            if prior:
                if prior.get('verdict') not in ('EXECUTE', 'REJECT') or (prior.get('verdict') == 'REJECT' and not re.match(r'^NO\b', prior.get('reason', ''), re.I)):
                    prior = None
                    vcache.pop(vk, None)
            if prior:
                if prior.get('verdict') == 'EXECUTE':
                    verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                                     'verdict': 'EXECUTE', 'gate': 'conflict', 'reason': 'probe confirmed (cached): ' + prior.get('reason', '')})
                    confirmed.append((score, j))
                    stats['probe_confirmed'] += 1
                    continue
                verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                                 'verdict': 'REJECT', 'gate': 'conflict', 'reason': 'probe rejected (cached): ' + prior.get('reason', '')})
                stats['probe_rejected'] += 1
                continue
            # PROBE: smallest falsifying test
            if probes >= MAX_PROBES:
                verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                                 'verdict': 'DEFER', 'gate': 'value', 'reason': 'probe budget exhausted'})
                break
            probes += 1
            try:
                vrd, why = verify(ntexts[i], ptexts[j])
                if vrd == 'ABSTAIN' and why.startswith('probe gave no final YES/NO') and probes < MAX_PROBES:
                    probes += 1
                    vrd, why = verify(ntexts[i], ptexts[j])
            except Exception as e:
                verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                                 'verdict': 'DEFER', 'gate': 'evidence', 'reason': 'probe failed: ' + str(e)[:80]})
                continue
            if vrd == 'EXECUTE':
                vcache[vk] = {'verdict': 'EXECUTE', 'reason': why}
                verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                                 'verdict': 'EXECUTE', 'gate': 'conflict', 'reason': 'probe confirmed: ' + why})
                confirmed.append((score, j))
                stats['probe_confirmed'] += 1
                continue
            if vrd == 'ABSTAIN':
                # equivocal YES (guard 2 parsing bug): never cached, never badged, not a reject
                verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                                 'verdict': 'ABSTAIN', 'gate': 'conflict', 'reason': why})
                stats['probe_abstained'] = stats.get('probe_abstained', 0) + 1
                continue
            vcache[vk] = {'verdict': 'REJECT', 'reason': why}
            verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                             'verdict': 'REJECT', 'gate': 'conflict', 'reason': 'probe rejected: ' + why})
            log['rejected'].append({'news_key': nk, 'headline': it.get('headline', '')[:120],
                                    'post_id': posts[j].get('id'), 'post': posts[j].get('text', '')[:120],
                                    'score': round(score, 4), 'gate': 'conflict', 'reason': why})
            stats['probe_rejected'] += 1
        confirmed.sort(key=lambda sj: posts[sj[1]].get('created_at') or posts[sj[1]].get('ts') or '', reverse=True)
        # Re-shop the final verified pool after freshness and reason gates. A pin
        # and its nearest/more candidates must come from this same qualified set.
        confirmed = [(sc, j) for sc, j in confirmed if not freshness_gate(it, posts[j])
                     and str(posts[j].get('id')) not in used_posts]
        # nearest (guard 2 class kill): NEVER unprobed cosine - only a probe-EXECUTE candidate for
        # THIS exact story may hold the fallback slot. No second probe-confirmed post -> NO nearest
        # entry; the client abstains (1:00) instead of rendering an unprobed post beside the story.
        if len(confirmed) > 1:
            _sc2, _j2 = confirmed[1]
            nearest[nk] = {'post_id': posts[_j2].get('id'), 'score': round(_sc2, 4), 'verified': True}
        if confirmed:
            best = confirmed[0]
            pin_id = str(posts[best[1]].get('id'))
            if nk in log['pairs']:
                nk = nk + '#' + str(i)  # duplicate link/headline keys must not overwrite a recorded pair
            log['pairs'][nk] = {'post_id': posts[best[1]].get('id'), 'score': round(best[0], 4),
                                'verified': True, 'verdicts': verdicts}
            stats['paired'] += 1
            used_posts.add(pin_id)
            for sc, j in confirmed[1:]:
                used_posts.add(str(posts[j].get('id')))
            if nk in nearest and str(nearest[nk]['post_id']) == pin_id:
                del nearest[nk]  # the pin IS the nearest - no fallback needed for this story
        else:
            stats['abstained'] += 1
            if verdicts:
                log['pairs'][nk] = {'post_id': None, 'score': None, 'verified': False, 'verdicts': verdicts}
            # NEVER-EMPTY ruling (owner 9/28 6:08 via main): the abstain line never renders.
            # When nothing fully confirms, the newest post the ALGO (onstory probe) judges
            # genuinely on-story fills the slide badged 'Latest from the feed'. Unprobed
            # posts, ads and other-story posts still never qualify.
            best_on = None
            for score, j in candidate_order(scored, posts)[:25]:
                if score < MORE_FLOOR or ons_probes >= MAX_ONS_PROBES:
                    break
                pid = str(posts[j].get('id'))
                if freshness_gate(it, posts[j]) or pid in used_posts or (RP_AD.search(ptexts[j]) or RP_AD2.search(ptexts[j]) or RP_PROMO_CAPS.search(ptexts[j])):
                    continue
                # pre-gates, latest bar (eg2): same story-level bar as verified - one story
                # entity, no foreign principal, story-type compatible (guard 2: badge or no badge)
                if story_type_gate(it.get('headline') or '', ptexts[j]) or latest_pick_gate(it.get('headline') or '', ptexts[j]):
                    continue
                if t_ents and (entity_conflict(t_ents, ptexts[j], 1) or post_persons(ptexts[j], t_ents)):
                    continue
                if not t_ents and foreign_person_vs_title(it.get('headline') or '', ptexts[j]):
                    continue
                ck = 'ONS|' + SALT + '|' + nk + '|' + pid
                pr2 = vcache.get(ck)
                if pr2 is not None:
                    ok2 = pr2.get('verdict') == 'EXECUTE' and reason_integrity(re.sub(r'^YES\b[\s:.-]*', '', pr2.get('reason', ''), flags=re.I), ntexts[i], ptexts[j])
                    if pr2.get('verdict') == 'EXECUTE' and not ok2:
                        vcache.pop(ck, None)
                else:
                    ons_probes += 1
                    try:
                        v2, why2 = onstory(ntexts[i], ptexts[j])
                    except Exception:
                        continue
                    ok2 = v2 == 'EXECUTE'
                    if v2 != 'ABSTAIN':  # equivocal on-story YES: never cached, never rendered
                        vcache[ck] = {'verdict': 'EXECUTE' if ok2 else 'REJECT', 'reason': why2}
                if ok2 and (best_on is None or (posts[j].get('created_at') or posts[j].get('ts') or '') > (best_on.get('created_at') or best_on.get('ts') or '')):
                    best_on = posts[j]
            if best_on:
                latest[nk] = {'post_id': best_on.get('id'), 'ts': best_on.get('created_at') or best_on.get('ts'), 'verified': False}
                used_posts.add(str(best_on.get('id')))
                stats['latest_filled'] += 1
        # "View more posts" (QA 3:53 systemic catch + owner 1:39 "very narrow"): VERIFIED-ONLY.
        # Raw cosine>=more-floor lists passed ticket ads/CS2/wrestling posts into expansions.
        # An expansion entry is now a probe-confirmed same-topic post that didn't take the pin -
        # the same six-gate discipline as the pair itself, never a looser topical list.
        log['more'][nk] = [{'post_id': posts[j].get('id'), 'score': round(sc, 4)}
                           for sc, j in confirmed[1:]][:MORE_CAP]
    # owner 1:39: topic-relatedness to news stories is the social feed's CORE admission test.
    # admit = every post related to at least one current story (verified pair or >= more floor).
    # 1:48 tighten (his "very narrow"): admission floor = PROBE floor (0.48), not the looser
    # view-more floor (0.42) - vague chatter that scraped 0.42 rendered ("prank" post QA pass).
    # A post renders socially only when it is related enough to a current story to merit a probe.
    admit = set()
    for v in log['pairs'].values():
        if (v or {}).get('post_id'):
            admit.add(str(v['post_id']))
    for lst in log['more'].values():
        for e in (lst or []):
            pid = str(e.get('post_id') or '')
            # combined gate (QA 1:49): relatedness floor AND sports-relevance - off-topic posts
            # that scrape the relatedness floor (Avengers podcast 0.43, prank 0.43) never admit
            if pid and (e.get('score') or 0) >= PROBE_FLOOR and (relevance.get(pid) or {}).get('on_topic'):
                admit.add(pid)
    for v in latest.values():
        admit.add(str(v['post_id']))
    log['admit'] = sorted(admit)
    log['nearest'] = nearest
    log['latest'] = latest
    stats['paired'] = sum(1 for v in log['pairs'].values() if (v or {}).get('verified'))
    log['audit'] = {'thresholds': {'auto_accept': AUTO_ACCEPT, 'probe_floor': PROBE_FLOOR, 'more_floor': MORE_FLOOR},
                    'probes_used': probes, **stats,
                    'coverage_pct': round(100.0 * stats['paired'] / max(1, len(items)), 1)}
    cur_keys = {key_news(it) for it in items}
    cur_pids = {str(pp.get('id')) for pp in posts}
    vcache = {k: v for k, v in vcache.items()
              if k.split('|')[-2] in cur_keys and k.split('|')[-1] in cur_pids}
    # guard 5 bootstrap kill: the version signal rides INSIDE soc_match.json, which every
    # rtPoll tick already fetches - a behind client sees client_build > its own build and
    # self-updates even if it predates the build.json mechanism. No viewer stranded again.
    try:
        log['client_build'] = json.load(open('slates/build.json')).get('build')
    except Exception:
        pass
    json.dump(vcache, open(VERD, 'w'))
    viol = enforce_uniqueness(log)
    if viol:
        print(f'uniqueness sweep stripped {len(viol)} cross-story repeats', file=sys.stderr)
    # Recompute admission from the surviving assignments. A post stripped for
    # cross-story reuse cannot remain admitted by a pre-sweep stale ID.
    surviving = {str(v['post_id']) for v in log['pairs'].values() if (v or {}).get('post_id')}
    surviving.update(str(e['post_id']) for lst in log['more'].values() for e in lst if e.get('post_id'))
    surviving.update(str(v['post_id']) for v in log['latest'].values() if v.get('post_id'))
    log['admit'] = sorted(set(log['admit']) & surviving)
    json.dump(log, open('slates/soc_match.json', 'w'))
    print('soc_match built:', json.dumps(log['audit']))
    return 0

if __name__ == '__main__':
    sys.exit(main())
