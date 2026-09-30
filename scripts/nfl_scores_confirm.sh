#!/usr/bin/env bash
# nfl_scores_confirm.sh - NFL second-feed for live pick relays (approved 9/27 11:59 via main:
# the-odds-api scores endpoint, 15-min cadence, ONLY during live NFL windows, budget-visible).
# Self-gates FREE on ESPN before spending a credit: no in-progress NFL event = exit 0, no API call.
# Output: nfl_scores.json at repo root (raw scores + credits_remaining from response headers).
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
if [ "$live" = "0" ]; then echo "no live NFL - no credit spent"; exit 0; fi
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
     "credits_remaining":int(remaining) if remaining and remaining.isdigit() else None,
     "source":"the-odds-api v4 nfl scores (daysFrom=1)","games":games}
json.dump(out,open('nfl_scores.json','w'),indent=1)
print(f"nfl_scores.json: {len(games)} games, credits remaining: {remaining}")
PY
rm -f nfl_scores_raw.json
