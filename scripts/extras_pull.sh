#!/usr/bin/env bash
# extras_pull.sh - MLS/MMA/boxing book pulls (the-odds-api free tier).
# Runs in GHA extras-sweep workflow; THE_ODDS_API_KEY comes from the repo secret.
# Budget: 3 credits/run, 2 runs/day = 6/day (inside the 16/day shared cap with odds_refresh).
# Output: extras_books.json at repo root (pulled_at, per-sport events with h2h books).
set -euo pipefail
cd "$(dirname "$0")/.."
: "${THE_ODDS_API_KEY:?THE_ODDS_API_KEY missing}"
SPORTS="soccer_usa_mls mma_mixed_martial_arts boxing_heavyweight"
OUT=extras_books.json
TMP=$(mktemp); RESP=$(mktemp)
trap 'rm -f "$TMP" "$RESP"' EXIT
echo '{"pulled_at_utc":"'"$(date -u '+%Y-%m-%dT%H:%M:%SZ')"'","sports":{}}' > "$TMP"
for s in $SPORTS; do
  curl -sS --max-time 25 "https://api.the-odds-api.com/v4/sports/${s}/odds/?regions=us&markets=h2h&oddsFormat=american&apiKey=${THE_ODDS_API_KEY}" > "$RESP"
  if python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if isinstance(d,list) else 1)" "$RESP"; then
    python3 - "$TMP" "$s" "$RESP" <<'PY'
import json,sys
path,sport,rpath=sys.argv[1],sys.argv[2],sys.argv[3]
d=json.load(open(path)); d['sports'][sport]=json.load(open(rpath))
json.dump(d,open(path,'w'),indent=1)
PY
  else
    echo "EXTRAS PULL FAIL $s: $(head -c 300 "$RESP")" >&2; exit 1
  fi
  sleep 1
done
mv "$TMP" "$OUT"
python3 -c "import json;d=json.load(open('$OUT'));print('extras_books.json written:',sum(len(v) for v in d['sports'].values()),'events across',len(d['sports']),'sports')"
