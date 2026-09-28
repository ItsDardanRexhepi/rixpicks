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

echo "-- stage: hunt slate transform ({rows:[...]}, instance_id/commence_utc/match schema)"
python3 - <<'PY'
import json
DT='2026-09-28'
slate=json.load(open(f'/tmp/slate_day_{DT}.json'))
rows=[]
for r in slate:
    rr=dict(r)
    rr['instance_id']=r.get('espn_id')
    rr['commence_utc']=r.get('commence')
    rr['match']=r.get('match') or f"{r.get('away','')} @ {r.get('home','')}"
    rows.append(rr)
json.dump({'rows':rows}, open(f'/tmp/hunt_slate_{DT}.json','w'))
print('hunt slate rows:', len(rows))
PY
echo "-- stage: hunt (floored first)"
python3 scripts/hunt_v2.py /tmp/hunt_slate_$DT.json /tmp/hunt_v2_$DT.json || echo "STAGE FAIL hunt_v2"
NCAND=$(python3 -c "
import json
try:
    log=json.load(open('/tmp/hunt_v2_$DT.json'))
    print(sum(1 for e in log if e.get('verdict')=='CANDIDATE'))
except Exception: print(0)")
echo "hunt candidates: $NCAND"
if [ "$NCAND" = "0" ]; then
  echo "-- stage: hunt fallback (floorless - zero-pick rule)"
  python3 scripts/hunt_nofloor.py /tmp/hunt_slate_$DT.json /tmp/hunt_v2_$DT.json || echo "STAGE FAIL hunt_nofloor"
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
echo "-- stage: tennis_card_candidates (adapter: catch -> build_manifest schema)"
python3 scripts/tennis_card_candidates.py /tmp/tennis_catch_$DT.json > /tmp/cand_tennis_$DT.json 2>/tmp/tennis_adapter_notes_$DT.txt || echo "STAGE FAIL tennis_adapter"
cat /tmp/tennis_adapter_notes_$DT.txt

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
for name,path in [('st',f'/tmp/cand_st_{DT}.json'),('props',f'/tmp/cand_props_{DT}.json'),('tennis',f'/tmp/cand_tennis_{DT}.json')]:
    try:
        rows=json.load(open(path))
        cands+=rows; print(f"{name}: {len(rows)} candidates")
    except Exception as e: print(f"{name} merge skip:", e)
json.dump(cands, open(f'/tmp/candidates_{DT}.json','w'), indent=1)
print("merged candidates:", len(cands))
PY

echo "-- stage: evaluation summary (zero-pick standard card sections)"
python3 - <<'PY'
import json, collections, html
DT='2026-09-28'
def load(p, dflt):
    try: return json.load(open(p))
    except Exception: return dflt
slate=load(f'/tmp/slate_day_{DT}.json',[])
hunt=load(f'/tmp/hunt_v2_{DT}.json',[])
cand_st=load(f'/tmp/cand_st_{DT}.json',[])
props=load('/tmp/props_candidates.json',{})
catch=load(f'/tmp/tennis_catch_{DT}.json',{})
try: notes=[l.strip() for l in open(f'/tmp/tennis_adapter_notes_{DT}.txt') if l.strip()]
except Exception: notes=[]
LG={'NFL':'football/nfl','ATP':'tennis/atp','WTA':'tennis/wta','PGA':'golf/pga'}
slc=collections.Counter(r.get('league') for r in slate)
hc=collections.Counter((e.get('league'),e.get('verdict')) for e in hunt)
sections=[]
def hunt_line(lg):
    c=collections.Counter({v:n for (l,v),n in hc.items() if l==lg})
    if not c: return None
    parts=', '.join(f'{n} {v}' for v,n in sorted(c.items(), key=lambda x:-x[1]))
    return f'Model hunt: {parts}'
for lg in ['NFL','ATP','WTA','PGA']:
    if slc.get(lg,0)==0: continue
    lines=[]
    matches=[r.get('match') or f"{r.get('away','')} @ {r.get('home','')}" for r in slate if r.get('league')==lg]
    lines.append(f"Slate: {slc[lg]} {'game' if slc[lg]==1 else 'events'}" + (f" - {matches[0]}" if slc[lg]==1 else ''))
    hl=hunt_line(lg)
    if hl:
        cuts=[e for e in hunt if e.get('league')==lg and e.get('verdict')=='cut']
        if cuts: hl+=f" (cut: {cuts[0].get('reason','')})"
        lines.append(hl)
    if lg=='NFL':
        try: n_ev=len(load('/tmp/odds_prefill_st.json',{}).get('games',load('/tmp/odds_prefill_st.json',[])))
        except Exception: n_ev='?'
        lines.append(f"Side/total engine: {n_ev} events priced, {len(cand_st)} candidates")
        pr=props.get('rows') or []
        rc=collections.Counter(r.get('reason') for r in pr if r.get('verdict')=='REJECT')
        rtxt='; '.join(f'{k} x{n}' for k,n in rc.most_common(3))
        lines.append(f"Props: {props.get('n_priced_rows',0)} rows priced, {props.get('n_kalshi_bound',0)} Kalshi-bound, {props.get('n_candidates',0)} candidates" + (f" - rejects: {rtxt}" if rtxt else ''))
    if lg in ('ATP','WTA'):
        pref='KX'+lg
        cats=[c for c in catch.get('catches',[]) if c.get('series','').startswith(pref)]
        npriced=sum(len(c.get('sides',[])) for c in cats)
        npass=sum(1 for c in cats for s in c.get('sides',[]) if (s.get('net_edge_c') or -99)>=2)
        lines.append(f"{len(cats)} matches settling {DT}, {npriced} sides priced (Polymarket fair anchor), {npass} passed P-EDGE-001")
        lines += notes
    if lg=='PGA':
        lines.append('No card market coverage - evaluated rows were capability gaps, not picks')
    sections.append({'espn_league': LG[lg], 'lines': lines})
json.dump({'date': DT, 'sections': sections}, open(f'/tmp/eval_summary_{DT}.json','w'), indent=1)
print('eval sections:', [(s['espn_league'], len(s['lines'])) for s in sections])
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
RP_EVAL_SUMMARY=/tmp/eval_summary_$DT.json python3 scripts/build_gh_page.py /tmp/manifest_preview_$DT.json /tmp/card_preview_$DT.html || echo "STAGE FAIL build_gh_page"
echo "== chain end $(date -u +%FT%TZ)"
