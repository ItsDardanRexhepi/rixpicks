#!/usr/bin/env node
/* Health gate vs the learnings panel. The Home panel "What the system is learning" (builder
   _learnings_html, #rpLearnHead + #rpLearn) puts ledger text - day briefs, per-pick notes - into
   index.html, and scripts/health_gate.js checks the page with plain substrings (the blank-pregame
   check fails on any 'Game not started'; presence markers pass on any copy of a marker). The gate
   reads the page with that section cut out (rpStripLearn), in the local build check and the served
   site check alike. This holds it to that:
     - rpStripLearn (the real function, from health_gate.js): cuts the heading and the box, each once,
       to the box's own closing tag; leaves look-alike ids alone; an unclosed section, or a cut that
       would take any tag but div/span, leaves the page whole;
     - the real gate, local mode, on a page in a throwaway folder: a note reading 'Game not started'
       no longer trips the blank-pregame check, while that text anywhere else still does, and a
       marker found only inside a note does not count as present;
     - the real gate, --serve mode, against the same pages through a stubbed fetch (no socket, no
       network: any other host throws): the same three outcomes; the clean page passes whole.
   The cut on a real built page is in test_learnings_panel.py.
   Run: node scripts/test_health_gate_learn.js */
'use strict';
const fs = require('fs'), os = require('os'), path = require('path'), vm = require('vm'), { spawnSync } = require('child_process');
const GATE = path.join(__dirname, 'health_gate.js');
const src = fs.readFileSync(GATE, 'utf8');
let failures = 0;
function check(label, cond, extra) {
  if (!cond) failures++;
  console.log((cond ? 'OK   ' : 'FAIL ') + label + (cond || extra === undefined ? '' : '  [' + extra + ']'));
}
function extract(name) {
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) { check(name + ' present in health_gate.js', false); return ''; }
  let depth = 0;
  for (let i = start; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) return src.slice(start, i + 1); }
  }
  check(name + ' balanced', false); return '';
}
const ctx = vm.createContext({ RegExp, String });
vm.runInContext(extract('rpStripLearn'), ctx);
const strip = s => (typeof ctx.rpStripLearn === 'function' ? ctx.rpStripLearn(s) : null);

// the builder's markup and escaping (_learnings_html: html.escape, then '/' as &#47;)
const escB = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
  .replace(/'/g, '&#x27;').replace(/\//g, '&#47;');
const HEAD = '<div class="sect home-only" id="rpLearnHead" style="margin-top:18px">What the system is learning</div>\n';
const item = (name, note) => '<div class="lnitem"><div class="lnhead"><span class="lnres W">W</span><span class="lnname">' + escB(name)
  + '</span><span class="lnunits">5u</span></div><div class="lnnote">' + escB(note) + '</div></div>';
const learn = (notes, brief) => HEAD + '<div class="card learn home-only" id="rpLearn" aria-live="polite"><div class="lnday">Thursday, Oct 1</div>'
  + (brief ? '<div class="lnbrief">' + escB(brief) + '</div>' : '') + notes.map((n, i) => item('Pick ' + i + ' ML', n)).join('') + '</div>\n';

// ---- rpStripLearn on its own ----
{
  const sec = learn(['Game not started at carding; the read held.', 'x <img src=y> // rpCmbGo'], 'Brief: Game not started.');
  check('section cut whole, heading and box, text around it kept', strip('A\n' + sec + 'B') === 'A\n\n\nB', String(JSON.stringify(strip('A\n' + sec + 'B'))).slice(0, 120));
  check('no section: page unchanged', strip('<div id="rpNews">Game not started</div>') === '<div id="rpNews">Game not started</div>');
  check('a look-alike attribute is not the section (data-id="rpLearn")',
    strip('<div data-id="rpLearn">Game not started</div>') === '<div data-id="rpLearn">Game not started</div>');
  check('a look-alike id is not the section (id="rpLearnX")', strip('<div id="rpLearnX">Game not started</div>') === '<div id="rpLearnX">Game not started</div>');
  check('the cut ends at the box\'s own closing tag (nested divs counted)',
    strip('<main><div class="card learn" id="rpLearn"><div><div>a</div></div></div><div id="after">Game not started</div></main>')
      === '<main><div id="after">Game not started</div></main>');
  const unclosed = '<main><div class="card learn" id="rpLearn"><div class="lnnote">Game not started</div></main>';
  check('an unclosed box (the cut would run past </main>) leaves the page whole', strip(unclosed) === unclosed);
  const runaway = '<div class="card learn" id="rpLearn"><div class="lnnote">x</div><script>var a=1</script></div>';
  check('a cut that would take a <script> leaves the page whole', strip(runaway) === runaway);
  const trunc = '<div class="card learn" id="rpLearn"><div class="lnnote">Game not started';
  check('a box with no closing tag at all leaves the page whole', strip(trunc) === trunc);
  check('each id is cut once: a second box later on stays',
    strip('<div id="rpLearn">a</div><div id="rpLearn">Game not started</div>') === '<div id="rpLearn">Game not started</div>');
  check('the heading alone is cut', strip('x' + HEAD + 'y') === 'x\ny');
}

// ---- the real gate on whole pages ----
const NOTE_PREGAME = 'Game not started when this was carded; c.estimate_note held the read.';
function page(o) {
  const js = (o.noCombos ? '' : 'var rpCmbGo=1;') + 'function rpComboFresh(){return true}window.rpComboFresh=rpComboFresh;var rpFeedWire=1;'
    + 'var c={futures:true};if(c.futures===true){}fetch("slates/wooder_dingers.json");fetch("slates/wooder_tickets.json");'
    + 'var count=null,state="pre";if(count==null&&(state==="in"||state==="post")){}';
  return '<!doctype html><html><head><meta charset="utf-8"><title>RixPicks</title></head><body><div class="layout"><main>\n'
    + '<div class="card" id="rpWNote">CASHED = live stat threshold met, not a verified payout.</div><div id="rpWRecWrap"></div>\n'
    + (o.outside || '') + (o.learn || '')
    + '<div class="sect home-only" style="margin-top:18px">News</div>\n<div class="card newscar home-only" id="rpNewsCar"></div>\n'
    + '</main></div>\n<script>' + js + '</script><script src="ticket-feed.js"></script>\n'
    + '<div hidden>' + 'x'.repeat(110000) + '</div></body></html>\n';
}
const CASES = {
  note: page({ learn: learn([NOTE_PREGAME], 'Game not started on two legs; the read held.') }),
  outside: page({ learn: learn([NOTE_PREGAME]), outside: '<div class="leg">Game not started</div>\n' }),
  markerInNote: page({ noCombos: true, learn: learn(['rpCmbGo was the module that carried this read.']) }),
  unclosed: page({ learn: HEAD + '<div class="card learn home-only" id="rpLearn" aria-live="polite"><div class="lnnote">' + escB(NOTE_PREGAME) + '</div>\n' }),
};
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'rp-gate-learn-'));
const clean = Object.assign({}, process.env);
for (const k of ['HOLD_SELFTEST_ERROR', 'HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'NODE_USE_ENV_PROXY']) delete clean[k];

// local mode: a throwaway folder holding only index.html (the gate's fixture, twin and yards checks
// fail there by design; only the page checks are read)
function local(html) {
  const d = fs.mkdtempSync(path.join(tmp, 'local-'));
  fs.writeFileSync(path.join(d, 'index.html'), html);
  const r = spawnSync(process.execPath, [GATE], { cwd: d, env: clean, encoding: 'utf8', timeout: 120000 });
  return { out: r.stdout || '', code: r.status };
}
// --serve mode: fetch stubbed before the gate loads; only https://gate.test answers, from files
const STUB = path.join(tmp, 'stub.js');
fs.writeFileSync(STUB, `'use strict';
const fs = require('fs'), path = require('path');
globalThis.fetch = async (u) => {
  const url = new URL(u);
  if (url.origin !== 'https://gate.test') throw new Error('stub: no network (' + url.origin + ')');
  const f = path.join(process.env.GATE_STUB_DIR, url.pathname === '/' ? 'index.html' : url.pathname.slice(1));
  if (!fs.existsSync(f)) return { ok: false, status: 404, text: async () => '' };
  const body = fs.readFileSync(f, 'utf8');
  return { ok: true, status: 200, text: async () => body };
};
`);
function serve(html) {
  const d = fs.mkdtempSync(path.join(tmp, 'serve-'));
  fs.mkdirSync(path.join(d, 'slates'));
  const now = new Date().toISOString();
  fs.writeFileSync(path.join(d, 'index.html'), html);
  fs.writeFileSync(path.join(d, 'slates', 'wooder_combos.json'), JSON.stringify({ combos: [{ id: 'c1' }] }));
  fs.writeFileSync(path.join(d, 'futures.json'), JSON.stringify([{ kalshi_quote: { quoted_at: now } }]));
  fs.writeFileSync(path.join(d, 'ticket-feed.js'), '/* ticket feed */\n' + 'var t=0;\n'.repeat(800));
  fs.writeFileSync(path.join(d, 'slates', 'past_tickets.json'), JSON.stringify({ entries: [{ id: 'p1' }] }));
  fs.writeFileSync(path.join(d, 'slates', 'nfl_rec_yards.json'), JSON.stringify({ fetched_at: now, players: { a: { yards: 12 } } }));
  fs.writeFileSync(path.join(d, 'slates', 'x_feed.json'), JSON.stringify({ items: [{ id: 'x1' }] }));
  const r = spawnSync(process.execPath, ['-r', STUB, GATE, '--serve', '--base=https://gate.test'],
    { cwd: d, env: Object.assign({}, clean, { GATE_STUB_DIR: d }), encoding: 'utf8', timeout: 120000 });
  return { out: r.stdout || '', code: r.status };
}
const line = (out, s) => out.split('\n').some(l => l === s);
const PAGE_CHECKS = ['no literal \\n text leak at page bottom', 'ticket boxes carry no repeated fine print (one note above Rolling Record)',
  'index.html: all 1 script blocks parse', 'index_nocanon.html retired (absent)', 'combos module (Same Game Parlays)', 'rpComboFresh exported global',
  'feed wire (live tracker paint)', 'futures bypass present', 'dingers module fetch', 'tickets module fetch', 'unknown-not-zero guard',
  'blank-pregame spec (no Game-not-started text)', 'CASHED explainer', 'ticket feed client', 'dingers module mounted exactly once'];

{
  const r = local(CASES.note);
  const bad = PAGE_CHECKS.filter(n => !line(r.out, 'OK   ' + n));
  check('local: a note and a brief reading "Game not started" (and c.estimate_note) trip no page check', bad.length === 0, bad.join(' | '));
  const r2 = local(CASES.outside);
  check('local: "Game not started" outside the panel still fails the blank-pregame check',
    line(r2.out, 'FAIL blank-pregame spec (no Game-not-started text)  [user impact: pregame legs show stale text instead of blank]') && r2.code === 1);
  const r3 = local(CASES.markerInNote);
  check('local: a marker found only inside a note is not present (combos check fails)',
    r3.out.split('\n').some(l => l.startsWith('FAIL combos module (Same Game Parlays)')) && r3.code === 1);
  const r4 = local(CASES.unclosed);
  check('local: an unclosed panel is read whole (its "Game not started" fails the check)',
    r4.out.split('\n').some(l => l.startsWith('FAIL blank-pregame spec')));
}
{
  const r = serve(CASES.note);
  check('serve: the page with a "Game not started" note passes the whole gate', r.code === 0 && line(r.out, 'HEALTH GATE PASS')
    && line(r.out, 'OK   served: no Game-not-started text') && line(r.out, 'OK   home page serves (>100KB)'), r.out.split('\n').filter(l => /^FAIL|ERROR/.test(l)).join(' | '));
  const r2 = serve(CASES.outside);
  check('serve: "Game not started" outside the panel still fails the served check',
    r2.code === 1 && r2.out.split('\n').some(l => l.startsWith('FAIL served: no Game-not-started text')));
  const r3 = serve(CASES.markerInNote);
  check('serve: a marker found only inside a note is not present (served combos check fails)',
    r3.code === 1 && r3.out.split('\n').some(l => l.startsWith('FAIL served: combos module present')));
  const r4 = serve(CASES.unclosed);
  check('serve: an unclosed panel is read whole (its "Game not started" fails the served check)',
    r4.code === 1 && r4.out.split('\n').some(l => l.startsWith('FAIL served: no Game-not-started text')));
}
fs.rmSync(tmp, { recursive: true, force: true });
console.log(failures ? failures + ' FAIL' : 'ALL OK');
process.exit(failures ? 1 : 0);
