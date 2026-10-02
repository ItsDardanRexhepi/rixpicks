#!/usr/bin/env node
/* Home Yesterday line at VIEW time (r3 review A1).
   The builder bakes the Home line for the build's PT yesterday (data-ydate) with the card dates that
   carried official picks and have no graded row (data-pending: manifests/ snapshots by the builder's
   date rule, plus the live card). A viewer on a later PT day saw that older line. rpYesterdayLine in
   index_v2.js recomputes it for the viewer's own PT yesterday from same-origin history.json:
     - a graded row: '<record> · <pick> <result> ...', linking yesterday.html while that page carries
       the day (its last two graded days), else the full record;
     - no row, and the date is a pending card date or the live manifest.json is that date's card (the
       builder's rule: most common PT date across its picks): 'results pending';
     - otherwise '0-0 - no official picks';
     - history.json unreadable: the line is hidden (no claim about another day).
   The viewer's own day matching data-ydate leaves the baked line alone (nothing fetched).
   Extracts the real functions from scripts/index_v2.js and runs them with a fake DOM, fetch and clock.
   Run: node scripts/test_home_yesterday_view.js */
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const src = fs.readFileSync(process.argv[2] || path.join(__dirname, 'index_v2.js'), 'utf8');
let failures = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  console.log((ok ? 'OK   ' : 'FAIL ') + label + (ok ? '' : ` (got ${JSON.stringify(got)}, want ${JSON.stringify(want)})`));
  if (!ok) failures++;
}
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
const code = extract('rpCardDate') + '\n' + extract('rpYesterdayLine');
check('index_v2.js carries rpYesterdayLine and rpCardDate', !!extract('rpYesterdayLine') && !!extract('rpCardDate'), true);
check('index_v2.js runs rpYesterdayLine on load', /\nrpYesterdayLine\(\);/.test(src), true);
const flush = () => new Promise(r => setImmediate(r));
function clockAt(iso) {
  const now = Date.parse(iso);
  return class FakeDate extends Date { constructor(...a) { if (a.length) super(...a); else super(now); } static now() { return now; } };
}
const row = (date, label, record, picks) => ({ date, label, record, units: '+0.00u', brief: '', picks: picks.map(([name, result]) => ({ name, result })) });
const HIST = { days: [row('2026-09-29', 'Tuesday, Sep 29', '2-3', [['Braves ML', 'W'], ['Maple Leafs ML', 'L']]),
                      row('2026-09-30', 'Wednesday, Sep 30', '1-0', [['White Sox ML', 'W']])] };
async function view({ at, ydate = '2026-10-01', pending = '2026-10-01 2026-10-02', text = 'Yesterday: results pending', history = HIST, manifest = null }) {
  const a = { attrs: { class: 'yesrec home-yes', href: 'record.html', 'data-ydate': ydate, 'data-pending': pending }, textContent: text, style: {},
    getAttribute(k) { return this.attrs[k] == null ? null : this.attrs[k]; }, setAttribute(k, v) { this.attrs[k] = String(v); } };
  const asked = [];
  const document = { querySelector: s => (s === '.home-yes' ? a : null) };
  const fetch = url => {
    const f = url.split('?')[0]; asked.push(f);
    const body = f === 'history.json' ? history : f === 'manifest.json' ? manifest : undefined;
    return body == null ? Promise.reject(new Error('offline')) : Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(JSON.stringify(body))) });
  };
  vm.runInContext(code + '\nrpYesterdayLine();', vm.createContext({ document, fetch, Date: clockAt(at), Intl, Promise, String, Array, isNaN }));
  for (let i = 0; i < 5; i++) await flush();
  return { text: a.textContent, href: a.attrs.href, hidden: a.style.display === 'none', ydate: a.attrs['data-ydate'], asked: asked.sort() };
}

(async () => {
  // built Oct 2 (line for Oct 1), viewed Oct 2 PT: the baked line stands, nothing fetched
  check('viewer on the build\'s own PT day: baked line kept, nothing fetched', await view({ at: '2026-10-02T19:00:00Z' }),
    { text: 'Yesterday: results pending', href: 'record.html', hidden: false, ydate: '2026-10-01', asked: [] });
  // viewed Oct 3 PT: Oct 2 is a pending card date (carded, no row)
  check('viewer on Oct 3 PT, Oct 2 carded and ungraded: results pending', await view({ at: '2026-10-03T17:00:00Z' }),
    { text: 'Yesterday: results pending', href: 'record.html', hidden: false, ydate: '2026-10-02', asked: ['history.json', 'manifest.json'] });
  // viewed Oct 3 PT: Oct 2 not carded at build time, and the live card is Oct 3's
  check('viewer on Oct 3 PT, no Oct 2 card: 0-0 - no official picks', await view({ at: '2026-10-03T17:00:00Z', pending: '2026-10-01',
    manifest: { date: '2026-10-03', picks: [{ name: 'Rangers ML', game: { commence: '2026-10-03T23:00Z' } }] } }),
    { text: 'Yesterday: 0-0 - no official picks', href: 'record.html', hidden: false, ydate: '2026-10-02', asked: ['history.json', 'manifest.json'] });
  // the live card is Oct 2's by its picks (posted after the build; one game after PT midnight)
  check('viewer on Oct 3 PT, the live card is the Oct 2 card by its picks: results pending', await view({ at: '2026-10-03T17:00:00Z', pending: '',
    manifest: { date: '2026-10-03', picks: [{ name: 'Devils ML', game: { commence: '2026-10-03T00:00Z' } }, { name: 'Kings ML', game: { commence: '2026-10-03T02:30Z' } },
                                            { name: 'Sharks ML', game: { commence: '2026-10-03T07:30Z' } }] } }),
    { text: 'Yesterday: results pending', href: 'record.html', hidden: false, ydate: '2026-10-02', asked: ['history.json', 'manifest.json'] });
  // a preview card is no official card
  check('viewer on Oct 3 PT, the live card is an Oct 2 preview: 0-0', await view({ at: '2026-10-03T17:00:00Z', pending: '',
    manifest: { date: '2026-10-02', preview: true, picks: [{ name: 'Devils ML', game: { commence: '2026-10-02T23:00Z' } }] } }),
    { text: 'Yesterday: 0-0 - no official picks', href: 'record.html', hidden: false, ydate: '2026-10-02', asked: ['history.json', 'manifest.json'] });
  // graded since the build: the row's record and picks; yesterday.html carries its last two graded days
  const H2 = { days: HIST.days.concat([row('2026-10-02', 'Friday, Oct 2', '1-1', [['Devils ML', 'W'], ['Under 38.5', 'L']])]) };
  check('viewer on Oct 3 PT, Oct 2 graded: the row, linking yesterday.html', await view({ at: '2026-10-03T17:00:00Z', history: H2 }),
    { text: 'Yesterday: 1-1 · Devils ML W · Under 38.5 L', href: 'yesterday.html', hidden: false, ydate: '2026-10-02', asked: ['history.json', 'manifest.json'] });
  // a graded row older than yesterday.html's two days links the full record
  const H3 = { days: [row('2026-09-28', 'Monday, Sep 28', '1-0', [['Lions ML', 'W']])].concat(HIST.days) };
  check('viewer on Sep 29 PT (built Sep 28), Sep 28 graded but not on yesterday.html: links the full record',
    await view({ at: '2026-09-29T17:00:00Z', ydate: '2026-09-27', history: H3 }),
    { text: 'Yesterday: 1-0 · Lions ML W', href: 'record.html', hidden: false, ydate: '2026-09-28', asked: ['history.json', 'manifest.json'] });
  // history.json unreadable: the line about another day is hidden, never left standing
  check('viewer on Oct 3 PT, history.json unreadable: the stale line is hidden', await view({ at: '2026-10-03T17:00:00Z', history: null }),
    { text: 'Yesterday: results pending', href: 'record.html', hidden: true, ydate: '2026-10-01', asked: ['history.json', 'manifest.json'] });
  // a line without an ISO date (an older build) is left alone
  check('a line without data-ydate is left alone', await view({ at: '2026-10-03T17:00:00Z', ydate: null }),
    { text: 'Yesterday: results pending', href: 'record.html', hidden: false, ydate: null, asked: [] });

  console.log(failures ? 'FAILURES: ' + failures : 'ALL CHECKS PASS');
  process.exit(failures ? 1 : 0);
})();
