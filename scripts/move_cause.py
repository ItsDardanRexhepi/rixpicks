#!/usr/bin/env python3
"""Odds-move cause logger (user feature, Sep 25 ~11:50 AM PT): every material book-price move
on a carded game gets logged with a timestamped causal note - the when, from-what, WHY and HOW.
Reads /tmp/odds_prefill.json (fresh The Odds API pull), diffs vs repo-tracked .odds_prev.json,
and for |move| >= 10 American points probes for a cause:
  1) ESPN league news headlines from the last 6h matching either team's name
  2) ESPN scoreboard state for the game (postponed/lineup context)
  3) fallback: market-move classification (no fresh headline = steam/market-driven)
Appends JSONL entries to odds_moves.jsonl and rewrites .odds_prev.json with current prices.
Never raises: a cause-probe failure must not break the odds refresh.
"""
import json,os,sys,urllib.request,datetime

REPO=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREV=os.path.join(REPO,'.odds_prev.json')
LOG=os.path.join(REPO,'odds_moves.jsonl')
MANIFEST=os.path.join(REPO,'manifest.json')
PREFILL='/tmp/odds_prefill.json'
THRESH=10  # American points
NEWS_HOURS=6

def get(u,timeout=15):
    req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'})
    return json.load(urllib.request.urlopen(req,timeout=timeout))

def team_tokens(name):
    parts=name.split()
    return {p.lower() for p in parts if len(p)>3}

def _mlb_teams():
    d=get('https://statsapi.mlb.com/api/v1/teams?sportId=1')
    return {t['name']:t['id'] for t in d['teams']}

def _mlb_cause(away,home):
    teams=_mlb_teams()
    start=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=48)).strftime('%Y-%m-%d')
    end=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
    found=[]
    for name in (away,home):
        tid=teams.get(name)
        if not tid: continue
        d=get(f'https://statsapi.mlb.com/api/v1/transactions?teamId={tid}&startDate={start}&endDate={end}')
        for t in d.get('transactions',[]):
            desc=t.get('description','')
            if any(k in desc for k in ('injured list','paternity','bereavement','designated','recalled','selected the contract','optioned','traded','activated')):
                found.append(f"[{t.get('date')}] {desc}")
    return found[:4]

def probe_cause(league,away,home,side_team):
    """Return (cause_note, evidence). MLB: official Stats API transactions (48h).
    Other leagues: ESPN news endpoint best-effort. Else classify market-driven."""
    if league.startswith('baseball/'):
        try:
            txns=_mlb_cause(away,home)
            if txns:
                return ' | '.join(txns), txns
            return 'no roster/IL transactions for either team in last 48h (MLB Stats API) - market-driven move (steam/sharp/positioning)', []
        except Exception as e:
            return f'transaction probe unavailable ({e}); move unclassified', []
    # non-MLB fallback: ESPN news
    headlines=[]
    try:
        d=get(f'https://site.api.espn.com/apis/site/v2/sports/{league}/news?limit=50')
        cutoff=datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=NEWS_HOURS)
        toks=team_tokens(away)|team_tokens(home)
        for a in d.get('articles',[]):
            pub=a.get('published','')
            try: pt=datetime.datetime.fromisoformat(pub.replace('Z','+00:00'))
            except Exception: continue
            if pt<cutoff: continue
            h=a.get('headline','')
            blob=(h+' '+a.get('description','')).lower()
            if any(t in blob for t in toks):
                headlines.append({'headline':h,'published':pub})
        headlines=headlines[:3]
    except Exception as e:
        return f'news probe unavailable ({e}); move unclassified',[]
    if headlines:
        note=' | '.join(f"[{h['published'][:16]}Z] {h['headline']}" for h in headlines)
        return note,headlines
    return 'no fresh team headline in last %dh - market-driven move (steam/sharp/positioning)'%NEWS_HOURS,[]

def main():
    man=json.load(open(MANIFEST))
    prefill=json.load(open(PREFILL))
    try: prev=json.load(open(PREV))
    except Exception: prev={}
    cur={}
    pf={}
    for g in prefill:
        pf[(g['away'],g['home'],g['commence'])]=g['books']
    moves=[]
    now=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    for p in man.get('picks',[]):
        g=p.get('game') or {}
        key=(g.get('away'),g.get('home'),g.get('commence'))
        books=pf.get(key)
        if not books: continue
        gk='|'.join(key)
        for book,rec in books.items():
            for side in ('away','home'):
                ml=rec.get(f'{side}_ml')
                if ml is None: continue
                ck=f'{gk}|{book}|{side}'
                cur[ck]=ml
                old=prev.get(ck)
                if old is None or abs(ml-old)<THRESH: continue
                side_team=g.get('away') if side=='away' else g.get('home')
                cause,_=probe_cause(p.get('espn_league','baseball/mlb'),g.get('away'),g.get('home'),side_team)
                entry={'ts':now,'pick':p.get('name'),'game':f"{g.get('away')} @ {g.get('home')}",
                       'book':book,'side':side,'team':side_team,'old':old,'new':ml,'delta':ml-old,
                       'cause':cause}
                moves.append(entry)
                print(f"MOVE {book} {side_team} {old}->{ml} ({ml-old:+d}) | {cause[:100]}")
    with open(LOG,'a') as f:
        for m in moves: f.write(json.dumps(m)+'\n')
    json.dump(cur,open(PREV,'w'))
    print(f"{len(moves)} material moves logged; {len(cur)} price points tracked")

if __name__=='__main__':
    try: main()
    except Exception as e:
        print(f'move_cause non-fatal error: {e}',file=sys.stderr)  # never break the refresh
