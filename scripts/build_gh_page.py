#!/usr/bin/env python3
"""Generate a self-contained index.html ('RixPicks picks page) for GitHub Pages from a manifest JSON.
Usage: build_gh_page.py manifest.json [outfile]
Manifest: {date_label, status_note, record, updated, picks:[{num,name,sub,odds,best_book,side,game:{away,home}|null,espn_league}], parlay:{legs:[...],note}|null}
DESIGN LOCKED (user, Sep 24 10:50 PM): this template IS the app design system. Daily builds change picks
content only - never layout, chip styling, terminology logic. Bump RP_DESIGN only on an approved design change.
Chips resolved from /tmp/odds_prefill.json (+ _sp) when present; NO chips render without a game-level link.
Branding: 'RixPicks only. No personal identifiers, ever.
"""
import json,sys,html

RP_DESIGN='1.1.0'  # locked design system version - bump only on user-approved design change. v1.1.0 (user, Sep 25 12:35 AM): match visitor system appearance - light (default, unchanged) + dark via prefers-color-scheme.

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
pre={}
try:
    for g in json.load(open('/tmp/odds_prefill.json')):
        pre[(g['away'],g['home'])]=g.get('books',{})
except Exception: pass
pre_sp={}
try:
    for g in json.load(open('/tmp/odds_prefill_sp.json')):
        pre_sp[(g['away'],g['home'])]={'books':g.get('books',{})}
except Exception: pass

def chips(p):
    out=[]
    side=p.get('side','away')
    kw=p['name'].split()[0]
    for name,short in BOOKS:
        link=None; ml=None
        pr=pre.get((p['game']['away'],p['game']['home'])) if p.get('game') else None
        if p.get('market')=='spread':
            pr=(pre_sp.get((p['game']['away'],p['game']['home'])) or {}).get('books') if p.get('game') else None
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
                st_=((pre_sp.get((p['game']['away'],p['game']['home'])) or {}).get('books') or {}).get('state_templates',{}) if p.get('game') else {}
                e=(st_.get('betmgm' if name=='BetMGM' else 'betrivers') or {}).get(side) or {}
                if e.get('link'): link=e['link']
                if e.get('price') is not None: ml=e['price']
            else:
                stt=((pre.get((p['game']['away'],p['game']['home'])) or {}).get('state_templates',{})) if p.get('game') else {}
                e=stt.get('betmgm' if name=='BetMGM' else 'betrivers') or {}
                if name=='BetMGM' and e.get(f"{side}_link"):
                    link=e[f"{side}_link"]; ml=e.get(f"{side}_ml")
                if name=='BetRivers' and e.get('event'):
                    link=e['event']; ml=e.get(f"{side}_ml")
        if name=='Kalshi' and p.get('kalshi'):
            link=p['kalshi']['url']; label=f"KAL {p['kalshi']['cents']}\u00a2"
            if p.get('best_book')=='Kalshi': label='\u2605 '+label
            tick=p['kalshi']['url'].rstrip('/').split('/')[-1].upper()
            best=(p.get('best_book')=='Kalshi')
            side=html.escape(p.get('kalshi',{}).get('team',''))
            out.append(f'<a class="chip{" best" if best else ""}"{bkstyle(short)} href="{html.escape(link)}" data-kalticker="{tick}" data-kalside="{side}" target="_blank" rel="noreferrer">{bkimg(short)}{label}</a>')
            continue
        if name=='Polymarket':
            if not p.get('polymarket'): continue
            web=p.get('polymarket_us',{}).get('url') or p['polymarket']['url'].replace('https://polymarket.com/','https://polymarket.us/'); app=web
            slug=poly_event_slug(p['polymarket']['url']) or ''
            sub=poly_sub(p['polymarket']['url']) or ''
            cents=poly_price(p['polymarket']['url'],kw)
            label=f"POLY {cents}\u00a2" if cents else "POLY"
            if p.get('best_book')=='Polymarket': label='\u2605 '+label
            best=(p.get('best_book')=='Polymarket')
            out.append(f'<a class="chip{" best" if best else ""}"{bkstyle("POLY")} href="{html.escape(web)}" data-book="POLY" data-sb="{html.escape(web)}" data-app="{html.escape(app)}" data-polyslug="{html.escape(slug)}" data-polysub="{html.escape(sub)}" data-polykw="{html.escape(kw)}" onclick="return rpRoute(event,this)" target="_blank" rel="noreferrer">{bkimg("POLY")}{label}</a>')
            continue
        if not link: continue  # no game-level link -> drop chip
        best=(p.get('best_book')==name)
        label=f"{short} {ml:+d}" if ml is not None else short
        if best: label='\u2605 '+label
        if name in ('FanDuel','DraftKings'):
            pm='https://www.fanduel.com/predicts' if name=='FanDuel' else (p.get('dkp',{}).get('url') or 'https://predictions.draftkings.com/')
            pmapp='https://predicts.fanduel.com/' if name=='FanDuel' else ''
            nopm=' data-nopm="1"' if (name=='DraftKings' and not p.get('dkp',{}).get('url')) else ''
            out.append(f'<a class="chip{" best" if best else ""}"{bkstyle(short)} href="{html.escape(link)}" data-book="{short}" data-sb="{html.escape(link)}" data-pm="{html.escape(pm)}" data-pmapp="{html.escape(pmapp)}"{nopm} onclick="return rpRoute(event,this)" target="_blank" rel="noreferrer">{bkimg(short)}{html.escape(label)}</a>')
        elif '{state}' in link:
            out.append(f'<a class="chip{" best" if best else ""}"{bkstyle(short)} href="{html.escape(link)}" data-book="{short}" data-sb="{html.escape(link)}" data-template="1" onclick="return rpRoute(event,this)" target="_blank" rel="noreferrer">{bkimg(short)}{html.escape(label)}</a>')
        else:
            out.append(f'<a class="chip{" best" if best else ""}"{bkstyle(short)} href="{html.escape(link)}" data-book="{short}" data-sb="{html.escape(link)}" onclick="return rpRoute(event,this)" target="_blank" rel="noreferrer">{bkimg(short)}{html.escape(label)}</a>')
    return ''.join(out)

rows=[]
for p in man['picks']:
    ch=chips(p)
    chips_html=f'<div class="chips">{ch}</div>' if ch else ''
    espn=html.escape(p.get('espn_league',''))
    mkt='spread' if p.get('market')=='spread' else 'ml'
    g=p.get('game') or {}
    rows.append(f'''<div class="pick" data-espn="{espn}" data-away="{html.escape(g.get('away',''))}" data-home="{html.escape(g.get('home',''))}" data-side="{p.get('side','away')}" data-market="{mkt}">
  <div class="pick-head"><span class="num">{p['num']}.</span><span class="name">{html.escape(p['name'])}</span><span class="units">{html.escape(p.get('units',''))}</span><span class="odds">{html.escape(p['odds'])}</span></div>
  <div class="sub">{html.escape(p['sub'])}</div>
  {chips_html}
</div>''')

parlay_html=''
if man.get('parlay'):
    pl=man['parlay']
    legs=''.join(f'<li>{html.escape(l)}</li>' for l in pl['legs'])
    pchip=''
    if pl.get('book_links'):
        c=[]
        for bk,(lab,url) in pl['book_links'].items():
            c.append(f'<a class="chip"{bkstyle(bk)} href="{html.escape(url)}" data-book="{bk}" data-sb="{html.escape(url)}" onclick="return rpRoute(event,this)" target="_blank" rel="noreferrer">{bkimg(bk)}{html.escape(lab)}</a>')
        pchip=f'<div class="chips" id="rpParlayChips" style="margin:10px 0">{"".join(c)}</div><div class="note" id="rpParlayNa" style="display:none">Parlay links are sportsbook-only tonight &mdash; no parlay chip in your state. Singles above work on Kalshi &amp; Polymarket everywhere.</div>'
    elif pl.get('link'):
        pchip=f'<div class="chips" style="margin:10px 0"><a class="chip best" href="{html.escape(pl["link"])}" target="_blank" rel="noreferrer">{html.escape(pl.get("label","BUILD THIS PARLAY"))}</a></div>'
    parlay_html=f'<div class="sect" id="rpParlayTitle">Parlay</div><ul class="legs">{legs}</ul>{pchip}<div class="note" id="rpParlayNote">{html.escape(pl.get("note",""))}</div>'

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
.num{{color:#6b6b72}}
.name{{font-weight:600;font-size:17px;flex:1}}
.odds{{color:#2f8f7d;font-weight:600;white-space:nowrap}}
.sub{{color:#6b6b72;font-size:14px;margin:6px 0 12px}}
.chips{{display:flex;flex-wrap:wrap;gap:8px}}
.chip{{display:inline-flex;align-items:center;gap:6px;min-height:36px;padding:6px 12px;border-radius:999px;border:none;color:#1b1b1f;text-decoration:none;font-size:13px;font-weight:600;background:#fff}}
.bklogo{{width:16px;height:16px;border-radius:3px;flex:none}}
.chip.best{{font-weight:800}}
.rec{{font-weight:600;font-size:16px;padding:8px 0}}
.units{{color:#8a8f98;font-size:13px;font-weight:600;margin-right:8px}}
.unitmath{{color:#8a8f98;font-size:13px;margin-top:2px}}
.legs{{padding-left:20px;font-size:15px;line-height:1.7}}
.note{{color:#6b6b72;font-size:13px;margin-top:6px}}
.foot{{margin-top:34px;color:#8a8a91;font-size:12px;line-height:1.6}}
#rpModal{{display:none;position:fixed;inset:0;background:rgba(20,20,25,.55);align-items:center;justify-content:center;z-index:50}}
#rpModal .box{{background:#fff;border-radius:14px;padding:22px 20px;max-width:340px;width:88%}}
#rpModal h3{{font-size:16px;margin-bottom:6px}}
#rpModal p{{font-size:13px;color:#6b6b72;margin-bottom:12px}}
#rpState{{width:100%;padding:10px;border:1px solid #e4e2de;border-radius:8px;font-size:15px;margin-bottom:12px}}
#rpSave{{width:100%;padding:11px;border:none;border-radius:8px;background:#2f8f7d;color:#fff;font-size:15px;font-weight:600;cursor:pointer}}
.rpstate-link{{color:#2f8f7d;cursor:pointer;text-decoration:underline}}
#rpPull{{position:fixed;top:0;left:0;right:0;height:56px;display:flex;align-items:center;justify-content:center;background:#f7f6f4;color:#2f8f7d;font-size:13px;font-weight:600;transform:translateY(-100%);z-index:60;pointer-events:none}}
.spin{{width:14px;height:14px;border:2px solid #cde3dd;border-top-color:#2f8f7d;border-radius:50%;animation:rpSpin .8s linear infinite;margin-right:8px;display:inline-block}}
@keyframes rpSpin{{to{{transform:rotate(360deg)}}}}
@media (prefers-color-scheme: dark){{
body{{background:#141416;color:#ececf1}}
h1 .tick,.odds,.rpstate-link{{color:#3aa895}}
.status,.intro,.sect,.num,.sub,.note{{color:#9a9aa3}}
.pick{{border-top-color:#2a2a2e}}
.chip{{background:#1e1e22;color:#ececf1}}
.foot{{color:#6f6f78}}
#rpModal{{background:rgba(0,0,0,.6)}}
#rpModal .box{{background:#1e1e22}}
#rpModal h3{{color:#ececf1}}
#rpModal p{{color:#9a9aa3}}
#rpState{{background:#141416;color:#ececf1;border-color:#2a2a2e}}
#rpGeoNote{{color:#3aa895 !important}}
#rpPull{{background:#141416;color:#3aa895}}
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
</style></head><body>
<div id="rpPull"></div>
<div class="wrap">
<h1><span class="tick">&rsquo;</span>RixPicks</h1>
<div class="status">{html.escape(man['date_label'])} &middot; {html.escape(man['status_note'])}</div>
<div class="intro">Tap any book under a pick to open that game there. Best line is highlighted.</div>
<div class="sect">Today&rsquo;s picks</div>
{chr(10).join(rows)}
{parlay_html}
<div class="sect">Record</div>
<div class="rec">&rsquo;RixPicks Overall Record: {html.escape(man['record'])}</div>
<div class="unitmath">1u = $5 per $1,000 in bankroll</div>
<div class="foot">Lines checked {html.escape(man['updated'])}. POLY prices and headline odds update live on this page; book lines refresh at each build. KAL chips open the exact market (works everywhere). FD/DK chips open the sportsbook where it&rsquo;s live in your state, or prediction markets elsewhere. Nothing is placed from this page &mdash; picks are informational, bets are yours to make. Bet responsibly. <span class="rpstate-link" id="rpStateLabel" onclick="rpEdit()">Set your state</span></div>
<div id="rpModal"><div class="box">
<h3>One quick thing</h3>
<p>Pick your state once so taps open the right product &mdash; sportsbook where it&rsquo;s live, prediction markets everywhere else. Saved on this device.</p>
<div id="rpGeoNote" style="font-size:12px;color:#2f8f7d;margin-bottom:10px"></div>
<select id="rpState"><option value="">Choose state&hellip;</option>{''.join(f'<option value="{c}">{n}</option>' for c,n in RP_STATES)}</select>
<button id="rpSave" onclick="rpSave()">Save &amp; continue</button>
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
function rpTerm(st){{const sb=RP_FD.includes(st)||RP_DK.includes(st);const T=sb?'Parlay':'Combo';
 const h=document.getElementById('rpParlayTitle');if(h)h.textContent=T;
 const na=document.getElementById('rpParlayNa');if(na)na.innerHTML=sb?'Parlay links are sportsbook-only tonight &mdash; no parlay chip in your state. Singles above work on Kalshi &amp; Polymarket everywhere.':'Combo links are sportsbook-only tonight &mdash; no combo chip in your state. Kalshi lists the games: build the combo in the Kalshi app. Singles above work on Kalshi &amp; Polymarket everywhere.';
 const nt=document.getElementById('rpParlayNote');if(nt&&!sb)nt.textContent='';}}
function rpFilter(st){{rpTerm(st);let parlayAllHidden=true;
 document.querySelectorAll('a[data-book]').forEach(function(a){{const b=a.dataset.book;
  const inParlay=!!a.closest('#rpParlayChips');
  if(b==='POLY'){{a.style.display='';return;}}
  if(b==='FD'||b==='DK'){{const L2=b==='FD'?RP_FD:RP_DK;if(inParlay){{a.style.display=L2.includes(st)?'':'none';}}else if(b==='FD'){{a.style.display=(a.dataset.nopm&&!L2.includes(st))?'none':'';}}else{{a.style.display=(a.dataset.nopm&&!L2.includes(st))?'none':'';}}return;}}
  const L=RP_L[b];if(!L){{return;}}
  if(!L.includes(st)){{a.style.display='none';}}else{{a.style.display='';parlayAllHidden=parlayAllHidden&&!a.closest('#rpParlayChips')?parlayAllHidden:false;}}
 }});
 const pc=document.querySelectorAll('#rpParlayChips a[data-book]');let any=false;
 pc.forEach(function(a){{if(a.style.display!=='none')any=true;}});
 const na=document.getElementById('rpParlayNa');if(na)na.style.display=(pc.length&&!any)?'':'none';}}
function rpRoute(e,a){{e.preventDefault();const st=localStorage.getItem('rp_state');if(!st){{window.__rpChip=a;rpAsk(false);return false;}}rpGo(a,st);return false;}}
function rpSave(){{const st=document.getElementById('rpState').value;if(!st)return;const gps=localStorage.getItem('rp_state_gps');
 if(gps&&st!==gps){{localStorage.setItem('rp_state',st);localStorage.setItem('rp_state_src','preview');}}else{{localStorage.setItem('rp_state',st);localStorage.setItem('rp_state_src',gps?'gps':'manual');}}
 document.getElementById('rpModal').style.display='none';rpLabel();if(window.__rpChip){{rpGo(window.__rpChip,st);}}}}
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
    if(window.__rpChip)rpGo(window.__rpChip,code);
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
    if(c>0&&c<100){{a.innerHTML=a.innerHTML.replace(/POLY[^<]*/,'POLY '+c+'\u00a2');}}
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
     if(typeof ml==='number'){{const s=d.querySelector('.odds');if(s)s.textContent=(ml>0?'+':'')+ml;}}
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
   a.innerHTML=a.innerHTML.replace(/KAL[^<]*/,'KAL '+c+'\u00a2');
  }}).catch(()=>{{}}); /* graceful fallback: relay/API failure keeps last build price */
 }});
}}catch(e){{}}}}
rpPolyTick();rpEspnTick();rpKalTick();setInterval(function(){{rpPolyTick();rpEspnTick();rpKalTick();}},60000);
</script>
</div></body></html>'''
import os
import time
build_sha=str(int(time.time()))
page=page.replace('{build_sha}',build_sha)
os.makedirs(os.path.dirname(out),exist_ok=True)
open(out,'w').write(page)
print('written:',out,len(page),'design v'+RP_DESIGN,'build',build_sha)
