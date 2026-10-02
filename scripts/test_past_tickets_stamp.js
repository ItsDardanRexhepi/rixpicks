#!/usr/bin/env node
/* Past Tickets display fixture (Oct 1 sweep, LS-15).
   Archived Sep 27-28 legs rendered 'WAS @ ATL · Today 4:00 PM PT' on Oct 1, and two entries
   with no removed_label/archived_at rendered a bare 'Removed ·'. Display rules under test:
   - an archived leg never wears a relative day word (Today/Tonight/Tomorrow); the clock time stays
   - no 'Removed' stamp without a removal time; no dangling separator without a reason
   - stored entries are only displayed differently, never rewritten
   Pulls the real Past Tickets script out of scripts/build_gh_page_v2.py (python3 evaluates the
   past_entry literal) and runs it in a vm sandbox against a stub fetch. No DOM library needed.
   Run: node scripts/test_past_tickets_stamp.js */
'use strict';
const path = require('path'), vm = require('vm'), { execFileSync } = require('child_process');
const builder = process.argv[2] || path.join(__dirname, 'build_gh_page_v2.py');
const html = execFileSync('python3', ['-c', [
  'import ast,sys,textwrap',
  'src=open(sys.argv[1]).read()',
  'i=src.index("past_entry=(")',
  'o=src.rfind("PAST_HIDE_MONEY =",0,i)',  // the owner option, when present, sits just above the literal
  'i=o if o>=0 and i-o<400 else i',
  'i=src.rfind("\\n",0,i)+1',
  'ns={}',
  'exec(textwrap.dedent(src[i:].split("\\n    _tabs_html=")[0]),ns)',
  'print(ns["past_entry"])'].join('\n'), builder], { encoding: 'utf8' });
const script = (html.match(/<script>([\s\S]*?)<\/script>/) || [])[1] || '';

let failures = 0;
function check(label, cond, extra) {
  if (!cond) failures++;
  console.log((cond ? 'OK   ' : 'FAIL ') + label + (cond || extra === undefined ? '' : '  [' + extra + ']'));
}
check('Past Tickets script found in the builder', script.length > 200, script.length);

const ENTRIES = [
  { id: 't10', title: 'WNBA 3-leg idea', origin: 'suggested', result: 'lost', archived_at: '2026-09-28T04:44', removed_label: 'Sep 28, 4:44 AM PT', reason: 'Game final',
    legs: [{ player: 'Kiki Iriafen', market: '16+ Points', matchup: 'WAS @ ATL', time: 'Today 4:00 PM PT', status: 'lost' },
           { player: 'Puka Nacua', market: 'Anytime TD', matchup: 'LAR @ DEN', time: 'tonight 5:20 PM PT', status: 'won' }] },
  { id: 't11', title: '3-leg HR SGP idea', origin: 'suggested', result: 'lost',
    legs: [{ player: 'Kyle Schwarber', market: 'Home Run', matchup: 'PHI @ MIA', time: 'Sep 29, 2:00 PM PT', status: 'lost' }] },
  { id: 't13', title: '4-leg Strikeouts parlay', origin: 'suggested', result: 'void', archived_at: '2026-09-30T13:55', removed_label: 'Sep 30, 1:55 PM PT' },
];
const frozen = JSON.stringify(ENTRIES);
const box = { innerHTML: '' }, bar = { innerHTML: '', querySelectorAll: () => [] };
const ctx = vm.createContext({
  document: { getElementById: id => (id === 'rpPastBox' ? box : id === 'rpPastBar' ? bar : null) },
  fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({ entries: ENTRIES }) }),
  Date, JSON, String, Array, Object, Promise,
});
vm.runInContext(script, ctx);
setTimeout(() => {
  const h = box.innerHTML;
  const cards = h.split('border-radius:12px;padding:11px 12px').slice(1);
  check('three archived cards render', cards.length === 3, cards.length);
  check("archived legs drop 'Today'", !/&middot; Today\b/i.test(h) && /WAS @ ATL<\/span> <span style="color:#8a8f98">&middot; 4:00 PM PT</.test(h), (h.match(/WAS @ ATL.{0,60}/) || [''])[0]);
  check("archived legs drop 'tonight'", !/&middot; tonight\b/i.test(h) && /&middot; 5:20 PM PT/.test(h));
  check('absolute leg dates stay as written', /&middot; Sep 29, 2:00 PM PT/.test(h));
  check("no bare 'Removed' stamp on an entry without a removal time", !/Removed\s*(&middot;|<\/div>)/.test(h) && !/Removed \s*&middot;/.test(h));
  check('entry without removal time shows no Removed line', cards[1] && !/Removed/.test(cards[1]));
  check('stamp with time and reason reads Removed <time> &middot; <reason>', /Removed Sep 28, 4:44 AM PT &middot; Game final<\/div>/.test(h));
  check('stamp with time but no reason has no dangling separator', /Removed Sep 30, 1:55 PM PT<\/div>/.test(h));
  check('stored entries untouched', JSON.stringify(ENTRIES) === frozen);
  if (failures) { console.error(failures + ' FAILURES'); process.exit(1); }
  console.log('past tickets stamp fixture: ALL PASS');
}, 30);
