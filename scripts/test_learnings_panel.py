#!/usr/bin/env python3
"""What the system is learning (Home, owner directive Oct 2: the site shows what the system is
learning, in real time, as picks grade). The builder bakes a Home-only section from history.json -
the latest graded day's brief, then the newest graded picks' notes, newest day first, at most 6 -
and index_v2.js repaints the same box from the live history.json by the same rules.

Runs the builder's real _learnings_html from source (both twins) on fixture ledgers in a temp dir
(no network, no repo writes) and checks:
- heading and Home-only classes; the section sits right before News in the Home shell;
- newest day first (stored order does not matter), day labels, at most 6 picks;
- only graded picks (W/L/P) that carry a note; the brief is the latest graded day's only;
- a hostile note is escaped text, never markup; the added-after-kickoff tag on that pick alone;
- no dollar sign anywhere (a text carrying one is left out whole);
- no comment-shaped run that scrub_shipped could eat (the section survives it unchanged);
- nothing at all (no heading, no box) on a missing, unreadable, wrong-shaped or empty ledger.
Then runs index_v2.js's real rpLearnHtml under node on the same fixtures and checks it renders the
same markup as the builder (entity spelling aside), and renders the live history.json read-only.
Run: python3 scripts/test_learnings_panel.py"""
import json, os, re, subprocess, sys, tempfile

SD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SD)
failures = 0
def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or not detail else '  [%s]' % (detail,)))
    if not ok: failures += 1

HEAD = '<div class="sect home-only" id="rpLearnHead" style="margin-top:18px">What the system is learning</div>\n'
BOX = '<div class="card learn home-only" id="rpLearn" aria-live="polite">'
HOSTILE = '<img src=x onerror=alert(1)>'

def pick(name, result, note=None, units='5u', **kw):
    p = {'name': name, 'game': 'vs Somebody', 'odds': '-110', 'units': units, 'result': result, 'score': 'A 1, B 0'}
    if note is not None:
        p['note'] = note
    p.update(kw)
    return p

# stored oldest first like history.json, with one day out of place to prove the newest-first sort
FIX = {'days': [
    {'date': '2026-09-20', 'label': 'Sunday, Sep 20', 'record': '2-0', 'units': '+2.00u', 'brief': 'Old brief, never shown.',
     'picks': [pick('Old One ML', 'W', 'old note one'), pick('Old Two ML', 'W', 'old note two')]},
    {'date': '2026-09-22', 'label': 'Tuesday, Sep 22', 'record': '3-1', 'units': '+1.00u', 'brief': 'Mid brief, never shown.',
     'picks': [pick('Mid B ML', 'L', HOSTILE),
               pick('Mid C ML', 'P', 'Push - stake back.', units='6u'),
               pick('Mid A ML', 'W', 'seventh note, past the cap'),
               pick('Mid D ML', 'W', 'eighth note, past the cap')]},
    {'date': '2026-09-24', 'label': 'Thursday, Sep 24', 'record': '2-1', 'units': '+3.10u',
     'brief': 'Gibbs\' 3rd TD & the "close" read held.',
     'picks': [pick('New A ML', 'W', 'Won +1.85u on 5u at -270.'),
               pick('New B ML', 'L', 'Risked $40 to win $15.'),
               pick('New C ML', 'W'),
               pick('Late Add ML', 'L', 'Carded after first pitch; lost.', added_after_kickoff=True),
               pick('Open ML', None, 'ungraded, never shown'),
               pick('Pend ML', 'pending', 'pending, never shown'),
               pick('Truthy Tag ML', 'W', 'string flag is no tag', added_after_kickoff='true')]},
    {'date': '2026-09-23', 'label': 'Wednesday, Sep 23', 'record': '1-0', 'units': '+1.00u', 'brief': '',
     'picks': [pick('Out Of Place ML', 'W', 'Read held // user order /* main */ <!-- his --> fine.')]},
    {'date': '2026-09-25', 'label': 'Friday, Sep 25', 'record': '0-0', 'units': '0.00u', 'brief': 'Ungraded day brief, never shown.',
     'picks': [pick('Tomorrow ML', None, 'not graded yet')]},
]}
WANT_NAMES = ['New A ML', 'Late Add ML', 'Truthy Tag ML', 'Out Of Place ML', 'Mid B ML', 'Mid C ML']
# one day, eight graded noted picks, a brief carrying a dollar sign
FIX_MANY = {'days': [{'date': '2026-10-01', 'label': 'Thursday, Oct 1', 'record': '8-0', 'units': '+8.00u',
                      'brief': 'Up $120 on the day.', 'picks': [pick('P%d ML' % i, 'W', 'note %d' % i) for i in range(1, 9)]}]}
# shaped like the ledger today: the newest graded days carry no notes and no brief
FIX_QUIET = {'days': [{'date': '2026-10-01', 'label': 'Thursday, Oct 1', 'record': '1-0', 'units': '+1.00u', 'brief': '',
                       'picks': [pick('Quiet ML', 'W')]}]}

def names(out):
    return re.findall(r'<span class="lnname">([^<]*)</span>', out)
def item_of(out, name):
    return next((c for c in out.split('<div class="lnitem">')[1:] if '>' + name + '<' in c), '')

def scrub_fn(src):
    ns = {}
    exec(src[src.index('import re as _re_scrub'):src.index('def _urf(')], ns)
    return ns['scrub_shipped']

tmp = tempfile.TemporaryDirectory(prefix='rp-learn-')
T = tmp.name
def put(name, data, raw=False):
    p = os.path.join(T, name)
    with open(p, 'w') as f:
        f.write(data if raw else json.dumps(data))
    return p

P_FIX, P_MANY, P_QUIET = put('fix.json', FIX), put('many.json', FIX_MANY), put('quiet.json', FIX_QUIET)
EMPTY_CASES = [('missing file', os.path.join(T, 'nope.json')), ('unreadable JSON', put('bad.json', '{"days": [', raw=True)),
               ('a JSON list', put('list.json', [])), ('days not a list', put('str.json', {'days': 'x'})),
               ('no days', put('none.json', {'days': []})),
               ('no graded pick', put('ungraded.json', {'days': [{'date': '2026-10-02', 'label': 'Friday, Oct 2', 'brief': 'Brief of an ungraded day.',
                                                                   'picks': [pick('Live ML', None, 'in progress')]}]})),
               ('graded picks, no notes, no brief', P_QUIET)]

outs = {}
for B in ('build_gh_page_v2.py', '_build_nocanon_v2.py'):
    src = open(os.path.join(SD, B)).read()
    i, j = src.find('def _learnings_html('), src.find('_learn_html = _learnings_html(')
    check(f'{B}: _learnings_html and its call are present', 0 <= i < j)
    if not 0 <= i < j:
        continue
    ns = {'os': os}
    exec(src[i:j], ns)
    learn = ns['_learnings_html']
    check(f'{B}: the call reads history.json beside the manifest',
          "_learn_html = _learnings_html(os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])), 'history.json'))" in src)
    check(f'{B}: the section sits right before News in the Home shell',
          "+fut_entry+'\\n'+_learn_html+'<div class=\"sect home-only\" style=\"margin-top:18px\">News</div>" in src)

    out = learn(P_FIX)
    outs[B] = out
    check(f'{B}: heading present, Home-only', out.startswith(HEAD), out[:120])
    check(f'{B}: box is a Home-only card with the live mount id', (BOX in out) and out.endswith('</div>\n'))
    check(f'{B}: newest day first, at most 6 picks, only graded picks with a note', names(out) == WANT_NAMES, names(out))
    days_seen = re.findall(r'<div class="lnday">([^<]*)</div>', out)
    check(f'{B}: day labels newest first, days with nothing to show left out',
          days_seen == ['Thursday, Sep 24', 'Wednesday, Sep 23', 'Tuesday, Sep 22'], days_seen)
    check(f'{B}: exactly 6 pick rows', out.count('<div class="lnitem">') == 6, out.count('<div class="lnitem">'))
    check(f'{B}: the latest graded day\'s brief only (escaped)',
          out.count('<div class="lnbrief">') == 1 and '<div class="lnbrief">Gibbs&#x27; 3rd TD &amp; the &quot;close&quot; read held.</div>' in out
          and 'never shown' not in out, re.findall(r'<div class="lnbrief">[^<]*', out))
    check(f'{B}: the brief sits under its own day label',
          '<div class="lnday">Thursday, Sep 24</div><div class="lnbrief">' in out)
    check(f'{B}: hostile note is escaped text, never markup',
          '<img' not in out and 'onerror=alert(1)' in out and '&lt;img src=x onerror=alert(1)&gt;' in out)
    check(f'{B}: no raw markup from ledger text anywhere',
          not re.search(r'<(?!/?(div|span)\b)', out), re.findall(r'<(?!/?(?:div|span)\b)[^>]{0,20}', out))
    check(f'{B}: added-after-kickoff tag on that pick alone',
          out.count('added after kickoff') == 1 and '<span class="lntag">added after kickoff</span>' in item_of(out, 'Late Add ML')
          and 'lntag' not in item_of(out, 'Truthy Tag ML'))
    check(f'{B}: result and units as displayed',
          '<span class="lnres L">L</span><span class="lnname">Mid B ML</span><span class="lnunits">5u</span>' in out
          and '<span class="lnres P">P</span><span class="lnname">Mid C ML</span><span class="lnunits">6u</span>' in out
          and '<span class="lnres W">W</span><span class="lnname">New A ML</span><span class="lnunits">5u</span>' in out)
    check(f'{B}: no dollar sign rendered (a text carrying one is left out whole)',
          '$' not in out and 'New B ML' not in out and 'Risked' not in out)
    check(f'{B}: no game, odds or score fields leak into the panel', 'vs Somebody' not in out and 'A 1, B 0' not in out and '-110' not in out)
    check(f'{B}: no comment-shaped run for scrub_shipped to eat', not re.search(r'//|/\*|\*/|<!--', out))
    check(f'{B}: the section survives scrub_shipped unchanged', scrub_fn(src)(out) == out)
    check(f'{B}: the slashes still read as text (entity-encoded)', 'Read held &#47;&#47; user order &#47;* main *&#47; &lt;!-- his --&gt; fine.' in out)

    many = learn(P_MANY)
    check(f'{B}: one day with 8 noted picks shows the first 6', names(many) == ['P%d ML' % k for k in range(1, 7)], names(many))
    check(f'{B}: a brief carrying a dollar sign is left out whole', '<div class="lnbrief">' not in many and '$' not in many)
    for why, path in EMPTY_CASES:
        r = learn(path)
        check(f'{B}: {why} renders nothing (no heading, no empty box)', r == '', r[:80])

check('both twins render the fixture identically', len(set(outs.values())) == 1 and len(outs) == 2)

# ---- client parity: index_v2.js's real rpLearnHtml under node, same fixtures ----
HARNESS = r'''
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync(process.argv[2], 'utf8');
function extract(name) {
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) return '';
  let depth = 0;
  for (let i = start; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) return src.slice(start, i + 1); }
  }
  return '';
}
const ctx = vm.createContext({});
vm.runInContext(extract('esc') + '\n' + extract('rpLearnHtml'), ctx);
const res = {};
for (const p of process.argv.slice(3)) {
  let data; try { data = JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { res[p] = 'UNREADABLE'; continue; }
  res[p] = ctx.rpLearnHtml(data);
}
process.stdout.write(JSON.stringify(res));
'''
hp = put('harness.js', HARNESS, raw=True)
LIVE = os.path.join(ROOT, 'history.json')
paths = [P_FIX, P_MANY, P_QUIET] + [p for _, p in EMPTY_CASES if os.path.exists(p)] + ([LIVE] if os.path.exists(LIVE) else [])
r = subprocess.run(['node', hp, os.path.join(SD, 'index_v2.js')] + paths, capture_output=True, text=True)
check('node runs index_v2.js rpLearnHtml', r.returncode == 0, r.stderr[-400:])
client = json.loads(r.stdout) if r.returncode == 0 and r.stdout else {}

def inner(server):
    # the box contents, in the client's entity spelling (a browser reads both the same)
    if not server:
        return ''
    return server[len(HEAD) + len(BOX):-len('</div>\n')].replace('&#x27;', "'").replace('&#47;', '/')

src0 = open(os.path.join(SD, 'build_gh_page_v2.py')).read()
ns0 = {'os': os}
exec(src0[src0.find('def _learnings_html('):src0.find('_learn_html = _learnings_html(')], ns0)
for label, p in [('fixture', P_FIX), ('8-pick day', P_MANY), ('quiet ledger', P_QUIET)]:
    check(f'client renders the {label} exactly as the builder', client.get(p) == inner(ns0['_learnings_html'](p)),
          (client.get(p) or '')[:160])
check('client: hostile note never markup', '<img' not in (client.get(P_FIX) or 'x<img'))
check('client: no dollar sign', '$' not in (client.get(P_FIX) or '$') and '$' not in (client.get(P_MANY) or '$'))
check('client: a wrong-shaped file is not a ledger (keeps the page as it is)',
      client.get(os.path.join(T, 'list.json')) is None and client.get(os.path.join(T, 'str.json')) is None)
check('client: a readable ledger with nothing to show renders empty (section hides)',
      client.get(os.path.join(T, 'none.json')) == '' and client.get(os.path.join(T, 'ungraded.json')) == '' and client.get(P_QUIET) == '')

# ---- the live ledger, read-only: whatever it holds, the panel stays inside the rules ----
if os.path.exists(LIVE):
    live = ns0['_learnings_html'](LIVE)
    check('live history.json: at most 6 picks', live.count('<div class="lnitem">') <= 6)
    check('live history.json: no dollar sign, no raw ledger markup', '$' not in live and not re.search(r'<(?!/?(div|span)\b)', live))
    check('live history.json: client and builder agree', client.get(LIVE) == inner(live), (client.get(LIVE) or '')[:160])

tmp.cleanup()
print('ALL OK' if not failures else '%d FAIL' % failures)
sys.exit(1 if failures else 0)
