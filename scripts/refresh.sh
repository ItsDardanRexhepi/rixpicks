#!/bin/bash
# J-049A-safe DK/FD odds refresh (cadence b, user-approved Sep 25): 15-min cron,
# rebuild only when a card game is live or starts within 2h, lane cap 33 runs/day (~99 credits, 3cr/run; real plan ~20k credits/mo per 9/27 header read); authoritative provider floor via x-requests-remaining.
set -e
git config user.name "RixPicks Bot"
git config user.email "rixpicks-bot@users.noreply.github.com"
export TZ=America/Los_Angeles
TODAY=$(date +%F)
COUNT_FILE=.odds_refresh_count.json
COUNT=0
[ -f "$COUNT_FILE" ] && COUNT=$(python3 -c "import json;d=json.load(open('$COUNT_FILE'));print(d.get('$TODAY',0))")
if [ "$COUNT" -ge 33 ]; then echo "daily odds-API lane budget (33 runs ~ 99 credits) reached - skip"; exit 0; fi
LASTREM_PRE=$(python3 -c "import json;d=json.load(open('$COUNT_FILE'));print(d.get('last_remaining') or 0)" 2>/dev/null || echo 0)
if [ "${LASTREM_PRE:-0}" -gt 0 ] && [ "$LASTREM_PRE" -lt 200 ]; then echo "provider quota floor (200 remaining, authoritative x-requests-remaining) - skip"; exit 0; fi
# Game window check: any picked game live or starting within 2h (ESPN, free)
# chaos drill (Sep 26): set -e killed quiet windows as red failures before GAME_WINDOW captured
set +e
python3 - <<'PY'
import json,urllib.request,datetime,sys,os
from zoneinfo import ZoneInfo
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
            dt=datetime.datetime.fromisoformat(e['date'].replace('Z','+00:00')).astimezone(ZoneInfo('America/Los_Angeles')).replace(tzinfo=None) if e.get('date') else now
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
python3 scripts/odds_prefill.py $SPORTS 2> >(tee /tmp/odds_prefill.err >&2)
LASTREM=$(grep -o 'credits remaining [0-9]*' /tmp/odds_prefill.err 2>/dev/null | tail -1 | grep -o '[0-9]*$' || true)
if [ -n "${LASTREM:-}" ]; then python3 -c "
import json
f='$COUNT_FILE'; d={}
try: d=json.load(open(f))
except: pass
d['last_remaining']=int('$LASTREM')
json.dump(d,open(f,'w'))"; fi
python3 scripts/move_cause.py || true
# Sep 26 live regression (hunter 7:25 AM): refresh rebuilds must never move record/units -
# RP_REFRESH=1 pins them from the live page; only an approved publish sets them from the manifest.
python3 scripts/futures_quotes.py futures.json --write || echo "futures_quotes failed - keeping last quotes" >&2
python3 scripts/wooder_td_feed.py slates/nfl_latest.json slates/nfl_live.json || echo "wooder_td_feed failed - keeping last live file" >&2
RP_REFRESH=1 python3 scripts/build_gh_page_v2.py manifest.json index.html
python3 scripts/backfill_history.py || true
if git diff --quiet index.html game-*.html futures.json slates/nfl_live.json odds_moves.jsonl .odds_prev.json price_history.jsonl 2>/dev/null; then echo "no price movement - no commit"; exit 0; fi
python3 -c "
import json,datetime
f='$COUNT_FILE'; d={}
try: d=json.load(open(f))
except: pass
d['$TODAY']=d.get('$TODAY',0)+1
json.dump(d,open(f,'w'))"
git add index.html futures.html futures.json slates/nfl_live.json manifest.json manifests/ "$COUNT_FILE" odds_moves.jsonl .odds_prev.json price_history.jsonl game-*.html team-*.html hist-*.json
git commit -m "odds refresh $(date '+%H:%M PT') (call $((COUNT+1))/33 today)"
# chaos drill (Sep 26): a push racing the publish window must retry+rebase, never fail red
for i in 1 2; do
  if git push; then break; fi
  git pull --rebase -X theirs || { git rebase --abort; continue; }
  OF=$(git show --pretty='' --name-only ORIG_HEAD)
  git diff --quiet ORIG_HEAD HEAD -- $OF || { echo 'REBASE GUARD: rebase altered generated content - failing loud; next cycle regenerates' >&2; exit 1; }
done
git ls-remote origin main | grep -q "$(git rev-parse HEAD)" || { echo 'PUSH READBACK FAILED: origin/main != HEAD' >&2; exit 1; }
echo "rebuilt and pushed"

