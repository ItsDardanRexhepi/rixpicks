#!/usr/bin/env python3
"""DAILY CARD PHOTO renderer (preview chain -> 6:45 build): the morning picks card as a
one-screen photo, by construction. Fixed template (standing spec: daily-picks-card, his
09-23/09-26 card): header "Today's 'RixPicks", good-morning + full date, "Yesterday W-L"
(no colon) with per-pick results under it, one digestible paragraph, picks separated by
league, parlay only when the card carries one, "'RixPicks Overall Record: W-L" as the
bottom line. Content centered. Never on the card: Kalshi/Polymarket, dollars, unit math,
side events (ITF/challenger), gate jargon. Zero-pick card: plain state line + one
audience-safe outcome line per evaluated league (from eval_summary card_lines).
Viewport: iPhone logical 393x852pt (1179x2556 @3x capture); page is exactly one screen,
overflow hidden - no scrolling, not a shrunken webpage.
IN : manifest JSON, eval_summary JSON (optional), OUT path."""
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

# full date ("September 28") from date_label ("Monday, Sep 28")
MON={'Sep':'September','Oct':'October','Nov':'November','Dec':'December','Jan':'January','Feb':'February',
     'Mar':'March','Apr':'April','May':'May','Jun':'June','Jul':'July','Aug':'August'}
dl=str(man.get('date_label') or '')
m=re.search(r'(\w+), (\w+) (\d+)', dl)
full_date=f"{MON.get(m.group(2), m.group(2))} {m.group(3)}" if m else dl

picks = man.get('picks') or []
has_picks = bool(picks)
B = []

# 0. header
B.append('<div class="hdr">Today&rsquo;s &rsquo;RixPicks</div>')
# 1. good morning + full date
B.append(f'<div class="gm">Good morning - {esc(full_date)}</div>')
# 2. Yesterday W-L (no colon) + per-pick results
if man.get('yesterday'):
    y=str(man['yesterday'])
    m2=re.match(r'\s*([\d]+-[\d]+)\s*[\u00b7-]?\s*(.*)', y)
    if m2:
        B.append(f'<div class="yes">Yesterday {esc(m2.group(1))}</div>')
        if m2.group(2): B.append(f'<div class="yesdet">{esc(m2.group(2))}</div>')
    else:
        B.append(f'<div class="yes">Yesterday {esc(y)}</div>')
# 3. one digestible paragraph
if has_picks:
    B.append(f'<div class="para">Full run across every league playing - {len(picks)} pick{"s" if len(picks)!=1 else ""} cleared 60%.</div>')
else:
    B.append('<div class="para">Full run across every league playing tomorrow. Nothing reached the 60% bar - the card stays empty rather than forcing one.</div>')
# 4. picks separated by league, or zero-pick league outcomes (audience-safe card_lines only)
if has_picks:
    last_lg=None
    for p in picks:
        lgk=p.get('espn_league','')
        lbl=LG_LABEL.get(lgk) or (lgk.split('/')[-1].upper() if lgk else '')
        if lgk!=last_lg:
            B.append(f'<div class="sect">{esc(lbl)}</div>'); last_lg=lgk
        lab=p.get('label')
        tag=f' <span class="tag">{esc(lab)}</span>' if lab else ''
        B.append(f'<div class="pick">{esc(p.get("name"))}{tag} <span class="meta">{esc(p.get("units"))} &middot; {esc(p.get("odds"))}</span></div>')
        if p.get('sub'): B.append(f'<div class="sub">{esc(p["sub"])}</div>')
else:
    for sec in (es.get('sections') or []):
        cl=sec.get('card_lines')
        if not cl: continue
        lbl=sec.get('label') or LG_LABEL.get(sec.get('espn_league','')) or sec.get('espn_league','?')
        B.append(f'<div class="sect">{esc(lbl)}</div>')
        for ln in cl[:1]: B.append(f'<div class="oline">{esc(ln)}</div>')
# 5. parlay of the day (only when the card carries one)
if man.get('parlay'):
    pr=man['parlay']
    B.append(f'<div class="sect">Parlay of the day</div>')
    B.append(f'<div class="pick">{esc(pr.get("label") or pr.get("name") or "")} <span class="meta">{esc(pr.get("payout") or pr.get("odds") or "")}</span></div>')
# 7. record line above footer (W-L only)
B.append(f'<div class="record">&rsquo;RixPicks Overall Record: {esc(man.get("record"))}</div>')

doc='''<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=393, initial-scale=1">
<style>
html,body{margin:0;padding:0;width:393px;height:852px;overflow:hidden;background:#ffffff;color:#111;
  font-family:-apple-system,'SF Pro Text','Helvetica Neue',Arial,sans-serif;text-align:center}
.wrap{width:393px;height:852px;box-sizing:border-box;padding:26px 22px 12px;position:relative}
.hdr{font-size:24px;font-weight:800;letter-spacing:.02em}
.gm{font-size:14px;color:#3a3a3f;margin-top:6px}
.yes{font-size:13.5px;font-weight:700;margin-top:10px}
.yesdet{font-size:12px;color:#3a3a3f;margin-top:2px}
.para{font-size:12.5px;color:#1c1c1e;margin-top:12px;line-height:1.45}
.sect{font-size:11px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#6b6b72;margin-top:14px}
.pick{font-size:14px;font-weight:600;margin-top:4px}
.pick .meta{font-weight:400;color:#3a3a3f;font-size:12.5px}
.sub{font-size:11.5px;color:#6b6b72;margin-top:1px}
.oline{font-size:12.5px;color:#1c1c1e;margin-top:3px;line-height:1.4}
.tag{display:inline-block;background:#111;color:#fff;border-radius:6px;font-size:9.5px;
  font-weight:800;letter-spacing:.06em;padding:1px 6px;vertical-align:2px}
.record{position:absolute;bottom:10px;left:22px;right:22px;font-size:13px;font-weight:800;
  border-top:1px solid #e4e2de;padding-top:8px}
</style></head><body><div class="wrap">'''+'\n'.join(B)+'</div></body></html>'
open(out,'w').write(doc)
print(f'card photo written: {out} ({len(doc)} bytes, picks={len(picks)}, league_lines={sum(1 for s in (es.get("sections") or []) if s.get("card_lines"))})')
