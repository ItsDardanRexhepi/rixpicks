"""Wooder Ice anytime-TD live tracker feed.
Reads slates/nfl_latest.json, resolves ESPN event ids from the NFL scoreboard,
polls per-event scoringPlays for pick-side TDs, writes slates/nfl_live.json.
Run at GHA refresh cadence (or faster - scoring plays update ~30s on ESPN).
Usage: python3 wooder_td_feed.py <slate_path> <out_path> [dates=YYYYMMDD]
Fail-soft per leg: unresolved event/player keeps td_scored=false + a reason.
"""
import json, sys, time, urllib.request, unicodedata

ESPN_SB = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={d}&limit=50"
ESPN_SUM = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={eid}"

def get(url):
    req = urllib.request.Request(url, headers={'User-Agent':'python-urllib/3.10'})
    return json.load(urllib.request.urlopen(req, timeout=20))

def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c)).lower()


import re as _re_pt
def _pt_detail(s):
    # owner rule 9/27: ALL times render PT, never ET. ESPN shortDetail arrives ET
    # ("9/27 - 1:00 PM EDT") - shift -3h, suffix PT. Non-matching strings pass through.
    def _cv(m):
        h=int(m.group(1)); ap=m.group(3)
        h24=(h%12)+(12 if ap=='P' else 0)
        h24=(h24-3)%24
        ap2='AM' if h24<12 else 'PM'
        h12=h24%12 or 12
        return m.group(0)[:m.start(1)-m.start(0)]+f"{h12}:{m.group(2)} {ap2} PT"
    return _re_pt.sub(r'(\d{1,2}):(\d{2}) ([AP])M E[DS]T',_cv,s) if s else s

def main(slate_path, out_path, dates=None):
    slate = json.load(open(slate_path))
    legs = slate['dk']['singles']
    import datetime
    d = dates or datetime.datetime.now(datetime.timezone.utc).astimezone(
        datetime.timezone(datetime.timedelta(hours=-4))).strftime('%Y%m%d')  # ET game day
    sb = get(ESPN_SB.format(d=d))
    events = {}
    for ev in sb.get('events', []):
        comp = ev['competitions'][0]
        away = comp['competitors'][[c['homeAway'] for c in comp['competitors']].index('away')]
        home = comp['competitors'][[c['homeAway'] for c in comp['competitors']].index('home')]
        AL = {'WSH':'WAS'}  # ESPN abbr -> slate abbr
        a = AL.get(away['team']['abbreviation'], away['team']['abbreviation'])
        h = AL.get(home['team']['abbreviation'], home['team']['abbreviation'])
        key = f"{a} @ {h}"
        events[key] = ev
    games, out_legs = {}, []
    for leg in legs:
        mu, player = leg['matchup'], leg['player']
        ev = events.get(mu)
        rec = {'player': player, 'team': leg['team'], 'matchup': mu,
               'price_c': leg['price_c'], 'td_scored': False, 'td_count': 0, 'last_td': None}
        if not ev:
            rec['note'] = 'espn event unresolved'; out_legs.append(rec); continue
        eid = ev['id']
        comp = ev['competitions'][0]
        st = ev['status']
        games[eid] = {'matchup': mu, 'espn_event_id': eid,
                      'commence': ev.get('date'),  # ISO UTC tip-off - countdown derives from this, never hardcoded
                      'status': st['type']['state'],  # pre|in|post
                      'detail': _pt_detail(st['type'].get('shortDetail','')),
                      'score': ' - '.join(f"{c['team']['abbreviation']} {c.get('score','0')}" for c in comp['competitors'])}
        rec['espn_event_id'] = eid
        try:
            summ = get(ESPN_SUM.format(eid=eid))
            np_ = norm(player)
            hits = []
            for sp in summ.get('scoringPlays', []):
                if 'touchdown' not in norm(sp.get('type',{}).get('text','')) and 'TD' not in sp.get('text',''):
                    # type text e.g. 'Rushing Touchdown'; fallback: text contains player + (TD|touchdown)
                    pass
                txt = sp.get('text','')
                ttype = norm(sp.get('type',{}).get('text',''))
                if 'touchdown' in ttype or 'td' in norm(txt):
                    if np_ in norm(txt):
                        hits.append(txt)
            rec['td_count'] = len(hits)
            rec['td_scored'] = bool(hits)
            rec['last_td'] = hits[-1] if hits else None
        except Exception as ex:
            rec['note'] = f'summary fetch failed: {str(ex)[:60]}'
        out_legs.append(rec)
        time.sleep(0.3)
    out = {'version': 1, 'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'window': slate.get('window'), 'legs': out_legs, 'games': list(games.values())}
    json.dump(out, open(out_path,'w'), indent=1)
    print(f"wrote {out_path}: {sum(1 for l in out_legs if l['td_scored'])}/{len(out_legs)} legs with TD, {len(games)} games", file=sys.stderr)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv)>3 else None)
