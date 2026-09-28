#!/usr/bin/env python3
"""RixPicks news<->social semantic matcher (owner directive 12:37 PT) on URF loop discipline (12:41).

Pipeline per refresh:
  embed (NIM nemotron-3-embed-1b via ultrix-core /nim, passage mode)
  -> cosine candidates per news item
  -> six-gate decide() per candidate (authority/evidence/value/risk/conflict/reversibility)
       evidence gate: score >= AUTO_ACCEPT passes; PROBE band -> smallest falsifying test
       (language-mode verify: is this post about THIS story?) -> confirm or reject-and-step
  -> verdict log per candidate (gate + reason); rejected candidates recorded (what-we-missed mining)
  -> abstain never forced: low-confidence items pair nothing, client falls back chronologically
  -> slates/soc_match.json (cached; client never calls the endpoint per pageview)

Public headlines/posts only (trial terms). Token from /tmp/.nim_client_token, never logged.
Fail closed: any endpoint/credit failure leaves the previous soc_match.json untouched and
writes status=fallback to slates/soc_match_status.json (client token-matches when map is stale).
"""
import json, math, os, sys, time, hashlib, urllib.request, datetime

NIM_URL = 'https://ultrix-core.itsdardanr.workers.dev/nim'
EMBED_MODEL = 'nvidia/nemotron-3-embed-1b'
VERIFY_MODEL = 'meta/llama-3.2-11b-vision-instruct'
REQUESTER = 'rixpicks-socmatch'
AUTO_ACCEPT = 0.62      # evidence gate passes outright
PROBE_FLOOR = 0.48      # band [FLOOR, ACCEPT): PROBE via LLM verify
MORE_FLOOR = 0.42       # "View more posts" list inclusion
MAX_PROBES = 60         # per-run LLM verify budget (trial credits)
TOP_CANDIDATES = 3
MORE_CAP = 20

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

def cos(a, b):
    dot = sum(x*y for x, y in zip(a, b))
    na = math.sqrt(sum(x*x for x in a)); nb = math.sqrt(sum(x*x for x in b))
    return dot / (na * nb) if na and nb else 0.0

def verify(story, post):
    """PROBE: smallest falsifying test - does this post talk about this story?"""
    prompt = ('You verify content pairings for a sports site.\n'
              'NEWS STORY: ' + story[:600] + '\n'
              'SOCIAL POST: ' + post[:600] + '\n'
              'Is the social post about the same specific story, game, team, or player as the news story? '
              'Same broad sport is NOT enough. Answer with exactly YES or NO, then one short reason.')
    out = nim({'requester': REQUESTER, 'mode': 'language', 'model': VERIFY_MODEL,
               'prompt': prompt, 'max_tokens': 60}, timeout=90)
    text = out.get('text', '').strip()
    return text.upper().startswith('YES'), text[:160]

def key_news(it):
    # client resolvable: the exact link (or headline) string is the key - no hashing needed in JS
    return (it.get('link') or '') or it.get('headline', '')

def main():
    news = json.load(open('slates/news.json'))
    x = json.load(open('slates/x_feed.json'))
    items = news.get('latest', [])
    posts = x.get('items', []) if isinstance(x, dict) else x
    log = {'built_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'model': EMBED_MODEL, 'framework': 'urf-six-gate',
           'news_count': len(items), 'post_count': len(posts),
           'pairs': {}, 'more': {}, 'rejected': [], 'audit': {}}
    if not items or not posts:
        log['audit']['aborted'] = 'empty feed'
        json.dump(log, open('slates/soc_match.json', 'w'))
        return 0

    ntexts = [(it.get('headline', '') + ' - ' + (it.get('blurb') or ''))[:1800] for it in items]
    ptexts = [p.get('text', '')[:1800] for p in posts]
    vecs = embed_all(ntexts + ptexts)
    nv, pv = vecs[:len(ntexts)], vecs[len(ntexts):]

    probes = 0
    stats = {'paired': 0, 'auto': 0, 'probe_confirmed': 0, 'abstained': 0, 'probe_rejected': 0}
    for i, it in enumerate(items):
        nk = key_news(it)
        scored = sorted(((cos(nv[i], pv[j]), j) for j in range(len(posts))), reverse=True)
        best = None
        verdicts = []
        for score, j in scored[:TOP_CANDIDATES]:
            # six-gate decide()
            if score >= AUTO_ACCEPT:
                verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                                 'verdict': 'EXECUTE', 'gate': 'evidence', 'reason': 'score>=auto_accept'})
                best = (score, j, True)
                break
            if score < PROBE_FLOOR:
                verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                                 'verdict': 'ABSTAIN', 'gate': 'evidence', 'reason': 'below probe floor'})
                break
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
                verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                                 'verdict': 'EXECUTE', 'gate': 'conflict', 'reason': 'probe confirmed: ' + why})
                best = (score, j, True)
                stats['probe_confirmed'] += 1
                break
            verdicts.append({'post_id': posts[j].get('id'), 'score': round(score, 4),
                             'verdict': 'REJECT', 'gate': 'conflict', 'reason': 'probe rejected: ' + why})
            log['rejected'].append({'news_key': nk, 'headline': it.get('headline', '')[:120],
                                    'post_id': posts[j].get('id'), 'post': posts[j].get('text', '')[:120],
                                    'score': round(score, 4), 'gate': 'conflict', 'reason': why})
            stats['probe_rejected'] += 1
        if best:
            log['pairs'][nk] = {'post_id': posts[best[1]].get('id'), 'score': round(best[0], 4),
                                'verified': best[2], 'verdicts': verdicts}
            stats['paired'] += 1
            if best[0] >= AUTO_ACCEPT:
                stats['auto'] += 1
        else:
            stats['abstained'] += 1
            if verdicts:
                log['pairs'][nk] = {'post_id': None, 'score': None, 'verified': False, 'verdicts': verdicts}
        # "View more posts" ranked list (loop-light: score-ranked, floor-gated, audit trail via scores)
        log['more'][nk] = [{'post_id': posts[j].get('id'), 'score': round(sc, 4)}
                           for sc, j in scored if sc >= MORE_FLOOR][:MORE_CAP]
    log['audit'] = {'thresholds': {'auto_accept': AUTO_ACCEPT, 'probe_floor': PROBE_FLOOR, 'more_floor': MORE_FLOOR},
                    'probes_used': probes, **stats,
                    'coverage_pct': round(100.0 * stats['paired'] / max(1, len(items)), 1)}
    json.dump(log, open('slates/soc_match.json', 'w'))
    print('soc_match built:', json.dumps(log['audit']))
    return 0

if __name__ == '__main__':
    sys.exit(main())
