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

RP_DESIGN='1.2.0'  # locked design system version - bump only on user-approved design change. v1.1.0 (user, Sep 25 12:35 AM): match visitor system appearance - light (default, unchanged) + dark via prefers-color-scheme. v1.2.0 (user, Sep 25 8:46 AM): current page shape approved as THE standing daily template - header without FINAL line, tap-any-book intro, per-pick chips + units, combo section, record + unit line, minimal footer (reference commit fbec1c1). Every morning build reproduces this exact shape; changes only on his explicit instruction.

def _pt_date(iso):
    # Sep 26 builder fix: real America/Los_Angeles conversion - a hard-coded UTC-7 is wrong in PST.
    try:
        import datetime as _dt
        from zoneinfo import ZoneInfo
        return _dt.datetime.fromisoformat((iso or '').replace('Z','+00:00')).astimezone(ZoneInfo('America/Los_Angeles')).date().isoformat()
    except Exception: return ''

man=json.load(open(sys.argv[1]))
# Sep 26 live regression (hunter 7:25 AM): an hourly odds refresh rebuilt record/units from a stale
# manifest and clobbered the tracker-canonical live values. Refresh builds (RP_REFRESH=1) INHERIT
# record/units from the live page being rebuilt; only an approved publish (RP_PUBLISH=1) may move
# them, from a manifest staged off the tracker at ship time.
if os.environ.get('RP_REFRESH')=='1':
    # Fail CLOSED (data auditor, Sep 26): a refresh that cannot pin record/units from the live page
    # aborts loudly with NO write - a skipped odds refresh is recoverable, a clobbered record is not.
    try:
        if len(sys.argv)<=2 or not os.path.exists(sys.argv[2]): raise FileNotFoundError('live page missing')
        _live=open(sys.argv[2],encoding='utf-8').read()
        _lr=re.search(r'id="rpRec"[^>]*data-bw="(\d+)"[^>]*data-bl="(\d+)"', _live)
        _lu=re.search(r'id="rpUnits"[^>]*>([^<]+)<', _live)
        if not (_lr and _lu): raise ValueError('live record/units not parseable')
        man['record']=f'{_lr.group(1)}-{_lr.group(2)}'
        man['units_pl']=_lu.group(1).replace('Units:','').strip()
        print(f"REFRESH INHERIT: record {man['record']} / units {man['units_pl']} pinned from live page (refresh cannot move them)", file=sys.stderr)
    except Exception as _e:
        print(f'REFRESH ABORTED: cannot pin record/units from live page ({type(_e).__name__}: {_e}) - no write, no push', file=sys.stderr)
        sys.exit(5)
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
BOOKS=[('DraftKings','DK'),('FanDuel','FD'),('ESPN BET','ESPN'),('Hard Rock','HR'),('BetMGM','MGM'),('BetRivers','BR'),('Kalshi','KAL'),('Polymarket','POLY')]
BKDOM={'DK':'draftkings.com','FD':'fanduel.com','ESPN':'espnbet.com','HR':'hardrock.bet','MGM':'betmgm.com','BR':'betrivers.com','KAL':'kalshi.com','POLY':'polymarket.com','B365':'bet365.com','FAN':'fanatics.com'}
# Brand fills (user 9/24 10:48 PM): every chip filled with the platform's own brand colors. (bg, fg)
BKFILL={'DK':('#0b0e11','#53d337'),'FD':('#e7f3ff','#0e6fd0'),'ESPN':('#e6faf3','#0a8a66'),'HR':('#faf3dd','#8a6d1a'),'MGM':('#f5f0e4','#7a6226'),'BR':('#e3f5fc','#0278a6'),'KAL':('#e6f9f3','#0a7c5c'),'POLY':('#e8f3fc','#1a6db0'),'B365':('#fff9db','#6b5900'),'FAN':('#f0f0f2','#1a1a1a')}
def bkimg(short):
    d=BKDOM.get(short)
    return f'<img class="bklogo" src="https://www.google.com/s2/favicons?domain={d}&sz=128" alt="" onerror="this.remove()">' if d else ''
def bkstyle(short):
    bf=BKFILL.get(short)
    return f' data-bk="{short}" style="background:{bf[0]};border-color:{bf[0]};color:{bf[1]}"' if bf else ''
def c2ml(c):
    c=int(round(c))
    if c<=0 or c>=100: return str(c)
    return ('-' if c>=50 else '+')+str(round(c/(100-c)*100) if c>=50 else round((100-c)/c*100))
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
    for m in re.finditer(r'options=([0-9-]+)',u or ''): ev.add(m.group(1).split('-')[0])
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
                _name={'draftkings':'DraftKings','fanduel':'FanDuel','espnbet':'ESPN BET','hardrockbet':'Hard Rock','betmgm':'BetMGM','betrivers':'BetRivers'}.get(_bn,_bn)
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
                    _name={'draftkings':'DraftKings','fanduel':'FanDuel','espnbet':'ESPN BET','hardrockbet':'Hard Rock','betmgm':'BetMGM','betrivers':'BetRivers'}.get(_bn,_bn)
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
            return (sfx, round(d*100) if 0<d<1 else None)
    return ('',None)

def chips(p):
    star='\u2605 '
    _mkt='spread' if p.get('market')=='spread' else 'ml'
    _dm=f' data-market="{_mkt}"'  # sentinel Sep 26: the line-shop market guard reads this
    out=[]
    side=p.get('side','away')
    kw=p['name'].split()[0]
    inst=game_instance(p.get('game'))
    inst=f' {inst}' if inst else ''
    for name,short in BOOKS:
        link=None; ml=None
        pr=sel_books(pre.get((p['game']['away'],p['game']['home'])), p.get('game')) if p.get('game') else None
        if p.get('market')=='spread':
            pr=(sel_books(pre_sp.get((p['game']['away'],p['game']['home'])), p.get('game')) or {}).get('books') if p.get('game') else None
        PKMAP={'FanDuel':'fanduel','DraftKings':'draftkings','ESPN BET':'espnbet','Hard Rock':'hardrockbet'}
        if pr and name in PKMAP:
            pk=PKMAP[name]
            if p.get('market')=='spread':
                e=(pr.get(pk) or {}).get(side) or {}
                if e.get('link'): link=e['link']
                if e.get('price') is not None: ml=e['price']
            else:
                pl=(pr.get(pk) or {}).get(f"{side}_link")
                if pl: link=pl
                if p.get('event_mode'):
                    ev=(pr.get(pk) or {}).get('event')
                    if ev: link=ev
                pm=(pr.get(pk) or {}).get(f"{side}_ml")
                if pm is not None: ml=pm
        if name in ('BetMGM','BetRivers'):
            if p.get('market')=='spread':
                st_=((sel_books(pre_sp.get((p['game']['away'],p['game']['home'])), p.get('game')) or {}).get('books') or {}).get('state_templates',{}) if p.get('game') else {}
                e=(st_.get('betmgm' if name=='BetMGM' else 'betrivers') or {}).get(side) or {}
                if e.get('link'): link=e['link']
                if e.get('price') is not None: ml=e['price']
            else:
                stt=((sel_books(pre.get((p['game']['away'],p['game']['home'])), p.get('game')) or {}).get('state_templates',{})) if p.get('game') else {}
                e=stt.get('betmgm' if name=='BetMGM' else 'betrivers') or {}
                if name=='BetMGM' and e.get(f"{side}_link"):
                    link=e[f"{side}_link"]; ml=e.get(f"{side}_ml")
                if name=='BetRivers' and e.get('event'):
                    link=e['event']; ml=e.get(f"{side}_ml")
        if name=='Kalshi' and p.get('kalshi'):
            link=p['kalshi']['url']
            tick=p['kalshi']['url'].rstrip('/').split('/')[-1].upper()
            _kside=(p.get('kalshi') or {}).get('team','')
            _sfx,_kc=kal_market(tick,_kside)
            _gate=(p.get('kalshi') or {}).get('gate_cents')
            if _gate is not None and _kc is not None and _kc>_gate:
                # ship condition (main, Sep 26 7:17 AM): pick ships only at gate_cents-or-better executable ask
                print(f"BUILD FAILED: {p.get('name')} Kalshi ask {_kc}c exceeds ship-condition ceiling {_gate}c", file=sys.stderr)
                sys.exit(3)
            if not _sfx or _kc is None:
                # Sep 26 hunter ruling: a stale price posing as fresh is worse than no build.
                print(f"BUILD FAILED: Kalshi market unresolved for {p.get('name')} team {_kside!r} under {tick}", file=sys.stderr)
                sys.exit(3)
            label=(f"KAL {c2ml(_kc)}" if _kc else "KAL")+inst
            if p.get('best_book')=='Kalshi': label=label
            best=(p.get('best_book')=='Kalshi')
            side=html.escape(_sfx)
            out.append(f'<a class="chip{" best" if best else ""}"{bkstyle(short)} href="{html.escape(link)}" data-book="KAL" data-kalticker="{tick}" data-kalside="{side}"{_dm} target="_blank" rel="noreferrer">{star if best else ""}{bkimg(short)}{label}</a>')
            continue
        if name=='Polymarket':
            if not p.get('polymarket'): continue
            slug=poly_event_slug(p['polymarket']['url']) or ''
            _us=(p.get('polymarket_us') or {}).get('url') or ''
            if _us and slug and poly_event_slug(_us)!=slug:
                # Sep 26 relocation-alias trap (hou-ath vs hou-oak): the .com slug is the
                # gamma-verifiable source of truth; a disagreeing .us slug is never bound.
                print(f"POLY SLUG WARNING: {p.get('name')} .us slug {poly_event_slug(_us)} != verified {slug} - using verified", file=sys.stderr)
            web=('https://polymarket.us/event/'+slug) if slug else (_us or p['polymarket']['url'].replace('https://polymarket.com/','https://polymarket.us/')); app=web
            sub=poly_sub(p['polymarket']['url']) or ''
            # price basis: gamma outcomePrices = mid/last, NOT the ask (auditor-confirmed Sep 26);
            # .us search snapshots are stale/unreliable - gamma is the build-time source of truth.
            cents=poly_price(p['polymarket']['url'],kw) or p.get('polycents')
            label=(f"POLY {c2ml(cents)}" if cents else "POLY")+inst
            if p.get('best_book')=='Polymarket': label=label
            best=(p.get('best_book')=='Polymarket')
            out.append(f'<a class="chip{" best" if best else ""}"{bkstyle("POLY")} href="{html.escape(web)}" data-book="POLY" data-sb="{html.escape(web)}" data-app="{html.escape(app)}" data-polyslug="{html.escape(slug)}"{_dm} data-polysub="{html.escape(sub)}" data-polykw="{html.escape(kw)}" onclick="return rpRoute(event,this)" target="_blank" rel="noreferrer">{star if best else ""}{bkimg("POLY")}{label}</a>')
            continue
        if link and p.get('game'):
            _sk=f"{p['game'].get('away')}|{p['game'].get('home')}|{(p['game'].get('commence') or '')[:10]}"
            NEWSHIPPED.setdefault(_sk,{})[name]={'link':link,'ml':ml,'commence':p['game'].get('commence','')}
        if not link and p.get('game'):
            _se=SHIPPED.get(f"{p['game'].get('away')}|{p['game'].get('home')}|{(p['game'].get('commence') or '')[:10]}",{}).get(name)
            if _se and _stale_carryover(name,_se.get('link'),p.get('game')): _se=None
            if _se: link=_se.get('link'); ml=_se.get('ml')
        if not link: continue  # no game-level link -> drop chip
        best=(p.get('best_book')==name)
        label=(f"{short} {ml:+d}" if ml is not None else short)+inst
        # star renders left of logo at append time
        if name in ('FanDuel','DraftKings'):
            pm=((p.get('fdp') or {}).get('url') or 'https://www.fanduel.com/predicts') if name=='FanDuel' else ((p.get('dkp') or {}).get('url') or 'https://predictions.draftkings.com/')
            pmapp='https://predicts.fanduel.com/' if name=='FanDuel' else ''
            nopm=' data-nopm="1"' if (name=='DraftKings' and not (p.get('dkp') or {}).get('url')) else ''
            _tm='{state}' in link
            _tmattr=' data-template="1"' if _tm else ''
            _href='https://www.'+BKDOM[short] if _tm else link
            out.append(f'<a class="chip{" best" if best else ""}"{bkstyle(short)} href="{html.escape(_href)}" data-book="{short}"{_dm} data-sb="{html.escape(link)}" data-pm="{html.escape(pm)}" data-pmapp="{html.escape(pmapp)}"{nopm}{_tmattr} onclick="return rpRoute(event,this)" target="_blank" rel="noreferrer">{star if best else ""}{bkimg(short)}{html.escape(label)}</a>')
        elif '{state}' in link:
            # Sep 26 inspector ruling (J-112 class extended to singles): a priced chip on a generic
            # destination violates game-level-or-no-chip. Static HTML ships a priced NON-TAPPABLE span
            # carrying the template in data-sbt; rpTapify (in rpFilter) swaps it to a deep-link anchor
            # once the reader's state is known and the book is live there, so the tap always lands on the exact game at their book.
            out.append(f'<span class="chip{" best" if best else ""} rpnontap"{bkstyle(short)} data-book="{short}"{_dm} data-sbt="{html.escape(link)}" data-template="1">{star if best else ""}{bkimg(short)}{html.escape(label)}</span>')
        else:
            out.append(f'<a class="chip{" best" if best else ""}"{bkstyle(short)} href="{html.escape(link)}" data-book="{short}"{_dm} data-sb="{html.escape(link)}" onclick="return rpRoute(event,this)" target="_blank" rel="noreferrer">{star if best else ""}{bkimg(short)}{html.escape(label)}</a>')
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


def lineshop_html(prs):
    prs=[v for v in prs if v is not None]
    if len(prs)<2: return ''
    def ip(a): return 100.0/(a+100) if a>0 else (-a)/((-a)+100.0)
    best=max(prs); worst=min(prs)
    edge=(ip(worst)-ip(best))*100
    if edge<0.05: return ''
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
last_lg=None
SEEN=[]
for p in man['picks']:
    lg=p.get('espn_league','')
    if lg!=last_lg:
        lbl=LG_LABEL.get(lg) or (lg.split('/')[-1].replace('-',' ').title() if lg else 'Other')
        ball=LG_BALL.get(lg,'\U0001f3c5')
        rows.append(f'<div class="lghead"><span style="display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;margin-right:8px;font-size:17px">{ball}</span>{html.escape(lbl)}</div>')
        last_lg=lg
    ch=chips(p)
    for _mm in re.finditer(r'<a [^>]*data-book="([A-Z]+)"[^>]*>', ch):
        # Sep 26: guard the EFFECTIVE destination - templated chips carry a generic href and the
        # real {state} template in data-sb; comparing hrefs false-alarms on the shared base domain.
        _tag=_mm.group(0)
        _m2=re.search(r'data-sb="([^"]+)"',_tag) or re.search(r'href="([^"]+)"',_tag)
        if not _m2: continue
        _pg=p.get('game') or {}
        SEEN.append((_mm.group(1), html.unescape(_m2.group(1)), (_pg.get('away',''),_pg.get('home',''),_pg.get('commence',''))))
    chips_html=f'<div class="chips">{ch}</div>' if ch else ''
    ls_html=(lineshop_html(LAST_PRICES) or '<div class="rplineshop" style="display:none;font-size:11px;color:#8a8f98;margin:3px 0 0"></div>') if ch else ''
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
        st='width:26px;height:26px;object-fit:contain;border-radius:50%;background:rgba(127,127,127,.14)'
        if overlap: st+=';margin-left:-7px'
        return '<img src="%s" alt="" style="%s" onerror="this.remove()">'%(html.escape(u),st)
    _av=_avimg(_ma)+_avimg(_mh,True)
    _avhtml='<span style="display:inline-flex;flex-shrink:0;align-items:center">'+_av+'</span>' if _av else ''
    rows.append(f'''<div class="pick" data-espn="{espn}" data-eid="{html.escape(_eid)}" data-gpk="{_gk3[0]}" data-aab="{_gk3[1]}" data-hab="{_gk3[2]}" data-room="g{p['num']}-{(_pt_date(g.get('commence','')) or 'card')}" data-away="{html.escape(g.get('away',''))}" data-home="{html.escape(g.get('home',''))}" data-side="{p.get('side','away')}" data-market="{mkt}" data-codds="{html.escape(p.get('odds',''))}" data-stake="{html.escape(re.sub(r'[^0-9.]','',p.get('units','')))}"{(' data-counted="1"' if p.get('result') in ('WIN','LOSS','PUSH') else '')}>
  <div class="pick-head"><a class="gamelink" href="game-{p['num']}.html">{_avhtml}<span class="num">{p['num']}.</span><span class="name">{html.escape(p['name'])}</span></a><span class="meta-grp"><a class="rpmetalink" href="game-{p['num']}.html"><span class="units">{html.escape(p.get('units',''))}</span><span class="odds">{html.escape(p['odds'])}</span></a><a class="rpchatlink" href="game-{p['num']}.html#rpChatPanel" aria-label="live chat"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg><span data-cc></span></a></span></div><span class="ls" data-ls></span>
  <div class="sub">{html.escape(p['sub'])}</div>
  {chips_html}
  {ls_html}
</div>''')

if not rows:
    # Empty-slate defense (Sep 26 chaos drill / app_spec Data rules): the page NEVER ships silently
    # empty. Degraded card: explicit state + yesterday's grades, locked layout otherwise intact.
    _y=html.escape(str(man.get('yesterday') or ''))
    rows.append('<div class="pick"><div class="pick-head"><span class="name">No picks today</span></div>'
                + (f'<div class="sub"><a class="yesrec" href="yesterday.html" style="color:inherit">Yesterday: {_y}</a></div>' if _y else '')
                + '</div>')
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
fut_ids=[f.get('id','') for f in FUT]
fut_entry=''
if FUT:
    fut_entry=('<div class="sect" style="margin-top:22px">Futures</div>'
      '<a href="futures.html?v={build_sha}" style="display:flex;align-items:center;justify-content:space-between;padding:11px 12px;border:1px solid rgba(127,127,127,.22);border-radius:12px;text-decoration:none;color:inherit">'
      '<span style="font-weight:600">Track every futures pick live<span id="rpFutNew" style="display:none;background:#e5484d;color:#fff;border-radius:8px;font-size:10px;padding:1px 6px;margin-left:8px;vertical-align:2px">NEW</span></span>'
      '<span style="color:#8a8f98;font-size:12px">'+str(len(FUT))+' live &rsaquo;</span></a>')
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
            _lbl='SB' if 'Super Bowl' in _f['market'] else _f['market'].replace(' Champion','')
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
        _fw=[]
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
                    _fimg='<img src="%s" style="width:20px;height:20px;border-radius:50%%%%;vertical-align:-4px;margin-right:7px" onerror="this.remove()">'%_isrc if _isrc else ''
                    _fw.append('<a href="futures.html?v={build_sha}" style="text-decoration:none;color:inherit"><div class="pick" data-espn="%s" data-away="%s" data-home="%s" data-side="%s">%s<b>%s</b> <span style="color:#8a8f98;font-size:12px">futures: %s</span><span class="ls" data-ls></span></div></a>'%(_LGMAP[_lg][0],html.escape(an),html.escape(hn),_side,_fimg,html.escape(t),' &middot; '.join(html.escape(x) for x in info['mkts'])))
                    break
        if _fw:
            fut_watch_html='<div class="sect" style="margin-top:22px">Futures live today</div>'+''.join(_fw)
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
        return ('<li class="cxleg" data-espn="%s" data-eid="%s" data-gpk="%s" data-aab="%s" data-hab="%s" data-away="%s" data-home="%s" data-side="%s"><a href="game-%s.html" style="display:block;color:inherit;text-decoration:none;margin:0 -8px;padding:2px 8px">%s<span class="ls" data-ls></span></a></li>'
                % (html.escape(p.get('espn_league','')), html.escape(str(g.get('eid') or '')), _gk3[0], _gk3[1], _gk3[2], html.escape(g.get('away','')), html.escape(g.get('home','')), html.escape(p.get('side','away')), p['num'], html.escape(l)))
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
        BKML=[('DK','draftkings',DKPM),('FD','fanduel','https://www.fanduel.com/predicts'),('ESPN','espnbet',None),('HR','hardrockbet',None),('MGM','betmgm',None),('BR','betrivers',None)]
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
            if not (ok and len(mls)==nlegs): continue
            r=routes.get(short) or {}
            price=r.get('price')
            if price is None: price=amer_from_mls(mls)
            if price is None: continue
            # J-112 (inspector ruling, Sep 26): combined price ALWAYS renders; the chip is tappable
            # ONLY with a tap-verified executable/deepest-real destination. No verified route -> the
            # price stays and the chip is a non-tappable span under the * manual-build disclaimer.
            link=r.get('link') if r.get('verified') else None
            pmattr=f' data-pm="{pm}"' if pm else ''
            if link:
                chips.append((short,f'<a class="chip%%BEST%%"{bkstyle(short)} href="{html.escape(link)}" data-book="{short}" data-market="parlay" data-sb="{html.escape(link)}"{pmattr} onclick="return rpRoute(event,this)" target="_blank" rel="noreferrer">%%STAR%%{bkimg(short)}{short} {price:+d}</a>',price))
            else:
                chips.append((short,f'<span class="chip%%BEST%% rpnontap"{bkstyle(short)} data-book="{short}" data-market="parlay">%%STAR%%{bkimg(short)}{short} {price:+d}</span>',price))
    order=['DK','FD','ESPN','HR','MGM','BR','KAL','POLY']
    chips.sort(key=lambda s: order.index(s[0]) if s[0] in order else 99)
    # best combo price gets the star left of the logo, same as solo best line (user, Sep 25 12:59 PM)
    priced=[c for c in chips if len(c)>2 and isinstance(c[2],(int,float))]
    best_i=None
    if priced:
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
RP_MGM=['AZ','CO','DC','IL','IN','IA','KS','KY','LA','MA','MD','MI','MS','NJ','NV','NY','NC','OH','PA','TN','VA','WV','WY']
RP_B365=['AZ','CO','IL','IN','IA','KS','KY','LA','NJ','NC','OH','PA','TN','VA']
RP_FAN=['AZ','CO','CT','DC','IL','IN','IA','KS','KY','LA','MA','MD','MI','NC','NJ','NY','OH','PA','TN','VT','VA','WV','WY']
RP_ESPN=['AZ','CO','IL','IN','IA','KS','KY','LA','MA','MD','MI','NJ','NC','OH','PA','TN','VA','WV']
RP_HR=['AZ','CO','FL','IL','IN','MI','NJ','OH','TN','VA']
RP_BR=['AZ','CO','CT','DE','DC','IL','IN','IA','KS','KY','LA','ME','MD','MA','MI','NH','NJ','NY','NC','OH','OR','PA','RI','TN','VT','VA','WV','WY']

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
<script>window.OneSignalDeferred=window.OneSignalDeferred||[];OneSignalDeferred.push(async function(OneSignal){{try{{await OneSignal.init({{appId:"5e86ebe3-a135-4984-9623-db83a0f1840c",serviceWorkerPath:"OneSignalSDKWorker.js",serviceWorkerParam:{{scope:"/rixpicks/"}}}});}}catch(e){{}}}});</script>
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="RixPicks">
<meta name="theme-color" content="#000000">
<meta property="og:title" content="&rsquo;RixPicks">
<meta property="og:description" content="Daily picks. Tap a book, the bet&rsquo;s built.">
<meta name="twitter:title" content="&rsquo;RixPicks">
<meta name="twitter:card" content="summary">
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
.pick-head{{display:flex;align-items:center;gap:10px}}.meta-grp{{display:inline-flex;align-items:center;gap:8px;flex:none}}.rpmetalink{{display:inline-flex;align-items:center;gap:8px;text-decoration:none;color:inherit}}.rpchatlink{{display:inline-flex;align-items:center;gap:3px;text-decoration:none;color:#8a8f98;font-size:11px;line-height:1;margin-left:-2px}}
.gamelink{{display:flex;align-items:center;gap:10px;flex:1;color:inherit;text-decoration:none;min-width:0}}
.chev{{color:#55555c;text-decoration:none}}
.mrow{{display:flex;align-items:center;gap:10px;padding:10px 0;border-top:1px solid #e4e2de;font-size:14px}}
.mrow:first-of-type{{border-top:none}}
.mrow .bk{{font-weight:700;width:52px;flex:none}}
.mrow .side{{flex:1}}
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
.bklogo{{width:16px;height:16px;border-radius:3px;flex:none}}
.chip.best{{font-weight:800}}
.rec{{font-weight:600;font-size:16px;padding:8px 0 1px}}
.units{{color:#8a8f98;font-size:13px;font-weight:600;line-height:1}}
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
#rpSave{{width:100%;padding:11px;border:none;border-radius:8px;background:#2f8f7d;color:#fff;font-size:15px;font-weight:600;cursor:pointer}}
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
.chip[data-bk="ESPN"]{{background:#0f2e26 !important;border-color:#0f2e26 !important;color:#3ec9a0 !important}}
.chip[data-bk="HR"]{{background:#2e2614 !important;border-color:#2e2614 !important;color:#d8b84e !important}}
.chip[data-bk="MGM"]{{background:#2b2517 !important;border-color:#2b2517 !important;color:#cdb271 !important}}
.chip[data-bk="BR"]{{background:#10262f !important;border-color:#10262f !important;color:#4fc3e8 !important}}
.chip[data-bk="KAL"]{{background:#0f2a22 !important;border-color:#0f2a22 !important;color:#3ed0a8 !important}}
.chip[data-bk="POLY"]{{background:#122536 !important;border-color:#122536 !important;color:#5aa9e0 !important}}
.chip[data-bk="B365"]{{background:#2a2410 !important;border-color:#2a2410 !important;color:#e0cd6a !important}}
.chip[data-bk="FAN"]{{background:#232326 !important;border-color:#232326 !important;color:#d8d8dc !important}}
}}
</style><meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate"></head><body>
<div id="rpPull"></div>
<div class="wrap">
<h1><span class="tick">&rsquo;</span>RixPicks</h1>
<div class="status">{html.escape(man['date_label'])}</div>
<div class="intro">Tap any book under a pick to open that game there. Best line is highlighted.</div>
{f'<a class="yesrec" href="yesterday.html" style="display:block;text-decoration:none;color:inherit">Yesterday: {html.escape(man["yesterday"])}</a>' if man.get('yesterday') else ''}
<div class="sect">Today&rsquo;s picks</div>
{chr(10).join(rows)}
{parlay_html}
{fut_watch_html}
{fut_entry}
<a class="rec" id="rpRec" data-bw="{man['record'].split('-')[0]}" data-bl="{man['record'].split('-')[1]}" href="record.html" style="display:block;text-decoration:none;color:inherit;margin-top:26px">&rsquo;RixPicks Overall Record: {html.escape(man['record'])}</a>
{wl_pct_line(man['record'])}
{f'<div class="yesrec unitspl" id="rpUnits" data-bu="{html.escape(re.sub(r"[^0-9.+-]","",man["units_pl"]))}">Units: {html.escape(man["units_pl"])}</div>' if man.get('units_pl') else ''}
<div class="unitmath">1u = $5 per $1,000 in bankroll</div>
<div class="foot">Bet responsibly. <span class="rpstate-link" id="rpStateLabel" onclick="rpEdit()">Set your state</span></div>
<div id="rpModal"><div class="box">
<h3>One quick thing</h3>
<p>Pick your state once so taps open the right product &mdash; sportsbook where it&rsquo;s live, prediction markets everywhere else. Saved on this device.</p>
<div id="rpGeoNote" style="font-size:12px;color:#2f8f7d;margin-bottom:10px"></div>
<select id="rpState"><option value="">Choose state&hellip;</option>{''.join(f'<option value="{c}">{n}</option>' for c,n in RP_STATES)}</select>
<button id="rpSave" onclick="rpSave()">Save &amp; continue</button>
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
const RP_L={{FD:RP_FD,DK:RP_DK,MGM:{json.dumps(RP_MGM)},B365:{json.dumps(RP_B365)},FAN:{json.dumps(RP_FAN)},ESPN:{json.dumps(RP_ESPN)},HR:{json.dumps(RP_HR)},BR:{json.dumps(RP_BR)}}};
const RP_COMBO_NONTAP={'true' if (man.get('parlay') and combo_nontap) else 'false'};
const RP_MOB=/iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
const RP_STANDALONE=(navigator.standalone===true)||window.matchMedia('(display-mode: standalone)').matches;
function rpOpen(u){{if(RP_STANDALONE){{location.assign(u);}}else{{window.open(u,'_blank','noopener');}}}}
if(RP_STANDALONE){{document.addEventListener('click',function(e){{const a=e.target.closest('a[target="_blank"]');if(a&&!a.onclick&&a.href){{e.preventDefault();location.assign(a.href);}}}},true);}}
function rpBookLive(b,st){{if(b==='KAL'||b==='POLY')return true;const L=RP_L[b];return L?L.indexOf(st)!==-1:true;}}
function rpDest(a,st){{const b=a.dataset.book;
 if(rpBookLive(b,st)){{const sb=a.getAttribute('data-sb')||a.getAttribute('data-sbt');if(sb)return sb.replaceAll('{{state}}',st.toLowerCase());return a.getAttribute('href')||null;}}
 if(a.dataset.pm&&a.dataset.nopm!=='1')return a.dataset.pm;
 return null;}}
function rpGo(a,st){{const b=a.dataset.book;
 if(b==='POLY'&&RP_MOB&&a.dataset.app){{location.href=a.dataset.app;return;}}
 if(!rpBookLive(b,st)&&b==='FD'&&RP_MOB&&a.dataset.pmapp&&a.dataset.nopm!=='1'){{location.href=a.dataset.pmapp;return;}}
 const d=rpDest(a,st);if(d)rpOpen(d);return;}}

function rpTerm(st){{const sb=RP_FD.includes(st)||RP_DK.includes(st);const ntap=(typeof RP_COMBO_NONTAP!=='undefined'&&RP_COMBO_NONTAP===true);
 const T=(sb?'Parlay':'Combo')+((!sb||ntap)?'<span style="letter-spacing:0">&thinsp;*</span>':'');
 const h=document.getElementById('rpParlayTitle');if(h)h.innerHTML=T;
 const rg=document.getElementById('rpComboReg');if(rg){{rg.style.display=(!sb||ntap)?'':'none';
  if(ntap)rg.textContent='* Combo prices are live per-book references - build the combo manually at your book. Chips go tappable as verified deep links land.';}}
 const nt=document.getElementById('rpParlayNote');if(nt)nt.style.display=nt.textContent?'':'none';}}
function rpBestStar(pk){{
 // Sep 26: the best-line star follows VISIBLE prices - geo filtering or a price tick can strand
 // it on a hidden/worse chip. Recomputed over visible chips only, max American odds wins.
 try{{
 const chips=[...pk.querySelectorAll('[data-book]')].filter(function(a){{return !a.querySelector('[data-book]');}});let best=null,bestV=-1e18;
 chips.forEach(function(a){{
  if(a.offsetParent===null)return;
  const m=a.textContent.match(/([+-]\d+)/);if(!m)return;
  const v=parseInt(m[1]);if(v>bestV){{bestV=v;best=a;}}
 }});
 chips.forEach(function(a){{a.classList.remove('best');a.innerHTML=a.innerHTML.replace(/^\u2605 /,'');}});
 if(best){{best.classList.add('best');best.innerHTML='\u2605 '+best.innerHTML;}}
 }}catch(e){{}}
}}
function rpAllBest(){{document.querySelectorAll('.pick').forEach(rpBestStar);}}
function rpTapify(el,st){{const d=rpDest(el,st);
 if(d){{let a=el;if(el.tagName!=='A'){{a=document.createElement('a');for(const at of el.attributes)a.setAttribute(at.name,at.value);a.innerHTML=el.innerHTML;el.replaceWith(a);}}
  a.setAttribute('href',d);a.setAttribute('onclick','return rpRoute(event,this)');a.setAttribute('target','_blank');a.setAttribute('rel','noreferrer');a.classList.remove('rpnontap');}}
 else{{let sp=el;if(el.tagName!=='SPAN'){{sp=document.createElement('span');for(const at of el.attributes)sp.setAttribute(at.name,at.value);sp.innerHTML=el.innerHTML;el.replaceWith(sp);}}
  sp.removeAttribute('href');sp.removeAttribute('onclick');sp.removeAttribute('target');sp.removeAttribute('rel');sp.classList.add('rpnontap');}}}}
function rpFilter(st){{window.rpSt=st;rpTerm(st);
 document.querySelectorAll('[data-book]').forEach(function(el){{el.style.display='';if(el.querySelector('[data-book]'))return;rpTapify(el,st);}});
 if(window.rpCxStar)rpCxStar(); }}
function rpRoute(e,a){{e.preventDefault();const st=localStorage.getItem('rp_state');if(!st){{window.__rpChip=a;rpAsk(false);return false;}}rpGo(a,st);return false;}}
function rpSave(){{const st=document.getElementById('rpState').value;if(!st)return;const gps=localStorage.getItem('rp_state_gps');
 if(gps&&st!==gps){{localStorage.setItem('rp_state',st);localStorage.setItem('rp_state_src','preview');}}else{{localStorage.setItem('rp_state',st);localStorage.setItem('rp_state_src',gps?'gps':'manual');}}
 document.getElementById('rpModal').style.display='none';rpLabel();if(window.__rpChip){{rpGo(window.__rpChip,st);}}else{{rpMaybeA2HS();}}}}
function rpExitPreview(){{const gps=localStorage.getItem('rp_state_gps');if(gps){{localStorage.setItem('rp_state',gps);localStorage.setItem('rp_state_src','gps');rpLabel();}}}}
function rpLabel(){{const el=document.getElementById('rpStateLabel');const st=localStorage.getItem('rp_state');if(st){{rpFilter(st);rpAllBest();rpAllLineShops();}}if(el&&st){{const src=localStorage.getItem('rp_state_src');
 if(src==='preview'){{el.innerHTML='Previewing: '+st+' &middot; <u onclick="rpExitPreview();event.stopPropagation()">back to your state</u>';}}
 else{{el.textContent='Your state: '+st+(src==='gps'?' (verified)':' (change)');}}}}}}
function rpNote(t){{const n=document.getElementById('rpGeoNote');if(n)n.textContent=t||'';}}
function rpAsk(manualOnly){{window.__rpChip=window.__rpChip||null;
 if(manualOnly||!navigator.geolocation){{rpNote('Location unavailable - pick your state below.');document.getElementById('rpModal').style.display='flex';return;}}
 rpNote('Checking your location&hellip;');document.getElementById('rpModal').style.display='flex';
 navigator.geolocation.getCurrentPosition(function(pos){{
  fetch('https://api.bigdatacloud.net/data/reverse-geocode-client?latitude='+pos.coords.latitude+'&longitude='+pos.coords.longitude+'&localityLanguage=en').then(r=>r.json()).then(j=>{{
   const code=(j.principalSubdivisionCode||'').split('-')[1]||'';
   if(code&&document.querySelector('#rpState option[value="'+code+'"]')){{
    localStorage.setItem('rp_state',code);localStorage.setItem('rp_state_src','gps');localStorage.setItem('rp_state_gps',code);
    document.getElementById('rpModal').style.display='none';rpLabel();
    if(window.__rpChip)rpGo(window.__rpChip,code);else rpMaybeA2HS();
   }}else{{rpNote('Could not resolve your state - pick it below.');}}
  }}).catch(()=>rpNote('Location lookup failed - pick your state below.'));
 }},function(){{rpNote('Location off - pick your state below (unverified).');}},{{timeout:9000}});}}
function rpEdit(){{window.__rpChip=null;
 if(navigator.geolocation){{rpNote('Verifying your new location&hellip;');document.getElementById('rpModal').style.display='flex';
 navigator.geolocation.getCurrentPosition(function(pos){{
  fetch('https://api.bigdatacloud.net/data/reverse-geocode-client?latitude='+pos.coords.latitude+'&longitude='+pos.coords.longitude+'&localityLanguage=en').then(r=>r.json()).then(j=>{{
   const code=(j.principalSubdivisionCode||'').split('-')[1]||'';
   if(code&&document.querySelector('#rpState option[value="'+code+'"]')){{localStorage.setItem('rp_state',code);localStorage.setItem('rp_state_src','gps');localStorage.setItem('rp_state_gps',code);rpNote('Updated from your location: '+code);rpLabel();setTimeout(()=>document.getElementById('rpModal').style.display='none',900);}}
   else rpNote('Could not verify - pick your state below.');
  }}).catch(()=>rpNote('Verification failed - pick your state below.'));
 }},function(){{rpNote('Location off - manual pick below (unverified).');}},{{timeout:9000}});}}
 else rpAsk(true);}}
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
 const mlb=picks.filter(x=>(x.dataset.espn||'')==='baseball/mlb');
 // class fix (9/25 Astros lapse): gamePk-keyed rows hit the per-game feed directly; a lookup
 // miss NEVER blanks a row that was live - it dims and keeps last-good until a good tick lands.
 const rpMlbMiss=pk=>{{window.__rpMissN=(window.__rpMissN||0)+1;const el=pk.querySelector('[data-ls]');if(el&&el.dataset.live==='1'){{el.style.opacity='.55';return;}}rpLsRender(pk,null);}};
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
    const j=cache[k];const ls=(j.liveData||{{}}).linescore||{{}};const st=((j.gameData||{{}}).status||{{}}).detailedState||'';
    if(!st){{rpMlbMiss(pk);return;}}
    rpMlbGame(pk,ls,st,pk.dataset.aab||pk.dataset.away.split(' ').map(w=>w[0]).join('').slice(0,3).toUpperCase(),pk.dataset.hab||pk.dataset.home.split(' ').map(w=>w[0]).join('').slice(0,3).toUpperCase());
   }}catch(e){{rpMlbMiss(pk);}}}})();}});
  // J-101 class fix: unkeyed rows NEVER stamp. The old teams-only fallback matched a PRIOR date's
  // completed game (same teams) and stamped its Final onto an unplayed pick. Keyed gamePk binding only.
 }}
 const byLg={{}};picks.filter(x=>x.dataset.espn&&(x.dataset.espn!=='baseball/mlb')).forEach(x=>{{(byLg[x.dataset.espn]=byLg[x.dataset.espn]||[]).push(x);}});
 for(const lg of Object.keys(byLg)){{try{{
  const _u='https://site.api.espn.com/apis/site/v2/sports/'+lg+'/scoreboard?cb='+Date.now()+(lg==='football/college-football'?'&groups=80&limit=400':'');
  const d=await (await fetch(_u)).json();
  // J-101 class fix: strict event-id binding - a row stamps ONLY when its own event (data-eid) is on the board.
  byLg[lg].forEach(pk=>{{let found=null;const want=pk.dataset.eid||'';
   if(!want){{rpLsRender(pk,null);return;}}
   (d.events||[]).forEach(e=>{{if(e.id!==want)return;
    const cs=e.competitions[0].competitors;
    const aw=cs.find(c=>c.homeAway==='away'),hm=cs.find(c=>c.homeAway==='home');if(!aw||!hm)return;
    found={{a:aw.team.abbreviation,h:hm.team.abbreviation,as:+aw.score||0,hs:+hm.score||0,st:e.status.type.shortDetail,state:e.status.type.state}};}});
   rpLsRender(pk,found);if(found&&found.state==='post')rpRecLive();}});}}catch(e){{}}}}
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
function rpRecLive(){{const rec=document.getElementById('rpRec');if(!rec)return;
 let w=parseInt(rec.dataset.bw||'0'),l=parseInt(rec.dataset.bl||'0');
 const uEl=document.getElementById('rpUnits');let u=uEl?parseFloat(uEl.dataset.bu||'0'):0;
 document.querySelectorAll('.pick[data-codds]').forEach(pk=>{{
  if(pk.dataset.counted==='1')return;  /* Sep 26 12-7 bug: result already graded into the baked base - never double-count */
  const sp=pk.querySelector('[data-ls]');if(!sp)return;
  const won=sp.classList.contains('won'),lost=sp.classList.contains('lost');
  if(!won&&!lost)return;
  const stake=parseFloat(pk.dataset.stake||(pk.querySelector('.units')||{{}}).textContent)||0;
  const ml=parseInt(pk.dataset.codds);if(!stake||!ml)return;
  if(won){{w++;u+=stake*(ml>0?ml/100:100/Math.abs(ml));}}else{{l++;u-=stake;}}
 }});
 rec.innerHTML='&rsquo;RixPicks Overall Record: '+w+'-'+l;
 const pct=document.getElementById('rpWlPct');if(pct&&(w+l)>0)pct.textContent='W/L: '+(100*w/(w+l)).toFixed(1)+'%';
 if(uEl)uEl.textContent='Units: '+(u>=0?'+':'')+u.toFixed(2)+'u';
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
 const pmkt=pk.dataset.market||'';
 [...pk.querySelectorAll('[data-book]')].filter(function(a){{return !a.querySelector('[data-book]');}}).forEach(function(a){{
  if(pmkt&&a.dataset.market!==pmkt)return;  /* sentinel Sep 26 (fail-closed): only chips WITH matching market identity enter the range */
  const cs=getComputedStyle(a);if(cs.display==='none'||cs.visibility==='hidden')return;  /* geo-hidden or dead books never enter the range */
  const m=a.textContent.match(/([+-]\d+)/);if(!m)return;
  const v=parseInt(m[1]);if(Math.abs(v)<=1500)prs.push(v);
 }});
 const el=pk.querySelector('.rplineshop');if(!el)return;
 if(prs.length<2){{el.style.display='none';return;}}
 const best=Math.max.apply(null,prs),worst=Math.min.apply(null,prs);
 const edge=(ip(worst)-ip(best))*100;
 if(edge<0.05){{el.style.display='none';return;}}
 el.style.display='';
 el.textContent='line shop: '+(worst>0?'+':'')+worst+' to '+(best>0?'+':'')+best+' \u00b7 '+edge.toFixed(1)+'% edge at the best price';
}}catch(e){{}}}}
function rpAllLineShops(){{document.querySelectorAll('.pick').forEach(rpLineShop);}}
async function rpLsTickAll(){{await rpLsTick();rpFinalsTop();rpCxLive();rpRecLive();rpChatCounts();rpAllLineShops();}}
{fut_badge_js}async function rpFastLoop(){{try{{await rpLsTick();}}catch(e){{}}setTimeout(rpFastLoop,((window.__rpMissN||0)>=5)?30000:3000);}}
rpFastLoop();rpLsTickAll();setInterval(function(){{rpFinalsTop();rpCxLive();rpRecLive();rpChatCounts();rpAllLineShops();}},30000);
document.getElementById('rpModal').addEventListener('click',function(e){{if(e.target===this){{this.style.display='none';localStorage.setItem('rp_state_dismissed','1');}}}});
if(!localStorage.getItem('rp_state')&&!localStorage.getItem('rp_state_dismissed')){{rpAsk(false);}}else{{rpLabel();}}
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
function rpC2ML(c){{c=Math.round(c);if(c<=0||c>=100)return null;return c>=50?-Math.round(c/(100-c)*100):Math.round((100-c)/c*100);}}
function rpMLF(m){{return (m>0?'+':'')+m;}}
function rpCxUpdMl(bk){{
 const span=document.querySelector('#rpParlayChips [data-book="'+bk+'"]');if(!span)return;
 const n=document.querySelectorAll('.legs li').length;if(!n)return;
 let d=1,cnt=0;
 document.querySelectorAll('.pick a[data-book="'+bk+'"]').forEach(function(a){{
  const m=a.textContent.match(/([+-]\d+)/);if(!m)return;
  const ml=parseInt(m[1]);cnt++;
  d*=ml>0?1+ml/100:1+100/Math.abs(ml);
 }});
 if(cnt!==n||d<=1)return;
 const ml2=d>=2?Math.round((d-1)*100):-Math.round(100/(d-1));
 span.innerHTML=span.innerHTML.replace(/([+-]\d+)/,(ml2>0?'+':'')+ml2);
 rpCxStar();
}}
function rpCxUpd(bk){{
 const chip=document.getElementById('rpCx'+bk);if(!chip)return;
 const n=parseInt(chip.dataset.n||'0');if(!n)return;
 const cxsel='a[data-cxleg="'+bk+'"]';
 const sel=document.querySelectorAll(cxsel).length?cxsel:(bk==='KAL'?'a[data-kalticker]':'a[data-polyslug]');
 const re=bk==='KAL'?/KAL ([+-]\d+)/:/POLY ([+-]\d+)/;
 let d=1,cnt=0,dead=false;
 document.querySelectorAll(sel).forEach(function(a){{
  if(a.id==='rpCxKAL'||a.id==='rpCxPOLY')return;
  if(a.dataset.won==='1'){{cnt++;return;}}
  if(a.dataset.lost==='1'){{cnt++;dead=true;return;}}
  const m=a.innerHTML.match(re);if(m){{const ml=parseInt(m[1]);d*=ml>0?1+ml/100:1+100/Math.abs(ml);cnt++;}}
 }});
 if(cnt!==n)return;
 if(dead){{rpCxStar();return;}}
 if(d<=1)return;
 const ml2=d>=2?Math.round((d-1)*100):-Math.round(100/(d-1));
 chip.innerHTML=chip.innerHTML.replace(/(KAL|POLY)( [+-]?\d+)?/, bk+' '+(ml2>0?'+':'')+ml2);
 rpCxStar();
}}
function rpCxStar(){{try{{
 const wrap=document.getElementById('rpParlayChips');if(!wrap)return;
 let best=null,bestV=-1e9;
 wrap.querySelectorAll('[data-book]').forEach(function(a){{
  const vis=a.style.display!=='none';
  a.classList.remove('best');
  a.innerHTML=a.innerHTML.replace(/^\u2605 /,'');
  if(!vis)return;
  const m=a.textContent.match(/([+-]\d+)/);if(!m)return;
  const v=parseInt(m[1]);
  if(v>bestV){{bestV=v;best=a;}}
 }});
 if(best){{best.classList.add('best');best.innerHTML='\u2605 '+best.innerHTML;}}
}}catch(e){{}}}}
function rpPolyTick(){{try{{
 document.querySelectorAll('a[data-polyslug]').forEach(function(a){{
  if(!a.dataset.polyslug)return;
  fetch('https://gamma-api.polymarket.com/events?slug='+a.dataset.polyslug).then(r=>r.json()).then(function(ev){{
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
   if(yn&&outs.length===2&&outs[0]==='Yes'&&pr[0]!=null){{outs=[kw];pr=[pr[0]];}}
   for(let i=0;i<outs.length;i++){{if(kw&&String(outs[i]).toLowerCase().indexOf(kw)>=0&&pr[i]!=null){{
    const c=Math.round(parseFloat(pr[i])*100);
    if(target.closed&&c>=99){{a.dataset.won='1';a.dataset.lost='';rpCxUpd('POLY');return;}}
    if(target.closed&&c<=1){{a.dataset.lost='1';a.dataset.won='';rpCxUpd('POLY');return;}}
    if(c>0&&c<100){{a.dataset.won='';a.dataset.lost='';a.innerHTML=a.innerHTML.replace(/POLY( [+-]?\d+| \u2713| \u2717)?/,'POLY '+rpMLF(rpC2ML(c)));rpCxUpd('POLY');
     const pk=a.closest('.pick');
     if(pk&&pk.dataset.market==='ml'){{const s2=pk.querySelector('.odds');
      if(s2){{const ml2=c>=50?-Math.round(c/(100-c)*100):Math.round((100-c)/c*100);s2.textContent=(ml2>0?'+':'')+ml2;}}}}}}
    return;
   }}}}
  }}).catch(()=>{{}});
 }});
}}catch(e){{}}}}
function rpEspnTick(){{try{{
 const leagues={{}};
 document.querySelectorAll('.pick[data-espn]').forEach(function(d){{if(!d.dataset.espn)return;(leagues[d.dataset.espn]=leagues[d.dataset.espn]||[]).push(d);}});
 Object.keys(leagues).forEach(function(lg){{
  fetch('https://site.api.espn.com/apis/site/v2/sports/'+lg+'/scoreboard?cb='+Date.now()).then(r=>r.json()).then(function(j){{
   (j.events||[]).forEach(function(ev){{
    const comp=(ev.competitions||[])[0]||{{}};const o=(comp.odds||[])[0];if(!o)return;
    leagues[lg].forEach(function(d){{
     if(d.dataset.market==='spread')return;
     /* J-108: bind by ESPN event id when carried; otherwise require BOTH team tokens AND
        the event's PT date to equal the pick's card date - never last-token-only. */
     if(d.dataset.eid&&String(ev.id)!==d.dataset.eid)return;
     const atok=(d.dataset.away||'').toLowerCase().split(' ').pop(),htok=(d.dataset.home||'').toLowerCase().split(' ').pop();
     const nm=(ev.name||'').toLowerCase();
     if(nm.indexOf(atok)<0||nm.indexOf(htok)<0)return;
     const rd=(d.dataset.room||'').split('-').slice(1).join('-');
     if(rd&&ev.date){{const pd=new Intl.DateTimeFormat('en-CA',{{timeZone:'America/Los_Angeles',year:'numeric',month:'2-digit',day:'2-digit'}}).format(new Date(ev.date));if(pd!==rd)return;}}
     const ml=d.dataset.side==='away'?(o.awayTeamOdds||{{}}).moneyLine:(o.homeTeamOdds||{{}}).moneyLine;
     if(typeof ml==='number'){{const s=d.querySelector('.odds');if(s)s.textContent=(ml>0?'+':'')+ml;
      const chip=d.querySelector('a[data-book="ESPN"]');
      if(chip){{chip.innerHTML=chip.innerHTML.replace(/([+-]\d+)/,(ml>0?'+':'')+ml);rpCxUpdMl('ESPN');rpBestStar(d);}}}}
    }});
   }});
  }}).catch(()=>{{}});
 }});
}}catch(e){{}}}}
function rpKalTick(){{try{{
 document.querySelectorAll('a[data-kalticker][data-kalside]').forEach(function(a){{
  if(!a.dataset.kalticker||!a.dataset.kalside)return;
  const u='https://api.elections.kalshi.com/trade-api/v2/markets/'+a.dataset.kalticker+'-'+a.dataset.kalside;
  fetch('https://api.allorigins.win/raw?url='+encodeURIComponent(u)).then(r=>r.json()).then(function(j){{
   const m=j&&j.market;if(!m)return;
   if(m.result==='yes'){{a.dataset.won='1';a.dataset.lost='';rpCxUpd('KAL');return;}}
   if(m.result==='no'){{a.dataset.lost='1';a.dataset.won='';rpCxUpd('KAL');return;}}
   const d=parseFloat(m.yes_ask_dollars);if(!(d>0&&d<1))return;
   const c=Math.round(d*100);
   a.dataset.won='';a.dataset.lost='';
   a.innerHTML=a.innerHTML.replace(/KAL( [+-]?\d+| \u2713| \u2717)?/,'KAL '+rpMLF(rpC2ML(c)));rpCxUpd('KAL');
   const pk=a.closest('.pick');
   if(pk&&pk.dataset.market==='ml'){{const s=pk.querySelector('.odds');
    if(s&&c>0&&c<100){{const ml=c>=50?-Math.round(c/(100-c)*100):Math.round((100-c)/c*100);
     s.textContent=(ml>0?'+':'')+ml;rpBestStar(pk);}}}}
  }}).catch(()=>{{}}); /* graceful fallback: relay/API failure keeps last build price */
 }});
}}catch(e){{}}}}
rpPolyTick();rpEspnTick();rpKalTick();setInterval(function(){{rpPolyTick();rpEspnTick();rpKalTick();}},60000);
// sportsbook prices ride the 15-min Action rebuild (refresh.sh): pull the rebuilt page and swap
// book chip prices + combo price spans in place. KAL/POLY stay on the 60s tick above.
function rpPageRefresh(){{try{{
 fetch(location.pathname+'?r='+Date.now(),{{cache:'no-store'}}).then(r=>r.text()).then(function(t){{
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
  /* Sep 26 (data auditor): same membership rule for the combo row - a combo chip added/removed
     between builds forces a full reload, same as per-pick chips. */
  const ccmb=document.getElementById('rpParlayChips'),ncx=doc.getElementById('rpParlayChips');
  if(ccmb&&ncx){{
   const c1=[...ccmb.querySelectorAll('[data-book]')].map(a=>a.dataset.book).sort().join(',');
   const c2=[...ncx.querySelectorAll('[data-book]')].map(a=>a.dataset.book).sort().join(',');
   if(c1!==c2){{location.reload();return;}}
  }}
  document.querySelectorAll('.pick').forEach(function(pk){{
   const k=(pk.dataset.gpk||'')+'@'+(pk.dataset.room||'');const np=nmap[k];if(!np)return;  /* null = absent or collided */
   /* Sep 26 (hunter #10): data-only refresh can never ADD a newly verified chip or REMOVE a retired
      one - a membership change between served and new build forces a full reload instead. */
   /* Sep 26 refresh-loop fix: membership = [data-book] ANY tag + template status. rpTapify turns
      template spans into anchors once state is known; tag alone is not membership, so an upgraded
      live DOM vs a fresh static build must compare equal. A real add/retire/kind-change still reloads. */
   const rpSig=function(root){{return [...root.querySelectorAll('[data-book]')].map(a=>a.dataset.book+(a.dataset.template?':t':'')).sort().join(',');}};
   const curB=rpSig(pk),newB=rpSig(np);
   if(curB!==newB){{location.reload();return;}}
   pk.querySelectorAll('[data-book]').forEach(function(a){{
    const b=a.dataset.book;if(b==='POLY')return;
    /* any-tag counterpart: priced spans reprice too (state unknown); an upgraded anchor reprices
       from its static span counterpart (state known) */
    const na=np.querySelector('[data-book="'+b+'"]');if(!na)return;
    const m=na.textContent.match(/([+-]\d+)/);if(!m)return;
    a.innerHTML=a.innerHTML.replace(/([+-]\d+)/,m[1]);
    if(na.dataset.sbt){{  /* template chip: price and templated destination travel together; never a homepage route */
     if(a.tagName==='A'){{a.dataset.sb=na.dataset.sbt;if(window.rpSt)a.href=na.dataset.sbt.replaceAll('{{state}}',window.rpSt.toLowerCase());}}
     else a.dataset.sbt=na.dataset.sbt;
    }}else{{
     if(a.tagName==='A'&&na.href)a.href=na.href;
     if(na.dataset.sb)a.dataset.sb=na.dataset.sb;
    }}
   }});
   const lo=pk.querySelector('.odds'),ln=np.querySelector('.odds');
   if(lo&&ln&&ln.textContent)lo.textContent=ln.textContent;
   rpBestStar(pk);
  }});
  const cc=document.getElementById('rpParlayChips');const nc=doc.getElementById('rpParlayChips');
  if(cc&&nc){{cc.querySelectorAll('[data-book]').forEach(function(s){{
   const b=s.dataset.book;if(b==='KAL'||b==='POLY')return;
   const ns=nc.querySelector('[data-book="'+b+'"]');
   if(ns){{const m=ns.textContent.match(/([+-]\d+)/);if(m)s.innerHTML=s.innerHTML.replace(/([+-]\d+)/,m[1]);
    if(ns.dataset.sbt){{if(s.tagName==='A'){{s.dataset.sb=ns.dataset.sbt;if(window.rpSt)s.href=ns.dataset.sbt.replaceAll('{{state}}',window.rpSt.toLowerCase());}}else s.dataset.sbt=ns.dataset.sbt;}}
    else{{if(s.tagName==='A'&&ns.href)s.href=ns.href;if(ns.dataset.sb)s.dataset.sb=ns.dataset.sb;}}
    if(ns.dataset.pm)s.dataset.pm=ns.dataset.pm;}}  /* Sep 26: destination travels with price - no stale parlay links; template chips swap data-sbt/data-sb, never a homepage route */
  }});rpCxStar();}}
 }}).catch(()=>{{}});
}}catch(e){{}}}}
setInterval(rpPageRefresh,60000);
</script>
<script src="myprofile.js?v={{build_sha}}"></script></div></body></html>'''

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
    NAME2KEY={'draftkings':'DK','fanduel':'FD','espnbet':'ESPN','hardrockbet':'HR'}
    RP_CONSTS=('const RP_FD='+json.dumps(RP_FD)+';const RP_DK='+json.dumps(RP_DK)+';\n'
        'const RP_L={FD:RP_FD,DK:RP_DK,MGM:'+json.dumps(RP_MGM)+',B365:'+json.dumps(RP_B365)+',FAN:'+json.dumps(RP_FAN)+',ESPN:'+json.dumps(RP_ESPN)+',HR:'+json.dumps(RP_HR)+',BR:'+json.dumps(RP_BR)+'};')
    STATE_OPTS=''.join('<option value="%s">%s</option>'%(c,n) for c,n in RP_STATES)
    def rt(short,url,tmpl_flag):
        # Sep 26: href never carries a raw {state} (context menu/no-JS 404s) - base domain href,
        # template lives in data-sb, rpGo substitutes the verified state at tap time.
        t=' data-template="1"' if tmpl_flag else ''
        href=('https://www.'+BKDOM[short]) if tmpl_flag else url
        return 'data-book="%s" data-sb="%s"%s onclick="return rpRoute(event,this)" href="%s" target="_blank" rel="noreferrer"'%(short,html.escape(url),t,html.escape(href))
    for p in man.get('picks',[]):
        g=p.get('game') or {}
        if not g: continue
        away,home=g.get('away',''),g.get('home','')
        side=p.get('side','away')
        carded_team=g.get(side,'')
        rows_html=[]
        books_present=[]
        hrow={'away':away,'home':home}
        pr=sel_books(pre.get((away,home)), g) or {}
        for key,short in NAME2KEY.items():
            rec=pr.get(key) or {}
            aml,hml=rec.get('away_ml'),rec.get('home_ml')
            if aml is None and hml is None: continue
            alink=rec.get('away_link') or rec.get('event') or ('https://www.'+BKDOM[short])
            hlink=rec.get('home_link') or rec.get('event') or ('https://www.'+BKDOM[short])
            a_lbl=('%+d'%aml) if aml is not None else '-'
            h_lbl=('%+d'%hml) if hml is not None else '-'
            rows_html.append('<div class="mrow" data-book="'+short+'">'+bkimg(short)+'<span class="bk">'+short+'</span>'
                '<span class="side"><a '+rt(short,alink,'{state}' in alink)+'>'+html.escape(away)+'</a></span><span class="pr"><a '+rt(short,alink,'{state}' in alink)+'>'+a_lbl+'</a></span>'
                '<span class="side" style="text-align:right"><a '+rt(short,hlink,'{state}' in hlink)+'>'+html.escape(home)+'</a></span><span class="pr"><a '+rt(short,hlink,'{state}' in hlink)+'>'+h_lbl+'</a></span></div>')
            hrow[short.lower()+'_a']=aml; hrow[short.lower()+'_h']=hml
            books_present.append(short)
        stt=pr.get('state_templates') or {}
        for key,short in (('betmgm','MGM'),('betrivers','BR')):
            rec=stt.get(key) or {}
            aml,hml=rec.get('away_ml'),rec.get('home_ml')
            if aml is None and hml is None: continue
            link=rec.get('event') or ('https://www.'+BKDOM[short])
            a_lbl=('%+d'%aml) if aml is not None else '-'
            h_lbl=('%+d'%hml) if hml is not None else '-'
            rows_html.append('<div class="mrow" data-book="'+short+'">'+bkimg(short)+'<span class="bk">'+short+'</span>'
                '<span class="side"><a '+rt(short,link,'{state}' in link)+'>'+html.escape(away)+'</a></span><span class="pr"><a '+rt(short,link,'{state}' in link)+'>'+a_lbl+'</a></span>'
                '<span class="side" style="text-align:right"><a '+rt(short,link,'{state}' in link)+'>'+html.escape(home)+'</a></span><span class="pr"><a '+rt(short,link,'{state}' in link)+'>'+h_lbl+'</a></span></div>')
            hrow[short.lower()+'_a']=aml; hrow[short.lower()+'_h']=hml
            books_present.append(short)
        # Kalshi full board (user, Sep 25 12:19 PM): both sides, live-ticked. Fallback: single-side tap row.
        kal_html=''
        if p.get('kalshi'):
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
            if am and hm:
                kal_html=('<div class="mrow" data-book="KAL">'+bkimg('KAL')+'<span class="bk">KAL</span>'
                    '<span class="side"><a '+rt('KAL',base+'-'+am[1].lower(),False)+'>'+html.escape(away)+'</a></span>'
                    '<span class="pr"><a data-kalmkt="'+am[0]+'" '+rt('KAL',base+'-'+am[1].lower(),False)+'>KAL '+c2ml(am[2])+'</a></span>'
                    '<span class="side" style="text-align:right"><a '+rt('KAL',base+'-'+hm[1].lower(),False)+'>'+html.escape(home)+'</a></span>'
                    '<span class="pr"><a data-kalmkt="'+hm[0]+'" '+rt('KAL',base+'-'+hm[1].lower(),False)+'>KAL '+c2ml(hm[2])+'</a></span></div>')
                hrow['kal_a']=am[2]; hrow['kal_h']=hm[2]
            else:
                kside=html.escape(p['kalshi'].get('team',''))
                kal_html=('<div class="mrow" data-book="KAL">'+bkimg('KAL')+'<span class="bk">KAL</span>'
                    '<span class="side"><a '+rt('KAL',kurl,False)+'>'+html.escape(carded_team)+'</a></span>'
                    '<span class="pr"><a data-kalticker="'+tick+'" data-kalside="'+kside+'" '+rt('KAL',kurl,False)+'>KAL '+str(c2ml(p['kalshi']['cents']))+'</a></span>'
                    '<span class="side" style="text-align:right;color:#8a8f98">full board on Kalshi</span><span class="pr"></span></div>')
                cc=p['kalshi']['cents']
                hrow['kal_a']=cc if side=='away' else None
                hrow['kal_h']=cc if side=='home' else None
            books_present.append('KAL')
        # Polymarket full board (user, Sep 25 12:19 PM): both sides, live-ticked. Fallback: single-side tap row.
        poly_html=''
        if p.get('polymarket'):
            _gs=poly_event_slug(p['polymarket']['url']) or ''
            web=('https://polymarket.us/event/'+_gs) if _gs else ((p.get('polymarket_us') or {}).get('url') or (p.get('polymarket') or {})['url'].replace('https://polymarket.com/','https://polymarket.us/'))
            slug=poly_event_slug(p['polymarket']['url']) or ''
            sub=poly_sub(p['polymarket']['url']) or ''
            akw=away.split()[-1]; hkw=home.split()[-1]
            ca=poly_price(p['polymarket']['url'],akw); chv=poly_price(p['polymarket']['url'],hkw)
            pvol=0.0
            try:
                import urllib.request
                _ev=_espn_get('https://gamma-api.polymarket.com/events?slug='+slug)
                if _ev: pvol=float(_ev[0].get('volume') or _ev[0].get('volumeNum') or 0)
            except Exception: pass
            if ca or chv:
                la=('POLY '+c2ml(ca)) if ca else 'POLY'
                lh=('POLY '+c2ml(chv)) if chv else 'POLY'
                pa='data-book="POLY" data-sb="'+html.escape(web)+'" data-app="'+html.escape(web)+'" onclick="return rpRoute(event,this)" href="'+html.escape(web)+'" target="_blank" rel="noreferrer"'
                poly_html=('<div class="mrow" data-book="POLY">'+bkimg('POLY')+'<span class="bk">POLY</span>'
                    '<span class="side"><a '+pa+'>'+html.escape(away)+'</a></span>'
                    '<span class="pr"><a data-polyslug="'+html.escape(slug)+'" data-polysub="'+html.escape(sub)+'" data-polykw="'+html.escape(akw)+'" '+pa+'>'+la+'</a></span>'
                    '<span class="side" style="text-align:right"><a '+pa+'>'+html.escape(home)+'</a></span>'
                    '<span class="pr"><a data-polyslug="'+html.escape(slug)+'" data-polysub="'+html.escape(sub)+'" data-polykw="'+html.escape(hkw)+'" '+pa+'>'+lh+'</a></span></div>')
                hrow['poly_a']=ca; hrow['poly_h']=chv
            else:
                kw=p['name'].split()[0]
                cents=poly_price(p['polymarket']['url'],kw)
                lbl=('POLY '+str(c2ml(cents))) if cents else 'POLY'
                poly_html=('<div class="mrow" data-book="POLY">'+bkimg('POLY')+'<span class="bk">POLY</span>'
                    '<span class="side"><a data-book="POLY" data-sb="'+html.escape(web)+'" data-app="'+html.escape(web)+'" onclick="return rpRoute(event,this)" href="'+html.escape(web)+'" target="_blank" rel="noreferrer">'+html.escape(carded_team)+'</a></span>'
                    '<span class="pr"><a data-polyslug="'+html.escape(slug)+'" data-polysub="'+html.escape(sub)+'" data-polykw="'+html.escape(kw)+'" data-book="POLY" data-sb="'+html.escape(web)+'" data-app="'+html.escape(web)+'" onclick="return rpRoute(event,this)" href="'+html.escape(web)+'" target="_blank" rel="noreferrer">'+lbl+'</a></span>'
                    '<span class="side" style="text-align:right;color:#8a8f98">full board on Polymarket</span><span class="pr"></span></div>')
                hrow['poly_a']=cents if side=='away' else None
                hrow['poly_h']=cents if side=='home' else None
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
        if books_present:
            charts_html=('<div class="sect">Price history</div>'
                '<div class="chartcard" data-books="'+' '.join(books_present)+'" style="padding:12px 0 8px;border-bottom:1px solid rgba(127,127,127,.15)">'
                '<svg class="rpchart" id="chart-main" viewBox="0 0 340 190" style="width:100%;height:auto;display:block"></svg>'
                '<div id="chartlegend" style="display:flex;flex-wrap:wrap;gap:8px;margin-top:6px;font-size:11px"></div>'
                '<div style="display:flex;justify-content:flex-end;font-size:11px;color:#8a8f98;margin-top:4px">'
                '<span class="rpranges"><span data-r="1D" style="padding:2px 6px;cursor:pointer">1D</span> <span data-r="1W" style="padding:2px 6px;cursor:pointer">1W</span> <span data-r="1M" style="padding:2px 6px;cursor:pointer">1M</span> <span data-r="ALL" style="padding:2px 6px;cursor:pointer;font-weight:700">ALL</span></span></div></div>')
        HIST[(away,home)]=hrow
        ch=_chips_fn(p)
        espn=html.escape(p.get('espn_league',''))
        mkt='spread' if p.get('market')=='spread' else 'ml'
        when=_pt_label(g.get('commence',''))
        inst=game_instance(g)
        inst_lbl=(' ('+inst+')') if inst else ''
        page_html=tmpl
        for tok,val in [('__TITLE__',html.escape(away+' at '+home)),('__CSS__',css),('__NUM__',str(p['num'])),
            ('__INST__',inst_lbl),('__ESPN__',espn),('__AWAY__',html.escape(away)),('__HOME__',html.escape(home)),('__GPK__',_gpk_for(away,home,g.get('commence',''))[0]),('__AAB__',_gpk_for(away,home,g.get('commence',''))[1]),('__HAB__',_gpk_for(away,home,g.get('commence',''))[2]),
            ('__EID__',html.escape(str(g.get('eid') or ''))),('__COUNTED__',' data-counted="1"' if p.get('result') in ('WIN','LOSS','PUSH') else ''),
            ('__SIDE__',side),('__MKT__',mkt),('__NAME__',html.escape(p['name'])),('__UNITS__',html.escape(p.get('units',''))),
            ('__ODDS__',html.escape(p['odds'])),('__SUB__',html.escape(p.get('sub',''))),('__WHEN__',html.escape(when)),
            ('__CHIPS__',ch),('__MATCHUP__',matchup),('__TEAMLINKS__',teamlinks),('__ROWS__',''.join(rows_html)),('__KAL__',kal_html),('__POLY__',poly_html),('__ROOM__','g%s-%s'%(p['num'],(_pt_date(g.get('commence','')) or 'card'))),('__START__',g.get('commence','') or ''),
            ('__CHARTS__',charts_html),('__BUILD__',build_sha),('__RPCONSTS__',RP_CONSTS),('__STATEOPTS__',STATE_OPTS)]:
            page_html=page_html.replace(tok,val)
        pages['game-%s.html'%p['num']]=page_html
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
open(out,'w').write(page)
_css=page.split('<style>')[1].split('</style>')[0]

FUTURES_TMPL='''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RixPicks Futures</title><style>__CSS__</style><style>body{overscroll-behavior-y:none}.wrap{min-height:101vh}</style><meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<script src="https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.page.js" defer></script>
<script>window.OneSignalDeferred=window.OneSignalDeferred||[];OneSignalDeferred.push(async function(OneSignal){try{await OneSignal.init({appId:"5e86ebe3-a135-4984-9623-db83a0f1840c",serviceWorkerPath:"OneSignalSDKWorker.js",serviceWorkerParam:{scope:"/rixpicks/"}});}catch(e){}});</script>
</head><body>
<div id="rpPull"></div>
<div class="wrap">
<h1><span class="tick">&rsquo;</span>RixPicks</h1>
<div class="status">Futures &middot; __COUNT__ picks &middot; live Polymarket tracking vs carded entry</div>
<div class="intro">Entry = the price we carded. Live = current market. Arrow shows movement since entry.</div>
__ROWS__
<div id="rpFd" style="display:none;position:fixed;top:0;left:0;right:0;bottom:0;z-index:70;background:rgba(0,0,0,.78);align-items:flex-end;justify-content:center" onclick="if(event.target===this)this.style.display='none'"><div id="rpFdBox" style="background:#000000;border-top:1px solid rgba(255,255,255,.14);border-radius:16px 16px 0 0;width:100%;max-width:520px;max-height:78vh;overflow-y:auto;padding:16px;color:#ECECF1"></div></div>
<div class="unitmath" style="margin-top:18px">Live prices via Polymarket &middot; refresh 60s &middot; build __BUILD__</div>
</div>
<script>
async function rpFutTick(){
 var bySlug={};
 document.querySelectorAll('.futrow[data-pslug]').forEach(function(r){
  if(!r.dataset.pslug)return;
  (bySlug[r.dataset.pslug]=bySlug[r.dataset.pslug]||[]).push(r);
 });
 var slugs=Object.keys(bySlug);
 for(var s=0;s<slugs.length;s++){
  try{
   var res=await fetch('https://gamma-api.polymarket.com/events?slug='+slugs[s]);
   var ev=await res.json();
   if(!ev||!ev.length)continue;
   var mkts=ev[0].markets||[];
   bySlug[slugs[s]].forEach(function(r){
    var kw=(r.dataset.pkw||'').toLowerCase();
    var m=null;
    for(var i=0;i<mkts.length;i++){if((mkts[i].question||'').toLowerCase().indexOf(kw)>=0){m=mkts[i];break;}}
    if(!m)return;
    var outs=[];try{outs=JSON.parse(m.outcomes||'[]');}catch(e){}
    var pr=[];try{pr=JSON.parse(m.outcomePrices||'[]');}catch(e){}
    var idx=0;
    for(var j=0;j<outs.length;j++){if(String(outs[j]).toLowerCase()==='yes'){idx=j;break;}}
    var p=parseFloat(pr[idx]);
    if(!(p>0&&p<1))return;
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
 }
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
rpFutTick();setInterval(rpFutTick,60000);
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
var rpFdCache={};
function rpFdClose(){document.getElementById('rpFd').style.display='none';}
function rpFutOpen(fid){
 var r=document.querySelector('.futrow[data-fid="'+fid+'"]');if(!r)return;
 var sh=document.getElementById('rpFd');var bx=document.getElementById('rpFdBox');
 var team=r.dataset.team,mkt=r.dataset.mkt,entry=r.dataset.entry,fair=r.dataset.fair,prob=r.dataset.prob,res=r.dataset.res,units=r.dataset.units,note=r.dataset.note;
 var h='<h3>'+team+'</h3><div class="rp-sub">'+mkt+'</div>';
 h+='<div class="rp-bet"><b>Why this pick</b><div style="margin-top:4px">Carded at <b>'+entry+'</b>'+(fair?' - our fair price was <b>'+fair+'</b>':'')+(prob?' (we rate it ~'+Math.round(parseFloat(prob)*100)+'% vs the '+entry+' implied price)':'')+'. The gap between our number and the market price is the edge; we sized '+(units||'2')+'u on it.</div>'+(note?'<div style="margin-top:4px;color:#9A9AA3">'+note+'</div>':'')+(res?'<div style="margin-top:4px;color:#9A9AA3">Resolves: '+res+'</div>':'')+'</div>';
 h+='<div class="rp-bet" id="rpFdLive"><b>Live market</b><div style="margin-top:4px" id="rpFdLiveBody">loading...</div></div>';
 bx.innerHTML=h+'<button class="rp-btn ghost" onclick="rpFdClose()">Close</button>';
 sh.style.display='flex';
 var slug=r.dataset.pslug,kw=(r.dataset.pkw||'').toLowerCase();
 function render(m){
  var b=document.getElementById('rpFdLiveBody');if(!b)return;
  try{
   var outs=JSON.parse(m.outcomes||'[]'),pr=JSON.parse(m.outcomePrices||'[]'),idx=0;
   for(var j=0;j<outs.length;j++){if(String(outs[j]).toLowerCase()==='yes'){idx=j;break;}}
   var p=parseFloat(pr[idx]);var c=p*100;
   var ml=c>=50?-Math.round(c/(100-c)*100):Math.round((100-c)/c*100);
   var eMl=parseInt(String(entry).replace('+',''),10)||100;
   var eImp=eMl>0?100/(eMl+100):(-eMl)/((-eMl)+100);
   var d=(p-eImp)*100;
   var arrow=d>0.5?'<span style="color:#3ecf6f">&#9650; '+d.toFixed(1)+' pts since entry</span>':(d<-0.5?'<span style="color:#e5484d">&#9660; '+Math.abs(d).toFixed(1)+' pts since entry</span>':'flat vs entry');
   var v24=m.volume24hr?('$'+Math.round(m.volume24hr).toLocaleString()+' traded in last 24h'):'';
   var liq=m.liquidity?(' &middot; $'+Math.round(m.liquidity).toLocaleString()+' liquidity'):'';
   var d1=(m.oneDayPriceChange!=null)?((m.oneDayPriceChange*100>=0?'+':'')+(m.oneDayPriceChange*100).toFixed(1)+' pts last 24h'):'';
   b.innerHTML='Live price <b>'+(ml>0?'+':'')+ml+'</b> ('+c.toFixed(1)+'%) &middot; '+arrow+'<div style="margin-top:4px;color:#9A9AA3">'+[d1,v24+liq].filter(Boolean).join(' &middot; ')+'</div>';
  }catch(e){b.textContent='live data unavailable';}
 }
 if(rpFdCache[slug]){var mm=null;for(var i=0;i<rpFdCache[slug].length;i++){if((rpFdCache[slug][i].question||'').toLowerCase().indexOf(kw)>=0){mm=rpFdCache[slug][i];break;}}if(mm){render(mm);return;}}
 fetch('https://gamma-api.polymarket.com/events?slug='+slug).then(function(r2){return r2.json();}).then(function(ev){
  var mkts=(ev&&ev[0]&&ev[0].markets)||[];rpFdCache[slug]=mkts;var mm=null;
  for(var i=0;i<mkts.length;i++){if((mkts[i].question||'').toLowerCase().indexOf(kw)>=0){mm=mkts[i];break;}}
  if(mm)render(mm);else{var b=document.getElementById('rpFdLiveBody');if(b)b.textContent='market not found';}
 }).catch(function(){var b=document.getElementById('rpFdLiveBody');if(b)b.textContent='live data unavailable';});
}
</script>
<script src="myprofile.js?v=__BUILD__"></script></body></html>'''
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
        _furl='https://polymarket.us/event/'+f.get('poly_slug','') if f.get('poly_slug') else ''
        if _furl and not _link_alive(_furl):
            print(f"LINK DROP: futures {f.get('team')} dead/generic .us destination: {_furl}", file=sys.stderr)
            _furl=''
        _flink=('<div style="margin-top:6px"><a class="chip"%s href="%s" data-book="POLY" data-sb="%s" target="_blank" rel="noreferrer">POLY &#8250;</a></div>'%(bkstyle('POLY'),html.escape(_furl),html.escape(_furl))) if _furl else ''
        rows.append(('<div class="futrow" data-fid="%s" data-pslug="%s" data-pkw="%s" data-entry="%s" data-team="%s" data-mkt="%s" data-fair="%s" data-prob="%s" data-res="%s" data-units="%s" data-note="%s" style="padding:12px 0;border-bottom:1px solid rgba(127,127,127,.15)">'
        '<div style="display:flex;justify-content:space-between;align-items:baseline;gap:10px">'
        '<span style="font-weight:700">'+('<img src="https://a.espncdn.com/i/teamlogos/'+_REGALL.get(f.get('league',''),{}).get('logo_dir','')+'/500/'+f.get('abbr','')+'.png" style="width:20px;height:20px;border-radius:50%%;vertical-align:-4px;margin-right:7px" onerror="this.remove()">' if f.get('abbr') and _REGALL.get(f.get('league',''),{}).get('logo_dir') else '')+'%s</span>'
        '<span style="white-space:nowrap"><span class="futlive" style="font-weight:700;color:#3aa895">&hellip;</span><button class="futdots" onclick="rpFutOpen(this.getAttribute(\'data-f\'))" data-f="%s" style="background:none;border:none;color:#8a8f98;font-size:16px;padding:2px 2px 2px 8px;cursor:pointer;vertical-align:1px">&#8943;</button></span></div>'
        '<div style="font-size:12px;color:#8a8f98;margin-top:2px">%s &middot; entry %s &middot; %su%s</div>'
        + ('<div style="font-size:12px;margin-top:3px;color:#d8a23a">&#8646; pick changed from %s (%s)</div>'%(html.escape(f['changed_from']['team']),html.escape(f['changed_from']['odds'])) if f.get('changed_from') else '')
        + _flink
        + '<div class="futmove" style="font-size:12px;margin-top:3px;color:#8a8f98"></div></div>')
        %(html.escape(f['id']),html.escape(f.get('poly_slug','')),html.escape(f.get('poly_kw','')),html.escape(f['odds']),
          html.escape(f['team']),html.escape(f['market']),html.escape(f.get('fair','')),html.escape(str(f.get('prob',''))),html.escape(f.get('res','')),str(f.get('units',2)),html.escape(f.get('note','')),
          html.escape(f['team']),html.escape(f['id']),html.escape(f['market']),html.escape(f['odds']),f.get('units',2),(' &middot; '+html.escape(f['note']) if f.get('note') else '')))
    pg=FUTURES_TMPL
    for tok,val in [('__CSS__',css),('__ROWS__',''.join(rows)),('__COUNT__',str(len(FUT))),('__BUILD__',build_sha)]:
        pg=pg.replace(tok,val)
    return pg
_fp=build_futures_page(_css,build_sha)
if _fp:
    # Sep 26 builder fix: futures page must land in the OUTPUT dir like every other page -
    # writing to cwd silently dropped it from candidate builds (and clobbered the repo copy on test runs).
    open(os.path.join(os.path.dirname(out) or '.','futures.html'),'w').write(_fp)
    print('written: futures.html',len(_fp))
for _fn,_html in build_team_pages(man,_css,build_sha).items():
    open(os.path.join(os.path.dirname(out) or '.',_fn),'w').write(_html)
    print('written:',_fn,len(_html))
for _fn,_html in build_game_pages(man,_css,build_sha).items():
    open(os.path.join(os.path.dirname(out) or '.',_fn),'w').write(_html)
    print('written:',_fn,len(_html))
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
    except Exception as _e:
        print(f'LEDGER WRITE FAILED: shipped_books.json not persisted ({type(_e).__name__}: {_e}) - J-106/J-101 defenses degraded', file=sys.stderr)
        sys.exit(4)
