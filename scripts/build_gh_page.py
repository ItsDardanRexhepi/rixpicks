#!/usr/bin/env python3
"""Generate a self-contained index.html ('RixPicks picks page) for GitHub Pages from a manifest JSON.
Usage: build_gh_page.py manifest.json [outfile]
Manifest: {date_label, status_note, record, updated, picks:[{num,name,sub,odds,best_book,side,game:{away,home}|null,espn_league}], parlay:{legs:[...],note}|null}
DESIGN LOCKED (user, Sep 24 10:50 PM): this template IS the app design system. Daily builds change picks
content only - never layout, chip styling, terminology logic. Bump RP_DESIGN only on an approved design change.
Chips resolved from /tmp/odds_prefill.json (+ _sp) when present; NO chips render without a game-level link.
Branding: 'RixPicks only. No personal identifiers, ever.
"""
import json,sys,html,re

RP_DESIGN='1.2.0'  # locked design system version - bump only on user-approved design change. v1.1.0 (user, Sep 25 12:35 AM): match visitor system appearance - light (default, unchanged) + dark via prefers-color-scheme. v1.2.0 (user, Sep 25 8:46 AM): current page shape approved as THE standing daily template - header without FINAL line, tap-any-book intro, per-pick chips + units, combo section, record + unit line, minimal footer (reference commit fbec1c1). Every morning build reproduces this exact shape; changes only on his explicit instruction.

man=json.load(open(sys.argv[1]))
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
LG_LABEL={'baseball/mlb':'MLB','football/nfl':'NFL','basketball/nba':'NBA','hockey/nhl':'NHL','basketball/wnba':'WNBA','football/college-football':'CFB','basketball/college-basketball':'CBB','tennis':'Tennis'}
def poly_event_slug(url):
    try: return url.split('/event/')[1].split('/')[0]
    except Exception: return None
def poly_sub(url):
    try:
        parts=url.split('/event/')[1].split('/')
        return parts[1] if len(parts)>1 and parts[1] else None
    except Exception: return None
def poly_price(url,kw):
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
        if target is None: return None
        outs=json.loads(target.get('outcomes') or '[]'); prs=json.loads(target.get('outcomePrices') or '[]')
        for i,o in enumerate(outs):
            if kwl in str(o).lower() and i<len(prs):
                c=round(float(prs[i])*100)
                if 0<c<100: return c
    except Exception: return None
    return None
def _load_prefill(path, wrap=False):
    out={}
    try:
        for g in json.load(open(path)):
            books=g.get('books',{})
            out.setdefault((g['away'],g['home']),[]).append((g.get('commence'), {'books':books} if wrap else books))
    except Exception: pass
    return out
HIST={}
pre=_load_prefill('/tmp/odds_prefill.json')

def _espn_get(url):
    import urllib.request
    # ESPN 403s a bare 'Mozilla/5.0' UA (verified Sep 25); urllib default UA passes.
    with urllib.request.urlopen(url,timeout=12) as r: return json.load(r)

def team_meta(man):
    meta={}
    lgs={p.get('espn_league','') for p in man.get('picks',[]) if p.get('espn_league')}
    for lg in lgs:
        try:
            sb=_espn_get('https://site.api.espn.com/apis/site/v2/sports/%s/scoreboard'%lg)
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


pre_sp=_load_prefill('/tmp/odds_prefill_sp.json', wrap=True)
TEAM_META.update(team_meta(man))
LG_BALL={'baseball/mlb':'\u26be','football/nfl':'\U0001f3c8','football/college-football':'\U0001f3c8','basketball/nba':'\U0001f3c0','basketball/wnba':'\U0001f3c0','basketball/college-basketball':'\U0001f3c0','hockey/nhl':'\U0001f3d2','tennis':'\U0001f3be'}

def game_instance(game):
    # J-092 (user, Sep 25 10:05 AM): when a team plays twice in a day, every chip must NAME
    # the game instance at tap time so the destination is never ambiguous.
    if not game: return ''
    cands=pre.get((game.get('away'),game.get('home')))
    if not cands or len(cands)<2: return ''
    ordered=sorted(c for c,_ in cands if c)
    com=game.get('commence')
    if com and com in ordered: return f"G{ordered.index(com)+1}"
    return ''

def sel_books(cands, game):
    # J-090 doubleheader fix (user, Sep 25 9:50 AM): match book data to the exact game
    # instance (commence), never the matchup alone. Same-team doubleheader with a
    # missing/unmatched commence -> suppress book links and warn loudly; never link
    # the wrong game.
    if not cands: return {}
    if len(cands)==1: return cands[0][1]
    com=(game or {}).get('commence')
    for c,b in cands:
        if com and c and c[:16]==com[:16]: return b
    print(f"DOUBLEHEADER WARNING: {game.get('away')} @ {game.get('home')} has {len(cands)} market entries, no commence match ({com!r}); book chips suppressed", file=sys.stderr)
    return {}

def chips(p):
    star='\u2605 '
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
            link=p['kalshi']['url']; label=f"KAL {c2ml(p['kalshi']['cents'])}"+inst
            if p.get('best_book')=='Kalshi': label=label
            tick=p['kalshi']['url'].rstrip('/').split('/')[-1].upper()
            best=(p.get('best_book')=='Kalshi')
            side=html.escape(p.get('kalshi',{}).get('team',''))
            out.append(f'<a class="chip{" best" if best else ""}"{bkstyle(short)} href="{html.escape(link)}" data-kalticker="{tick}" data-kalside="{side}" target="_blank" rel="noreferrer">{star if best else ""}{bkimg(short)}{label}</a>')
            continue
        if name=='Polymarket':
            if not p.get('polymarket'): continue
            web=p.get('polymarket_us',{}).get('url') or p['polymarket']['url'].replace('https://polymarket.com/','https://polymarket.us/'); app=web
            slug=poly_event_slug(p['polymarket']['url']) or ''
            sub=poly_sub(p['polymarket']['url']) or ''
            cents=poly_price(p['polymarket']['url'],kw)
            label=(f"POLY {c2ml(cents)}" if cents else "POLY")+inst
            if p.get('best_book')=='Polymarket': label=label
            best=(p.get('best_book')=='Polymarket')
            out.append(f'<a class="chip{" best" if best else ""}"{bkstyle("POLY")} href="{html.escape(web)}" data-book="POLY" data-sb="{html.escape(web)}" data-app="{html.escape(app)}" data-polyslug="{html.escape(slug)}" data-polysub="{html.escape(sub)}" data-polykw="{html.escape(kw)}" onclick="return rpRoute(event,this)" target="_blank" rel="noreferrer">{star if best else ""}{bkimg("POLY")}{label}</a>')
            continue
        if not link: continue  # no game-level link -> drop chip
        best=(p.get('best_book')==name)
        label=(f"{short} {ml:+d}" if ml is not None else short)+inst
        # star renders left of logo at append time
        if name in ('FanDuel','DraftKings'):
            pm='https://www.fanduel.com/predicts' if name=='FanDuel' else (p.get('dkp',{}).get('url') or 'https://predictions.draftkings.com/')
            pmapp='https://predicts.fanduel.com/' if name=='FanDuel' else ''
            nopm=' data-nopm="1"' if (name=='DraftKings' and not p.get('dkp',{}).get('url')) else ''
            out.append(f'<a class="chip{" best" if best else ""}"{bkstyle(short)} href="{html.escape(link)}" data-book="{short}" data-sb="{html.escape(link)}" data-pm="{html.escape(pm)}" data-pmapp="{html.escape(pmapp)}"{nopm} onclick="return rpRoute(event,this)" target="_blank" rel="noreferrer">{star if best else ""}{bkimg(short)}{html.escape(label)}</a>')
        elif '{state}' in link:
            out.append(f'<a class="chip{" best" if best else ""}"{bkstyle(short)} href="{html.escape(link)}" data-book="{short}" data-sb="{html.escape(link)}" data-template="1" onclick="return rpRoute(event,this)" target="_blank" rel="noreferrer">{star if best else ""}{bkimg(short)}{html.escape(label)}</a>')
        else:
            out.append(f'<a class="chip{" best" if best else ""}"{bkstyle(short)} href="{html.escape(link)}" data-book="{short}" data-sb="{html.escape(link)}" onclick="return rpRoute(event,this)" target="_blank" rel="noreferrer">{star if best else ""}{bkimg(short)}{html.escape(label)}</a>')
    return ''.join(out)

_chips_fn=chips
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
    for _mm in re.finditer(r'href="([^"]+)"[^>]*data-book="([A-Z]+)"', ch):
        _pg=p.get('game') or {}
        SEEN.append((_mm.group(2), _mm.group(1), (_pg.get('away',''),_pg.get('home',''),_pg.get('commence',''))))
    chips_html=f'<div class="chips">{ch}</div>' if ch else ''
    espn=html.escape(p.get('espn_league',''))
    mkt='spread' if p.get('market')=='spread' else 'ml'
    g=p.get('game') or {}
    _lga=p.get('espn_league','')
    _ma=TEAM_META.get((_lga,g.get('away',''))) or {}; _mh=TEAM_META.get((_lga,g.get('home',''))) or {}
    def _avimg(mm,overlap=False):
        u=mm.get('logo','')
        if not u: return ''
        st='width:26px;height:26px;object-fit:contain;border-radius:50%;background:rgba(127,127,127,.14)'
        if overlap: st+=';margin-left:-7px'
        return '<img src="%s" alt="" style="%s" onerror="this.remove()">'%(html.escape(u),st)
    _av=_avimg(_ma)+_avimg(_mh,True)
    _avhtml='<span style="display:inline-flex;flex-shrink:0;align-items:center">'+_av+'</span>' if _av else ''
    rows.append(f'''<div class="pick" data-espn="{espn}" data-away="{html.escape(g.get('away',''))}" data-home="{html.escape(g.get('home',''))}" data-side="{p.get('side','away')}" data-market="{mkt}" data-codds="{html.escape(p.get('odds',''))}">
  <div class="pick-head"><a class="gamelink" href="game-{p['num']}.html">{_avhtml}<span class="num">{p['num']}.</span><span class="name">{html.escape(p['name'])}</span><span class="units">{html.escape(p.get('units',''))}</span><span class="odds">{html.escape(p['odds'])}</span></a><a class="chev" href="game-{p['num']}.html" aria-label="live markets">&rsaquo;</a></div><span class="ls" data-ls></span>
  <div class="sub">{html.escape(p['sub'])}</div>
  {chips_html}
</div>''')

_seen={}
for _bk,_lnk,_gk in SEEN:
    _k=(_bk,_lnk)
    if _k in _seen and _seen[_k]!=_gk:
        print(f"DOUBLEHEADER REGRESSION: {_bk} link reused across different game instances: {_lnk[:120]}", file=sys.stderr)
        sys.exit(2)
    _seen[_k]=_gk

parlay_html=''
if man.get('parlay'):
    pl=man['parlay']
    def _leg_li(l):
        m=[p for p in man['picks'] if p['name'].lower() in l.lower() or l.lower() in p['name'].lower()]
        if not m: return f'<li>{html.escape(l)}</li>'
        p=m[0]; g=p.get('game') or {}
        return ('<li class="cxleg" data-espn="%s" data-away="%s" data-home="%s" data-side="%s"><a href="game-%s.html" style="color:inherit;text-decoration:none">%s</a><span class="ls" data-ls></span></li>'
                % (html.escape(p.get('espn_league','')), html.escape(g.get('away','')), html.escape(g.get('home','')), html.escape(p.get('side','away')), p['num'], html.escape(l)))
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
        kc=None
        if pl.get('kalshi_legs') and len(pl['kalshi_legs'])==nlegs:
            kc=[l['cents'] for l in pl['kalshi_legs'] if l.get('cents')]
            hidden=''.join(f'<a data-cxleg="KAL" data-kalticker="{html.escape(l["ticker"])}" data-kalside="{html.escape(l["side"])}" style="display:none">KAL {c2ml(l["cents"])}</a>' for l in pl['kalshi_legs'] if l.get('cents'))
        else:
            kc=[p['kalshi']['cents'] for p in lp if p.get('kalshi') and p['kalshi'].get('cents')]
            hidden=''
        if kc and len(kc)==nlegs:
            c=amer_from_cents(kc)
            if c is not None:
                chips.append(('KAL',f'<a class="chip%%BEST%%"{bkstyle("KAL")} href="https://kalshi.com/category/sports/all-sports" data-book="KAL" data-sb="https://kalshi.com/category/sports/all-sports" id="rpCxKAL" data-n="{nlegs}" onclick="return rpRoute(event,this)" target="_blank" rel="noreferrer">%%STAR%%{bkimg("KAL")}KAL {c2ml(c)}</a>{hidden}',int(c2ml(c))))
        pc=[]; okp=True; purl='https://polymarket.us'; phidden=''
        if pl.get('poly_legs') and len(pl['poly_legs'])==nlegs:
            for l in pl['poly_legs']:
                cc=poly_price(l['url'], l.get('kw',''))
                if not cc: okp=False; break
                pc.append(cc)
                slug=poly_event_slug(l['url']) or ''
                phidden+=f'<a data-cxleg="POLY" data-polyslug="{html.escape(slug)}" data-polysub="" data-polykw="{html.escape(l.get("kw",""))}" style="display:none">POLY {c2ml(cc)}</a>'
        else:
            for p in lp:
                if not p.get('polymarket'): okp=False; break
                cc=poly_price(p['polymarket']['url'], p['name'].split()[0])
                if not cc: okp=False; break
                pc.append(cc)
                if p.get('polymarket_us',{}).get('url'): purl=p['polymarket_us']['url']
        if okp and len(pc)==nlegs:
            c=amer_from_cents(pc)
            if c is not None:
                chips.append(('POLY',f'<a class="chip%%BEST%%"{bkstyle("POLY")} href="{html.escape(purl)}" data-book="POLY" data-sb="{html.escape(purl)}" id="rpCxPOLY" data-n="{nlegs}" onclick="return rpRoute(event,this)" target="_blank" rel="noreferrer">%%STAR%%{bkimg("POLY")}POLY {c2ml(c)}</a>{phidden}',int(c2ml(c))))
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
            link=r.get('link') or f'https://www.{BKDOM[short]}'
            pmattr=f' data-pm="{pm}"' if pm else ''
            chips.append((short,f'<a class="chip%%BEST%%"{bkstyle(short)} href="{html.escape(link)}" data-book="{short}" data-sb="{html.escape(link)}"{pmattr} onclick="return rpRoute(event,this)" target="_blank" rel="noreferrer">%%STAR%%{bkimg(short)}{short} {price:+d}</a>',price))
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
    # his 9:10 AM carve-out: in states where combos can't legally be built, asterisk the title + one-line footnote
    parlay_html=(f'<div class="sect" id="rpParlayTitle">Parlay</div><ul class="legs">{legs}</ul><div class="note" id="rpCxLive" style="display:none;margin-top:6px"></div>{pchip}'
                 f'<div class="note" id="rpComboReg" style="display:none">* Due to regulations in your state, combos can\u2019t legally be built out for you and must be done manually.</div>'
                 f'<div class="note" id="rpParlayNote">{html.escape(pl.get("note",""))}</div>')

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
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="RixPicks">
<meta name="theme-color" content="#2f8f7d">
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
h1 .tick{{color:#2f8f7d}}
.status{{color:#6b6b72;font-size:14px;margin-top:6px}}
.intro{{color:#6b6b72;font-size:14px;margin-top:2px}}
.sect{{margin:26px 0 4px;font-size:13px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#6b6b72}}
.pick{{padding:18px 0;border-top:1px solid #e4e2de}}
.pick:first-of-type{{border-top:none}}
.pick-head{{display:flex;align-items:baseline;gap:10px}}
.gamelink{{display:flex;align-items:baseline;gap:10px;flex:1;color:inherit;text-decoration:none;min-width:0}}
.chev{{color:#b9b9c0;font-size:20px;font-weight:600;text-decoration:none;padding:0 2px;line-height:1}}
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
.odds{{color:#2f8f7d;font-weight:600;white-space:nowrap}}
.sub{{color:#6b6b72;font-size:14px;margin:6px 0 12px}}
.chips{{display:flex;flex-wrap:wrap;gap:8px}}
.chip{{display:inline-flex;align-items:center;gap:6px;min-height:36px;padding:6px 12px;border-radius:999px;border:none;color:#1b1b1f;text-decoration:none;font-size:13px;font-weight:600;background:#fff}}
.bklogo{{width:16px;height:16px;border-radius:3px;flex:none}}
.chip.best{{font-weight:800}}
.rec{{font-weight:600;font-size:16px;padding:8px 0 1px}}
.units{{color:#8a8f98;font-size:13px;font-weight:600;margin-right:8px}}
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
h1 .tick,.odds,.rpstate-link{{color:#3aa895}}
.status,.intro,.sect,.num,.sub,.note{{color:#9a9aa3}}
.pick{{border-top-color:#2a2a2e}}
.chip{{background:#1e1e22;color:#ececf1}}
.foot{{color:#6f6f78}}
#rpModal{{background:rgba(0,0,0,.6)}}
#rpModal .box{{background:#1e1e22}}
#rpModal h3{{color:#ececf1}}
#rpModal p{{color:#9a9aa3}}
#rpA2hs{{background:rgba(0,0,0,.6)}}
#rpA2hs .box{{background:#1e1e22}}
#rpA2hs h3{{color:#ececf1}}
#rpA2hs ol{{color:#c8c8d0}}
#rpA2hs .ghost{{background:#2a2a30;color:#9a9aa3}}
#rpA2hs .dots{{color:#555}}
.ls{{color:#3ec9a0}}
#rpState{{background:#141416;color:#ececf1;border-color:#2a2a2e}}
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
<a class="rec" id="rpRec" data-bw="{man['record'].split('-')[0]}" data-bl="{man['record'].split('-')[1]}" href="record.html" style="display:block;text-decoration:none;color:inherit;margin-top:26px">&rsquo;RixPicks Overall Record: {html.escape(man['record'])}</a>
{wl_pct_line(man['record'])}
{f'<div class="yesrec unitspl" id="rpUnits" data-bu="{html.escape(man["units_pl"])}">Units: {html.escape(man["units_pl"])}</div>' if man.get('units_pl') else ''}
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
const RP_MOB=/iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
const RP_STANDALONE=(navigator.standalone===true)||window.matchMedia('(display-mode: standalone)').matches;
function rpOpen(u){{if(RP_STANDALONE){{location.assign(u);}}else{{window.open(u,'_blank','noopener');}}}}
if(RP_STANDALONE){{document.addEventListener('click',function(e){{const a=e.target.closest('a[target="_blank"]');if(a&&!a.onclick&&a.href){{e.preventDefault();location.assign(a.href);}}}},true);}}
function rpGo(a,st){{const b=a.dataset.book;
 if(b==='POLY'){{if(RP_MOB&&a.dataset.app){{location.href=a.dataset.app;}}else{{rpOpen(a.dataset.sb);}}return;}}
 if(b==='FD'||b==='DK'){{const sb=b==='FD'?RP_FD:RP_DK;
  if(sb.includes(st)){{rpOpen(a.dataset.sb);}}
  else if(b==='FD'&&RP_MOB&&a.dataset.pmapp){{location.href=a.dataset.pmapp;}}
  else{{rpOpen(a.dataset.pm);}}}}
 else if(a.dataset.template){{rpOpen(a.dataset.sb.replaceAll('{{state}}',st.toLowerCase()));}}
 else rpOpen(a.dataset.sb);}}
function rpTerm(st){{const sb=RP_FD.includes(st)||RP_DK.includes(st);const T=sb?'Parlay':'Combo *';
 const h=document.getElementById('rpParlayTitle');if(h)h.textContent=T;
 const rg=document.getElementById('rpComboReg');if(rg)rg.style.display=sb?'none':'';
 const nt=document.getElementById('rpParlayNote');if(nt&&!sb)nt.textContent='';}}
function rpFilter(st){{rpTerm(st);let parlayAllHidden=true;
 document.querySelectorAll('a[data-book]').forEach(function(a){{const b=a.dataset.book;
  const inParlay=!!a.closest('#rpParlayChips');
  if(b==='POLY'){{a.style.display='';return;}}
  if(b==='FD'||b==='DK'){{const L2=b==='FD'?RP_FD:RP_DK;if(inParlay){{a.style.display='';}}else if(b==='FD'){{a.style.display=(a.dataset.nopm&&!L2.includes(st))?'none':'';}}else{{a.style.display=(a.dataset.nopm&&!L2.includes(st))?'none':'';}}return;}}
  const L=RP_L[b];if(!L){{return;}}
  if(!L.includes(st)){{a.style.display='none';}}else{{a.style.display='';parlayAllHidden=parlayAllHidden&&!a.closest('#rpParlayChips')?parlayAllHidden:false;}}
 }});
 const pc=document.querySelectorAll('#rpParlayChips a[data-book]');let any=false;
 pc.forEach(function(a){{if(a.style.display!=='none')any=true;}});
 if(window.rpCxStar)rpCxStar();
 }}
function rpRoute(e,a){{e.preventDefault();const st=localStorage.getItem('rp_state');if(!st){{window.__rpChip=a;rpAsk(false);return false;}}rpGo(a,st);return false;}}
function rpSave(){{const st=document.getElementById('rpState').value;if(!st)return;const gps=localStorage.getItem('rp_state_gps');
 if(gps&&st!==gps){{localStorage.setItem('rp_state',st);localStorage.setItem('rp_state_src','preview');}}else{{localStorage.setItem('rp_state',st);localStorage.setItem('rp_state_src',gps?'gps':'manual');}}
 document.getElementById('rpModal').style.display='none';rpLabel();if(window.__rpChip){{rpGo(window.__rpChip,st);}}else{{rpMaybeA2HS();}}}}
function rpExitPreview(){{const gps=localStorage.getItem('rp_state_gps');if(gps){{localStorage.setItem('rp_state',gps);localStorage.setItem('rp_state_src','gps');rpLabel();}}}}
function rpLabel(){{const el=document.getElementById('rpStateLabel');const st=localStorage.getItem('rp_state');if(st)rpFilter(st);if(el&&st){{const src=localStorage.getItem('rp_state_src');
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
 if(mlb.length){{try{{
  const d=await (await fetch('https://statsapi.mlb.com/api/v1/schedule?sportId=1&date='+new Date().toLocaleDateString('en-CA')+'&hydrate=linescore,team')).json();
  const games=(d.dates||[]).flatMap(x=>x.games||[]);
  mlb.forEach(pk=>{{const g=games.find(g=>g.teams.away.team.name===pk.dataset.away&&g.teams.home.team.name===pk.dataset.home);
   if(!g){{rpLsRender(pk,null);return;}}
   const ls=g.linescore||{{}};const st=g.status.detailedState;
   const inn=(st==='In Progress')?((ls.inningState||'')+' '+(ls.currentInningOrdinal||'')).trim():st;
   rpLsRender(pk,{{a:g.teams.away.team.abbreviation||g.teams.away.team.name.split(' ').pop().slice(0,3).toUpperCase(),h:g.teams.home.team.abbreviation||g.teams.home.team.name.split(' ').pop().slice(0,3).toUpperCase(),
    as:(ls.teams&&ls.teams.away&&ls.teams.away.runs)||0,hs:(ls.teams&&ls.teams.home&&ls.teams.home.runs)||0,
    bat:st==='In Progress'?(ls.inningState==='Top'?'a':(ls.inningState==='Bottom'?'h':null)):null,
    st:inn,state:st==='In Progress'?'in':(st==='Final'||st==='Game Over')?'post':'pre'}});}});}}catch(e){{}}}}
 const byLg={{}};picks.filter(x=>x.dataset.espn&&(x.dataset.espn!=='baseball/mlb')).forEach(x=>{{(byLg[x.dataset.espn]=byLg[x.dataset.espn]||[]).push(x);}});
 for(const lg of Object.keys(byLg)){{try{{
  const d=await (await fetch('https://site.api.espn.com/apis/site/v2/sports/'+lg+'/scoreboard')).json();
  byLg[lg].forEach(pk=>{{let found=null;(d.events||[]).forEach(e=>{{const cs=e.competitions[0].competitors;
   const aw=cs.find(c=>c.homeAway==='away'),hm=cs.find(c=>c.homeAway==='home');if(!aw||!hm)return;
   const an=aw.team.displayName,hn=hm.team.displayName;
   if((an===pk.dataset.away||an.includes(pk.dataset.away)||pk.dataset.away.includes(an))&&(hn===pk.dataset.home||hn.includes(pk.dataset.home)||pk.dataset.home.includes(hn)))
    found={{a:aw.team.abbreviation,h:hm.team.abbreviation,as:+aw.score||0,hs:+hm.score||0,st:e.status.type.shortDetail,state:e.status.type.state}};}});
   rpLsRender(pk,found);}});}}catch(e){{}}}}
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
  const sp=pk.querySelector('[data-ls]');if(!sp)return;
  const won=sp.classList.contains('won'),lost=sp.classList.contains('lost');
  if(!won&&!lost)return;
  const stake=parseFloat((pk.querySelector('.units')||{{}}).textContent)||0;
  const ml=parseInt(pk.dataset.codds);if(!stake||!ml)return;
  if(won){{w++;u+=stake*(ml>0?ml/100:100/Math.abs(ml));}}else{{l++;u-=stake;}}
 }});
 rec.innerHTML='&rsquo;RixPicks Overall Record: '+w+'-'+l;
 const pct=document.getElementById('rpWlPct');if(pct&&(w+l)>0)pct.textContent='W/L: '+(100*w/(w+l)).toFixed(1)+'%';
 if(uEl)uEl.textContent='Units: '+(u>=0?'+':'')+u.toFixed(2)+'u';
}}
async function rpLsTickAll(){{await rpLsTick();rpCxLive();rpRecLive();}}
rpLsTickAll();setInterval(rpLsTickAll,30000);
if(!localStorage.getItem('rp_state')){{rpAsk(false);}}else{{rpLabel();}}
const RP_BUILD='{{build_sha}}';
window.addEventListener('pageshow',function(){{try{{
 if(sessionStorage.getItem('rp_reloaded'))return;
 fetch(location.pathname+'?cb='+Date.now(),{{cache:'no-store'}}).then(r=>r.text()).then(t=>{{
  if(t.indexOf(RP_BUILD)<0){{sessionStorage.setItem('rp_reloaded','1');location.replace(location.pathname+'?v='+RP_BUILD);}}
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
 const span=document.querySelector('#rpParlayChips a[data-book="'+bk+'"]');if(!span)return;
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
 let d=1,cnt=0;
 document.querySelectorAll(sel).forEach(function(a){{
  if(a.id==='rpCxKAL'||a.id==='rpCxPOLY')return;
  const m=a.innerHTML.match(re);if(m){{const ml=parseInt(m[1]);d*=ml>0?1+ml/100:1+100/Math.abs(ml);cnt++;}}
 }});
 if(cnt!==n||d<=1)return;
 const ml2=d>=2?Math.round((d-1)*100):-Math.round(100/(d-1));
 chip.innerHTML=chip.innerHTML.replace(/(KAL|POLY) [+-]?\d+/, bk+' '+(ml2>0?'+':'')+ml2);
 rpCxStar();
}}
function rpCxStar(){{try{{
 const wrap=document.getElementById('rpParlayChips');if(!wrap)return;
 let best=null,bestV=-1e9;
 wrap.querySelectorAll('a[data-book]').forEach(function(a){{
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
   let target=null;
   (ev[0].markets||[]).forEach(function(m){{
    if(target)return;
    if(sub){{if(m.slug===sub)target=m;return;}}
    const q=String(m.question||'');if(q.indexOf(':')>=0)return;
    let oo=[];try{{oo=JSON.parse(m.outcomes||'[]');}}catch(e){{return;}}
    for(let k=0;k<oo.length;k++){{if(String(oo[k]).toLowerCase().indexOf(kw)>=0){{target=m;break;}}}}
   }});
   if(!target)return;
   let outs=[],pr=[];try{{outs=JSON.parse(target.outcomes||'[]');pr=JSON.parse(target.outcomePrices||'[]');}}catch(e){{return;}}
   for(let i=0;i<outs.length;i++){{if(kw&&String(outs[i]).toLowerCase().indexOf(kw)>=0&&pr[i]!=null){{
    const c=Math.round(parseFloat(pr[i])*100);
    if(c>0&&c<100){{a.innerHTML=a.innerHTML.replace(/POLY [+-]?\d+/,'POLY '+rpMLF(rpC2ML(c)));rpCxUpd('POLY');
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
  fetch('https://site.api.espn.com/apis/site/v2/sports/'+lg+'/scoreboard').then(r=>r.json()).then(function(j){{
   (j.events||[]).forEach(function(ev){{
    const comp=(ev.competitions||[])[0]||{{}};const o=(comp.odds||[])[0];if(!o)return;
    leagues[lg].forEach(function(d){{
     if(d.dataset.market==='spread')return;
     const atok=(d.dataset.away||'').toLowerCase().split(' ').pop(),htok=(d.dataset.home||'').toLowerCase().split(' ').pop();
     const nm=(ev.name||'').toLowerCase();
     if(nm.indexOf(atok)<0||nm.indexOf(htok)<0)return;
     const ml=d.dataset.side==='away'?(o.awayTeamOdds||{{}}).moneyLine:(o.homeTeamOdds||{{}}).moneyLine;
     if(typeof ml==='number'){{const s=d.querySelector('.odds');if(s)s.textContent=(ml>0?'+':'')+ml;
      const chip=d.querySelector('a[data-book="ESPN"]');
      if(chip){{chip.innerHTML=chip.innerHTML.replace(/([+-]\d+)/,(ml>0?'+':'')+ml);rpCxUpdMl('ESPN');}}}}
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
   const d=parseFloat(m.yes_ask_dollars);if(!(d>0&&d<1))return;
   const c=Math.round(d*100);
   a.innerHTML=a.innerHTML.replace(/KAL [+-]?\d+/,'KAL '+rpMLF(rpC2ML(c)));rpCxUpd('KAL');
   const pk=a.closest('.pick');
   if(pk&&pk.dataset.market==='ml'){{const s=pk.querySelector('.odds');
    if(s&&c>0&&c<100){{const ml=c>=50?-Math.round(c/(100-c)*100):Math.round((100-c)/c*100);
     s.textContent=(ml>0?'+':'')+ml;}}}}
  }}).catch(()=>{{}}); /* graceful fallback: relay/API failure keeps last build price */
 }});
}}catch(e){{}}}}
rpPolyTick();rpEspnTick();rpKalTick();setInterval(function(){{rpPolyTick();rpEspnTick();rpKalTick();}},60000);
// sportsbook prices ride the 15-min Action rebuild (refresh.sh): pull the rebuilt page and swap
// book chip prices + combo price spans in place. KAL/POLY stay on the 60s tick above.
function rpPageRefresh(){{try{{
 fetch(location.pathname+'?r='+Date.now(),{{cache:'no-store'}}).then(r=>r.text()).then(function(t){{
  const doc=new DOMParser().parseFromString(t,'text/html');
  const picks=document.querySelectorAll('.pick');const npicks=doc.querySelectorAll('.pick');
  for(let i=0;i<picks.length;i++){{
   if(!npicks[i])continue;
   picks[i].querySelectorAll('a[data-book]').forEach(function(a){{
    const b=a.dataset.book;if(b==='POLY')return;
    const na=npicks[i].querySelector('a[data-book="'+b+'"]');if(!na)return;
    const m=na.textContent.match(/([+-]\d+)/);if(!m)return;
    a.innerHTML=a.innerHTML.replace(/([+-]\d+)/,m[1]);
   }});
  }}
  const cc=document.getElementById('rpParlayChips');const nc=doc.getElementById('rpParlayChips');
  if(cc&&nc){{cc.querySelectorAll('a[data-book]').forEach(function(s){{
   const b=s.dataset.book;if(b==='KAL'||b==='POLY')return;
   const ns=nc.querySelector('a[data-book="'+b+'"]');
   if(ns){{const m=ns.textContent.match(/([+-]\d+)/);if(m)s.innerHTML=s.innerHTML.replace(/([+-]\d+)/,m[1]);}}
  }});rpCxStar();}}
 }}).catch(()=>{{}});
}}catch(e){{}}}}
setInterval(rpPageRefresh,60000);
</script>
</div></body></html>'''

def _pt_label(iso):
    try:
        import datetime as _dt
        d=_dt.datetime.fromisoformat(iso.replace('Z','+00:00'))-_dt.timedelta(hours=7)
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
        t=' data-template="1"' if tmpl_flag else ''
        return 'data-book="%s" data-sb="%s"%s onclick="return rpRoute(event,this)" href="%s" target="_blank" rel="noreferrer"'%(short,html.escape(url),t,html.escape(url))
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
            web=p.get('polymarket_us',{}).get('url') or p['polymarket']['url'].replace('https://polymarket.com/','https://polymarket.us/')
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
        ma=TEAM_META.get((lg,away)) or {}; mh=TEAM_META.get((lg,home)) or {}
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
            ('__INST__',inst_lbl),('__ESPN__',espn),('__AWAY__',html.escape(away)),('__HOME__',html.escape(home)),
            ('__SIDE__',side),('__MKT__',mkt),('__NAME__',html.escape(p['name'])),('__UNITS__',html.escape(p.get('units',''))),
            ('__ODDS__',html.escape(p['odds'])),('__SUB__',html.escape(p.get('sub',''))),('__WHEN__',html.escape(when)),
            ('__CHIPS__',ch),('__MATCHUP__',matchup),('__TEAMLINKS__',teamlinks),('__ROWS__',''.join(rows_html)),('__KAL__',kal_html),('__POLY__',poly_html),
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
for _fn,_html in build_team_pages(man,_css,build_sha).items():
    open(os.path.join(os.path.dirname(out) or '.',_fn),'w').write(_html)
    print('written:',_fn,len(_html))
for _fn,_html in build_game_pages(man,_css,build_sha).items():
    open(os.path.join(os.path.dirname(out) or '.',_fn),'w').write(_html)
    print('written:',_fn,len(_html))
if not os.environ.get('RP_NOHIST'):
    import datetime as _dt
    _ts=_dt.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    _hp=os.path.join(os.path.dirname(out) or '.','price_history.jsonl')
    with open(_hp,'a') as _hf:
        for _hr in HIST.values():
            _r={'ts':_ts}; _r.update(_hr); _hf.write(json.dumps(_r)+'\n')
    print('history appended:',len(HIST),'games ->',_hp)
print('written:',out,len(page),'design v'+RP_DESIGN,'build',build_sha)
