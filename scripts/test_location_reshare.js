#!/usr/bin/env node
/* Location re-share fixture (owner, Oct 13: "geolocation isn't working after a user clears their
   cookies, they can re-share their location"). Drives the REAL rpRoute / rpAsk / rpShareLoc /
   rpResolveState of the built page in a jsdom window with a stub geolocation + permissions API and
   a stub reverse-geocode fetch, the way a visitor's browser would:
   A. a first visitor taps a market chip: the prompt opens, the browser asks for location, the
      shared state is stored and the chip opens;
   B. the visitor shared earlier, then cleared the site data (storage empty, permission back to
      "prompt"): the next tap asks again and stores the state again;
   C. the browser refuses storage outright (Safari with cookies blocked throws on localStorage):
      before the fix rpRoute threw on its first line - the tap went dead with no prompt at all;
      now the tap prompts, the share goes through and the chip opens, with the state kept in memory;
   D. the visitor denied the browser prompt: the note says where to turn location on; tapping
      Share my location again asks again;
   E. the site data is cleared while the page sits in another tab: on return the footer label and
      the chips follow storage again, so the next tap asks instead of trusting a stale state.
   jsdom is not vendored: the fixture resolves it from NODE_PATH, the repo, or /tmp/node_modules
   (the x-feed workflow installs jsdom@30.1.1 before running it).
   Run: node scripts/test_location_reshare.js [index.html]   (default: the built ../index.html) */
'use strict';
const fs = require('fs'), path = require('path');
let JSDOM;
try { ({ JSDOM } = require('jsdom')); } catch (e) { ({ JSDOM } = require('/tmp/node_modules/jsdom')); }
const html = fs.readFileSync(process.argv[2] ? path.resolve(process.argv[2]) : path.join(__dirname, '..', 'index.html'), 'utf8');
let failures = 0;
function check(label, ok, extra) { if (!ok) failures++; console.log((ok ? 'OK   ' : 'FAIL ') + label + (ok || extra === undefined ? '' : '  [' + extra + ']')); }
const wait = ms => new Promise(r => setTimeout(r, ms));

function load(setup) {
  const st = { geo: 0, opened: 0, errors: [] };
  const dom = new JSDOM(html, {
    runScripts: 'dangerously', pretendToBeVisual: true, url: 'https://rix-picks.com/',
    beforeParse(w) {
      w.fetch = u => /reverse-geocode/.test(String(u))
        ? Promise.resolve({ json: () => Promise.resolve({ principalSubdivisionCode: 'US-' + (setup.state || 'NJ') }) })
        : new Promise(() => {});
      w.matchMedia = w.matchMedia || (() => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }));
      w.scrollTo = () => {}; w.open = () => { st.opened++; return null; };
      w.IntersectionObserver = class { observe() {} disconnect() {} unobserve() {} };
      Object.defineProperty(w.navigator, 'geolocation', { configurable: true, value: { getCurrentPosition(ok, err) {
        st.geo++; if (setup.deny) { if (err) err({ code: 1, message: 'User denied Geolocation' }); } else ok({ coords: { latitude: 40.7, longitude: -74.0 } }); } } });
      Object.defineProperty(w.navigator, 'permissions', { configurable: true, value: { query: () => Promise.resolve({ state: setup.perm || 'prompt' }) } });
      if (setup.blockStorage) Object.defineProperty(w, 'localStorage', { configurable: true, get() { throw new w.DOMException('The operation is insecure.', 'SecurityError'); } });
      w.addEventListener('error', e => st.errors.push(String(e.message || e.error).slice(0, 120)));
    }
  });
  st.w = dom.window; st.d = dom.window.document; return st;
}
function chip(st) {  // a prediction-market chip in the builder's emission shape (the fail-closed set is tappable in every state)
  const d = st.d, box = d.querySelector('.pick .chips') || d.querySelector('.pick') || d.querySelector('main') || d.body;
  const a = d.createElement('a'); a.className = 'chip'; a.setAttribute('data-book', 'POLY');
  a.setAttribute('href', 'https://example.com/poly/market/1'); a.setAttribute('data-sb', 'https://example.com/poly/market/1');
  a.setAttribute('onclick', 'return rpRoute(event,this)'); a.setAttribute('target', '_blank'); a.textContent = 'POLY 55c';
  box.appendChild(a); return a;
}
function tap(st, a) { try { a.dispatchEvent(new st.w.MouseEvent('click', { bubbles: true, cancelable: true })); return null; } catch (e) { return e.message; } }
const stored = st => { try { return st.w.localStorage.getItem('rp_state'); } catch (e) { return null; } };
const label = st => st.d.getElementById('rpStateLabel').textContent;
const modal = st => st.d.getElementById('rpModal').style.display;
const note = st => st.d.getElementById('rpGeoNote').textContent;

(async () => {
  let st = load({});
  await wait(300);
  check('page exposes rpRoute / rpShareLoc / rpFreshState', ['rpRoute', 'rpShareLoc', 'rpFreshState', 'rpResolveState'].every(f => typeof st.w[f] === 'function'));
  // A
  let a = chip(st), g0 = st.geo; tap(st, a); await wait(150);
  check('A first visitor: the tap asks the browser for location', st.geo === g0 + 1, st.geo - g0);
  check('A first visitor: the shared state is stored', stored(st) === 'NJ', stored(st));
  check('A first visitor: the chip opens after the share', st.opened === 1 && modal(st) === 'none', st.opened + ' ' + modal(st));
  check('A first visitor: the footer shows the verified state', /NJ \(verified\)/.test(label(st)), label(st));
  // B: site data cleared (storage empty, permission back to prompt), page reloaded
  st = load({ perm: 'prompt' }); st.w.localStorage.clear(); await wait(300);
  check('B after clearing site data: nothing stored, the footer asks to share', stored(st) === null && /Share\/update location/.test(label(st)), label(st));
  a = chip(st); g0 = st.geo; const errB = tap(st, a); await wait(150);
  check('B after clearing site data: the tap asks for location again', errB === null && st.geo === g0 + 1, errB || (st.geo - g0));
  check('B after clearing site data: the state is stored again and the chip opens', stored(st) === 'NJ' && st.opened === 1, stored(st) + ' ' + st.opened);
  // C: storage refused (Safari, cookies blocked)
  st = load({ blockStorage: true }); await wait(300);
  check('C storage blocked: the page still boots (no uncaught error)', st.errors.length === 0, st.errors.join(' | '));
  a = chip(st); g0 = st.geo; const errC = tap(st, a); await wait(150);
  check('C storage blocked: the tap still asks for location (no dead tap, no thrown error)', errC === null && st.errors.length === 0 && st.geo === g0 + 1, (errC || st.errors.join(' | ')) + ' geo=' + (st.geo - g0));
  check('C storage blocked: the share closes the prompt and opens the chip', modal(st) === 'none' && st.opened === 1, modal(st) + ' ' + st.opened);
  check('C storage blocked: the state is kept in memory for this page', st.w.rpFreshState() === 'NJ' && /NJ \(verified\)/.test(label(st)), st.w.rpFreshState() + ' ' + label(st));
  // D: denied, then asks again
  st = load({ deny: true }); await wait(300);
  a = chip(st); g0 = st.geo; tap(st, a); await wait(150);
  check('D denied: the prompt stays open with a note that says where to turn location on', modal(st) === 'flex' && /turn it on/i.test(note(st)), modal(st) + ' ' + note(st));
  check('D denied: nothing is stored and the chip did not open', stored(st) === null && st.opened === 0);
  st.w.rpShareLoc(); await wait(50);
  check('D denied: Share my location asks the browser again', st.geo === g0 + 2, st.geo - g0);
  // E: shared, then the site data is cleared while the page sits in the background
  st = load({ perm: 'granted' }); await wait(300);
  a = chip(st); tap(st, a); await wait(150);
  check('E shared: verified state in the footer', /NJ \(verified\)/.test(label(st)), label(st));
  st.w.localStorage.clear();
  Object.defineProperty(st.d, 'hidden', { configurable: true, get: () => false });
  st.d.dispatchEvent(new st.w.Event('visibilitychange'));
  await wait(50);
  check('E site data cleared in the background: on return the footer asks to share again', /Share\/update location/.test(label(st)), label(st));
  g0 = st.geo; tap(st, a); await wait(150);
  check('E site data cleared in the background: the next tap asks for location again', st.geo === g0 + 1, st.geo - g0);

  console.log(failures ? 'FAILURES: ' + failures : 'location re-share fixture: ALL PASS');
  process.exit(failures ? 1 : 0);
})();
