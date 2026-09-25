#!/usr/bin/env python3
"""Build yesterday.html + record.html from history.json (RP_DESIGN v1.2.0 language).
Runs at morning build + nightly grading; the 15-min odds Action does not touch these.
Doctrine (user, Sep 25 9:54 AM): 'the app and system holding itself accountable in every
aspect possible' - losses named plainly, lessons specific, no hindsight inflation."""
import json,sys,html

CSS = """
*{margin:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background:#f7f6f4;color:#1b1b1f;min-height:100vh}
.wrap{max-width:680px;margin:0 auto;padding:28px 18px 60px}
h1{font-size:26px;font-weight:800;letter-spacing:-0.01em}
h1 .tick{color:#2f8f7d}
h1 a{color:inherit;text-decoration:none}
.status{color:#6b6b72;font-size:14px;margin-top:6px}
.back{display:inline-block;margin-top:10px;color:#2f8f7d;font-size:14px;text-decoration:none}
.dayhead{display:flex;align-items:baseline;gap:10px;margin:26px 0 4px}
.dayhead .d{font-size:13px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#6b6b72;flex:1}
.dayhead .r{font-weight:700;font-size:14px}
.dayhead .u{font-size:13px;color:#6b6b72;font-weight:600}
.pk{padding:16px 0;border-top:1px solid #e4e2de}
.pk-top{display:flex;align-items:baseline;gap:10px}
.res{flex:none;font-weight:800;font-size:13px;width:20px;height:20px;border-radius:6px;display:inline-flex;align-items:center;justify-content:center;color:#fff}
.res.W{background:#2f8f7d}
.res.L{background:#c0392b}
.nm{font-weight:600;font-size:16px;flex:1}
.od{color:#2f8f7d;font-weight:600;white-space:nowrap}
.un{color:#8a8f98;font-size:13px;font-weight:600}
.gm{color:#6b6b72;font-size:13px;margin-top:3px}
.sc{font-size:14px;font-weight:600;margin-top:6px}
.nt{color:#6b6b72;font-size:14px;margin-top:5px;line-height:1.5}
.brief{margin:14px 0 6px;padding:14px 16px;background:#fff;border-left:3px solid #2f8f7d;border-radius:0 10px 10px 0;font-size:14px;line-height:1.55;color:#3a3a40}
.brief .bt{font-size:11px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:#2f8f7d;display:block;margin-bottom:6px}
.foot{margin-top:34px;color:#8a8a91;font-size:12px;line-height:1.6}
@media (prefers-color-scheme: dark){
body{background:#000;color:#ececf1}
h1 .tick,.od,.back{color:#3aa895}
.status,.dayhead .d,.gm,.nt{color:#9a9aa3}
.pk{border-top-color:#2a2a2e}
.brief{background:#141416;color:#c9c9d1}
.foot{color:#6f6f78}
}
"""

def page(title, subtitle, body):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{html.escape(title)} - 'RixPicks</title>
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<style>{CSS}</style></head><body><div class="wrap">
<h1><a href="index.html"><span class="tick">&rsquo;</span>RixPicks</a></h1>
<div class="status">{html.escape(subtitle)}</div>
<a class="back" href="index.html">&larr; Back to today&rsquo;s picks</a>
{body}
<div class="foot">Bet responsibly.</div>
</div></body></html>"""

def pick_html(p):
    cls = p['result']
    return f"""<div class="pk">
<div class="pk-top"><span class="res {cls}">{cls}</span><span class="nm">{html.escape(p['name'])}</span><span class="un">{html.escape(p.get('units',''))}</span><span class="od">{html.escape(p.get('odds',''))}</span></div>
<div class="gm">{html.escape(p.get('game',''))}</div>
<div class="sc">{html.escape(p.get('score',''))}</div>
{f'<div class="nt">{html.escape(p["note"])}</div>' if p.get('note') else ''}
</div>"""

def day_html(d, with_brief_title):
    rows = ''.join(pick_html(p) for p in d['picks'])
    return f"""<div class="dayhead"><span class="d">{html.escape(d['label'])}</span><span class="r">{html.escape(d['record'])}</span><span class="u">{html.escape(d['units'])}</span></div>
{rows}
<div class="brief"><span class="bt">{html.escape(with_brief_title)}</span>{html.escape(d['brief'])}</div>"""

def main(hist_path):
    h = json.load(open(hist_path))
    days = h['days']
    # yesterday.html = most recent graded day
    yd = days[-1]
    open('yesterday.html','w').write(page(
        f"Yesterday: {yd['record']}", f"Yesterday - {yd['label']}",
        day_html(yd, 'What the system learned')))
    # record.html = all days, newest first
    tot_w = sum(int(d['record'].split('-')[0]) for d in days)
    tot_l = sum(int(d['record'].split('-')[1]) for d in days)
    body = f'<div class="dayhead"><span class="d">Overall</span><span class="r">{tot_w}-{tot_l}</span><span class="u"></span></div>'
    body += ''.join(day_html(d, 'What the system learned') for d in reversed(days))
    open('record.html','w').write(page(
        f"Overall Record: {tot_w}-{tot_l}", "Overall record - day by day", body))
    print('wrote yesterday.html + record.html')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'history.json')
