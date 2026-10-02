#!/usr/bin/env bash
# nfl_scores_confirm.sh - NFL second-feed for live pick relays (approved 9/27 11:59 via main:
# the-odds-api scores endpoint, 15-min cadence, ONLY during live NFL windows, budget-visible).
# Self-gates FREE on ESPN before spending a credit: no in-progress NFL event = exit 0, no API call,
# except the bounded final chase below (a started game this file still holds as not completed).
# Output: nfl_scores.json at repo root (raw scores). The provider credit count from the response
# headers is printed to the run log only, never written to the public file (LS-22).
set -euo pipefail
cd "$(dirname "$0")/.."
: "${THE_ODDS_API_KEY:?THE_ODDS_API_KEY missing}"
# free gate: any NFL game in progress right now? (the scoreboard is kept for the final chase below)
ESPN=$(mktemp); HDR=$(mktemp); trap 'rm -f "$ESPN" "$HDR"' EXIT
live=""
for attempt in 1 2 3; do
  if curl -sS --max-time 15 -o "$ESPN" "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard" \
    && live=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(sum(1 for e in d.get('events',[]) if e['status']['type']['state']=='in'))" "$ESPN"); then
    break
  fi
  live=""
  echo "ESPN gate probe attempt $attempt failed - retrying in 5s" >&2
  sleep 5
done
# gate unreachable after retries: skip the cycle free (no credit spent) - next cron tick re-probes
if [ -z "$live" ]; then echo "ESPN gate unavailable after 3 attempts - skipping cycle, no credit spent"; exit 0; fi
# Final chase (F3, Oct 2 TNF frozen at 7-7 completed:false): the 'in' gate alone stops pulling at
# the final whistle, so the last game of every live window was never recorded final. A game this
# file holds as started but not completed, kicked off within CHASE_HOURS, gets one more pull per
# cycle until the-odds-api reports it completed. Free again once the final lands or the window ends.
# Bounded to games ESPN itself reports in progress ('in') or played to a final ('post' and
# completed): a postponed, canceled, suspended, still-'pre' or unlisted game is never chased, so a
# game that never started cannot spend a pull every cycle for the whole window.
CHASE_HOURS=5
chase=$(python3 - "$CHASE_HOURS" "$ESPN" <<'PY'
import json,sys
from datetime import datetime,timezone,timedelta
try:
    games=json.load(open('nfl_scores.json')).get('games') or []
except Exception:
    games=[]
try:
    events=json.load(open(sys.argv[2])).get('events') or []
except Exception:
    events=[]
NOPE=('POSTPONED','CANCELED','CANCELLED','SUSPENDED')
espn={}
for e in events:
    try:
        st=e['status']['type']; c=e['competitions'][0]['competitors']
        side={x['homeAway']:x['team']['displayName'].lower() for x in c}
        espn[(side['home'],side['away'])]=st
    except (KeyError,IndexError,TypeError):
        continue
def played(st):
    name=str(st.get('name') or '').upper()+' '+str(st.get('description') or '').upper()
    if any(w in name for w in NOPE):
        return False
    return st.get('state')=='in' or (st.get('state')=='post' and st.get('completed') is True)
now=datetime.now(timezone.utc); win=timedelta(hours=float(sys.argv[1])); n=0
for g in games:
    try:
        ko=datetime.fromisoformat(str(g.get('commence_time')).replace('Z','+00:00'))
    except (TypeError,ValueError):
        continue
    if g.get('completed') or not timedelta(0) <= now-ko <= win:
        continue
    st=espn.get((str(g.get('home_team','')).lower(),str(g.get('away_team','')).lower()))
    if st is not None and played(st):
        n+=1
    else:
        print(f"chase skipped: {g.get('away_team')} @ {g.get('home_team')} - ESPN reports "
              f"{(st or {}).get('name') or 'no such game'} (only in-progress or final games are chased)", file=sys.stderr)
print(n)
PY
) || chase=0
if [ "$live" = "0" ] && [ "${chase:-0}" = "0" ]; then echo "no live NFL - no credit spent"; exit 0; fi
if [ "$live" = "0" ]; then echo "no live NFL; $chase started game(s) not yet final within ${CHASE_HOURS}h - one confirm pull"; fi
curl -sS --max-time 25 -D "$HDR" -o nfl_scores_raw.json \
  "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/scores/?daysFrom=1&apiKey=${THE_ODDS_API_KEY}"
remaining=$(grep -i '^x-requests-remaining:' "$HDR" | tr -d '\r' | awk '{print $2}')
python3 - "$remaining" <<'PY'
import json,sys
from datetime import datetime,timezone
remaining=sys.argv[1]
games=json.load(open('nfl_scores_raw.json'))
out={"pulled_at_utc":datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
     "source":"the-odds-api v4 nfl scores (daysFrom=1)","games":games}
json.dump(out,open('nfl_scores.json','w'),indent=1)
print(f"nfl_scores.json: {len(games)} games, credits remaining: {remaining}")
PY
rm -f nfl_scores_raw.json
