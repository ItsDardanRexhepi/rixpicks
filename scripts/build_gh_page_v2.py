#!/usr/bin/env python3
"""Generate a self-contained index.html ('RixPicks picks page) for GitHub Pages from a manifest JSON.
Usage: build_gh_page.py manifest.json [outfile]
Manifest: {date_label, status_note, record, updated, picks:[{num,name,sub,odds,best_book,side,game:{away,home}|null,espn_league}], parlay:{legs:[...],note}|null}
DESIGN LOCKED (user, Sep 24 10:50 PM): this template IS the app design system. Daily builds change picks
content only - never layout, chip styling, terminology logic. Bump RP_DESIGN only on an approved design change.
Chips resolved from /tmp/odds_prefill.json (+ _sp) when present; NO chips render without a game-level link.
Branding: 'RixPicks only. No personal identifiers, ever.
"""
import json,sys,html,re,os

# Publish hygiene: shipped pages never carry internal session narration, directive
# provenance, or personal attributions. Functional comments stay; narration goes.
import re as _re_scrub
_SCRUB_PAT=_re_scrub.compile(r"(his\b|her\b|\buser\b|\bmain\b|swarm|swamp|tester|inspector|sentinel|matrix|batch ?\d|round-?\d|doctrine|ux bar|verbatim|approved|regression gate|9/2[0-9]|sep ?2[0-9]|u-disp|j-10\d|core-kill|re-audit|swamp catch|his rule|order)",_re_scrub.I)
def _scrub_comment(c):
    return '' if _SCRUB_PAT.search(c) else c
def scrub_shipped(html_out):
    html_out=_re_scrub.sub(r"/\*[\s\S]*?\*/",lambda m:_scrub_comment(m.group(0)) or '/* */',html_out)
    html_out=_re_scrub.sub(r"(?<![:>'\"/])//[^\n]*",lambda m:_scrub_comment(m.group(0)),html_out)
    html_out=_re_scrub.sub(r"<!--[\s\S]*?-->",lambda m:_scrub_comment(m.group(0)),html_out)
    return html_out

def _urf(decision,scores,action,why):
    # Matrix outcome_truth/urf.py doctrine (Sep 26 inspection): every deploy-affecting build choice
    # emits one auditable fixed-order decision line (C,F,R,U,V,CE + T). Log lives in build output,
    # not just chat. Scores are 0-3; T = time sensitivity.
    print(f"URF Decision: {decision} - {scores} | {action}: {why}", file=sys.stderr)

# Feed arbiter transport (main Sep 26 2:44:52): registry + arbiter module are build inputs with a
# SINGLE writer; the build fails loudly if they are missing or the version stamp drifts.
try:
    _ARB_SRC=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','feed_arbiter.js')).read()
    _REG=json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','feed_registry.json')))
except Exception as _e:
    print(f"BUILD FAILED: feed arbiter/registry unreadable ({_e}) - fail loud, never bake a guess", file=sys.stderr)
    sys.exit(4)
if str(_REG.get('version'))!='1.8':
    _urf("ABORT","C=3 F=0 R=3 U=2 V=2 CE=0 T=med","registry stamp drift",f"registry version {_REG.get('version')} != 1.8 - refusing to bake stale clock config")
    sys.exit(4)
_CLG=json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','config_leagues.json')))['leagues']
_RP_SPORT_CLOCK={}
for _lk,_lv in _CLG.items():
    _sc=(_REG.get('sport_clock') or {}).get(_lk)
    if _sc and _lv.get('espn'):
        _RP_SPORT_CLOCK[_lv['espn']]={'period_seconds':_sc['period_seconds'],'counts_down':_sc['counts_down']}
# registry-clocked leagues with no config_leagues entry still bake their clock (tester hold Sep 26:
# FIFA_WC/EPL count-up cfgs were silently dropped - the registry is the source of truth, all 10 ride)
for _lk,_esp in [('FIFA_WC','soccer/fifa.world'),('EPL','soccer/eng.1')]:
    _sc=(_REG.get('sport_clock') or {}).get(_lk)
    if _sc:
        _RP_SPORT_CLOCK.setdefault(_esp,{'period_seconds':_sc['period_seconds'],'counts_down':_sc['counts_down']})
ARB_INJECT=_ARB_SRC+'\nvar RP_SPORT_CLOCK='+json.dumps(_RP_SPORT_CLOCK,separators=(',',':'))+';\n' 

_V2=os.environ.get('RP_V2')!='0'  # v2 dark shell is the default build. RP_V2=0 reproduces v1.2.0 exactly (escape hatch).
RP_DESIGN='2.0.0' if _V2 else '1.2.0'  # locked design system version - bump only on user-approved design change. v1.1.0 (user, Sep 25 12:35 AM): match visitor system appearance - light (default, unchanged) + dark via prefers-color-scheme. v1.2.0 (user, Sep 25 8:46 AM): current page shape approved as THE standing daily template - header without FINAL line, tap-any-book intro, per-pick chips + units, combo section, record + unit line, minimal footer (reference commit fbec1c1). Every morning build reproduces this exact shape; changes only on his explicit instruction.

def _pt_date(iso):
    # Sep 26 builder fix: real America/Los_Angeles conversion - a hard-coded UTC-7 is wrong in PST.
    try:
        import datetime as _dt
        from zoneinfo import ZoneInfo
        return _dt.datetime.fromisoformat((iso or '').replace('Z','+00:00')).astimezone(ZoneInfo('America/Los_Angeles')).date().isoformat()
    except Exception: return ''

man=json.load(open(sys.argv[1]))
# --- pick-content hash gate (permanent): price ship conditions gate pick CONTENT only.
# manifest carries pick_content_hash = sha256 over the FULL canonical pick object (see exclusion
# list in _pick_content_hash). Any real content change forces the full gate.
# same hash as last shipped (shipped_pick_hash.txt) = display-only rebuild = conditions skipped.
# A manifest display_only flag is NEVER honored: absence of the shipped hash takes the normal
# publish path with full condition eval - only a hash match can skip it.
import hashlib as _hl
def _pick_content_hash(m):
    # Full-object hashing (hunter reject 3): hash the canonical FULL pick object so any content
    # field - current or future - is covered automatically. EXCLUSION LIST (volatile/non-content
    # operational fields, audit before extending): num (build-assigned display order), result and
    # _final (post-settlement grading state, not pick content), polycents (live Polymarket price
    # snapshot), kalshi.cents (live Kalshi ask snapshot - the gate re-checks it live anyway),
    # card_ts (first-lock provenance - excluded per main Sep 27 10:04 ruling; its stability is
    # guarded by the dedicated ledger-equality assertion in build_manifest.py, not by this hash).
    _EXCL_TOP={'num','result','_final','polycents','card_ts'}
    def _canon(p):
        c={k:v for k,v in p.items() if k not in _EXCL_TOP}
        if isinstance(c.get('kalshi'),dict):
            c['kalshi']={k:v for k,v in c['kalshi'].items() if k!='cents'}
        # d03ba56 contract: dkp harvest snapshots are volatile like kalshi.cents - prices/harvest
        # metadata excluded; the market URL stays (a new arm = content change = full gate).
        c.pop('dkp_note',None)
        if isinstance(c.get('dkp'),dict):
            c['dkp']={k:v for k,v in c['dkp'].items() if k not in ('team_cents','home_cents','away_cents','derived','harvested')}
            if not c['dkp']: c.pop('dkp')
        return c
    rows=sorted(json.dumps(_canon(p),sort_keys=True) for p in m.get('picks',[]))
    return _hl.sha256('\n'.join(rows).encode()).hexdigest()
_PC_HASH=_pick_content_hash(man)
_DECLARED_HASH=man.get('pick_content_hash')
if _DECLARED_HASH and _DECLARED_HASH!=_PC_HASH:
    print(f'BUILD FAILED: manifest pick_content_hash {_DECLARED_HASH[:12]}... != computed {_PC_HASH[:12]}... - manifest integrity', file=sys.stderr)
    sys.exit(3)
_HASHF=os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])),'shipped_pick_hash.txt')
_LAST_HASH=''
if os.path.exists(_HASHF):
    try: _LAST_HASH=open(_HASHF).read().strip()
    except Exception: _LAST_HASH=''
_DISPLAY_ONLY=bool(_LAST_HASH and _LAST_HASH==_PC_HASH)
if man.get('display_only') is True and not _LAST_HASH:
    print('manifest display_only flag IGNORED: no shipped pick-content hash on record - full condition eval', file=sys.stderr)
if _DISPLAY_ONLY:
    print(f'DISPLAY-ONLY BUILD (pick-content hash {_PC_HASH[:12]} matches last shipped): price ship conditions skipped', file=sys.stderr)
# Sep 26 live regression (hunter 7:25 AM): an hourly odds refresh rebuilt record/units from a stale
# manifest and clobbered the tracker-canonical live values. Refresh builds (RP_REFRESH=1) INHERIT
# record/units from the live page being rebuilt; only an approved publish (RP_PUBLISH=1) may move
# them, from a manifest staged off the tracker at ship time.
if os.environ.get('RP_REFRESH')=='1':
    # Main ruling Sep 27 2:32 PM (option a, one-record-one-source): refresh builds take record/units
    # from the MANIFEST as loaded - never from the live page. The page's baked rpRec attributes went
    # stale (13-6/+3.89u) and every pin re-poisoned the next build, flashing the wrong record on
    # first paint while hydration showed the right one. Manifest is canonical post-fc312355.
    # Fail CLOSED: a refresh whose manifest lacks record/units aborts loudly with NO write.
    if not man.get('record') or not man.get('units_pl'):
        print('REFRESH ABORTED: manifest.json missing record/units - no write, no push', file=sys.stderr)
        sys.exit(5)
    print(f"REFRESH SOURCE: record {man['record']} / units {man['units_pl']} from manifest.json (canonical)", file=sys.stderr)
def _rawurl(u):
    # Sep 26 builder fix: links can arrive HTML-escaped (past builds escaped into storage);
    # storage is RAW, escaping happens once at render. Loop because some stored links are double-escaped.
    if not u: return u
    prev=None; cur=str(u)
    for _ in range(3):
        if cur==prev: break
        prev=cur; cur=html.unescape(cur)
    return cur
def _sanitize_man(man):
    # Chaos-drill hardening (Sep 26): a present-but-null section or leg must never crash the build -
    # null coerces to empty at ingestion, the card ships with what IS verified (degraded mode).
    if not isinstance(man.get('picks'),list): man['picks']=[]
    man['picks']=[p for p in man['picks'] if isinstance(p,dict)]
    for p in man['picks']:
        for sect in ('game','kalshi','dkp','fdp','polymarket','polymarket_us'):
            if p.get(sect) is None: p[sect]={}
    if man.get('parlay') is None: man['parlay']={}
    pl=man.get('parlay') or {}
    for sect in ('kalshi_legs','poly_legs'):
        if not isinstance(pl.get(sect),list): pl[sect]=[]
        pl[sect]=[l for l in pl[sect] if isinstance(l,dict)]
    if not isinstance(pl.get('routes'),dict): pl['routes']={}
    for p in man.get('picks',[]):
        for sect in ('kalshi','dkp','fdp','polymarket','polymarket_us'):
            if isinstance(p.get(sect),dict) and p[sect].get('url'): p[sect]['url']=_rawurl(p[sect]['url'])
    pl=man.get('parlay') or {}
    for sect in ('kalshi_legs','poly_legs'):
        for l in (pl.get(sect) or []):
            if isinstance(l,dict) and l.get('url'): l['url']=_rawurl(l['url'])
    for r in (pl.get('routes') or {}).values():
        if isinstance(r,dict) and r.get('link'): r['link']=_rawurl(r['link'])
_sanitize_man(man)
out=sys.argv[2] if len(sys.argv)>2 else '/home/sandbox/gh_page/index.html'
BOOKS=[('BetRivers','BR'),('DraftKings','DK'),('FanDuel','FD'),('Hard Rock','HR'),('Kalshi','KAL'),('BetMGM','MGM'),('Polymarket','POLY'),('theScore','TSB')]  # alphabetical by displayed chip label (his Sep 25 9:19 AM spec: alphabetical chips; audit Sep 26 caught combo order regressed - root fix is the shared order, solo+combo read the same sequence)  # U-GEO-003: ESPN BET is DEAD - dropped at ingestion, never mapped (tester gate). theScore Bet is the single canonical arm (one chip per arm).
BKDOM={'DK':'draftkings.com','FD':'fanduel.com','TSB':'thescore.bet','HR':'hardrock.bet','MGM':'betmgm.com','BR':'betrivers.com','KAL':'kalshi.com','POLY':'polymarket.com','B365':'bet365.com','FAN':'fanatics.com','DKP':'predictions.draftkings.com','FDP':'fanduel.com'}
_POLY_US_ABBR={'nyl':'ny'}
_POLY_US_PRICED=False  # 9/27 P1 (main 8:31): .com-gamma quotes never label .us-linked POLY chips (Bengals -150 vs .us -163 class). Flip True ONLY when analysis ships verified .us-sourced quotes; until then POLY chips are destination-only and excluded from best-line.  # add entries ONLY after verifying the .us slug live; verified 9/27: nyl->ny
def _poly_us_url(slug):
    # polymarket.us serves events under /sports/<sport>/<slug>, NOT /event/<slug> (soft-404 shell).
    # .us team abbrs diverge from .com slugs for shared-city teams (verified 9/27: wnba-nyl-min -> wnba-ny-min).
    parts=slug.split('-'); sport=parts[0]
    parts=[parts[0]]+[_POLY_US_ABBR.get(x,x) for x in parts[1:]]
    return 'https://polymarket.us/sports/'+sport+'/'+'-'.join(parts)

# Brand fills (user 9/24 10:48 PM): every chip filled with the platform's own brand colors. (bg, fg)
BKFILL={'DK':('#0b0e11','#53d337'),'FD':('#e7f3ff','#0e6fd0'),'TSB':('#0d1b2e','#4d94ff'),'HR':('#faf3dd','#8a6d1a'),'MGM':('#f5f0e4','#7a6226'),'BR':('#e3f5fc','#0278a6'),'KAL':('#e6f9f3','#0a7c5c'),'POLY':('#e8f3fc','#1a6db0'),'B365':('#fff9db','#6b5900'),'FAN':('#f0f0f2','#1a1a1a'),'DKP':('#0b1a0e','#9be25f'),'FDP':('#e7f3ff','#4d9de0')}
def bkimg(short):
    d=BKDOM.get(short)
    return f'<img class="bklogo" src="https://www.google.com/s2/favicons?domain={d}&sz=128" alt="" onerror="this.remove()">' if d else ''
def bkstyle(short):
    bf=BKFILL.get(short)
    return f' data-bk="{short}" style="background:{bf[0]};border-color:{bf[0]};color:{bf[1]}"' if bf else ''
def _rh(x):
    # half-up rounding, identical to JS Math.round - Python round() is banker's and drifted card vs game-page ML display (sentinel 9/26: POLY 68c showed -212 card / -213 game header)
    import math
    return int(math.floor(float(x)+0.5))
def _clbl(c):
    # U-DISP-001: PM-arm chips display cents (57c, 38.2c); comparison math stays American via c2ml_int
    return ('%g'%round(c,1))+'c'
def c2ml_int(c):
    # raw American int for star/range math even when the display goes cents notation (main 11:11)
    c=_rh(c)
    if c<=0 or c>=100: return None
    return -(_rh(c/(100-c)*100)) if c>=50 else _rh((100-c)/c*100)
def c2ml(c):
    c=_rh(c)
    if c<=0: return str(c)
    if c>=100: return f"{c}c"  # 100c ask: American odds can't express it - exchange-native cents (main 11:11)
    ml=_rh(c/(100-c)*100) if c>=50 else _rh((100-c)/c*100)
    return ('-' if c>=50 else '+')+str(ml)
def _pt_time(iso):
    try:
        import datetime as _dt
        from zoneinfo import ZoneInfo
        t=_dt.datetime.fromisoformat((iso or '').replace('Z','+00:00')).astimezone(ZoneInfo('America/Los_Angeles'))
        return t.strftime('%I:%M %p').lstrip('0')+' PT'
    except Exception: return ''
def _is_underway(g):
    try:
        import datetime as _dt
        c=(g or {}).get('commence')
        if not c: return False
        return _dt.datetime.now(_dt.timezone.utc)>=_dt.datetime.fromisoformat(c.replace('Z','+00:00'))
    except Exception: return False
def wl_pct_line(rec):
    try:
        w,l=[int(x) for x in str(rec).split('-')]
        if w+l<=0: return ''
        return f'<div class="yesrec" id="rpWlPct">W/L: {100.0*w/(w+l):.1f}%</div>'
    except Exception:
        return ''
LG_LABEL={'baseball/mlb':'MLB','football/nfl':'NFL','basketball/nba':'NBA','hockey/nhl':'NHL','basketball/wnba':'WNBA','football/college-football':'CFB','basketball/college-basketball':'CBB','tennis':'Tennis','tennis/atp':'ATP','tennis/wta':'WTA','soccer/usa.1':'MLS','soccer/usa.nwsl':'NWSL','golf/pga':'PGA','racing/nascar':'NASCAR','mma/ufc':'UFC','boxing':'Boxing'}
def poly_event_slug(url):
    try: return url.split('/event/')[1].split('/')[0]
    except Exception: return None
def poly_sub(url):
    try:
        parts=url.split('/event/')[1].split('/')
        return parts[1] if len(parts)>1 and parts[1] else None
    except Exception: return None
def poly_price(url,kw,won_ok=False):
    slug=poly_event_slug(url)
    if not slug: return None
    try:
        # Authenticated POLY transport (owner directive Sep 27): gateway.polymarket.us signed reads
        # are primary whenever POLYMARKET_API_KEY_ID/SECRET are present (CI). Secrets present but the
        # read failing -> fail closed (None), NEVER a silent public fallback on authed runners.
        # No secrets (local verification builds) -> legacy public gamma, so chip presence stays true.
        import os as _pos, sys as _psys
        _psys.path.insert(0, _pos.path.dirname(_pos.path.abspath(__file__)))
        import poly_us as _pus
        if _pos.environ.get('POLYMARKET_API_KEY_ID') and _pos.environ.get('POLYMARKET_API_SECRET'):
            ev=_pus.gamma_shaped(slug)
            if not ev: return None
        else:
            import urllib.request
            req=urllib.request.Request(f'https://gamma-api.polymarket.com/events?slug={slug}',headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(req,timeout=10) as r:
                ev=json.load(r)
        if not ev: return None
        kwl=kw.lower(); sub=poly_sub(url); mkts=ev[0].get('markets') or []
        target=None
        if sub:
            for m in mkts:
                if m.get('slug')==sub: target=m; break
        if target is None:
            for m in mkts:
                q=str(m.get('question') or '')
                if ':' in q: continue
                try: outs=json.loads(m.get('outcomes') or '[]')
                except Exception: continue
                if any(kwl in str(o).lower() for o in outs): target=m; break
        yn=False
        if target is None:
            for m in mkts:  # soccer-style 'Will <team> win ...' Yes/No markets: match by question, price = Yes
                q=str(m.get('question') or '').lower()
                if q.startswith('will ') and ' win' in q and kwl in q:
                    target=m; yn=True; break
        if target is None: return None
        outs=json.loads(target.get('outcomes') or '[]'); prs=json.loads(target.get('outcomePrices') or '[]')
        if yn and outs==['Yes','No'] and prs:
            c=round(float(prs[0])*100)
            if 0<c<100: return c
            return None
        for i,o in enumerate(outs):
            if kwl in str(o).lower() and i<len(prs):
                c=round(float(prs[i])*100)
                if 0<c<100: return c
                if won_ok and target.get('closed'):
                    if c==100: return 100  # resolved win - leg is home, factor 1
                    if c==0: return 0      # resolved loss - leg is dead; combo marks dead, chip is NEVER dropped (class fix 9/25: leg close = status update only)
    except Exception: return None
    return None
def _load_prefill(path, wrap=False):
    out={}
    def _deesc(x):
        if isinstance(x,str): return _rawurl(x)
        if isinstance(x,dict): return {k:_deesc(v) for k,v in x.items()}
        if isinstance(x,list): return [_deesc(v) for v in x]
        return x
    try:
        for g in json.load(open(path)):
            books=_deesc(g.get('books',{}))
            out.setdefault((g['away'],g['home']),[]).append((g.get('commence'), {'books':books} if wrap else books))
    except Exception as e:
        # Sep 26 chaos-drill fix: a missing/unreadable prefill must NEVER be silent (empty odds column class) -
        # chips degrade to manifest-only books and the build log says so loudly.
        print(f'PREFILL WARNING: {path} unavailable ({type(e).__name__}) - sportsbook chips degrade to manifest-only books', file=sys.stderr)
        return out
    print(f'prefill: {sum(len(v) for v in out.values())} slates from {path}', file=sys.stderr)
    return out
HIST={}
def _prefill_path(name):
    # Sep 26: repo-local prefill (next to the manifest or cwd) beats the pipeline's /tmp scratch path -
    # a hardcoded /tmp path silently zeroed sportsbook chips for any build outside the pipeline container.
    for c in (os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])),name), name, '/tmp/'+name):
        if os.path.exists(c): return c
    return '/tmp/'+name
pre=_load_prefill(_prefill_path('odds_prefill.json'))

def _espn_get(url):
    import urllib.request
    # ESPN 403s a bare 'Mozilla/5.0' UA (verified Sep 25); urllib default UA passes.
    with urllib.request.urlopen(url,timeout=12) as r: return json.load(r)

def team_meta(man):
    meta={}
    lgs={p.get('espn_league','') for p in man.get('picks',[]) if p.get('espn_league')}
    # logos bind to the CARD's own dates - a preview card's teams are not on today's board
    dates=set()
    for p in man.get('picks',[]):
        c=(((p.get('game') or {}).get('commence','') or '')[:10]).replace('-','')
        if c: dates.add(c)
    dates.add('')  # today as fallback (live rows)
    for lg in lgs:
        for d in dates:
            try:
                qs=('dates='+d if d else '')
                if lg=='football/college-football': qs+=(('&' if qs else '')+'groups=80&limit=400')
                sb=_espn_get('https://site.api.espn.com/apis/site/v2/sports/%s/scoreboard'%lg+('?'+qs if qs else ''))
                for ev in sb.get('events',[]):
                    comp=(ev.get('competitions') or [{}])[0]
                    for c in comp.get('competitors',[]):
                        t=c.get('team') or {}
                        nm=t.get('displayName','')
                        meta[(lg,nm)]={'id':t.get('id'),'abbr':t.get('abbreviation',''),'logo':t.get('logo',''),
                            'record':(c.get('records') or [{}])[0].get('summary','')}
            except Exception: pass
    return meta

TEAM_META={}


pre_sp=_load_prefill(_prefill_path('odds_prefill_sp.json'), wrap=True)
# J-106 (Sep 26): shipped book links freeze with the card. Prefill only knows live/upcoming
# games - a refresh rebuild for a settled game used to find nothing and DROP the chips
# (the Orioles-row regression he caught). shipped_books.json is committed with the site:
# fresh resolutions record into it every build; settled/missing games fall back to it.
SHIPPED={}
try:
    SHIPPED=json.load(open('shipped_books.json'))
    for _sk,_bm in SHIPPED.items():
        for _bn,_be in list(_bm.items()):
            if isinstance(_be,dict) and _be.get('link'): _be['link']=_rawurl(_be['link'])
except Exception: SHIPPED={}
NEWSHIPPED={}
# J-099+ (swamp+tester Sep 26): entry price AND entry timestamp are ONE immutable provenance pair,
# sourced from the original card record and carried in the shipped ledger keyed by card date.
# No publish path can re-stamp an entry: a rewritten manifest.updated only feeds the FIRST seed of a new card day.
import datetime as _dtc
def _card_date_of(m):
    # Sep 27 swamp kill (archived game-4..11 wore Saturday's 7:21 AM lock): the card date belongs to
    # the CARD, not the clock - derive from the picks' commence dates (PT), today only as a gameless
    # fallback. date.today() made post-midnight rebuilds pin whatever lock the ledger carried.
    from collections import Counter as _Ct
    _ds=[_pt_date((p.get('game') or {}).get('commence','')) for p in m.get('picks',[]) if isinstance(p,dict)]
    _ds=[d for d in _ds if d]
    return _Ct(_ds).most_common(1)[0][0] if _ds else _dtc.date.today().isoformat()
_CARD_DATE=_card_date_of(man)
_MAN_SHA=_PC_HASH  # card identity: canonical pick-content hash (tester hold Sep 27) - volatile
# operational fields (num/result/_final/polycents/kalshi.cents/dkp snapshots, updated stamp,
# formatting) never move it, so a same-card rebuild keeps the pin; real pick content moves it.
_cardprev=SHIPPED.get('__card__') or {}
# precedence (tester gate 5): the shipped-ledger pin WINS, but only on PROVEN card identity -
# same card date AND same canonical pick-content identity (teams/side/odds/units/commence;
# updated stamps, graded results, and formatting mutations do NOT move the pin). Sep 27:
# date-only matching let the live card's lock bleed
# into a same-day rebuild of a different card (the archived Friday-night 8-game card).
_pin_ok=_cardprev.get('date')==_CARD_DATE and _cardprev.get('picks_sha')==_MAN_SHA
_cts=[p.get('card_ts') for p in man.get('picks',[]) if p.get('card_ts')]
_ct_lock=None
if _cts:
    _c0=min(_cts)  # canonical provenance (main Sep 27 7:26): lock label carries the original ledger card_ts, never a rebuild restamp
    from zoneinfo import ZoneInfo as _ZI
    _c0d=_dtc.datetime.fromisoformat(_c0.replace('Z','+00:00')).astimezone(_ZI('America/Los_Angeles'))
    _ct_lock=_c0d.strftime('%b %d').replace(' 0',' ')+', '+_pt_time(_c0)
ENTRY_LOCK=(_cardprev.get('locked') if _pin_ok else None) or man.get('entry_locked') or _ct_lock or man.get('updated','')
_ODDS_CHECKED=man.get('stamp_label')=='odds_checked'  # reconstructed/archive card: odds-check evidence only, no lock event - render "Odds checked <stamp>", never "locked" (main ruling Sep 27)
def _stamp_html(p):
    if _ODDS_CHECKED:
        return 'Odds checked '+html.escape(ENTRY_LOCK)
    return html.escape((p.get('locked') or ENTRY_LOCK).split(', ')[-1].replace(' PT',''))+' &middot; locked'
_today_iso=_dtc.date.today().isoformat()
if _CARD_DATE>=_today_iso and (_cardprev.get('date')!=_CARD_DATE or not _cardprev.get('locked') or not _cardprev.get('picks_sha')):
    # the ledger tracks the CURRENT card only: a past-dated build (archive rebuild) never writes;
    # a same-date entry without an identity hash (legacy/corrupt) gets replaced by this card's.
    NEWSHIPPED['__card__']={'date':_CARD_DATE,'locked':ENTRY_LOCK,'picks_sha':_MAN_SHA}

# Canonical market truth record (Matrix-mining design, user 9/26): ONE record per
# (source,event,market,side) - price (cents canonical, ml display cache), phase, timestamp,
# verified link, status - drives every chip/star/range/combo. Never parse rendered text into numbers.
_MARKETS=[]
_COLL=[_MARKETS]  # current record collector: index -> _MARKETS; a game page -> its own _PM (data-mr indexes must match the page's injected RP_MARKETS)
def _mkrec(src,ev='',mkt='',side='',ml=None,cents=None,link='',ph='pre_game',ts='',lv='verified',st='ok'):
    if ml is None and cents is None and st=='ok':
        # swamp Sep 26: a null quote must never wear ok/verified - coerced at the record chokepoint
        # itself, loudly, so no present or future call site can bake a lying record.
        print(f"RECORD COERCED: {src} {mkt} {side} null quote carried st=ok - forced st=unknown (fail-closed)", file=sys.stderr)
        st='unknown'
    _COLL[0].append({'src':src,'ev':ev,'mkt':mkt,'side':side,'ml':ml,'c':cents,'link':link,'ph':ph,'ts':ts,'lv':lv,'st':st})
    return ' data-mr="%d"'%(len(_COLL[0])-1)
TEAM_META.update(team_meta(man))
def _meta_for(lg,name):
    m=TEAM_META.get((lg,name))
    if m: return m
    if not name: return {}
    for (l2,n2),v in TEAM_META.items():
        if l2==lg and n2 and (name in n2 or n2 in name): return v
    return {}

LG_BALL={'baseball/mlb':'\u26be','football/nfl':'\U0001f3c8','football/college-football':'\U0001f3c8','basketball/nba':'\U0001f3c0','basketball/wnba':'\U0001f3c0','basketball/college-basketball':'\U0001f3c0','hockey/nhl':'\U0001f3d2','tennis':'\U0001f3be','tennis/atp':'\U0001f3be','tennis/wta':'\U0001f3be','soccer/usa.1':'\u26bd','soccer/usa.nwsl':'\u26bd','golf/pga':'\u26f3','racing/nascar':'\U0001f3ce\U0000fe0f','mma/ufc':'\U0001f94a','boxing':'\U0001f94a'}

def game_instance(game):
    # J-092 (user, Sep 25 10:05 AM): when a team plays twice in a day, every chip must NAME
    # the game instance at tap time so the destination is never ambiguous.
    # Sep 26 builder fix: fall back to the GPK (schedule feed) candidate set when prefill is
    # thin, and match by NEAREST commence - string-exact matching missed on precision drift.
    if not game: return ''
    import datetime as _dt3
    cands=pre.get((game.get('away'),game.get('home')))
    comms=[c for c,_ in cands if c] if cands else []
    if len(comms)<2:
        comms=[c[3] for c in (GPK.get((game.get('away'),game.get('home'))) or []) if len(c)>3 and c[3]]
    if len(comms)<2: return ''
    ordered=sorted(comms)
    com=game.get('commence')
    if com and com in ordered: return f"G{ordered.index(com)+1}"
    try:
        _ct=_dt3.datetime.fromisoformat((com or '').replace('Z','+00:00'))
        def _dd(c):
            try: return abs((_dt3.datetime.fromisoformat(c.replace('Z','+00:00'))-_ct).total_seconds())
            except Exception: return 9e18
        return f"G{ordered.index(min(ordered,key=_dd))+1}"
    except Exception: return ''

def _canon_book(n):
    return {'draftkings':'draftkings','fanduel':'fanduel','espnbet':'espn bet','thescore':'espn bet','hardrockbet':'hard rock','betmgm':'betmgm','betrivers':'betrivers'}.get((n or '').lower(),(n or '').lower())
def _link_ids(u):
    # (event_scoped, selection_scoped) ids inside a book link. Sep 26 chaos drill: selectionIds
    # live in small recycled namespaces (a seat, not the game) - only event-scoped ids (or 2+
    # shared ids) prove a different event.
    ev=set(); sel=set()
    for pat in (r'outcomes=([0-9A-Za-z_]+)', r'marketId=([0-9.]+)', r'#event/(\d+)',
                r'/events?/(\d+)', r'-(\d{8,})(?:\?|$)', r'/event/[a-z0-9%40-]+/(\d{7,})',
                r'betslip/(\d+)'):
        for m in re.finditer(pat,u or ''): ev.add(m.group(1))
    # Sep 26 hotfix: betmgm template options=6:<event>-<market>-<selection> - the old [0-9-]+ pattern
    # captured only the leading '6' as an event id, so EVERY betmgm link shared it and any second
    # slate game >3h away false-rejected every betmgm carryover (live MGM chip drop, build 1790443075).
    # Colon-form carries the real event scope; the plain form keeps legacy behavior, colon excluded.
    for m in re.finditer(r'options=([0-9-]+)(?!:)',u or ''): ev.add(m.group(1).split('-')[0])
    for m in re.finditer(r'options=[0-9]+:([0-9]+)',u or ''): ev.add(m.group(1))
    for m in re.finditer(r'selectionId=(\d+)',u or ''): sel.add(m.group(1))
    # chaos Sep 26: market_selection_id is a UUID - event-unique, one shared UUID is sufficient reject evidence
    for m in re.finditer(r'market_selection_id(?:%5B0%5D|\[0\])=([0-9a-f-]+)',u or ''): ev.add(m.group(1))
    return ev,sel
def _stale_carryover(book_name, link, game):
    # Sep 26 chaos-hardened J-101 defense: reject when an event-scoped id (or 2+ ids) already
    # shipped for a DIFFERENT event (commence delta > 3h; legacy date-prefix entries fall back
    # to date compare). Missing game commence on a screened link = suppress loudly, never bypass.
    if not link or not game: return False
    gc=(game.get('commence','') or '')
    if not gc:
        print(f"STALE SCREEN SUPPRESS: {game.get('away')} @ {game.get('home')} {book_name} - no commence to verify against: {link[:90]}", file=sys.stderr)
        return True
    ev,sel=_link_ids(link)
    if not ev and not sel: return False
    import datetime as _dtc
    try: gct=_dtc.datetime.fromisoformat(gc.replace('Z','+00:00'))
    except Exception: gct=None
    bn=_canon_book(book_name)
    for k,bm in SHIPPED.items():
        parts=k.split('|')
        if len(parts)<3:
            print(f"LEDGER WARNING: malformed shipped_books key {k!r}", file=sys.stderr)
            continue
        kd=parts[2]
        for bn2,be in (bm or {}).items():
            if _canon_book(bn2)!=bn: continue
            ev2,sel2=_link_ids((be or {}).get('link',''))
            shared_ev=ev & ev2
            shared_n=len(shared_ev)+len(sel & sel2)
            if not shared_ev and shared_n<2: continue
            lc=(be or {}).get('commence','')
            same=True
            if lc and gct:
                try:
                    _lt=_dtc.datetime.fromisoformat(lc.replace('Z','+00:00'))
                    if _lt.tzinfo is None: _lt=_lt.replace(tzinfo=_dtc.timezone.utc)  # N1: naive ledger commence = UTC, never degrade to date equality
                    same=abs((_lt-gct).total_seconds())<=3*3600
                except Exception: same=(kd==gc[:10])
            else:
                same=(kd==gc[:10])
            if not same:
                print(f"STALE CARRYOVER REJECTED: {game.get('away')} @ {game.get('home')} {book_name} link reuses a {kd} event id: {link[:90]}", file=sys.stderr)
                return True
    return False
def sel_books(cands, game):
    # J-090 doubleheader fix (user, Sep 25 9:50 AM): match book data to the exact game
    # instance (commence), never the matchup alone. Same-team doubleheader with a
    # missing/unmatched commence -> suppress book links and warn loudly; never link
    # the wrong game.
    if not cands: return {}
    if len(cands)==1:
        _b=cands[0][1]
        # Sep 26: single-candidate slates get the carryover screen too (commence match alone
        # proved insufficient - a fresh-commence slate carried Friday's selection IDs).
        if isinstance(_b,dict):
            for _bn,_bd in list(_b.items()):
                if not isinstance(_bd,dict): continue
                if _bn=='state_templates':
                    for _sb,_srec in list(_bd.items()):
                        if not isinstance(_srec,dict): continue
                        for _f in ('event','away_link','home_link'):
                            if _srec.get(_f) and _stale_carryover({'betmgm':'BetMGM','betrivers':'BetRivers'}.get(_sb,_sb),_srec[_f],game):
                                _srec[_f]=None
                    continue
                _name={'draftkings':'DraftKings','fanduel':'FanDuel','espnbet':'theScore','hardrockbet':'Hard Rock','betmgm':'BetMGM','betrivers':'BetRivers'}.get(_bn,_bn)
                for _f in ('event','away_link','home_link'):
                    if _bd.get(_f) and _stale_carryover(_name, _bd[_f], game):
                        _bd[_f]=None
        return _b
    com=(game or {}).get('commence')
    for c,b in cands:
        if com and c and c[:16]==com[:16]:
            if isinstance(b,dict):
                for _bn,_bd in list(b.items()):
                    if not isinstance(_bd,dict): continue
                    _name={'draftkings':'DraftKings','fanduel':'FanDuel','espnbet':'theScore','hardrockbet':'Hard Rock','betmgm':'BetMGM','betrivers':'BetRivers'}.get(_bn,_bn)
                    for _f in ('event','away_link','home_link'):
                        if _bd.get(_f) and _stale_carryover(_name,_bd[_f],game): _bd[_f]=None
            return b
    print(f"DOUBLEHEADER WARNING: {game.get('away')} @ {game.get('home')} has {len(cands)} market entries, no commence match ({com!r}); book chips suppressed", file=sys.stderr)
    return {}

_LINKCACHE={}
try: RETIRED=json.load(open('retired_links.json'))
except Exception: RETIRED={}
def _link_alive(url):
    # J-110 (Sep 26): pre-publish tap pass - only a clear 404 kills a link; bot-blocks (403/429)
    # and network errors keep the chip (never drop on ambiguous evidence). Bot-blocked hosts
    # (DK Predictions 403s datacenter IPs) can't be tap-checked from the build host: a verified
    # 404 from a real-browser tap pass lands in retired_links.json and retires the link here.
    if not url or '{state}' in url: return True
    if url in RETIRED: return False
    if url in _LINKCACHE: return _LINKCACHE[url]
    ok=True
    try:
        import urllib.request
        if 'polymarket.us' in url or 'polymarket.com' in url:
            # 9/27 swamp catch: polymarket.us soft-404s - HTTP 200 with OG title "Page not found".
            # Status alone proves nothing on this host; verify page content.
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(req,timeout=10) as r: body=r.read(1200000).decode('utf-8','ignore')  # soft-404 marker sits ~466KB in - past any small cap
            import re as _re2
            _og=_re2.search(r'og:title[^>]*content="([^"]*)"',body)
            # .us soft-404: og:title "Page not found | Polymarket". Good .com pages carry the raw
            # string inside the JS bundle, so ONLY the OG title is evidence (9/27 .com restore).
            ok=(_og is not None and 'Page not found' not in _og.group(1))
        else:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'},method='HEAD')
            with urllib.request.urlopen(req,timeout=8) as r: ok=(r.status!=404)
    except Exception as e:
        if '404' in str(e): ok=False
    _LINKCACHE[url]=ok
    return ok

_KALEVT={}
def kal_market(tick, team_display):
    # Returns (market_suffix, cents) for the picked team's market under the event.
    # Sep 26 gate catch: data-kalside must carry the exact market-ticker suffix (TOR/SEA/HOU/PSU) -
    # a display name ("Penn St.") builds a not_found endpoint and the live tick dies silently.
    if not tick: return ('',None)
    if tick not in _KALEVT:
        try:
            import urllib.request
            req=urllib.request.Request(f'https://api.elections.kalshi.com/trade-api/v2/markets?event_ticker={tick}&limit=100',headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(req,timeout=8) as r: _KALEVT[tick]=json.load(r).get('markets',[])
        except Exception: _KALEVT[tick]=[]
    td=(team_display or '').lower().replace('.','').strip()
    for m in _KALEVT[tick]:
        mt=(m.get('ticker') or '')
        sfx=mt.rsplit('-',1)[-1]
        title=((m.get('title') or '')+' '+(m.get('subtitle') or '')).lower().replace('.','')
        if td and (td in title or td.replace(' ','')==sfx.lower()):
            try:
                d=float(m.get('yes_ask_dollars') or 0)
            except Exception: d=0
            return (sfx, round(d*100) if 0<d<=1 else None)
    return ('',None)

def chips(p):
    star='\u2605 '
    _pr=[]
    _uw=_is_underway(p.get('game') or {})
    _mkt='spread' if p.get('market')=='spread' else 'ml'
    _dm=f' data-market="{_mkt}"'  # sentinel Sep 26: the line-shop market guard reads this
    out=[]
    _SIDE=p.get('side','away')  # loop-scoped constant: set once, never rebound - a per-book branch mutating the pick side poisoned every later book's lookup (Sep 26: Kalshi rebound it, killing MGM/TSB chips for picks without ledger carryover)
    kw=p['name'].split()[0]
    _g=p.get('game') or {}
    _cm=_g.get('commence','')
    _eid=str(_g.get('eid') or '')
    _sk=f"{_g.get('away')}|{_g.get('home')}|{(_cm or '')[:10]}" if _g else ''
    _ph='last_pre_game' if _uw else 'pre_game'
    inst=game_instance(p.get('game'))
    inst=f' {inst}' if inst else ''
    for name,short in BOOKS:
        link=None; ml=None
        pr=sel_books(pre.get((p['game']['away'],p['game']['home'])), p.get('game')) if p.get('game') else None
        if p.get('market')=='spread':
            pr=(sel_books(pre_sp.get((p['game']['away'],p['game']['home'])), p.get('game')) or {}).get('books') if p.get('game') else None
        PKMAP={'FanDuel':'fanduel','DraftKings':'draftkings','theScore':'espnbet','Hard Rock':'hardrockbet'}  # U-GEO-003: feed still ships theScore lines under the legacy 'espnbet' key - ingested ONCE into the canonical TSB arm (never the ESPN identity)
        if pr and name in PKMAP:
            pk=PKMAP[name]
            if p.get('market')=='spread':
                e=(pr.get(pk) or {}).get(_SIDE) or {}
                if e.get('link'): link=e['link']
                if e.get('price') is not None: ml=e['price']
            else:
                pl=(pr.get(pk) or {}).get(f"{_SIDE}_link")
                if pl: link=pl
                if p.get('event_mode'):
                    ev=(pr.get(pk) or {}).get('event')
                    if ev: link=ev
                pm=(pr.get(pk) or {}).get(f"{_SIDE}_ml")
                if pm is not None: ml=pm
        if name in ('BetMGM','BetRivers'):
            if p.get('market')=='spread':
                st_=((sel_books(pre_sp.get((p['game']['away'],p['game']['home'])), p.get('game')) or {}).get('books') or {}).get('state_templates',{}) if p.get('game') else {}
                e=(st_.get('betmgm' if name=='BetMGM' else 'betrivers') or {}).get(_SIDE) or {}
                if e.get('link'): link=e['link']
                if e.get('price') is not None: ml=e['price']
            else:
                stt=((sel_books(pre.get((p['game']['away'],p['game']['home'])), p.get('game')) or {}).get('state_templates',{})) if p.get('game') else {}
                e=stt.get('betmgm' if name=='BetMGM' else 'betrivers') or {}
                if name=='BetMGM' and e.get(f"{_SIDE}_link"):
                    link=e[f"{_SIDE}_link"]; ml=e.get(f"{_SIDE}_ml")
                if name=='BetRivers' and e.get('event'):
                    link=e['event']; ml=e.get(f"{_SIDE}_ml")
        if name=='Kalshi' and p.get('kalshi'):
            link=p['kalshi']['url']
            tick=p['kalshi']['url'].rstrip('/').split('/')[-1].upper()
            _kside=(p.get('kalshi') or {}).get('team','')
            _sfx,_kc=kal_market(tick,_kside)
            _gate=(p.get('kalshi') or {}).get('gate_cents')
            if _gate is not None and _kc is not None and _kc>_gate:
                # ship condition (main, Sep 26 7:17 AM): pick ships only at gate_cents-or-better executable ask.
                # Display-only rebuilds (no pick-content change) skip it - the card shipped at its condition already.
                if _DISPLAY_ONLY:
                    print(f"DISPLAY-ONLY: {p.get('name')} Kalshi ask {_kc}c above ship ceiling {_gate}c - condition skipped, pick content unchanged", file=sys.stderr)
                elif p.get('result') or p.get('_final'):
                    # settled pick: the ship condition was evaluated at entry - a post-final 100c ask is
                    # settlement, not a price. Settled markets keep their entry price (J-099); never gate on it.
                    print(f"SETTLED: {p.get('name')} graded - Kalshi ship ceiling skipped (entry condition already met)", file=sys.stderr)
                elif _uw:
                    # in play (root fix, Sep 26 record-ship block): the ship condition was evaluated at entry;
                    # a live in-play ask is not an entry price. Per-leg freeze-at-kickoff doctrine: the chip
                    # uses the pinned pre-game snapshot below; the ceiling must never kill an in-play build.
                    print(f"IN-PLAY: {p.get('name')} Kalshi ask {_kc}c above ship ceiling {_gate}c - ceiling skipped (game underway; chip renders frozen pre-game snapshot)", file=sys.stderr)
                else:
                    print(f"BUILD FAILED: {p.get('name')} Kalshi ask {_kc}c exceeds ship-condition ceiling {_gate}c", file=sys.stderr)
                    sys.exit(3)
            if _uw:
                # in play (never-blank + phase provenance, Sep 26): freeze the last PRE-GAME snapshot -
                # SHIPPED carryover first, manifest ship cents as fallback; never a live in-play ask
                # (an in-play 99c beside pre-game closers poisons every same-phase comparison).
                _frozen=((SHIPPED.get(_sk) or {}).get('Kalshi') or {}).get('cents') or (p.get('kalshi') or {}).get('cents')
                if _frozen and _frozen!=_kc:
                    print(f"IN-PLAY FREEZE: {p.get('name')} Kalshi live ask {_kc} - frozen to pre-game snapshot {_frozen}c", file=sys.stderr)
                    _kc=_frozen
                if _frozen:
                    # kickoff lock (tester caveat, build 1790470472): persist the pin so the snapshot
                    # survives in the ledger - the original publish predates the ledger's PM-arm lines.
                    NEWSHIPPED.setdefault(_sk,{})['Kalshi']={'link':link,'cents':_frozen,'commence':_cm}
            else:
                NEWSHIPPED.setdefault(_sk,{})['Kalshi']={'link':link,'cents':_kc,'commence':_cm}
            if not _sfx or _kc is None:
                # e4f128e absorbed (run 36262260747): Kalshi delists/halts in-play markets - an
                # unresolved market must not kill underway/display-only rebuilds. Degrade to the
                # pinned snapshot (SHIPPED ledger first, manifest ship cents as fallback). Pre-game
                # NEW content still hard-fails (ship condition must re-verify a real market).
                _pin=((SHIPPED.get(_sk) or {}).get('Kalshi') or {}).get('cents') or (p.get('kalshi') or {}).get('cents')
                if (_DISPLAY_ONLY or _uw) and _pin is not None:
                    print(f"IN-PLAY DEGRADE: {p.get('name')} Kalshi market unresolved under {tick} - pinned snapshot {_pin}c (market closed/halted in-play)", file=sys.stderr)
                    _urf("EXECUTE","C=3 F=3 R=1 U=1 V=2 CE=1 T=high","in-play degrade to pinned snapshot",f"{p.get('name')} under {tick}: Kalshi delisted/halted in-play, pinned {_pin}c is the last verified pre-game quote; a stale-labeled-honest chip beats a killed build")
                    _kc=_pin
                elif _uw:
                    # regression gate Sep 26 (11:21 AM incident, 3h outage): an in-play delisting with NO
                    # pinned snapshot must not kill the build either - degrade to an honest unpriced chip
                    # (st:'unknown', no cents). Pre-game NEW content still hard-fails below.
                    print(f"IN-PLAY DEGRADE: {p.get('name')} Kalshi market unresolved under {tick} and no pinned snapshot - chip ships unpriced (honest unknown), build continues", file=sys.stderr)
                    _urf("EXECUTE","C=3 F=3 R=1 U=2 V=2 CE=1 T=high","in-play degrade to honest unpriced",f"{p.get('name')} under {tick}: no pinned snapshot exists; UNKNOWN is not a failure (outcome_truth three-way verdict) - ship st:unknown, never invent a price")
                    _kc=None
                else:
                    # Sep 26 hunter ruling: a stale price posing as fresh is worse than no build.
                    print(f"BUILD FAILED: Kalshi market unresolved for {p.get('name')} team {_kside!r} under {tick}", file=sys.stderr)
                    _urf("ABORT","C=3 F=0 R=3 U=2 V=3 CE=0 T=high","pre-game NEW content hard-fail",f"{p.get('name')} under {tick}: no live market, no pin, not underway - shipping would pose an unverified price as fresh (hunter ruling Sep 26)")
                    sys.exit(3)
            # LOCKED-PRICE BAKE (Sep 27 7:47 tester NO-GO, main directive): the picked chip always
            # bakes the LOCKED card price (manifest kalshi.cents, "Kalshi ask at lock"), never the
            # live ask pulled at build time. Live ask still feeds the ship-condition ceiling above;
            # the baked snapshot is the lock. Client-side ticking still refreshes the page live.
            _lck=(p.get('kalshi') or {}).get('cents')
            if _lck is not None and _kc is not None and _kc!=_lck:
                print(f"LOCKED BAKE: {p.get('name')} chip pinned to locked {_lck}c (live ask {_kc}c at build)", file=sys.stderr)
                _kc=_lck
            label=(f"KAL {c2ml(_kc)}" if _kc else "KAL")+inst  # user Sep 26 12:58 PM: ALL chips American, PM arms included (supersedes U-DISP-001 c1)  # in play _kc is the frozen last-known price - never blank (inspector Sep 26)
            best=(p.get('best_book')=='Kalshi')
            _kside_html=html.escape(_sfx)  # Kalshi-scoped: never rebind the pick side
            _pr.append((len(out), c2ml_int(_kc) if _kc else None))
            _kcattr=f' data-cents="{_kc}"' if _kc else ''
            _kcattr+=_mkrec('Kalshi',tick,tick+'-'+_kside_html,_kside_html,cents=_kc,link=link,ph=_ph,ts=(((SHIPPED.get(_sk) or {}).get('Kalshi') or {}).get('ts') or '') if _uw else '',st=('ok' if _kc else 'unknown'))
            out.append(f'<a class="chip%%BEST%%"{bkstyle(short)} href="{html.escape(link)}" data-book="KAL" data-kalticker="{tick}" data-kalside="{_kside_html}"{_dm}{_kcattr} target="_blank" rel="noreferrer">%%STAR%%{bkimg(short)}{label}</a>')
            continue
        if name=='Polymarket':
            if not p.get('polymarket'): continue
            slug=poly_event_slug(p['polymarket']['url']) or ''
            _us=(p.get('polymarket_us') or {}).get('url') or ''
            if _us and slug and poly_event_slug(_us)!=slug:
                # Sep 26 relocation-alias trap (hou-ath vs hou-oak): the .com slug is the
                # gamma-verifiable source of truth; a disagreeing .us slug is never bound.
                print(f"POLY SLUG WARNING: {p.get('name')} .us slug {poly_event_slug(_us)} != verified {slug} - using verified", file=sys.stderr)
            web=_poly_us_url(slug) if slug else (_us or ''); app=web
            sub=poly_sub(p['polymarket']['url']) or ''
            # price basis: gamma outcomePrices = mid/last, NOT the ask (auditor-confirmed Sep 26);
            # .us search snapshots are stale/unreliable - gamma is the build-time source of truth.
            if _uw:
                # in play: freeze the verified PRE-GAME snapshot (SHIPPED carryover, then manifest
                # polycents) - never a live in-play gamma quote in the frozen comparison set.
                cents=((SHIPPED.get(_sk) or {}).get('Polymarket') or {}).get('cents') or p.get('polycents')
                if cents and _POLY_US_PRICED: NEWSHIPPED.setdefault(_sk,{})['Polymarket']={'link':web,'cents':cents,'commence':_cm}
            else:
                cents=poly_price(p['polymarket']['url'],kw) or p.get('polycents')
                if cents and _POLY_US_PRICED: NEWSHIPPED.setdefault(_sk,{})['Polymarket']={'link':web,'cents':cents,'commence':_cm}
            if not _POLY_US_PRICED: cents=None  # P1: no .com-gamma price on a .us link
            _usv=(p.get('polymarket_us') or {})
            if _usv.get('verified'):
                if _usv.get('url'): web=_usv['url']; app=web  # 9/27 8:34 feed: hub-verified .us URL verbatim
                if _usv.get('cents'):
                    cents=_usv['cents']  # .us pick-side mid - the ONLY price a .us chip may wear
                    NEWSHIPPED.setdefault(_sk,{})['Polymarket']={'link':web,'cents':cents,'commence':_cm}
            # never-blank (inspector Sep 26): entry odds are the last-resort fallback on the
            # picked book. Never a bare 'POLY' when any price was ever known.
            _pcattr=f' data-cents="{round(cents)}"' if cents else ''
            _pcattr+=_mkrec('Polymarket',slug,sub or slug,_SIDE,cents=cents,link=web,ph=_ph,ts=(((SHIPPED.get(_sk) or {}).get('Polymarket') or {}).get('ts') or '') if _uw else '',st=('ok' if cents else 'unknown'))
            label=(('POLY '+str(c2ml(cents))) if cents else 'POLY')+inst  # priced only from verified .us cents (never .com)
            best=(p.get('best_book')=='Polymarket') and bool(cents)  # an unpriced POLY row never takes the star
            _pr.append((len(out), (c2ml_int(cents) if cents else None)))
            _polyattrs=(f' data-polyslug="{html.escape(slug)}" data-polysub="{html.escape(sub)}" data-polykw="{html.escape(kw)}"') if _POLY_US_PRICED else ''  # P1: no slug attrs -> client tick cannot re-price from .com gamma
            out.append(f'<a class="chip%%BEST%%"{bkstyle("POLY")} href="{html.escape(web)}" data-book="POLY" data-sb="{html.escape(web)}" data-app="{html.escape(app)}"{_dm}{_polyattrs}{_pcattr} onclick="return rpRoute(event,this)" target="_blank" rel="noreferrer">%%STAR%%{bkimg("POLY")}{label}</a>')
            continue
        if link and p.get('game'):
            _sk=f"{p['game'].get('away')}|{p['game'].get('home')}|{(p['game'].get('commence') or '')[:10]}"
            NEWSHIPPED.setdefault(_sk,{})[name]={'link':link,'ml':ml,'commence':p['game'].get('commence','')}
        if not link and p.get('game'):
            _se=SHIPPED.get(f"{p['game'].get('away')}|{p['game'].get('home')}|{(p['game'].get('commence') or '')[:10]}",{}).get(name)
            if _se and _stale_carryover(name,_se.get('link'),p.get('game')): _se=None
            if _se: link=_se.get('link'); ml=_se.get('ml')
        if not link:
            if _uw:
                # in-play (inspector Sep 26): books pull markets at commence; freeze the last-known
                # price when we have one, else unpriced - the chip never drops, never goes blank.
                _lbl=(f"{short} {ml:+d}" if ml is not None else short+' \u2014')+inst  # watchdog Sep 26: explicit unpriced state - never a bare chip that reads broken
                _pr.append((len(out), ml))
                _mr=_mkrec(name,_eid,_mkt,_SIDE,ml=ml,link='',ph=_ph,lv='none',st=('ok' if ml is not None else 'unknown'))
                _upcls='' if ml is not None else ' rpunpriced'
                out.append(f'<span class="chip%%BEST%% rpnontap{_upcls}"{bkstyle(short)} data-book="{short}"{_dm}{_mr}>{bkimg(short)}{html.escape(_lbl)}</span>')
            continue  # no game-level link -> drop chip (pre-game only)
        best=(p.get('best_book')==name)
        # in-play (inspector ruling Sep 26): freeze each book's last-known price - ml from the live
        # feed or the SHIPPED carryover above; the chip never goes blank and the link still carries
        # to the live market. No price ever known -> unpriced inert chip, never a dropped chip.
        label=(f"{short} {ml:+d}" if ml is not None else short+' \u2014')+inst  # watchdog Sep 26: explicit unpriced state at core - every book, every surface
        # star renders left of logo at append time
        if name in ('FanDuel','DraftKings'):
            # exact PM market url or fail-closed (complaint-lens via main 9/26): a generic Predicts/Predictions
            # homepage never substantiates a displayed selection, on any surface.
            pm=((p.get('fdp') or {}).get('url')) if name=='FanDuel' else ((p.get('dkp') or {}).get('url'))
            pmapp=('https://predicts.fanduel.com/' if pm else '') if name=='FanDuel' else ''
            nopm='' if pm else ' data-nopm="1"'
            _pmattr=(' data-pm="'+html.escape(pm)+'"') if pm else ''
            _tm='{state}' in link
            _tmattr=' data-template="1"' if _tm else ''
            _href='https://www.'+BKDOM[short] if _tm else link
            _pr.append((len(out), ml))
            _mr=_mkrec(name,_eid,_mkt,_SIDE,ml=ml,link=link,ph=_ph,st=('ok' if ml is not None else 'unknown'))
            out.append(f'<a class="chip%%BEST%%"{bkstyle(short)} href="{html.escape(_href)}" data-book="{short}"{_dm}{_mr} data-sb="{html.escape(link)}"{_pmattr} data-pmapp="{html.escape(pmapp)}"{nopm}{_tmattr} onclick="return rpRoute(event,this)" target="_blank" rel="noreferrer">%%STAR%%{bkimg(short)}{html.escape(label)}</a>')
        elif '{state}' in link:
            # Sep 26 inspector ruling (J-112 class extended to singles): a priced chip on a generic
            # destination violates game-level-or-no-chip. Static HTML ships a priced NON-TAPPABLE span
            # carrying the template in data-sbt; rpTapify (in rpFilter) swaps it to a deep-link anchor
            # once the reader's state is known and the book is live there, so the tap always lands on the exact game at their book.
            _pr.append((len(out), ml))
            _mr=_mkrec(name,_eid,_mkt,_SIDE,ml=ml,link=link,ph=_ph,st=('ok' if ml is not None else 'unknown'))  # tester gate 9/26: EVERY priced chip carries a record - the range set is identical static vs JS
            out.append(f'<span class="chip%%BEST%% rpnontap rppending"{bkstyle(short)} data-book="{short}"{_dm}{_mr} data-sbt="{html.escape(link)}" data-template="1">%%STAR%%{bkimg(short)}{html.escape(label)}</span>')
        else:
            _pr.append((len(out), ml))
            _mr=_mkrec(name,_eid,_mkt,_SIDE,ml=ml,link=link,ph=_ph,st=('ok' if ml is not None else 'unknown'))  # tester gate 9/26: EVERY priced chip carries a record
            out.append(f'<a class="chip%%BEST%%"{bkstyle(short)} href="{html.escape(link)}" data-book="{short}"{_dm}{_mr} data-sb="{html.escape(link)}" onclick="return rpRoute(event,this)" target="_blank" rel="noreferrer">%%STAR%%{bkimg(short)}{html.escape(label)}</a>')
    # U-GEO-002 platform-arm chips (PS6: arms are distinct platforms) - DK Predictions / FD Predicts.
    # Priced only from a verified market record (fail closed); otherwise an unpriced platform chip
    # on a verified destination (predictions.draftkings.com / fanduel.com/predicts - verified Sep 26).
    for _arm,_albl,_aurl,_pmkey in (('DKP','DK Predictions','https://predictions.draftkings.com/','dkp'),('FDP','FD Predicts','https://www.fanduel.com/predicts','fdp')):
        if _arm=='FDP': continue  # his call Sep 26 4:00 PM: FD Predicts chip hidden on ALL cards until the state-gated FD pipeline ships - restored by the queued DK+FD pipeline work
        _pm=(p.get(_pmkey) or {})
        _pmu=_pm.get('url');_pmc=_pm.get('team_cents') if _pm.get('team_cents') is not None else _pm.get('cents')  # d03ba56 contract: team_cents is the pick-side price (harvest snapshot); 'cents' = legacy key
        if _pmu and _pmc is not None:
            _pr.append((len(out),rp_c2a(_pmc) if 'rp_c2a' in dir() else None))
            _mr=_mkrec(_arm,_eid,_mkt,_SIDE,ml=None,cents=_pmc,link=_pmu,ph=_ph,st=('ok' if _pmc is not None else 'unknown'))
            out.append(f'<a class="chip%%BEST%%"{bkstyle(_arm)} href="{html.escape(_pmu)}" data-book="{_arm}"{_dm}{_mr} data-sb="{html.escape(_pmu)}" data-cents="{_pmc}" onclick="return rpRoute(event,this)" target="_blank" rel="noreferrer">{bkimg(_arm)}{html.escape(_albl+" "+c2ml(_pmc))}</a>')  # parity fix Sep 26: priced prediction-arm chips carry market identity like every other priced chip - the line-shop guard was silently excluding them (MSST card lost its range line in KAL+DKP-only states)
        # unpriced prediction-arm chips are never emitted: a chip requires a verified priced record (url + cents), fail closed
    # build-time star = same max-American rule as client rpBestStar: the star never sits on
    # anything but the best displayed price, and never in play.
    _win=None
    _cand=[(i,v) for i,v in _pr if v is not None and i<len(out)]
    if _cand: _win=max(_cand,key=lambda t:t[1])[0]  # star marks the best DISPLAYED price - frozen prices in play included (inspector Sep 26)
    out=[o.replace('%%BEST%%',' best' if i==_win else '').replace('%%STAR%%',star if i==_win else '') for i,o in enumerate(out)]
    # J-110 (Sep 26): settled-link retirement + tap pass. Feed-verified settled + retired
    # destination -> chip freezes non-tappable with brand fill + entry price. Dead link on a
    # live/upcoming event -> chip dropped until a working exact-market link exists.
    _kept=[]
    for _o in out:
        # destinations a tap can actually reach: data-pm (FD/DK outside sportsbook states),
        # then data-sb/href. {state} templates resolve client-side - skipped here.
        _pm=re.search(r'data-pm="([^"]+)"',_o)
        _nopm=' data-nopm="1"' in _o
        _cands=[]
        if _pm and not _nopm: _cands.append(html.unescape(_pm.group(1)))
        for _m in (re.search(r'data-sb="([^"]+)"',_o),re.search(r'href="([^"]+)"',_o)):
            if _m:
                _u2=html.unescape(_m.group(1))
                if '{state}' not in _u2 and _u2 not in _cands: _cands.append(_u2)
        _dead=[u for u in _cands if not _link_alive(u)]
        if not _dead:
            _kept.append(_o); continue
        if p.get('_final'):
            # settled + retired destination: freeze the chip non-tappable, brand fill + entry price stay
            _o=re.sub(r'<a class="chip','<span class="chip',_o)
            _o=re.sub(r' href="[^"]*"','',_o)
            _o=re.sub(r' onclick="[^"]*"','',_o)
            _o=re.sub(r' target="_blank" rel="noreferrer"','',_o)
            # frozen chips must leave every live-tick selection set (sentinel, Sep 26)
            _o=re.sub(r' data-(kalticker|kalside|polyslug|polysub|polykw|pm|pmapp|sb|app|book)="[^"]*"','',_o)
            _o=_o.replace('</a>','</span>')
            print(f"LINK FROZEN: {p.get('name')} settled chip, retired destination: {_dead[0]}", file=sys.stderr)
        else:
            if _pm and html.unescape(_pm.group(1)) in _dead and len(_dead)<len(_cands):
                # live/upcoming with a surviving sb destination: retire only the dead pm path
                print(f"LINK RETIRE: {p.get('name')} dead predictions link, sb link kept: {_dead[0]}", file=sys.stderr)
                _o=re.sub(r' data-pm="[^"]*"','',_o)
                _o=re.sub(r' data-pmapp="[^"]*"','',_o)
                _o=_o.replace('<a class="chip','<a data-nopm="1" class="chip',1)
            else:
                print(f"LINK DROP: {p.get('name')} dead link on live/upcoming event: {_dead[0]}", file=sys.stderr)
                continue
        _kept.append(_o)
    out=_kept
    global LAST_PRICES
    LAST_PRICES=[]
    for _o in out:
        _txt=re.sub(r'<[^>]+>','',_o)
        _nums=re.findall(r'[+-]\d{2,5}',_txt)
        if _nums:
            _v=int(_nums[0])
            if abs(_v)<=1500: LAST_PRICES.append(_v)
    return ''.join(out)


def lineshop_html(prs, underway=False):
    prs=[v for v in prs if v is not None]
    if len(prs)<2: return ''
    def ip(a): return 100.0/(a+100) if a>0 else (-a)/((-a)+100.0)
    best=max(prs); worst=min(prs)
    edge=(ip(worst)-ip(best))*100
    if edge<0.05: return ''
    if underway:  # frozen pre-game closers: historical reference, never obtainable-now language (swamp 9/26)
        return '<div class="rplineshop" style="font-size:11px;color:#8a8f98;margin:3px 0 0">pre-game range: %+d to %+d</div>'%(worst,best)
    return '<div class="rplineshop" style="font-size:11px;color:#8a8f98;margin:3px 0 0">line shop: %+d to %+d &middot; %.1f%% edge at the best price</div>'%(worst,best,edge)
_chips_fn=chips
# Chronological pick order within each league (user, Sep 25 4:48 PM); league groups keep first-appearance order. Finished-first reorder stays client-side (rpFinalsTop).
_lg_seen={}
for _p in man['picks']:
    _lgk=_p.get('espn_league','')
    if _lgk not in _lg_seen: _lg_seen[_lgk]=len(_lg_seen)
man['picks'].sort(key=lambda _p:(_lg_seen.get(_p.get('espn_league',''),99), (_p.get('game') or {}).get('commence','') or '9999'))
for _i,_p in enumerate(man['picks'],1): _p['num']=_i  # card display order IS the pick number (matches game-N.html + GAME header)

# Class fix (9/25 Astros home-row lapse): bind every MLB row to its immutable gamePk, resolved
# ONCE server-side, so the client never depends on a fragile date+name schedule lookup.
GPK={}
try:
    import urllib.request as _u2
    from zoneinfo import ZoneInfo as _ZI
    import datetime as _dt2
    _dates=set()
    for _p2 in man['picks']:
        if (_p2.get('espn_league') or '')!='baseball/mlb': continue
        _c=((_p2.get('game') or {}).get('commence','') or '')
        try: _dates.add(_dt2.datetime.fromisoformat(_c.replace('Z','+00:00')).astimezone(_ZI('America/Los_Angeles')).date().isoformat())
        except Exception: pass
    for _ds in sorted(_dates):
        try:
            _req=_u2.Request('https://statsapi.mlb.com/api/v1/schedule?sportId=1&date='+_ds+'&hydrate=team',headers={'User-Agent':'python-urllib/3.10'})
            _dd=json.load(_u2.urlopen(_req,timeout=12))
            for _x in _dd.get('dates',[]):
                for _gm in _x.get('games',[]):
                    _t=_gm.get('teams',{})
                    GPK.setdefault((_t['away']['team']['name'],_t['home']['team']['name']),[]).append((str(_gm['gamePk']),_t['away']['team'].get('abbreviation',''),_t['home']['team'].get('abbreviation',''),_gm.get('gameDate','')))
        except Exception: pass
except Exception: pass
# doubleheader-safe: disambiguate same-matchup games by closest start time to the card's commence
def _gpk_for(away,home,commence=''):
    cands=GPK.get((away,home)) or []
    if len(cands)<2: return (cands[0][:3] if cands else ('','',''))
    try:
        _ct=_dt2.datetime.fromisoformat((commence or '').replace('Z','+00:00'))
        def _dist(c):
            try: return abs((_dt2.datetime.fromisoformat(c[3].replace('Z','+00:00'))-_ct).total_seconds())
            except Exception: return 9e9
        return min(cands,key=_dist)[:3]
    except Exception: return cands[0][:3]
def _eid_resolve(man):
    # Sep 26 builder fix: every pick should carry its ESPN event id - MLB binds by gpk, other leagues
    # have no gpk, and an empty eid leaves the 60s odds tick on token+date fallback (J-108 class).
    cache={}
    try:
        _reg=json.load(open(os.path.join(os.path.dirname(__file__),'..','config_leagues.json')))['leagues']
    except Exception: _reg={}
    prms={}
    for v in _reg.values():
        if v.get('espn'): prms[v['espn']]=('&'+v['espn_params']) if v.get('espn_params') else ''
    for p in man.get('picks',[]):
        g=p.get('game') or {}
        if not p.get('espn_league') or not g.get('away') or not g.get('home'): continue
        lg=p['espn_league']; d=_pt_date(g.get('commence',''))
        if not d: continue
        key=(lg,d)
        if key not in cache:
            try:
                cache[key]=_espn_get('https://site.api.espn.com/apis/site/v2/sports/%s/scoreboard?dates=%s%s'%(lg,d.replace('-',''),prms.get(lg,''))).get('events',[])
            except Exception: cache[key]=[]
        at=g['away'].lower(); ht=g['home'].lower()
        best=None; bestd=9e18
        for ev in cache[key]:
            comps=[]
            if ev.get('competitions'): comps.append(ev['competitions'][0])
            for gr in ev.get('groupings',[]): comps.extend(gr.get('competitions') or [])
            for c in comps:
                nm={((x.get('team') or {}).get('displayName','').lower()):x.get('homeAway') for x in c.get('competitors',[])}
                am=[n for n in nm if at in n or n in at]; hm=[n for n in nm if ht in n or n in ht]
                if not am or not hm: continue
                if nm[am[0]]!='away' or nm[hm[0]]!='home': continue
                try:
                    d0=_dt2.datetime.fromisoformat((g.get('commence','') or '').replace('Z','+00:00'))
                    d1=_dt2.datetime.fromisoformat((ev.get('date','') or '').replace('Z','+00:00'))
                    if d0.tzinfo is None: d0=d0.replace(tzinfo=_dt2.timezone.utc)
                    if d1.tzinfo is None: d1=d1.replace(tzinfo=_dt2.timezone.utc)
                    dd=abs((d1-d0).total_seconds())
                except Exception: dd=None  # sentinel Sep 26: a failed compare must NEVER win the argmin
                if dd is None: continue
                if dd<bestd: best=ev; bestd=dd
        if best is not None and best.get('id') and bestd<=30*3600:
            if g.get('eid') and str(g['eid'])!=str(best['id']):
                # Sep 26: never trust a manifest eid the feed contradicts - teams+date win
                print(f"EID OVERRIDE: {p.get('name')} manifest eid {g['eid']} -> feed {best['id']}", file=sys.stderr)
            g['eid']=str(best['id'])
            comps=[]
            if best.get('competitions'): comps.append(best['competitions'][0])
            for gr in best.get('groupings',[]): comps.extend(gr.get('competitions') or [])
            for c in comps:
                _st=(c.get('status') or {}).get('type') or {}
                if _st.get('completed') or _st.get('state')=='post': p['_final']=True
        elif g.get('eid'):
            # sentinel Sep 26: an unverifiable eid is suppressed, never shipped on team-name faith -
            # the ESPN tick/link dies with it rather than pointing at an arbitrary same-team event
            print(f"EID SUPPRESSED: {p.get('name')} manifest eid {g['eid']} failed feed verification (best delta {bestd if best is not None else 'n/a'}) - tick/link suppressed", file=sys.stderr)
            g['eid']=''
_eid_resolve(man)
rows=[]
_row_lgs=[]
last_lg=None
SEEN=[]
for p in man['picks']:
    lg=p.get('espn_league','')
    if lg!=last_lg:
        lbl=LG_LABEL.get(lg) or (lg.split('/')[-1].replace('-',' ').title() if lg else 'Other')
        ball=LG_BALL.get(lg,'\U0001f3c5')
        rows.append(f'<div class="lghead"><span style="display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;margin-right:8px;font-size:17px">{ball}</span>{html.escape(lbl)}</div>')
        _row_lgs.append(lg)
        last_lg=lg
    ch=chips(p)
    for _mm in re.finditer(r'<a [^>]*data-book="([A-Z]+)"[^>]*>', ch):
        # Sep 26: guard the EFFECTIVE destination - templated chips carry a generic href and the
        # real {state} template in data-sb; comparing hrefs false-alarms on the shared base domain.
        _tag=_mm.group(0)
        if 'data-platform="1"' in _tag: continue  # platform-level arm destinations (DK Predictions/FD Predicts) are not game-scoped - the doubleheader guard protects market links only
        _m2=re.search(r'data-sb="([^"]+)"',_tag) or re.search(r'href="([^"]+)"',_tag)
        if not _m2: continue
        _pg=p.get('game') or {}
        SEEN.append((_mm.group(1), html.unescape(_m2.group(1)), (_pg.get('away',''),_pg.get('home',''),_pg.get('commence',''))))
    chips_html=f'<div class="chips">{ch}</div>' if ch else ''
    ls_html='<div class="rplineshop" style="display:none;font-size:11px;color:#8a8f98;margin:3px 0 0"></div>' if ch else ''  # parity sentinel Sep 26: no baked all-books range - client computes over the visible set only, same as game pages
    espn=html.escape(p.get('espn_league',''))
    mkt='spread' if p.get('market')=='spread' else 'ml'
    g=p.get('game') or {}
    _gk3=_gpk_for(g.get('away',''),g.get('home',''),g.get('commence',''))
    if g.get('gpk'): _gk3=(str(g['gpk']),_gk3[1],_gk3[2])
    _eid=str(g.get('eid') or '')
    _lga=p.get('espn_league','')
    _ma=_meta_for(_lga,g.get('away','')); _mh=_meta_for(_lga,g.get('home',''))
    def _avimg(mm,overlap=False):
        u=mm.get('logo','')
        if not u: return ''
        st='width:26px;height:26px;object-fit:contain'
        if overlap: st+=';margin-left:-8px'
        return '<img src="%s" alt="" style="%s" onerror="this.remove()">'%(html.escape(u),st)
    _av=_avimg(_ma)+_avimg(_mh,True)
    _avhtml='<span style="display:inline-flex;flex-shrink:0;align-items:center;margin-right:6px">'+_av+'</span>' if _av else ''
    rows.append(f'''<div class="pick" data-espn="{espn}" data-eid="{html.escape(_eid)}" data-gpk="{_gk3[0]}" data-aab="{_gk3[1]}" data-hab="{_gk3[2]}" data-room="g{p['num']}-{(_pt_date(g.get('commence','')) or 'card')}" data-commence="{html.escape(g.get('commence',''))}" data-away="{html.escape(g.get('away',''))}" data-home="{html.escape(g.get('home',''))}" data-side="{p.get('side','away')}" data-market="{mkt}" data-codds="{html.escape(p.get('odds',''))}" data-stake="{html.escape(re.sub(r'[^0-9.]','',p.get('units','')))}"{(' data-counted="1"' if p.get('result') in ('WIN','LOSS','PUSH') else '')}>
  <div class="pick-head"><a class="gamelink" href="game-{p['num']}.html">{_avhtml}<span class="num">{p['num']}.</span><span class="name">{html.escape(p['name'])}</span></a><span class="meta-grp"><a class="rpmetalink" href="game-{p['num']}.html"><span class="uo"><span class="units">{html.escape(p.get('units',''))}</span><span class="odds">{html.escape(p['odds'])}</span></span><span class="oddslock">{_stamp_html(p)}</span></a><a class="rpchatlink" href="game-{p['num']}.html#rpChatPanel" aria-label="live chat"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg><span data-cc></span></a></span></div><span class="ls" data-ls></span>
  <div class="rpstart" data-commence="{html.escape(g.get('commence',''))}">{_pt_time(g.get('commence',''))}</div>
  <div class="sub">{html.escape(p['sub'])}</div>
  {chips_html}
  {ls_html}
</div>''')
    _row_lgs.append(lg)

if not rows:
    # Empty-slate defense (Sep 26 chaos drill / app_spec Data rules): the page NEVER ships silently
    # empty. Degraded card: explicit state + yesterday's grades, locked layout otherwise intact.
    _y=html.escape(str(man.get('yesterday') or ''))
    rows.append('<div class="pick"><div class="pick-head"><span class="name">No picks today</span></div>'
                + (f'<div class="sub"><a class="yesrec" href="yesterday.html" style="color:inherit">Yesterday: {_y}</a></div>' if _y else '')
                + '</div>')
    _row_lgs.append('')
    print('EMPTY SLATE: degraded card shipped (no picks in manifest)', file=sys.stderr)

_seen={}
for _bk,_lnk,_gk in SEEN:
    _k=(_bk,_lnk)
    if _k in _seen and _seen[_k]!=_gk:
        print(f"DOUBLEHEADER REGRESSION: {_bk} link reused across different game instances: {_lnk[:120]}", file=sys.stderr)
        sys.exit(2)
    _seen[_k]=_gk

parlay_html=''

# futures book (futures.json) - compact home entry + NEW marker + futures page
FUT=[]
try:
    FUT=json.load(open('futures.json'))
    _led={}
    import os as _os
    _lp='/home/sandbox/rps_tmp/kb/ledger/picks.jsonl'
    if _os.path.exists(_lp):
        for _ln in open(_lp):
            try: _d=json.loads(_ln)
            except Exception: continue
            if str(_d.get('id','')).startswith('F-') and _d.get('team'): _led[_d['team']+'|'+_d['market'].lower().replace(' winner',' champion').replace('LXI champion','LXI Champion')]=_d
    for _f in FUT:
        for _k,_v in _led.items():
            if _v['team']==_f['team'] and (_f['market'].lower().startswith(_v['market'].split()[0].lower()) or _v['market'].split()[0].lower() in _f['market'].lower()):
                _f.setdefault('fair',_v.get('fair_price_est',''));_f.setdefault('prob',_v.get('est_prob',''));_f.setdefault('res',_v.get('resolution',''))
                break
except Exception:
    FUT=[]
# root fix (Sep 26 regression): fair/prob/res now ship INLINE in futures.json - read them off the row,
# ledger join above stays as enrichment only. Loud failure when any row still lacks them (never silent-empty again).
for _f in FUT:
    _f.setdefault('fair',_f.get('fair_price_est',''));_f.setdefault('prob',_f.get('est_prob',''));_f.setdefault('res',_f.get('resolution',''))
import sys as _sys
_missing=[_f.get('team','?') for _f in FUT if not _f.get('fair') or not _f.get('prob') or not _f.get('res')]
if _missing:
    print('FUTURES SHEET VALUES MISSING (fair/prob/res) for: '+', '.join(_missing)+' - futures.json must carry fair_price_est/est_prob/resolution inline (bde1792 contract)', file=_sys.stderr)
fut_ids=[f.get('id','') for f in FUT]
fut_entry=''
if FUT:
    fut_entry=('<div class="sect" style="margin-top:22px">Futures</div>'
      '<a href="futures.html?v={build_sha}" style="display:flex;align-items:center;justify-content:space-between;padding:11px 12px;border:1px solid rgba(127,127,127,.22);border-radius:12px;text-decoration:none;color:inherit">'
      '<span style="font-weight:600">Track every futures pick live<span id="rpFutNew" style="display:none;background:#e5484d;color:#fff;border-radius:8px;font-size:10px;padding:1px 6px;margin-left:8px;vertical-align:2px">NEW</span></span>'
      '<span style="color:#8a8f98;font-size:12px">'+str(len(FUT))+' live &rsaquo;</span></a>')
# guest NFL anytime-TD slate (contract slates/schema_v1.json) - home section hydrates from
# slates/nfl_latest.json; empty state until the first slate lands; stale slates (4d+) fall back to empty
nfl_entry=(
r'<div class="sect" style="margin-top:22px">Picks from Wooder Ice<span style="display:inline-block;background:#0b6e5f;color:#fff;border-radius:8px;font-size:10px;font-weight:700;letter-spacing:.06em;padding:1px 7px;margin-left:8px;vertical-align:2px">GUEST</span></div>'
r'<div style="border:1px dashed rgba(127,127,127,.35);border-radius:12px;padding:11px 12px">'
r'<div id="rpNflHead"></div>'
r'<div class="rpwhead">Anytime TD Scorers</div>'
r'<div style="font-size:12px;color:#8a8f98;margin:2px 0 8px">Separate from the RixPicks card and record. Picks only, no wagers placed.</div>'
r'<div id="rpNfl"><div style="color:#8a8f98;font-size:13px;padding:6px 0">Loading&hellip;</div></div>'
r'</div>'
r'<style>.rpnpick{padding:12px 0;border-top:1px solid #e4e2de}.rpwhead{font-size:20px;font-weight:800;letter-spacing:.05em;margin:0 0 2px}'
r'@media (prefers-color-scheme:dark){.rpnpick{border-top-color:#2a2a2e}}</style>'
r'<script>(function(){'
r'var box=document.getElementById("rpNfl");if(!box)return;'
r'function esc(s){var M={"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"};return String(s==null?"":s).replace(/[&<>"]/g,function(c){return M[c];});}'
r'function okUrl(u){return (typeof u==="string")&&/^https:\/\/([a-z0-9-]+\.)*(draftkings\.com|kalshi\.com)(\/[A-Za-z0-9\-._~:/?&=%,+@!$()*;]*)?$/i.test(u)?u:null;}'
r'function chip(bk,label,url,pm){if(!url)return "";var a=" data-bk=\""+bk+"\" data-book=\""+bk+"\" data-sb=\""+esc(url)+"\"";if(pm)a+=" data-pm=\""+esc(pm)+"\"";return "<span class=\"chip rpnontap\""+a+">"+esc(label)+"</span>";}'
r'function ptLabel(iso){try{return new Date(iso).toLocaleString("en-US",{timeZone:"America/Los_Angeles",weekday:"short",hour:"numeric",minute:"2-digit"})+" PT";}catch(e){return "";}}'
r'var RPCHIPS={},RP_CARDED_TM="";function RPKEY(p2,t2){return((p2||"")+"|"+(t2||"")).toLowerCase();}'
r"""function rpPT(s){return String(s==null?"":s).replace(/(\d{1,2}):(\d{2}) ([AP])M E[DS]T/g,function(m,h,mi,ap){var h24=(parseInt(h,10)%12)+(ap==="P"?12:0);h24=(h24+21)%24;var ap2=h24<12?"AM":"PM";return (h24%12||12)+":"+mi+" "+ap2+" PT";});}"""
r'function trkHtml(l,g){if(!g)return"";var dot=function(c){return"<span style=\"display:inline-block;width:7px;height:7px;border-radius:50%;background:"+c+";margin-right:6px;vertical-align:1px\"></span>";};var sc=(g.score&&g.status!=="pre")?(" &middot; "+esc(g.score)):"";if(g.status==="pre")return dot("#8a8f98")+"<span style=\"color:#8a8f98\">"+esc(rpPT(g.detail)||"Upcoming")+"</span>";var td=l.td_scored?("<b style=\"color:#0b6e5f\">TD"+(l.td_count>1?(" x"+l.td_count):"")+" &#10003;</b>"):null;if(g.status==="post")return td?(dot("#0b6e5f")+td+"<span style=\"color:#8a8f98\"> &middot; Final"+sc+"</span>"):(dot("#8a8f98")+"<span style=\"color:#8a8f98\">No TD &middot; Final"+sc+"</span>");return td?(dot("#0b6e5f")+td+"<span style=\"color:#8a8f98\"> &middot; "+esc(rpPT(g.detail)||"Live")+sc+"</span>"):(dot("#e8a13d")+"<span style=\"color:#b07708\">Live - no TD yet</span><span style=\"color:#8a8f98\"> &middot; "+esc(rpPT(g.detail)||"")+sc+"</span>");}'
r'function updTrk(){fetch("slates/nfl_live.json?cb="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){cdFrom(j);var gm={};(j.games||[]).forEach(function(g){gm[g.espn_event_id]=g;});(j.legs||[]).forEach(function(l){var el=document.querySelector("[data-trk=\""+RPKEY(l.player,l.team)+"\"]");if(el)el.innerHTML=trkHtml(l,gm[l.espn_event_id]);});}).catch(function(){});}'
r'function updChips(){var apply=function(quotes){document.querySelectorAll("[data-trk]").forEach(function(trk){var kc=RPCHIPS[trk.getAttribute("data-trk")];if(!kc)return;var row=trk.closest(".rpnpick");if(!row)return;var chs=row.querySelectorAll("[data-book=\"KAL\"]");for(var i=0;i<chs.length;i++){if(chs[i].querySelector("[data-book]"))continue;var q=kc.ticker?quotes[kc.ticker]:null;var lbl=null,fin=q&&q.status&&q.status!=="active";var qok=false;if(q&&q.status==="active"&&typeof q.yes_ask==="number"&&q.yes_ask>=1&&q.yes_ask<=99&&q.quoted_at){try{var qa=Date.now()-Date.parse(q.quoted_at);qok=qa>=0&&qa<=21600000;}catch(e){}}if(qok)lbl="KAL "+rpAml(q.yes_ask);else if(fin)lbl="KAL Final";else if(RP_CARDED_TM)lbl="KAL "+rpAml(kc.ask_c)+" \u00b7 "+RP_CARDED_TM;if(!lbl){chs[i].style.display="none";continue;}chs[i].style.display="";if(chs[i].textContent!==lbl)chs[i].textContent=lbl;if(fin){chs[i].removeAttribute("data-sb");}else{var sb=okUrl(kc.url);if(sb)chs[i].setAttribute("data-sb",sb);}}});};'
r'fetch("slates/nfl_kalshi_quotes.json?cb="+Date.now(),{cache:"no-store"}).then(function(r){return r.ok?r.json():null;}).then(function(qj){var fresh=false;try{var age=Date.now()-Date.parse(qj.quoted_at);fresh=qj&&qj.quoted_at&&age>=0&&age<=600000;}catch(e){}apply((fresh&&qj&&qj.quotes)||{});}).catch(function(){apply({});});}'
r'/* URF live-chip rule (main Sep-27 10:57 + 11:25): bare label = LIVE only when the quotes file is <=10 min old, market status is active, AND the per-ticker quoted_at (Kalshi updated_time) is <=6h old (main ruling 11:35: the gate catches frozen/dormant markets like a 20h-unchanged book; file-level 10-min remains the true quote-freshness proof). Non-active = plain-text Final, no route. Anything else reverts to carded price + explicit as-of, or hides. Stale never wears LIVE. */'
r'function empty(){box.innerHTML="<div style=\"color:#8a8f98;font-size:13px;padding:6px 0\">No NFL slate yet - Wooder Ice anytime TD picks land here Sundays.</div>";}'
r'function rpAml(c){var q=c/100;if(q<=0||q>=1)return"";return q>=0.5?String(Math.round(-100*q/(1-q))):"+"+String(Math.round(100*(1-q)/q));}'
r'function rpHM(ms){try{return new Date(ms).toLocaleString("en-US",{timeZone:"America/Los_Angeles",hour:"numeric",minute:"2-digit"}).toLowerCase().replace(/\s/g,"");}catch(e){return"";}}'
r'/* window countdown (Julian 12:18, design-approved via main): target = earliest game commence in nfl_live.json (ESPN), never hardcoded; fail-closed blank when no commence data; no negative countdown - post-kickoff shows games-underway. */'
r'var RP_CD=null;'
r'function cdFrom(j){var ts=[];(j.games||[]).forEach(function(g){var t=Date.parse(g.commence||"");if(!isNaN(t))ts.push(t);});RP_CD=ts.length?Math.min.apply(Math,ts):null;cdPaint();}'
r'function cdPaint(){var el=document.getElementById("rpNflCd");if(!el)return;if(!RP_CD){el.innerHTML="";return;}var now=Date.now();if(now>=RP_CD){el.innerHTML="<span style=\"display:inline-block;width:7px;height:7px;border-radius:50%;background:#0b6e5f;margin-right:6px;vertical-align:1px\"></span><b style=\"color:#0b6e5f\">Games underway</b><span style=\"color:#8a8f98\"> &middot; tracking live</span>";return;}var s=Math.max(0,Math.floor((RP_CD-now)/1000));var hh=Math.floor(s/3600),mm=Math.floor((s%3600)/60),ss=s%60;el.innerHTML="<span style=\"color:#b07708\">First kickoff <b>"+esc(rpHM(RP_CD))+" PT</b> in <b>"+(hh?hh+"h ":"")+mm+"m "+("0"+ss).slice(-2)+"s</b></span>";}'
r'function rpLegPx(o){var hasA=(o.odds!==undefined&&o.odds!==null&&String(o.odds)!=="");var hasC=(typeof o.price_c==="number"&&o.price_c>=1&&o.price_c<=99&&o.price_type==="contract_cents");if(hasA===hasC)return null;if(hasC)return{label:"DKP "+rpAml(o.price_c),head:rpAml(o.price_c)};return{label:"DK "+o.odds,head:String(o.odds)};}'
r'function render(j){'
r'var singles=((j.dk||{}).singles)||[],parlays=((j.dk||{}).parlays)||[];'
r'var kal=j.kalshi||{},top=kal.top10||[],bb=kal.bankroll_builder;'
r'if(!singles.length&&!parlays.length&&!top.length&&!(bb&&(bb.picks||[]).length)){empty();return;}'
r'var hd=document.getElementById("rpNflHead");if(hd){var WM={"sun-early":"EARLY PICKS","sun-afternoon":"AFTERNOON PICKS","sun-night":"NIGHT PICKS","mon-night":"MONDAY NIGHT PICKS","thu-night":"THURSDAY NIGHT PICKS"};var wt=WM[j.window]||((typeof j.window==="string"&&j.window)?(j.window.replace(/-/g," ").toUpperCase()+" PICKS"):"");hd.innerHTML=wt?("<div style=\"font-size:20px;font-weight:800;letter-spacing:.05em;margin:0 0 1px\">"+esc(wt)+"</div><div id=\"rpNflCd\" style=\"font-size:13px;margin:0 0 6px;min-height:16px\"></div>"):"";}'
r'var h="<div style=\"font-size:12px;color:#8a8f98;margin:2px 0 4px\">"+esc(j.window_label||"")+(j.generated_at?" &middot; posted "+esc(ptLabel(j.generated_at)):"")+"</div>";'
r'if(singles.length){h+="<div class=\"sect\" style=\"margin-top:10px\">DraftKings singles</div>";'
r'singles.forEach(function(s,i){var kl=null;'
r'top.forEach(function(t){if((t.player||"").toLowerCase()===(s.player||"").toLowerCase()&&(t.matchup||"")===(s.matchup||""))kl=t;});'
r'var px=rpLegPx(s);if(!px)return;var chips=chip("DKP",px.label,okUrl(s.link),null);'
r'var kc=RPCHIPS[RPKEY(s.player,s.team)];RP_CARDED_TM=j.generated_at?rpHM(Date.parse(j.generated_at)):"";var ctm=RP_CARDED_TM;if(kc&&ctm)chips+=chip("KAL","KAL "+rpAml(kc.ask_c)+" \u00b7 "+ctm,okUrl(kc.url),null);else if(kl&&ctm)chips+=chip("KAL","KAL "+rpAml(kl.price_c)+" \u00b7 "+ctm,okUrl(kl.link),null);'
r'h+="<div class=\"rpnpick\"><div class=\"pick-head\"><span class=\"gamelink\" style=\"cursor:default\"><span class=\"num\">"+(i+1)+".</span><span class=\"name\"><b>"+esc(s.player)+"</b> anytime TD</span></span><span class=\"uo\"><span class=\"odds\">"+esc(px.head)+"</span></span></div>"'
r'+"<div class=\"sub\">"+esc(s.matchup||"")+"</div><div class=\"sub rpntrk\" data-trk=\""+esc(RPKEY(s.player,s.team))+"\" style=\"margin-top:3px;font-size:12px\"></div>"+(chips?"<div class=\"chips\">"+chips+"</div>":"")+"</div>";});}'
r'if(parlays.length){h+="<div class=\"rpwhead\" style=\"margin-top:18px\">Parlays</div>";'
r'parlays.forEach(function(p){var _bad=false;var legs=(p.legs||[]).map(function(l){var lp=rpLegPx(l);if(!lp)_bad=true;return esc(l.player)+" ("+(lp?esc(lp.head):"?")+")";}).join(" + ");if(_bad)return;'
r'var _co=p.combined_odds,_cc=p.combined_price_c,_hasCO=(_co!==undefined&&_co!==null&&String(_co)!==""),_hasCC=(typeof _cc==="number"&&_cc>=1&&_cc<=99&&p.price_type==="contract_cents");if(_hasCO===_hasCC)return;var _clab=_hasCC?("DKP "+rpAml(_cc)):("DK "+_co),_chead=_hasCC?rpAml(_cc):String(_co);var chips=chip("DKP",_clab,okUrl(p.link),okUrl(p.pm));'
r'h+="<div class=\"rpnpick\"><div class=\"pick-head\"><span class=\"gamelink\" style=\"cursor:default\"><span class=\"name\"><b>"+(p.legs||[]).length+"-leg parlay</b></span></span><span class=\"uo\"><span class=\"odds\">"+esc(_chead)+"</span></span></div>"'
r'+"<div class=\"sub\">"+legs+"</div>"+(p.est_payout?"<div class=\"sub\">Est. payout "+esc(p.est_payout)+"</div>":"")+(chips?"<div class=\"chips\">"+chips+"</div>":"")+"</div>";});}'
r'if(top.length){h+="<div class=\"sect\" style=\"margin-top:14px\">Kalshi top "+top.length+"</div>";'
r'top.forEach(function(t,i){'
r'h+="<div class=\"rpnpick\"><div class=\"pick-head\"><span class=\"gamelink\" style=\"cursor:default\"><span class=\"num\">"+(i+1)+".</span><span class=\"name\"><b>"+esc(t.player)+"</b></span></span><span class=\"uo\"><span class=\"odds\">"+esc(rpAml(t.price_c))+"</span></span></div>"'
r'+"<div class=\"sub\">"+esc(t.matchup||"")+" &middot; "+Math.round((t.prob||0)*100)+"%</div>"'
r'+"<div class=\"chips\">"+chip("KAL","KAL "+rpAml(t.price_c),okUrl(t.link),null)+"</div></div>";});}'
r'if(bb&&(bb.picks||[]).length){h+="<div class=\"rpwhead\" style=\"margin-top:18px\">Bankroll Builder</div>";'
r'var bchips="";(bb.picks||[]).forEach(function(b2){bchips+=chip("KAL","KAL "+rpAml(b2.price_c),okUrl(b2.link),null);});'
r'h+="<div class=\"rpnpick\"><div class=\"pick-head\"><span class=\"gamelink\" style=\"cursor:default\"><span class=\"name\"><b>"+esc(bb.matchup||"")+"</b></span></span></div>"'
r'+"<div class=\"sub\">"+(bb.picks||[]).map(function(b2){return esc(b2.player)+" "+esc(rpAml(b2.price_c));}).join(" + ")+"</div>"'
r'+(bb.est_cost_c?"<div class=\"sub\">Sum of individual asks "+esc(bb.est_cost_c)+"c &middot; not a combined quote</div>":"")+(bchips?"<div class=\"chips\">"+bchips+"</div>":"")+"</div>";}'
r'box.innerHTML=h;'
r'try{if(window.rpFilter)rpFilter(localStorage.getItem("rp_state"));}catch(e){}}'
r'fetch("slates/nfl_chips.json?cb="+Date.now(),{cache:"no-store"}).then(function(r){return r.ok?r.json():null;}).then(function(cj){/* carded prices only; as-of comes from the slate generated_at at render (main Sep-27 URF directive). The file mtime advances without content change, so it must never be shown as the quote time. */((cj&&cj.legs)||[]).forEach(function(l){if(l.kalshi&&typeof l.kalshi.ask_c==="number")RPCHIPS[RPKEY(l.player,l.team)]={ask_c:l.kalshi.ask_c,url:l.kalshi.url,ticker:(typeof l.kalshi.ticker==="string"?l.kalshi.ticker:null)};});}).catch(function(){}).then(function(){'
r'fetch("slates/nfl_latest.json?cb="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){'
r'if(!j||j.version!==1){empty();return;}'
r'try{if(j.generated_at&&Date.now()-Date.parse(j.generated_at)>4*24*3600*1000){empty();return;}}catch(e){}'
r'render(j);updTrk();updChips();setInterval(function(){updTrk();updChips();},60000);setInterval(cdPaint,1000);}).catch(empty);});'
r'})();</script>')
# NIGHT PICKS block (night-picks agent 9/27; ported into the builder 3:38 PT so GHA rebuilds stop
# clobbering the hand-edited index.html): client-hydrated from slates/nfl_night.json, hides on
# missing/invalid/wrong-window. PT-only: source window_label carries ET - kickoff renders PT instead.
# Singles block carries its snapshot label (main 3:37): 'as of <capture> PT' from generated_at.
# okUrl uses indexOf, not a /\/// regex: scrub_shipped strips '//' comments - adjacent slashes
# get eaten as a comment and truncate the whole tab body (3:42 truncation bug).
nfl_entry+=(
r'''<div style="border:1px dashed rgba(127,127,127,.35);border-radius:12px;padding:11px 12px;margin-top:14px"><div id="rpNightHead"></div><div class="rpwhead">Anytime TD Scorers - Night</div><div style="font-size:12px;color:#8a8f98;margin:2px 0 8px">Separate from the RixPicks card and record. Picks only, no wagers placed.</div><div id="rpNight"><div style="color:#8a8f98;font-size:13px;padding:6px 0">Loading&hellip;</div></div></div>'''
r"""<script>(function(){var box=document.getElementById("rpNight");if(!box)return;function esc(s){var M={"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"};return String(s==null?"":s).replace(/[&<>"]/g,function(c){return M[c];});}function okUrl(u){return (typeof u==="string"&&u.indexOf("https://")===0)?u:null;}function rpAml(c){var q=c/100;if(q<=0||q>=1)return"";return q>=0.5?String(Math.round(-100*q/(1-q))):"+"+String(Math.round(100*(1-q)/q));}function rpHM(ms){try{return new Date(ms).toLocaleString("en-US",{timeZone:"America/Los_Angeles",hour:"numeric",minute:"2-digit"}).toLowerCase().replace(/\s/g,"");}catch(e){return"";}}function ptLabel(iso){try{return new Date(iso).toLocaleString("en-US",{timeZone:"America/Los_Angeles",weekday:"short",hour:"numeric",minute:"2-digit"})+" PT";}catch(e){return"";}}function chip(bk,label,url){if(!url)return "";return '<span class="chip rpnontap" data-bk="'+bk+'" data-book="'+bk+'" data-sb="'+esc(url)+'">'+esc(label)+"</span>";}function RPKEY(p2,t2){return((p2||"")+"|"+(t2||"")).toLowerCase();}var RP_KO=null;function cdPaint(){var el=document.getElementById("rpNightCd");if(!el)return;if(!RP_KO){el.innerHTML="";return;}var now=Date.now();if(now>=RP_KO){el.innerHTML="";return;}var s=Math.max(0,Math.floor((RP_KO-now)/1000));var hh=Math.floor(s/3600),mm=Math.floor((s%3600)/60),ss=s%60;el.innerHTML='<span style="color:#b07708">Kickoff <b>'+esc(rpHM(RP_KO))+' PT</b> in <b>'+(hh?hh+"h ":"")+mm+"m "+("0"+ss).slice(-2)+"s</b></span>";}function render(j){var singles=((j.dk||{}).singles)||[];var gl=((j.kalshi||{}).game_lines)||[];var sgp=j.sgp_idea||null;if(!singles.length&&!gl.length&&!sgp){box.innerHTML='<div style="color:#8a8f98;font-size:13px;padding:6px 0">No night slate yet.</div>';return;}var hd=document.getElementById("rpNightHead");if(hd){hd.innerHTML='<div style="font-size:20px;font-weight:800;letter-spacing:.05em;margin:0 0 1px">NIGHT PICKS</div><div id="rpNightCd" style="font-size:13px;margin:0 0 6px;min-height:16px"></div>';}RP_KO=j.kickoff?Date.parse(j.kickoff):null;cdPaint();setInterval(cdPaint,1000);var h='<div style="font-size:12px;color:#8a8f98;margin:2px 0 4px">'+(j.kickoff?esc(ptLabel(j.kickoff)):esc(j.window_label||""))+(j.generated_at?" &middot; posted "+esc(ptLabel(j.generated_at)):"")+"</div>";if(singles.length){var sao=j.generated_at?rpHM(Date.parse(j.generated_at)):"";h+='<div class="sect" style="margin-top:10px">DraftKings singles'+(sao?" &middot; as of "+esc(sao)+" PT":"")+"</div>";singles.forEach(function(s,i){var pc=(typeof s.price_c==="number"&&s.price_c>=1&&s.price_c<=99&&s.price_type==="contract_cents")?s.price_c:null;if(pc===null)return;var chips=chip("DKP","DKP "+rpAml(pc),okUrl(s.link));h+='<div class="rpnpick"><div class="pick-head"><span class="gamelink" style="cursor:default"><span class="num">'+(i+1)+'.</span><span class="name"><b>'+esc(s.player)+'</b> anytime TD</span></span><span class="uo"><span class="odds">'+esc(rpAml(pc))+'</span></span></div>'+'<div class="sub">'+esc(s.matchup||"")+'</div><div class="sub rpntrk" data-trk="'+esc(RPKEY(s.player,s.team))+'" style="margin-top:3px;font-size:12px"></div>'+(chips?'<div class="chips">'+chips+"</div>":"")+"</div>";});}if(sgp&&(sgp.legs||[]).length){var names=sgp.legs.map(function(l){return esc(l.player);}).join(" + ");var ev=okUrl((singles[0]||{}).link);var sc=chip("DKP","DKP",ev);h+='<div class="rpnpick"><div class="pick-head"><span class="gamelink" style="cursor:default"><span class="name"><b>'+esc(sgp.title||"Same Game Parlay idea")+'</b></span></span></div>'+'<div class="sub">'+names+" "+esc(sgp.market||"")+"</div>"+(sgp.note?'<div class="sub">'+esc(sgp.note)+"</div>":"")+(sc?'<div class="chips">'+sc+"</div>":"")+"</div>";}if(gl.length){var cap=gl[0].captured_at?rpHM(Date.parse(gl[0].captured_at)):"";h+='<div class="sect" style="margin-top:14px">Kalshi game lines'+(cap?" &middot; as of "+esc(cap)+" PT":"")+"</div>";gl.forEach(function(g){var pc=(typeof g.price_c==="number"&&g.price_c>=1&&g.price_c<=99)?g.price_c:null;if(pc===null)return;var kc=chip("KAL","KAL "+rpAml(pc)+(cap?" · "+cap:""),okUrl(g.link));h+='<div class="rpnpick"><div class="pick-head"><span class="gamelink" style="cursor:default"><span class="name"><b>'+esc(g.title)+'</b></span></span><span class="uo"><span class="odds">'+esc(rpAml(pc))+'</span></span></div>'+'<div class="sub">'+esc(g.market||"")+" &middot; LAR @ DEN</div>"+(kc?'<div class="chips">'+kc+"</div>":"")+"</div>";});}box.innerHTML=h;try{if(window.rpFilter)rpFilter(localStorage.getItem("rp_state"));}catch(e){}}fetch("slates/nfl_night.json?cb="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){if(!j||j.version!==1||j.window!=="sun-night")return;render(j);}).catch(function(){});})();</script>"""
)
# Wooder night eight-leg DK idea; distinct from the eight ATD singles and four-TD text idea.
# Its own file survives generated-index rebuilds. Never infer a combined quote or a placed wager.
nfl_entry+=(
r'<div style="margin-top:14px;border:1px solid rgba(11,110,95,.45);border-radius:12px;padding:11px 12px" id="rpNightSgpCard" hidden>'
r'<div class="rpwhead" style="margin-top:0">Night eight-leg DK idea</div>'
r'<div id="rpNightSgp"></div></div>'
r'<script>(function(){'
r'var box=document.getElementById("rpNightSgp"),card=document.getElementById("rpNightSgpCard");if(!box||!card)return;'
r'function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]||"&quot;";});}'
r'function american(n){if(typeof n!=="number"||n<=0||n>=100)return "";return n<50?"+"+Math.round(100*(100-n)/n):String(Math.round(-100*n/(100-n)));}'
r'function stamp(s){try{return new Date(s).toLocaleString("en-US",{timeZone:"America/Los_Angeles",hour:"numeric",minute:"2-digit"}).toLowerCase().replace(/\s/g,"")+" PT";}catch(e){return "";}}'
r'fetch("slates/nfl_night_sgp.json?cb="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){'
r'if(!j||j.version!==1||j.kind!=="nfl-sgp-idea"||j.status!=="idea_only"||j.combined_price!==null||!Array.isArray(j.legs)||j.legs.length!==8||j.matchup!=="LAR @ DEN")return;'
r'var rows=j.legs.map(function(l,i){var a=american(l.price_c);if(!a||!l.player||!l.market||!l.captured_at||l.price_type!=="displayed_probability_percent")return "";return "<div class=\"rpnpick\" style=\"padding:8px 0\"><div style=\"display:flex;justify-content:space-between;gap:12px;align-items:baseline\"><span style=\"font-size:13px\">"+(i+1)+". <b>"+esc(l.player)+"</b> "+esc(l.market)+"</span><b style=\"white-space:nowrap\">"+a+"</b></div><div style=\"font-size:11px;color:#8a8f98;margin-top:2px\">DK Predictions · as of "+esc(stamp(l.captured_at))+(typeof l.source_snapshot_c==="number"&&l.source_snapshot_c!==l.price_c?" · Julian\u2019s snapshot "+l.source_snapshot_c+"c; live DK "+l.price_c+"% at capture":"")+" · selection link unavailable</div></div>";});'
r'if(rows.some(function(x){return !x;}))return;'
r'box.innerHTML="<div style=\"font-size:12px;color:#8a8f98;margin:3px 0 8px\">LAR @ DEN · Sunday 5:20pm PT · idea only, not bought</div>"+rows.join("")+"<div style=\"font-size:12px;color:#8a8f98;margin-top:9px;line-height:1.45\">Individual DK displayed percentages converted to American-style equivalents at capture. Prices can move. No combined DK quote or wager posted. Event page is not an exact-selection link, so these rows are unlinked.</div>";'
r'card.hidden=false;}).catch(function(){});})();</script>')
# Wooder WNBA three-leg idea; separate from the NFL night idea and tickets.
# Research snapshots remain marked as such when the source cannot be live rechecked.
# PLACEMENT (Julian 9/27 4:34 PT via main, standing): his WNBA content always lives on the WNBA tab, never the Wooder tab.
wnba_entry=(
r'<div style="margin-top:14px;border:1px solid rgba(11,110,95,.45);border-radius:12px;padding:11px 12px" id="rpWnbaSgpCard" hidden>'
r'<div class="rpwhead" style="margin-top:0">WNBA three-leg SGP idea</div><div id="rpWnbaSgp"></div></div>'
r'<script>(function(){'
r'var box=document.getElementById("rpWnbaSgp"),card=document.getElementById("rpWnbaSgpCard");if(!box||!card)return;'
r'function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){return c==="&"?"&amp;":c==="<"?"&lt;":c===">"?"&gt;":"&quot;";});}'
r'function aml(n){return typeof n!=="number"||n<=0||n>=100?"":(n<50?"+"+Math.round(100*(100-n)/n):String(Math.round(-100*n/(100-n))));}'
r'function stamp(s){try{return new Date(s).toLocaleString("en-US",{timeZone:"America/Los_Angeles",hour:"numeric",minute:"2-digit"}).toLowerCase().replace(/\s/g,"")+" PT";}catch(e){return "";}}'
r'fetch("slates/wnba_sgp_idea.json?cb="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){'
r'if(!j||j.version!==1||j.kind!=="wnba-sgp-idea"||j.status!=="idea_only"||j.combined_price!==null||!Array.isArray(j.legs)||j.legs.length!==3)return;'
r'var rows=j.legs.map(function(l,i){var d=aml(l.dk_display_probability);if(!l.player||!l.original_market||!l.dk_market||!d)return "";var sub=l.original_market!==l.dk_market?"<div style=\"font-size:11px;color:#b07708\">DK substitute: "+esc(l.dk_market)+" is stricter than original "+esc(l.original_market)+"</div>":"";var kal=l.kalshi_status==="not_verified"?"Kalshi: exact selection unavailable / no quote verified":("Kalshi "+esc(l.kalshi_market)+" "+aml(l.kalshi_display_probability)+(l.kalshi_status==="stricter_substitute"?" (stricter than original "+esc(l.original_market)+")":"")+" · as of "+esc(stamp(l.kalshi_as_of))+" · "+(l.kalshi_verified==="web_page_snapshot"?"board snapshot":"research snapshot, not live-verified")+", no exact link");return "<div class=\"rpnpick\" style=\"padding:8px 0\"><div style=\"display:flex;justify-content:space-between;gap:12px;align-items:baseline\"><span style=\"font-size:13px\">"+(i+1)+". <b>"+esc(l.player)+"</b> "+esc(l.original_market)+"</span><b style=\"white-space:nowrap\">"+d+"</b></div>"+sub+"<div style=\"font-size:11px;color:#8a8f98;margin-top:2px\">DK "+esc(l.dk_market)+" · as of "+esc(stamp(l.dk_as_of))+" · research snapshot, not live-verified · no exact link</div><div style=\"font-size:11px;color:#8a8f98;margin-top:2px\">"+kal+"</div></div>";});'
r'if(rows.some(function(x){return !x;}))return;box.innerHTML="<div style=\"font-size:12px;color:#8a8f98;margin:3px 0 8px\">WAS @ ATL · Sunday 4:00pm PT · idea only, not bought</div>"+rows.join("")+"<div style=\"font-size:12px;color:#8a8f98;margin-top:9px;line-height:1.45\">Individual displayed probabilities converted to American-style equivalents; not executable quotes. Kalshi has no complete three-leg match. No combined quote or wager posted. All rows unlinked without exact-selection links.</div>";card.hidden=false;}).catch(function(){});})();</script>')
# Wooder Ice first-TD picks (main 12:46, publish promptly): additive block - individual
# first-touchdown picks only. NEVER a linked parlay: no combined odds/stake/payout/status
# (source crop establishes none). No venue chips - source establishes no venue. Client-hydrated
# from slates/wooder_first_td.json; hides on missing/invalid. All times PT (owner 9/27 rule).
nfl_entry+=(
r'<div style="margin-top:14px;border:1px solid rgba(11,110,95,.45);border-radius:12px;padding:11px 12px">'
r'<div class="rpwhead" style="margin-top:0">FIRST TD SCORERS</div>'
r'<div id="rpFtd"></div>'
r'</div>'
r'<script>(function(){'
r'var box=document.getElementById("rpFtd");if(!box)return;'
r'function esc(s){var M={"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"};return String(s==null?"":s).replace(/[&<>"]/g,function(c){return M[c];});}'
r'function ptT(iso){try{return new Date(iso).toLocaleString("en-US",{timeZone:"America/Los_Angeles",hour:"numeric",minute:"2-digit"})+" PT";}catch(e){return "";}}'
r'fetch("slates/wooder_first_td.json?cb="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){'
r'var ps=(j&&j.picks)||[];'
r'if(!ps.length){box.parentNode.style.display="none";return;}'
r'box.innerHTML=ps.map(function(p,i){'
r'if(!p||!p.player||!p.market||!p.american)return "";'
r'return "<div style=\"margin-top:8px;border:1px solid rgba(11,110,95,.35);border-radius:10px;padding:9px 11px\">"'
r'+"<div style=\"font-size:10px;font-weight:700;letter-spacing:.09em;color:#0a7c5c\">PERSONAL PICK "+(i+1)+"</div>"'
r'+"<div style=\"display:flex;justify-content:space-between;align-items:baseline;margin-top:3px\"><b>"+esc(p.player)+"</b><span style=\"font-weight:700\">"+esc(p.american)+"</span></div>"'
r'+"<div style=\"font-size:12px;color:#8a8f98;margin-top:2px\">"+esc(p.market)+" &middot; "+esc(p.matchup||"")+(p.commence?" &middot; "+esc(ptT(p.commence)):"")+"</div>"'
r'+"</div>";}).join("");'
r'}).catch(function(){box.parentNode.style.display="none";});'
r'})();</script>')
# Wooder Ice same-game combos (main 9:22): additive Kalshi combo list - legs + game link only
# (no combined odds/payout; nothing priced or invented). Client-hydrated, hides when empty.
nfl_entry+=(
r'<div style="margin-top:14px;border:1px solid rgba(11,110,95,.45);border-radius:12px;padding:11px 12px">'
r'<div class="rpwhead">Same Game Parlays</div>'
r'<div id="rpCmb"></div>'
r'</div>'
r'<script>(function(){'
r'var box=document.getElementById("rpCmb");if(!box)return;'
r'function esc(s){var M={"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"};return String(s==null?"":s).replace(/[&<>"]/g,function(c){return M[c];});}'
r'fetch("slates/wooder_combos.json?cb="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){'
r'var cs=(j&&j.combos)||[];'
r'if(!cs.length){box.parentNode.style.display="none";return;}'
r'box.innerHTML=cs.map(function(c,i){'
r'return "<a class=\"rpnpick\" style=\"display:block;text-decoration:none;color:inherit\" href=\""+esc(c.url)+"\" target=\"_blank\" rel=\"noreferrer\">"'
r'+"<div style=\"display:flex;justify-content:space-between;align-items:baseline\"><b>"+(i+1)+". "+esc((c.legs||[]).join(" + "))+"</b><span style=\"color:#0a7c5c;font-size:11px;font-weight:700;white-space:nowrap\">KAL &#8250;</span></div>"'
r'+"<div style=\"font-size:12px;color:#8a8f98;margin-top:2px\">"+esc(c.matchup||"")+(c.time?" &middot; "+esc(c.time):"")+"</div>"'
r'+"</a>";}).join("");'
r'}).catch(function(){box.parentNode.style.display="none";});'
r'})();</script>')
# Wooder Ice's current tickets (main 9:05): additive ticket ledger shared by the guest -
# client-hydrated from slates/wooder_tickets.json; section hides when no tickets exist.
nfl_entry+=(
r'<div style="margin-top:14px;border:1px solid rgba(216,162,58,.45);border-radius:12px;padding:11px 12px">'
r'<div id="rpTix"><div style="color:#8a8f98;font-size:13px;padding:6px 0">Loading&hellip;</div></div>'
r'</div>'
r'<script>(function(){'
r'var box=document.getElementById("rpTix"),boxW=document.getElementById("rpTixW");if(!box)return;'
r'function esc(s){var M={"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"};return String(s==null?"":s).replace(/[&<>"]/g,function(c){return M[c];});}'
r"""function dot(c){return "<span style=\"display:inline-block;width:7px;height:7px;border-radius:50%;background:"+c+";margin-right:6px;vertical-align:1px\"></span>";}"""
r"""function abPair(m){var N={WAS:"WSH"};var p=String(m||"").toUpperCase().split("-");if(p.length!==2)return null;var x=p[0].trim(),y=p[1].trim();return [N[x]||x,N[y]||y];}"""
r"""function statOf(sj,name,key){try{var tms=(sj.boxscore&&sj.boxscore.players)||[];var total=0,found=false;for(var t=0;t<tms.length;t++){var sts=tms[t].statistics||[];for(var q=0;q<sts.length;q++){var keys=sts[q].keys||[];var idx=[];for(var k=0;k<keys.length;k++){if(key==="__TD__"){if(/touchdowns$/i.test(keys[k])&&!/passing/i.test(keys[k]))idx.push(k);}else if(keys[k]===key)idx.push(k);}if(!idx.length)continue;var aths=sts[q].athletes||[];for(var a=0;a<aths.length;a++){if((((aths[a].athlete||{}).displayName)||"").toLowerCase()===String(name||"").toLowerCase()){found=true;for(var z=0;z<idx.length;z++){var v=parseInt((aths[a].stats||[])[idx[z]],10);if(!isNaN(v))total+=v;}}}}}return found?total:null;}catch(e){}return null;}"""
r"""function mSpec(m){m=String(m||"");var x;if(/anytime\s*td/i.test(m))return{td:true,label:"TD",target:1,key:"__TD__"};if(x=m.match(/(\d+)\+?\s*rushing\s*yards?/i))return{label:"rush yds",target:+x[1],key:"rushingYards"};if(x=m.match(/(\d+)\+?\s*receptions?/i))return{label:"rec",target:+x[1],key:"receptions"};if(x=m.match(/(\d+)\+?\s*passing\s*touchdowns?/i))return{label:"pass TD",target:+x[1],key:"passingTouchdowns"};return null;}"""
r"""function tS(spec,count,state,det){var cur=(count==null?0:count);var got=(count!=null&&count>=spec.target);var txt=spec.td?(got?(spec.label+(cur>1?(" x"+cur):"")):("No "+spec.label+" yet")):(cur+"/"+spec.target+" "+spec.label);var badge=got?("<b style=\"color:#0b6e5f\">"+txt+" &#10003;</b>"):null;if(state==="post")return got?(dot("#0b6e5f")+badge+"<span style=\"color:#8a8f98\"> &middot; Final</span>"):(dot("#8a8f98")+"<span style=\"color:#8a8f98\">"+(spec.td?("No "+spec.label):txt)+" &middot; Final</span>");if(got)return dot("#0b6e5f")+badge;var dly=/delay|postpon|suspend/i.test(det||"");if(state==="in")return dly?(dot("#e8a13d")+"<span style=\"color:#b07708\">"+txt+" &middot; Delayed</span>"):(dot("#e8a13d")+"<span style=\"color:#b07708\">"+txt+"</span>");if(dly)return dot("#8a8f98")+"<span style=\"color:#8a8f98\">Delayed</span>";return dot("#8a8f98")+"<span style=\"color:#8a8f98\">Game not started</span>";}"""
r"""function updTix(){fetch("slates/julian_live.json?cb="+Date.now(),{cache:"no-store"}).then(function(r){return r.ok?r.json():null;}).catch(function(){return null;}).then(function(lj){var llegs=(lj&&lj.live_legs)||[];function nrm(s){return String(s||"").toLowerCase().replace(/[^a-z0-9]+/g,"");}Array.prototype.forEach.call(document.querySelectorAll(".rptixtrk"),function(el){var fm=el.getAttribute("data-fm");if(!fm)return;var np=nrm(el.getAttribute("data-p")),nm=nrm(String(el.getAttribute("data-m")||"").replace(/\s*@\s*/g,"-"));var hit=null;llegs.forEach(function(l){if(hit)return;if(l.market!==fm)return;if(nrm(l.player)!==np)return;if(nm&&nrm(String(l.matchup||"").replace(/\s*@\s*/g,"-"))!==nm)return;hit=l;});if(!hit)return;el.__fed=true;var st=hit.game_state||"",det=hit.game_detail||"",pr2=hit.progress||"";if(/[AP]M\s*(E|C|M|P)/i.test(det))det="";var g0="";var paintG=function(rp){(rp||[]).forEach(function(p){if(g0)return;if(p.market!==fm)return;if(nrm(p.label)!==np)return;if(nm&&nrm(String(p.matchup||"").replace(/\s*@\s*/g,"-"))!==nm)return;g0=(p.status==="won"||p.status==="lost")?p.status:"";});};var runG=function(){paintG(window.__rpRecPicks||[]);if(g0){el.innerHTML=(g0==="won"?(dot("#0b6e5f")+"<b style=\"color:#0b6e5f\">Won &#10003;</b>"):(dot("#8a8f98")+"<span style=\"color:#8a8f98\">Lost</span>"))+(st==="post"?"<span style=\"color:#8a8f98\"> &middot; Final</span>":(det?"<span style=\"color:#8a8f98\"> &middot; "+esc(det)+"</span>":""));}else if(st==="post"){el.innerHTML=dot("#8a8f98")+(pr2?("<span style=\"color:#8a8f98\">"+esc(pr2)+"</span>"):"")+"<span style=\"color:#8a8f98\"> &middot; Final</span>";}else{el.innerHTML=dot(st==="in"?"#e8a13d":"#8a8f98")+(pr2?("<span style=\"color:"+(st==="in"?"#b07708":"#8a8f98")+"\">"+esc(pr2)+"</span>"):"")+(det?"<span style=\"color:#8a8f98\"> &middot; "+esc(det)+"</span>":"");}};if(window.__rpRecPicks){runG();}else{fetch("slates/julian_record.json?cb="+Date.now(),{cache:"no-store"}).then(function(r){return r.ok?r.json():null;}).then(function(rj){window.__rpRecPicks=(rj&&rj.picks)||[];runG();}).catch(function(){window.__rpRecPicks=[];runG();});}});fetch("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?cb="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(sb){var gm={};(sb.events||[]).forEach(function(ev){var cmp=(ev.competitions||[])[0]||{};var st=(cmp.status&&cmp.status.type)||{};var home=null,away=null;(cmp.competitors||[]).forEach(function(c){var o={ab:((c.team||{}).abbreviation||"").toUpperCase()};if(c.homeAway==="home")home=o;else away=o;});if(home&&away)gm[away.ab+"-"+home.ab]={state:st.state||"",eid:ev.id,det:(st.detail||st.shortDetail||"")};});var seen={};Array.prototype.forEach.call(document.querySelectorAll(".rptixtrk"),function(el){if(el.__fed)return;var pr=abPair(el.getAttribute("data-m"));var g=pr?gm[pr[0]+"-"+pr[1]]:null;if(!g){el.innerHTML="";return;}el.__st=g.state;el.__det=g.det;if(g.eid&&g.state!=="pre"){(seen[g.eid]=seen[g.eid]||[]).push(el);}else{var sp=mSpec(el.getAttribute("data-mkt"));el.innerHTML=sp?tS(sp,null,g.state,g.det):"";}});Object.keys(seen).forEach(function(eid){fetch("https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event="+eid+"&cb="+Date.now(),{cache:"no-store"}).then(function(r){return r.ok?r.json():null;}).then(function(sj){if(!sj)return;seen[eid].forEach(function(el){var sp=mSpec(el.getAttribute("data-mkt"));if(!sp){el.innerHTML="";return;}el.innerHTML=tS(sp,statOf(sj,el.getAttribute("data-p"),sp.key),el.__st,el.__det);});}).catch(function(){});});}).catch(function(){});});}"""
r"""function startTrk(){updTix();setInterval(updTix,30000);}"""
r'fetch("slates/wooder_tickets.json?cb="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){'
r'var tixAll=(j&&j.tickets)||[];'
r'function renderInto(bx,arr){if(!bx)return;if(!arr.length){bx.parentNode.style.display="none";return;}var h="",ups=[];'
'arr.forEach(function(t,ti){'
r'(t.site_updates||[]).forEach(function(u){ups.push(u);});'
r'h+="<div class=\"rpnpick\""+(ti>0?" style=\"margin-top:18px;border-top:1px solid #e4e2de;padding-top:14px\"":"")+">"'
r'+"<div class=\"rpwhead\">Ticket "+(t.id||(ti+1))+(t.title?" &middot; "+esc(t.title):"")+"</div>"'
r'+"<div style=\"display:flex;justify-content:space-between;align-items:baseline;margin-top:2px\"><span>"+(t.bought?"<span style=\"background:#0b6e5f;color:#fff;border-radius:8px;font-size:11px;font-weight:700;padding:1px 8px\">BOUGHT</span> ":"")+(t.pct?"<span style=\"color:#8a8f98\">"+esc(t.pct)+"</span> ":"")+(t.odds_was?"<s style=\"color:#8a8f98\">"+esc(t.odds_was)+"</s> ":"")+(t.odds_boosted?"<span style=\"background:#7c3aed;color:#fff;border-radius:8px;font-size:11px;font-weight:700;padding:1px 8px\">"+esc(t.odds_boosted)+"</span>":"")+"</span>"+(t.status?"<span style=\"background:rgba(216,162,58,.18);color:#b07708;border-radius:8px;font-size:11px;font-weight:700;padding:1px 8px\">"+esc(t.status)+"</span>":"")+"</div>"'
r'+(function(){var bTxt=(typeof t.bought==="string"&&t.bought)?("Bought "+esc(t.bought)):"";return (bTxt||t.to_pay||t.fancash)?("<div style=\"font-size:12px;color:#8a8f98;margin-top:2px\">"+bTxt+(bTxt&&t.to_pay?" &middot; ":"")+(t.to_pay?"To Pay "+esc(t.to_pay):"")+((bTxt||t.to_pay)&&t.fancash?" &middot; ":"")+(t.fancash?"FanCash "+esc(t.fancash):"")+"</div>"):"";})()'
r'+(t.legs||[]).map(function(l,i){var fin=l.status||"";var pill="";if(fin==="won")pill=dot("#0b6e5f")+"<b style=\"color:#0b6e5f\">Won &#10003;</b><span style=\"color:#8a8f98\"> &middot; Final</span>";else if(fin==="lost")pill=dot("#8a8f98")+"<span style=\"color:#8a8f98\">Lost &middot; Final</span>";else if(fin==="void")pill=dot("#8a8f98")+"<span style=\"color:#8a8f98\">Void</span>";return "<div style=\"font-size:13px;margin-top:5px\">"+(i+1)+". <b>"+esc(l.player)+"</b> <span style=\"color:#8a8f98\">"+esc(l.market||"")+(l.matchup?" &middot; "+esc(l.matchup):"")+(l.time?" &middot; "+esc(l.time):"")+"</span></div>"+(pill?"<div style=\"margin-top:1px;font-size:12px\">"+pill+"</div>":("<div class=\"rptixtrk\" data-p=\""+esc(l.fp||l.player||"")+"\" data-m=\""+esc(l.matchup||"")+"\" data-mkt=\""+esc(l.market||"")+"\" data-fm=\""+esc(l.fm||"")+"\" style=\"margin-top:1px;font-size:12px\"></div>"));}).join("")'
r'+"</div>";});'
r'if(ups.length){h+="<div class=\"rpwhead\" style=\"margin-top:20px\">Site Update <span style=\"background:rgba(216,162,58,.18);color:#b07708;border-radius:8px;font-size:10px;font-weight:700;padding:1px 7px;vertical-align:3px\">PROPOSED &middot; NOT BOUGHT</span></div>";'
r'h+=ups.map(function(u){'
r'return "<div style=\"margin-top:8px;border:1px dashed rgba(216,162,58,.6);border-radius:10px;padding:8px 10px\">"'
r'+"<div style=\"font-size:11px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:#b07708\">"+esc(u.label||"Wooder Ice site update")+"</div>"'
r'+(u.note?"<div style=\"font-size:12px;color:#8a8f98;margin-top:3px\">"+esc(u.note)+"</div>":"")'
r'+(u.items||[]).map(function(it){return "<div style=\"font-size:13px;margin-top:5px\">"+(it.proposed?"<span style=\"background:rgba(216,162,58,.18);color:#b07708;border-radius:8px;font-size:10px;font-weight:700;padding:1px 7px;margin-right:8px;vertical-align:1px;letter-spacing:.04em\">PROPOSED</span>":"")+"<b>"+esc(it.player||"")+"</b> <span style=\"color:#8a8f98\">"+esc(it.market||"")+(it.matchup?" &middot; "+esc(it.matchup):"")+(it.time?" &middot; "+esc(it.time):"")+(it.status?" &middot; "+esc(it.status):"")+"</span>"+(it.kalshi&&it.kalshi.url?" <a class=\"chip\" style=\"background:#e6f9f3;border-color:#e6f9f3;color:#0a7c5c;font-size:11px;padding:2px 10px\" href=\""+esc(it.kalshi.url)+"\" target=\"_blank\" rel=\"noreferrer\">KAL "+esc(it.kalshi.american||"")+"</a>":"")+"</div>";}).join("")'
r'+"</div>";}).join("");}'
r'bx.innerHTML=h;}'
r'renderInto(box,tixAll.filter(function(t){return t.sport!=="wnba";}));'
r'renderInto(boxW,tixAll.filter(function(t){return t.sport==="wnba";}));'
r'startTrk();'
r'}).catch(function(){box.parentNode.style.display="none";if(boxW)boxW.parentNode.style.display="none";});'
r'})();</script>')


# Wooder Ice rolling record (Dardan 12:37-12:38 via main): live graded record of the guest's
# picks, Wooder tab ONLY, updates in real time as picks resolve. Client-hydrated from
# slates/julian_record.json (analysis feed, rebuilt each wire cycle); 60s re-fetch; fail-closed
# hide on missing/invalid. Pending renders as pending - never blank, never guessed.
nfl_entry+=(
r'<div id="rpWRecWrap" style="margin-top:14px;border:1px solid rgba(127,127,127,.35);border-radius:12px;padding:11px 12px">'
r'<div id="rpWRecHead" style="display:flex;justify-content:space-between;align-items:center;cursor:pointer;user-select:none"><div class="rpwhead">Rolling Record</div><span id="rpWRecChev" style="font-size:14px;font-weight:700;color:#8a8f98;padding:0 4px;line-height:1">v</span></div>'
r'<div id="rpWRecBody" style="display:none">'
r'<div style="font-size:12px;color:#8a8f98;margin:2px 0 8px">Wooder Ice picks only - separate from the RixPicks card and record.</div>'
r'<div id="rpWRec"><div style="color:#8a8f98;font-size:13px;padding:6px 0">Loading&hellip;</div></div>'
r'</div>'
r'</div>'
r'<script>(function(){'
r'var box=document.getElementById("rpWRec");if(!box)return;'
r'var head=document.getElementById("rpWRecHead");if(head)head.onclick=function(){var b=document.getElementById("rpWRecBody");var c=document.getElementById("rpWRecChev");if(!b||!c)return;var open=b.style.display!=="none";b.style.display=open?"none":"";c.textContent=open?"v":"^";};'
r'function esc(s){var M={"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"};return String(s==null?"":s).replace(/[&<>"]/g,function(c){return M[c];});}'
r'var MM={anytime_td:"Anytime TD",home_run:"Home Run",ml:"ML",passing_yards:"Passing Yds",pass_td:"Pass TD",receptions:"Receptions",rushing_yards:"Rush Yds",total_over:"Total Over",first_td:"First TD"};'
r'function wlabel(w){return String(w||"").replace(/-\d{4}-\d{2}-\d{2}$/,"").replace(/-/g," ").replace(/\b\w/g,function(c){return c.toUpperCase();});}'
r'function pill(st){var m={w:["#0b6e5f","W"],l:["#e5484d","L"],p:["#8a8f98","P"]};var x=m[st];if(!x)return "<span style=\"color:#8a8f98;font-size:11px;font-weight:700\">pending</span>";return "<span style=\"color:"+x[0]+";font-size:11px;font-weight:700\">"+x[1]+"</span>";}'
r'function paint(j){var r=j.record||{};var h="<div style=\"font-size:17px;font-weight:800\">"+(r.wins||0)+"-"+(r.losses||0)+((r.pushes||0)?("-"+r.pushes):"")+" <span style=\"font-size:12px;font-weight:600;color:#8a8f98\">"+(r.pending||0)+" pending</span></div>";'
r'var bw=j.by_window||{};var keys=Object.keys(bw);'
r'if(keys.length){h+="<div style=\"margin:4px 0 6px\">"+keys.map(function(k){var v=bw[k]||{};return "<span style=\"display:inline-block;background:rgba(127,127,127,.12);border-radius:8px;font-size:11px;font-weight:600;padding:2px 8px;margin:2px 4px 2px 0\">"+esc(wlabel(k))+" "+(v.wins||0)+"-"+(v.losses||0)+((v.pushes||0)?("-"+v.pushes):"")+" &middot; "+(v.pending||0)+" pend</span>";}).join("")+"</div>";}'
r'var ps=j.picks||[];var byW={};var ord=[];ps.forEach(function(p){var w=p.window||"other";if(!byW[w]){byW[w]=[];ord.push(w);}byW[w].push(p);});'
r'h+=ord.map(function(w){var rows=byW[w].map(function(p){var pr=(p.price!=null?String(p.price):"");var vn=p.venue?esc(p.venue):"";'
r'return "<div style=\"display:flex;justify-content:space-between;align-items:baseline;font-size:13px;margin-top:4px\"><span><b>"+esc(p.label||"")+"</b> <span style=\"color:#8a8f98\">"+esc(MM[p.market]||p.market||"")+(p.line!=null?(" "+esc(p.line)):"")+(p.matchup?" &middot; "+esc(p.matchup):"")+"</span></span><span style=\"white-space:nowrap\">"+(vn?("<span style=\"color:#8a8f98;font-size:11px\">"+vn+(pr?" "+esc(pr):"")+"</span> "):"")+pill(p.status)+"</span></div>";}).join("");'
r'return "<div style=\"margin-top:10px;border-top:1px solid #e4e2de;padding-top:8px\"><div style=\"font-size:11px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:#8a8f98\">"+esc(wlabel(w))+"</div>"+rows+"</div>";}).join("");'
r'box.innerHTML=h;}'
r'function load(){fetch("slates/julian_record.json?cb="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){if(!j||!j.record||!Array.isArray(j.picks))throw 0;paint(j);}).catch(function(){var w=document.getElementById("rpWRecWrap");if(w)w.style.display="none";});}'
r'load();setInterval(load,60000);'
r'})();</script>')

wnba_entry+=(
r'<div style="margin-top:22px">'
r'<div class="sect">Wooder Ice<span style="display:inline-block;background:#0b6e5f;color:#fff;border-radius:8px;font-size:10px;font-weight:700;letter-spacing:.06em;padding:1px 7px;margin-left:8px;vertical-align:2px">GUEST</span></div>'
r'<div style="font-size:12px;color:#8a8f98;margin:2px 0 8px">Separate from the RixPicks card and record. Picks only, no wagers placed.</div>'
r'<div style="border:1px solid rgba(216,162,58,.45);border-radius:12px;padding:11px 12px">'
r'<div id="rpTixW"><div style="color:#8a8f98;font-size:13px;padding:6px 0">Loading&hellip;</div></div>'
r'</div></div>')

fut_watch_html=''
if FUT:
    try:
        import urllib.request as _u, datetime as _dt
        from zoneinfo import ZoneInfo as _ZI
        _today=_dt.datetime.now(_ZI('America/Los_Angeles')).strftime('%Y%m%d')
        _REG=json.load(open(os.path.join(os.path.dirname(__file__),'..','config_leagues.json')))['leagues']
        _LGMAP={k:(v['espn'],v.get('logo_dir')) for k,v in _REG.items() if v.get('espn') and v.get('futures')}
        _held={}
        for _f in FUT:
            if _f.get('league') not in _LGMAP or not _f.get('abbr'): continue
            _held.setdefault(_f['team'],{'abbr':_f['abbr'],'mkts':[],'lg':_f['league']})
            _lbl='SB' if 'Super Bowl' in _f['market'] else (_f['market'][:-9] if _f['market'].endswith(' Champion') else _f['market'])
            if _lbl not in _held[_f['team']]['mkts']: _held[_f['team']]['mkts'].append(_lbl)
        _sbs={}
        for _lg in {v['lg'] for v in _held.values()}:
            try:
                _prm='&'+_REG[_lg].get('espn_params','') if _REG[_lg].get('espn_params') else ''
                _req=_u.Request('https://site.api.espn.com/apis/site/v2/sports/%s/scoreboard?dates='%_LGMAP[_lg][0]+_today+'&limit=100'+_prm,headers={'User-Agent':'python-urllib/3.10'})
                _sbs[_lg]=json.load(_u.urlopen(_req,timeout=15))
            except Exception: pass
        _mlogo={}
        for _lg2,_sb2 in _sbs.items():
            for _ev2 in _sb2.get('events',[]):
                for _c2 in (_ev2.get('competitions') or [{}])[0].get('competitors',[]):
                    _t2=_c2.get('team') or {}
                    if _t2.get('logo'): _mlogo[(_lg2,_t2.get('displayName',''))]=_t2['logo']
        _fw=[];_fwgot=set()
        for _lg,_sb in _sbs.items():
          for ev in _sb.get('events',[]):
            cs=ev['competitions'][0]['competitors']
            aw=next((c for c in cs if c['homeAway']=='away'),None); hm=next((c for c in cs if c['homeAway']=='home'),None)
            if not aw or not hm: continue
            an=aw['team']['displayName']; hn=hm['team']['displayName']
            for t,info in _held.items():
                if (t==an or t==hn) and info['lg']==_lg:
                    _side='away' if t==an else 'home'
                    _isrc=_mlogo.get((_lg,t)) or ('https://a.espncdn.com/i/teamlogos/%s/500/%s.png'%(_LGMAP[_lg][1],info['abbr']) if _LGMAP[_lg][1] else '')
                    _fimg='<img src="%s" style="width:20px;height:20px;vertical-align:-4px;margin-right:7px" onerror="this.remove()">'%_isrc if _isrc else ''
                    _fw.append('<a href="futures.html?v={build_sha}" style="text-decoration:none;color:inherit"><div class="pick" data-espn="%s" data-eid="%s" data-away="%s" data-home="%s" data-side="%s">%s<b>%s</b> <span style="color:#8a8f98;font-size:12px">futures: %s</span><span class="ls" data-ls></span></div></a>'%(_LGMAP[_lg][0],ev['id'],html.escape(an),html.escape(hn),_side,_fimg,html.escape(t),' &middot; '.join(html.escape(x) for x in info['mkts'])))  # 12:31 core fix: futures-live rows bind their event id - rpLsTick's strict eid lane (J-101) hydrates them with the same live score/clock/quarter data as score rows; no eid = static row was the root defect
                    _fwgot.add(t)
                    break
        _fw2=[]
        _tola=_dt.datetime.now(_ZI('America/Los_Angeles')).date().isoformat()
        for _f in FUT:
            if _f.get('placed')!=_tola or _f.get('league') not in _LGMAP or not _f.get('abbr'): continue
            if _f['team'] in _fwgot: continue  # game-day card already carries them
            _fwgot.add(_f['team'])
            _isrc2='https://a.espncdn.com/i/teamlogos/%s/500/%s.png'%(_LGMAP[_f['league']][1],_f['abbr']) if _LGMAP[_f['league']][1] else ''
            _fimg2='<img src="%s" style="width:20px;height:20px;vertical-align:-4px;margin-right:7px" onerror="this.remove()">'%_isrc2 if _isrc2 else ''
            _lbl2='SB' if 'Super Bowl' in _f['market'] else (_f['market'][:-9] if _f['market'].endswith(' Champion') else _f['market'])
            _da2=(' data-espn="%s"'%_LGMAP[_f['league']][0]) if _V2 else ''
            _fw2.append('<a href="futures.html?v={build_sha}" style="text-decoration:none;color:inherit"><div class="pick"%s>%s<b>%s</b> <span style="color:#8a8f98;font-size:12px">new futures: %s &middot; %s</span></div></a>'%(_da2,_fimg2,html.escape(_f['team']),html.escape(_lbl2),html.escape(_f.get('odds',''))))
        fut_watch_html=('' if not _fw2 else '<div class="sect" style="margin-top:22px">New futures</div>'+''.join(_fw2))+('' if not _fw else '<div class="sect" style="margin-top:22px">Futures live today</div>'+''.join(_fw))
    except Exception:
        fut_watch_html=''
fut_badge_js=("try{\n"
"var rpFutSeen=JSON.parse(localStorage.getItem('rp_fut_seen')||'[]');\n"
"var rpFutIds="+json.dumps(fut_ids)+";\n"
"if(rpFutIds.some(function(i){return rpFutSeen.indexOf(i)<0;})){var nb=document.getElementById('rpFutNew');if(nb)nb.style.display='';}\n"
"}catch(e){}\n")
if man.get('parlay'):
    pl=man['parlay']
    def _leg_li(l):
        m=[p for p in man['picks'] if p['name'].lower() in l.lower() or l.lower() in p['name'].lower()]
        if not m: return f'<li>{html.escape(l)}</li>'
        p=m[0]; g=p.get('game') or {}
        inst=game_instance(g)
        if inst: l=l+' \u00b7 '+inst
        _gk3=_gpk_for(g.get('away',''),g.get('home',''),g.get('commence',''))
        if g.get('gpk'): _gk3=(str(g['gpk']),_gk3[1],_gk3[2])
        return ('<li class="cxleg" data-espn="%s" data-eid="%s" data-gpk="%s" data-aab="%s" data-hab="%s" data-away="%s" data-home="%s" data-commence="%s" data-side="%s"><a href="game-%s.html" style="display:block;color:inherit;text-decoration:none;margin:0 -8px;padding:2px 8px">%s<span class="ls" data-ls></span></a></li>'
                % (html.escape(p.get('espn_league','')), html.escape(str(g.get('eid') or '')), _gk3[0], _gk3[1], _gk3[2], html.escape(g.get('away','')), html.escape(g.get('home','')), html.escape(g.get('commence','')), html.escape(p.get('side','away')), p['num'], html.escape(l)))
    legs=''.join(_leg_li(l) for l in pl['legs'])
    # per-platform combo chips (his 9:08 AM directive): each chip carries the platform's combo
    # price and IS the build action - no separate build button. Verified prefill routes from the
    # manifest ('routes'); where none exists, chip is price-only and taps to the platform.
    def amer_from_cents(cl):
        c=1.0
        for x in cl: c*=x
        c=c/(100**(len(cl)-1))
        if not (0<c<100): return None
        return c
    def amer_from_mls(mls):
        d=1.0
        for ml in mls: d*=(1+ml/100.0) if ml>0 else (1+100.0/abs(ml))
        if d<=1.0: return None
        return (round((d-1)*100)) if d>=2 else (-round(100/(d-1)))
    lp=[p for p in man['picks'] if any(p['name'].lower() in l.lower() or l.lower() in p['name'].lower() for l in pl['legs'])]
    nlegs=len(pl['legs'])
    routes=pl.get('routes',{})
    chips=[]
    DKPM='https://predictions.draftkings.com/'
    try:
        lgs={p.get('espn_league') for p in lp}
        if len(lgs)==1 and None not in lgs: DKPM='https://predictions.draftkings.com/en/markets/'+lgs.pop()
    except Exception: pass
    if len(lp)==nlegs:
        # Inspector ruling (Sep 26): no KAL/POLY combo chips - the exchanges have no native
        # parlay product, and per-leg chips on each pick already route to the real markets.
        # A priced chip linking to a homepage/category page is a defect; dead-combo pricing dies at the root here.
        BKML=[('DK','draftkings',None),('FD','fanduel',None),('TSB','thescore',None),('HR','hardrockbet',None),('MGM','betmgm',None),('BR','betrivers',None)]  # DK pm: fail closed pending verified state list
        for short,pk,pm in BKML:
            mls=[]; ok=True
            for p in lp:
                side=p.get('side','away')
                pr=sel_books(pre.get((p['game']['away'],p['game']['home'])), p.get('game')) if p.get('game') else None
                if not pr: ok=False; break
                if pk in ('betmgm','betrivers'):
                    e=(pr.get('state_templates') or {}).get(pk) or {}
                else:
                    e=pr.get(pk) or {}
                v=e.get(f"{side}_ml")
                if v is None: ok=False; break
                mls.append(v)
            if not (ok and len(mls)==nlegs):
                # his 8:51 visibility directive: every book renders a combo chip; without full-leg
                # prices it's an unpriced inert reference, tappability still gated on verified routes.
                chips.append((short,f'<span class="chip%%BEST%% rpunpriced rpnontap"{bkstyle(short)} data-book="{short}" data-market="parlay"{_mkrec(short,"","parlay","",link="",ph=("last_pre_game" if any(_is_underway((pp.get("game") or {})) for pp in lp) else "pre_game"),lv="none",st="unknown")}>%%STAR%%{bkimg(short)}{short} \u2014</span>',None))
                continue
            r=routes.get(short) or {}
            price=r.get('price')
            if price is None: price=amer_from_mls(mls)
            if price is None:
                chips.append((short,f'<span class="chip%%BEST%% rpunpriced rpnontap"{bkstyle(short)} data-book="{short}" data-market="parlay"{_mkrec(short,"","parlay","",link="",ph=("last_pre_game" if any(_is_underway((pp.get("game") or {})) for pp in lp) else "pre_game"),lv="none",st="unknown")}>%%STAR%%{bkimg(short)}{short} \u2014</span>',None))
                continue
            # J-112 (inspector ruling, Sep 26): combined price ALWAYS renders; the chip is tappable
            # ONLY with a tap-verified executable/deepest-real destination. No verified route -> the
            # price stays and the chip is a non-tappable span under the * manual-build disclaimer.
            link=r.get('link') if r.get('verified') else None
            pmattr=f' data-pm="{pm}"' if pm else ''
            _cxph='last_pre_game' if any(_is_underway((pp.get('game') or {})) for pp in lp) else 'pre_game'
            if link:
                chips.append((short,f'<a class="chip%%BEST%%"{bkstyle(short)} href="{html.escape(link)}" data-book="{short}" data-market="parlay" data-sb="{html.escape(link)}"{pmattr}{_mkrec(short,"","parlay","",ml=price,link=link,ph=_cxph)} onclick="return rpRoute(event,this)" target="_blank" rel="noreferrer">%%STAR%%{bkimg(short)}{short} {price:+d}</a>',price))
            else:
                chips.append((short,f'<span class="chip%%BEST%% rpnontap"{bkstyle(short)} data-book="{short}" data-market="parlay"{pmattr}{_mkrec(short,"","parlay","",ml=price,link="",ph=_cxph,lv="none")}>%%STAR%%{bkimg(short)}{short} {price:+d}</span>',price))
        # combos get market chips in every state, exchanges included. No native exchange
        # parlay product exists, so the real combined price renders as an inert span (J-112), never a route.
        _kc=[]
        for p in lp:
            _v=(p.get('kalshi') or {}).get('cents')
            _pg=(p.get('game') or {})
            if _v is not None and _is_underway(_pg):
                # same-phase rule: an in-play leg contributes its pre-game snapshot, never a live quote
                _v=((SHIPPED.get(f"{_pg.get('away')}|{_pg.get('home')}|{((_pg.get('commence') or '') or '')[:10]}") or {}).get('Kalshi') or {}).get('cents') or _v
            _kc.append(_v)
        if len(_kc)==nlegs and all(isinstance(x,(int,float)) and 0<x<100 for x in _kc):
            _cc=amer_from_cents(_kc)
            if _cc:
                _lab=_re_scrub.search(r'\(\s*([+-]\d+)\s*\)', pl.get('label','') or '')
                _aml=_lab.group(1) if _lab else (('+'+str(_rh((100-_cc)/_cc*100))) if _cc<50 else ('-'+str(_rh(_cc/(100-_cc)*100))))  # manifest label American is canonical (main 7:44); fallback exact, never cents
                chips.append(('KAL',f'<span class="chip%%BEST%% rpnontap"{bkstyle("KAL")} id="rpCxKAL" data-n="{nlegs}" data-book="KAL" data-market="parlay" data-cents="{_rh(_cc)}"{_mkrec("Kalshi","","parlay","",cents=_cc,link="",ph=("last_pre_game" if any(_is_underway((pp.get("game") or {})) for pp in lp) else "pre_game"),lv="none")}>%%STAR%%{bkimg("KAL")}KAL {_aml}</span>',c2ml_int(_cc)))
        _pc=[]
        for p in lp:
            _v=None
            if p.get('polymarket'):
                _pg=(p.get('game') or {})
                _psk=f"{_pg.get('away')}|{_pg.get('home')}|{((_pg.get('commence') or '') or '')[:10]}"
                if _is_underway(_pg):
                    # same-phase rule: an in-play leg contributes its pre-game snapshot, never a live quote
                    _v=((SHIPPED.get(_psk) or {}).get('Polymarket') or {}).get('cents') or p.get('polycents')
                else:
                    try: _v=poly_price(p['polymarket']['url'],p['name'].split()[0]) or p.get('polycents')
                    except Exception: _v=p.get('polycents')
            _pc.append(_v)
        if len(_pc)==nlegs and all(isinstance(x,(int,float)) and 0<x<100 for x in _pc):
            _cp=amer_from_cents(_pc)
            if _cp:
                _aml=('+'+str(_rh((100-_cp)/_cp*100))) if _cp<50 else ('-'+str(_rh(_cp/(100-_cp)*100)))  # exact unrounded American, never cents (his all-+/- override)
                chips.append(('POLY',f'<span class="chip%%BEST%% rpnontap"{bkstyle("POLY")} id="rpCxPOLY" data-n="{nlegs}" data-book="POLY" data-market="parlay" data-cents="{_rh(_cp)}"{_mkrec("Polymarket","","parlay","",cents=_cp,link="",ph=("last_pre_game" if any(_is_underway((pp.get("game") or {})) for pp in lp) else "pre_game"),lv="none")}>%%STAR%%{bkimg("POLY")}POLY {_aml}</span>',c2ml_int(_cp)))
    order=['BR','DK','FD','HR','KAL','MGM','POLY','TSB']  # alphabetical by chip label (his Sep 25 9:19 AM spec; matches solo order)
    chips.sort(key=lambda s: order.index(s[0]) if s[0] in order else 99)
    # best combo price gets the star left of the logo, same as solo best line (user, Sep 25 12:59 PM)
    priced=[c for c in chips if len(c)>2 and isinstance(c[2],(int,float))]
    best_i=None
    if priced:  # star on the best DISPLAYED combo price - frozen prices in play included (inspector Sep 26)
        best_price=max(c[2] for c in priced)
        for i,c in enumerate(chips):
            if len(c)>2 and c[2]==best_price: best_i=i; break
    rendered=[]
    for i,c in enumerate(chips):
        h=c[1].replace('%%BEST%%',' best' if i==best_i else '').replace('%%STAR%%','\u2605 ' if i==best_i else '')
        rendered.append(h)
    pchip=f'<div class="chips" id="rpParlayChips" style="margin:10px 0">{"".join(rendered)}</div>' if chips else ''
    combo_nontap=any('rpnontap' in c[1] for c in chips)
    # his 9:10 AM carve-out: in states where combos can't legally be built, asterisk the title + one-line footnote
    parlay_html=(f'<div class="sect" id="rpParlayTitle">Parlay</div><ul class="legs">{legs}</ul><div class="note" id="rpCxLive" style="display:none;margin-top:6px"></div>{pchip}'
                 f'<div class="note" id="rpComboReg" style="display:none">* Due to regulations in your state, combos can\u2019t legally be built out for you and must be done manually.</div>'
                 f'<div class="note" id="rpParlayNote" style="display:none">{html.escape(pl.get("note",""))}</div>')

RP_STATES=[('AL','Alabama'),('AK','Alaska'),('AZ','Arizona'),('AR','Arkansas'),('CA','California'),('CO','Colorado'),('CT','Connecticut'),('DE','Delaware'),('DC','Washington D.C.'),('FL','Florida'),('GA','Georgia'),('HI','Hawaii'),('ID','Idaho'),('IL','Illinois'),('IN','Indiana'),('IA','Iowa'),('KS','Kansas'),('KY','Kentucky'),('LA','Louisiana'),('ME','Maine'),('MD','Maryland'),('MA','Massachusetts'),('MI','Michigan'),('MN','Minnesota'),('MS','Mississippi'),('MO','Missouri'),('MT','Montana'),('NE','Nebraska'),('NV','Nevada'),('NH','New Hampshire'),('NJ','New Jersey'),('NM','New Mexico'),('NY','New York'),('NC','North Carolina'),('ND','North Dakota'),('OH','Ohio'),('OK','Oklahoma'),('OR','Oregon'),('PA','Pennsylvania'),('PR','Puerto Rico'),('RI','Rhode Island'),('SC','South Carolina'),('SD','South Dakota'),('TN','Tennessee'),('TX','Texas'),('UT','Utah'),('VT','Vermont'),('VA','Virginia'),('WA','Washington'),('WV','West Virginia'),('WI','Wisconsin'),('WY','Wyoming')]
RP_FD=['AZ','AR','CO','CT','IL','IN','IA','KS','KY','LA','MD','MA','MI','MO','NJ','NY','NC','OH','PA','TN','VT','VA','WV','WY','DC','PR']
RP_DK=['AZ','AR','CO','CT','IL','IN','IA','KS','KY','LA','ME','MD','MA','MI','MO','NH','NJ','NY','NC','OH','OR','PA','TN','VT','VA','WV','WY','DC']
# U-GEO-002 core data: full 51-jurisdiction arm-level legality table (research task, as-of 2026-09-26; state-legality.json committed to RixPicksSystem). Mechanism consumes DATA - flips land as data edits, never code.
RP_LEGAL_ASOF='2026-09-26'
TABLE={"AK": ["KAL", "POLY", "DKP", "FDP"], "AL": ["KAL", "POLY", "DKP", "FDP"], "AR": ["DK", "FD", "KAL", "POLY"], "AZ": ["DK", "FD", "TSB", "HR", "MGM", "BR", "KAL"], "CA": ["KAL", "POLY", "DKP", "FDP"], "CO": ["DK", "FD", "TSB", "HR", "MGM", "BR", "KAL", "POLY"], "CT": ["DK", "FD", "KAL"], "DC": ["DK", "FD", "TSB", "MGM", "KAL", "POLY"], "DE": ["BR", "KAL", "POLY", "DKP", "FDP"], "FL": ["HR", "KAL", "POLY", "DKP", "FDP"], "GA": ["KAL", "POLY", "DKP", "FDP"], "HI": ["KAL", "POLY", "DKP", "FDP"], "IA": ["DK", "FD", "TSB", "MGM", "BR", "KAL", "POLY"], "ID": ["KAL", "POLY", "DKP", "FDP"], "IL": ["DK", "FD", "TSB", "HR", "MGM", "BR", "KAL", "POLY"], "IN": ["DK", "FD", "TSB", "HR", "MGM", "BR", "KAL", "POLY"], "KS": ["DK", "FD", "TSB", "MGM", "KAL", "POLY"], "KY": ["DK", "FD", "TSB", "MGM", "KAL", "POLY"], "LA": ["DK", "FD", "TSB", "MGM", "BR", "KAL", "POLY"], "MA": ["DK", "FD", "TSB", "MGM", "KAL", "POLY"], "MD": ["DK", "FD", "TSB", "MGM", "BR", "KAL"], "ME": ["DK", "KAL", "POLY"], "MI": ["DK", "FD", "TSB", "HR", "MGM", "BR"], "MN": ["KAL", "POLY", "DKP", "FDP"], "MO": ["DK", "FD", "TSB", "MGM", "KAL", "POLY"], "MS": ["MGM", "KAL", "POLY"], "MT": ["KAL", "POLY"], "NC": ["DK", "FD", "TSB", "MGM", "KAL", "POLY"], "ND": ["KAL", "POLY", "DKP", "FDP"], "NE": ["KAL", "POLY", "DKP", "FDP"], "NH": ["DK", "KAL", "POLY"], "NJ": ["DK", "FD", "TSB", "HR", "MGM", "BR", "KAL", "POLY"], "NM": ["KAL", "POLY", "DKP", "FDP"], "NV": ["MGM"], "NY": ["DK", "FD", "TSB", "MGM", "BR", "KAL", "POLY"], "OH": ["DK", "FD", "TSB", "HR", "MGM", "BR", "KAL", "POLY"], "OK": ["KAL", "POLY", "DKP", "FDP"], "OR": ["DK", "KAL", "POLY"], "PA": ["DK", "FD", "TSB", "MGM", "BR", "KAL", "POLY"], "RI": ["KAL", "POLY", "DKP", "FDP"], "SC": ["KAL", "POLY", "DKP", "FDP"], "SD": ["KAL", "POLY", "DKP", "FDP"], "TN": ["DK", "FD", "TSB", "HR", "MGM", "KAL"], "TX": ["KAL", "POLY", "DKP", "FDP"], "UT": ["DKP", "FDP"], "VA": ["DK", "FD", "TSB", "HR", "MGM", "BR", "KAL", "POLY"], "VT": ["DK", "FD", "KAL", "POLY"], "WA": ["POLY"], "WI": ["KAL", "POLY"], "WV": ["DK", "FD", "TSB", "MGM", "BR", "KAL", "POLY"], "WY": ["DK", "FD", "MGM", "KAL", "POLY"]}  # U-GEO-002 core data: state-legality.json (as-of 2026-09-26, RixPicksSystem); construction = status in licensed_live/limited/live/live_contested/blocked_imminent (rule 3: blocked_imminent stays SHOWN until geoblock confirms): state-legality.json (as-of 2026-09-26, RixPicksSystem) baked at build time
RP_LEGAL_STATE=TABLE
RP_LEGAL_BI_DATA={'OH':['KAL'],'TN':['KAL']}  # blocked_imminent in-data flags (shown with caveat until geoblock confirms) - from state-legality.json blocked_imminent_flag
# arms present in the table with no chip feed yet: TSB (theScore Bet - ESPN BET is DEAD, PENN terminated Nov 2025; chip + feed mapping land when a verified theScore source exists). B365/FAN not in the researched table -> fail closed (never render).
RP_MGM=['AZ','CO','DC','IL','IN','IA','KS','KY','LA','MA','MD','MI','MS','NJ','NV','NY','NC','OH','PA','TN','VA','WV','WY']
RP_B365=['AZ','CO','IL','IN','IA','KS','KY','LA','NJ','NC','OH','PA','TN','VA']
RP_FAN=['AZ','CO','CT','DC','IL','IN','IA','KS','KY','LA','MA','MD','MI','NC','NJ','NY','OH','PA','TN','VT','VA','WV','WY']
RP_TSB=['AZ','CO','DC','IL','IN','IA','KS','KY','LA','MA','MD','MI','MO','NJ','NY','NC','OH','PA','TN','VA','WV']  # theScore Bet 20 states + DC (U-GEO-003)
RP_HR=['AZ','CO','FL','IL','IN','MI','NJ','OH','TN','VA']
RP_BR=['AZ','CO','CT','DE','DC','IL','IN','IA','KS','KY','LA','ME','MD','MA','MI','NH','NJ','NY','NC','OH','OR','PA','RI','TN','VT','VA','WV','WY']

# --- shell: v2 dark redesign when RP_V2=1; otherwise the locked v1.2.0 markup, byte-for-byte.
# 9/27 (Julian/Dardan): the Yesterday strip is PER-LEAGUE - a tab shows only its own league's
# results, from manifest yesterday_by_league {tab_key: "3-0 - ..."}. No entry for a tab = strip
# hidden (never fabricate, never show another league's results). Legacy aggregate
# man['yesterday'] stays data-only; v2 never renders it globally.
_yestr=''
_YBL=man.get('yesterday_by_league') or {}
def _ystr_for(_tab):
    _s=_YBL.get(_tab)
    return ('<a class="yesrec" href="yesterday.html" style="display:block;text-decoration:none;color:inherit">Yesterday: '+html.escape(_s)+'</a>') if _s else ''
_units_line=(f'<div class="yesrec unitspl" id="rpUnits" data-bu="{html.escape(re.sub(r"[^0-9.+-]","",man["units_pl"]))}">Units: {html.escape(man["units_pl"])}</div>' if man.get('units_pl') else '')
_rw,_rl=man['record'].split('-')[0],man['record'].split('-')[1]
_navpct=''
try:
    _w0,_l0=int(_rw),int(_rl)
    if _w0+_l0>0: _navpct='<span>W/L <b id="rpNavPct">'+('%.2f'%(100.0*_w0/(_w0+_l0)))+'%</b></span>'
except Exception: _navpct=''
_tail_html=('<a class="rec" id="rpRec" data-bw="'+html.escape(str(_rw))+'" data-bl="'+html.escape(str(_rl))+'" href="record.html" style="display:block;text-decoration:none;color:inherit;margin-top:26px">&rsquo;RixPicks Overall Record: '+html.escape(man['record'])+'</a>\n'
    +wl_pct_line(man['record'])+'\n'+_units_line+'\n'
    '<div class="unitmath">1u = $5 per $1,000 in bankroll</div>\n'
    '<div class="foot">Bet responsibly. <span class="rpstate-link" id="rpStateLabel" onclick="rpEdit()">Share/update location</span></div>')
if _V2:
    INDEX_V2_CSS=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'index_v2.css')).read()
    INDEX_V2_JS=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'index_v2.js')).read()
    def _tab_of_lg(lg):
        if lg=='football/college-football': return ('ncaaf','NCAAF',lg)
        if lg=='football/nfl': return ('nfl','NFL',lg)
        if lg=='baseball/mlb': return ('mlb','MLB',lg)
        if lg=='basketball/nba': return ('nba','NBA',lg)
        if lg in ('tennis','tennis/atp','tennis/wta'): return ('tennis','Tennis',lg)
        if lg=='basketball/mens-college-basketball': return ('ncaab','NCAAB',lg)
        if lg=='basketball/wnba': return ('wnba','WNBA',lg)
        if lg=='hockey/nhl': return ('nhl','NHL',lg)
        if lg=='soccer/usa.1': return ('mls','MLS',lg)
        if lg=='soccer/usa.nwsl': return ('nwsl','NWSL',lg)
        if lg=='golf/pga': return ('pga','PGA',lg)
        if lg in ('racing/nascar-premier','racing/nascar'): return ('nascar','NASCAR',lg)
        if lg in ('mma/ufc','boxing'): return ('ufcboxing','UFC/Boxing',lg)
        lbl=LG_LABEL.get(lg) or (lg.split('/')[-1].replace('-',' ').title() if lg else 'Other')
        return (re.sub(r'[^a-z0-9]','',lbl.lower()) or 'other', lbl, lg)
    # 9/27 9:40:49 (Dardan, verbatim): "Only have leagues show up that have picks for the
    # day." NO hardcoded always-on tabs - a league's tab renders only when it has a pick on
    # today's card (its row header in _row_lgs appends it below). No pick = tab hidden.
    # Supersedes the 9:40 all-13-always-show direction (reversed one minute later).
    _CANON_TABS=[]
    _panels={}
    for _lg,_h in zip(_row_lgs,rows):
        _k,_lbl,_esp=_tab_of_lg(_lg)
        _panels.setdefault(_k,[]).append(_h)
    RP_TABS=[{'key':k,'label':l,'espn':e} for k,l,e in _CANON_TABS]
    _canon_keys=[t['key'] for t in RP_TABS]
    for _lg,_h in zip(_row_lgs,rows):
        _k,_lbl,_esp=_tab_of_lg(_lg)
        if _k not in _canon_keys and not any(t['key']==_k for t in RP_TABS):
            RP_TABS.append({'key':_k,'label':_lbl,'espn':_esp})
    # futures/watch data-espn no longer appends nav tabs (9:40:49 rule: picks only) -
    # futures/combo content renders globally in <main>, never tab-scoped, so nothing orphans.
    # Julian 12:38 (his design decision via main, supersedes 9:40:49 for these two only):
    # CFB and NBA tabs are ALWAYS visible, desktop+mobile, even on no-pick days - the
    # standard empty state renders instead of hiding. Canonical slots: CFB right after
    # NFL (else first), NBA right after CFB. Every other league keeps the picks-only rule.
    def _ensure_tab(_lg,_after):
        _k,_lbl,_esp=_tab_of_lg(_lg)
        if any(t['key']==_k for t in RP_TABS): return
        _t={'key':_k,'label':_lbl,'espn':_esp}
        for _i,_x in enumerate(RP_TABS):
            if _x['key']==_after: RP_TABS.insert(_i+1,_t); return
        RP_TABS.insert(0,_t)
    _ensure_tab('football/college-football','nfl')
    _ensure_tab('basketball/nba','ncaaf')
    _cxesp=','.join(sorted(set(re.findall(r'data-espn="([^"]+)"',parlay_html))))
    _combo_wrap=('<div id="rpComboTail" data-cx-espn="'+_cxesp+'">'+parlay_html+'</div>') if parlay_html else ''
    _fut_wrap=('<div id="rpFutTail">'+fut_watch_html+'</div>') if fut_watch_html else ''
    # Wooder Ice guest tab (Julian 12:25 design-approved via main, scope settled 12:25:40): ALL Wooder NFL
    # guest content moves here from the NFL tab (slate+countdown, combos, tickets, Kincaid update, builders).
    # Shared data: same slates/*.json hydration, no divergent state. Dingers stays on the MLB tab.
    RP_TABS.append({'key':'wooder','label':'Picks from Wooder Ice','espn':''})

    RP_TABS.append({'key':'past','label':'Past Tickets','espn':''})
    # Past Tickets archive (Julian 1:33 spec via main, Dardan full-control): completed/removed picks
    # and tickets with All/Won/Lost filters. Original selection, result, provenance preserved -
    # nothing deleted, just moved. BOUGHT stays visually distinct from SUGGESTED forever; voids render
    # as their own state, never forced Won/Lost; no settlement/payout implications. Client-hydrated
    # from slates/past_tickets.json; honest empty/unavailable states, nothing invented.
    past_entry=(
    r'<div style="margin-top:6px">'
    r'<div class="sect">Past Tickets</div>'
    r'<div class="sub" style="margin-bottom:10px">Archive of completed and removed Wooder Ice picks and tickets. Original selection, result and provenance preserved - nothing is deleted, just moved. No settlement or payout implications.</div>'
    r'<div id="rpPastBar" style="display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap"></div>'
    r'<div id="rpPastBox"></div>'
    r'</div>'
    r'<script>(function(){'
    r'var box=document.getElementById("rpPastBox"),bar=document.getElementById("rpPastBar");if(!box||!bar)return;'
    r'function esc(s){var M={"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"};return String(s==null?"":s).replace(/[&<>"]/g,function(c){return M[c];});}'
    r'var ALL=[],FILT="all";'
    r'function badge(e){if(e.origin==="bought")return "<span style=\"display:inline-block;background:#0b6e5f;color:#fff;border-radius:8px;font-size:10px;font-weight:700;letter-spacing:.06em;padding:1px 7px;margin-left:8px;vertical-align:2px\">BOUGHT TICKET</span>";if(e.origin==="suggested")return "<span style=\"display:inline-block;border:1px solid rgba(127,127,127,.4);color:#8a8f98;border-radius:8px;font-size:10px;font-weight:700;letter-spacing:.06em;padding:1px 7px;margin-left:8px;vertical-align:2px\">SUGGESTED</span>";return "";}'
    r'function rbadge(r){r=(r||"").toLowerCase();if(r==="won")return "<b style=\"color:#0b6e5f\">WON</b>";if(r==="lost")return "<b style=\"color:#e5484d\">LOST</b>";if(r==="void")return "<b style=\"color:#8a8f98\">VOID</b>";return "<b style=\"color:#8a8f98\">"+esc(r.toUpperCase())+"</b>";}'
    r'function draw(){'
    r'var es=ALL.filter(function(e){return FILT==="all"||((e.result||"").toLowerCase()===FILT);});'
    r'var h="";'
    r'es.forEach(function(e){'
    r'var legs=(e.legs||[]).map(function(l){'
    r'var st=(l.status||"").toLowerCase();'
    r'var dot=st==="won"?"#0b6e5f":(st==="lost"?"#e5484d":(st?"#8a8f98":""));'
    r'var dt=dot?("<span style=\"display:inline-block;width:7px;height:7px;border-radius:50%;background:"+dot+";margin-right:6px;vertical-align:1px\"></span>"):"";'
    r'return "<div style=\"font-size:13px;padding:3px 0\">"+dt+"<b>"+esc(l.player)+"</b>"+(l.market?(" <span style=\"color:#8a8f98\">"+esc(l.market)+"</span>"):"")+(l.matchup?(" <span style=\"color:#8a8f98\">&middot; "+esc(l.matchup)+"</span>"):"")+(l.time?(" <span style=\"color:#8a8f98\">&middot; "+esc(l.time)+"</span>"):"")+"</div>";'
    r'}).join("");'
    r'h+="<div style=\"border:1px solid rgba(127,127,127,.22);border-radius:12px;padding:11px 12px;margin-bottom:10px\">"'
    r'+"<div style=\"display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:4px\"><span style=\"min-width:0\"><b>"+esc(e.title)+"</b>"+badge(e)+"</span><span style=\"flex:0 0 auto;margin-left:auto;padding-left:8px\">"+rbadge(e.result)+"</span></div>"'
    r'+(e.detail?("<div style=\"font-size:12px;color:#8a8f98;margin-top:2px\">"+esc(e.detail)+"</div>"):"")'
    r'+(legs?("<div style=\"margin-top:6px\">"+legs+"</div>"):"")'
    r'+"<div style=\"font-size:11px;color:#8a8f98;margin-top:8px\">Removed "+esc(e.removed_label||e.archived_at||"")+" &middot; "+esc(e.reason||"")+"</div>"'
    r'+(e.provenance?("<div style=\"font-size:11px;color:#8a8f98;opacity:.8;margin-top:2px\">Source: "+esc(e.provenance)+"</div>"):"")'
    r'+"</div>";});'
    r'box.innerHTML=h||"<div class=\"sub\">Nothing archived in this view yet.</div>";}'
    r'function barDraw(){'
    r'var n={all:ALL.length,won:0,lost:0,void:0};'
    r'ALL.forEach(function(e){var r=(e.result||"").toLowerCase();if(n[r]!=null)n[r]++;});'
    r'var defs=[["all","All"],["won","Won"],["lost","Lost"],["void","Void"]];'
    r'bar.innerHTML=defs.map(function(d){'
    r'var on=FILT===d[0];'
    r'return "<a href=\"#past\" data-f=\""+d[0]+"\" style=\"text-decoration:none;font-size:12px;font-weight:700;padding:4px 12px;border-radius:999px;border:1px solid "+(on?"#0b6e5f":"rgba(127,127,127,.35)")+";color:"+(on?"#0b6e5f":"#8a8f98")+"\">"+d[1]+" "+n[d[0]]+"</a>";'
    r'}).join("");'
    r'Array.prototype.forEach.call(bar.querySelectorAll("a"),function(a){a.onclick=function(ev){ev.preventDefault();FILT=a.getAttribute("data-f");barDraw();draw();};});}'
    r'fetch("slates/past_tickets.json?cb="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){ALL=(j&&j.entries)||[];barDraw();draw();}).catch(function(){box.innerHTML="<div class=\"sub\">Archive unavailable right now.</div>";});'
    r'})();</script>')
    _tabs_html=''.join('<a class="tab" data-tab="'+t['key']+'" href="#'+t['key']+'">'+html.escape(t['label'])+'</a>' for t in RP_TABS)
    _panels_html=''

    # --- Dingers Only (main 9:33 contract): Wooder Ice MLB daily HR picks, MLB tab ONLY.
    # Client-hydrated from slates/wooder_dingers.json; hides on missing/empty/wrong-date file,
    # drops invalid picks/links silently, never renders invented prices. Contract-pinned venue map.
    # Contract venues (KAL/POLY/DKP) accept "cents" or "american"; sportsbook venues take
    # "american" ONLY (native book odds - a sportsbook line can never be derived from a
    # contract quote). Both present on one link = REJECT the link. No price field = chip
    # renders without a price (allowed, pinned).
    _DING_VENUES={'KAL':('kalshi.com','#e6f9f3','#0a7c5c',1),'POLY':('polymarket.com','#e8f3fc','#1a6db0',1),
     'DK':('sportsbook.draftkings.com','#0b0e11','#53d337',0),'DKP':('predictions.draftkings.com','#0b1a0e','#9be25f',1),
     'FD':('sportsbook.fanduel.com','#e7f3ff','#0e6fd0',0),'MGM':('betmgm.com','#f5f0e4','#7a6226',0),
     'BR':('betrivers.com','#e3f5fc','#0278a6',0),'HR':('hardrock.bet','#faf3dd','#8a6d1a',0),
     'TSB':('thescore.bet','#0d1b2e','#4d94ff',0),'B365':('bet365.com','#f0f6f0','#1c6e3c',0),'FAN':('sportsbook.fanatics.com','#f3f3f3','#111',0)}
    mlb_entry=(
    r'<div style="margin-top:22px">'
    r'<div class="sect">Wooder Ice<span style="display:inline-block;background:#0b6e5f;color:#fff;border-radius:8px;font-size:10px;font-weight:700;letter-spacing:.06em;padding:1px 7px;margin-left:8px;vertical-align:2px">GUEST</span></div>'
    r'<div style="border:1px solid rgba(11,110,95,.45);border-radius:12px;padding:11px 12px">'
    r'<div class="lghead" style="margin-top:0">Dingers Only &#128293;</div>'
    r'<div class="sub" style="margin-bottom:8px">Separate from the RixPicks card and record. Picks only, no wagers placed.</div>'
    r'<div id="rpDing"></div>'
    r'</div></div>'
    r'<script>(function(){'
    r'var box=document.getElementById("rpDing");if(!box)return;'
    r'var VEN={};'
    r'function esc(s){var M={"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"};return String(s==null?"":s).replace(/[&<>"]/g,function(c){return M[c];});}'
    r'function c2ml(c){c=+c;return c>=50?-Math.round(c/(100-c)*100):Math.round((100-c)/c*100);}'
    r'function ptDate(){try{return new Date().toLocaleDateString("en-CA",{timeZone:"America/Los_Angeles"});}catch(e){var d=new Date();return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0");}}'
    # swarm 9:49: third parent from #rpDing is .state#st-mlb (whole panel incl. official picks).
    # Hide ONLY the enclosing Wooder guest module (margin-top wrapper = two parents up).
    r'function hide(){box.parentNode.parentNode.style.display="none";}'
r"""function dot(c){return "<span style=\"display:inline-block;width:7px;height:7px;border-radius:50%;background:"+c+";margin-right:6px;vertical-align:1px\"></span>";}"""
r"""function ab2(m){var N={CWS:"CHW"};var p=String(m||"").toUpperCase().split(" AT ");if(p.length!==2)return null;var a=p[0].trim(),b=p[1].trim();return [N[a]||a,N[b]||b];}"""
r"""function hrOf(sj,name){try{var tms=(sj.boxscore&&sj.boxscore.players)||[];for(var t=0;t<tms.length;t++){var sts=tms[t].statistics||[];for(var q=0;q<sts.length;q++){var keys=sts[q].keys||[];if(keys.indexOf("atBats")<0)continue;var hi=keys.indexOf("homeRuns");if(hi<0)hi=keys.indexOf("HR");if(hi<0)continue;var aths=sts[q].athletes||[];for(var a=0;a<aths.length;a++){if((((aths[a].athlete||{}).displayName)||"").toLowerCase()===String(name||"").toLowerCase()){var v=parseInt((aths[a].stats||[])[hi],10);return isNaN(v)?0:v;}}}}}catch(e){}return null;}"""
r"""function tS(count,state,det){var cur=(count==null?0:count);var got=(count!=null&&count>0);var txt=got?("HR"+(cur>1?(" x"+cur):"")):"No HR yet";var badge=got?("<b style=\"color:#0b6e5f\">"+txt+" &#10003;</b>"):null;if(state==="post")return got?(dot("#0b6e5f")+badge+"<span style=\"color:#8a8f98\"> &middot; Final</span>"):(dot("#8a8f98")+"<span style=\"color:#8a8f98\">No HR &middot; Final</span>");if(got)return dot("#0b6e5f")+badge;var dly=/delay|postpon|suspend/i.test(det||"");if(state==="in")return dly?(dot("#e8a13d")+"<span style=\"color:#b07708\">"+txt+" &middot; Delayed</span>"):(dot("#e8a13d")+"<span style=\"color:#b07708\">"+txt+"</span>");if(dly)return dot("#8a8f98")+"<span style=\"color:#8a8f98\">Delayed</span>";return dot("#8a8f98")+"<span style=\"color:#8a8f98\">Game not started</span>";}"""
r"""function updDing(){fetch("https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard?cb="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(sb){var gm={};(sb.events||[]).forEach(function(ev){var cmp=(ev.competitions||[])[0]||{};var st=(cmp.status&&cmp.status.type)||{};var home=null,away=null;(cmp.competitors||[]).forEach(function(c){var o={ab:((c.team||{}).abbreviation||"").toUpperCase()};if(c.homeAway==="home")home=o;else away=o;});if(home&&away)gm[away.ab+"@"+home.ab]={state:st.state||"",eid:ev.id,det:(st.detail||st.shortDetail||"")};});var seen={};Array.prototype.forEach.call(document.querySelectorAll(".rpdingtrk"),function(el){var pr=ab2(el.getAttribute("data-m"));var g=pr?gm[pr[0]+"@"+pr[1]]:null;if(!g){el.innerHTML="";return;}el.__st=g.state;el.__det=g.det;if(g.eid&&g.state!=="pre"){(seen[g.eid]=seen[g.eid]||[]).push(el);}else{el.innerHTML=tS(null,g.state,g.det);}});Object.keys(seen).forEach(function(eid){fetch("https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/summary?event="+eid+"&cb="+Date.now(),{cache:"no-store"}).then(function(r){return r.ok?r.json():null;}).then(function(sj){if(!sj)return;seen[eid].forEach(function(el){el.innerHTML=tS(hrOf(sj,el.getAttribute("data-p")),el.__st,el.__det);});}).catch(function(){});});}).catch(function(){});}"""
r"""function startDing(){updDing();setInterval(updDing,30000);}"""
r'fetch("slates/wooder_dingers.json?cb="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){'
    r'var ps=(j&&j.picks)||[];'
    r'if(!ps.length||(j.date||"")!==ptDate()){hide();return;}'
    r'var h="";'
    r'ps.slice(0,10).forEach(function(pk,i){'
    r'if(!pk.player||!pk.team||!pk.matchup||!pk.time||!pk.market)return;'
    r'var chips="";'
    r'(pk.links||[]).forEach(function(l){'
    r'var v=VEN[l.venue];if(!v)return;'
    r'if(l.url!=null&&l.url.indexOf(v[0])===-1)return;'
    r'if(l.american!=null&&l.cents!=null)return;'
    r'var pr="";'
    r'if(l.american!=null)pr=String(l.american);'
    r'else if(l.cents!=null){if(!v[3])return;if(typeof l.cents==="number"&&l.cents>0&&l.cents<100)pr=(c2ml(l.cents)>0?"+":"")+c2ml(l.cents);}'
    # 9:43 owner rule: exact market page or NOTHING - url:null renders an unlinked chip (venue label only), never a wrong-target link.
    r'var st="background:"+v[1]+";border-color:"+v[1]+";color:"+v[2]+";font-size:11px;padding:2px 10px";'
    r'chips+=l.url?(" <a class=\"chip\" style=\""+st+"\" href=\""+esc(l.url)+"\" target=\"_blank\" rel=\"noreferrer\">"+esc(l.venue)+(pr?" "+esc(pr):"")+"</a>"):(" <span class=\"chip\" style=\""+st+"\">"+esc(l.venue)+(pr?" "+esc(pr):"")+"</span>");});'
    r'if(!chips)return;'
    r'h+="<div class=\"rpnpick\"><div style=\"display:flex;justify-content:space-between;align-items:baseline\"><b>"+(i+1)+". "+esc(pk.player)+"</b><span style=\"color:#8a8f98;font-size:12px\">"+esc(pk.market)+"</span></div>"'
    r'+"<div style=\"font-size:12px;color:#8a8f98;margin-top:2px\">"+esc(pk.matchup)+" &middot; "+esc(pk.time)+"</div><div class=\"rpdingtrk\" data-p=\""+esc(pk.player)+"\" data-m=\""+esc(pk.matchup)+"\" style=\"margin-top:3px;font-size:12px\"></div>"'
    r'+"<div style=\"margin-top:4px\">"+chips+"</div></div>";});'
    r'if(!h){hide();return;}'
    r'box.innerHTML=h;startDing();'
    r'}).catch(hide);'
    r'})();</script>')
    mlb_entry=mlb_entry.replace('var VEN={};','var VEN='+json.dumps({k:[v[0],v[1],v[2],v[3]] for k,v in _DING_VENUES.items()},separators=(',',':'))+';')

    for t in RP_TABS:
        _prows=''.join(_panels.get(t['key']) or [])
        _body=(_prows if t['key']=='nfl' else ((nfl_entry if t['key']=='wooder' else (past_entry if t['key']=='past' else ((_prows+mlb_entry) if t['key']=='mlb' else ((_prows+wnba_entry) if t['key']=='wnba' else _prows))))))
        _body=_ystr_for(t['key'])+_body
        if not _body.strip():
            _body='<div class="pick rp-empty"><div class="pick-head"><span class="name">No picks today</span></div></div>'
        elif _prows.strip():
            _body='<div class="sect" style="margin-top:2px">Today&rsquo;s picks</div>'+_body
        _panels_html+='<div class="state" id="st-'+t['key']+'">'+_body+'</div>\n'
    _navu=(f'<span>Units <b id="rpNavU">{html.escape(man["units_pl"])}</b></span>' if man.get('units_pl') else '')
    _SHELL=('<section id="rpIntro" aria-label="welcome"><div class="wm"><span class="rx">&rsquo;</span><span>R</span><span>i</span><span>x</span><span>P</span><span>i</span><span>c</span><span>k</span><span>s</span></div><div class="scrolldn">Scroll</div></section>\n'
    '<nav class="rpnav"><a class="logo" href="index.html"><em>&rsquo;</em>RixPicks</a><button id="burger" aria-label="menu"><span></span><span></span><span></span></button><div class="tabs">'+_tabs_html+'</div><div class="rec"><span>Record <b><span id="rpNavRecW">'+html.escape(str(_rw))+'</span>-<span id="rpNavRecL">'+html.escape(str(_rl))+'</span></b></span>'+_navpct+_navu+'</div></nav>\n'
    '<div class="layout"><main><div class="rpdate">'+html.escape(man['date_label'])+'</div>\n<div class="intro">Tap any book under a pick to open that game there. Best line is highlighted.</div>\n'+_yestr+'\n'+_panels_html+_combo_wrap+'\n'+_fut_wrap+'\n'+fut_entry+'\n'+_tail_html+'</main>'
    '<aside><div class="col-head"><div class="sect">Games</div><span class="sub" id="rpAsideSub"></span></div><div class="card" id="rpGames"></div><div class="col-head" style="margin-top:18px"><div class="sect">News</div></div><div class="card" id="rpNews"></div></aside></div>\n'
    '<div class="tickbar" id="rpTickBar"><div class="ticktrack" id="rpTickTrack"></div></div>')
    _V2_ASSETS='<style>'+INDEX_V2_CSS+'</style>'
    _kal_watch=[]
    if os.environ.get('RP_KAL_TICKER')=='1':
        for _p in man.get('picks',[]):
            _k=_p.get('kalshi') or {}
            _u=(_k.get('url') or '').rstrip('/')
            _g=_p.get('game') or {}
            _lg=_p.get('espn_league') or ''
            if not (_u and _g.get('eid') and _lg and isinstance(_k.get('cents'),(int,float))): continue
            _awa=(_meta_for(_lg,_g.get('away','')).get('abbr') or '').upper()
            _hom=(_meta_for(_lg,_g.get('home','')).get('abbr') or '').upper()
            _kt=_k.get('team','') or ''
            _sfx=(_meta_for(_lg,_kt).get('abbr') or _meta_for(_lg,_kt.rstrip('.')).get('abbr') or '').upper()
            if not _sfx:
                _ktn=_kt.rstrip('.').lower()
                if _ktn and _ktn in (_g.get('away','') or '').lower(): _sfx=_awa
                elif _ktn and _ktn in (_g.get('home','') or '').lower(): _sfx=_hom
            if not (_awa and _hom and _sfx): continue
            _kal_watch.append({'eid':_g['eid'],'lg':_lg,'ev':_u.split('/')[-1].upper(),'entry':_k['cents'],'sfx':_sfx,'awa':_awa,'hom':_hom})
    _V2_SCRIPTS='<script>window.RP_TABS='+json.dumps(RP_TABS,separators=(',',':'))+';window.RP_KAL_TICKER='+(str(len(_kal_watch)) if os.environ.get('RP_KAL_TICKER')=='1' else '0')+';window.RP_KAL_WATCH='+json.dumps(_kal_watch,separators=(',',':'))+';</script><script>'+INDEX_V2_JS+'</script>'
else:
    _SHELL=('<h1><a href="index.html"><span class="tick">&rsquo;</span>RixPicks</a></h1>\n'
    f'<div class="status">{html.escape(man["date_label"])}</div>\n'
    '<div class="intro">Tap any book under a pick to open that game there. Best line is highlighted.</div>\n'
    +_yestr+'\n'
    '<div class="sect">Today&rsquo;s picks</div>\n'
    +chr(10).join(rows)+'\n'
    +parlay_html+'\n'+fut_watch_html+'\n'+nfl_entry+'\n'+fut_entry+'\n'+_tail_html)
    _V2_ASSETS=''
    _V2_SCRIPTS=''
page=f'''<!DOCTYPE html>
<!-- 'RixPicks design system v{RP_DESIGN} - LOCKED (user, Sep 24 2026). Daily builds change picks content only. -->
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>&rsquo;RixPicks</title>
<link rel="icon" href="favicon.ico?v={{build_sha}}" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="favicon-32.png?v={{build_sha}}">
<link rel="apple-touch-icon" href="apple-touch-icon.png?v={{build_sha}}">
<link rel="manifest" href="site.webmanifest?v={{build_sha}}">
<script src="https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.page.js" defer></script>
<script>window.OneSignalDeferred=window.OneSignalDeferred||[];OneSignalDeferred.push(async function(OneSignal){{try{{await OneSignal.init({{appId:"5e86ebe3-a135-4984-9623-db83a0f1840c",serviceWorkerPath:"OneSignalSDKWorker.js",serviceWorkerParam:{{scope:(location.pathname.indexOf("/rixpicks/")===0?"/rixpicks/":"/")}}  /* Sep 26: SW scope must match the ORIGIN's path root - rix-picks.com serves at /, github.io at /rixpicks/; a hardcoded /rixpicks/ scope makes subscriptions impossible on the custom domain */}});try{{OneSignal.Notifications.addEventListener("permissionChange",function(granted){{if(granted&&!localStorage.getItem("rp_gc_push")){{rpGcEvent("new-user-push","rp_gc_push");}}}});}}catch(e){{}}}}catch(e){{}}}});</script>
<script>{ARB_INJECT}</script>
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="RixPicks">
<meta name="theme-color" content="#000000">
<meta property="og:type" content="website">
<meta property="og:url" content="https://rix-picks.com/">
<meta property="og:title" content="&rsquo;RixPicks">
<meta property="og:description" content="Free picks, live tracked, every league in one place. Built in public - the record is never edited.">
<meta property="og:image" content="https://rix-picks.com/og-card.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="&rsquo;RixPicks">
<meta name="twitter:description" content="Free picks, live tracked, every league in one place. Built in public - the record is never edited.">
<meta name="twitter:image" content="https://rix-picks.com/og-card.png">
<meta name="description" content="&rsquo;RixPicks picks of the day. Tap any book under a pick to open that game there.">
<style>
*{{margin:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background:#f7f6f4;color:#1b1b1f;min-height:100vh;overscroll-behavior-y:contain}}
.wrap{{max-width:680px;margin:0 auto;padding:28px 18px 60px}}
h1{{font-size:26px;font-weight:800;letter-spacing:-0.01em}}
h1 .tick{{color:#3BEBF5}}
.status{{color:#6b6b72;font-size:14px;margin-top:6px}}
.intro{{color:#6b6b72;font-size:14px;margin-top:2px}}
.yesrec+.sect{{margin-top:6px}}.sect+.lghead{{margin-top:6px}}
.lghead span{{font-family:'Apple Color Emoji','Segoe UI Emoji','Noto Color Emoji',sans-serif}}.sect{{margin:16px 0 4px;font-size:13px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#6b6b72}}
.pick{{padding:18px 0;border-top:1px solid #e4e2de}}
.pick:first-of-type{{border-top:none}}
.pick-head{{display:flex;align-items:center;gap:10px}}.gamelink{{flex:1;min-width:0}}.meta-grp{{display:inline-flex;align-items:center;gap:8px;flex:none}}.rpmetalink{{display:inline-flex;flex-direction:column;align-items:flex-end;gap:2px;text-decoration:none;color:inherit}}.uo{{display:inline-flex;align-items:center;gap:8px}}.oddslock{{font-size:10px;letter-spacing:.4px;color:#8a8f98;text-transform:uppercase;white-space:nowrap}}.rpchatlink{{display:inline-flex;align-items:center;gap:3px;text-decoration:none;color:#8a8f98;font-size:11px;line-height:1;margin-left:-2px}}
.gamelink{{display:flex;align-items:center;gap:10px;flex:1;color:inherit;text-decoration:none;min-width:0}}
.chev{{color:#55555c;text-decoration:none}}
.mrow{{display:flex;align-items:center;gap:10px;padding:10px 0;border-top:1px solid #e4e2de;font-size:14px}}
.mrow:first-of-type{{border-top:none}}
.mrow .bk{{font-weight:700;width:52px;flex:none}}
.mrow .side{{flex:1;min-width:0}}
.mrow .pr{{font-weight:600;color:#2f8f7d;white-space:nowrap}}
.mrow a{{color:inherit;text-decoration:none}}
.back{{color:#6b6b72;font-size:14px;text-decoration:none}}
.score{{font-size:14px;color:#6b6b72;margin-top:4px}}
@media (prefers-color-scheme: dark){{.chev{{color:#55555c}}.mrow{{border-top-color:#2a2a2e}}.mrow .pr{{color:#3aa895}}.back,.score{{color:#9a9aa3}}}}
.num{{color:#6b6b72}}
.name{{font-weight:600;font-size:17px;flex:1}}
.odds{{color:#2f8f7d;font-weight:600;white-space:nowrap;line-height:1}}
.sub{{color:#6b6b72;font-size:14px;margin:6px 0 12px}}
.chips{{display:flex;flex-wrap:wrap;gap:8px}}
.chip{{display:inline-flex;align-items:center;gap:6px;min-height:36px;padding:6px 12px;border-radius:999px;border:none;color:#1b1b1f;text-decoration:none;font-size:13px;font-weight:600;background:#fff}}
.chip.rpunpriced{{opacity:.45}}  /* watchdog Sep 26: explicit unpriced state - dimmed, em-dash, inert */
.bklogo{{width:16px;height:16px;border-radius:3px;flex:none}}
.chip.best{{font-weight:800}}
.rec{{font-weight:600;font-size:16px;padding:8px 0 1px}}
.units{{color:#8a8f98;font-size:13px;font-weight:600;line-height:1}}
.rpstart{{color:#8a8f98;font-size:12px;font-weight:600;line-height:1;margin:2px 0 0}}
.unitmath{{color:#8a8f98;font-size:13px;margin-top:8px}}
.legs{{padding-left:20px;font-size:15px;line-height:1.7}}
.note{{color:#6b6b72;font-size:13px;margin-top:6px}}
.yesrec{{color:#6b6b72;font-size:13px;margin-top:2px}}

.lghead{{color:#6b6b72;font-size:12px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;margin:16px 0 4px;display:flex;align-items:center}}
.lghead:first-of-type{{margin-top:6px}}
.cpx{{margin:8px 0 2px;font-size:13px;color:#9a9aa3}}
.cpx span{{margin-right:12px;font-weight:600}}
.foot{{margin-top:34px;color:#8a8a91;font-size:12px;line-height:1.6}}
#rpModal{{display:none;position:fixed;inset:0;background:rgba(20,20,25,.55);align-items:center;justify-content:center;z-index:50}}
#rpModal .box{{background:#fff;border-radius:14px;padding:22px 20px;max-width:340px;width:88%}}
#rpModal h3{{font-size:16px;margin-bottom:6px}}
#rpModal p{{font-size:13px;color:#6b6b72;margin-bottom:12px}}
#rpState{{width:100%;padding:10px;border:1px solid #e4e2de;border-radius:8px;font-size:15px;margin-bottom:12px}}
#rpShareLoc{{width:100%;padding:11px;border:none;border-radius:8px;background:#2f8f7d;color:#fff;font-size:15px;font-weight:600;cursor:pointer}}
.rpstate-link{{color:#2f8f7d;cursor:pointer;text-decoration:underline}}
#rpA2hs{{display:none;position:fixed;inset:0;background:rgba(20,20,25,.55);align-items:center;justify-content:center;z-index:60}}
#rpA2hs .box{{background:#fff;border-radius:14px;padding:22px 20px;max-width:340px;width:88%;text-align:center}}
#rpA2hs h3{{font-size:16px;margin-bottom:4px}}
#rpA2hs .plat{{font-size:11px;letter-spacing:1px;text-transform:uppercase;color:#2f8f7d;font-weight:700;margin-bottom:12px}}
#rpA2hs ol{{text-align:left;font-size:13px;color:#3a3a40;margin:0 0 16px 0;padding-left:20px}}
#rpA2hs ol li{{margin-bottom:8px}}
#rpA2hs .nav{{display:flex;gap:8px}}
#rpA2hs .nav button{{flex:1;padding:11px;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer}}
#rpA2hs .primary{{background:#2f8f7d;color:#fff}}
#rpA2hs .ghost{{background:#eee;color:#555}}
#rpA2hs .dots{{font-size:10px;color:#bbb;margin-top:12px;letter-spacing:3px}}
.ls{{display:none;align-items:center;gap:5px;font-size:11px;font-weight:700;color:#2f8f7d;white-space:nowrap;margin:5px 0 2px}}
.ls.on{{display:flex}}
.ls .dot{{width:6px;height:6px;border-radius:50%;background:#e5484d;animation:rpblink 1.2s infinite}}
.ls.won{{color:#3ecf6f}}
.ls.lost{{color:#e5484d}}
@keyframes rpblink{{0%,100%{{opacity:1}}50%{{opacity:.25}}}}
#rpPull{{position:fixed;top:0;left:0;right:0;height:56px;display:flex;align-items:center;justify-content:center;background:#f7f6f4;color:#2f8f7d;font-size:13px;font-weight:600;transform:translateY(-100%);z-index:60;pointer-events:none}}
.spin{{width:14px;height:14px;border:2px solid #cde3dd;border-top-color:#2f8f7d;border-radius:50%;animation:rpSpin .8s linear infinite;margin-right:8px;display:inline-block}}
@keyframes rpSpin{{to{{transform:rotate(360deg)}}}}
@media (prefers-color-scheme: dark){{
body{{background:#000;color:#ececf1}}
h1 .tick{{color:#3BEBF5}}
.odds,.rpstate-link{{color:#3aa895}}
.status,.intro,.sect,.num,.sub,.note{{color:#9a9aa3}}
.pick{{border-top-color:#2a2a2e}}
.chip{{background:#0a0a0c;border:1px solid #232328;color:#ececf1}}
.foot{{color:#6f6f78}}
#rpModal{{background:rgba(0,0,0,.6)}}
#rpModal .box{{background:#000;border:1px solid #2a2a2e}}
#rpModal h3{{color:#ececf1}}
#rpModal p{{color:#9a9aa3}}
#rpA2hs{{background:rgba(0,0,0,.6)}}
#rpA2hs .box{{background:#000;border:1px solid #2a2a2e}}
#rpA2hs h3{{color:#ececf1}}
#rpA2hs ol{{color:#c8c8d0}}
#rpA2hs .ghost{{background:#111114;color:#9a9aa3}}
#rpA2hs .dots{{color:#555}}
.ls{{color:#3ec9a0}}
#rpState{{background:#000;color:#ececf1;border-color:#2a2a2e}}
#rpGeoNote{{color:#3aa895 !important}}
#rpPull{{background:#000;color:#3aa895}}
.spin{{border-color:#2a4a44;border-top-color:#3aa895}}
.chip[data-bk="FD"]{{background:#12283d !important;border-color:#12283d !important;color:#5aa9e8 !important}}
.chip[data-bk="TSB"]{{background:#0d1b2e !important;border-color:#0d1b2e !important;color:#4d94ff !important}}
.chip[data-bk="HR"]{{background:#2e2614 !important;border-color:#2e2614 !important;color:#d8b84e !important}}
.chip[data-bk="MGM"]{{background:#2b2517 !important;border-color:#2b2517 !important;color:#cdb271 !important}}
.chip[data-bk="BR"]{{background:#10262f !important;border-color:#10262f !important;color:#4fc3e8 !important}}
.chip[data-bk="KAL"]{{background:#0f2a22 !important;border-color:#0f2a22 !important;color:#3ed0a8 !important}}
.chip[data-bk="POLY"]{{background:#122536 !important;border-color:#122536 !important;color:#5aa9e0 !important}}
.chip[data-bk="B365"]{{background:#2a2410 !important;border-color:#2a2410 !important;color:#e0cd6a !important}}
.chip[data-bk="FAN"]{{background:#232326 !important;border-color:#232326 !important;color:#d8d8dc !important}}
}}
</style>{_V2_ASSETS}<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate"></head><body>
<div id="rpPull"></div>
<div class="wrap">
{_SHELL}
<div id="rpModal"><div class="box">
<h3>One quick thing</h3>
<p>Share your location once so taps open the right product &mdash; sportsbook where it&rsquo;s live, prediction markets everywhere else. Location is required for market links. Saved on this device.</p>
<div id="rpGeoNote" style="font-size:12px;color:#2f8f7d;margin-bottom:10px"></div>
<button id="rpShareLoc" onclick="rpShareLoc()">Share my location</button>
</div></div>
<div id="rpA2hs"><div class="box">
<div class="plat" id="rpA2hsPlat"></div>
<h3>Add RixPicks to your Home Screen</h3>
<ol id="rpA2hsSteps"></ol>
<div class="nav"><button class="ghost" id="rpA2hsBack" onclick="rpA2hsStep(-1)">Back</button><button class="primary" id="rpA2hsNext" onclick="rpA2hsStep(1)">Next</button></div>
<div class="dots" id="rpA2hsDots"></div>
</div></div>
<script>
const RP_FD={json.dumps(RP_FD)};const RP_DK={json.dumps(RP_DK)};
let RP_MARKETS={json.dumps(_MARKETS,separators=(',',':'))};  /* canonical market truth records (Matrix-mining design 9/26) - chips carry data-mr indexes; never parse text into numbers */
const RP_L={{FD:RP_FD,DK:RP_DK,MGM:{json.dumps(RP_MGM)},B365:{json.dumps(RP_B365)},FAN:{json.dumps(RP_FAN)},TSB:{json.dumps(RP_TSB)},HR:{json.dumps(RP_HR)},BR:{json.dumps(RP_BR)}}};
const RP_COMBO_NONTAP={'true' if (man.get('parlay') and combo_nontap) else 'false'};
const RP_MOB=/iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
if(location.protocol==='http:'&&/(^|\.)rix-picks\.com$/.test(location.hostname)){{location.replace('https://'+location.host+location.pathname+location.search+location.hash);}}
const RP_STANDALONE=(navigator.standalone===true)||window.matchMedia('(display-mode: standalone)').matches;
function rpOpen(u){{if(RP_STANDALONE){{location.assign(u);}}else{{window.open(u,'_blank','noopener');}}}}
if(RP_STANDALONE){{document.addEventListener('click',function(e){{const a=e.target.closest('a[target="_blank"]');if(a&&!a.onclick&&a.href){{e.preventDefault();location.assign(a.href);}}}},true);}}
/* U-GEO-002 (user Sep 26 12:27 PM): ONE arm-level legality table as DATA at core - arms, never parent brands (DK Sportsbook != DK Predictions; the dead pre-rebrand arm never renders). Unresolved state fails closed to the prediction-market set (federally-regulated class), state prompt stays. */
const RP_LEGAL_STATE={json.dumps(TABLE,sort_keys=True)};const RP_LEGAL_ASOF='{RP_LEGAL_ASOF}';const RP_LEGAL_BI={{"OH": ["KAL"], "TN": ["KAL"]}};
const RP_PM_DEFAULT=['KAL','POLY','DKP','FDP'];
function rpBookLive(b,st){{if(!st)return RP_PM_DEFAULT.indexOf(b)!==-1;const L=RP_LEGAL_STATE[st];return L?L.indexOf(b)!==-1:false;}}
function rpPm(el){{if(el.dataset.pm&&el.dataset.nopm!=='1')return el.dataset.pm;const mr=el.closest?el.closest('.mrow'):null;if(mr&&mr.dataset.pm&&mr.dataset.nopm!=='1')return mr.dataset.pm;return null;}}
function rpDest(a,st){{const b=a.dataset.book;
 if(a.dataset.platform==='1'&&!a.getAttribute('data-sb'))return null;  /* inspector Sep 26 interim: platform-arm root URLs are NOT tap destinations - non-tappable until event-level deep links land */
 if(rpBookLive(b,st)){{const sb=a.getAttribute('data-sb')||a.getAttribute('data-sbt');if(sb)return sb.replaceAll('{{state}}',st.toLowerCase());return a.getAttribute('href')||null;}}
 return rpPm(a);}}
function rpGo(a,st){{const b=a.dataset.book;
 if(b==='POLY'&&RP_MOB&&a.dataset.app){{location.href=a.dataset.app;return;}}
 if(!rpBookLive(b,st)&&b==='FD'&&RP_MOB&&a.dataset.pmapp&&a.dataset.nopm!=='1'){{location.href=a.dataset.pmapp;return;}}
 const d=rpDest(a,st);if(d)rpOpen(d);return;}}

function rpTerm(st){{const sb=RP_FD.includes(st)||RP_DK.includes(st);const ntap=(typeof RP_COMBO_NONTAP!=='undefined'&&RP_COMBO_NONTAP===true);
 const T=(sb?'Parlay':'Combo')+((!sb||ntap)?'<span style="letter-spacing:0">&thinsp;*</span>':'');
 const h=document.getElementById('rpParlayTitle');if(h)h.innerHTML=T;
 const rg=document.getElementById('rpComboReg');if(rg){{rg.style.display=(!sb||ntap)?'':'none';
  if(ntap){{let _ip=false;document.querySelectorAll('.cxleg').forEach(function(l){{if(rpInPlay(l))_ip=true;}});
   rg.textContent=_ip?'* Combo prices are frozen pre-game references - books pull combos in play. Chips go tappable as verified deep links land.':'* Combo prices are live per-book references - build the combo manually at your book. Chips go tappable as verified deep links land.';}}}}
 const nt=document.getElementById('rpParlayNote');if(nt)nt.style.display=nt.textContent?'':'none';}}
function rpInPlay(pk){{try{{const c=pk.dataset.commence;if(c&&Date.now()>=Date.parse(c))return true;}}catch(e){{}}return false;}}
function rpBestStar(pk){{
 // Sep 26: the best-line star follows VISIBLE prices - geo filtering or a price tick can strand
 // it on a hidden/worse chip. Recomputed over visible chips only, max American odds wins.
 try{{
 const chips=[...pk.querySelectorAll('[data-book]')].filter(function(a){{return !a.querySelector('[data-book]');}});let best=null,bestV=-1e18;
 const ph0=rpPickPhase(pk);
 /* star persists in play on the best FROZEN price (inspector Sep 26) - never-blank doctrine */
 chips.forEach(function(a){{
  if(a.offsetParent===null)return;
  if(a.dataset.pmroute==='1')return;  /* F3: generic PM fallbacks are never best-line */
  if(a.dataset.marker==='1')return;  /* interim markers are references, never best-line */
  if(!rpSamePh(a,ph0))return;  /* never compare across phases */
  const v=rpChipML(a);if(v===null)return;
  if(v>bestV){{bestV=v;best=a;}}
 }});
 chips.forEach(function(a){{a.classList.remove('best');a.innerHTML=a.innerHTML.replace(/^\u2605 /,'');}});
 if(best){{best.classList.add('best');best.innerHTML='\u2605 '+best.innerHTML;}}
 }}catch(e){{}}
}}
function rpAllBest(){{document.querySelectorAll('.pick').forEach(rpBestStar);}}
function rpTapify(el,st){{const d=rpDest(el,st);const pmr=!!(d&&!rpBookLive(el.dataset.book,st));let out;
 if(d){{let a=el;if(el.tagName!=='A'){{a=document.createElement('a');for(const at of el.attributes)a.setAttribute(at.name,at.value);a.innerHTML=el.innerHTML;el.replaceWith(a);}}
  a.setAttribute('href',d);a.setAttribute('onclick','return rpRoute(event,this)');a.setAttribute('target','_blank');a.setAttribute('rel','noreferrer');a.classList.remove('rpnontap');a.classList.remove('rppending');out=a;}}
 else{{let sp=el;if(el.tagName!=='SPAN'){{sp=document.createElement('span');for(const at of el.attributes)sp.setAttribute(at.name,at.value);sp.innerHTML=el.innerHTML;el.replaceWith(sp);}}
  sp.removeAttribute('href');sp.removeAttribute('onclick');sp.removeAttribute('target');sp.removeAttribute('rel');sp.classList.add('rpnontap');out=sp;}}
 /* F3: a prediction-market fallback route never wears sportsbook numbers; restore them when the book is live */
 if(pmr){{if(!out.dataset.pmrprice){{const m=out.innerHTML.match(/^\s*([+-]\d+)\s*$/)||out.innerHTML.match(/ ([+-]\d+)$/);if(m)out.dataset.pmrprice=m[1];}}
  out.innerHTML=out.innerHTML.replace(/^\s*[+-]\d+\s*$/,'').replace(/ [+-]\d+$/,'');out.dataset.pmroute='1';}}
 else{{if(out.dataset.pmrprice&&out.innerHTML.indexOf(out.dataset.pmrprice)<0){{out.innerHTML=(out.innerHTML?out.innerHTML+' ':'')+out.dataset.pmrprice;}}
  delete out.dataset.pmrprice;delete out.dataset.pmroute;}}}}
function rpRowAvail(el,st){{return rpBookLive(el.dataset.book,st)||!!rpPm(el);}}
function rpStrip(el){{el.removeAttribute('href');el.removeAttribute('onclick');el.removeAttribute('target');el.removeAttribute('rel');el.classList.add('rpnontap');}}
function rpGate(el){{if(!(el.getAttribute('href')||el.getAttribute('data-sb')||el.getAttribute('data-sbt')||el.getAttribute('data-pm'))){{rpStrip(el);el.style.display='';return;}}  /* no-route price reference: visibly inert, never prompts */
 const h=el.getAttribute('href');if(h&&!el.getAttribute('data-sb'))el.setAttribute('data-sb',h);rpStrip(el);el.style.display='';el.classList.remove('rpnontap');el.setAttribute('onclick','return rpRoute(event,this)');}}  /* unresolved state: visible, route-stripped, tap opens the state prompt */
function rpFilter(st){{window.rpSt=st;rpTerm(st);
 /* U-GEO-001 amendment (user Sep 26 12:27 PM): visibility is state-scoped - a book with no legal route in the resolved state does NOT render (no inert prices, no markers). The resolved SET is identical on every surface; ranges/star compute over exactly it. Unresolved state = fail-closed nationwide set (KAL/POLY). */
 document.querySelectorAll('[data-book]').forEach(function(el){{
  if(el.querySelector('[data-book]')){{  /* container rows (LIVE MARKETS): children decide, row follows */
   let _any=false;
   el.querySelectorAll('[data-book]').forEach(function(a){{
    if(a.querySelector('[data-book]'))return;
    if(rpBookLive(a.dataset.book,st)){{a.style.display='';delete a.dataset.marker;rpTapify(a,st);_any=true;}}
    else{{a.style.display='none';delete a.dataset.marker;}}
   }});
   el.style.display=_any?'':'none';
   return;}}
  if(!rpBookLive(el.dataset.book,st)){{el.style.display='none';delete el.dataset.marker;return;}}
  el.style.display='';delete el.dataset.marker;rpTapify(el,st);
 }});
 if(window.rpCxStar)rpCxStar();rpAllBest();rpAllLineShops(); }}
const RP_CODES=[{','.join('"%s"'%c for c,_ in RP_STATES)}];
function rpRoute(e,a){{e.preventDefault();const st=localStorage.getItem('rp_state');const src=localStorage.getItem('rp_state_src');const ts=+(localStorage.getItem('rp_state_ts')||0);
 if(!st||src!=='gps'||!ts||Date.now()-ts>12*3600*1000){{window.__rpChip=a;rpAsk(false);return false;}}  /* his rule Sep 26 + tester freshness gate: taps need a CURRENT shared+verified location - expired fixes go back through the prompt */
 rpGo(a,st);return false;}}
function rpShareLoc(){{  /* the ONLY way state resolves now (his verbatim Sep 26 1:52 PM): no manual pick, no preview */
 if(!navigator.geolocation){{rpNote('This browser has no location services. Markets need your location - try another browser.');return;}}
 rpNote('Checking your location…');
 navigator.geolocation.getCurrentPosition(function(pos){{
  fetch('https://api.bigdatacloud.net/data/reverse-geocode-client?latitude='+pos.coords.latitude+'&longitude='+pos.coords.longitude+'&localityLanguage=en').then(r=>r.json()).then(j=>{{
   const code=(j.principalSubdivisionCode||'').split('-')[1]||'';
   if(code&&RP_CODES.indexOf(code)>=0){{
    localStorage.setItem('rp_state',code);localStorage.setItem('rp_state_src','gps');localStorage.setItem('rp_state_gps',code);localStorage.setItem('rp_state_ts',String(Date.now()));
    document.getElementById('rpModal').style.display='none';rpLabel();
    if(window.__rpChip){{const c=window.__rpChip;window.__rpChip=null;rpGo(c,code);}}else{{rpMaybeA2HS();}}
   }}else{{rpNote('Could not resolve your state from that location - tap to retry.');}}
  }}).catch(()=>rpNote('Location lookup failed - tap to retry.'));
 }},function(){{rpNote('Location is required for market links. Enable it for this site, then tap to retry.');}},{{timeout:9000}});}}
function rpLabel(){{try{{const el=document.getElementById('rpStateLabel');const st=localStorage.getItem('rp_state');if(st){{rpFilter(st);rpAllBest();rpAllLineShops();}}if(el){{el.textContent=st?('Your state: '+st+' (verified)'):'Share/update location';}}}}catch(e){{}}}}
function rpNote(t){{const n=document.getElementById('rpGeoNote');if(n)n.textContent=t||'';}}
function rpAsk(manualOnly){{window.__rpChip=window.__rpChip||null;
 rpNote('');document.getElementById('rpModal').style.display='flex';
 rpShareLoc();}}
function rpEdit(){{window.__rpChip=null;rpAsk(false);}}  /* change state = re-verify via location; there is no manual path (his rule Sep 26) */
const RP_A2HS=[{{plat:'iPhone &middot; Safari',steps:['Tap the <b>Share</b> button (square with an up arrow) in Safari&rsquo;s toolbar.','Scroll down and tap <b>Add to Home Screen</b>.','Tap <b>Add</b> - RixPicks now opens full-screen, like an app.']}},{{plat:'Android &middot; Chrome',steps:['Tap the <b>&#8942;</b> menu (top right) in Chrome.','Tap <b>Add to Home screen</b>.','Tap <b>Install</b> - RixPicks now opens full-screen, like an app.']}}];
let rpA2hsI=/iPhone|iPad|iPod/i.test(navigator.userAgent)?0:1;
function rpA2hsRender(){{const c=RP_A2HS[rpA2hsI];document.getElementById('rpA2hsPlat').innerHTML=c.plat;
 document.getElementById('rpA2hsSteps').innerHTML=c.steps.map(x=>'<li>'+x+'</li>').join('');
 document.getElementById('rpA2hsBack').style.visibility=rpA2hsI===0?'hidden':'visible';
 document.getElementById('rpA2hsNext').textContent=rpA2hsI===RP_A2HS.length-1?'Done':'Next';
 document.getElementById('rpA2hsDots').innerHTML=RP_A2HS.map((_,i)=>i===rpA2hsI?'&#9679;':'&#9675;').join(' ');}}
function rpA2hsStep(d){{if(d>0&&rpA2hsI===RP_A2HS.length-1){{rpA2hsDone();return;}}rpA2hsI=Math.min(RP_A2HS.length-1,Math.max(0,rpA2hsI+d));rpA2hsRender();}}
function rpA2hsDone(){{localStorage.setItem('rp_a2hs_v1','1');document.getElementById('rpA2hs').style.display='none';}}
function rpMaybeA2HS(){{if(RP_STANDALONE||RP_MOB===false)return;if(localStorage.getItem('rp_a2hs_v1'))return;
 rpA2hsRender();document.getElementById('rpA2hs').style.display='flex';}}
const RP_BAT='<svg width="12" height="12" viewBox="0 0 24 24" style="vertical-align:-2px;margin:0 3px 0 1px"><g transform="rotate(45 12 12)" fill="#e8b93c"><rect x="10.3" y="1.2" width="3.4" height="12" rx="1.7"/><rect x="11.1" y="12.8" width="1.8" height="7.4" rx="0.9"/><circle cx="12" cy="21.6" r="1.9"/></g></svg>';
function rpFeedStatusTxt(F){{ /* worker-composed canonical moment -> strip status text; a stale clock never wears live (period-only) */
 const gv=function(k){{return (F[k]&&F[k].value!=null)?F[k].value:null;}};
 const clk=gv('clock'),per=gv('period');
 let t='';
 if(clk&&!(F.clock&&F.clock.stale))t=clk;
 if(per&&per!=='FINAL'){{const pn=parseInt(per,10);const po=isNaN(pn)?String(per):(pn===1?'1st':pn===2?'2nd':pn===3?'3rd':pn===4?'4th':(pn===5?'OT':(pn-4)+'OT'));t=t?(t+' - '+po):po;}}
 if(!t){{const dv=gv('detail');if(dv)t=rpPT(dv);}}
 return t;}}
function rpMomentOf(t){{ /* 'm:ss - 3rd' | '3rd' | '2:41 - OT' | '2OT' -> moment parts; null = transitional detail text (not comparable) */
 const m=/^(?:(\d+):(\d\d) - )?(?:(\d+)(?:st|nd|rd|th)(?:\s+(?:quarter|qtr|q|half|period))?|(\d*)OT)$/i.exec(t||''); /* production text forms: '3rd', '3rd Quarter', '1st Half', 'OT' */

 if(!m)return null;
 return {{per:(m[3]!=null)?+m[3]:5+(m[4]?+m[4]-1:0),clk:(m[1]!=null)?(+m[1])*60+(+m[2]):null}};}}
function rpMomentOK(cur,nxt){{ /* cross-lane moment monotonicity: the displayed moment never regresses - period never rewinds; within a period the clock only runs down */
 const a=rpMomentOf(cur),b=rpMomentOf(nxt);
 if(!a||!b)return true;
 if(b.per!==a.per)return b.per>a.per;
 if(a.clk!=null&&b.clk!=null)return b.clk<=a.clk;
 return true;}}
function rpLsEnrichEspn(_pk,_f,_seq){{ /* degradation lane when the worker feed cannot answer: summary fetch + client arbiter */
 fetch('https://site.api.espn.com/apis/site/v2/sports/'+_pk.dataset.espn+'/summary?event='+_f.eid+'&t='+Date.now()).then(r=>r.json()).then(function(sj){{
  if(_seq!==window.__rpLsSeq)return;
  const sc2=(((sj.header||{{}}).competitions)||[])[0]||{{}};const st2=(sc2.status||{{}}).type||{{}};
  if(st2.state!=='in')return;
  if((+(_pk.dataset.lsrank||0))>1)return;
  const _st2x=rpStatusText(_pk,sj,st2);
  if(!_st2x)return;  /* never blank a live strip with an empty summary status */
  if(_pk.__lsLast&&_pk.__lsLast.arb&&rpMomentOf(_pk.__lsLast.st)&&!rpMomentOf(_st2x))return;  /* an answer without a comparable moment never displaces a formed one */
  if(_pk.__lsLast&&_pk.__lsLast.arb&&_pk.__lsLast.state==='in'&&!rpMomentOK(_pk.__lsLast.st,_st2x))return;  /* stale lane answer: the displayed moment never rewinds */
  const _fa=(_pk.__lsLast&&_pk.__lsLast.state==='in')?Math.max(_f.as,_pk.__lsLast.as):_f.as,_fh=(_pk.__lsLast&&_pk.__lsLast.state==='in')?Math.max(_f.hs,_pk.__lsLast.hs):_f.hs;
  const _nf={{a:_f.a,h:_f.h,as:_fa,hs:_fh,st:_st2x,state:'in',arb:true}};  /* per-side canonical floor - lane takeover never lowers displayed scores */
_pk.__lsArbTs=Date.now();const _e4=_pk.querySelector('[data-ls]');if(_e4)_e4.style.opacity='';_pk.__lsLast=_nf;rpLsRender(_pk,_nf);
 }}).catch(()=>{{}});}}
function rpLsRender(pk,g){{const el=pk.querySelector('[data-ls]');if(!el)return;
 if(!g||g.state==='pre'){{el.className='ls';el.innerHTML='';return;}}
 if(g.state==='post'){{const side=pk.dataset.side||'away';
  const win=(side==='away')?(g.as>g.hs):(g.hs>g.as);
  el.className='ls on '+(win?'won':'lost');
  el.innerHTML='<b>'+(win?'W':'L')+'</b> &middot; '+g.a+' '+g.as+' - '+g.h+' '+g.hs+' Final';return;}}
 el.className='ls on';
 const ba=(g.bat==='a')?RP_BAT:'',bh=(g.bat==='h')?RP_BAT:'';
 el.innerHTML=(g.state==='in'?'<span class="dot"></span>':'')+ba+g.a+' '+g.as+' - '+bh+g.h+' '+g.hs+' &middot; '+g.st;}}
async function rpLsTick(){{const picks=[...document.querySelectorAll('.pick[data-away],.cxleg[data-away]')].filter(x=>x.dataset.away);if(!picks.length)return;
 const _seq=(window.__rpLsSeq=(window.__rpLsSeq||0)+1);  /* swarm 16: overlapping ticks - a response from an older tick NEVER writes */
 const mlb=picks.filter(x=>(x.dataset.espn||'')==='baseball/mlb');
 // class fix (9/25 Astros lapse): gamePk-keyed rows hit the per-game feed directly; a lookup
 // miss NEVER blanks a row that was live - it dims and keeps last-good until a good tick lands.
 const rpMlbMiss=pk=>{{window.__rpMissN=(window.__rpMissN||0)+1;const el=pk.querySelector('[data-ls]');if(el&&el.dataset.live==='1'){{el.style.opacity='.55';return;}}rpLsRender(pk,null);}};
 const rpLsMiss=pk=>{{const el=pk.querySelector('[data-ls]');if(el&&(el.dataset.live==='1'||pk.__lsLast)){{el.style.opacity='.55';return;}}rpLsRender(pk,null);}};  /* swarm 11: ESPN lane matches the MLB lane - a board miss DIMS last-good, never erases it */
 const rpLsRank={{pre:0,in:1,post:2}};
 const rpMlbGame=(pk,ls,st,aab,hab)=>{{window.__rpMissN=0;
  const KNOWN=['Scheduled','Pre-Game','Warmup','In Progress','Final','Game Over','Delayed','Delayed Start','Postponed','Suspended','Completed Early','Called'];
  if(KNOWN.indexOf(st)<0){{rpMlbMiss(pk);return;}}
  const inn=(st==='In Progress')?((ls.inningState||'')+' '+(ls.currentInningOrdinal||'')).trim():st;
  const el=pk.querySelector('[data-ls]');if(el){{el.style.opacity='';el.dataset.live=(st==='In Progress')?'1':'';}}
  rpLsRender(pk,{{a:aab,h:hab,as:((ls.teams||{{}}).away||{{}}).runs||0,hs:((ls.teams||{{}}).home||{{}}).runs||0,
   bat:st==='In Progress'?((ls.inningState==='Top'||ls.inningState==='End')?'a':'h'):null,
   st:inn,state:st==='In Progress'?'in':(st==='Final'||st==='Game Over')?'post':'pre'}});if(st==='Final'||st==='Game Over')rpRecLive();}};
 if(mlb.length){{
  const keyed=mlb.filter(x=>x.dataset.gpk),unkeyed=mlb.filter(x=>!x.dataset.gpk);
  const cache={{}};
  keyed.forEach(pk=>{{(async()=>{{
   const k=pk.dataset.gpk;
   try{{
    if(!cache[k]){{const r=await fetch('https://statsapi.mlb.com/api/v1.1/game/'+k+'/feed/live?fields=liveData,linescore,teams,away,home,runs,currentInningOrdinal,inningState,gameData,status,detailedState&t='+Date.now());if(!r.ok)throw new Error('feed');cache[k]=await r.json();}}
    if(_seq!==window.__rpLsSeq)return;  /* swarm 16 */
    const j=cache[k];const ls=(j.liveData||{{}}).linescore||{{}};const st=((j.gameData||{{}}).status||{{}}).detailedState||'';
    if(!st){{rpMlbMiss(pk);return;}}
    rpMlbGame(pk,ls,st,pk.dataset.aab||pk.dataset.away.split(' ').map(w=>w[0]).join('').slice(0,3).toUpperCase(),pk.dataset.hab||pk.dataset.home.split(' ').map(w=>w[0]).join('').slice(0,3).toUpperCase());
   }}catch(e){{rpMlbMiss(pk);}}}})();}});
  // J-101 class fix: unkeyed rows NEVER stamp. The old teams-only fallback matched a PRIOR date's
  // completed game (same teams) and stamped its Final onto an unplayed pick. Keyed gamePk binding only.
 }}
 const byLg={{}};picks.filter(x=>x.dataset.espn).forEach(x=>{{(byLg[x.dataset.espn]=byLg[x.dataset.espn]||[]).push(x);}});
 for(const lg of Object.keys(byLg)){{try{{
  const _u='https://site.api.espn.com/apis/site/v2/sports/'+lg+'/scoreboard?cb='+Date.now()+(lg==='football/college-football'?'&groups=80&limit=400':'');
  const d=await (await fetch(_u)).json();
  if(_seq!==window.__rpLsSeq)return;  /* a delayed older board dies here */
  if(d&&Array.isArray(d.events)){{window.__rpEspnOk=Date.now();}}  /* three-way verdict (Matrix outcome_truth Sep 26): TSB stamps ok ONLY when named fields parse - an error body or shape change is UNKNOWN and never stamps */
  // J-101 class fix: strict event-id binding - a row stamps ONLY when its own event (data-eid) is on the board.
  byLg[lg].forEach(pk=>{{let found=null;const want=pk.dataset.eid||'';const _isMlb=pk.dataset.espn==='baseball/mlb';
   if(!want){{if(!_isMlb)rpLsRender(pk,null);return;}}
   (d.events||[]).forEach(e=>{{if(e.id!==want)return;
    const cs=e.competitions[0].competitors;
    const aw=cs.find(c=>c.homeAway==='away'),hm=cs.find(c=>c.homeAway==='home');if(!aw||!hm)return;
    found={{a:aw.team.abbreviation,h:hm.team.abbreviation,as:+aw.score||0,hs:+hm.score||0,st:e.status.type.shortDetail,state:e.status.type.state}};}});
   if(!_isMlb){{
    if(!found){{rpLsMiss(pk);}}
    else{{const nr=rpLsRank[found.state]||0,pr=+(pk.dataset.lsrank||0);
     {{if(pk.__lsLast&&pk.__lsLast.arb&&found.state==='in'&&pk.__lsLast.state==='in'){{
   /* canonical-hold: once an arbiter lane (worker feed or summary arbiter) owns the live render, the raw board advances
      SCORES ONLY, per-side monotonic - its low-resolution status text never overwrites the canonical moment.
      Evaluated on EVERY live board tick under arb ownership, advance or regress: the carried-state dim never depends on the board moving. */
   const _mg={{a:found.a,h:found.h,as:Math.max(found.as,pk.__lsLast.as),hs:Math.max(found.hs,pk.__lsLast.hs),st:pk.__lsLast.st,state:'in',arb:true}};
   pk.__lsLast=_mg;pk.dataset.lsrank=nr;const _e=pk.querySelector('[data-ls]');
   if(_e)_e.style.opacity=(Date.now()-(pk.__lsArbTs||0)>60000)?'.55':'';
   rpLsRender(pk,_mg);
  }}else if((nr>=pr||!pk.__lsLast)&&!(pk.__lsLast&&pk.__lsLast.state==='in'&&found.state==='in'&&(found.as+found.hs)<(pk.__lsLast.as+pk.__lsLast.hs))){{pk.__lsLast=found;pk.dataset.lsrank=nr;const _e=pk.querySelector('[data-ls]');if(_e)_e.style.opacity='';rpLsRender(pk,found);if(found.state==='post')rpRecLive();}}}}  /* swarm 16: same-state boards also monotonic on progress - 17-21 never rewrites to 10-14 */  /* swarm 11: monotonic pre->in->post - a stale pre-board never rolls state BACKWARD; last-good snapshot held */
    }}}}
   /* odds + clock ride the 2s score tick (his Sep 26 instant spec): odds from the same scoreboard payload
      (zero extra fetches); one summary fetch per LIVE pick arbitrates the strip clock against advancing plays */
   /* attribution root fix Sep 26 (swamp catch, his rule): the scoreboard's odds payload is a DraftKings quote -
      writing it into a[data-book="TSB"] labeled DK's number as theScore and poisoned the canonical record.
      Chips render ONLY from their own attributed record (own-platform ticks: rpPolyTick/rpKalTick) or stay at snapshot. */
   if(found&&found.state==='in'){{(function(_pk,_f){{
    fetch('https://api.rix-picks.com/feed/game/'+_f.eid+'?league='+encodeURIComponent(_pk.dataset.espn)+'&t='+Date.now()).then(r=>r.json()).then(function(fj){{
     if(_seq!==window.__rpLsSeq)return;
     if(!fj||!fj.fields){{rpLsEnrichEspn(_pk,_f,_seq);return;}}  /* worker feed cannot answer: degradation lane, never worse than the pre-feed path */
     const F=fj.fields;const stv=(F.state&&F.state.value)||fj.state||'';
     if(stv!=='in')return;  /* monotonic: a non-live feed never rewrites the live render; post lands via the board branch */
     const _staleFld=['scoreAway','scoreHome','clock','period','state','detail'].some(function(k){{return F[k]&&F[k].stale===true;}});
     if(fj.allDown===true||_staleFld){{rpLsEnrichEspn(_pk,_f,_seq);return;}}  /* stale worker answer (total upstream outage or aged fields): must never restamp apparent liveness or clear the dim - the degradation lane arbitrates, else the hold+dim path keeps last good (outage doctrine) */
     if((+(_pk.dataset.lsrank||0))>1)return;
     const sa=(F.scoreAway&&F.scoreAway.value!=null&&!isNaN(+F.scoreAway.value))?+F.scoreAway.value:null;
     const sh=(F.scoreHome&&F.scoreHome.value!=null&&!isNaN(+F.scoreHome.value))?+F.scoreHome.value:null;
     const _st=rpFeedStatusTxt(F)||_f.st;
     if(_pk.__lsLast&&_pk.__lsLast.arb&&_pk.__lsLast.state==='in'&&!rpMomentOK(_pk.__lsLast.st,_st))return;  /* stale lane answer: the displayed moment never rewinds */
     const _fa=(_pk.__lsLast&&_pk.__lsLast.state==='in')?Math.max(_f.as,_pk.__lsLast.as):_f.as,_fh=(_pk.__lsLast&&_pk.__lsLast.state==='in')?Math.max(_f.hs,_pk.__lsLast.hs):_f.hs;
     const _nf={{a:_f.a,h:_f.h,as:(sa!=null&&sa>=_fa)?sa:_fa,hs:(sh!=null&&sh>=_fh)?sh:_fh,st:_st,state:'in',arb:true}};  /* canonical arbitrated scores - the wrong-score class (raw-board behind-read) cannot surface on the index; per-side floor = the board snapshot */
     _pk.__lsArbTs=Date.now();const _e3=_pk.querySelector('[data-ls]');if(_e3)_e3.style.opacity='';_pk.__lsLast=_nf;rpLsRender(_pk,_nf);
    }}).catch(()=>{{rpLsEnrichEspn(_pk,_f,_seq);}});
   }})(pk,Object.assign({{eid:want}},found));}}
  }});}}catch(e){{}}}}
}}
function rpCxLive(){{const legs=[...document.querySelectorAll('.cxleg')];const el=document.getElementById('rpCxLive');if(!el||!legs.length)return;
 let w=0,l=0,live=0;
 legs.forEach(x=>{{const sp=x.querySelector('[data-ls]');if(!sp)return;
  if(sp.classList.contains('won'))w++;else if(sp.classList.contains('lost'))l++;else if(sp.classList.contains('on'))live++;}});
 if(!w&&!l&&!live){{el.style.display='none';return;}}
 el.style.display='';
 if(l>0){{el.innerHTML='<span style="color:#e5484d;font-weight:700">Combo dead</span> - '+w+' of '+legs.length+' legs home';return;}}
 if(w===legs.length){{el.innerHTML='<span style="color:#3ecf6f;font-weight:700">Combo cashed</span> - all '+legs.length+' legs home';return;}}
 el.textContent=w+' of '+legs.length+' legs home'+(live?' \u00b7 '+live+' live':'')+(legs.length-w-l-live>0?' \u00b7 '+(legs.length-w-l-live)+' upcoming':'');}}
let _rpRecLast=0;
async function rpRecLive(){{const rec=document.getElementById('rpRec');if(!rec)return;
 /* Live canonical record: hydrate from same-origin manifest.json - the ledger-verified served record written by record_final (one record, one source, every surface - main 9/27; the api.rix-picks.com/record worker is a stale mirror, keeper-side). 404/failure keeps baked last-build values: fail closed, never invent. Page finals are still NEVER added locally. */
 const _now=Date.now();
 if(_now-_rpRecLast>15000){{_rpRecLast=_now;
 try{{const r=await fetch('manifest.json?cb='+_now);if(r.ok){{const j=await r.json();const m=/^([0-9]+)-([0-9]+)/.exec((j&&j.record)||'');if(m){{rec.dataset.bw=m[1];rec.dataset.bl=m[2];const u0=document.getElementById('rpUnits');if(u0&&j.units_pl){{const up=parseFloat(String(j.units_pl).replace('u',''));if(!isNaN(up))u0.dataset.bu=up;}}}}}}}}catch(e){{}}}}
 const w=parseInt(rec.dataset.bw||'0'),l=parseInt(rec.dataset.bl||'0');
 rec.innerHTML='&rsquo;RixPicks Overall Record: '+w+'-'+l;
 const pct=document.getElementById('rpWlPct');if(pct&&(w+l)>0)pct.textContent='W/L: '+(100*w/(w+l)).toFixed(1)+'%';
 const uEl=document.getElementById('rpUnits');if(uEl){{const u=parseFloat(uEl.dataset.bu||'0');uEl.textContent='Units: '+(u>=0?'+':'')+u.toFixed(2)+'u';}}
}}
function rpFinalsTop(){{document.querySelectorAll('.pick').forEach(function(pk){{
 var sp=pk.querySelector('[data-ls]');if(!sp)return;
 var done=sp.classList.contains('won')||sp.classList.contains('lost');if(!done||pk.dataset.fin)return;
 pk.dataset.fin='1';
 var h=pk.previousElementSibling;while(h&&!h.classList.contains('lghead'))h=h.previousElementSibling;
 if(h&&h.parentNode===pk.parentNode)h.parentNode.insertBefore(pk,h.nextElementSibling);
 }});
}}
function rpRenumber(){{try{{
 let i=0;
 document.querySelectorAll('.pick').forEach(function(pk){{const n=pk.querySelector('.num');if(!n)return;i++;n.textContent=i+'.';}});
}}catch(e){{}}}}
document.addEventListener('click',function(e){{const pk=e.target.closest('.pick');if(!pk)return;if(e.target.closest('a,button,input,select,textarea,label'))return;const gl=pk.querySelector('.gamelink');if(gl){{e.preventDefault();location.assign(gl.getAttribute('href'));}}}});
let _rpCcLast=0;
function rpChatCounts(){{try{{
 const now=Date.now();if(now-_rpCcLast<60000)return;_rpCcLast=now;
 document.querySelectorAll('.pick[data-room]').forEach(function(pk){{
  const sp=pk.querySelector('[data-cc]');if(!sp)return;
  fetch('https://api.rix-picks.com/chat/'+pk.dataset.room).then(r=>r.json()).then(function(j){{sp.textContent=j.count>0?' '+j.count:'';}}).catch(()=>{{}});
 }});
}}catch(e){{}}}}
function rpLineShop(pk){{try{{
 const ip=function(a){{return a>0?100.0/(a+100):(-a)/((-a)+100.0);}};
 const prs=[];
 const ph0=rpPickPhase(pk);
 const pmkt=pk.dataset.market||'';
 [...pk.querySelectorAll('[data-book]')].filter(function(a){{return !a.querySelector('[data-book]');}}).forEach(function(a){{
  if(pmkt&&a.dataset.market!==pmkt)return;  /* sentinel Sep 26 (fail-closed): only chips WITH matching market identity enter the range */
  if(!rpSamePh(a,ph0))return;
  if(!rpMkt(a))return;  /* canonical-record-only (user 9/26 parity): the range is the pick's truth set - identical for every viewer; geo/routing/marker state never changes the math */
  if(a.offsetParent===null)return;  /* U-DATA-001 amendment: the range is computed over exactly the state-resolved VISIBLE set */
  const v=rpChipML(a);if(v===null)return;
  if(Math.abs(v)<=1500)prs.push(v);
 }});
 const el=pk.querySelector('.rplineshop');if(!el)return;
 /* his rule 9:43:53: EVERY pick gets the line, every time - agreement is a truth to render,
    never a reason to omit. Zero readable prices stays hidden (nothing truthful to show). */
 if(prs.length<1){{el.style.display='none';return;}}
 const best=Math.max.apply(null,prs),worst=Math.min.apply(null,prs);
 const edge=(ip(worst)-ip(best))*100;
 const _inplay=rpInPlay(pk);
 if(prs.length<2){{el.style.display='';el.textContent=(_inplay?'pre-game: ':'line shop: ')+(best>0?'+':'')+best+' - only one book priced';return;}}
 if(edge<0.05){{el.style.display='';el.textContent=(_inplay?'pre-game: ':'line shop: ')+(best>0?'+':'')+best+' at every book - no edge';return;}}
 el.style.display='';
 el.textContent=_inplay?('pre-game range: '+(worst>0?'+':'')+worst+' to '+(best>0?'+':'')+best):('line shop: '+(worst>0?'+':'')+worst+' to '+(best>0?'+':'')+best+' \u00b7 '+edge.toFixed(1)+'% edge at the best price');
}}catch(e){{}}}}
function rpAllLineShops(){{document.querySelectorAll('.pick').forEach(rpLineShop);}}
function rpStartTimes(){{const now=Date.now();document.querySelectorAll('.rpstart[data-commence]').forEach(function(el){{const t=Date.parse(el.dataset.commence);if(t&&now>=t)el.remove();}});}}
async function rpLsTickAll(){{await rpLsTick();rpFinalsTop();rpCxLive();rpRecLive();rpChatCounts();rpAllLineShops();}}
function rpLiveClock(d,j,st){{ /* panel auditor Sep 26: frozen status clock never wins over advancing plays; both frozen >4min = stale-as-live */
 const _acfg=(window.RP_SPORT_CLOCK||{{}})[d.dataset.espn];
 const _am=(_acfg&&window.rpFeedArb&&rpFeedArb.markerFromEspnSummary)?rpFeedArb.markerFromEspnSummary(j,_acfg):undefined;  /* ONE parser (arbiter v3.1) for every registry-clocked league - no field-extraction drift */
 if(_acfg&&_am===null)return '';  /* unknown/drift: no clock served, never guessed from prose */
 if(_am&&_am.negative)return '';  /* failed verdict (completed/not-started): status text carries the truth */
 const _fmt=function(v){{return (v==null)?'':(Math.floor(v/60)+':'+('0'+v%60).slice(-2));}};  /* regression hold Sep 26 (live NEB repro): arbiter raw fields are SECONDS - format m:ss at the display boundary; 0:00 is a valid clock, never ||-defaulted away */
 const s=_am?_fmt(_am.sClock):((st.displayClock||((st.shortDetail||'').match(/^\d+:\d+/)||[''])[0]||''));
 const pl=_am?[]:((((j.drives||{{}}).current||{{}}).plays)||j.plays||[]);
 const lp=_am?null:(pl.length?pl[pl.length-1]:null);
 const p=_am?_fmt(_am.pClock):(lp?(((lp.clock||{{}}).displayValue)||''):'');
 const nk=_am?(_am.playKey||''):(pl.length+'|'+(((j.drives||{{}}).previous)||[]).length+'|'+(lp?(lp.id||lp.text||''):''));
 const k=d.dataset.eid||'x';const W=window.__rpClk=window.__rpClk||{{}};const rec=W[k]=W[k]||{{s:'',sT:0,p:'',pT:0,n:'',nT:0}};
 const now=Date.now();
 if(s&&s!==rec.s){{rec.s=s;rec.sT=now;}}
 if(p&&p!==rec.p){{rec.p=p;rec.pT=now;}}
 if(nk!==rec.n){{rec.n=nk;rec.nT=now;}}
 rec.stale=(now-Math.max(rec.sT,rec.pT,rec.nT))>240000;
 if(rec.p&&rec.pT>rec.sT)return rec.p;
 if(rec.s&&rec.sT>rec.pT)return rec.s;
 const _sec=function(v){{const m=/^(\d+):(\d+)$/.exec(v||'');return m?(+m[1])*60+(+m[2]):null;}};
 const _ps=_sec(rec.p),_ss=_sec(rec.s);
 if(_ps!=null&&_ss!=null&&_ps<_ss&&(_ss-_ps)<=600)return rec.p;
 return rec.s||rec.p;
}}
function rpStatusText(d,j,st){{ /* tester Sep 26 presentation parity: EVERY clock on the page comes from the one arbiter */
 const rec=(window.__rpClk||{{}})[d.dataset.eid||'x']||{{}};
 const per=(st.shortDetail||'').replace(/^\d+:\d+\s*-\s*/,'');
 const c=rpLiveClock(d,j,st);
 if(rec.stale)return per;
 return c?(c+(per?' - '+per:'')):per;  /* regression hold Sep 26: an empty arbiter verdict NEVER falls back to unstripped shortDetail - its embedded clock is exactly what the verdict rejected */
}}
{fut_badge_js}async function rpFastLoop(){{try{{await rpLsTick();}}catch(e){{}}try{{rpPolyTick();}}catch(e){{}}
 try{{const _now=Date.now();[['POLY','__rpPolyOk',30000],['KAL','__rpKalOk',90000],['TSB','__rpEspnOk',30000]].forEach(function(pr){{const dim=(_now-(window[pr[1]]||0))>pr[2];document.querySelectorAll('[data-book="'+pr[0]+'"]').forEach(function(c){{c.style.opacity=dim?'.55':'';}});}});}}catch(e){{}}  /* honesty dims: stale source dims, stale never re-stamps; KAL threshold 90s matches its 60s pregame cadence (proxy route), others 30s */
 setTimeout(rpFastLoop,((window.__rpMissN||0)>=5)?5000:2000);}}
function rpGamesTick(){{var el=document.getElementById('rpGames');if(!el)return;fetch("slates/live_games.json?cb="+Date.now(),{{cache:"no-store"}}).then(function(r){{if(!r.ok)throw 0;return r.json();}}).then(function(j){{var html="";(j.leagues||[]).forEach(function(L){{(L.games||[]).forEach(function(g){{var sc=(g.score&&g.status!=="pre")?(" &middot; "+esc(g.score)):"";var to="";if(typeof g.away_to==="number"&&typeof g.home_to==="number"){{to=" &middot; <span style=\\"color:#b07708\\">TO "+g.away_to+"-"+g.home_to+"</span>";}}html+="<div style=\\"padding:6px 0;border-top:1px solid #ececf0;font-size:13px\\"><span style=\\"color:#8a8f98;font-size:11px;letter-spacing:.04em\\">"+esc(L.league)+"</span> "+esc(g.matchup)+sc+" <span style=\\"color:#8a8f98\\">"+esc(rpPT(g.detail)||"")+"</span>"+to+"</div>";}});}});el.innerHTML=html||"<div style=\\"padding:10px 0;color:#8a8f98;font-size:13px\\">No live games right now</div>";var s=document.getElementById('rpAsideSub');if(s){{try{{s.textContent=j.generated_at?("updated "+new Date(j.generated_at).toLocaleTimeString("en-US",{{timeZone:"America/Los_Angeles",hour:"numeric",minute:"2-digit"}}).toLowerCase().replace(" ","")+" PT"):"";}}catch(e){{}}}}}}).catch(function(){{}});}}
rpFastLoop();rpLsTickAll();rpStartTimes();rpGamesTick();setInterval(function(){{rpFinalsTop();rpCxLive();rpRecLive();rpChatCounts();rpAllBest();rpAllLineShops();rpStartTimes();rpGamesTick();}},30000);
document.getElementById('rpModal').addEventListener('click',function(e){{if(e.target===this){{this.style.display='none';localStorage.setItem('rp_state_dismissed','1');}}}});
function rpFreshState(){{try{{const st=localStorage.getItem('rp_state'),src=localStorage.getItem('rp_state_src'),ts=+(localStorage.getItem('rp_state_ts')||0);return (st&&src==='gps'&&ts&&Date.now()-ts<=12*3600*1000)?st:'';}}catch(e){{return '';}}}}  /* tester Sep 26: even the FIRST paint never exposes an expired jurisdiction */
var _rpFs=rpFreshState();rpFilter(_rpFs);if(!_rpFs&&!localStorage.getItem('rp_state_dismissed')){{try{{rpAsk(false);}}catch(e){{}}}}rpResolveState();
function rpResolveState(){{try{{  /* his rule Sep 26 1:52 PM: ONLY shared location resolves state - no IP guess, no manual, no preview. Unverified = fail-closed PM set + location prompt on tap. */
 const saved=localStorage.getItem('rp_state'),src=localStorage.getItem('rp_state_src');
 /* freshness boundary (tester Sep 26): a saved GPS state expires after 12h - re-verify silently when
    location permission persists, fail closed (clear + prompt on tap) when it does not */
 const _sts=+(localStorage.getItem('rp_state_ts')||0);
 if(saved&&src==='gps'&&(!_sts||Date.now()-_sts>12*3600*1000)){{
  localStorage.removeItem('rp_state');localStorage.removeItem('rp_state_src');rpLabel();  /* tester re-gate Sep 26: expired state is CLEARED UP FRONT - taps fail closed until the async re-verify below lands a new fix */
 }}
 if(saved&&src!=='gps'){{const gps=localStorage.getItem('rp_state_gps');const gts=+(localStorage.getItem('rp_state_ts')||0);
  if(gps&&gts&&Date.now()-gts<=12*3600*1000){{localStorage.setItem('rp_state',gps);localStorage.setItem('rp_state_src','gps');rpLabel();}}  /* legacy promotion only with a FRESH stamp */
  else{{localStorage.removeItem('rp_state');localStorage.removeItem('rp_state_src');localStorage.removeItem('rp_state_gps');rpLabel();}}  /* legacy unverified state cleared - fail closed */
 }}
 const apply=function(code){{if(code&&RP_CODES.indexOf(code)>=0){{localStorage.setItem('rp_state',code);localStorage.setItem('rp_state_src','gps');localStorage.setItem('rp_state_gps',code);localStorage.setItem('rp_state_ts',String(Date.now()));rpLabel();}}}};
 if(navigator.permissions&&navigator.geolocation){{
  navigator.permissions.query({{name:'geolocation'}}).then(function(p){{
   if(p.state==='granted'){{navigator.geolocation.getCurrentPosition(function(pos){{
    fetch('https://api.bigdatacloud.net/data/reverse-geocode-client?latitude='+pos.coords.latitude+'&longitude='+pos.coords.longitude+'&localityLanguage=en').then(r=>r.json()).then(function(j){{const code=(j.principalSubdivisionCode||'').split('-')[1]||'';if(code)apply(code);}}).catch(function(){{}});
   }},function(){{}},{{timeout:6000}});}}
  }}).catch(function(){{}});
 }}
}}catch(e){{}}}}
rpLabel(); /* state prompt fires only on outbound market taps - never gates score/game content (complaint-lens via main 9/26) */
const RP_BUILD='{{build_sha}}';
try{{fetch('https://api.rix-picks.com/beacon',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{page:'index',build:RP_BUILD,vw:innerWidth,vh:innerHeight,dpr:devicePixelRatio,ua:navigator.userAgent}}),keepalive:true}}).catch(()=>{{}});}}catch(e){{}}
window.addEventListener('pageshow',function(){{try{{
 if(sessionStorage.getItem('rp_reloaded')===RP_BUILD)return;
 fetch(location.pathname+'?cb='+Date.now(),{{cache:'no-store'}}).then(r=>r.text()).then(t=>{{
  const m=t.match(/RP_BUILD='([^']+)'/);
  const fresh=m?m[1]:null;
  if(fresh&&fresh!==RP_BUILD){{sessionStorage.setItem('rp_reloaded',fresh);location.replace(location.pathname+'?v='+fresh);}}
 }}).catch(()=>{{}});
}}catch(e){{}}}});
/* Pull-to-refresh (incl. Home Screen standalone) - user 9/24 10:40 PM */
(function(){{let y0=null;const el=document.getElementById('rpPull');
 window.addEventListener('touchstart',function(e){{if(window.scrollY<=0&&e.touches.length===1)y0=e.touches[0].clientY;}},{{passive:true}});
 window.addEventListener('touchmove',function(e){{if(y0===null)return;
  const d=e.touches[0].clientY-y0;
  if(d>12&&window.scrollY<=0){{el.style.transform='translateY('+Math.min(d/2.2,56)+'px)';el.dataset.armed=d>80?'1':'';el.innerHTML=d>80?'<span class="spin"></span>Release to refresh':'Pull to refresh';}}
 }},{{passive:true}});
 window.addEventListener('touchend',function(){{if(y0!==null&&el.dataset.armed==='1'){{el.innerHTML='<span class="spin"></span>Refreshing&hellip;';location.replace(location.pathname+'?r='+Date.now());return;}}el.style.transform='translateY(-100%)';y0=null;}},{{passive:true}});
}})();
/* Live odds - POLY chips (public gamma API, ~60s) + headline consensus (ESPN free feed, ~60s). No keys. */
function rpC2ML(c){{c=Math.round(c);if(c<=0)return null;if(c>=100)return c+'c';const m=c>=50?-Math.round(c/(100-c)*100):Math.round((100-c)/c*100);return Math.abs(m)>1000?c+'c':m;}}
function rpC2MLn(c){{c=Math.round(c);if(c<=0||c>=100)return null;return c>=50?-Math.round(c/(100-c)*100):Math.round((100-c)/c*100);}}  /* numeric American - comparison math only, never display */
function rpMkt(a){{try{{const i=a.dataset.mr;if(i==null||typeof RP_MARKETS==='undefined')return null;return RP_MARKETS[+i]||null;}}catch(e){{}}return null;}}
function rpChipPh(a){{const r=rpMkt(a);return r?r.ph:null;}}
function rpChipML(a){{const r=rpMkt(a);if(r){{if(r.st!=='ok')return null;if(r.c!=null)return rpC2MLn(r.c);return r.ml;}}if(a.dataset&&a.dataset.cents){{return rpC2MLn(a.dataset.cents);}}const m=a.textContent.match(/([+-]\d+)/);return m?parseInt(m[1]):null;}}  /* canonical truth record first (Matrix design 9/26); text is never a computational source when a record exists */
function rpPickPhase(pk){{let ph=null;pk.querySelectorAll('[data-mr]').forEach(function(a){{if(ph)return;const r=rpMkt(a);if(r)ph=r.ph;}});return ph;}}
function rpSamePh(a,ph){{if(!ph)return true;const r=rpMkt(a);return !!r&&r.ph===ph;}}  /* fail-closed (main/swamp Sep 26): record-less chips (no phase provenance) never join star/range/combo comparisons */
function rpMLF(m){{return (typeof m==='string')?m:(m>0?'+':'')+m;}}
function rpCxLegAnchors(bk){{
 const out=[];
 document.querySelectorAll('.legs li[data-eid]').forEach(function(li){{
  const pk=document.querySelector('.pick[data-eid="'+li.dataset.eid+'"]');if(!pk)return;
  const a=pk.querySelector('a[data-cxleg="'+bk+'"]')||pk.querySelector('a[data-book="'+bk+'"]')||pk.querySelector(bk==='KAL'?'a[data-kalticker]':'a[data-polyslug]');
  if(a)out.push(a);
 }});
 return out;  /* swarm 9: legs bind by EVENT IDENTITY inside their own card - sitewide anchor counts can never mismatch */
}}
function rpCxUpdMl(bk){{
 const span=document.querySelector('#rpParlayChips [data-book="'+bk+'"]');if(!span)return;
 const cr=rpMkt(span);  /* inspector Sep 26: combo recomputes on every leg tick - leg records self-freeze at their own kickoff, product stays same-phase */
 const n=document.querySelectorAll('.legs li').length;if(!n)return;
 let d=1,cnt=0;
 rpCxLegAnchors(bk).forEach(function(a){{
  const lr=rpMkt(a);  /* no leg-phase gate: each record holds its phase-correct value (frozen at kickoff, live while pre-game) */
  const ml=rpChipML(a);if(ml===null)return;  /* record-first pricing - rendered text is never a source */
  cnt++;
  d*=ml>0?1+ml/100:1+100/Math.abs(ml);
 }});
 if(cnt!==n||d<=1)return;
 const ml2=d>=2?Math.round((d-1)*100):-Math.round(100/(d-1));
 if(cr){{cr.ml=ml2;cr.ts=Date.now();}}  /* canonical record write-through: display derives from the record, never the reverse */
 span.innerHTML=span.innerHTML.replace(/([+-]\d+)/,(ml2>0?'+':'')+ml2);
 rpCxStar();
}}
function rpCxUpd(bk){{
 const chip=document.getElementById('rpCx'+bk);if(!chip)return;
 const cr=rpMkt(chip);  /* inspector Sep 26: combo recomputes on every leg tick - leg records self-freeze at their own kickoff, product stays same-phase */
 const n=parseInt(chip.dataset.n||'0');if(!n)return;
 let d=1,cnt=0,dead=false;
 rpCxLegAnchors(bk).forEach(function(a){{
  if(a.id==='rpCxKAL'||a.id==='rpCxPOLY')return;
  if(a.dataset.won==='1'){{cnt++;return;}}
  if(a.dataset.lost==='1'){{cnt++;dead=true;return;}}
  const lr=rpMkt(a);  /* no leg-phase gate: each record holds its phase-correct value (frozen at kickoff, live while pre-game) */
  const ml=rpChipML(a);if(ml!==null){{d*=ml>0?1+ml/100:1+100/Math.abs(ml);cnt++;}}  /* combo American from the per-leg CARD AMERICANS (main 7:47 ruling): matches the manifest label, the static chip, the card photo and the social post; the raw-cents path yields a fighting value (+1304 vs +1306) */

 }});
 if(cnt!==n)return;
 if(dead){{rpCxStar();return;}}
 if(d<=1)return;
 const ml2=d>=2?Math.round((d-1)*100):-Math.round(100/(d-1));
 const cc=Math.round(100/d);
 const lbl=(ml2>0?'+':'')+ml2;  /* user Sep 26 12:58 PM: ALL chips American, PM combo chips included (supersedes both U-DISP-001 c1 and the old +/-1000 cents fallback) */
 if(cr){{cr.ml=ml2;delete cr.c;cr.ts=Date.now();}}  /* canonical record write-through: star/rank read the SAME American the chip shows (c cleared - cents no longer the combo source of truth) */
 chip.dataset.cents=cc;
 chip.innerHTML=chip.innerHTML.replace(/(KAL|POLY)( [+-]?\d+| \d+c)?/, bk+' '+lbl);
 rpCxStar();
}}
function rpCxStar(){{try{{
 const wrap=document.getElementById('rpParlayChips');if(!wrap)return;
 let best=null,bestV=-1e9;
 const ph0=(function(){{let ph=null;document.querySelectorAll('.cxleg').forEach(function(l){{if(rpInPlay(l))ph='last_pre_game';}});return ph;}})();
 wrap.querySelectorAll('[data-book]').forEach(function(a){{
  const vis=a.style.display!=='none';
  a.classList.remove('best');
  a.innerHTML=a.innerHTML.replace(/^\u2605 /,'');
  if(!vis||a.dataset.pmroute==='1')return;  /* F3 */
  if(!rpSamePh(a,ph0))return;
  const v=rpChipML(a);if(v===null)return;
  if(v>bestV){{bestV=v;best=a;}}
 }});
 if(best){{best.classList.add('best');best.innerHTML='\u2605 '+best.innerHTML;}}
}}catch(e){{}}}}
function rpPolyTick(){{try{{
 document.querySelectorAll('a[data-polyslug]').forEach(function(a){{
  if(!a.dataset.polyslug)return;
  const r0=rpMkt(a);if(r0&&r0.ph==='last_pre_game')return;  /* frozen phases never tick (phase = event status, not fetch time) */
  fetch('https://gamma-api.polymarket.com/events?slug='+a.dataset.polyslug+'&_='+Date.now()).then(r=>r.json()).then(function(ev){{
   if(!ev||!ev.length)return;const kw=(a.dataset.polykw||'').toLowerCase();const sub=a.dataset.polysub||'';
   let target=null,yn=false;
   (ev[0].markets||[]).forEach(function(m){{
    if(target)return;
    if(sub){{if(m.slug===sub)target=m;return;}}
    const q=String(m.question||'');if(q.indexOf(':')>=0)return;
    let oo=[];try{{oo=JSON.parse(m.outcomes||'[]');}}catch(e){{return;}}
    for(let k=0;k<oo.length;k++){{if(String(oo[k]).toLowerCase().indexOf(kw)>=0){{target=m;break;}}}}
   }});
   if(!target){{
    (ev[0].markets||[]).forEach(function(m){{
     if(target)return;
     const q=String(m.question||'').toLowerCase();
     if(q.indexOf('will ')===0&&q.indexOf(' win')>=0&&kw&&q.indexOf(kw)>=0){{target=m;yn=true;}}
    }});
   }}
   if(!target)return;
   let outs=[],pr=[];try{{outs=JSON.parse(target.outcomes||'[]');pr=JSON.parse(target.outcomePrices||'[]');}}catch(e){{return;}}
   window.__rpPolyOk=Date.now();  /* regression gate Sep 26: stamp BEFORE the outcome loop - old site sat after an unconditional return and never ran */
   if(yn&&outs.length===2&&outs[0]==='Yes'&&pr[0]!=null){{outs=[kw];pr=[pr[0]];}}
   for(let i=0;i<outs.length;i++){{if(kw&&String(outs[i]).toLowerCase().indexOf(kw)>=0&&pr[i]!=null){{
    const c=Math.round(parseFloat(pr[i])*100);
    if(target.closed&&c>=99){{a.dataset.won='1';a.dataset.lost='';rpCxUpd('POLY');return;}}
    if(target.closed&&c<=1){{a.dataset.lost='1';a.dataset.won='';rpCxUpd('POLY');return;}}
    if(c>0&&c<100){{a.dataset.won='';a.dataset.lost='';
     const pk=a.closest('.pick');
     if(!(pk&&rpInPlay(pk))){{a.dataset.cents=c;if(r0){{r0.c=c;r0.ts=Date.now();}}a.innerHTML=a.innerHTML.replace(/POLY( [+-]?\d+| \d+c| \u2713| \u2717)?/,'POLY '+rpMLF(rpC2ML(c)));}}rpCxUpd('POLY');rpQuoteMut(pk);  /* tester Sep 26: POLY tick recomputes too */
}}
    return;
   }}}}
  }}).catch(()=>{{}});
 }});
}}catch(e){{}}}}
function rpQuoteMut(pk){{if(!pk)return;rpBestStar(pk);rpLineShop(pk);}}  /* ONE shared derivation (tester Sep 26 index tick defect): every canonical price change - KAL, POLY, ESPN - recomputes range AND star on the affected pick in the same callback; range hides itself when prices converge */
/* header .odds = locked entry price, FROZEN on every surface (tester ruling Sep 26): no ticker and no refresh ever writes .pick .odds - live market lives in chips + range only */
/* rpEspnTick RETIRED Sep 26 (his instant spec): odds ride the 2s rpLsTick scoreboard pass - zero extra fetches */
function rpKalTick(){{try{{
 document.querySelectorAll('a[data-kalticker][data-kalside]').forEach(function(a){{
  if(!a.dataset.kalticker||!a.dataset.kalside)return;
  const r0=rpMkt(a);if(r0&&r0.ph==='last_pre_game')return;  /* canonical record: frozen phases never tick (phase = event status, not fetch time) */
  const _pk0=a.closest('.pick');if(_pk0&&rpInPlay(_pk0))return;  /* regression gate Sep 26: proxies measured unusable (allorigins 500@14.7s/522, codetabs 522/503, corsproxy 401) - KAL ticks PREGAME-ONLY until the api.rix-picks.com relay lands; in-play dims honestly, never re-stamps */
  const u='https://api.elections.kalshi.com/trade-api/v2/markets/'+a.dataset.kalticker+'-'+a.dataset.kalside+'?_='+Date.now();
  fetch('https://api.allorigins.win/raw?url='+encodeURIComponent(u)).then(r=>r.json()).then(function(j){{
   const m=j&&j.market;if(!m)return;
   window.__rpKalOk=Date.now();
   if(m.result==='yes'){{a.dataset.won='1';a.dataset.lost='';rpCxUpd('KAL');return;}}
   if(m.result==='no'){{a.dataset.lost='1';a.dataset.won='';rpCxUpd('KAL');return;}}
   const d=parseFloat(m.yes_ask_dollars);if(!(d>0&&d<=1))return;  /* $1.00 ask is a real quote (Sep 26 root fix) */
   const c=Math.round(d*100);
   /* URF dormant-market gate (swamp Sep 27: Jeanty/Jones/Irving early tickets quoted >6h stale):
      a market whose updated_time is >6h old must never re-stamp a bare live price - it wears the
      carded price + as-of label, same rule as the updChips per-ticker 6h gate. */
   let stale=false;try{{if(m.updated_time){{const age=Date.now()-Date.parse(m.updated_time);stale=!(age>=0&&age<=21600000);}}}}catch(e){{}}
   a.dataset.won='';a.dataset.lost='';
   const pk=a.closest('.pick');
   if(!(pk&&rpInPlay(pk))){{
    if(stale){{
     if(typeof RP_CARDED_TM!=='undefined'&&RP_CARDED_TM&&a.innerHTML.indexOf('\u00b7')<0){{a.innerHTML=a.innerHTML.replace(/KAL( [+-]?\d+| \d+c)?/,'KAL$1 \u00b7 '+RP_CARDED_TM);}}
    }}else{{
     a.dataset.cents=c;if(r0){{r0.c=c;r0.ts=Date.now();}}a.innerHTML=a.innerHTML.replace(/KAL( [+-]?\d+| \d+c| \u2713| \u2717)?/,'KAL '+rpMLF(rpC2ML(c)));
    }}
   }}rpCxUpd('KAL');
    rpQuoteMut(pk);  /* tester Sep 26: pre-game ticks recompute too - the in-play-only gate left the stale star/range live */
  }}).catch(()=>{{}}); /* graceful fallback: relay/API failure keeps last build price */
 }});
}}catch(e){{}}}}
window.__rpPolyOk=window.__rpKalOk=window.__rpEspnOk=Date.now();
rpPolyTick();rpKalTick();setInterval(rpKalTick,60000);  /* regression gate Sep 26: pregame-only KAL at 60s via proxy (15s+ latency makes 5s pointless and abusive); relay restores live cadence when the PAT lands */
// sportsbook prices ride the 15-min Action rebuild (refresh.sh): pull the rebuilt page and swap
// book chip prices + combo price spans in place. KAL/POLY stay on the 60s tick above.
function rpPageRefresh(){{try{{
 fetch(location.pathname+'?r='+Date.now(),{{cache:'no-store'}}).then(function(r){{return r.ok?r.text():null;}}).then(function(t){{
  if(!t)return;  /* swamp Sep 27 re-test (1b): a failed/empty fetch skips the cycle silently - a transient CDN error page must never parse as an empty card and force a reload loop */
  const _mm=t.match(/let RP_MARKETS=(\[.*?\]);/);if(!_mm)return;  /* not a built page (malformed/short/error HTML) - skip the cycle, never reload */
  const doc=new DOMParser().parseFromString(t,'text/html');
  /* J-107 (Sep 26): bind by stable pick key (data-gpk, else data-room), never DOM position -
     rpFinalsTop reorders the live DOM, so index-mapping sprayed another game's prices onto
     the wrong pick with the wrong link. Price and href/data-sb update together. */
  const nmap={{}};
  doc.querySelectorAll('.pick').forEach(function(np){{
   const k=(np.dataset.gpk||'')+'@'+(np.dataset.room||'');
   if(k==='@')return;  /* no stable key - never guess */
   if(nmap[k]){{console.warn('rpRefresh duplicate key',k);nmap[k]=null;}}else{{nmap[k]=np;}}  /* collision: bind neither, never overwrite */
  }});
  /* swamp Sep 27 (pre-deploy): a tab left open across a card rollover must not keep showing the
     old card - if the stable pick-key set (gpk@room) or the slate date label differs between the
     live DOM and the fetched page, force a full reload BEFORE any merge/record reuse. */
  const curKeys=[...document.querySelectorAll('.pick')].map(function(x){{return (x.dataset.gpk||'')+'@'+(x.dataset.room||'');}}).filter(function(k){{return k!=='@';}}).sort().join('|');
  const newKeys=[...doc.querySelectorAll('.pick')].map(function(x){{return (x.dataset.gpk||'')+'@'+(x.dataset.room||'');}}).filter(function(k){{return k!=='@';}}).sort().join('|');
  if(curKeys!==newKeys){{location.reload();return;}}
  const cd0=document.querySelector('.status,.rpdate'),nd0=doc.querySelector('.status,.rpdate');
  if(cd0&&nd0&&cd0.textContent.trim()!==nd0.textContent.trim()){{location.reload();return;}}
  /* Sep 26 (data auditor): same membership rule for the combo row - a combo chip added/removed
     between builds forces a full reload, same as per-pick chips. */
  const ccmb=document.getElementById('rpParlayChips'),ncx=doc.getElementById('rpParlayChips');
  if(ccmb&&ncx){{
   const c1=[...ccmb.querySelectorAll('[data-book]')].map(a=>a.dataset.book).sort().join(',');
   const c2=[...ncx.querySelectorAll('[data-book]')].map(a=>a.dataset.book).sort().join(',');
   if(c1!==c2){{location.reload();return;}}
  }}
  /* swamp Sep 27 re-test (1a): per-pick chip membership validated in a pre-scan, and the canonical
     RP_MARKETS record swaps ONLY after every mismatch guard passes - no interval where an old tab
     wears the new card's markets before reload fires. */
  const rpSig=function(root){{return [...root.querySelectorAll('[data-book]')].map(a=>a.dataset.book+(a.dataset.template?':t':'')).sort().join(',');}};
  let memBad=false;
  document.querySelectorAll('.pick').forEach(function(pk){{
   const k=(pk.dataset.gpk||'')+'@'+(pk.dataset.room||'');const np=nmap[k];if(!np)return;  /* null = absent or collided */
   if(rpSig(pk)!==rpSig(np))memBad=true;
  }});
  if(memBad){{location.reload();return;}}
  try{{RP_MARKETS=JSON.parse(_mm[1]);}}catch(e){{}}  /* canonical records travel with the rebuilt page - refresh never desyncs display from truth */
  document.querySelectorAll('.pick').forEach(function(pk){{
   const k=(pk.dataset.gpk||'')+'@'+(pk.dataset.room||'');const np=nmap[k];if(!np)return;  /* null = absent or collided */
   /* Sep 26 (hunter #10): data-only refresh can never ADD a newly verified chip or REMOVE a retired
      one - a membership change between served and new build forces a full reload instead. */
   /* Sep 26 refresh-loop fix: membership = [data-book] ANY tag + template status. rpTapify turns
      template spans into anchors once state is known; tag alone is not membership, so an upgraded
      live DOM vs a fresh static build must compare equal. A real add/retire/kind-change still reloads. */
   const curB=rpSig(pk),newB=rpSig(np);
   if(curB!==newB){{location.reload();return;}}
   pk.querySelectorAll('[data-book]').forEach(function(a){{
    const b=a.dataset.book;
    /* any-tag counterpart: priced spans reprice too (state unknown); an upgraded anchor reprices
       from its static span counterpart (state known). Label + record attrs travel as one unit
       (canonical record, Sep 26) - display and truth never desync. */
    const na=np.querySelector('[data-book="'+b+'"]');if(!na)return;
    if(!na.textContent.match(/([+-]\d+|\d+c)/)){{  /* tester Sep 26 re-hold: priced->unpriced is a FIRST-CLASS transition - quote, route and record come OFF atomically; a stale price never lingers tappable */
     a.innerHTML=na.innerHTML;a.classList.add('rpunpriced');
     if(na.dataset.cents)a.dataset.cents=na.dataset.cents;else delete a.dataset.cents;
     if(na.dataset.mr)a.dataset.mr=na.dataset.mr;else delete a.dataset.mr;
     if(a.tagName==='A'){{const sp=document.createElement('span');for(const at of a.attributes)sp.setAttribute(at.name,at.value);sp.innerHTML=a.innerHTML;sp.classList.add('rpnontap');sp.removeAttribute('href');sp.removeAttribute('onclick');sp.removeAttribute('target');sp.removeAttribute('rel');a.replaceWith(sp);}}
     return;
    }}
    a.classList.remove('rpunpriced');
    a.innerHTML=na.innerHTML;
    if(na.dataset.cents)a.dataset.cents=na.dataset.cents;else delete a.dataset.cents;
    if(na.dataset.mr)a.dataset.mr=na.dataset.mr;else delete a.dataset.mr;
    if(na.dataset.sbt){{  /* template chip: price and templated destination travel together; never a homepage route */
     if(a.tagName==='A'){{a.dataset.sb=na.dataset.sbt;if(window.rpSt)a.href=na.dataset.sbt.replaceAll('{{state}}',window.rpSt.toLowerCase());}}
     else a.dataset.sbt=na.dataset.sbt;
    }}else{{
     if(a.tagName==='A'&&na.href)a.href=na.href;
     if(na.dataset.sb)a.dataset.sb=na.dataset.sb;
    }}
   }});
   rpBestStar(pk);
  }});
  const cc=document.getElementById('rpParlayChips');const nc=doc.getElementById('rpParlayChips');
  if(cc&&nc){{cc.querySelectorAll('[data-book]').forEach(function(s){{
   const b=s.dataset.book;
   const ns=nc.querySelector('[data-book="'+b+'"]');
   if(ns){{if(ns.textContent.match(/([+-]\d+|\d+c)/)){{s.classList.remove('rpunpriced');s.innerHTML=ns.innerHTML;if(ns.dataset.cents)s.dataset.cents=ns.dataset.cents;else delete s.dataset.cents;if(ns.dataset.mr)s.dataset.mr=ns.dataset.mr;else delete s.dataset.mr;
    if(ns.dataset.sbt){{if(s.tagName==='A'){{s.dataset.sb=ns.dataset.sbt;if(window.rpSt)s.href=ns.dataset.sbt.replaceAll('{{state}}',window.rpSt.toLowerCase());}}else s.dataset.sbt=ns.dataset.sbt;}}
    else{{if(s.tagName==='A'&&ns.href)s.href=ns.href;if(ns.dataset.sb)s.dataset.sb=ns.dataset.sb;}}
    if(ns.dataset.pm)s.dataset.pm=ns.dataset.pm;}}
    else{{s.innerHTML=ns.innerHTML;s.classList.add('rpunpriced');if(ns.dataset.mr)s.dataset.mr=ns.dataset.mr;else delete s.dataset.mr;if(ns.dataset.cents)s.dataset.cents=ns.dataset.cents;else delete s.dataset.cents;if(s.tagName==='A'){{const sp2=document.createElement('span');for(const at2 of s.attributes)sp2.setAttribute(at2.name,at2.value);sp2.innerHTML=s.innerHTML;sp2.classList.add('rpnontap');sp2.removeAttribute('href');sp2.removeAttribute('onclick');sp2.removeAttribute('target');sp2.removeAttribute('rel');s.replaceWith(sp2);}}}}}}  /* Sep 26: destination travels with price - no stale parlay links; template chips swap data-sbt/data-sb, never a homepage route */
  }});rpCxStar();}}
 }}).catch(()=>{{}});
}}catch(e){{}}}}
setInterval(rpPageRefresh,60000);
</script>
<script src="myprofile.js?v={{build_sha}}"></script><script data-goatcounter="https://rixpicks.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script><script>window.rpGcEvent=function(p,flag){{var pend=window.__rpGcPend=window.__rpGcPend||{{}};if(pend[p])return;pend[p]=1;var n=0;var go=function(){{try{{if(flag&&localStorage.getItem(flag)){{pend[p]=0;return;}}if(window.goatcounter&&goatcounter.count){{goatcounter.count({{path:p,event:true}});if(flag){{try{{localStorage.setItem(flag,'1');}}catch(e){{}}}}pend[p]=0;}}else if(n++<20)setTimeout(go,1500);else pend[p]=0;}}catch(e){{pend[p]=0;if(n++<20)setTimeout(go,3000);}}}};go();}};</script></div>{_V2_SCRIPTS}</body></html>'''

def _pt_label(iso):
    try:
        import datetime as _dt
        from zoneinfo import ZoneInfo
        d=_dt.datetime.fromisoformat(iso.replace('Z','+00:00')).astimezone(ZoneInfo('America/Los_Angeles'))
        return d.strftime('%-I:%M %p PT')
    except Exception: return ''

def build_game_pages(man, css, build_sha):
    "Per-game live-market pages (user, Sep 25 12:11 PM)."
    tmpl=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'game_page_template.html')).read()
    pages={}
    NAME2KEY={'espnbet':'TSB','draftkings':'DK','fanduel':'FD','thescore':'TSB','hardrockbet':'HR'}  # legacy 'espnbet' key = theScore data (U-GEO-003); _rsseen below guarantees one row per ARM
    RP_CONSTS=('const RP_FD='+json.dumps(RP_FD)+';const RP_DK='+json.dumps(RP_DK)+';\n'
        'const RP_L={FD:RP_FD,DK:RP_DK,MGM:'+json.dumps(RP_MGM)+',B365:'+json.dumps(RP_B365)+',FAN:'+json.dumps(RP_FAN)+',TSB:'+json.dumps(RP_TSB)+',HR:'+json.dumps(RP_HR)+',BR:'+json.dumps(RP_BR)+'};const RP_LEGAL_STATE='+json.dumps(TABLE,sort_keys=True)+';const RP_LEGAL_BI='+json.dumps(RP_LEGAL_BI_DATA,sort_keys=True)+';const RP_PM_DEFAULT=[\'KAL\',\'POLY\',\'DKP\',\'FDP\'];')
    STATE_OPTS=''.join('<option value="%s">%s</option>'%(c,n) for c,n in RP_STATES)
    def rt(short,url,tmpl_flag):
        # Sep 26: href never carries a raw {state} (context menu/no-JS 404s) - base domain href,
        # template lives in data-sb, rpGo substitutes the verified state at tap time.
        t=' data-template="1"' if tmpl_flag else ''
        href=('https://www.'+BKDOM[short]) if tmpl_flag else url
        return 'data-book="%s" data-sb="%s"%s onclick="return rpRoute(event,this)" href="%s" target="_blank" rel="noreferrer"'%(short,html.escape(url),t,html.escape(href))
    def rtc(short,url,lbl,style=''):
        # verified market-level link or priced inert span (J-112) - a bare homepage is never an actionable price
        generic=re.match(r'^https://www\.[a-z0-9.-]+/?$',url or '') is not None
        if generic:
            return '<span class="rpnontap" data-book="'+short+'"'+(' style="%s"'%style if style else '')+'>'+lbl+'</span>'
        return '<a '+rt(short,url,'{state}' in url)+(' style="%s"'%style if style else '')+'>'+lbl+'</a>'
    for p in man.get('picks',[]):
        g=p.get('game') or {}
        if not g: continue
        away,home=g.get('away',''),g.get('home','')
        side=p.get('side','away')
        carded_team=g.get(side,'')
        _uw=_is_underway(g)
        _sk=f"{away}|{home}|{(g.get('commence') or '')[:10]}"
        _shk=(SHIPPED.get(_sk) or {}) if _uw else {}
        _gph='last_pre_game' if _uw else 'pre_game'
        _fqt=_pt_label(((_shk.get('Kalshi') or _shk.get('Polymarket') or {}).get('ts')) or '') if _uw else ''
        _mkthdr=('Frozen pre-game prices%s - both sides' % (' - '+_fqt if _fqt else '')) if _uw else 'Live markets - both sides'
        _foot=('Prices shown are frozen pre-game references%s - in-play markets move without us. Tap a price to open the live market.' % (' as of '+_fqt if _fqt else '')) if _uw else 'Prices update live: Kalshi ticks every 60s; Polymarket & sportsbook prices refresh with each page rebuild. Tap a price to open the market.'
        _PM=[]
        _COLL[0]=_PM  # chips() below must index into THIS page's record list
        def _pmk(src,ev='',mkt='',side_='',ml=None,cents=None,link='',lv='verified',st='ok'):
            _PM.append({'src':src,'ev':ev,'mkt':mkt,'side':side_,'ml':ml,'c':cents,'link':link,'ph':_gph,'ts':'','lv':lv,'st':st})
            return ' data-mr="%d"'%(len(_PM)-1)
        rows_html=[]
        books_present=[]
        hrow={'away':away,'home':home}
        pr=sel_books(pre.get((away,home)), g) or {}
        _rsseen=set()
        for key,short in NAME2KEY.items():
            if short in _rsseen: continue  # one row per arm: a feed carrying both legacy and current keys never doubles
            rec=pr.get(key) or {}
            aml,hml=rec.get('away_ml'),rec.get('home_ml')
            if aml is None and hml is None: continue
            _rsseen.add(short)
            alink=rec.get('away_link') or rec.get('event') or ('https://www.'+BKDOM[short])
            hlink=rec.get('home_link') or rec.get('event') or ('https://www.'+BKDOM[short])
            a_lbl=('%+d'%aml) if aml is not None else '-'
            h_lbl=('%+d'%hml) if hml is not None else '-'
            if short=='FD':
                # generic Predicts homepage never substantiates a displayed selection (complaint-lens via main 9/26) - exact market url only
                _fdpu=(p.get('fdp') or {}).get('url')
                _rowpm=(' data-pm="'+html.escape(_fdpu)+'"') if _fdpu else ''
            elif short=='DK' and (p.get('dkp') or {}).get('url'):
                _rowpm=' data-pm="'+html.escape(p['dkp']['url'])+'"'
            else:
                _rowpm=''
            # Sep 26 swamp ruling: a side without its own selection link must not carry the shared
            # event url under a side-specific price - inert price, single 'view game' route per row.
            _aevt=not rec.get('away_link'); _hevt=not rec.get('home_link')
            if _aevt or _hevt:
                _evl=rec.get('event') or ''
                if not _evl:
                    _fn={s2:n2 for n2,s2 in BOOKS}.get(short,short)
                    _se=SHIPPED.get(f"{away}|{home}|{(g.get('commence') or '')[:10]}",{}).get(_fn)
                    if _se and not _stale_carryover(_fn,_se.get('link'),g): _evl=_se.get('link') or ''
                _evl=_evl or alink
                rows_html.append('<div class="mrow" data-book="'+short+'"'+_rowpm+'>'+bkimg(short)+'<span class="bk">'+short+'</span>'
                    '<span class="side">'+html.escape(away)+' <span class="pr">'+a_lbl+'</span></span>'
                    '<span class="side" style="text-align:right">'+html.escape(home)+' <span class="pr">'+h_lbl+'</span></span>'
                    +rtc(short,_evl,'view game')+'</div>')
                hrow[short.lower()+'_a']=aml; hrow[short.lower()+'_h']=hml
                books_present.append(short)
                continue
            rows_html.append('<div class="mrow" data-book="'+short+'"'+_rowpm+'>'+bkimg(short)+'<span class="bk">'+short+'</span>'
                '<span class="side">'+rtc(short,alink,html.escape(away))+'</span><span class="pr">'+rtc(short,alink,a_lbl)+'</span>'
                '<span class="side" style="text-align:right">'+rtc(short,hlink,html.escape(home),'text-align:right')+'</span><span class="pr">'+rtc(short,hlink,h_lbl)+'</span></div>')
            hrow[short.lower()+'_a']=aml; hrow[short.lower()+'_h']=hml
            books_present.append(short)
        stt=pr.get('state_templates') or {}
        for key,short in (('betmgm','MGM'),('betrivers','BR')):
            rec=stt.get(key) or {}
            aml,hml=rec.get('away_ml'),rec.get('home_ml')
            if aml is None and hml is None: continue
            link=rec.get('event') or ''
            if not link:
                # Sep 26 hunter: the index chips hold verified exact event routes via the SHIPPED
                # ledger - the game-page row uses the SAME verified route; homepage only when no
                # event url exists at all.
                _fn='BetMGM' if key=='betmgm' else 'BetRivers'
                _se=SHIPPED.get(f"{away}|{home}|{(g.get('commence') or '')[:10]}",{}).get(_fn)
                if _se and not _stale_carryover(_fn,_se.get('link'),g): link=_se.get('link') or ''
            link=link or ('https://www.'+BKDOM[short])
            a_lbl=('%+d'%aml) if aml is not None else '-'
            h_lbl=('%+d'%hml) if hml is not None else '-'
            # Sep 26 swamp ruling: MGM/BR carry EVENT-ONLY urls - both sides tapping the same event page
            # implies outcome prefill the route can't deliver. Side prices render inert; the event route
            # becomes ONE 'view game' label per row until verified side-specific selection ids exist.
            rows_html.append('<div class="mrow" data-book="'+short+'">'+bkimg(short)+'<span class="bk">'+short+'</span>'
                '<span class="side">'+html.escape(away)+' <span class="pr">'+a_lbl+'</span></span>'
                '<span class="side" style="text-align:right">'+html.escape(home)+' <span class="pr">'+h_lbl+'</span></span>'
                +rtc(short,link,'view game')+'</div>')
            hrow[short.lower()+'_a']=aml; hrow[short.lower()+'_h']=hml
            books_present.append(short)
        # Kalshi full board (user, Sep 25 12:19 PM): both sides, live-ticked. Fallback: single-side tap row.
        kal_html=''
        if p.get('kalshi'):
            kurl=p['kalshi']['url']; tick=kurl.rstrip('/').split('/')[-1].upper()
            board=[]; et=tick; kvol=0.0
            if _uw:
                # in play (tester caveat on build 1790470472, Sep 26): pre-game snapshots LOCK at kickoff
                # and never refresh from in-play reads - the live-board branch below is pre-game only.
                # Snapshot source: shipped-ledger cents, then manifest ship cents; the other side is
                # honestly unpriced. No snapshot at all -> the picked side ships honestly unpriced too.
                _kc=((_shk.get('Kalshi') or {}).get('cents')) or (p.get('kalshi') or {}).get('cents')
                kal_html=('<div class="mrow" data-book="KAL">'+bkimg('KAL')+'<span class="bk">KAL</span>'
                    '<span class="side"><a '+rt('KAL',kurl,False)+'>'+html.escape(carded_team)+'</a></span>'
                    '<span class="pr"><a data-kalticker="'+tick+'" data-kalside="'+html.escape(p['kalshi'].get('team',''))+'"'+(f' data-cents="{round(_kc)}"' if _kc else '')+_pmk('Kalshi',tick,tick,side,cents=_kc,link=kurl,st=('ok' if _kc else 'unknown'))+' '+rt('KAL',kurl,False)+'>'+(f'KAL {c2ml(_kc)}' if _kc else 'KAL')+'</a></span>'
                    '<span class="side" style="text-align:right;color:#8a8f98">pre-game snapshot</span><span class="pr"></span></div>')
                hrow['kal_a']=_kc if side=='away' else None
                hrow['kal_h']=_kc if side=='home' else None
                books_present.append('KAL')
        if p.get('kalshi') and not kal_html and not _uw:
            kurl=p['kalshi']['url']; tick=kurl.rstrip('/').split('/')[-1].upper()
            board=[]; et=tick; kvol=0.0
            try:
                import urllib.request
                # URL may end at the event ticker or at a -SIDE market ticker: try the segment as-is, then stripped.
                for cand in (tick, tick.rsplit('-',1)[0]):
                    try:
                        req=urllib.request.Request('https://api.elections.kalshi.com/trade-api/v2/markets?event_ticker=%s&status=open&limit=50'%cand,headers={'User-Agent':'Mozilla/5.0'})
                        with urllib.request.urlopen(req,timeout=10) as r: km=json.load(r)
                        ms=[m for m in km.get('markets',[]) if str(m.get('ticker','')).startswith(cand+'-')]
                        if ms:
                            et=cand
                            for m in ms:
                                try: ya=float(m.get('yes_ask_dollars') or 0)
                                except Exception: continue
                                if not (0<ya<1): continue
                                sub=str(m.get('yes_sub_title') or m.get('title') or '')
                                suf=str(m.get('ticker','')).rsplit('-',1)[-1]
                                try: kv=float(m.get('volume_dollars') or 0)
                                except Exception: kv=0
                                kvol+=kv
                                board.append((sub,str(m.get('ticker','')),suf,int(round(ya*100))))
                            break
                    except Exception: continue
            except Exception: board=[]
            def kmatch(team):
                toks=[t for t in team.lower().split() if len(t)>2]
                for sub,tk,suf,c in board:
                    sl=sub.lower()
                    if any(t in sl for t in toks): return tk,suf,c
                return None
            am=kmatch(away); hm=kmatch(home)
            # two-market event: if one side matched, the other market is the other side (handles 'A\'s' vs 'Athletics')
            if am and not hm and len(board)==2:
                o=[b for b in board if b[1]!=am[0]]
                if o: hm=(o[0][1],o[0][2],o[0][3])
            if hm and not am and len(board)==2:
                o=[b for b in board if b[1]!=hm[0]]
                if o: am=(o[0][1],o[0][2],o[0][3])
            base=kurl if et==tick else kurl.rsplit('-',1)[0]
            # LOCKED-PRICE BAKE (Sep 27 7:47, tester NO-GO): the picked side's baked price is the
            # LOCKED card price from the manifest, never the live board quote pulled at build time.
            # Unpicked side may show the live quote; the card side is always the lock.
            _lk=(p.get('kalshi') or {}).get('cents')
            if _lk and am and hm:
                if side=='away': am=(am[0],am[1],_lk)
                else: hm=(hm[0],hm[1],_lk)
            if am and hm:
                kal_html=('<div class="mrow" data-book="KAL">'+bkimg('KAL')+'<span class="bk">KAL</span>'
                    '<span class="side"><a '+rt('KAL',base+'-'+am[1].lower(),False)+'>'+html.escape(away)+'</a></span>'
                    '<span class="pr"><a data-prc="1" data-kalmkt="'+am[0]+'" data-cents="'+str(round(am[2]))+'"'+_pmk('Kalshi',et,am[0],'away',cents=am[2],link=kurl)+' '+rt('KAL',base+'-'+am[1].lower(),False)+'>'+c2ml(am[2])+'</a></span>'
                    '<span class="side" style="text-align:right"><a '+rt('KAL',base+'-'+hm[1].lower(),False)+'>'+html.escape(home)+'</a></span>'
                    '<span class="pr"><a data-prc="1" data-kalmkt="'+hm[0]+'" data-cents="'+str(round(hm[2]))+'"'+_pmk('Kalshi',et,hm[0],'home',cents=hm[2],link=kurl)+' '+rt('KAL',base+'-'+hm[1].lower(),False)+'>'+c2ml(hm[2])+'</a></span></div>')
                hrow['kal_a']=am[2]; hrow['kal_h']=hm[2]
            else:
                kside=html.escape(p['kalshi'].get('team',''))
                kal_html=('<div class="mrow" data-book="KAL">'+bkimg('KAL')+'<span class="bk">KAL</span>'
                    '<span class="side"><a '+rt('KAL',kurl,False)+'>'+html.escape(carded_team)+'</a></span>'
                    '<span class="pr"><a data-kalticker="'+tick+'" data-kalside="'+kside+'" data-cents="'+str(round(p['kalshi']['cents']))+'"'+_pmk('Kalshi',tick,tick,side,cents=p['kalshi']['cents'],link=kurl)+' '+rt('KAL',kurl,False)+'>KAL '+str(c2ml(p['kalshi']['cents']))+'</a></span>'
                    '<span class="side" style="text-align:right;color:#8a8f98">full board on Kalshi</span><span class="pr"></span></div>')
                cc=p['kalshi']['cents']
                hrow['kal_a']=cc if side=='away' else None
                hrow['kal_h']=cc if side=='home' else None
            books_present.append('KAL')
        # Polymarket full board (user, Sep 25 12:19 PM): both sides, live-ticked. Fallback: single-side tap row.
        poly_html=''
        if p.get('polymarket'):
            _gs=poly_event_slug(p['polymarket']['url']) or ''
            _usv=(p.get('polymarket_us') or {})
            web=(_usv.get('url') if _usv.get('verified') else '') or (_poly_us_url(_gs) if _gs else '')
            slug=poly_event_slug(p['polymarket']['url']) or ''
            sub=poly_sub(p['polymarket']['url']) or ''
            akw=away.split()[-1]; hkw=home.split()[-1]
            if _uw:
                # in play (tester caveat on build 1790470472, Sep 26): frozen pre-game snapshot on the
                # picked side only - shipped-ledger cents, then manifest polycents; NEVER a live
                # in-play gamma read. No snapshot -> both sides honestly unpriced.
                _pf=((_shk.get('Polymarket') or {}).get('cents')) or p.get('polycents')
                ca=(_pf if side=='away' else None)
                chv=(_pf if side=='home' else None)
            else:
                ca=(poly_price(p['polymarket']['url'],akw) if _POLY_US_PRICED else None); chv=(poly_price(p['polymarket']['url'],hkw) if _POLY_US_PRICED else None)  # P1
            pvol=0.0  # gateway.polymarket.us events carry NO volume field - pvol stays 0 on authed
            # reads (reported to main Sep 27); the legacy gamma volume probe is retired with the public feed.

            if ca or chv:
                la=c2ml(ca) if ca else 'POLY'  # board price cells are price-only (390px fit); bare book name when the side was never priced
                lh=c2ml(chv) if chv else 'POLY'
                pa='data-book="POLY" data-sb="'+html.escape(web)+'" data-app="'+html.escape(web)+'" onclick="return rpRoute(event,this)" href="'+html.escape(web)+'" target="_blank" rel="noreferrer"'
                poly_html=('<div class="mrow" data-book="POLY">'+bkimg('POLY')+'<span class="bk">POLY</span>'
                    '<span class="side"><a '+pa+'>'+html.escape(away)+'</a></span>'
                    '<span class="pr"><a data-prc="1" data-polyslug="'+html.escape(slug)+'" data-polysub="'+html.escape(sub)+'" data-polykw="'+html.escape(akw)+'"'+(' data-cents="'+str(round(ca))+'"' if ca else '')+(_pmk('Polymarket',slug,sub or slug,'away',cents=ca,link=web,st=('ok' if ca else 'unknown')))+' '+pa+'>'+la+'</a></span>'
                    '<span class="side" style="text-align:right"><a '+pa+'>'+html.escape(home)+'</a></span>'
                    '<span class="pr"><a data-prc="1" data-polyslug="'+html.escape(slug)+'" data-polysub="'+html.escape(sub)+'" data-polykw="'+html.escape(hkw)+'"'+(' data-cents="'+str(round(chv))+'"' if chv else '')+(_pmk('Polymarket',slug,sub or slug,'home',cents=chv,link=web,st=('ok' if chv else 'unknown')))+' '+pa+'>'+lh+'</a></span></div>')
                hrow['poly_a']=ca; hrow['poly_h']=chv
            else:
                kw=p['name'].split()[0]
                cents=None if (_uw or not _POLY_US_PRICED) else poly_price(p['polymarket']['url'],kw)  # P1
                if _usv.get('verified') and _usv.get('cents'): cents=_usv['cents']  # 9/27: .us pick-side mid wins
                lbl=('POLY '+str(c2ml(cents))) if cents else 'POLY'
                poly_html=('<div class="mrow" data-book="POLY">'+bkimg('POLY')+'<span class="bk">POLY</span>'
                    '<span class="side"><a data-book="POLY" data-sb="'+html.escape(web)+'" data-app="'+html.escape(web)+'" onclick="return rpRoute(event,this)" href="'+html.escape(web)+'" target="_blank" rel="noreferrer">'+html.escape(carded_team)+'</a></span>'
                    '<span class="pr"><a data-polyslug="'+html.escape(slug)+'" data-polysub="'+html.escape(sub)+'" data-polykw="'+html.escape(kw)+'"'+_pmk('Polymarket',slug,sub or slug,side,cents=cents,link=web,st=('ok' if cents else 'unknown'))+' data-book="POLY" data-sb="'+html.escape(web)+'" data-app="'+html.escape(web)+'" onclick="return rpRoute(event,this)" href="'+html.escape(web)+'" target="_blank" rel="noreferrer">'+lbl+'</a></span>'
                    '<span class="side" style="text-align:right;color:#8a8f98">full board on Polymarket</span><span class="pr"></span></div>')
                hrow['poly_a']=cents if side=='away' else None
                hrow['poly_h']=cents if side=='home' else None
            if not _POLY_US_PRICED: poly_html=re.sub(r' data-poly(slug|sub|kw)="[^"]*"','',poly_html)  # P1: kill client tick on .us-linked rows
            books_present.append('POLY')
        # Per-book price-history charts (user, Sep 25 12:20 PM): Kalshi-style line, one per platform.
        lg=p.get('espn_league','')
        ma=_meta_for(lg,away); mh=_meta_for(lg,home)
        abbr_a=ma.get('abbr') or away.split()[-1][:4].upper(); abbr_h=mh.get('abbr') or home.split()[-1][:4].upper()
        def tlogo(mm):
            u=mm.get('logo','')
            return '<img src="%s" alt="" style="width:54px;height:54px;object-fit:contain" onerror="this.remove()">'%html.escape(u) if u else ''
        matchup=('<div style="display:flex;align-items:center;justify-content:space-between;margin:16px 0 4px;text-align:center">'
            '<a href="team-%s.html" style="flex:1;text-decoration:none;color:inherit">%s<div style="font-weight:700;margin-top:4px">%s</div></a>'
            '<div style="flex:1.6"><div style="font-size:18px;font-weight:800">%s vs %s</div>'
            '<div class="sub" style="margin-top:3px">%s</div></div>'
            '<a href="team-%s.html" style="flex:1;text-decoration:none;color:inherit">%s<div style="font-weight:700;margin-top:4px">%s</div></a></div>'
            )%(team_slug(away),tlogo(ma),html.escape(abbr_a),
               html.escape(away.split()[-1] if len(away.split())>1 else away),html.escape(home.split()[-1] if len(home.split())>1 else home),
               html.escape(_pt_label(g.get('commence',''))),
               team_slug(home),tlogo(mh),html.escape(abbr_h))
        teamlinks=''
        charts_html=''
        # price-history graphs removed (user 9/26 10:58 iMessage via main) - no chart markup emitted
        HIST[(away,home)]=hrow
        ch=_chips_fn(p)
        espn=html.escape(p.get('espn_league',''))
        mkt='spread' if p.get('market')=='spread' else 'ml'
        when=_pt_label(g.get('commence',''))
        inst=game_instance(g)
        inst_lbl=(' ('+inst+')') if inst else ''
        if not _uw:
            _kal_rows='KAL' in books_present
            _pm_rows='POLY' in books_present
            _sb_rows=any(b not in ('KAL','POLY') for b in books_present)
            _bits=[]
            if _kal_rows and _pm_rows: _bits.append('Kalshi ticks every 60s; Polymarket refreshes each rebuild')
            elif _kal_rows: _bits.append('Kalshi ticks every 60s')
            elif _pm_rows: _bits.append('Polymarket refreshes each rebuild')
            if _sb_rows: _bits.append('sportsbook rows refresh with each page rebuild')
            _foot=('Prices update live: '+'; '.join(_bits)+'. Tap a price to open the market.') if _bits else 'No live market rows on this page yet - tap a pick chip to open the market.'
        page_html=tmpl
        for tok,val in [('__TITLE__',html.escape(away+' at '+home)),('__CSS__',css),('__NUM__',str(p['num'])),
            ('__INST__',inst_lbl),('__ESPN__',espn),('__AWAY__',html.escape(away)),('__HOME__',html.escape(home)),('__GPK__',_gpk_for(away,home,g.get('commence',''))[0]),('__AAB__',abbr_a),('__HAB__',abbr_h),  # swamp 9/26: gpk registry blanks on unregistered games rendered UNLABELED arbiter-only scores - abbrs come from the same verified _meta_for source as the matchup display
            ('__EID__',html.escape(str(g.get('eid') or ''))),('__COUNTED__',' data-counted="1"' if p.get('result') in ('WIN','LOSS','PUSH') else ''),
            ('__SIDE__',side),('__MKT__',mkt),('__NAME__',html.escape(p['name'])),('__UNITS__',html.escape(p.get('units',''))),
            ('__ODDS__',html.escape(p['odds'])),('__LOCK__',_stamp_html(p)),('__SUB__',html.escape(p.get('sub',''))),('__WHEN__',html.escape(when)),
            ('__MKTHDR__',_mkthdr),('__FOOTNOTE__',_foot),
            ('__CHIPS__',ch),('__MATCHUP__',matchup),('__TEAMLINKS__',teamlinks),('__ROWS__',''.join(rows_html)),('__KAL__',kal_html),('__POLY__',poly_html),('__ROOM__','g%s-%s'%(p['num'],(_pt_date(g.get('commence','')) or 'card'))),('__START__',g.get('commence','') or ''),
            ('__CHARTS__',charts_html),('__BUILD__',build_sha),('__RPARB__',ARB_INJECT),('__RPCONSTS__',RP_CONSTS+'\nlet RP_MARKETS='+json.dumps(_PM,separators=(',',':'))+';'),('__STATEOPTS__',STATE_OPTS),('__STATECODES__','['+','.join(chr(34)+c+chr(34) for c,_ in RP_STATES)+']')]:
            page_html=page_html.replace(tok,val)
        pages['game-%s.html'%p['num']]=page_html
        _COLL[0]=_MARKETS  # restore the index collector for the next build phase
    return pages


def team_slug(name):
    return re.sub(r'[^a-z0-9]+','-',name.lower()).strip('-')

def build_team_pages(man, css, build_sha):
    "Per-team stat pages, tappable from game pages (user, Sep 25 12:23 PM)."
    tmpl=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'team_page_template.html')).read()
    pages={}
    teams=set()
    for p in man.get('picks',[]):
        g=p.get('game') or {}
        if not g: continue
        teams.add((p.get('espn_league',''),g.get('away','')))
        teams.add((p.get('espn_league',''),g.get('home','')))
    info=dict(TEAM_META)
    for lg,name in sorted(teams):
        if not name: continue
        meta=info.get((lg,name)) or {}
        tid=meta.get('id'); abbr=meta.get('abbr',''); logo=meta.get('logo',''); rec=meta.get('record','')
        logo_html='<img src="%s" alt="" style="width:26px;height:26px;object-fit:contain;margin-right:8px" onerror="this.remove()">'%html.escape(logo) if logo else ''
        last5=[]; upcoming=[]; runs_for=0; runs_against=0; n_scored=0; streak=''
        if tid and lg:
            try:
                sch=_espn_get('https://site.api.espn.com/apis/site/v2/sports/%s/teams/%s/schedule'%(lg,tid))
                for ev in sch.get('events',[]):
                    comp=(ev.get('competitions') or [{}])[0]
                    st=(comp.get('status') or {}).get('type') or {}
                    comps=comp.get('competitors',[])
                    me=next((c for c in comps if str((c.get('team') or {}).get('id'))==str(tid)),{})
                    opp=next((c for c in comps if str((c.get('team') or {}).get('id'))!=str(tid)),{})
                    opp_nm=((opp.get('team') or {}).get('abbreviation')) or ((opp.get('team') or {}).get('displayName',''))
                    loc='vs' if me.get('homeAway')=='home' else '@'
                    dt=str(ev.get('date',''))[:10]
                    if st.get('completed'):
                        def _sc(c):
                            v=c.get('score',0)
                            if isinstance(v,dict): v=v.get('value',0)
                            try: return int(float(v))
                            except Exception: return None
                        ms=_sc(me); os_=_sc(opp)
                        if ms is None or os_ is None: continue
                        wl='W' if ms>os_ else ('L' if ms<os_ else 'T')
                        last5.append('%s %d-%d %s %s · %s'%(wl,ms,os_,loc,opp_nm,dt[5:]))
                        runs_for+=ms; runs_against+=os_; n_scored+=1
                    else:
                        import datetime as _d
                        if dt >= str(_d.date.today()) and len(upcoming)<3: upcoming.append('%s %s · %s'%(loc,opp_nm,dt[5:]))
                last5=last5[-5:]
                if last5:
                    streak=last5[-1][0]
                    k=1
                    for r in reversed(last5[:-1]):
                        if r[0]==streak: k+=1
                        else: break
                    streak=streak+str(k)
            except Exception: pass
        injuries=[]
        if tid and lg:
            try:
                inj=_espn_get('https://site.api.espn.com/apis/site/v2/sports/%s/teams/%s/injuries'%(lg,tid))
                items=inj.get('items') or inj.get('injuries') or []
                if items and isinstance(items[0],dict) and 'injuries' in items[0]:
                    flat=[]
                    for it in items: flat+=it.get('injuries') or []
                    items=flat
                for it in items[:6]:
                    ath=(it.get('athlete') or {}).get('displayName','?')
                    stat=str(it.get('status') or '')
                    det=str(it.get('type') or it.get('description') or '')[:60]
                    injuries.append('%s · %s%s'%(ath,stat,(' - '+det) if det else ''))
            except Exception: pass
        form_html=''.join('<div class="sub" style="padding:7px 0;border-bottom:1px solid rgba(127,127,127,.15)">%s</div>'%html.escape(r) for r in reversed(last5)) or '<div class="sub">No recent games found.</div>'
        avgs_html=('<div class="sub" style="padding:7px 0">Scored %.1f &middot; allowed %.1f per game over last %d</div>'%(runs_for/n_scored,runs_against/n_scored,n_scored)) if n_scored else '<div class="sub">Not enough recent games.</div>'
        next_html=''.join('<div class="sub" style="padding:7px 0;border-bottom:1px solid rgba(127,127,127,.15)">%s</div>'%html.escape(r) for r in upcoming) or '<div class="sub">No upcoming games listed.</div>'
        inj_html=''.join('<div class="sub" style="padding:7px 0;border-bottom:1px solid rgba(127,127,127,.15)">%s</div>'%html.escape(r) for r in injuries) or '<div class="sub">None reported.</div>'
        tagline=' · '.join(x for x in [rec and ('Record '+rec), streak and ('Streak '+streak)] if x)
        today=''
        for p in man.get('picks',[]):
            g=p.get('game') or {}
            if name in (g.get('away',''),g.get('home','')):
                opp=g.get('home') if g.get('away')==name else g.get('away')
                today='Today: %s %s · %s'%(('vs' if g.get('home')==name else '@'),opp,_pt_label(g.get('commence','')))
        page=tmpl
        for tok,val in [('__TEAM__',html.escape(name)),('__CSS__',css),('__RECORD__',html.escape(rec)),
            ('__TAGLINE__',html.escape(tagline)),('__TODAY__',html.escape(today)),('__LOGO__',logo_html),
            ('__LIVE__',''),('__FORM__',form_html),('__AVGS__',avgs_html),('__NEXT__',next_html),
            ('__INJURIES__',inj_html),('__BUILD__',build_sha)]:
            page=page.replace(tok,val)
        page=page.replace('<div class="pick">','<div class="pick" data-espn="%s" data-team="%s">'%(html.escape(lg),html.escape(name)),1)
        pages['team-%s.html'%team_slug(name)]=page
    return pages

import os
import time
build_sha=str(int(time.time()))
page=page.replace('{build_sha}',build_sha)
os.makedirs(os.path.dirname(out) or '.',exist_ok=True)
open(out,'w').write(scrub_shipped(page))
_css=page.split('<style>')[1].split('</style>')[0]

FUTURES_TMPL='''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RixPicks Futures</title><meta property="og:type" content="website"><meta property="og:url" content="https://rix-picks.com/futures.html"><meta property="og:title" content="&rsquo;RixPicks Futures"><meta property="og:description" content="Free picks, live tracked, every league in one place. Built in public - the record is never edited."><meta property="og:image" content="https://rix-picks.com/og-card.png"><meta name="twitter:card" content="summary_large_image"><style>__CSS__</style><style>body{overscroll-behavior-y:none}.wrap{min-height:101vh}</style><meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<script src="https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.page.js" defer></script>
<script>window.OneSignalDeferred=window.OneSignalDeferred||[];OneSignalDeferred.push(async function(OneSignal){try{await OneSignal.init({appId:"5e86ebe3-a135-4984-9623-db83a0f1840c",serviceWorkerPath:"OneSignalSDKWorker.js",serviceWorkerParam:{scope:(location.pathname.indexOf("/rixpicks/")===0?"/rixpicks/":"/")}  /* Sep 26: SW scope must match the ORIGIN's path root - rix-picks.com serves at /, github.io at /rixpicks/ */});try{OneSignal.Notifications.addEventListener("permissionChange",function(granted){if(granted&&!localStorage.getItem("rp_gc_push")){rpGcEvent("new-user-push","rp_gc_push");}});}catch(e){}}catch(e){}});</script>
<script>__RPARB__</script>
</head><body>
<div id="rpPull"></div>
<div class="wrap">
<h1><a href="index.html"><span class="tick">&rsquo;</span>RixPicks</a></h1>
<div class="status">Futures &middot; __COUNT__ picks &middot; live Kalshi tracking vs carded entry</div>
<div class="intro">Entry = the price we carded. Live = current market. Arrow shows movement since entry.</div>
<div class="intro"><span id="rpFutPre">Live quotes as of </span><span id="rpFutAsOf">__FUTASOF__</span><span id="rpFutTail"> PT &middot; refresh every ~5 min</span></div>
__ROWS__
<div id="rpFd" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;z-index:70;background:rgba(0,0,0,.78);align-items:flex-end;justify-content:center" onclick="if(event.target===this)rpFdClose()"><div id="rpFdBox" style="background:#000000;border-top:1px solid rgba(255,255,255,.14);border-radius:16px 16px 0 0;width:100%;max-width:520px;max-height:78vh;overflow-y:auto;padding:16px;color:#ECECF1"></div></div>
<div class="unitmath" style="margin-top:18px">Live prices via Kalshi &middot; refresh live &middot; build __BUILD__</div>
</div>
<script>
async function rpFutTick(){
 var bySlug={};
 document.querySelectorAll('.futrow[data-pslug]').forEach(function(r){
  if(!r.dataset.pslug)return;
  if(r.dataset.ksrc==='kalshi')return;  /* 9/27: Kalshi-sourced rows tick from Kalshi only */
  (bySlug[r.dataset.pslug]=bySlug[r.dataset.pslug]||[]).push(r);
 });
 var slugs=Object.keys(bySlug);
 await Promise.all(slugs.map(async function(slugS){
  try{
   var res=await fetch('https://gamma-api.polymarket.com/events?slug='+slugS+'&_='+Date.now());
   var ev=await res.json();
   if(!ev||!ev.length)return;
   var mkts=ev[0].markets||[];
   (window.__rpFutMkts=window.__rpFutMkts||{})[slugS]=mkts;
   bySlug[slugS].forEach(function(r){
    var kw=(r.dataset.pkw||'').toLowerCase();
    var m=null;
    for(var i=0;i<mkts.length;i++){if((mkts[i].question||'').toLowerCase().indexOf(kw)>=0){m=mkts[i];break;}}
    if(!m)return;
    var outs=[];try{outs=JSON.parse(m.outcomes||'[]');}catch(e){}
    var pr=[];try{pr=JSON.parse(m.outcomePrices||'[]');}catch(e){}
    var idx=0;
    for(var j=0;j<outs.length;j++){if(String(outs[j]).toLowerCase()==='yes'){idx=j;break;}}
    var p=parseFloat(pr[idx]);
    if(!(p>0&&p<1))return;window.__rpPolyOk=Date.now();(window.__rpPolyOkByFid=window.__rpPolyOkByFid||{})[r.dataset.fid]=Date.now();  /* swarm 7 HIGH: a row's liveness = ITS last valid parsed price - a response without the row's market stamps nothing */
    var c=p*100;
    var ml=c>=50?-Math.round(c/(100-c)*100):Math.round((100-c)/c*100);
    var el=r.querySelector('.futlive');
    el.textContent=(ml>0?'+':'')+ml;
    var entry=r.dataset.entry||'+0';
    var eMl=parseInt(entry.replace('+',''),10)||100;
    var eImp=eMl>0?100/(eMl+100):(-eMl)/((-eMl)+100);
    var mv=r.querySelector('.futmove');
    if(p>eImp+0.005){mv.innerHTML='<span style="color:#3ecf6f">&#9650; shortened from '+entry+' ('+(eImp*100).toFixed(1)+'% &rarr; '+c.toFixed(1)+'%)</span>';}
    else if(p<eImp-0.005){mv.innerHTML='<span style="color:#e5484d">&#9660; drifted from '+entry+' ('+(eImp*100).toFixed(1)+'% &rarr; '+c.toFixed(1)+'%)</span>';}
    else{mv.textContent='steady vs entry '+entry+' ('+(eImp*100).toFixed(1)+'%)';}
   });
  }catch(e){}
 }));
 try{var _nw=Date.now();document.querySelectorAll('.futrow').forEach(function(r){
  var polyDead=r.dataset.pslug&&(_nw-((window.__rpPolyOkByFid||{})[r.dataset.fid]||0))>30000;
  var kalDead=false;  /* 9/27: server-side futures_quotes.py owns Kalshi numbers (proxy tick removed per main) - rows re-seed each rebuild */
  var dm=!!(polyDead||kalDead);
  var lv=r.querySelector('.futlive');var mv=r.querySelector('.futmove');
  var hasKnown=!!((r.dataset.pslug&&(window.__rpPolyOkByFid||{})[r.dataset.fid])||(r.dataset.kalticker&&(window.__rpKalOkByFid||{})[r.dataset.fid]));  /* 'last known' requires a prior VERIFIED price (stamp present); a never-priced row has no last known - it is 'unavailable', never mislabeled */
  var dmK=dm&&hasKnown;
  if(lv){lv.style.opacity=dmK?'.55':'';var lk=r.querySelector('.futlk');if(dmK&&!lk){lv.insertAdjacentHTML('afterend','<span class="futlk" style="font-size:10px;color:#8a8f98;font-weight:600;letter-spacing:.04em;margin-left:6px;vertical-align:1px">last known</span>');}if(!dmK&&lk)lk.remove();}
  if(mv){mv.style.opacity=dmK?'.55':'';
   if(dm&&!mv.textContent){mv.textContent='live price unavailable - checking again shortly';}}  /* his 9/26 seamless bar: dead source = quiet dim + last confirmed data stays; 'never' is not a timestamp; no alarm copy */
  if(window.__rpFdFid&&r.dataset.fid===window.__rpFdFid&&!r.dataset.kalticker){rpFdRenderLive(r);}  /* tester regression Sep 26: the open sheet rides EVERY tick incl. failed fetches - one render point after the staleness decision; KAL-driven sheets untouched while the lane is dormant */
 });}catch(e6){}  /* honesty dims (approved Sep 26): >30s stale source dims AND labels the row's live line; stale never re-stamps or passes as live */
}
try{
 var rpFutIds2=[];
 document.querySelectorAll('.futrow').forEach(function(r){if(r.dataset.fid)rpFutIds2.push(r.dataset.fid);});
 localStorage.setItem('rp_fut_seen',JSON.stringify(rpFutIds2));
}catch(e){}
let rpPtrY=null,rpPtrPull=0,rpPtrOn=false;
document.addEventListener('touchstart',function(e){if(e.touches.length===1&&window.scrollY<2){rpPtrY=e.touches[0].clientY;rpPtrPull=0;rpPtrOn=true;}else{rpPtrOn=false;rpPtrY=null;rpPtrPull=0;}},{passive:true});
document.addEventListener('touchmove',function(e){if(!rpPtrOn||rpPtrY===null)return;const d=e.touches[0].clientY-rpPtrY;if(d>rpPtrPull)rpPtrPull=d;
 if(rpPtrPull>50){const el=document.getElementById('rpPull');if(el){el.style.transform='translateY(0)';el.textContent='release to refresh';}}},{passive:true});
function rpPtrEnd(){const el=document.getElementById('rpPull');
 if(rpPtrOn&&rpPtrPull>50){if(el){el.style.transform='translateY(0)';el.textContent='refreshing...';}
  Promise.resolve(rpFutTick()).then(function(){setTimeout(function(){if(el)el.style.transform='translateY(-100%)';},900);});}
 else if(el){el.style.transform='translateY(-100%)';}
 rpPtrOn=false;rpPtrY=null;rpPtrPull=0;}
document.addEventListener('touchend',rpPtrEnd,{passive:true});
document.addEventListener('touchcancel',rpPtrEnd,{passive:true});
rpFutTick();setInterval(rpFutTick,2000); /* approved Sep 26: POLY rides 2s (CORS *) */
const RP_BUILD='__BUILD__';
try{fetch('https://api.rix-picks.com/beacon',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({page:location.pathname,build:RP_BUILD,vw:innerWidth,vh:innerHeight,dpr:devicePixelRatio,ua:navigator.userAgent}),keepalive:true}).catch(function(){});}catch(e){}
window.addEventListener('pageshow',function(){try{
 if(sessionStorage.getItem('rp_reloaded')===RP_BUILD)return;
 fetch(location.pathname+'?cb='+Date.now(),{cache:'no-store'}).then(function(r){return r.text();}).then(function(t){
  var m=t.match(/RP_BUILD='([^']+)'/);var fresh=m?m[1]:null;
  if(fresh&&fresh!==RP_BUILD){sessionStorage.setItem('rp_reloaded',fresh);location.replace(location.pathname+'?v='+fresh);}
 }).catch(function(){});
}catch(e){}});
/* futures detail sheet: reasoning + live market depth */
function rpFdClose(){document.getElementById('rpFd').style.display='none';window.__rpFdFid=null;}
function rpFutOpen(fid){
 var r=document.querySelector('.futrow[data-fid="'+fid+'"]');if(!r)return;
 window.__rpFdFid=fid;var _fid=fid;  /* swarm round 2 race guard: late fetch callbacks for a closed/superseded row write NOTHING */
 var sh=document.getElementById('rpFd');var bx=document.getElementById('rpFdBox');
 var team=r.dataset.team,mkt=r.dataset.mkt,entry=r.dataset.entry,fair=r.dataset.fair,prob=r.dataset.prob,res=r.dataset.res,units=r.dataset.units,note=r.dataset.note;
 var h='<h3>'+team+'</h3><div class="rp-sub">'+mkt+'</div>';
 h+='<div class="rp-bet"><b>Why this pick</b><div style="margin-top:4px">Carded at <b>'+entry+'</b>'+(fair?' - our fair price was <b>'+fair+'</b>':'')+(prob?' (we rate it ~'+Math.round(parseFloat(prob)*100)+'% vs the '+entry+' implied price)':'')+'. The gap between our number and the market price is the edge; we sized '+(units||'2')+'u on it.</div>'+(note?'<div style="margin-top:4px;color:#9A9AA3">'+note+'</div>':'')+(res?'<div style="margin-top:4px;color:#9A9AA3">Resolves: '+res+'</div>':'')+'</div>';
 h+='<div class="rp-bet" id="rpFdLive"><b>Live market</b><div style="margin-top:4px" id="rpFdLiveBody">loading...</div></div>';
 bx.innerHTML=h+'<button class="rp-btn ghost" onclick="rpFdClose()">Close</button>';
 sh.style.display='flex';
 var slug=r.dataset.pslug,kw=(r.dataset.pkw||'').toLowerCase();
 if(r.dataset.ksrc==='kalshi'){rpFdRenderLive(r);return;}  /* 9/27: seeded Kalshi sheet FIRST (server-verified quote) - proxy only for non-seeded rows */
 var kt=r.dataset.kalticker;
 if(kt){var u2='https://api.elections.kalshi.com/trade-api/v2/markets/'+kt+'?_='+Date.now();
  var _ac=new AbortController();setTimeout(function(){_ac.abort();},8000);  /* futures batch: loading must RESOLVE - data or an honest unavailable state, never spin forever */
  fetch('https://api.allorigins.win/raw?url='+encodeURIComponent(u2),{signal:_ac.signal}).then(function(r3){return r3.json();}).then(function(j){
   if(window.__rpFdFid!==_fid)return;var m=j&&j.market;var b=document.getElementById('rpFdLiveBody');if(!b)return;
   var p=m?parseFloat(m.yes_ask_dollars):NaN;if(!(p>0&&p<1)){b.textContent='live data unavailable';return;}
   var c=p*100;var ml=c>=50?-Math.round(c/(100-c)*100):Math.round((100-c)/c*100);
   var eMl=parseInt(String(entry).replace('+',''),10)||100;var eImp=eMl>0?100/(eMl+100):(-eMl)/((-eMl)+100);
   var d=(p-eImp)*100;
   var arrow=d>0.5?'<span style="color:#3ecf6f">&#9650; '+d.toFixed(1)+' pts since entry</span>':(d<-0.5?'<span style="color:#e5484d">&#9660; '+Math.abs(d).toFixed(1)+' pts since entry</span>':'flat vs entry');
   b.innerHTML='Live price <b>'+(ml>0?'+':'')+ml+'</b> ('+c.toFixed(1)+'%) &middot; '+arrow;
  }).catch(function(){if(window.__rpFdFid!==_fid)return;var b=document.getElementById('rpFdLiveBody');if(b)b.textContent='live data unavailable';});
  return;}
 if((window.__rpFutMkts||{})[slug]){rpFdRenderLive(r);return;}
 var _ac2=new AbortController();setTimeout(function(){_ac2.abort();},8000);
 fetch('https://gamma-api.polymarket.com/events?slug='+slug,{signal:_ac2.signal}).then(function(r2){return r2.json();}).then(function(ev){
  if(window.__rpFdFid!==_fid)return;var mkts=(ev&&ev[0]&&ev[0].markets)||[];(window.__rpFutMkts=window.__rpFutMkts||{})[slug]=mkts;
  rpFdRenderLive(r);
 }).catch(function(){if(window.__rpFdFid!==_fid)return;var b=document.getElementById('rpFdLiveBody');if(b){b.style.opacity='.55';b.textContent='live data unavailable';}});
}
/* shared sheet live renderer - driven by the 2s tick cache so the open sheet rides the tick;
   source death shows a dimmed honest label instead of a stale price (his Sep 26 rule) */
function rpFdRenderLive(r){
 var b=document.getElementById('rpFdLiveBody');if(!b)return;
 if(r.dataset.ksrc==='kalshi'){var _kc=parseFloat(r.dataset.kc||'0');if(!(_kc>0&&_kc<100)){b.style.opacity='.55';b.textContent='live data unavailable';return;}
  var _ml=_kc>=50?-Math.round(_kc/(100-_kc)*100):Math.round((100-_kc)/_kc*100);
  var _e=r.dataset.entry||'+0',_eMl=parseInt(_e.replace('+',''),10)||100,_eImp=_eMl>0?100/(_eMl+100):(-_eMl)/((-_eMl)+100),_p=_kc/100;
  var _mv=_p>_eImp+0.005?'&#9650; shortened':(_p<_eImp-0.005?'&#9660; drifted':'steady');
  b.style.opacity='';b.innerHTML='Live on Kalshi (ask) <b>'+(_ml>0?'+':'')+_ml+'</b> ('+_kc.toFixed(1)+'%) &middot; '+_mv+' vs entry '+_e+' &middot; refreshes each site rebuild';return;}  /* 9/27 futures live-odds: Kalshi-sourced, never .com gamma */

 var slug=r.dataset.pslug,kw=(r.dataset.pkw||'').toLowerCase(),entry=r.dataset.entry||'+0';
 var ok=((window.__rpPolyOkByFid||{})[r.dataset.fid])||0;
 if(!ok){b.style.opacity='.55';b.textContent='live data unavailable';return;}  /* never delivered: say so, no fake timestamp */
 if((Date.now()-ok)>30000){b.style.opacity='.55';if(!b.dataset.live){b.textContent='live data unavailable';return;}if(!b.querySelector('.futlk')){b.insertAdjacentHTML('beforeend',' <span class="futlk" style="font-size:11px;color:#8a8f98;font-weight:600">&middot; last known</span>');}return;}  /* swarm round 2: dim-only applies to CONFIRMED prices; an unconfirmed placeholder resolves to explicit unavailable - loading never persists */
 b.style.opacity='';var _lk2=b.querySelector('.futlk');if(_lk2)_lk2.remove();
 var mkts=(window.__rpFutMkts||{})[slug]||[];
 var m=null;for(var i=0;i<mkts.length;i++){if((mkts[i].question||'').toLowerCase().indexOf(kw)>=0){m=mkts[i];break;}}
 if(!m){b.textContent='market not found';return;}
 try{
  var outs=JSON.parse(m.outcomes||'[]'),pr=JSON.parse(m.outcomePrices||'[]'),idx=0;
  for(var j=0;j<outs.length;j++){if(String(outs[j]).toLowerCase()==='yes'){idx=j;break;}}
  var p=parseFloat(pr[idx]);if(!(p>0&&p<1)){b.textContent='live data unavailable';return;}
  var c=p*100;
  var ml=c>=50?-Math.round(c/(100-c)*100):Math.round((100-c)/c*100);
  var eMl=parseInt(String(entry).replace('+',''),10)||100;
  var eImp=eMl>0?100/(eMl+100):(-eMl)/((-eMl)+100);
  var d=(p-eImp)*100;
  var arrow=d>0.5?'<span style="color:#3ecf6f">&#9650; '+d.toFixed(1)+' pts since entry</span>':(d<-0.5?'<span style="color:#e5484d">&#9660; '+Math.abs(d).toFixed(1)+' pts since entry</span>':'flat vs entry');
  var v24=m.volume24hr?('$'+Math.round(m.volume24hr).toLocaleString()+' traded in last 24h'):'';
  var liq=m.liquidity?(' &middot; $'+Math.round(m.liquidity).toLocaleString()+' liquidity'):'';
  var d1=(m.oneDayPriceChange!=null)?((m.oneDayPriceChange*100>=0?'+':'')+(m.oneDayPriceChange*100).toFixed(1)+' pts last 24h'):'';
  b.dataset.live='1';b.innerHTML='Live price <b>'+(ml>0?'+':'')+ml+'</b> ('+c.toFixed(1)+'%) &middot; '+arrow+'<div style="margin-top:4px;color:#9A9AA3">'+[d1,v24+liq].filter(Boolean).join(' &middot; ')+'</div>';
 }catch(e){b.textContent='live data unavailable';}
}
</script>
__FUTPOLL__<script src="myprofile.js?v=__BUILD__"></script><script data-goatcounter="https://rixpicks.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script><script>window.rpGcEvent=function(p,flag){var pend=window.__rpGcPend=window.__rpGcPend||{};if(pend[p])return;pend[p]=1;var n=0;var go=function(){try{if(flag&&localStorage.getItem(flag)){pend[p]=0;return;}if(window.goatcounter&&goatcounter.count){goatcounter.count({path:p,event:true});if(flag){try{localStorage.setItem(flag,'1');}catch(e){}}pend[p]=0;}else if(n++<20)setTimeout(go,1500);else pend[p]=0;}catch(e){pend[p]=0;if(n++<20)setTimeout(go,3000);}};go();};</script></body></html>'''
def build_futures_page(css,build_sha):
    if not FUT: return None
    import os as _os2
    _REGALL=json.load(open(_os2.path.join(_os2.path.dirname(__file__),'..','config_leagues.json')))['leagues']
    BALL={'NFL':'&#127944;','MLB':'&#9918;','NBA':'&#127936;','NHL':'&#127954;','WTA':'&#127934;','ATP':'&#127934;','CFB':'&#127944;','WNBA':'&#127936;','NCAAB':'&#127936;','MLS':'&#9917;','NWSL':'&#9917;','PGA':'&#9971;','NASCAR':'&#127950;','UFC':'&#129354;','Boxing':'&#129354;'}
    rows=[]
    seen_lg=set()
    for f in FUT:
        lg=f.get('league','Other')
        if lg not in seen_lg:
            seen_lg.add(lg)
            rows.append('<div class="sect" style="margin-top:18px">%s %s</div>'%(BALL.get(lg,'&#127937;'),html.escape(lg)))
        # owner 9/27 9:00 (supersedes 8:25 .us-only): .us first, .com fills markets .us lacks.
        # PRICE-VENUE LOCK: the chip's price comes from the venue it opens, never mixed.
        _furl=_poly_us_url(f.get('poly_slug','')) if f.get('poly_slug') else ''
        if _furl and not _link_alive(_furl):
            print(f"LINK DROP: futures {f.get('team')} dead/generic .us destination: {_furl}", file=sys.stderr)
            _furl=''
        _pus=(f.get('polymarket_us') or {})
        _pcom=(f.get('polymarket_com') or {})
        _flink=''
        if _furl:
            _flbl='POLY'+((' '+c2ml(_pus['cents'])) if isinstance(_pus.get('cents'),(int,float)) else '')
            _flink=('<div style="margin-top:6px"><a class="chip futpoly"%s href="%s" data-book="POLY" data-sb="%s" target="_blank" rel="noreferrer">%s</a></div>'%(bkstyle('POLY'),html.escape(_furl),html.escape(_furl),html.escape(_flbl)))
        elif _pcom.get('url') and _pcom.get('verified') and isinstance(_pcom.get('cents'),(int,float)) and 0<_pcom['cents']<100:
            if _link_alive(_pcom['url']):
                _flink=('<div style="margin-top:6px"><a class="chip futpoly"%s href="%s" data-book="POLY" data-sb="%s" target="_blank" rel="noreferrer">POLY %s</a></div>'%(bkstyle('POLY'),html.escape(_pcom['url']),html.escape(_pcom['url']),html.escape(c2ml(_pcom['cents']))))
            else:
                print(f"LINK DROP: futures {f.get('team')} dead/generic .com destination: {_pcom['url']}", file=sys.stderr)
        # 9/27 owner instruction: futures odds live on-site. Server-seeded Kalshi ask (futures_quotes.py
        # at refresh) owns the numbers - no client poll (Kalshi sends no CORS header; proxy tick removed 9/27 per main); no quote -> locked entry, never blank.
        _kq=(f.get('kalshi_quote') or {})
        _kqok=(_kq.get('status')=='active' and isinstance(_kq.get('ask_c'),(int,float)) and 0<_kq['ask_c']<100)
        _fut_live=c2ml(_kq['ask_c']) if _kqok else f['odds']
        _kqattrs=(' data-ksrc="kalshi" data-kc="%d"'%round(_kq['ask_c'])) if _kqok else ''
        _ktick=_kq.get('ticker','') if _kqok else f.get('kalshi_ticker','')
        _futmove=''
        if _kqok:
            try:
                _eMl=int(str(f['odds']).replace('+',''))
                _eImp=(100/(_eMl+100)) if _eMl>0 else ((-_eMl)/((-_eMl)+100))
                _p=float(_kq['ask_c'])/100
                if _p>_eImp+0.005: _futmove='<span style="color:#3ecf6f">&#9650; shortened from %s (%.1f%% &rarr; %.1f%%)</span>'%(html.escape(f['odds']),_eImp*100,_p*100)
                elif _p<_eImp-0.005: _futmove='<span style="color:#e5484d">&#9660; drifted from %s (%.1f%% &rarr; %.1f%%)</span>'%(html.escape(f['odds']),_eImp*100,_p*100)
                else: _futmove='steady vs entry %s (%.1f%%)'%(html.escape(f['odds']),_eImp*100)
            except Exception: _futmove=''
        rows.append(('<div class="futrow" data-fid="%s" data-pslug="%s" data-pkw="%s" data-kalticker="%s"%s data-entry="%s" data-team="%s" data-mkt="%s" data-fair="%s" data-prob="%s" data-res="%s" data-units="%s" data-note="%s" style="padding:12px 0;border-bottom:1px solid rgba(127,127,127,.15)">'
        '<div style="display:flex;justify-content:space-between;align-items:baseline;gap:10px">'
        '<span style="font-weight:700">'+('<img src="https://a.espncdn.com/i/teamlogos/'+_REGALL.get(f.get('league',''),{}).get('logo_dir','')+'/500/'+f.get('abbr','')+'.png" style="width:20px;height:20px;vertical-align:-4px;margin-right:7px" onerror="this.remove()">' if f.get('abbr') and _REGALL.get(f.get('league',''),{}).get('logo_dir') else '')+'%s</span>'
        '<span style="white-space:nowrap"><span class="futlive" style="font-weight:700;color:#3aa895;opacity:%s">%s</span><button class="futdots" onclick="rpFutOpen(this.getAttribute(\'data-f\'))" data-f="%s" style="background:none;border:none;color:#8a8f98;font-size:16px;padding:2px 2px 2px 8px;cursor:pointer;vertical-align:1px">&#8943;</button></span></div>'
        '<div style="font-size:12px;color:#8a8f98;margin-top:2px">%s &middot; entry %s &middot; %su%s</div>'
        + ('<div style="font-size:12px;margin-top:3px;color:#d8a23a">&#8646; pick changed from %s (%s)</div>'%(html.escape(f['changed_from']['team']),html.escape(f['changed_from']['odds'])) if f.get('changed_from') else '')
        + '%s'
        + '<div class="futmove" style="font-size:12px;margin-top:3px;color:#8a8f98">%s</div></div>')
        %(html.escape(f['id']),html.escape(f.get('poly_slug','')),html.escape(f.get('poly_kw','')),html.escape(_ktick),_kqattrs,html.escape(f['odds']),
          html.escape(f['team']),html.escape(f['market']),html.escape(f.get('fair','')),html.escape(str(f.get('prob',''))),html.escape(f.get('res','')),str(f.get('units',2)),html.escape(f.get('note','')),
          html.escape(f['team']),('' if _kqok else '.55'),html.escape(_fut_live),html.escape(f['id']),html.escape(f['market']),html.escape(f['odds']),f.get('units',2),(' &middot; '+html.escape(f['note']) if f.get('note') else ''),_flink,_futmove))
    _FUTPOLL="""<script>(function(){
function _faml(c){var q=c/100;if(!(q>0&&q<1))return"";return q>=0.5?String(Math.round(-100*q/(1-q))):"+"+String(Math.round(100*(1-q)/q));}
function _fpt(iso){try{return new Date(iso).toLocaleString("en-US",{timeZone:"America/Los_Angeles",hour:"numeric",minute:"2-digit"});}catch(e){return"";}}
function _fmv(entry,c){var eMl=parseInt(String(entry).replace("+",""),10)||100;var eImp=eMl>0?100/(eMl+100):(-eMl)/((-eMl)+100);var p=c/100;
 if(p>eImp+0.005)return '<span style="color:#3ecf6f">&#9650; shortened from '+entry+' ('+(eImp*100).toFixed(1)+'% &rarr; '+(p*100).toFixed(1)+'%)</span>';
 if(p<eImp-0.005)return '<span style="color:#e5484d">&#9660; drifted from '+entry+' ('+(eImp*100).toFixed(1)+'% &rarr; '+(p*100).toFixed(1)+'%)</span>';
 return 'steady vs entry '+entry+' ('+(eImp*100).toFixed(1)+'%)';}
function rpFutPoll(){fetch("futures.json?cb="+Date.now(),{cache:"no-store"}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(rows){
 var asof="";
 (rows||[]).forEach(function(f){
  var kq=f&&f.kalshi_quote;if(!kq||kq.status!=="active"||!(kq.ask_c>0&&kq.ask_c<100))return;
  var el=document.querySelector('.futrow[data-fid="'+f.id+'"]');if(!el)return;
  el.dataset.kc=String(kq.ask_c);
  var lv=el.querySelector(".futlive");if(lv){lv.textContent=_faml(kq.ask_c);lv.style.opacity="";}
  var mv=el.querySelector(".futmove");if(mv)mv.innerHTML=_fmv(el.dataset.entry||"+0",kq.ask_c);
  if(kq.quoted_at&&kq.quoted_at>asof)asof=kq.quoted_at;
  var pc=f.polymarket_com;
  if(pc&&pc.quoted_at&&pc.quoted_at>asof)asof=pc.quoted_at;
  if(pc&&pc.verified&&typeof pc.cents==="number"&&pc.cents>0&&pc.cents<100){var pel=el.querySelector(".futpoly");if(pel)pel.textContent="POLY "+_faml(pc.cents);}
 });
 if(asof){
  var age=Date.now()-new Date(asof).getTime();
  var stale=!(age>=0&&age<12*60*1000); /* promise is ~5 min - 12 min = honest slack, never stale-as-live */
  /* tester 9:57: never replace the parent node - it deleted #rpFutAsOf and the label could
     never recover on fresh quotes. Preserve the spans, update text only. */
  var iv=document.getElementById("rpFutAsOf"),_fpre=document.getElementById("rpFutPre"),_ftl=document.getElementById("rpFutTail");
  if(iv){iv.textContent=_fpt(asof);
    if(_fpre)_fpre.textContent=stale?'Quotes as of ':'Live quotes as of ';
    if(_ftl)_ftl.innerHTML=stale?' PT &middot; refresh delayed - showing last verified prices':' PT &middot; refresh every ~5 min';}
  var fl=document.querySelectorAll(".futlive,.futmove,.futpoly");
  for(var i=0;i<fl.length;i++)fl[i].style.opacity=stale?".55":"";
 }
}).catch(function(){
 var iv=document.getElementById("rpFutAsOf"),_fpre=document.getElementById("rpFutPre"),_ftl=document.getElementById("rpFutTail");
 if(iv)iv.textContent='';
 if(_fpre)_fpre.textContent='Quotes unavailable';
 if(_ftl)_ftl.innerHTML=' - refresh delayed';
 var fl=document.querySelectorAll(".futlive,.futmove,.futpoly");
 for(var i=0;i<fl.length;i++)fl[i].style.opacity=".55";
});}
rpFutPoll();setInterval(rpFutPoll,60000); /* server fast-loop owns the file; page just mirrors it - never ticks the exchange directly */
})();</script>"""
    try:
        import datetime as _dt2
        from zoneinfo import ZoneInfo as _ZI2
        _qts=[(f.get('kalshi_quote') or {}).get('quoted_at') for f in FUT]
        _qts=[q for q in _qts if q]
        _asof=_dt2.datetime.fromisoformat(max(_qts)).astimezone(_ZI2('America/Los_Angeles')).strftime('%I:%M %p').lstrip('0') if _qts else 'unavailable'
    except Exception: _asof='unavailable'
    pg=FUTURES_TMPL
    for tok,val in [('__CSS__',css),('__FUTASOF__',_asof),('__FUTPOLL__',_FUTPOLL),('__ROWS__',''.join(rows)),('__COUNT__',str(len(FUT))),('__BUILD__',build_sha),('__RPARB__',ARB_INJECT)]:
        pg=pg.replace(tok,val)
    return pg
_fp=build_futures_page(_css,build_sha)
_pages=0
if _fp:
    # Sep 26 builder fix: futures page must land in the OUTPUT dir like every other page -
    # writing to cwd silently dropped it from candidate builds (and clobbered the repo copy on test runs).
    open(os.path.join(os.path.dirname(out) or '.','futures.html'),'w').write(scrub_shipped(_fp))
    print('written: futures.html',len(_fp))
    _pages+=1
for _fn,_html in build_team_pages(man,_css,build_sha).items():
    open(os.path.join(os.path.dirname(out) or '.',_fn),'w').write(scrub_shipped(_html))
    print('written:',_fn,len(_html))
    _pages+=1
for _fn,_html in build_game_pages(man,_css,build_sha).items():
    open(os.path.join(os.path.dirname(out) or '.',_fn),'w').write(scrub_shipped(_html))
    print('written:',_fn,len(_html))
    _pages+=1
if os.environ.get('RP_PUBLISH')=='1':
    import datetime as _dt
    _ts=_dt.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    _hp=os.path.join(os.path.dirname(out) or '.','price_history.jsonl')
    with open(_hp,'a') as _hf:
        for _hr in HIST.values():
            _r={'ts':_ts}; _r.update(_hr); _hf.write(json.dumps(_r)+'\n')
    print('history appended:',len(HIST),'games ->',_hp)
if man.get('units_ledger'): print('units reconciliation:',man['units_ledger'],file=sys.stderr)
print('written:',out,len(page),'design v'+RP_DESIGN,'build',build_sha)
# process gap (main, Sep 27): every build leaves a content-addressed snapshot of the manifest it
# built from in manifests/ - the Sep 25 8-game card shipped from an uncommitted /tmp manifest and
# orphaned (game-4..11 with no recoverable source). Content-hash naming dedupes: rebuilds with an
# unchanged manifest reuse the file, so refresh cycles add no commit noise; any add-all commit
# path (publish.yml, refresh.sh, agent payload) carries the snapshot automatically.
import hashlib as _hl2
_mby=open(os.path.abspath(sys.argv[1]),'rb').read()
os.makedirs('manifests',exist_ok=True)
_msn=os.path.join('manifests','manifest-'+_hl2.sha256(_mby).hexdigest()[:12]+'.json')
if not os.path.exists(_msn):
    open(_msn,'wb').write(_mby)
    print('manifest snapshot:',_msn,file=sys.stderr)

# J-106: persist freshly resolved book links so refresh rebuilds can never strip shipped chips.
# Sep 26 chaos drill: ledger writes are OPT-IN (RP_PUBLISH=1, set by publish.yml on approve=true) -
# candidate builds never touch the ledger, and a failed write fails LOUDLY (a silent miss kills
# both the freeze defense and the carryover screen).
if os.environ.get('RP_PUBLISH')=='1':
    try:
        for _k,_v in NEWSHIPPED.items():
            SHIPPED.setdefault(_k,{}).update(_v)
        if NEWSHIPPED:
            json.dump(SHIPPED,open('shipped_books.json','w'),indent=1)
            print(f'shipped_books ledger: {len(NEWSHIPPED)} game(s) persisted', file=sys.stderr)
        open('shipped_pick_hash.txt','w').write(_PC_HASH+'\n')
        print(f'pick-content hash persisted: {_PC_HASH[:12]}... -> shipped_pick_hash.txt', file=sys.stderr)
    except Exception as _e:
        print(f'LEDGER WRITE FAILED: shipped_books.json not persisted ({type(_e).__name__}: {_e}) - J-106/J-101 defenses degraded', file=sys.stderr)
        sys.exit(4)

# Guaranteed build-level audit record (verifier Sep 26): EXACTLY ONE URF line per build invocation,
# clean or not. Branch _urf lines above are per-choice detail; this is the deploy-affecting summary
# and it fires unconditionally - a clean build can never leave an empty audit trail.
_urf("EXECUTE","C=3 F=3 R=2 U=1 V=3 CE=1 T=med",f"build {build_sha} complete",f"{_pages+1} pages written (index + {_pages} secondary); arbiter v3.1 baked; registry 1.8 verified; ledger {'persisted' if os.environ.get('RP_PUBLISH')=='1' else 'untouched (candidate build)'}")
