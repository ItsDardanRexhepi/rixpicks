#!/usr/bin/env python3
"""Build yesterday.html + record.html from history.json (RP_DESIGN v1.2.0 language).
Runs at morning build + nightly grading; the 15-min odds Action does not touch these.
Doctrine (user, Sep 25 9:54 AM): 'the app and system holding itself accountable in every
aspect possible' - losses named plainly, lessons specific, no hindsight inflation.
Nothing here reads the wall clock: these pages are rebuilt only on record writes, so a page
baked against 'today' goes stale at the PT date flip. record.html lists EVERY graded day (the
live Today section hides the static block for the date it paints), and yesterday.html carries
the latest graded days and picks the one for the viewer's PT yesterday at view time."""
import glob,json,os,sys,html,re
from collections import Counter
from datetime import datetime as _DT  # parses card times only: nothing here reads the wall clock
from zoneinfo import ZoneInfo

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

def page(title, subtitle, body, live=False, slug=''):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{html.escape(title)} - 'RixPicks</title>
<meta property="og:type" content="website"><meta property="og:url" content="https://rix-picks.com/{slug}"><meta property="og:title" content="{html.escape(title)} - 'RixPicks"><meta property="og:description" content="Free picks, live tracked, every league in one place. Built in public - the record is never edited."><meta property="og:image" content="https://rix-picks.com/og-card.png"><meta name="twitter:card" content="summary_large_image">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<style>{CSS}</style></head><body><div class="wrap">
<h1><a href="index.html"><span class="tick">&rsquo;</span>RixPicks</a></h1>
<div class="status">{html.escape(subtitle)}</div>
<a class="back" href="index.html">&larr; Back to today&rsquo;s picks</a>
{body}{(chr(10) + TODAY_CSS + chr(10) + LIVE_JS + chr(10) + TODAY_JS) if live else ''}
<div class="foot">Bet responsibly.</div>
</div></body></html>"""


# Live canonical record hydration (his order 9/26): record.html overall header hydrates from
# same-origin manifest.json (ledger-verified served record; the worker mirror is stale - 9/27). 404/failure keeps baked values - fail closed.
TODAY_JS = '<script defer src="scripts/record_today.js"></script>'
TODAY_CSS = '<style>#rpToday .res.P,#rpToday .res.pending{background:#8a8f98}#rpToday .nt{overflow-wrap:anywhere}</style>'
LIVE_JS = """<script>(function(){function up(j){if(!j)return;var m=/^([0-9]+)-([0-9]+)/.exec(j.record||'');if(!m)return;var el=document.getElementById('rpOverall');if(el)el.textContent=m[1]+'-'+m[2];var u=document.getElementById('rpOverallU');if(u&&j.units_pl){var v=parseFloat(String(j.units_pl).replace('u',''));if(!isNaN(v))u.textContent=(v>=0?'+':'')+v.toFixed(2)+'u';}}function go(){fetch('manifest.json?cb='+Date.now()).then(function(r){return r.ok?r.json():null;}).then(up).catch(function(){});}go();setInterval(go,60000);})();</script>"""


# Note coherence (swarm 8): a forward-looking 'pending' sentence DIES at assembly once the
# referenced team has a graded result anywhere in the data - never hand-maintained.
def _resolved_tokens(days):
    toks=set()
    for d in days:
        for p in d['picks']:
            if p.get('result') in ('W','L','P'):
                for src in (p.get('name',''),p.get('game',''),p.get('score','')):
                    for t in re.findall(r"[A-Za-z]{3,}",src):
                        toks.add(t.lower())
    return toks

_PENDING_RE=re.compile(r"[^.!?]*\bpending\b[^.!?]*[.!?]")
def _coherent_note(note,resolved):
    if not note or 'pending' not in note.lower(): return note
    def drop(m):
        toks={t.lower() for t in re.findall(r"[A-Za-z]{3,}",m.group(0))}
        return '' if toks & resolved else m.group(0)
    return re.sub(r"\s{2,}"," ",_PENDING_RE.sub(drop,note)).strip()

def clv_html(p):
    if p.get('close') is None or p.get('clv') is None: return ''
    clv=p['clv']
    sign='+' if clv>0 else ''
    col='#2f8f7d' if clv>0 else ('#c0392b' if clv<0 else '#8a8f98')
    verdict='beat the close' if clv>0.05 else ('gave back vs the close' if clv<-0.05 else 'matched the close')
    return f'<div class="clv" style="font-size:12px;color:#8a8f98;margin-top:4px">close {p["close"]:+d} &middot; CLV <b style="color:{col}">{sign}{clv}%</b> - {verdict}</div>'

def pick_html(p):
    cls = p['result']
    return f"""<div class="pk">
<div class="pk-top"><span class="res {cls}">{cls}</span><span class="nm">{html.escape(p['name'])}</span><span class="un">{html.escape(p.get('units',''))}</span><span class="od">{html.escape(p.get('odds',''))}</span></div>
<div class="gm">{html.escape(p.get('game',''))}</div>
<div class="sc">{html.escape(p.get('score',''))}</div>
{f'<div class="nt">{html.escape(p["note"])}</div>' if p.get('note') else ''}
{clv_html(p)}
</div>"""

# An unfiled day-close brief is said plainly - never an empty box, never an invented lesson.
NO_BRIEF = 'No brief filed for this day.'

def day_html(d, with_brief_title, hidden=False):
    rows = ''.join(pick_html(p) for p in d['picks'])
    brief = d.get('brief') or ''
    attrs = ' '.join(f'data-{k}="{html.escape(str(d.get(k, "")))}"' for k in ('date', 'label', 'record'))
    return f"""<div class="rpday" {attrs}{' hidden' if hidden else ''}><div class="dayhead"><span class="d">{html.escape(d['label'])}</span><span class="r">{html.escape(d['record'])}</span><span class="u">{html.escape(d['units'])}</span></div>
{rows}
<div class="brief"><span class="bt">{html.escape(with_brief_title)}</span>{html.escape(brief) if brief.strip() else NO_BRIEF}</div></div>"""

# Card dates that carried official picks and have no graded row (r3 review: once the next card
# replaced manifest.json, an ungraded yesterday read '0-0 - no official picks'). The builder's rule
# (build_gh_page_v2._card_date_of, record_final.card_date_of): a card's date is the most common PT
# date across its picks' commence; a card with no readable commence counts under its own ISO date.
# Every manifests/ snapshot counts, and so does the live manifest.json; a card with no picks, or a
# preview, is no official card. build_gh_page_v2._yesterday_pending bakes the same set into the
# Home line on every build.
def card_date(m):
    if not isinstance(m, dict) or m.get('preview') is True:
        return None
    ps = [p for p in (m.get('picks') or []) if isinstance(p, dict)]
    if not ps:
        return None
    ds = []
    for p in ps:
        try:
            t = _DT.fromisoformat(str((p.get('game') or {}).get('commence') or '').replace('Z', '+00:00'))
        except ValueError:
            continue
        if t.tzinfo is not None:
            ds.append(t.astimezone(ZoneInfo('America/Los_Angeles')).date().isoformat())
    if ds:
        return Counter(ds).most_common(1)[0][0]
    md = str(m.get('date') or '')
    return md if re.fullmatch(r'\d{4}-\d{2}-\d{2}', md) else None

def pending_dates(base, days):
    carded = set()
    for f in sorted(glob.glob(os.path.join(base, 'manifests', 'manifest-*.json'))) + [os.path.join(base, 'manifest.json')]:
        try:
            c = card_date(json.load(open(f)))
        except Exception:
            continue
        if c:
            carded.add(c)
    return sorted(carded - {str(d.get('date')) for d in days if d.get('picks')})

# yesterday.html at VIEW time (K18 rule, same as the Home line): show the row for the viewer's
# PT yesterday. With no row: results pending when that date carried official picks - it is in the
# card dates baked into this page (#rpYdNone data-pending), or in the ones the Home page carries
# (index.html, rebuilt by every build, so it knows a card published after this page was built),
# or the live manifest.json is that date's card by the builder's rule (cd below); otherwise that day
# had no official picks, said only once the Home page's dates were read. Nothing readable makes no
# claim either way. The last graded day shows under its own name. Without JS the page reads 'Last
# graded day', true at any hour.
YESTERDAY_JS = """<script>(function(){var bs=[].slice.call(document.querySelectorAll('.rpday[data-date]'));if(!bs.length)return;
var F=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Los_Angeles',year:'numeric',month:'2-digit',day:'2-digit'});var t=F.format(new Date());
var y=new Date(t+'T12:00:00Z');y.setUTCDate(y.getUTCDate()-1);y=y.toISOString().slice(0,10);
var hit=null,last=null;bs.forEach(function(b){var d=b.getAttribute('data-date');if(d===y)hit=b;if(!last&&d<t)last=b;});
var show=hit||last;bs.forEach(function(b){b.hidden=b!==show;});
var st=document.querySelector('.status'),nt=document.getElementById('rpYdNone');
if(hit){if(st)st.textContent='Yesterday - '+hit.getAttribute('data-label');document.title='Yesterday: '+hit.getAttribute('data-record')+" - 'RixPicks";return;}
if(st)st.textContent=show?'Last graded day - '+show.getAttribute('data-label'):'No graded day before today';
if(!nt)return;var lab='Yesterday, '+new Intl.DateTimeFormat('en-US',{timeZone:'UTC',weekday:'long',month:'short',day:'numeric'}).format(new Date(y+'T12:00:00Z'))+': ';
var say=function(s){nt.textContent=lab+s;nt.hidden=false;};
if((nt.getAttribute('data-pending')||'').split(' ').indexOf(y)>=0){say('results pending.');return;}
var cd=function(m){if(!m||m.preview===true||!Array.isArray(m.picks)||!m.picks.length)return '';var c={},o=[],b='',n=0;
m.picks.forEach(function(p){var s=String((p&&p.game&&p.game.commence)||''),x=/(Z|[+-][0-9]{2}:?[0-9]{2})$/i.test(s)?Date.parse(s):NaN;if(isNaN(x))return;
var d=F.format(new Date(x));if(!(d in c)){c[d]=0;o.push(d);}c[d]++;});o.forEach(function(d){if(c[d]>n){n=c[d];b=d;}});
return b||(/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(String(m.date||''))?String(m.date):'');};
var g=function(u,k){return fetch(u+'?cb='+Date.now(),{cache:'no-store'}).then(function(r){return r.ok?r[k]():null;}).catch(function(){return null;});};
try{Promise.all([g('manifest.json','json'),g('index.html','text')]).then(function(r){var m=r[0],ix=r[1],hp=null;
var a=typeof ix==='string'&&ix.match(/<a class="yesrec home-yes"[^>]*>/),q=a&&a[0].match(/data-pending="([^"]*)"/);if(q)hp=q[1].split(' ');
if((hp&&hp.indexOf(y)>=0)||(m&&cd(m)===y)){say('results pending.');return;}
if(hp)say('0-0 - no official picks.');}).catch(function(){});}catch(e){}})();</script>"""

def main(hist_path):
    h = json.load(open(hist_path))
    days = h['days']
    _res=_resolved_tokens(days)
    for _d in days:
        for _p in _d['picks']:
            _p['note']=_coherent_note(_p.get('note'),_res)
    # yesterday.html: the last two graded days, newest shown, and the card dates still waiting for
    # grades; the view-time script picks the viewer's PT yesterday (or states its results are
    # pending, or that it had no official picks) - see YESTERDAY_JS
    yd = days[-1]
    pend = pending_dates(os.path.dirname(os.path.abspath(hist_path)), days)
    ybody = f'<div class="nt" id="rpYdNone" data-pending="{html.escape(" ".join(pend))}" hidden></div>' + ''.join(
        day_html(d, 'What the system learned', hidden=i > 0) for i, d in enumerate(reversed(days[-2:]))) + YESTERDAY_JS
    open('yesterday.html','w').write(page(
        f"Last graded day: {yd['record']}", f"Last graded day - {yd['label']}", ybody, slug='yesterday.html'))
    # record.html = all days, newest first
    tot_w = sum(int(d['record'].split('-')[0]) for d in days)
    tot_l = sum(int(d['record'].split('-')[1]) for d in days)
    clvs=[p['clv'] for d in days for p in d['picks'] if p.get('clv') is not None]
    clv_line=''
    if clvs:
        avg=sum(clvs)/len(clvs)
        pos=sum(1 for c in clvs if c>0)
        col='#2f8f7d' if avg>0 else '#c0392b'
        clv_line=f'<div style="font-size:13px;color:#6b6b72;margin-top:4px">CLV vs close: <b style="color:{col}">{avg:+.1f}%</b> avg &middot; beat the close on {pos}/{len(clvs)} graded picks</div>'
    body = '<section id="rpToday" aria-live="polite"></section>' + f'<div class="dayhead"><span class="d">Overall</span><span class="r" id="rpOverall">{tot_w}-{tot_l}</span><span class="u" id="rpOverallU"></span></div>{clv_line}'
    # every graded day, newest first: the static blocks always add up to the Overall line
    body += ''.join(day_html(d, 'What the system learned') for d in reversed(days))
    open('record.html','w').write(page(
        f"Overall Record: {tot_w}-{tot_l}", "Overall record - day by day", body, live=True, slug='record.html'))
    print('wrote yesterday.html + record.html')

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'history.json')
