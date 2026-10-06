#!/usr/bin/env node
/* Late-post disclosure in the record page's live Today section (record_today.js): a pick posted
   after its game began says 'Added after the final' (game already over at posting) or 'Added after
   kickoff' - from the card itself while it is live, and from its chain-written history row (which
   record_final.py now carries the flags onto). Only a JSON true counts; other picks show nothing.
   Offline: fake DOM, fetch and clock. Bite-proof: red on the pre-fix record_today.js.
   Run: node scripts/test_late_disclosure_today.js */
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
let failures = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  console.log((ok ? 'OK   ' : 'FAIL ') + label + (ok ? '' : ` (got ${JSON.stringify(got)}, want ${JSON.stringify(want)})`));
  if (!ok) failures++;
}
const flush = () => new Promise(r => setImmediate(r));
function el(tag) {
  return { tag, className: '', textContent: '', children: [], style: {}, attrs: {}, hidden: false,
    appendChild(c) { this.children.push(c); return c; }, setAttribute(k, v) { this.attrs[k] = v; },
    getAttribute(k) { return this.attrs[k] == null ? null : this.attrs[k]; },
    replaceChildren(...c) { this.children = c; } };
}
function clockAt(iso) {
  const c = { now: Date.parse(iso) };
  class FakeDate extends Date {
    constructor(...a) { if (a.length) super(...a); else super(c.now); }
    static now() { return c.now; }
  }
  c.Date = FakeDate;
  return c;
}
const SRC = fs.readFileSync(path.join(__dirname, 'record_today.js'), 'utf8');
function run(manifest, history) {
  const clock = clockAt('2026-10-03T03:00:00Z'), mount = el('section');
  const files = { 'manifest.json': manifest, 'history.json': history };
  const document = { hidden: false, getElementById: id => (id === 'rpToday' ? mount : null),
    createDocumentFragment: () => el('#frag'), createElement: el, querySelectorAll: () => [], addEventListener() {} };
  const fetch = url => {
    const f = url.split('?')[0];
    if (!(f in files)) return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve(null) });
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(JSON.stringify(files[f]))) });
  };
  vm.runInContext(SRC, vm.createContext({ document, fetch, Date: clock.Date, Intl, setInterval() {}, console }));
  return mount;
}
// the painted pick boxes: name -> the .late text under it ('' when none)
function lateByPick(mount) {
  const frag = mount.children[0] || { children: [] }, out = {};
  for (const box of frag.children || []) {
    if (box.className !== 'pk') continue;
    const top = box.children[0] || { children: [] }, nm = (top.children[1] || {}).textContent;
    const late = (box.children || []).filter(c => c.className === 'late').map(c => c.textContent);
    out[nm] = late.join('|');
  }
  return out;
}
const tot = (name, eid, side, odds, extra) => Object.assign({ name, market_class: 'total', market: 'total', side, line: 3.5, odds,
  card_american: Number(odds), units: '5u', espn_league: 'soccer/usa.nwsl', league: 'NWSL',
  game: { eid, away: 'San Diego Wave FC', home: 'Orlando Pride', commence: '2026-10-03T00:00Z' } }, extra || {});
const CARD = { date: '2026-10-02', picks: [
  tot('Under 6.5', '401890001', 'under', '-133'),
  tot('Under 3.5', '401854015', 'under', '-170', { added_after_kickoff: true, added_after_final: true }),
  tot('Over 43.5', '401858476', 'over', '-138', { added_after_kickoff: true }),
  tot('Under 54.5', '401858245', 'under', '-104', { added_after_kickoff: 'true' })] };
const NO_ROWS = { days: [] };

(async () => {
  // 1. live, ungraded: the card's own flags
  let m = run(CARD, NO_ROWS); await flush();
  let late = lateByPick(m);
  check('card flags: Under 3.5 says Added after the final', late['Under 3.5'], 'Added after the final');
  check('card flags: Over 43.5 says Added after kickoff', late['Over 43.5'], 'Added after kickoff');
  check('card flags: Under 6.5 (pre-game) says nothing', late['Under 6.5'], '');
  check('card flags: a string "true" is no disclosure', late['Under 54.5'], '');
  // 2. graded: the chain-written row's flags count even when the card copy carries none
  const bare = JSON.parse(JSON.stringify(CARD));
  bare.picks.forEach(p => { delete p.added_after_kickoff; delete p.added_after_final; });
  const row = (name, extra) => Object.assign({ name, result: 'W', score: 'SD 2, ORL 1', _delta: '1' }, extra || {});
  const HIST = { days: [{ date: '2026-10-02', label: 'Friday, Oct 2', record: '3-0', units: '+3.00u', brief: '', picks: [
    row('Under 6.5'), row('Under 3.5', { added_after_kickoff: true, added_after_final: true }), row('Over 43.5', { added_after_kickoff: true })] }] };
  m = run(bare, HIST); await flush();
  late = lateByPick(m);
  check('row flags: Under 3.5 says Added after the final', late['Under 3.5'], 'Added after the final');
  check('row flags: Over 43.5 says Added after kickoff', late['Over 43.5'], 'Added after kickoff');
  check('row flags: Under 6.5 says nothing', late['Under 6.5'], '');
  console.log(failures ? 'FAILURES: ' + failures : 'ALL OK');
  process.exit(failures ? 1 : 0);
})();
