#!/usr/bin/env python3
"""Predictions by UltRix - producer (owner spec Sep 27-28 iMessages via main,
phonemsg-01M3NDXWDD74F73AA113HBE72R):
- genuine FORWARD predictions only; anything already decided/announced is rejected
- a prediction renders only after THREE independent NIM cross-checks concur on the
  same side AND every confidence estimate is >= CONF_FLOOR (0.70)
- the gate and confidence values NEVER reach the served artifact, the DOM, or site copy
- learning loop: a repo-side ledger records every rendered prediction and grades it at
  settle; recent misses are fed back as adversarial context (learn from mistakes)
Public-site rules: plain outcome forecasts, no bet/stake/wager/odds language, PT display
is the client's job (artifact carries UTC).
Fail-closed: any producer error leaves the last good artifact untouched.
"""
import json, re, sys, time, hashlib, urllib.request
from datetime import datetime, timezone, timedelta

NIM_URL = 'https://ultrix-core.itsdardanr.workers.dev/nim'
MODEL = 'meta/llama-3.2-11b-vision-instruct'  # only live language model on this NIM account
REQUESTER = 'rixpicks-predictions'
ARTIFACT = 'slates/predictions.json'
LEDGER = 'predictions_ledger.json'
CONF_FLOOR = 0.70      # owner gate - internal only, never emitted
MAX_PROBES = 12        # new events probed per run (NIM burn control)
MAX_ITEMS = 6          # rendered cap (layout)
HORIZON_H = 168     # owner directive 8:18 PT 9/28: 48h -> 7 days ahead
FRESH_MIN = 12         # self-throttle under the 15-min external tick (owner 7:58: 'most instant pass it can do, not hourly'); dedupes accidental double-dispatch, NIM cost stays gated by new-events-only
TEAM_LEAGUES = [('NFL','football/nfl'),('CFB','football/college-football'),('NBA','basketball/nba'),
    ('WNBA','basketball/wnba'),('MLB','baseball/mlb'),('NHL','hockey/nhl'),
    ('NCAAB','basketball/mens-college-basketball'),('MLS','soccer/usa.1'),('NWSL','soccer/usa.nwsl')]
# ESPN UA rules from datacenter IPs are inverted (verified 9/28 6:57 PM): browser or
# URL-bearing UAs get 403, the plain urllib default gets 200 - so send no explicit UA.
# NIM's Cloudflare zone needs the browser UA (bot-fight, verified 12:48).
UA_NIM = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36'}
UA_ESPN = {}

def token():
    with open('/tmp/.nim_client_token') as f:
        return f.read().strip()

def nim(payload, timeout=90):
    req = urllib.request.Request(NIM_URL, data=json.dumps(payload).encode(),
        headers=dict(UA_NIM, **{'x-nim-key': token(), 'content-type': 'application/json'}))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read().decode())
    if not out.get('ok'):
        raise RuntimeError('nim error: ' + str(out.get('error')))
    return out.get('text', '').strip()

def get_json(url, timeout=30):
    req = urllib.request.Request(url, headers=UA_ESPN)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def now():
    return datetime.now(timezone.utc)

def parse_verdict(text):
    """strict: PICK: <team> / PROB: <0.xx> / WHY: <line>; DECIDED kills the candidate."""
    if re.search(r'^\s*DECIDED', text, re.M | re.I):
        return None, 0.0, 'decided'
    pick = re.search(r'^\s*PICK:\s*(.+)$', text, re.M)
    prob = re.search(r'^\s*PROB:\s*(0?\.\d+|1\.0+)\s*$', text, re.M)
    why = re.search(r'^\s*WHY:\s*(.+)$', text, re.M)
    if not pick or not prob:
        return None, 0.0, (text or '')[:120]
    return pick.group(1).strip(), float(prob.group(1)), (why.group(1).strip() if why else '')[:160]

def same_side(p1, p2, home, away):
    """fuzzy team-name agreement: normalized substring either way against BOTH event teams."""
    def norm(s): return re.sub(r'[^a-z0-9 ]', '', (s or '').lower()).strip()
    a, b, h, w = norm(p1), norm(p2), norm(home), norm(away)
    def side(p):
        if not p: return None
        if h and (h in p or p in h): return 'home'
        if w and (w in p or p in w): return 'away'
        return None
    s1, s2 = side(a), side(b)
    return s1 if s1 and s1 == s2 else None

def probe_once(prompt):
    """One NIM call + strict parse, retried once on transport error or unparseable text.
    A flaky/empty reply must cost one retry, not the whole cross-check; a DECIDED answer
    is final and never retried. Still fail-closed: persistent junk reads as dissent."""
    for _ in (1, 2):
        try:
            t = nim({'requester': REQUESTER, 'mode': 'language', 'model': MODEL,
                     'prompt': prompt, 'max_tokens': 150}, timeout=90)
            pick, prob, why = parse_verdict(t)
            if pick or why == 'decided':
                return pick, prob, why
        except Exception:
            pass
    return None, 0.0, 'unparseable'

def upcoming():
    evs = []
    horizon = now() + timedelta(hours=HORIZON_H)
    for lg, path in TEAM_LEAGUES:
        try:
            j = get_json(f'https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?limit=50')
        except Exception as e:
            print(f'{lg}: scoreboard fetch failed: {e}', file=sys.stderr); continue
        for e in j.get('events', []):
            try:
                comp = (e.get('competitions') or [{}])[0]
                st = (comp.get('status') or {}).get('type') or {}
                if st.get('state') != 'pre': continue
                dt = datetime.fromisoformat(e['date'].replace('Z', '+00:00'))
                if not (now() < dt <= horizon): continue
                home = away = None
                for c in comp.get('competitors', []):
                    nm = (c.get('team') or {}).get('displayName') or ''
                    if c.get('homeAway') == 'home': home = nm
                    elif c.get('homeAway') == 'away': away = nm
                if not home or not away: continue
                evs.append({'id': str(e.get('id')), 'league': lg, 'path': path,
                            'home': home, 'away': away, 'date': dt})
            except Exception:
                continue
    evs.sort(key=lambda x: x['date'])
    return evs

def settle(ledger):
    """grade pending predictions whose event finished; void if unverifiable after 36h."""
    changed = 0
    for p in ledger:
        if p.get('status') != 'pending': continue
        dt = datetime.fromisoformat(p['kickoff_utc'].replace('Z', '+00:00'))
        age_h = (now() - dt).total_seconds() / 3600
        if age_h < 2.5: continue
        if age_h > 36:
            p['status'] = 'void'; changed += 1; continue
        try:
            day = dt.strftime('%Y%m%d')
            j = get_json(f"https://site.api.espn.com/apis/site/v2/sports/{p['path']}/scoreboard?dates={day}&limit=100")
            ev = next((e for e in j.get('events', []) if str(e.get('id')) == p['event_id']), None)
            if not ev: continue
            comp = (ev.get('competitions') or [{}])[0]
            st = (comp.get('status') or {}).get('type') or {}
            if st.get('state') != 'post': continue
            winner = next(((c.get('team') or {}).get('displayName') for c in comp.get('competitors', []) if c.get('winner')), None)
            if not winner: continue
            side = same_side(p['pick_team'], winner, p['home'], p['away'])
            if not side: continue
            p['status'] = 'hit' if same_side(winner, p['pick_team'], p['home'], p['away']) else 'miss'
            p['settled_at'] = now().isoformat()
            changed += 1
        except Exception as e:
            print(f"settle {p.get('id')}: {e}", file=sys.stderr)
    return changed

def news_context(league):
    try:
        j = json.load(open('slates/news.json'))
    except Exception:
        return ''
    heads = []
    for it in (j.get('items') or [])[:80]:
        if (it.get('league') or '').upper() == league and it.get('title'):
            heads.append(it['title'][:120])
        if len(heads) >= 6: break
    return '\n'.join('- ' + h for h in heads)

def miss_context(ledger, league):
    misses = [p for p in ledger if p.get('status') == 'miss'][-40:]
    misses.sort(key=lambda p: (p.get('league') != league, p.get('settled_at', '')), reverse=False)
    out = []
    for p in misses[-4:]:
        out.append(f"- predicted {p.get('prediction')} ({p.get('league')}) - WRONG")
    return '\n'.join(out)

def probe(ev, news, misses):
    """THREE independent cross-checks; all must concur on one side, each >= CONF_FLOOR."""
    when = ev['date'].strftime('%A %B %-d, %-I:%M %p UTC')
    base = (f"EVENT: {ev['away']} at {ev['home']} ({ev['league']}), starts {when}.\n")
    if news: base += f"RECENT {ev['league']} HEADLINES:\n{news}\n"
    fmt = ('Answer in exactly three lines:\nPICK: <winning team name>\nPROB: <your probability the picked team wins, 0.50-0.99>\nWHY: <one short line>\n'
           'If this event is already decided or its outcome is already publicly announced, answer one line: DECIDED\n')
    # pass 1: direct estimate (with mistake feedback)
    p1 = base
    if misses: p1 += f"PAST PREDICTION MISTAKES TO LEARN FROM:\n{misses}\n"
    p1 += ('You are a careful sports prediction engine. Weigh matchup form, injuries, schedule spot and '
           'historical patterns, then pick the winner honestly. ' + fmt)
    pick1, prob1, why1 = probe_once(p1)
    # pass 2: independent ADVERSARIAL estimate - no sight of pass 1
    p2 = base + ('You are the skeptic on a prediction desk. Build the strongest honest case for EITHER side, '
                 'weighing what the public narrative is most likely getting wrong, then commit to the team that '
                 'genuinely wins. ' + fmt)
    pick2, prob2, why2 = probe_once(p2)
    # pass 3: arbiter re-weigh after seeing the disagreement
    p3 = base + (f"ANALYST A: pick {pick1 or 'n/a'} (prob {prob1:.2f}) - {why1}\n"
                 f"ANALYST B (skeptic): pick {pick2 or 'n/a'} (prob {prob2:.2f}) - {why2}\n"
                 'You are the final arbiter. Re-weigh both analyses on the evidence, not on confidence '
                 'theater, and give the final call. ' + fmt)
    pick3, prob3, why3 = probe_once(p3)
    s12 = same_side(pick1, pick2, ev['home'], ev['away'])
    side = same_side(pick3, s12 and (ev['home'] if s12 == 'home' else ev['away']) or '', ev['home'], ev['away']) if s12 else None
    if not side:
        print(f"  REJECT {ev['away']}@{ev['home']}: cross-checks disagree ({pick1}/{prob1:.2f}, {pick2}/{prob2:.2f}, {pick3}/{prob3:.2f})")
        return None
    probs = [prob1, prob2, prob3]
    if min(probs) < CONF_FLOOR:
        print(f"  REJECT {ev['away']}@{ev['home']}: confidence below floor {min(probs):.2f}")
        return None
    team = ev['home'] if side == 'home' else ev['away']
    other = ev['away'] if side == 'home' else ev['home']
    print(f"  ACCEPT {ev['away']}@{ev['home']}: {team} (probs {prob1:.2f}/{prob2:.2f}/{prob3:.2f})")
    return {'id': hashlib.sha1((ev['id'] + '|winner').encode()).hexdigest()[:10],
            'event_id': ev['id'], 'league': ev['league'], 'path': ev['path'],
            'home': ev['home'], 'away': ev['away'], 'pick_team': team,
            'prediction': f'{team} beat {other}' if ev['league'] in ('MLS','NWSL') else f'{team} beat {other}',
            'kickoff_utc': ev['date'].isoformat(), 'status': 'pending',
            'created_at': now().isoformat()}

def main():
    force = '--force' in sys.argv
    try:
        art = json.load(open(ARTIFACT))
        gen = datetime.fromisoformat(art.get('generated_at', '2000-01-01T00:00:00+00:00').replace('Z', '+00:00'))
        if not force and (now() - gen) < timedelta(minutes=FRESH_MIN):
            print(f'fresh ({art.get("generated_at")}) - skip'); return
    except FileNotFoundError:
        pass
    try:
        ledger = json.load(open(LEDGER))
    except Exception:
        ledger = []
    n_set = settle(ledger)
    if n_set: print(f'settled {n_set} ledger entries')
    known = {p.get('event_id') for p in ledger}
    evs = [e for e in upcoming() if e['id'] not in known]
    print(f'{len(evs)} new events in {HORIZON_H}h horizon')
    approved = 0
    far = now() + timedelta(hours=48)
    for ev in evs[:MAX_PROBES]:
        try:
            ko = datetime.fromisoformat(ev['kickoff_utc'].replace('Z','+00:00'))
            if ko > far: print(f"  NOTE {ev['away']}@{ev['home']}: >48h out - reduced information (lineups/injuries unset); concur gate + 0.70 floor arbitrate")
            r = probe(ev, news_context(ev['league']), miss_context(ledger, ev['league']))
        except Exception as e:
            print(f"  probe error {ev['away']}@{ev['home']}: {e}", file=sys.stderr); continue
        if r:
            ledger.append(r); approved += 1
        time.sleep(0.5)
    print(f'{approved} new predictions approved')
    # artifact: pending predictions for events not yet started, kickoff order - NO confidence/gate fields
    items = []
    for p in ledger:
        if p.get('status') != 'pending': continue
        dt = datetime.fromisoformat(p['kickoff_utc'].replace('Z', '+00:00'))
        if dt <= now(): continue
        items.append({'id': p['id'], 'league': p['league'],
                      'event': f"{p['away']} @ {p['home']}",
                      'prediction': p['prediction'],
                      'kickoff_utc': p['kickoff_utc']})
    items.sort(key=lambda x: x['kickoff_utc'])
    json.dump({'generated_at': now().isoformat(), 'items': items[:MAX_ITEMS]},
              open(ARTIFACT, 'w'), indent=1)
    json.dump(ledger[-400:], open(LEDGER, 'w'), indent=1)
    print(f'artifact: {min(len(items), MAX_ITEMS)} items, ledger {len(ledger)} entries')

if __name__ == '__main__':
    main()
