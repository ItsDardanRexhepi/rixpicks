#!/usr/bin/env python3
"""UltRix LEARNING ENGINE brief composer (his 12:32 AM standing rule, verbatim:
"picks go through KB and learning engine and then the system actually gives you what to post there").
Every daily brief and per-pick note is ENGINE OUTPUT composed from the system's own verified data:
  - sheet picks tab (graded rows, verify-twice via eod_day_close helpers)
  - ESPN summary API (event URL carried in the row's note provenance): scoring plays,
    win-probability series, box-score leaders, closing moneyline (pickcenter), recap headline
  - published-card odds for the units math
NO hand summaries. Every claim traces to a fetched system record; missing data is stated as a
gap, never invented. Depth target: per-pick CLV, in-game sweat (min win prob), decisive play,
read verdict (controlled / sweat / bad beat / read failure) - comparable to Sep 25-26 rows."""
import json, re, urllib.request, datetime, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import eod_day_close as eod

def fetch_json(url, timeout=15):
    return json.load(urllib.request.urlopen(url, timeout=timeout))

def implied(american):
    a = int(american)
    return (abs(a)/(abs(a)+100)) if a < 0 else (100/(a+100))

def card_american(locked):
    m = re.search(r'(-?\d{3,4}) published card', str(locked)) or re.search(r'^(-?\d{3,4})\b', str(locked))
    return int(m.group(1)) if m else None

def espn_url(note):
    m = re.search(r'https://site\.api\.espn\.com/\S+', str(note))
    return m.group(0).rstrip(' ;') if m else None

def our_side(summary, pick_name, side=None):
    """Return (side, team_name, competitors) of the picked team; (None, None, competitors) when
    the pick names no single team - a gap the note states, never a guess. An explicit card side
    (home/away) wins. Otherwise only the pick's own words count: the text before any '@'/'vs'/
    'at' opponent clause, matched on whole words - 'Bengals ML @ Steelers' is the Bengals (away),
    never the home team named after the '@' (Sep 27: the home-first substring hit published the
    Steelers' and Giants' closing lines and win probability as the Bengals' and Dodgers').
    A total (Over/Under) has no team side."""
    comp = summary.get('header',{}).get('competitions',[{}])[0]
    comps = comp.get('competitors',[])
    if side in ('home', 'away'):
        c = next((c for c in comps if c.get('homeAway') == side), None)
        return (side, c.get('team',{}).get('displayName'), comps) if c else (None, None, comps)
    head = re.split(r'\s(?:@|vs\.?|v\.?|at)\s', pick_name or '', maxsplit=1, flags=re.I)[0].lower()
    if re.match(r'\s*(over|under)\b', head):
        return None, None, comps
    hits = [c for c in comps if any(n and re.search(r'\b' + re.escape(n.lower()) + r'\b', head)
                                     for n in (c.get('team',{}).get('displayName',''), c.get('team',{}).get('shortDisplayName',''),
                                               c.get('team',{}).get('name',''), c.get('team',{}).get('abbreviation','')))]
    if len(hits) != 1:
        return None, None, comps
    return hits[0].get('homeAway'), hits[0].get('team',{}).get('displayName'), comps

def pick_note(p, summary):
    """Engine per-pick note. Every field from system data; gaps stated."""
    res = eod.result_of(p); url = espn_url(p.get('note',''))
    card = card_american(p.get('locked_odds',''))
    u = eod.units_delta(p)
    units_txt = f"{'+' if u>=0 else ''}{round(u,2)}u on {p.get('units','5u')} at the {card} published card price"
    if not summary:
        return f"{units_txt}. ESPN summary unavailable - game-state depth not on file.", {}
    side, team, comps = our_side(summary, p.get('pick',''), p.get('side'))
    facts = {'clv_pp': None, 'min_wp': None, 'headline': None}
    # CLV: card vs closing moneyline (pickcenter)
    clv_txt = 'no closing moneyline on file'
    pc = (summary.get('pickcenter') or [{}])
    ml = None
    if pc and side:
        ho = pc[0].get('homeTeamOdds',{}).get('moneyLine'); ao = pc[0].get('awayTeamOdds',{}).get('moneyLine')
        ml = ho if side=='home' else ao
        prov = pc[0].get('provider',{}).get('name','book')
        if prov.lower().replace(' ','') in ('draftkings',): prov='DK'
    if ml is not None and card is not None:
        clv = round((implied(ml)-implied(card))*100, 1)
        facts['clv_pp'] = clv
        clv_txt = f"closed {prov} {ml} vs card {card} - CLV {'+' if clv>=0 else ''}{clv}pp"
        if clv <= -20: clv_txt += f" (market flipped the pick to {ml} by close)"
        facts['market_flip'] = clv <= -20
    # sweat: win-probability series for our side
    wp = summary.get('winprobability') or []
    sweat_txt = 'no in-game win-probability feed on file'
    verdict = ''
    if wp and side:
        probs = [w.get('homeWinPercentage') for w in wp if w.get('homeWinPercentage') is not None]
        if probs:
            ours = [pr if side=='home' else 1-pr for pr in probs]
            mn, mx = min(ours), max(ours)
            facts['min_wp'] = round(mn,3); facts['max_wp'] = round(mx,3)
            def dp(x): return '99%+' if x>=0.995 else ('<1%' if x<0.005 else '{:.0%}'.format(x))
            if res=='win':
                if mn < 0.10: state = 'stolen comeback - win probability touched {} and it won anyway'.format(dp(mn))
                elif mn < 0.55: state = 'sweated - win probability dipped to {}'.format(dp(mn))
                elif mn < 0.75: state = 'controlled'
                else: state = 'wire-to-wire control'
                verdict = f"read confirmed - {state}"
                sweat_txt = f"in-game win probability never below {dp(mn)}" if mn>=0.55 else f"in-game win probability bottom {dp(mn)}"
            else:
                if mx >= 0.75: verdict = "bad beat - win probability peaked at {} before the collapse".format(dp(mx))
                elif mx >= 0.5: verdict = "coin-flip that broke wrong - peaked at {}".format(dp(mx))
                else: verdict = "read failed - never held the win-probability edge (peaked at {})".format(dp(mx))
                sweat_txt = f"in-game win probability peaked at {dp(mx)}"
    # decisive play: ESPN's own recap headline
    headline = (summary.get('article') or {}).get('headline','')
    facts['headline'] = headline
    def cap(t): return t[:1].upper()+t[1:] if t else t
    dec_txt = f"Decisive: {headline}" if headline else ''
    note = f"{units_txt}. {cap(clv_txt)}. {cap(sweat_txt)}. {cap(verdict)}. {dec_txt}".strip()
    return note, facts

def compose_brief(date, graded, notes_facts):
    w = sum(1 for p in graded if eod.result_of(p)=='win'); l = len(graded)-w
    units = round(sum(eod.units_delta(p) for p in graded), 2)
    parts = [f"{w}-{l}, {'+' if units>=0 else ''}{units}u on the day across {len(graded)} carded picks."]
    clvs = [f['clv_pp'] for _, f in notes_facts if f.get('clv_pp') is not None]
    if clvs:
        parts.append(f"Closing-line value on the {len(clvs)} picks with a closing line on file: avg {'+' if sum(clvs)/len(clvs)>=0 else ''}{round(sum(clvs)/len(clvs),1)}pp ({', '.join(('+' if c>=0 else '')+str(c) for c in clvs)}pp).")
    wins = [(p,f) for p,f in notes_facts if eod.result_of(p)=='win']
    losses = [(p,f) for p,f in notes_facts if eod.result_of(p)=='loss']
    def clip(t, n=110):
        t = t or 'see note'
        return t if len(t)<=n else t[:n].rsplit(' ',1)[0]+'...'
    if wins:
        parts.append("What won: " + '; '.join(f"{p.get('pick')} ({clip(f.get('headline'))})" for p,f in wins) + ".")
    if losses:
        lparts = []
        for p,f in losses:
            mx = f.get('max_wp')
            tag = ("win probability peaked at {} before the collapse".format('99%+' if mx>=0.995 else '{:.0%}'.format(mx))) if mx is not None else 'no win-prob feed'
            lparts.append(f"{p.get('pick')} ({p.get('result')}, {tag})")
        parts.append("Losses named plainly: " + '; '.join(lparts) + ".")
    parts.append(f"All {len(graded)} results verified twice against the sheet; every fact above is pulled from the sheet, ESPN summary feeds, and closing lines on file - engine output, not a hand summary.")
    return ' '.join(parts)

def learn(date):
    """Full engine pass for a date. Returns {'brief':..., 'notes':{pick: note}, 'verified':...} or HOLD."""
    picks = eod.day_rows(date)
    if not picks: return {'status':'HOLD','why':f'no carded picks for {date}'}
    graded = [p for p in picks if eod.result_of(p) in ('win','loss')]
    pending = [p for p in picks if eod.result_of(p) is None]
    if pending: return {'status':'HOLD','why':f'{len(pending)} picks ungraded','pending':[p.get('pick') for p in pending]}
    # verify twice: fresh re-read must match
    picks2 = eod.day_rows(date)
    if [(p.get('pick'), eod.result_of(p)) for p in picks] != [(p.get('pick'), eod.result_of(p)) for p in picks2]:
        return {'status':'HOLD','why':'verify-twice failed: two sheet reads disagree'}
    notes_facts = []
    for p in graded:
        url = espn_url(p.get('note',''))
        summary = None
        if url:
            try: summary = fetch_json(url)
            except Exception: summary = None
        note, facts = pick_note(p, summary)
        notes_facts.append((p, facts))
        p['_engine_note'] = note
    brief = compose_brief(date, graded, notes_facts)
    return {'status':'OK','date':date,'brief':brief,
            'notes':{p.get('pick'): p['_engine_note'] for p in graded},
            'verified':'twice (picks-tab re-read identical); facts from ESPN summary + closing lines on file'}

if __name__ == '__main__':
    date = sys.argv[sys.argv.index('--date')+1] if '--date' in sys.argv else (datetime.date.today()-datetime.timedelta(days=1)).isoformat()
    print(json.dumps(learn(date), indent=1))
