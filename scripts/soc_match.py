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
PROMPT_VERSION = 'v5-story-relationship'  # probe wording is decision-changing: version MUST salt the verdict cache
SALT = '|'.join([str(AUTO_ACCEPT), str(PROBE_FLOOR), str(MORE_FLOOR), EMBED_MODEL, VERIFY_MODEL, PROMPT_VERSION])

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
              '- An exact quote of the story' + chr(39) + 's headline or story URL with no contradiction: YES.\n'
              '- A promo/bonus-bet article matches ONLY posts identifying THAT brand and THAT offer; other '
              'sportsbooks, deposit bonuses, or game commentary: NO.\n'
              '- A betting preview or picks article matches ONLY posts discussing THAT specific pick or odds '
              'line; an unrelated pick or a sales CTA: NO.\n'
              '- Radio plugs, station kickoff promos, venue promotions, ticket resale, food or drink specials, '
              'viewing schedules, and sales CTAs are NEVER about the news story: NO.\n'
              '- A different player, team, game, or storyline as the MAIN subject is NOT a match.\n'
              'Answer: two Step-1 lines, then a final line starting with exactly YES or NO and one short reason.')
    out = nim({'requester': REQUESTER, 'mode': 'language', 'model': VERIFY_MODEL,
               'prompt': prompt, 'max_tokens': 200}, timeout=90)
    text = out.get('text', '').strip()
    # v3: verdict lives on the LAST non-empty line (step-1 subject lines come first)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    verdict_line = ''
    for l in reversed(lines):
        if l.upper().startswith('YES') or l.upper().startswith('NO'):
            verdict_line = l
            break
    if not verdict_line:
        verdict_line = lines[-1] if lines else ''
    return verdict_line.upper().startswith('YES'), (verdict_line or text)[:160]


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
              'Answer: two Step-1 lines, then a final line starting with exactly YES or NO and one short reason.')
    out = nim({'requester': REQUESTER, 'mode': 'language', 'model': VERIFY_MODEL,
               'prompt': prompt, 'max_tokens': 160}, timeout=90)
    text = out.get('text', '').strip()
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    verdict_line = ''
    for l in reversed(lines):
        if l.upper().startswith('YES') or l.upper().startswith('NO'):
            verdict_line = l
            break
    if not verdict_line:
        verdict_line = lines[-1] if lines else ''
    return verdict_line.upper().startswith('YES'), (verdict_line or text)[:160]

def key_news(it):
    # client resolvable: the exact link (or headline) string is the key - no hashing needed in JS
    return (it.get('link') or '') or it.get('headline', '')

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
        print('live news fetch failed (%s) - falling back to checkout snapshot' % str(e)[:80])
    if not isinstance(news, dict) or not news.get('latest'):
        news = json.load(open('slates/news.json'))
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
        return not re.search(r'\b(bets|capper|cappers|handicapp|betfair|bet99|draftkings|fanduel|kalshi|betmgm|caesars|bet365|pointsbet|betrivers|unibet|betway|polymarket|sportsbook)\\b', unicodedata.normalize('NFKC', str(p.get('author_name') or '') + ' ' + str(p.get('author_username') or '')), re.I)
    _pre = len(posts)
    posts = [p for p in posts if _pub(p)]
    if len(posts) != _pre:
        print('publishability vet: dropped %d ad/promo posts at generation' % (_pre - len(posts)))
    log = {'built_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'model': EMBED_MODEL, 'framework': 'urf-six-gate',
           'news_count': len(items), 'post_count': len(posts),
           'news_generated_at': news_gen,
           'pairs': {}, 'more': {}, 'nearest': {}, 'rejected': [], 'audit': {}}
    if not items or not posts:
        log['audit']['aborted'] = 'empty feed'
        json.dump(log, open('slates/soc_match.json', 'w'))
        return 0

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
        for score, j in scored[:TOP_CANDIDATES]:
            if str(posts[j].get('id')) in used_posts:
                continue
            if (RP_AD.search(ptexts[j]) or RP_AD2.search(ptexts[j]) or RP_PROMO_CAPS.search(ptexts[j])):
                verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                                 'verdict': 'REJECT', 'gate': 'scope', 'reason': 'commercial/venue ad - never a news pair (QA 5:21 false-green class)'})
                continue
            # six-gate decide() - owner 1:00/1:01 hard rule: EVERY link passes the full loop.
            # Cosine alone NEVER pairs (adversarial proof 1:03: different-team same-injury-pattern
            # scored 0.628 > old 0.62 auto-accept). Every candidate >= floor takes the LLM probe
            # (conflict gate); only probe-confirmed pairs may render.
            if score < PROBE_FLOOR:
                verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                                 'verdict': 'ABSTAIN', 'gate': 'evidence', 'reason': 'below probe floor'})
                break
            vk = SALT + '|' + nk + '|' + str(posts[j].get('id'))
            prior = vcache.get(vk)
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
                ok, why = verify(ntexts[i], ptexts[j])
            except Exception as e:
                verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                                 'verdict': 'DEFER', 'gate': 'evidence', 'reason': 'probe failed: ' + str(e)[:80]})
                continue
            if ok:
                vcache[vk] = {'verdict': 'EXECUTE', 'reason': why}
                verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                                 'verdict': 'EXECUTE', 'gate': 'conflict', 'reason': 'probe confirmed: ' + why})
                confirmed.append((score, j))
                stats['probe_confirmed'] += 1
                continue
            vcache[vk] = {'verdict': 'REJECT', 'reason': why}
            verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                             'verdict': 'REJECT', 'gate': 'conflict', 'reason': 'probe rejected: ' + why})
            log['rejected'].append({'news_key': nk, 'headline': it.get('headline', '')[:120],
                                    'post_id': posts[j].get('id'), 'post': posts[j].get('text', '')[:120],
                                    'score': round(score, 4), 'gate': 'conflict', 'reason': why})
            stats['probe_rejected'] += 1
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
            for score, j in scored[:25]:
                if score < MORE_FLOOR or ons_probes >= MAX_ONS_PROBES:
                    break
                pid = str(posts[j].get('id'))
                if pid in used_posts or (RP_AD.search(ptexts[j]) or RP_AD2.search(ptexts[j]) or RP_PROMO_CAPS.search(ptexts[j])):
                    continue
                ck = 'ONS|' + SALT + '|' + nk + '|' + pid
                pr2 = vcache.get(ck)
                if pr2 is not None:
                    ok2 = pr2.get('verdict') == 'EXECUTE'
                else:
                    ons_probes += 1
                    try:
                        ok2, why2 = onstory(ntexts[i], ptexts[j])
                    except Exception:
                        continue
                    vcache[ck] = {'verdict': 'EXECUTE' if ok2 else 'REJECT', 'reason': why2}
                if ok2 and (best_on is None or (posts[j].get('ts') or '') > (best_on.get('ts') or '')):
                    best_on = posts[j]
            if best_on:
                latest[nk] = {'post_id': best_on.get('id'), 'ts': best_on.get('ts'), 'verified': False}
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
    json.dump(log, open('slates/soc_match.json', 'w'))
    print('soc_match built:', json.dumps(log['audit']))
    return 0

if __name__ == '__main__':
    sys.exit(main())
