#!/bin/bash
# J-049A-safe DK/FD odds refresh (cadence b, user-approved Sep 25): 15-min cron,
# rebuild only when a card game is live or starts within 2h, max 16 odds-API calls/day.
set -e
git config user.name "RixPicks Bot"
git config user.email "rixpicks-bot@users.noreply.github.com"
export TZ=America/Los_Angeles
TODAY=$(date +%F)
COUNT_FILE=.odds_refresh_count.json
COUNT=0
[ -f "$COUNT_FILE" ] && COUNT=$(python3 -c "import json;d=json.load(open('$COUNT_FILE'));print(d.get('$TODAY',0))")
if [ "$COUNT" -ge 16 ]; then echo "daily odds-API budget (16) reached - skip"; exit 0; fi
# Game window check: any picked game live or starting within 2h (ESPN, free)
python3 - <<'PY'
import json,urllib.request,datetime,sys,os
os.environ.setdefault('TZ','America/Los_Angeles')
man=json.load(open('manifest.json'))
now=datetime.datetime.now()
reg=json.load(open('config_leagues.json'))['leagues']
for v in reg.values():
    lg=v.get('espn')
    if not lg: continue
    prm='&'+v['espn_params'] if v.get('espn_params') else ''
    try:
        d=json.load(urllib.request.urlopen(f'https://site.api.espn.com/apis/site/v2/sports/{lg}/scoreboard?dates={now:%Y%m%d}'+prm,timeout=15))
    except Exception: continue
    for e in d.get('events',[]):
        comps=[]
        if e.get('competitions'): comps.append(e['competitions'][0])
        for g in e.get('groupings',[]):
            comps.extend(g.get('competitions') or [])
        for c in comps:
            st=(c.get('status') or {}).get('type') or {}
            dt=(datetime.datetime.fromisoformat(e['date'].replace('Z','+00:00')).replace(tzinfo=None)-datetime.timedelta(hours=7)) if e.get('date') else now
            if st.get('state')=='in' or (st.get('state')=='pre' and 0 <= (dt-now).total_seconds() <= 7200):
                sys.exit(0)
sys.exit(1)
PY
GAME_WINDOW=$?
set -e
if [ $GAME_WINDOW -ne 0 ]; then echo "no live/imminent game - skip"; exit 0; fi
if [ -z "$THE_ODDS_API_KEY" ]; then echo "THE_ODDS_API_KEY secret missing - skip (page keeps last build prices)"; exit 0; fi
SPORTS=$(python3 -c "
import json
m=json.load(open('manifest.json'))
reg=json.load(open('config_leagues.json'))['leagues']
ls=sorted({(reg.get(p.get('league','')) or {}).get('odds_api') or 'baseball_mlb' for p in m['picks']})
print(' '.join(ls))")
python3 scripts/odds_prefill.py $SPORTS
python3 scripts/move_cause.py || true
python3 scripts/build_gh_page.py manifest.json index.html
python3 scripts/backfill_history.py || true
if git diff --quiet index.html game-*.html odds_moves.jsonl .odds_prev.json price_history.jsonl 2>/dev/null; then echo "no price movement - no commit"; exit 0; fi
python3 -c "
import json,datetime
f='$COUNT_FILE'; d={}
try: d=json.load(open(f))
except: pass
d['$TODAY']=d.get('$TODAY',0)+1
json.dump(d,open(f,'w'))"
git add index.html futures.html futures.json manifest.json "$COUNT_FILE" odds_moves.jsonl .odds_prev.json price_history.jsonl game-*.html team-*.html hist-*.json
git commit -m "odds refresh $(date '+%H:%M PT') (call $((COUNT+1))/16 today)"
git push
echo "rebuilt and pushed"
