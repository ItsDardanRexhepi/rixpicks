#!/usr/bin/env python3
"""CARD PHOTO renderer (preview chain -> 6:45 build): the one-screen daily card photo,
by construction. NOT a shrunken webpage - its own compact fixed-viewport layout.

Viewport: iPhone logical 393x852pt (captures 1179x2556 @3x). The page is exactly one
screen, overflow hidden - no scrolling possible. Density rules (standing rule: the daily
card photo fits one phone screen):
  header (wordmark, date, record/units) + yesterday: fixed compact block
  picks (when the card has picks): one line per pick, prioritized - league outcome
    sections compress to one line each
  zero-pick card: state line + up to two outcome lines per league
  footer: source + updated stamp
IN : manifest JSON (build_manifest output), eval_summary JSON (optional, zero-pick sections)
OUT: fixed-size HTML file (path arg 3)."""
import json, sys, html

def esc(s): return html.escape(str(s or ''))

man = json.load(open(sys.argv[1]))
es = {}
if len(sys.argv) > 2 and sys.argv[2] != '-':
    try: es = json.load(open(sys.argv[2]))
    except Exception as e: print(f'LOUD: eval summary unreadable ({e}) - photo renders without outcome sections', file=sys.stderr)
out = sys.argv[3] if len(sys.argv) > 3 else '/tmp/card_photo.html'

LG_LABEL={'baseball/mlb':'MLB','football/nfl':'NFL','basketball/nba':'NBA','hockey/nhl':'NHL',
          'basketball/wnba':'WNBA','football/college-football':'CFB','basketball/college-basketball':'CBB',
          'tennis':'Tennis','tennis/atp':'ATP','tennis/wta':'WTA','soccer/usa.1':'MLS','soccer/usa.nwsl':'NWSL',
          'golf/pga':'PGA','racing/nascar':'NASCAR','mma/ufc':'UFC','boxing':'Boxing'}

picks = man.get('picks') or []
has_picks = bool(picks)
body = []

# header
body.append(f'<div class="hdr"><span class="wm">RIXPICKS</span><span class="rec">{esc(man.get("record"))} &middot; {esc(man.get("units_pl"))}</span></div>')
body.append(f'<div class="date">{esc(man.get("date_label"))}</div>')
if man.get('yesterday'):
    body.append(f'<div class="yes">Yesterday: {esc(man["yesterday"])}</div>')

# picks or zero-pick state
if has_picks:
    last_lg = None
    for p in picks:
        g = p.get('game') or {}
        lgk = p.get('espn_league','')
        lbl = LG_LABEL.get(lgk) or (lgk.split('/')[-1].upper() if lgk else '')
        if lgk != last_lg:
            body.append(f'<div class="sect">{esc(lbl)}</div>')
            last_lg = lgk
        body.append(f'<div class="pick"><b>{p.get("num")}. {esc(p.get("name"))}</b>'
                    f'<span class="meta">{esc(p.get("units"))} &middot; {esc(p.get("odds"))}</span></div>'
                    f'<div class="sub">{esc(p.get("sub"))}</div>')
else:
    body.append(f'<div class="state">No card picks for {esc(man.get("date_label") or "today")}</div>')
    body.append('<div class="statesub">Zero picks cleared the card gates. Every league evaluated:</div>')

# league outcome sections (eval summary): 2 lines zero-pick, 1 line with picks
cap = 1 if has_picks else 2
for sec in (es.get('sections') or []):
    lbl = sec.get('label') or LG_LABEL.get(sec.get('espn_league','')) or sec.get('espn_league','?')
    lines = (sec.get('compact') or sec.get('lines') or [])[:cap]
    if not lines: continue
    body.append(f'<div class="sect">{esc(lbl)}</div>')
    for ln in lines:
        body.append(f'<div class="oline">{esc(ln)}</div>')

body.append(f'<div class="ftr">rix-picks.com &middot; {esc(man.get("updated"))}</div>')

html_doc = '''<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=393, initial-scale=1">
<style>
html,body{margin:0;padding:0;width:393px;height:852px;overflow:hidden;background:#fff;color:#111;
  font-family:-apple-system,'SF Pro Text','Helvetica Neue',Arial,sans-serif}
.wrap{width:393px;height:852px;box-sizing:border-box;padding:14px 16px 10px;display:block;position:relative}
.hdr{display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid #111;padding-bottom:5px}
.wm{font-weight:800;font-size:19px;letter-spacing:.08em}
.rec{font-size:13px;font-weight:700}
.date{font-size:15px;font-weight:700;margin-top:6px}
.yes{font-size:11.5px;color:#3a3a3f;margin-top:2px}
.state{font-size:14px;font-weight:700;margin-top:10px}
.statesub{font-size:11.5px;color:#6b6b72;margin-top:1px}
.sect{font-size:10.5px;font-weight:800;letter-spacing:.09em;text-transform:uppercase;color:#6b6b72;margin-top:9px}
.pick{font-size:13px;margin-top:3px}
.pick .meta{color:#3a3a3f;font-size:12px;margin-left:6px}
.sub{font-size:11px;color:#6b6b72;margin-top:1px}
.oline{font-size:11.5px;color:#1c1c1e;margin-top:2px;line-height:1.35}
.ftr{position:absolute;bottom:8px;left:16px;right:16px;font-size:10px;color:#9a9aa3;
  border-top:1px solid #e4e2de;padding-top:4px}
@media (prefers-color-scheme:dark){
 html,body{background:#0f0f10;color:#f2f2f4}
 .hdr{border-bottom-color:#f2f2f4}
 .yes,.sub,.statesub{color:#9a9aa3}
 .oline{color:#e8e8ea}
 .ftr{border-top-color:#2a2a2e}
}
</style></head><body><div class="wrap">''' + '\n'.join(body) + '</div></body></html>'
open(out,'w').write(html_doc)
print(f'card photo written: {out} ({len(html_doc)} bytes, picks={len(picks)}, sections={len(es.get("sections") or [])})')
