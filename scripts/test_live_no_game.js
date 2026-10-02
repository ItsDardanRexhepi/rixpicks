#!/usr/bin/env node
/* live.html no-game fixture (Oct 1 sweep, LS-19).
   Opened without a game (no eid / bad league) the page said 'No game specified.' while GAME VIEW,
   SCORING, TEAM STATS and WIN CHANCE spun 'Loading...' forever and the footer claimed it polls
   every 2s. With no game, every live panel, its heading and the polling footer must be hidden;
   with a valid game nothing is hidden.
   Runs the page's own inline script in a vm sandbox against a minimal element model built from
   live.html's static markup (no DOM library needed).
   Run: node scripts/test_live_no_game.js */
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const page = fs.readFileSync(process.argv[2] || path.join(__dirname, '..', 'live.html'), 'utf8');

let failures = 0;
function check(label, cond, extra) {
  if (!cond) failures++;
  console.log((cond ? 'OK   ' : 'FAIL ') + label + (cond || extra === undefined ? '' : '  [' + extra + ']'));
}
const body = page.slice(page.indexOf('<div class="wrap">'), page.indexOf('<script>'));
const script = (page.match(/<script>([\s\S]*?)<\/script>/) || [])[1] || '';

function run(search) {
  const els = [];
  const tagRe = /<(div|a|span)\b([^>]*)>/g; let m;
  while ((m = tagRe.exec(body))) {
    const attrs = m[2];
    const id = (attrs.match(/\bid="([^"]+)"/) || [])[1] || '';
    const cls = ((attrs.match(/\bclass="([^"]+)"/) || [])[1] || '').split(/\s+/).filter(Boolean);
    const hidden = /style="[^"]*display:none/.test(attrs);
    els.push({ tag: m[1], id, cls, style: { display: hidden ? 'none' : '' }, innerHTML: '', textContent: '', href: '' });
  }
  const match = (e, sel) => sel.split(',').map(s => s.trim()).some(s => (s[0] === '#' ? e.id === s.slice(1) : (s[0] === '.' ? e.cls.includes(s.slice(1)) : false)));
  const document = {
    getElementById: id => els.find(e => e.id === id) || null,
    querySelectorAll: sel => els.filter(e => match(e, sel)),
    querySelector: sel => els.find(e => match(e, sel)) || null,
    createElement: () => ({ style: {}, appendChild() {}, setAttribute() {} }),
    addEventListener() {}, hidden: false,
  };
  const ctx = vm.createContext({
    document, location: { search, href: 'https://rix-picks.com/live.html' + search }, URLSearchParams,
    fetch: () => new Promise(() => {}), setInterval: () => 0, setTimeout: () => 0, clearInterval() {}, clearTimeout() {},
    Date, JSON, Math, String, Number, Array, Object, RegExp, parseInt, parseFloat, isFinite, encodeURIComponent, Intl, Promise,
    console, window: {},
  });
  ctx.window = ctx;
  let err = '';
  try { vm.runInContext(script, ctx); } catch (e) { err = e.message; }
  return { els, err, byId: id => els.find(e => e.id === id) };
}

const PANELS = ['rpField', 'rpScoreTbl', 'rpPlays', 'rpStats', 'rpGraph'];
for (const [label, q] of [['no params', ''], ['league but no eid', '?espn=football/nfl'], ['bad eid', '?espn=football/nfl&eid=abc'], ['unknown league', '?espn=foo/bar&eid=401872964']]) {
  const r = run(q);
  check(label + ': page script runs', !r.err, r.err);
  check(label + ': says no game specified', /No game specified/.test(r.byId('rpScore').innerHTML));
  const shown = PANELS.filter(id => r.byId(id).style.display !== 'none');
  check(label + ': every live panel hidden', shown.length === 0, shown.join(','));
  const heads = r.els.filter(e => e.cls.includes('sect') && e.style.display !== 'none');
  check(label + ': no orphan section headings', heads.length === 0, heads.length);
  const foot = r.els.find(e => e.cls.includes('foot'));
  check(label + ": no 'page polls every 2s' footer", foot && foot.style.display === 'none');
}
const ok = run('?espn=football/nfl&eid=401872964');
check('valid game: page script runs', !ok.err, ok.err);
check('valid game: live panels stay visible', PANELS.every(id => ok.byId(id).style.display !== 'none'));
check('valid game: footer stays visible', ok.els.find(e => e.cls.includes('foot')).style.display !== 'none');

if (failures) { console.error(failures + ' FAILURES'); process.exit(1); }
console.log('live no-game fixture: ALL PASS');
