#!/bin/bash
# Preview card chain for 2026-09-28 (owner green light 9/27 via main): CANDIDATE ARTIFACTS ONLY.
# No commits, no pushes - go-live gate holds. Env: THE_ODDS_API_KEY/ODDS_API_KEY (+ Polymarket pair).
set -uo pipefail
LOG=/tmp/card_chain.log
exec > >(tee -a "$LOG") 2>&1
DT=2026-09-28; D=20260928
SLATE=/tmp/slate_day_$DT.json
echo "== card chain preview $DT (PT) start $(date -u +%FT%TZ)"

# analysis-tree overlays (preview-only; main repo untouched): core/ overrides + hunt production feeds
if [ -d previews/overlay ]; then cp -rf previews/overlay/. .; echo "overlay applied: $(find previews/overlay -type f | tr '
' ' ')"; fi
if [ -d previews/feeds ]; then cp -f previews/feeds/* /tmp/; echo "feeds staged: $(ls previews/feeds | tr '
' ' ')"; fi

echo "-- stage: league_slate"
python3 scripts/league_slate.py MLB NFL CFB WNBA NBA NHL NCAAB MLS NWSL PGA ATP WTA NASCAR UFC --date $D --odds --json > $SLATE
echo "slate rows: $(python3 -c "import json;print(len(json.load(open('$SLATE'))))" 2>/dev/null || echo ERR)"

echo "-- stage: hunt (floored first)"
python3 scripts/hunt_v2.py $SLATE /tmp/hunt_v2_$DT.json || echo "STAGE FAIL hunt_v2"
NCAND=$(python3 -c "
import json
try:
    log=json.load(open('/tmp/hunt_v2_$DT.json'))
    print(sum(1 for e in log if e.get('verdict')=='CANDIDATE'))
except Exception: print(0)")
echo "hunt candidates: $NCAND"
if [ "$NCAND" = "0" ]; then
  echo "-- stage: hunt fallback (floorless - zero-pick rule)"
  python3 scripts/hunt_nofloor.py $SLATE /tmp/hunt_v2_$DT.json || echo "STAGE FAIL hunt_nofloor"
fi

echo "-- stage: st prefill"
SPORTS=$(python3 - <<'PY'
import json
reg=json.load(open('config_leagues.json'))['leagues']
try: slate=json.load(open('/tmp/slate_day_2026-09-28.json'))
except Exception: slate=[]
ls=sorted({r.get('league') for r in slate if r.get('league') in reg})
print(' '.join(sorted({(reg[l].get('odds_api') or '') for l in ls} - {''})))
PY
)
echo "st sports: $SPORTS"
if [ -n "$SPORTS" ]; then ODDS_PREFILL_ST_OUT=/tmp/odds_prefill_st.json python3 scripts/odds_prefill_st.py $SPORTS || echo "STAGE FAIL st_prefill"; fi

echo "-- stage: st_fair"
python3 scripts/st_fair.py > /tmp/st_fair_$DT.json || echo "STAGE FAIL st_fair"
echo "-- stage: st_card_candidates"
python3 scripts/st_card_candidates.py /tmp/st_fair_$DT.json > /tmp/cand_st_$DT.json || echo "STAGE FAIL st_card_candidates"

echo "-- stage: props_engine (pregame)"
python3 scripts/props_engine.py || echo "STAGE FAIL props_engine"
echo "-- stage: props_card_candidates (pre-game gate live)"
python3 scripts/props_card_candidates.py /tmp/props_candidates.json > /tmp/cand_props_$DT.json || echo "STAGE FAIL props_card_candidates"

echo "-- stage: tennis_kalshi_discovery"
python3 - <<'PY'
import json
try:
    slate=json.load(open('/tmp/slate_day_2026-09-28.json'))
except Exception:
    slate=[]
rows=[{"league":r.get("league"),"match":f"{r.get('away','')} @ {r.get('home','')}","instance_id":r.get("espn_id")} for r in slate if r.get("league") in ("ATP","WTA")]
json.dump({"rows":rows},open('/tmp/tennis_slate_2026-09-28.json','w'))
print(f"tennis slate rows: {len(rows)}")
PY
python3 scripts/tennis_kalshi_discovery.py --date 2026-09-28 --slate /tmp/tennis_slate_$DT.json --out /tmp/tennis_catch_$DT.json || echo "STAGE FAIL tennis"

echo "-- stage: merge candidate classes"
python3 - <<'PY'
import json
DT='2026-09-28'
cands=[]
try:
    log=json.load(open(f'/tmp/hunt_v2_{DT}.json'))
    h=[e for e in log if e.get('verdict')=='CANDIDATE']
    cands+=h; print(f"hunt: {len(h)} candidates")
except Exception as e: print("hunt merge skip:", e)
for name,path in [('st',f'/tmp/cand_st_{DT}.json'),('props',f'/tmp/cand_props_{DT}.json')]:
    try:
        rows=json.load(open(path))
        cands+=rows; print(f"{name}: {len(rows)} candidates")
    except Exception as e: print(f"{name} merge skip:", e)
# NOTE: tennis catches are NOT build_manifest schema (no market_class/line) - excluded from
# candidates.json pending a tennis adapter; shipped as its own artifact (tennis_catch_2026-09-28.json).
json.dump(cands, open(f'/tmp/candidates_{DT}.json','w'), indent=1)
print("merged candidates:", len(cands))
PY

echo "-- stage: build_manifest --preview"
python3 - <<'PY'
import json, datetime
m=json.load(open('manifest.json'))
meta={'record': m.get('record'), 'units_pl': m.get('units_pl'),
      'units_ledger': m.get('units_ledger'), 'yesterday': m.get('yesterday'),
      'status_note': m.get('status_note'), 'date_label': 'Monday, Sep 28',
      'updated': datetime.datetime.now().strftime('%b %-d, %-I:%M %p PT')}
json.dump(meta, open('/tmp/card_meta.json','w'))
print('meta:', meta['record'], meta['units_pl'])
PY
python3 scripts/build_manifest.py /tmp/candidates_$DT.json /tmp/manifest_preview_$DT.json --preview --meta /tmp/card_meta.json || echo "STAGE FAIL build_manifest"
echo "-- stage: card render (legacy builder, candidate artifact only - NOT published)"
python3 scripts/build_gh_page.py /tmp/manifest_preview_$DT.json /tmp/card_preview_$DT.html || echo "STAGE FAIL build_gh_page"
echo "== chain end $(date -u +%FT%TZ)"
