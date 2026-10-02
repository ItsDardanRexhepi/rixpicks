#!/bin/bash
# J-049A-safe DK/FD odds refresh (cadence b, user-approved Sep 25): 15-min cron,
# rebuild only when a card game is live or starts within 2h. STANDING RULE (his word 9/27): no cap unless we hit a hard cap ever - no daily/lane cap; the only tripwire is the API plan's own 20,000 credits/month hard limit, enforced fail-loud via core/budget.py (local lane) and the authoritative x-requests-remaining floor below (this lane). Run count kept as telemetry only.
set -e
git config user.name "RixPicks Bot"
git config user.email "rixpicks-bot@users.noreply.github.com"
export TZ=America/Los_Angeles
TODAY=$(date +%F)
COUNT_FILE=.odds_refresh_count.json
COUNT=0
# run scratch (fixture hook: scripts/test_refresh_lane.py points it at its own temp folder)
T="${RP_TMP:-/tmp}"
# The provider's last x-requests-remaining reading is ops state, not site content: every file in
# the checkout is served (Pages + the Cloudflare mirror), so it lives outside it, carried between
# runs by odds_refresh.yml's cache step. .odds_refresh_count.json served the paid API's credit
# count (LS-22); it now carries the run-count telemetry only.
OPS_DIR="${RP_OPS_STATE:-$HOME/.rixpicks-ops}"
QUOTA_FILE="$OPS_DIR/odds_quota.json"
[ -f "$COUNT_FILE" ] && COUNT=$(python3 -c "import json;d=json.load(open('$COUNT_FILE'));print(d.get('$TODAY',0))")
# 33/day lane cap REMOVED 9/27 (standing rule: no cap unless hard cap ever); COUNT is telemetry in the commit message
# legacy fallback (first runs after the move, before the cache holds a reading): the committed
# counter's last value, which the next counted run drops
LASTREM_PRE=$(python3 -c "import json;d=json.load(open('$QUOTA_FILE'));print(int(d.get('last_remaining') or 0))" 2>/dev/null \
  || python3 -c "import json;d=json.load(open('$COUNT_FILE'));print(int(d.get('last_remaining') or 0))" 2>/dev/null || echo 0)
if [ "${LASTREM_PRE:-0}" -gt 0 ] && [ "$LASTREM_PRE" -lt 200 ]; then echo "HARD CAP TRIPWIRE: provider monthly quota nearly exhausted (200 remaining, authoritative x-requests-remaining) - fail loud per standing rule 9/27" >&2; exit 1; fi
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
python3 scripts/odds_prefill.py $SPORTS 2> >(tee "$T/odds_prefill.err" >&2)
cp "$T/odds_prefill.json" slates/odds_prefill.json
ODDS_CREDITS_LEDGER="$T/odds_credits_gha.jsonl" ODDS_PREFILL_ST_OUT=slates/odds_prefill_st.json ODDS_PREFILL_ST_SNAPSHOT=slates/odds_prefill_st_pregame.json python3 scripts/odds_prefill_st.py $SPORTS 2> >(tee "$T/odds_prefill_st.err" >&2) || { if grep -q "credit cap" "$T/odds_prefill_st.err" 2>/dev/null; then echo "ST BUDGET BREACH - hard fail" >&2; exit 1; fi; echo "odds_prefill_st failed - keeping last st file" >&2; }
# props prefill (paid tier; J-123a gate in-script): in-window NFL/MLB event ids from the st pull
python3 - <<'PYX' > "$T/props_args.txt"
import json, datetime
try: d=json.load(open('slates/odds_prefill_st.json'))
except Exception: d=[]
now=datetime.datetime.now(datetime.timezone.utc)
by={}
for r in d:
    sp=r.get('sport'); e=r.get('provider_event_id')
    if sp not in ('americanfootball_nfl','baseball_mlb') or not e: continue
    try: ct=datetime.datetime.fromisoformat((r.get('commence') or '').replace('Z','+00:00'))
    except Exception: continue
    if (ct-now).total_seconds() > 7200 or (now-ct).total_seconds() > 14400: continue
    by.setdefault(sp,[])
    if e not in by[sp]: by[sp].append(e)
for sp,ids in by.items(): print(sp+' '+' '.join(ids))
PYX
while read -r line; do
  [ -z "$line" ] && continue
  if ! ODDS_CREDITS_LEDGER="$T/odds_credits_gha.jsonl" python3 scripts/odds_prefill_props.py $line 2>"$T/props_err.txt"; then
    cat "$T/props_err.txt" >&2
    if grep -q "credit cap" "$T/props_err.txt" 2>/dev/null; then echo "PROPS BUDGET BREACH - hard fail" >&2; exit 1; fi
    echo "props prefill failed: $line" >&2
  else cat "$T/props_err.txt" >&2; fi
done < "$T/props_args.txt"
LASTREM=$(grep -o 'credits remaining [0-9]*' "$T/odds_prefill.err" 2>/dev/null | tail -1 | grep -o '[0-9]*$' || true)
if [ -n "${LASTREM:-}" ]; then mkdir -p "$OPS_DIR" && python3 -c "
import json
json.dump({'pt_date':'$TODAY','last_remaining':int('$LASTREM')},open('$QUOTA_FILE','w'))"; fi
# run-count telemetry (the commit message's 'call N today'); the credit count never goes here
bump_count() { python3 -c "
import json
f='$COUNT_FILE'; d={}
try: d=json.load(open(f))
except: pass
d['$TODAY']=d.get('$TODAY',0)+1
d.pop('last_remaining',None)
json.dump(d,open(f,'w'))"; }
python3 scripts/move_cause.py || true
# Sep 26 live regression (hunter 7:25 AM): refresh rebuilds must never move record/units -
# RP_REFRESH=1 pins them from the live page; only an approved publish sets them from the manifest.
python3 scripts/futures_quotes.py futures.json --write || echo "futures_quotes failed - keeping last quotes" >&2
python3 scripts/wooder_td_feed.py slates/nfl_latest.json slates/nfl_live.json || echo "wooder_td_feed failed - keeping last live file" >&2
python3 scripts/live_games.py slates/live_games.json || echo "live_games failed - keeping last live_games file" >&2
# Card hold: the feeds exit 3 when manifest.json's picks do not match its declared
# pick_content_hash (a corrupted or hand-edited card); the builder exits 3 on that integrity gate
# or a failed ship condition. Such a card is never swallowed as an ordinary feed failure and never
# rebuilt: the pages stay on the last verified build, the live data unrelated to the card still
# ships, and the run then fails loud. Any other feed failure keeps the last manifest, as before.
CARD_HOLD=""
feed() {
  local name=$1 rc=0; shift
  python3 "scripts/$name" "$@" || rc=$?
  if [ $rc -eq 3 ]; then CARD_HOLD="$CARD_HOLD $name"; echo "CARD HOLD: $name refused manifest.json (pick_content_hash does not match its picks)" >&2
  elif [ $rc -ne 0 ]; then echo "$name failed - keeping last manifest" >&2; fi
}
feed polymarket_feed.py manifest.json
feed prediction_feed.py manifest.json slates/prediction_markets.json
if [ -z "$CARD_HOLD" ]; then
  BRC=0
  RP_REFRESH=1 python3 scripts/build_gh_page_v2.py manifest.json index.html || BRC=$?
  if [ $BRC -eq 3 ]; then CARD_HOLD=" build_gh_page_v2.py"; echo "CARD HOLD: the builder refused the card (exit 3, see BUILD FAILED above)" >&2
  elif [ $BRC -ne 0 ]; then exit $BRC; fi
fi
DATA_FILES="futures.json slates/nfl_live.json slates/live_games.json slates/odds_prefill.json slates/odds_prefill_st.json slates/odds_prefill_st_pregame.json slates/odds_prefill_props.json odds_moves.jsonl .odds_prev.json"
if [ -n "$CARD_HOLD" ]; then
  git add -N slates/odds_prefill.json slates/odds_prefill_st.json slates/odds_prefill_st_pregame.json slates/odds_prefill_props.json 2>/dev/null || true
  if git diff --quiet -- $DATA_FILES 2>/dev/null; then
    echo "card held - no live data movement either - nothing to commit" >&2
  else
    bump_count
    git add $DATA_FILES "$COUNT_FILE"
    git commit -m "odds refresh $(date '+%H:%M PT') (call $((COUNT+1)) today) - live data only, card held"
    git checkout -- . 2>/dev/null || true  # nothing the held card touched ships (feed or partial page writes)
    bash scripts/push_with_guard.sh
  fi
  echo "CARD HOLD:$CARD_HOLD - pages not rebuilt, manifest.json not committed; re-stamp or fix the card with build_manifest.py" >&2
  exit 3
fi
python3 scripts/backfill_history.py || true
git add -N slates/odds_prefill.json slates/odds_prefill_st.json slates/odds_prefill_st_pregame.json slates/odds_prefill_props.json 2>/dev/null || true
if git diff --quiet -- index.html game-*.html team-*.html futures.html futures.json slates/nfl_live.json slates/live_games.json slates/odds_prefill.json slates/odds_prefill_st.json slates/odds_prefill_st_pregame.json slates/odds_prefill_props.json odds_moves.jsonl .odds_prev.json price_history.jsonl 2>/dev/null; then echo "no price movement - no commit"; exit 0; fi
bump_count
git add index.html futures.html futures.json slates/game_routes.json slates/nfl_live.json slates/live_games.json slates/odds_prefill.json slates/odds_prefill_st.json slates/odds_prefill_st_pregame.json slates/odds_prefill_props.json manifest.json manifests/ "$COUNT_FILE" odds_moves.jsonl .odds_prev.json price_history.jsonl game-*.html team-*.html hist-*.json
git commit -m "odds refresh $(date '+%H:%M PT') (call $((COUNT+1)) today)"
# chaos drill (Sep 26): a push racing the publish window must retry+rebase, never fail red
# K22 (Sep 30): loop lives in push_with_guard.sh - every loud-fail path resets HEAD to
# origin/main first, because the on-failure incident hook pushes HEAD (run 36730127672).
# The guard also reads the push back (origin/main must contain HEAD); a run with
# nothing to commit has nothing to read back (Oct 2 runs 36962855292 + 36962967323).
bash scripts/push_with_guard.sh
echo "rebuilt and pushed"

