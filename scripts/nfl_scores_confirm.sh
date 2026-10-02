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
# free gate: any NFL game in progress right now?
live=""
for attempt in 1 2 3; do
  if live=$(curl -sS --max-time 15 "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(sum(1 for e in d.get('events',[]) if e['status']['type']['state']=='in'))"); then
    break
  fi
  echo "ESPN gate probe attempt $attempt failed - retrying in 5s" >&2
  sleep 5
done
# gate unreachable after retries: skip the cycle free (no credit spent) - next cron tick re-probes
if [ -z "$live" ]; then echo "ESPN gate unavailable after 3 attempts - skipping cycle, no credit spent"; exit 0; fi
# Final chase (F3, Oct 2 TNF frozen at 7-7 completed:false): the 'in' gate alone stops pulling at
# the final whistle, so the last game of every live window was never recorded final. A game this
# file holds as started but not completed, kicked off within CHASE_HOURS, gets one more pull per
# cycle until the-odds-api reports it completed. Free again once the final lands or the window ends.
CHASE_HOURS=5
chase=$(python3 - "$CHASE_HOURS" <<'PY'
import json,sys
from datetime import datetime,timezone,timedelta
try:
    games=json.load(open('nfl_scores.json')).get('games') or []
except Exception:
    games=[]
now=datetime.now(timezone.utc); win=timedelta(hours=float(sys.argv[1])); n=0
for g in games:
    try:
        ko=datetime.fromisoformat(str(g.get('commence_time')).replace('Z','+00:00'))
    except (TypeError,ValueError):
        continue
    if not g.get('completed') and timedelta(0) <= now-ko <= win:
        n+=1
print(n)
PY
) || chase=0
if [ "$live" = "0" ] && [ "${chase:-0}" = "0" ]; then echo "no live NFL - no credit spent"; exit 0; fi
if [ "$live" = "0" ]; then echo "no live NFL; $chase started game(s) not yet final within ${CHASE_HOURS}h - one confirm pull"; fi
HDR=$(mktemp); trap 'rm -f "$HDR"' EXIT
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
