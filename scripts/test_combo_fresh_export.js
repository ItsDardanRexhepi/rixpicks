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
  if (modMatch) {
    const modSrc = modMatch[0].replace(/^<script>/, '').replace(/<\/script>$/, '');
    const sample = { combos: [{ id: 'idea-mlb-ks-20260930', type: 'idea', date: '2026-09-30',
      title: 'Strikeouts Parlay (4 legs)', matchup: 'PHI@ATL', time: 'from 11:00 AM PT',
      legs: [{ player: 'Cristopher Sanchez', market: '7+ strikeouts vs ATL', kalshi: '+138 · 42c' }],
      estimate_note: 'note', prices_note: 'snap' }] };
    const listeners = {}, timers = [];
    const style = { display: '' };
    const box = { innerHTML: '', parentNode: { style } };
    const sandbox = {
      document: { getElementById: () => box, readyState: 'loading' },
      addEventListener: (ev, fn) => { (listeners[ev] = listeners[ev] || []).push(fn); },
      fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve(sample) }),
      setTimeout: (fn) => { timers.push(fn); return 1; },
      Date, JSON, console,
    };
    sandbox.window = sandbox;
    vm.createContext(sandbox);
    vm.runInContext(modSrc, sandbox); // rpComboFresh intentionally NOT defined yet
    for (let i = 0; i < 8; i++) await new Promise(r => setImmediate(r));
    const renderedEarly = box.innerHTML.length > 0;
    // now the utils script "runs": define the global, then fire load + timers
    vm.runInContext(extract('rpComboFresh') + '\nwindow.rpComboFresh=rpComboFresh;', sandbox);
    (listeners.load || []).forEach(fn => fn());
    timers.forEach(fn => fn());
    for (let i = 0; i < 8; i++) await new Promise(r => setImmediate(r));
    check('module does not render before load when fetch resolves instantly', !renderedEarly);
    check('module renders Strikeouts card after load with global present', box.innerHTML.includes('Strikeouts Parlay (4 legs)'));
    check('module parent not hidden after successful render', style.display !== 'none');
  }
  if (failures) { console.error(failures + ' FAIL'); process.exit(1); }
  console.log('ALL OK (incl. race sim)');
})();

