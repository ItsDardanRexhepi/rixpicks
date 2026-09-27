#!/usr/bin/env python3
"""Hunt evaluator v2 - per-event gates over the local-day slate. Reusable (speed directive).
Usage: python3 hunt_v2.py /tmp/slate_day_<date>.json /tmp/hunt_v2_<date>.jsonl
"""
import json, datetime, re, sys, os, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # repo-local urf (packaged)
sys.path.insert(0,'/home/sandbox')
import urf  # URF core (user directive phonemsg-01M3FR1WBQXZFBHXSQ8ZQ45HMH): every candidate card decision runs the six gates
def _newest(pat):
    fs = sorted(glob.glob(pat), key=os.path.getmtime)
    return fs[-1] if fs else None
MKTS_PATH='/tmp/kalshi_open_by_league.json'; CFB_PATH='/tmp/cfb_weighted.json'; MLB_PATH=_newest('/tmp/mlb_*_edges.json')
_missing=[n for p,n in ((MKTS_PATH,'kalshi open feed'),(CFB_PATH,'cfb model'),(MLB_PATH,'mlb edges'),
                        ('/tmp/mls_edges.json','mls edges'),('/tmp/nwsl_model_out.json','nwsl model')) if not p or not os.path.exists(p)]
if _missing:
    print('FAIL LOUD: missing production feeds: '+', '.join(_missing)+' - hunt cannot run; fix the feed chain, do not degrade quietly'); sys.exit(2)
slate = json.load(open(sys.argv[1]))
mkts = json.load(open(MKTS_PATH))
cfb_model = {g['id']: g for g in json.load(open(CFB_PATH))}
def gem_check(best):
    """J-119 gem screen: near-miss candidates get flagged, not silently cut."""
    if not best: return None
    reasons=[]
    if 0 <= best['gross_c'] < 2: reasons.append(f"near-bar model edge {best['gross_c']:+.1f}c")
    if 55 <= best['ask']*100 <= 75: reasons.append(f"price zone {best['ask']:.0%}")
    if best['side']=='home': reasons.append('home side')
    return reasons if len(reasons)>=2 else None
gems=[]

mlb_edges = [e for e in json.load(open(MLB_PATH)) if 'side' in e]
mls_edges = json.load(open('/tmp/mls_edges.json'))
nwsl_model = json.load(open('/tmp/nwsl_model_out.json'))

def fee(ask): return 0.07*ask*(1-ask)
def tok(s): return re.sub(r'[^A-Z0-9]','',(s or '').upper())
def daycode(commence_utc):
    # Kalshi event-ticker date token (YYMMMDD) from the game's commence, user-local day
    from zoneinfo import ZoneInfo
    dt = datetime.datetime.fromisoformat(commence_utc.replace('Z','+00:00')).astimezone(ZoneInfo('America/Los_Angeles'))
    return dt.strftime('%y%b%d').upper()
def bind_standard(row, markets):
    ALIAS={'CHW':'CWS','ARI':'AZ'}  # ESPN abbr -> Kalshi abbr
    aa0, ha0 = tok(row.get('away_abbr')), tok(row.get('home_abbr'))
    aa, ha = ALIAS.get(aa0,aa0), ALIAS.get(ha0,ha0)
    if not aa or not ha: return []
    # exact-instance: same-day date token + EXACT away+home or home+away abbr concat (substring matching
    # produced the Oklahoma@Georgia -> HOUGASO contamination; under-binding is the safe direction)
    dc = daycode(row['commence_utc'])
    ok = {aa+ha, ha+aa}
    def code(t):
        seg = t.split('-')[1]
        seg = re.sub(r'^\d{2}[A-Z]{3}\d{2}','',seg)  # strip the YYMMMDD date token
        return re.sub(r'^\d{4}','',seg)  # MLB embeds a HHMM start-time token before the team concat
    return [m for m in markets if dc in m['ticker'] and code(m['ticker']) in ok]
def _surnames(match_str):
    parts = re.split(r'\s+vs\.?\s+', match_str.split('[')[0], flags=re.I)
    out = []
    for p in parts[:2]:
        words = [w for w in re.findall(r"[A-Za-z']+", p) if len(w) >= 3]
        if words: out.append(words[-1].lower())
    return out
def bind_fight(row, markets):
    sn = _surnames(row['match'])
    if len(sn) < 2: return []  # fail closed - cannot identify both fighters
    return [m for m in markets if all(s in (m.get('title') or '').lower() for s in sn)]
def bind_tennis(row, markets):
    sn = _surnames(row['match'])
    if len(sn) < 2: return []
    return [m for m in markets if all(s in (m.get('title') or '').lower() for s in sn)]
def model_fair(lg, r):
    if lg=='CFB':
        g=cfb_model.get(r.get('parent_event_id'))
        return ({'home':g['adj_home']/100,'away':1-g['adj_home']/100}, 'cfb_weights FPI blend') if g else (None,'')
    if lg=='MLB':
        AL={'CHW':'CWS','ARI':'AZ'}
        key=f"{AL.get(r.get('away_abbr'),r.get('away_abbr'))}@{AL.get(r.get('home_abbr'),r.get('home_abbr'))}"
        er={e['side']:e['model'] for e in mlb_edges if e.get('game')==key}
        if not er: return None,''
        def match(s, full): 
            s=s.lower(); full=(full or '').lower()
            return s in full or (s=="a's" and 'athletics' in full)
        hm=next((v for s,v in er.items() if match(s, r.get('home'))), None)
        am=next((v for s,v in er.items() if match(s, r.get('away'))), None)
        if hm is None or am is None: return None,''
        return {'home':hm,'away':am}, 'mlb weights'
    if lg=='MLS':
        key=f"{r.get('away_abbr')}@{r.get('home_abbr')}"
        er={e['side']:e['model'] for e in mls_edges if e.get('match')==key}
        return ({'home':er.get(r.get('home_abbr')),'away':er.get(r.get('away_abbr'))}, 'soccer xG 3-way (win leg)') if er else (None,'')
    if lg=='NWSL':
        key=f"{r.get('away_abbr')}@{r.get('home_abbr')}"
        g=next((x for x in nwsl_model if x.get('match')==key), None)
        return ({'home':g['model']['home'],'away':g['model']['away']}, 'soccer xG 3-way (win leg)') if g else (None,'')
    return None,''

log=[]; cands=[]
for r in slate['rows']:
    lg=r['league']
    entry={'league':lg,'instance_id':r['instance_id'],'match':r.get('match') or f"{r.get('away')} @ {r.get('home')}",
           'match_type':r.get('match_type','game'),'commence_utc':r['commence_utc'],'status':r['status']}
    if r['status']!='STATUS_SCHEDULED':
        entry['verdict']='not hunted'; entry['reason']=f"already {r['status'].replace('STATUS_','')}"; log.append(entry); continue
    bound = bind_tennis(r, mkts.get(lg,[])) if lg in ('ATP','WTA') else bind_fight(r, mkts.get(lg,[])) if lg=='UFC' else bind_standard(r, mkts.get(lg,[])) if lg in mkts else []
    entry['markets_bound']=[(m['ticker'],m.get('yes_ask_dollars')) for m in bound]
    if lg=='NHL':
        entry['verdict']='not_evaluable'; entry['reason']='capability gap: no NHL fair engine (preseason) - not a genuine evaluation'; log.append(entry); continue
    if lg=='PGA':
        entry['verdict']='not_evaluable'; entry['reason']='capability gap: no per-match golf model (outright-only coverage) - not a genuine evaluation'; log.append(entry); continue
    if lg=='UFC':
        # fail-loud: absent league key or series fetch errors = board state UNKNOWN, never 'no market'
        if 'UFC' not in mkts or mkts.get('_errors',{}).get('UFC'):
            entry['verdict']='not_evaluable'; entry['reason']=f"board state unknown: UFC series fetch failed ({mkts.get('_errors',{}).get('UFC')}) - rerun board build"; log.append(entry); continue
        if not bound:
            entry['verdict']='not_evaluable'; entry['reason']='capability gap: no market bound across UFC series (KXUFCFIGHT+KXMMAFIGHT, healthy fetch)'; log.append(entry); continue
        entry['verdict']='not_evaluable'; entry['reason']='capability gap: market bound but no UFC fair engine (Elo buildout pending) - not a genuine evaluation'; log.append(entry); continue
    if not bound:
        entry['verdict']='not_evaluable'; entry['reason']='capability gap: no executable Kalshi market bound to this exact instance (date+teams verified) - not a genuine evaluation'; log.append(entry); continue
    if lg in ('ATP','WTA'):
        entry['verdict']='not_evaluable'; entry['reason']='capability gap: price bound but no tennis fair engine (exchange-anchored model cannot diverge; book-reference feed buildout pending) - not a genuine evaluation'; log.append(entry); continue
    fair,note = model_fair(lg,r)
    entry['model']=note or None
    if not fair or fair.get('home') is None or fair.get('away') is None:
        entry['verdict']='not_evaluable'; entry['reason']='capability gap: market bound but no model read for this event'; log.append(entry); continue
    best=None
    ha, aa = tok(r.get('home_abbr')), tok(r.get('away_abbr'))
    hword = (r.get('home','').split() or [''])[0].lower()
    aword = (r.get('away','').split() or [''])[0].lower()
    for m in bound:
        t=(m.get('title') or '').lower()
        ya=m.get('yes_ask_dollars')
        if ya is None: continue
        ya=float(ya)
        # primary: ticker suffix token = the side's abbr; fallback: first word of team name in title
        suffix = m['ticker'].rsplit('-',1)[-1].upper()
        if suffix == ha: side='home'
        elif suffix == aa: side='away'
        elif hword and hword in t: side='home'
        elif aword and aword in t: side='away'
        else: continue
        p=fair[side]; gross=p-ya; net=gross-fee(ya)
        if best is None or net>best['net_c']: best={'side':side,'model':round(p,3),'ask':ya,'gross_c':round(gross*100,1),'net_c':round(net*100,1),'title':m.get('title'),'ticker':m['ticker']}
    entry['best_side']=best
    if not best:
        entry['verdict']='cut'; entry['reason']='model sides not matchable to bound market titles - JOIN DEFECT'
    elif best['ask']>=0.85:
        entry['verdict']='cut'; entry['reason']=f"genuine evaluation: 85%+ market-price pre-filter (ask {best['ask']:.0%}) - standing rule"
    elif best['gross_c']<2:
        entry['verdict']='cut'; entry['reason']=f"genuine evaluation: no edge vs executable ask (gross {best['gross_c']:+.1f}c < 2c bar; model {best['model']:.1%} vs {best['ask']:.0%})"
        g=gem_check(best)
        if g:
            entry['gem']=True; entry['gem_reasons']=g+['availability pending probe']; gems.append(entry)
            # J-122 core gate wiring (rps_tmp/kb/core/card_gate.py): a gem is cardable only with a
            # validated Kalshi binding for this event+class+side. Carding still needs the J-119
            # 2-evidence-check bar via core/gems.py - this flag marks eligibility, not a card.
            try:
                sys.path.insert(0,'/home/sandbox/rix_tmp')  # in-repo core/ package (canonical call site)
                from core.binding import KalshiBinding as _KB
                from core.card_gate import card_eligible as _ce
                import os as _os
                # binding built from the REAL market record in mkts (status/ask from the record,
                # freshness from the feed file's fetch time) - never asserted; missing fields fail closed.
                _rec = None
                for _lg, _lst in mkts.items():
                    for _m in (_lst if isinstance(_lst, list) else []):
                        if _m.get('ticker') == best.get('ticker'): _rec = _m; break
                    if _rec: break
                if not _rec: raise ValueError('ticker not in Kalshi open feed - cannot bind')
                _ask = _rec.get('yes_ask') or (float(_rec['yes_ask_dollars'])*100 if _rec.get('yes_ask_dollars') else None)
                _b = _KB(ticker=_rec['ticker'], event_id=entry['instance_id'], market_class='ml',
                         side=best['side'], status=_rec.get('status','unknown'),
                         ask_c=_ask if _ask else -1,
                         quote_ts=datetime.datetime.fromtimestamp(_os.path.getmtime('/tmp/kalshi_open_by_league.json'), datetime.timezone.utc).isoformat())
                entry['gem_gate'] = list(_ce(_b, 'ml', entry['instance_id'], best['side']))
            except Exception as _e:
                entry['gem_gate'] = [False, f'gate closed: {_e}']
            entry['reason']+=' | GEM FLAG (J-119): '+', '.join(g) + f" | gate: {entry['gem_gate'][1]}"
    elif best['net_c']<0.5:
        entry['verdict']='cut'; entry['reason']=f"genuine evaluation: gross {best['gross_c']:+.1f}c dies after fee (net {best['net_c']:+.1f}c)"
    else:
        # URF gate (six-gate decision protocol, phonemsg-01M3FR1WBQXZFBHXSQ8ZQ45HMH).
        # C: card criteria testable+agreed=3 ('JOIN DEFECT' caveat would have cut above). F: engine ran, proven path=3.
        # R: paper card, internal, reversible=1 (money execution is separately gated R=3 + J-043 exact-state approval).
        # U: book convergence + availability not yet verified at this stage = 2 -> canonical outcome PROBE:
        #    the probe IS the convergence+availability step; the pick only cards after it runs clean (auto-card
        #    authority phonemsg-01M3F71QZCGMZ5109NE1M2HEPN covers EXECUTE outcomes, not PROBE ones).
        # V: net edge >=2c meaningful=2, >=5c high-leverage=3. CE: first coverage of a league today=1.
        d = urf.decide(f"card {lg} {entry['match']}",
                       C=3, F=3, R=1, U=2,
                       V=3 if best['net_c']>=5 else 2,
                       CE=1, T='medium',
                       rationale=f"{best['side'].upper()} model {best['model']:.1%} vs ask {best['ask']:.0%}: gross {best['gross_c']:+.1f}c net {best['net_c']:+.1f}c",
                       evidence=[best['ticker']], approach='hunt_v2-candidate',
                       artifact='picks card after convergence+availability probe',
                       verification='fresh cache-busted fetch + live render vs book reference')
        entry['urf']={'decision':d['line'],'id':d['record']['id'],'outcome':d['outcome']}
        entry['verdict']='CANDIDATE'
        entry['reason']=f"{best['side'].upper()} model {best['model']:.1%} vs ask {best['ask']:.0%}: gross {best['gross_c']:+.1f}c net {best['net_c']:+.1f}c | {d['line']} -> probe: run book convergence + availability, then card on clean pass"
        cands.append(entry)
    log.append(entry)

json.dump(log, open(sys.argv[2],'w'), indent=1)
import collections
print('verdicts:', collections.Counter(e['verdict'] for e in log))
print('gems:', [(g['match'], g['gem_reasons']) for g in gems])
print('CANDIDATES:', len(cands))
for c in sorted(cands, key=lambda e:e['commence_utc']):
    print(' ', c['league'], c['match'], '->', c['reason'])
gen = sum(1 for e in log if e.get('reason','').startswith('genuine evaluation'))
cap = sum(1 for e in log if e.get('reason','').startswith('capability gap'))
print(f'genuine evaluations: {gen} | capability gaps: {cap} | not hunted (started/final): {sum(1 for e in log if e["verdict"]=="not hunted")}')

# --- TIER EVAL (J-096 ladder + user directive 2026-09-26 12:23:57 PT) ---
def tier_eval(fair_c, gross_c):
    # J-096 (user iMessage 2026-09-25 10:33:20): 60-69c=5u, 70-79c=10u, 80-89c=15u, 90c+=100u
    # User directive phonemsg-01M3FJTAVAKTMTQ89WTX0K64QN (iMessage 2026-09-26 12:24:34 PM, verbatim verified):
    #   'If you have 3c games. Put them in the 10u tier and run it against that tiers math
    #   to see if it can get approved to get accepted for that tier'
    #   10u requires BOTH fair 70-79c AND gross >= 3c; a 70-79 fair with gross < 3c is not
    #   approved for the tier and cards at the 5u rung instead. 15u/100u tiers unchanged (band-only).
    if fair_c>=90: return 100
    if 80<=fair_c<90: return 15
    if 70<=fair_c<80: return 10 if gross_c>=3 else 5
    if 60<=fair_c<70: return 5
    return 0  # below card band
