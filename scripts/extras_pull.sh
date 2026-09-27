#!/usr/bin/env bash
# extras_pull.sh v2 - MLS/MMA/boxing book pulls (the-odds-api free tier).
# Runs in GHA extras-sweep workflow; THE_ODDS_API_KEY comes from the repo secret.
# Budget: 3 credits/run, 2 runs/day = 6/day (inside the 16/day shared cap with odds_refresh).
# Output: extras_books.json at repo root (pulled_at, per-sport events with h2h books).
# v2: a single sport failing (bad key, offseason, provider outage) is recorded inline as
# {"error": ...} and does NOT kill the run; the run fails only if ALL sports fail.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${THE_ODDS_API_KEY:?THE_ODDS_API_KEY missing}"
SPORTS="soccer_usa_mls mma_mixed_martial_arts boxing_heavyweight"
OUT=extras_books.json
TMP=$(mktemp); RESP=$(mktemp)
trap 'rm -f "$TMP" "$RESP"' EXIT
echo '{"pulled_at_utc":"'"$(date -u '+%Y-%m-%dT%H:%M:%SZ')"'","sports":{}}' > "$TMP"
ok=0
for s in $SPORTS; do
  code=$(curl -sS --max-time 25 -o "$RESP" -w '%{http_code}' "https://api.the-odds-api.com/v4/sports/${s}/odds/?regions=us&markets=h2h&oddsFormat=american&apiKey=${THE_ODDS_API_KEY}")
  if [ "$code" = "200" ] && python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if isinstance(d,list) else 1)" "$RESP"; then
    python3 - "$TMP" "$s" "$RESP" <<'PY'
import json,sys
path,sport,rpath=sys.argv[1],sys.argv[2],sys.argv[3]
d=json.load(open(path)); d['sports'][sport]=json.load(open(rpath))
json.dump(d,open(path,'w'),indent=1)
PY
    ok=$((ok+1))
  else
    echo "WARN extras pull $s: HTTP $code: $(head -c 200 "$RESP")" >&2
    python3 - "$TMP" "$s" "$RESP" "$code" <<'PY'
import json,sys
path,sport,rpath,code=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4]
d=json.load(open(path))
try: body=json.load(open(rpath))
except Exception: body=open(rpath).read()[:200]
d['sports'][sport]={"error":f"HTTP {code}","detail":body if isinstance(body,dict) else {"body":body}}
json.dump(d,open(path,'w'),indent=1)
PY
  fi
  sleep 1
done
mv "$TMP" "$OUT"
python3 -c "import json;d=json.load(open('$OUT'));print('extras_books.json written:',sum(len(v) for v in d['sports'].values() if isinstance(v,list)),'events, ok sports:',sum(1 for v in d['sports'].values() if isinstance(v,list)))"
[ "$ok" -ge 1 ] || { echo "EXTRAS PULL TOTAL FAILURE - all sports errored" >&2; exit 1; }
