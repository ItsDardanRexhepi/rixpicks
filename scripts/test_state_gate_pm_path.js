#!/usr/bin/env node
/* Render-level regression fixture for the state-gate positive path (owner 9/29 9:33 PT):
   a pick priced by a prediction-market arm must RENDER that chip in CA and in the
   unresolved state - the fail-closed default is the nationwide PM set (KAL/POLY/DKP/FDP),
   not KAL alone. Drives the REAL rpFilter/rpBookLive/RP_LEGAL_STATE in the built page:
   injects synthetic priced PM-arm chips (builder emission shape) into the first pick,
   runs the gate per state, asserts visibility + tappability.
   Run: node scripts/test_state_gate_pm_path.js */
'use strict';
const fs = require('fs'), path = require('path');
let JSDOM;
try { ({ JSDOM } = require('jsdom')); } catch (e) { ({ JSDOM } = require('/tmp/node_modules/jsdom')); }
const html = fs.readFileSync(process.env.RP_FIXTURE_HTML || path.join(__dirname, '..', 'index.html'), 'utf8');
let failures = 0;
function check(label, ok) { if (!ok) failures++; console.log((ok ? 'OK   ' : 'FAIL ') + label); }

function visibleBooks(win, st) {
  win.rpFilter(st);
  const pk = win.document.querySelector('.pick');
  const chips = [...pk.querySelectorAll('[data-book]')].filter(a => !a.querySelector('[data-book]'));
  const vis = {}, hid = [];
  chips.forEach(a => { if (a.style.display !== 'none') vis[a.dataset.book] = a; else hid.push(a.dataset.book); });
  return { vis, hid };
}

const dom = new JSDOM(html, {
  url: 'https://rix-picks.com/', runScripts: 'dangerously', pretendToBeVisual: true,
  beforeParse(w) {
    w.matchMedia = w.matchMedia || function () { return { matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }; };
    w.fetch = function () { return new Promise(function () {}); };
  }
});

setTimeout(() => {
  const w = dom.window, d = w.document;
  if (typeof w.rpFilter !== 'function' || typeof w.rpBookLive !== 'function') { console.error('FAIL: gate functions not exposed by built page'); process.exit(1); }
  const box = d.querySelector('.pick .chips') || d.querySelector('.pick');
  if (!box) { console.error('FAIL: no pick in built page'); process.exit(1); }
  ['POLY', 'DKP', 'FDP'].forEach(b => {
    const a = d.createElement('a');
    a.className = 'chip'; a.setAttribute('data-book', b);
    a.setAttribute('href', 'https://example.com/' + b.toLowerCase() + '/market/1');
    a.setAttribute('data-sb', 'https://example.com/' + b.toLowerCase() + '/market/1');
    a.setAttribute('onclick', 'return rpRoute(event,this)');
    a.setAttribute('target', '_blank'); a.setAttribute('rel', 'noreferrer');
    a.textContent = b + ' +100';
    box.appendChild(a);
  });
  const SB = ['DK', 'MGM', 'BR', 'HR', 'TSB'];

  let r = visibleBooks(w, 'CA');
  check('CA: POLY chip renders', !!r.vis.POLY);
  check('CA: DKP chip renders', !!r.vis.DKP);
  check('CA: FDP chip renders', !!r.vis.FDP);
  check('CA: PM chips stay tappable anchors', ['POLY', 'DKP', 'FDP'].every(b => r.vis[b] && r.vis[b].tagName === 'A' && r.vis[b].getAttribute('href')));
  check('CA: sportsbook chips hidden', SB.every(b => !r.vis[b]));

  r = visibleBooks(w, '');
  check('unset: POLY chip renders', !!r.vis.POLY);
  check('unset: DKP chip renders', !!r.vis.DKP);
  check('unset: FDP chip renders', !!r.vis.FDP);
  check('unset: sportsbook chips hidden', SB.every(b => !r.vis[b]));

  r = visibleBooks(w, 'NJ');
  check('NJ: POLY chip renders (table includes POLY)', !!r.vis.POLY);
  check('NJ: DKP/FDP hidden (not in NJ set)', !r.vis.DKP && !r.vis.FDP);
  check('NJ: priced sportsbook arms render', SB.every(b => !!r.vis[b]));

  console.log(failures ? ('FAILURES: ' + failures) : 'ALL CHECKS PASSED');
  process.exit(failures ? 1 : 0);
}, 2000);
