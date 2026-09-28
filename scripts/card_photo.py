#!/usr/bin/env python3
"""DAILY CARD PHOTO renderer (preview chain -> 6:45 build): the morning picks card as a
one-screen photo, by construction. FIXED VISUAL TEMPLATE (his 09-27 reference image,
sent 09-27 8:21 PM via main - the standing template for every daily card):
  cream page (#ece8e1), white rounded card centered, serif display header
  "Today's 'RixPicks", green abbrev date line ("Mon Sep 28"), yesterday block with left
  green border (bold "Yesterday W-L" + muted per-pick line; "sweep" suffix on sweeps),
  league labels small gray caps, numbered picks (bold name left, teal "odds . units"
  right, gray reasoning subtext incl. "model XX.X vs Kalshi XXc ask" when priced),
  parlay pill (only when the card carries one), footer "'RixPicks Overall Record:
  W-L . pct%" bold + muted "Odds checked ..." line. Zero-pick card: same shell, league
  sections carry one honest muted outcome line, no parlay pill.
Viewport: iPhone logical 393x852pt (1179x2556 @3x capture); exactly one screen,
overflow hidden. IN: manifest JSON, eval_summary JSON (optional), OUT path."""
import json, sys, html, re

def esc(s): return html.escape(str(s or ''))

man = json.load(open(sys.argv[1]))
es = {}
if len(sys.argv) > 2 and sys.argv[2] != '-':
    try: es = json.load(open(sys.argv[2]))
    except Exception as e: print(f'LOUD: eval summary unreadable ({e}) - photo renders without league lines', file=sys.stderr)
out = sys.argv[3] if len(sys.argv) > 3 else '/tmp/card_photo.html'

LG_LABEL={'baseball/mlb':'MLB','football/nfl':'NFL','basketball/nba':'NBA','hockey/nhl':'NHL',
          'basketball/wnba':'WNBA','football/college-football':'CFB','basketball/college-basketball':'CBB',
          'tennis':'Tennis','tennis/atp':'ATP','tennis/wta':'WTA','soccer/usa.1':'MLS','soccer/usa.nwsl':'NWSL',
          'golf/pga':'PGA','racing/nascar':'NASCAR','mma/ufc':'UFC','boxing':'Boxing'}

# green abbrev date line: "Mon Sep 28" from date_label "Monday, Sep 28"
WK={'Monday':'Mon','Tuesday':'Tue','Wednesday':'Wed','Thursday':'Thu','Friday':'Fri','Saturday':'Sat','Sunday':'Sun'}
dl=str(man.get('date_label') or '')
m=re.match(r'(\w+), (.+)', dl)
green_date=f"{WK.get(m.group(1), m.group(1))} {m.group(2)}" if m else dl

picks = man.get('picks') or []
has_picks = bool(picks)
B = []

B.append('<div class="hdr">Today&rsquo;s &rsquo;RixPicks</div>')
B.append(f'<div class="gm">{esc(green_date)}</div>')

if man.get('yesterday'):
    y=str(man['yesterday'])
    m2=re.match(r'\s*([\d]+)-([\d]+)\s*[\u00b7]?\s*(.*)', y)
    if m2:
        wl=f"{m2.group(1)}\u2013{m2.group(2)}"
        sweep = ' \u00b7 sweep' if m2.group(2)=='0' and m2.group(1)!='0' else ''
        B.append(f'<div class="yesblk"><div class="yes">Yesterday {esc(wl)}{sweep}</div>')
        if m2.group(3): B.append(f'<div class="yesdet">{esc(m2.group(3))}</div>')
        B.append('</div>')
    else:
        B.append(f'<div class="yesblk"><div class="yes">Yesterday {esc(y)}</div></div>')

def pick_sub(p):
    sub=str(p.get('sub') or '')
    mod=p.get('model'); kal=(p.get('kalshi') or {})
    cents=kal.get('cents')
    if mod is not None and cents is not None:
        mv=f"{float(mod):.1f}" if isinstance(mod,(int,float)) else str(mod)
        tail=f"model {mv} vs Kalshi {int(round(float(cents)))}c ask"
        sub=(sub+' \u00b7 '+tail) if sub else tail
    return sub

if has_picks:
    last_lg=None
    for p in picks:
        lgk=p.get('espn_league','')
        lbl=LG_LABEL.get(lgk) or (lgk.split('/')[-1].upper() if lgk else '')
        if lgk!=last_lg:
            B.append(f'<div class="sect">{esc(lbl)}</div>'); last_lg=lgk
        B.append(f'<div class="prow"><span class="pnum">{esc(p.get("num"))}.</span>'
                 f'<span class="pname">{esc(p.get("name"))}</span>'
                 f'<span class="podds">{esc(p.get("odds"))} \u00b7 {esc(p.get("units"))}</span></div>')
        s=pick_sub(p)
        if s: B.append(f'<div class="psub">{esc(s)}</div>')
else:
    for sec in (es.get('sections') or []):
        cl=sec.get('card_lines')
        if not cl: continue
        lbl=sec.get('label') or LG_LABEL.get(sec.get('espn_league','')) or sec.get('espn_league','?')
        B.append(f'<div class="sect">{esc(lbl)}</div>')
        B.append(f'<div class="psub">{esc(cl[0])}</div>')

if man.get('parlay'):
    pr=man['parlay']
    legs=pr.get('label') or pr.get('name') or ''
    comb=pr.get('payout') or pr.get('odds') or ''
    B.append(f'<div class="pill"><span class="pill-l">PARLAY OF THE DAY</span>'
             f'<span class="pill-m">{esc(legs)}</span><span class="pill-r">{esc(comb)}</span></div>')

rec=str(man.get('record') or '').replace('-','\u2013')
pct=str(man.get('pct') or man.get('win_pct') or '')
if not pct:
    _mr=re.match(r'\s*(\d+)\s*-\s*(\d+)', str(man.get('record') or ''))
    if _mr and (int(_mr.group(1))+int(_mr.group(2)))>0:
        pct=f"{100.0*int(_mr.group(1))/(int(_mr.group(1))+int(_mr.group(2))):.1f}%"
rec_line=f"'RixPicks Overall Record: {rec}" + (f" \u00b7 {pct}" if pct else '')
upd=str(man.get('updated') or '')
B.append(f'<div class="ftr"><div class="frec">{esc(rec_line)}</div>'
         f'<div class="fmut">Odds checked {esc(upd)} \u00b7 Conviction-selected, edge floor first - floorless only when the floor yields zero</div></div>')

doc='''<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=393, initial-scale=1">
<style>
html,body{margin:0;padding:0;width:393px;height:852px;overflow:hidden;background:#ece8e1;
  font-family:-apple-system,'SF Pro Text','Helvetica Neue',Arial,sans-serif;color:#111}
.card{box-sizing:border-box;width:353px;height:812px;margin:20px;background:#fff;border-radius:20px;
  padding:26px 24px 14px;position:relative;overflow:hidden}
.hdr{font-family:Georgia,'Times New Roman',serif;font-size:34px;font-weight:400;letter-spacing:.01em;color:#111}
.gm{font-size:14px;font-weight:600;color:#4a9d7f;margin-top:8px}
.yesblk{border-left:3px solid #4a9d7f;padding-left:10px;margin-top:18px}
.yes{font-size:15px;font-weight:700}
.yesdet{font-size:12.5px;color:#8a8f98;margin-top:3px}
.sect{font-size:11px;font-weight:600;letter-spacing:.14em;color:#9a9aa3;margin-top:20px}
.prow{display:flex;align-items:baseline;margin-top:10px}
.pnum{color:#9a9aa3;font-size:14px;width:24px;flex-shrink:0}
.pname{font-size:15.5px;font-weight:700;flex:1}
.podds{font-size:14px;font-weight:600;color:#2f9e8f;white-space:nowrap}
.psub{font-size:12px;color:#8a8f98;margin:3px 0 0 24px;line-height:1.4}
.pill{display:flex;align-items:center;justify-content:space-between;background:#f1ede6;
  border-radius:12px;padding:12px 14px;margin-top:24px}
.pill-l{font-size:10px;font-weight:700;letter-spacing:.1em;color:#9a9aa3}
.pill-m{font-size:14px;font-weight:700}
.pill-r{font-size:15px;font-weight:700;color:#2f9e8f}
.ftr{position:absolute;bottom:14px;left:24px;right:24px}
.frec{font-size:15px;font-weight:800}
.fmut{font-size:11.5px;color:#9a9aa3;margin-top:4px;line-height:1.4}
</style></head><body><div class="card">'''+'\n'.join(B)+'</div></body></html>'
open(out,'w').write(doc)
print(f'card photo written: {out} ({len(doc)} bytes, picks={len(picks)}, league_lines={sum(1 for s in (es.get("sections") or []) if s.get("card_lines"))})')
