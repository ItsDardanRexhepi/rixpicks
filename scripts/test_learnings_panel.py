#!/usr/bin/env python3
"""What the system is learning (Home, owner directive Oct 2: the site shows what the system is
learning, in real time, as picks grade). The builder bakes a Home-only section from history.json and
index_v2.js repaints the same box from the live history.json by the same rules: day groups newest day
first, at most 3; under each day label that day's own brief, then its graded picks' lessons
newest-graded first (reverse ledger order), at most 6 picks in all.

Runs the builder's real _learnings_html from source (both twins) on fixture ledgers in a temp dir
(no network, no repo writes) and checks:
- heading and Home-only classes; the section sits right before News in the Home shell;
- newest day first (stored order does not matter); within a day the newest-graded pick first;
- at most 6 picks and at most 3 day groups; once 6 picks are shown no further day is opened;
- each group shows its own day's brief; a graded day with a brief and no pick text shows its brief;
  a day with no graded pick is never a group;
- a pick's lesson is its note, else its learning (the record_final chain's field: chain-shaped rows
  carry learning and no note); a left-out note renders as if absent, so the learning stands;
- a hostile note is escaped text, never markup; the added-after-kickoff tag on that pick alone;
- money left out whole: '$', fullwidth U+FF04, small U+FE69, the words dollar(s) / USD (any case,
  ASCII word boundaries in both renderers), in a brief, a note or a learning; look-alikes kept;
- a text holding a lone surrogate (not writable as UTF-8) is left out as if absent;
- both renderers trim the same whitespace set (a whitespace-only note is blank);
- no comment-shaped run that scrub_shipped could eat (the section survives it unchanged);
- nothing at all (no heading, no box) on a missing, unreadable, wrong-shaped or empty ledger.
Then runs index_v2.js's real rpLearnHtml under node on the same fixtures and checks it renders the
same markup as the builder (entity spelling aside), and renders the live history.json read-only.
Last, builds a real page with each twin (throwaway tree, network blocked through a dead proxy) from a
ledger whose notes hold a lone surrogate and 'Game not started': index.html is written, the bad text
is left out, and the health gate's rpStripLearn cuts exactly the section from the built page.
Run: python3 scripts/test_learnings_panel.py"""
import json, os, re, shutil, subprocess, sys, tempfile

SD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SD)
TWINS = ('build_gh_page_v2.py', '_build_nocanon_v2.py')
failures = 0
def check(name, ok, detail=''):
    global failures
    line = ('OK   ' if ok else 'FAIL ') + name + ('' if ok or not detail else '  [%s]' % (detail,))
    print(line.encode('utf-8', 'backslashreplace').decode('utf-8'))  # a lone surrogate in a detail prints, never crashes
    if not ok: failures += 1

HEAD = '<div class="sect home-only" id="rpLearnHead" style="margin-top:18px">What the system is learning</div>\n'
BOX = '<div class="card learn home-only" id="rpLearn" aria-live="polite">'
HOSTILE = '<img src=x onerror=alert(1)>'

def pick(name, result, note=None, units='5u', **kw):
    # learn_brief's shape: the per-pick lesson as `note`
    p = {'name': name, 'game': 'vs Somebody', 'odds': '-110', 'units': units, 'result': result, 'score': 'A 1, B 0'}
    if note is not None:
        p['note'] = note
    p.update(kw)
    return p
def chain_pick(name, result, learning=None, units='5u'):
    # the record_final grading chain's row: no note; the lesson, when filed, as `learning`
    p = {'name': name, 'game': 'vs Somebody', 'odds': '+100', 'units': units, 'result': result, 'score': 'A 1, B 0', '_delta': '-5.0'}
    if learning is not None:
        p['learning'] = learning
    return p

# stored oldest first like history.json, with days out of place to prove the newest-first sort;
# within a day the ledger order is the grading order (the chain appends), so the last row is newest
FIX = {'days': [
    {'date': '2026-09-20', 'label': 'Sunday, Sep 20', 'record': '1-0', 'units': '+1.00u', 'brief': 'Oldest brief, past the day cap.',
     'picks': [pick('Old One ML', 'W', 'old note, past the day cap')]},
    {'date': '2026-09-22', 'label': 'Tuesday, Sep 22', 'record': '1-1', 'units': '-1.00u', 'brief': 'Tuesday brief: graded, no pick text.',
     'picks': [pick('Quiet A ML', 'W'), chain_pick('Quiet B ML', 'L')]},
    {'date': '2026-09-24', 'label': 'Thursday, Sep 24', 'record': '2-3', 'units': '+3.10u',
     'brief': 'Gibbs\' 3rd TD & the "close" read held.',
     'picks': [pick('New A ML', 'W', 'Won +1.85u on 5u at -270.'),
               pick('New B ML', 'L', 'Risked $40 to win $15.'),
               pick('Mid B ML', 'L', HOSTILE),
               pick('New C ML', 'W'),
               pick('Late Add ML', 'L', 'Carded after first pitch; lost.', added_after_kickoff=True),
               pick('Open ML', None, 'ungraded, never shown'),
               pick('Pend ML', 'pending', 'pending, never shown'),
               pick('Push ML', 'P', 'Push - stake back.', units='6u')]},
    {'date': '2026-09-23', 'label': 'Wednesday, Sep 23', 'record': '1-0', 'units': '+1.00u', 'brief': '',
     'picks': [pick('Out Of Place ML', 'W', 'Read held // user order /* main */ <!-- his --> fine.')]},
    {'date': '2026-09-25', 'label': 'Friday, Sep 25', 'record': '0-0', 'units': '0.00u', 'brief': 'Ungraded day brief, never shown.',
     'picks': [pick('Tomorrow ML', None, 'not graded yet')]},
]}
WANT_SEQ = [('day', 'Thursday, Sep 24'), ('brief', 'Gibbs&#x27; 3rd TD &amp; the &quot;close&quot; read held.'),
            ('item', 'Push ML'), ('item', 'Late Add ML'), ('item', 'Mid B ML'), ('item', 'New A ML'),
            ('day', 'Wednesday, Sep 23'), ('item', 'Out Of Place ML'),
            ('day', 'Tuesday, Sep 22'), ('brief', 'Tuesday brief: graded, no pick text.')]
# one day, eight graded noted picks (P8 graded last), a brief carrying a dollar sign
FIX_MANY = {'days': [{'date': '2026-10-01', 'label': 'Thursday, Oct 1', 'record': '8-0', 'units': '+8.00u', 'brief': 'Up $120 on the day.',
                      'picks': [pick('P%d ML' % i, 'W', 'note %d' % i) for i in range(1, 8)]
                               + [pick('P8 ML', 'W', 'string flag is no tag', added_after_kickoff='true')]}]}
# the 6-pick cap reached inside the second day: the third day (brief and all) is never opened
FIX_CAP = {'days': [
    {'date': '2026-10-01', 'label': 'Thursday, Oct 1', 'record': '1-0', 'units': '+1.00u', 'brief': 'Oldest brief, past the pick cap.',
     'picks': [pick('C1 ML', 'W', 'c1, past the pick cap')]},
    {'date': '2026-10-02', 'label': 'Friday, Oct 2', 'record': '4-0', 'units': '+4.00u', 'brief': 'Friday brief.',
     'picks': [pick('B%d ML' % i, 'W', 'b%d' % i) for i in range(1, 5)]},
    {'date': '2026-10-03', 'label': 'Saturday, Oct 3', 'record': '0-4', 'units': '-20.00u', 'brief': 'Saturday brief.',
     'picks': [pick('A%d ML' % i, 'L', 'a%d' % i) for i in range(1, 5)]},
]}
WANT_CAP = [('day', 'Saturday, Oct 3'), ('brief', 'Saturday brief.'), ('item', 'A4 ML'), ('item', 'A3 ML'), ('item', 'A2 ML'), ('item', 'A1 ML'),
            ('day', 'Friday, Oct 2'), ('brief', 'Friday brief.'), ('item', 'B4 ML'), ('item', 'B3 ML')]
# shaped like the live chain's rows (record_final): learning only, no note, no brief
FIX_CHAIN = {'days': [
    {'date': '2026-09-29', 'label': 'Tuesday, Sep 29', 'record': '2-3', 'units': '-7.19u', 'brief': '',
     'picks': [chain_pick('Braves ML', 'W'),
               chain_pick('Yordan Alvarez over 1.5 hits', 'L'),
               chain_pick('Loai Abushaar ML', 'L', 'User-directed pick carded by owner word at disclosed sub-bar'),
               chain_pick('Maple Leafs ML', 'L', 'Carded at even money; the read missed.'),
               chain_pick('Bruins ML', 'W', 'Won +5.0u (NYR 0 @ BOS 3); the read held.')]},
    {'date': '2026-09-30', 'label': 'Wednesday, Sep 30', 'record': '1-0', 'units': '+6.90u', 'brief': '',
     'picks': [chain_pick('White Sox ML', 'W')]},
]}
WANT_CHAIN = [('day', 'Tuesday, Sep 29'), ('item', 'Bruins ML'), ('item', 'Maple Leafs ML'), ('item', 'Loai Abushaar ML')]
# note before learning; a note that is missing, blank, not a string or left out falls back to the learning
FIX_PREF = {'days': [{'date': '2026-09-30', 'label': 'Wednesday, Sep 30', 'record': '5-1', 'units': '+1.00u', 'brief': '',
                      'picks': [pick('Both ML', 'W', 'Note shown over the learning.', learning='learning hidden when a note is shown'),
                                pick('Blank Note ML', 'W', '   ', learning='A blank note falls back to the learning.'),
                                pick('Money Note ML', 'W', 'Cost us $5.', learning='A money note is left out; the learning stands.'),
                                pick('Lone Note ML', 'W', 'bad \ud800 text', learning='An unencodable note is left out; the learning stands.'),
                                pick('Number Note ML', 'W', 42, learning='A non-string note falls back to the learning.'),
                                pick('Money Both ML', 'L', 'Paid 5 USD.', learning='Five dollars down.')]}]}
WANT_PREF = [('Number Note ML', 'A non-string note falls back to the learning.'),
             ('Lone Note ML', 'An unencodable note is left out; the learning stands.'),
             ('Money Note ML', 'A money note is left out; the learning stands.'),
             ('Blank Note ML', 'A blank note falls back to the learning.'),
             ('Both ML', 'Note shown over the learning.')]
# a graded day with a brief and no pick text still shows its brief
FIX_BRIEF = {'days': [{'date': '2026-10-01', 'label': 'Thursday, Oct 1', 'record': '1-0', 'units': '+1.00u', 'brief': 'Only a brief today.',
                       'picks': [pick('Quiet ML', 'W'), chain_pick('Quiet Chain ML', 'W')]}]}
# lone surrogates (json.dumps writes them as \\udXXX escapes, as a corrupted ledger could carry them)
FIX_SURR = {'days': [{'date': '2026-10-02', 'label': 'Friday, Oct 2', 'record': '4-1', 'units': '+1.00u', 'brief': 'Brief with a lone \ud800 surrogate.',
                      'picks': [pick('Lone Low ML', 'W', 'x\udc00y'),
                                pick('Lone High End ML', 'L', 'ends in \ud83d'),
                                pick('Lone Name \udfff ML', 'W', 'the name carries a lone low surrogate'),
                                pick('Pair ML', 'W', 'An emoji pair \U0001F600 is fine.'),
                                pick('Reversed Pair ML', 'W', 'low then high \udc00\ud800 are two lone halves')]}]}
WANT_SURR = [('day', 'Friday, Oct 2'), ('item', 'Pair ML')]
# money, each spelling in a brief, a note and a learning: the text goes, the clean pick stays
MONEY = ['Risked $40 to win $15.', 'Risked 40USD to win 15USD.', 'Down 5dollars on the close.', 'USD40 risked.', 'Risked \uff0440 on it.', 'Risked \ufe6940 on it.', 'Down forty dollars.', 'One dollar back.',
         'Paid 40 USD.', 'paid in usd today', 'DOLLARS and cents.', 'Dollar-for-dollar value.', 'Odds (Usd) moved.',
         'Caf\u00e9dollar sale.']  # the last: word boundaries are ASCII in both renderers (e-acute is no word character)
def money_ledger(v):
    return {'days': [{'date': '2026-10-01', 'label': 'Thursday, Oct 1', 'record': '3-0', 'units': '+3.00u', 'brief': v,
                      'picks': [pick('Note Money ML', 'W', v), chain_pick('Learning Money ML', 'W', v), pick('Clean ML', 'W', 'Clean note.')]}]}
# look-alikes that name no money stay
KEEP = ['Dollarhide read held.', 'USDA-grade read.', 'Petrodollar talk aside, the read held.', 'KUSD radio call held.']
FIX_KEEP = {'days': [{'date': '2026-10-01', 'label': 'Thursday, Oct 1', 'record': '4-0', 'units': '+4.00u', 'brief': '',
                      'picks': [pick('K%d ML' % i, 'W', v) for i, v in enumerate(KEEP, 1)]}]}
# shaped like the ledger on Sep 30 and Oct 1: graded days with no lesson and no brief
FIX_QUIET = {'days': [{'date': '2026-10-01', 'label': 'Thursday, Oct 1', 'record': '1-0', 'units': '+1.00u', 'brief': '',
                       'picks': [pick('Quiet ML', 'W'), chain_pick('Quiet Chain ML', 'W')]}]}

# whitespace both renderers strip alike (str.isspace() plus U+FEFF == JS whitespace plus U+001C-U+001F, U+0085):
# a whitespace-only note is blank (the learning stands), padding is trimmed off a name and a note
FIX_WS = {'days': [{'date': '2026-10-01', 'label': 'Thursday, Oct 1', 'record': '2-0', 'units': '+2.00u', 'brief': '\u2028\x85 \x1c',
                    'picks': [pick('WS Note ML', 'W', '\x85\x1c \ufeff', learning='A whitespace-only note falls back to the learning.'),
                              pick('\ufeffPadded ML\x1f', 'W', '\u3000Padded note.\x85')]}]}
WANT_WS = [('Padded ML', 'Padded note.'), ('WS Note ML', 'A whitespace-only note falls back to the learning.')]

def seq(out):
    s = []
    for m in re.finditer(r'<div class="ln(day|brief)">([^<]*)</div>|<span class="lnname">([^<]*)</span>', out):
        s.append((m.group(1), m.group(2)) if m.group(1) else ('item', m.group(3)))
    return s
def names(out):
    return [v for k, v in seq(out) if k == 'item']
def notes(out):
    return re.findall(r'<span class="lnname">([^<]*)</span>.*?<div class="lnnote">([^<]*)</div>', out)
def item_of(out, name):
    return next((c for c in out.split('<div class="lnitem">')[1:] if '>' + name + '<' in c), '')
MONEY_RE = re.compile(r'[$\uff04\ufe69]|(?<![A-Za-z])(?:dollars?|usd)(?![A-Za-z])', re.I | re.A)

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

P = {k: put(k + '.json', v) for k, v in [('fix', FIX), ('many', FIX_MANY), ('cap', FIX_CAP), ('chain', FIX_CHAIN), ('pref', FIX_PREF),
                                          ('brief', FIX_BRIEF), ('surr', FIX_SURR), ('keep', FIX_KEEP), ('quiet', FIX_QUIET), ('ws', FIX_WS)]}
P_MONEY = [put('money%d.json' % i, money_ledger(v)) for i, v in enumerate(MONEY)]
EMPTY_CASES = [('missing file', os.path.join(T, 'nope.json')), ('unreadable JSON', put('bad.json', '{"days": [', raw=True)),
               ('a JSON list', put('list.json', [])), ('days not a list', put('str.json', {'days': 'x'})),
               ('no days', put('none.json', {'days': []})),
               ('no graded pick', put('ungraded.json', {'days': [{'date': '2026-10-02', 'label': 'Friday, Oct 2', 'brief': 'Brief of an ungraded day.',
                                                                   'picks': [pick('Live ML', None, 'in progress')]}]})),
               ('graded picks, no lessons, no brief', P['quiet'])]

def builder_fn(B):
    src = open(os.path.join(SD, B)).read()
    i, j = src.find('def _learnings_html('), src.find('_learn_html = _learnings_html(')
    if not 0 <= i < j:
        return src, None
    ns = {'os': os}
    exec(src[i:j], ns)
    return src, ns['_learnings_html']

outs = {}
for B in TWINS:
    src, learn = builder_fn(B)
    check(f'{B}: _learnings_html and its call are present', learn is not None)
    if learn is None:
        continue
    check(f'{B}: the call reads history.json beside the manifest',
          "_learn_html = _learnings_html(os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])), 'history.json'))" in src)
    check(f'{B}: the section sits right before News in the Home shell',
          "+fut_entry+'\\n'+_learn_html+'<div class=\"sect home-only\" style=\"margin-top:18px\">News</div>" in src)

    out = learn(P['fix'])
    outs[B] = out
    check(f'{B}: heading present, Home-only', out.startswith(HEAD), out[:120])
    check(f'{B}: box is a Home-only card with the live mount id', (BOX in out) and out.endswith('</div>\n'))
    check(f'{B}: days newest first, each with its own brief, newest-graded pick first, at most 3 days',
          seq(out) == WANT_SEQ, seq(out))
    check(f'{B}: a day with no graded pick is never a group; the 4th day past the cap is left out',
          'never shown' not in out and 'past the day cap' not in out and 'Friday, Sep 25' not in out and 'Sunday, Sep 20' not in out)
    check(f'{B}: the brief sits under its own day label',
          '<div class="lnday">Thursday, Sep 24</div><div class="lnbrief">' in out
          and '<div class="lnday">Tuesday, Sep 22</div><div class="lnbrief">Tuesday brief: graded, no pick text.</div></div>\n' in out)
    check(f'{B}: hostile note is escaped text, never markup',
          '<img' not in out and 'onerror=alert(1)' in out and '&lt;img src=x onerror=alert(1)&gt;' in out)
    check(f'{B}: no raw markup from ledger text anywhere',
          not re.search(r'<(?!/?(div|span)\b)', out), re.findall(r'<(?!/?(?:div|span)\b)[^>]{0,20}', out))
    check(f'{B}: added-after-kickoff tag on that pick alone',
          out.count('added after kickoff') == 1 and '<span class="lntag">added after kickoff</span>' in item_of(out, 'Late Add ML'))
    check(f'{B}: result and units as displayed',
          '<span class="lnres L">L</span><span class="lnname">Mid B ML</span><span class="lnunits">5u</span>' in out
          and '<span class="lnres P">P</span><span class="lnname">Push ML</span><span class="lnunits">6u</span>' in out
          and '<span class="lnres W">W</span><span class="lnname">New A ML</span><span class="lnunits">5u</span>' in out)
    check(f'{B}: no dollar sign rendered (a text carrying one is left out whole)',
          '$' not in out and 'New B ML' not in out and 'Risked' not in out)
    check(f'{B}: no game, odds or score fields leak into the panel', 'vs Somebody' not in out and 'A 1, B 0' not in out and '-110' not in out)
    check(f'{B}: no comment-shaped run for scrub_shipped to eat', not re.search(r'//|/\*|\*/|<!--', out))
    check(f'{B}: the section survives scrub_shipped unchanged', scrub_fn(src)(out) == out)
    check(f'{B}: the slashes still read as text (entity-encoded)', 'Read held &#47;&#47; user order &#47;* main *&#47; &lt;!-- his --&gt; fine.' in out)

    many = learn(P['many'])
    check(f'{B}: one day with 8 lessons shows the 6 newest-graded, newest first', names(many) == ['P%d ML' % k for k in range(8, 2, -1)], names(many))
    check(f'{B}: a brief carrying a dollar sign is left out whole', '<div class="lnbrief">' not in many and '$' not in many)
    check(f'{B}: a string added_after_kickoff flag is no tag', 'lntag' not in many)
    cap = learn(P['cap'])
    check(f'{B}: the pick cap reached inside a day: no further day is opened, brief and all', seq(cap) == WANT_CAP, seq(cap))
    chain = learn(P['chain'])
    check(f'{B}: chain-shaped rows (learning, no note) show their learning, newest-graded first', seq(chain) == WANT_CHAIN, seq(chain))
    check(f'{B}: a chain row\'s learning is the pick text',
          '<div class="lnnote">Won +5.0u (NYR 0 @ BOS 3); the read held.</div>' in chain
          and '<div class="lnnote">User-directed pick carded by owner word at disclosed sub-bar</div>' in chain)
    pref = learn(P['pref'])
    check(f'{B}: note before learning; a missing, blank, non-string or left-out note falls back to the learning',
          notes(pref) == WANT_PREF, notes(pref))
    check(f'{B}: a pick whose note and learning both name money is left out', 'Money Both ML' not in pref and 'dollars' not in pref)
    brief = learn(P['brief'])
    check(f'{B}: a graded day with a brief and no pick text shows its brief',
          seq(brief) == [('day', 'Thursday, Oct 1'), ('brief', 'Only a brief today.')] and brief.startswith(HEAD), seq(brief))
    surr = learn(P['surr'])
    check(f'{B}: lone-surrogate texts are left out as if absent (brief, notes, name); a proper pair stays',
          seq(surr) == WANT_SURR and '\U0001F600' in surr, seq(surr))
    try:
        surr.encode('utf-8'); enc = True
    except UnicodeEncodeError:
        enc = False
    check(f'{B}: the section is always writable as UTF-8', enc)
    for v, pth in zip(MONEY, P_MONEY):
        r = learn(pth)
        check(f'{B}: money left out whole in brief, note and learning: {v!r}',
              seq(r) == [('day', 'Thursday, Oct 1'), ('item', 'Clean ML')] and not MONEY_RE.search(r), seq(r))
    ws = learn(P['ws'])
    check(f'{B}: whitespace-only texts are blank and padding is trimmed (the client\'s set)',
          notes(ws) == WANT_WS and '<div class="lnbrief">' not in ws, notes(ws))
    keep = learn(P['keep'])
    check(f'{B}: look-alikes that name no money stay', [t for _, t in notes(keep)] == KEEP[::-1], notes(keep))
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
paths = list(P.values()) + P_MONEY + [p for _, p in EMPTY_CASES if os.path.exists(p)] + ([LIVE] if os.path.exists(LIVE) else [])
r = subprocess.run(['node', hp, os.path.join(SD, 'index_v2.js')] + paths, capture_output=True, text=True)
check('node runs index_v2.js rpLearnHtml', r.returncode == 0, r.stderr[-400:])
client = json.loads(r.stdout) if r.returncode == 0 and r.stdout else {}

def inner(server):
    # the box contents, in the client's entity spelling (a browser reads both the same)
    if not server:
        return ''
    return server[len(HEAD) + len(BOX):-len('</div>\n')].replace('&#x27;', "'").replace('&#47;', '/')

_, learn0 = builder_fn(TWINS[0])
for label, p in list(P.items()) + [('money %r' % v, p) for v, p in zip(MONEY, P_MONEY)]:
    check(f'client renders the {label} ledger exactly as the builder', client.get(p) == inner(learn0(p)),
          (client.get(p) or '')[:160])
check('client: chain-shaped rows render their learning', 'Won +5.0u (NYR 0 @ BOS 3); the read held.' in (client.get(P['chain']) or ''))
check('client: hostile note never markup', '<img' not in (client.get(P['fix']) or 'x<img'))
check('client: no money anywhere', all(not MONEY_RE.search(client.get(p) or '$') for p in [P['fix'], P['many'], P['pref']] + P_MONEY))
check('client: lone surrogates left out', not re.search(r'[\ud800-\udfff]', client.get(P['surr']) or '\ud800') and 'Pair ML' in (client.get(P['surr']) or ''))
check('client: a wrong-shaped file is not a ledger (keeps the page as it is)',
      client.get(os.path.join(T, 'list.json')) is None and client.get(os.path.join(T, 'str.json')) is None)
check('client: a readable ledger with nothing to show renders empty (section hides)',
      client.get(os.path.join(T, 'none.json')) == '' and client.get(os.path.join(T, 'ungraded.json')) == '' and client.get(P['quiet']) == '')

# ---- the live ledger, read-only: whatever it holds, the panel stays inside the rules ----
if os.path.exists(LIVE):
    live = learn0(LIVE)
    check('live history.json: at most 6 picks and 3 days', live.count('<div class="lnitem">') <= 6 and live.count('<div class="lnday">') <= 3)
    check('live history.json: no money, no raw ledger markup', not MONEY_RE.search(live) and not re.search(r'<(?!/?(div|span)\b)', live))
    check('live history.json: client and builder agree', client.get(LIVE) == inner(live), (client.get(LIVE) or '')[:160])

# ---- a real build per twin: a lone surrogate never crashes the page write; the gate cuts the section ----
DEAD = 'http://127.0.0.1:9'
CARD = {'date': '2099-10-01', 'date_label': 'Thursday, Oct 1', 'updated': 'Oct 1, 8:42 AM PT', 'record': '21-11', 'units_pl': '+4.76u',
        'units_ledger': None, 'yesterday': '', 'status_note': '', 'preview': False, 'parlay': None, 'picks': []}
BUILD_HIST = {'days': [{'date': '2026-10-01', 'label': 'Thursday, Oct 1', 'record': '3-1', 'units': '+2.00u', 'brief': 'Brief \ud800 cut.',
                        'picks': [pick('Clean ML', 'W', 'Game not started when this was carded; the read held.'),
                                  pick('Lone ML', 'L', 'lone \udc00 low half'),
                                  chain_pick('Chain ML', 'W', 'Chain lesson kept.'),
                                  pick('Lone Learn ML', 'W', learning='lone high \ud83d at the end')]}]}
def build(builder):
    d = tempfile.mkdtemp(prefix='rp-learnbuild-')
    try:
        os.makedirs(os.path.join(d, 'scripts')); os.makedirs(os.path.join(d, 'slates'))
        shutil.copy(builder, os.path.join(d, 'scripts', 'build_gh_page_v2.py'))
        for f in ('index_v2.js', 'index_v2.css', 'game_page_template.html', 'team_page_template.html', 'poly_us.py'):
            shutil.copy(os.path.join(SD, f), os.path.join(d, 'scripts', f))
        for f in ('feed_arbiter.js', 'feed_registry.json', 'config_leagues.json'):
            shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
        json.dump(CARD, open(os.path.join(d, 'manifest.json'), 'w'), indent=1)
        json.dump(BUILD_HIST, open(os.path.join(d, 'history.json'), 'w'), indent=1)
        json.dump([], open(os.path.join(d, 'slates', 'odds_prefill.json'), 'w'))
        env = dict(os.environ, RP_REFRESH='1', http_proxy=DEAD, https_proxy=DEAD, HTTP_PROXY=DEAD, HTTPS_PROXY=DEAD)
        r = subprocess.run([sys.executable, os.path.join(d, 'scripts', 'build_gh_page_v2.py'), 'manifest.json', 'index.html'],
                           cwd=d, env=env, capture_output=True, text=True, timeout=600)
        ip = os.path.join(d, 'index.html')
        page = open(ip, encoding='utf-8').read() if os.path.exists(ip) else ''
        return r.returncode, page, r.stderr
    finally:
        shutil.rmtree(d, ignore_errors=True)

STRIP = r'''
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync(process.argv[2], 'utf8');
const start = src.indexOf('function rpStripLearn(');
let depth = 0, end = -1;
for (let i = start; start >= 0 && i < src.length; i++) {
  if (src[i] === '{') depth++;
  else if (src[i] === '}') { depth--; if (depth === 0) { end = i + 1; break; } }
}
const ctx = vm.createContext({});
vm.runInContext(src.slice(start, end), ctx);
process.stdout.write(ctx.rpStripLearn(fs.readFileSync(process.argv[3], 'utf8')));
'''
sp = put('strip.js', STRIP, raw=True)
for B in TWINS:
    rc, page, err = build(os.path.join(SD, B))
    check(f'{B}: builds with lone surrogates in the ledger, index.html written', rc == 0 and len(page) > 10000, err[-300:])
    if not page:
        continue
    sec = page[page.find(HEAD):]
    sec = sec[:sec.find('</div>\n', sec.find(BOX)) + len('</div>\n')] if HEAD in page and BOX in page else ''
    check(f'{B}: the built panel shows the clean lessons and leaves the lone-surrogate texts out',
          bool(sec) and seq(sec) == [('day', 'Thursday, Oct 1'), ('item', 'Chain ML'), ('item', 'Clean ML')], seq(sec))
    check(f'{B}: the built page holds no lone surrogate', not re.search(r'[\ud800-\udfff]', page))
    pp = put('built-' + B + '.html', page, raw=True)
    r = subprocess.run(['node', sp, os.path.join(SD, 'health_gate.js'), pp], capture_output=True, text=True)
    cut = r.stdout if r.returncode == 0 else ''
    check(f'{B}: the health gate cuts exactly the learnings section from the built page',
          bool(sec) and cut == page.replace(sec, '\n\n', 1), r.stderr[-300:])
    check(f'{B}: so a note reading "Game not started" never reaches the gate\'s substring checks',
          'Game not started' in page and 'Game not started' not in cut and 'rpCmbGo' in cut and 'id="rpNewsCar"' in cut)

tmp.cleanup()
print('ALL OK' if not failures else '%d FAIL' % failures)
sys.exit(1 if failures else 0)
