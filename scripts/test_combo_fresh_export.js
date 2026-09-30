#!/usr/bin/env node
/* Standing regression fixture (Sep 30 strikeouts-idea incident): the Same Game Parlays
   module reads rpComboFresh as a GLOBAL from inside its async fetch callback, but
   index_v2.js wraps everything in IIFEs - without an explicit window export the function
   is undefined at callback time, the module throws, its .catch fail-closes hidden, and
   every combo (type idea or link) silently never renders. A hidden module is visually
   identical to "no fresh combos", so this went unnoticed until a dated idea had to render.
   Guards: (1) the export line exists in index_v2.js, (2) document-order simulation - a
   consumer callback registered BEFORE the utils script executes still resolves the global
   afterwards, (3) the built page carries the export. Run: node scripts/test_combo_fresh_export.js */
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
let failures = 0;
function check(label, ok) { if (!ok) failures++; console.log((ok ? 'OK   ' : 'FAIL ') + label); }

const src = fs.readFileSync(path.join(__dirname, 'index_v2.js'), 'utf8');

// (1) export exists, exactly once, after the def
const defIdx = src.indexOf('function rpComboFresh(');
check('rpComboFresh defined in index_v2.js', defIdx > 0);
const expCount = (src.match(/window\.rpComboFresh=rpComboFresh;/g) || []).length;
check('window.rpComboFresh export present exactly once', expCount === 1);
check('export comes after the definition', expCount === 1 && src.indexOf('window.rpComboFresh=rpComboFresh;') > defIdx);

// (2) document-order simulation: the page emits the consumer module BEFORE the utils script.
// The consumer's filter runs in a later (async) turn - it must find the global by then.
function extract(name) {
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) { console.error('FAIL: ' + name + ' not found'); process.exit(1); }
  let depth = 0;
  for (let i = start; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) return src.slice(start, i + 1); }
  }
  console.error('FAIL: unbalanced ' + name); process.exit(1);
}
const ctx = vm.createContext({ Date, JSON, RegExp, String, Number });
ctx.window = ctx; // classic-script global proxy
vm.runInContext(`var later=null; function consumer(){ later=function(){ return (([{id:'idea-x-20990101'}]).filter(rpComboFresh)).length; }; } consumer();`, ctx);
// the utils script's relevant slice: the def, then (per the patch) the export line
const exportLine = src.includes('window.rpComboFresh=rpComboFresh;') ? 'window.rpComboFresh=rpComboFresh;' : '';
vm.runInContext(extract('rpComboFresh') + '\n' + exportLine, ctx);
let got = 'threw';
try { got = vm.runInContext('later()', ctx); } catch (e) { got = 'threw:' + e.message; }
check('consumer callback registered before utils script resolves rpComboFresh after it runs', got === 1);

// (3) built page carries the export (gate on the committed artifact)
const page = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
check('built index.html contains the window.rpComboFresh export', page.includes('window.rpComboFresh=rpComboFresh;'));


// (4) behavioral race simulation: the module's fetch chain must not run before the page's
// last script can define rpComboFresh. Simulates a cache-hit fetch (resolves immediately,
// .then runs in the between-scripts microtask checkpoint) with rpComboFresh NOT yet defined,
// then fires load and asserts the module renders. Old (ungated) module: filter throws
// ReferenceError -> catch hides -> FAIL here.
const comboPage = fs.readFileSync(process.argv[2] || path.join(__dirname, '..', 'index.html'), 'utf8');
const modMatch = comboPage.match(/<script>\(function\(\)\{var box=document\.getElementById\("rpCmb"\)[\s\S]*?<\/script>/);
check('combos module script found in page', !!modMatch);
(async () => {
  let sandboxFeed = null;
  async function runSim(sample, feedPayload) {
    sandboxFeed = feedPayload ? () => Promise.resolve(feedPayload) : undefined;
    const modSrc = modMatch[0].replace(/^<script>/, '').replace(/<\/script>$/, '');
    const listeners = {}, timers = [];
    const style = { display: '' };
    const box = { innerHTML: '', parentNode: { style } };
    box.querySelector = () => (box.innerHTML.includes('class="rpfeedtrk"') ? {} : null);
    box.querySelectorAll = () => {
      const out = [];
      const re = /<div class="rpfeedtrk" data-p="([^"]*)"><\/div>/g;
      let m;
      while ((m = re.exec(box.innerHTML))) {
        const el = { _p: m[1].replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>'), innerHTML: '', getAttribute(k) { return k === 'data-p' ? this._p : null; } };
        out.push(el);
      }
      box._trk = out;
      return out;
    };
    const sandbox = {
      document: { getElementById: () => box, readyState: 'loading', createElement: () => ({ set src(v) {}, set onload(f) {} }), head: { appendChild() {} } },
      addEventListener: (ev, fn) => { (listeners[ev] = listeners[ev] || []).push(fn); },
      fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve(sample) }),
      setTimeout: (fn) => { timers.push(fn); return 1; },
      setInterval: () => 1,
      rpTicketFeed: sandboxFeed,
      Date, JSON, console,
    };
    sandbox.window = sandbox;
    vm.createContext(sandbox);
    vm.runInContext(modSrc, sandbox); // rpComboFresh intentionally NOT defined yet
    for (let i = 0; i < 8; i++) await new Promise(r => setImmediate(r));
    const renderedEarly = box.innerHTML.length > 0;
    vm.runInContext(extract('rpComboFresh') + '\nwindow.rpComboFresh=rpComboFresh;', sandbox);
    (listeners.load || []).forEach(fn => fn());
    timers.forEach(fn => fn());
    for (let i = 0; i < 8; i++) await new Promise(r => setImmediate(r));
    return { box, style, renderedEarly };
  }
  if (modMatch) {
    const s1 = { combos: [{ id: 'idea-mlb-ks-20260930', type: 'idea', date: '2026-09-30',
      title: 'Strikeouts Parlay (4 legs)', badge: 'PLACED - reported by Julian',
      matchup: 'PHI@ATL', time: 'from 11:00 AM PT',
      legs: [{ player: 'Cristopher Sanchez', market: '7+ strikeouts vs ATL', kalshi: '+138 · 42c' }],
      estimate_note: 'note', prices_note: 'snap' }] };
    s1.combos[0].legs = [
      { player: 'Cristopher Sanchez', market: '7+ strikeouts vs ATL', kalshi: '+138 · 42c' },
      { player: 'Hunter Brown', market: '7+ strikeouts vs CWS', kalshi: '+117 · 46c' },
      { player: 'Max Fried', market: '6+ strikeouts vs BOS', kalshi: '+117 · 46c' },
      { player: 'Kevin Gausman', market: '5+ strikeouts at SD', kalshi: '+117 · 46c' },
      { player: 'Nobody Feedless', market: '9+ strikeouts', kalshi: '+200' }];
    const feed = { generatedAt: '2026-09-30T18:00:00Z', tickets: [{ id: 'k-parlay-2026-09-30', legs: [
      { legId: 'k-sanchez', kind: 'pitcher_strikeouts', threshold: 7, player: { name: 'Cristopher Sánchez' }, current: 3, status: 'pending', freshness: { sourceTs: '2026-09-30T17:59:50Z' } },
      { legId: 'k-brown', kind: 'pitcher_strikeouts', threshold: 7, player: { name: 'Hunter Brown' }, current: 7, status: 'hit', freshness: { sourceTs: '2026-09-30T17:59:50Z' } },
      { legId: 'k-fried', kind: 'pitcher_strikeouts', threshold: 6, player: { name: 'Max Fried' }, current: null, status: 'pre', freshness: { sourceTs: null } },
      { legId: 'k-gausman', kind: 'pitcher_strikeouts', threshold: 5, player: { name: 'Kevin Gausman' }, current: null, status: 'unavailable', freshness: { sourceTs: null } }] },
      { id: 'hits-tracker-2026-09-30', legs: [
      { legId: 'h-turner', kind: 'batter_hits', threshold: 1, player: { name: 'Trea Turner' }, current: 1, status: 'hit', freshness: { sourceTs: '2026-09-30T18:25:00Z' } }] }] };
    const r1 = await runSim(s1, feed);
    check('module does not render before load when fetch resolves instantly', !r1.renderedEarly);
    check('module renders Strikeouts card after load with global present', r1.box.innerHTML.includes('Strikeouts Parlay (4 legs)'));
    check('module parent not hidden after successful render', r1.style.display !== 'none');
    check('badge override renders (PLACED - reported by Julian)', r1.box.innerHTML.includes('PLACED - reported by Julian'));
    check('badge override replaces the default (no NOT BOUGHT)', !r1.box.innerHTML.includes('NOT BOUGHT'));
    const painted = () => (r1.box._trk || []).map(e => e._p + '=>' + e.innerHTML).join('|');
    check('feed wire: pending renders "3 of 7 Ks"', painted().includes('3 of 7 Ks'));
    check('feed wire: hit renders "7 of 7 Ks" with check', painted().includes('7 of 7 Ks \u2713'));
    check('feed wire: pre renders "Game not started" (never 0)', painted().includes('Game not started'));
    check('feed wire: unavailable renders "Unavailable" (never 0)', painted().includes('Unavailable'));
    check('feed wire: freshness timestamp shown', painted().includes('2026-09-30T17:59:50Z'));
    check('feed wire: accent-insensitive player match (Sanchez)', (r1.box._trk || []).some(e => e._p === 'Cristopher Sanchez' && e.innerHTML.includes('3 of 7 Ks')));
    check('feed wire: unmatched leg stays empty (fail-closed)', (r1.box._trk || []).some(e => e._p === 'Nobody Feedless' && e.innerHTML === ''));
    const s4 = { combos: [{ id: 'idea-mlb-hits-20260930b', type: 'idea', date: '2026-09-30',
      title: 'Hits', matchup: 'PHI@ATL', legs: [{ player: 'Trea Turner', market: '1+ hit', kalshi: '-233' }] }] };
    const r4 = await runSim(s4, feed);
    const painted4 = () => (r4.box._trk || []).map(e => e._p + '=>' + e.innerHTML).join('|');
    check('feed wire: hits kind renders H suffix never HR', painted4().includes('1 of 1 H \u2713') && !painted4().includes('HR'));
    const s2 = { combos: [{ id: 'idea-mlb-hits-20260930', type: 'idea', date: '2026-09-30',
      title: 'Hits Parlay Tracker (4 legs)', matchup: 'PHI@ATL', time: 'from 11:00 AM PT',
      legs: [{ player: 'Trea Turner', market: '1+ hit at ATL', kalshi: '-233 · 70c', tag: 'Confirmed leadoff' }] }] };
    const r2 = await runSim(s2);
    check('default badge renders without override (IDEA · NOT BOUGHT)', r2.box.innerHTML.includes('IDEA · NOT BOUGHT'));
    check('leg tag renders (Confirmed leadoff)', r2.box.innerHTML.includes('Confirmed leadoff'));
    const s3 = { combos: [{ id: 'idea-plain-20260930', type: 'idea', date: '2026-09-30',
      title: 'Plain', matchup: 'X', legs: [{ player: 'P', market: 'm', kalshi: '+100' }] }] };
    const r3 = await runSim(s3);
    check('no tag field renders no tag', !r3.box.innerHTML.includes('Confirmed leadoff'));
  }
  if (failures) { console.error(failures + ' FAIL'); process.exit(1); }
  console.log('ALL OK (incl. race sim + badge/tag)');
})();

