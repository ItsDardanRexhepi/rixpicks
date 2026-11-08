#!/usr/bin/env node
/* Past Tickets display fixture (Oct 1 sweep, LS-15; Nov 8 History redesign).
   The History tab now renders each archived entry as a collapsed <details class="hp-tk"> card:
   sport chip, title, placed tag, result badge, legs with outcome classes, a plain-English why line
   from the stored reason, and a nested "Full record" with the verbatim provenance (placement note,
   removal stamp, source lines). Display rules under test (unchanged intent):
   - an archived leg never wears a relative day word (Today/Tonight/Tomorrow)
   - no 'Removed' stamp without a removal time; a stamp is only the time (the reason lives in the why line)
   - stored entries are only displayed differently, never rewritten
   - leg outcomes carry hit/miss/open classes; void renders as its own result state
   Pulls the real History script out of scripts/build_gh_page_v2.py (python3 evaluates the
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
check('History script found in the builder', script.length > 200, script.length);

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
  Date, JSON, String, Array, Object, Promise, Intl,
});
vm.runInContext(script, ctx);
setTimeout(() => {
  const h = box.innerHTML;
  // sorted newest first: t13 (Sep 30), t10 (Sep 28), t11 (undated -> "Earlier")
  const cards = h.split('<details class="hp-tk"').slice(1);
  check('three archived cards render', cards.length === 3, cards.length);
  check("archived legs drop 'Today'", !/\bToday\s+\d/.test(h), (h.match(/Today.{0,30}/) || [''])[0]);
  check("archived legs drop 'tonight'", !/tonight\s+\d/i.test(h));
  check("no relative day words anywhere in the archive view", !/\b(Today|Tonight|Tomorrow)\b/.test(h));
  const heads = [...h.matchAll(/hp-date">([^<]+)</g)].map(m => m[1]);
  check('three date headings, newest first, undated labelled Earlier', heads.length === 3 && /Sep 30/.test(heads[0]) && /Sep 28/.test(heads[1]) && heads[2] === 'Earlier', JSON.stringify(heads));
  check('void entry carries the void state', /data-result="void"/.test(cards[0] || '') && /hp-res void">VOID</.test(cards[0] || ''));
  check('stamp with a removal time reads Removed <time>', /Removed Sep 28, 4:44 AM PT</.test(cards[1] || ''), (cards[1] || '').slice(0, 300));
  check("no bare 'Removed' stamp on an entry without a removal time", !/Removed/.test(cards[2] || ''));
  check('reason renders as the plain-English why line', /Why it lost:<\/b> Game final</.test(cards[1] || ''));
  check('leg outcomes carry hit/miss classes', /class="miss"/.test(cards[1] || '') && /class="hit"/.test(cards[1] || ''));
  check('full record keeps the provenance nested', /hp-record"><summary>Full record</.test(cards[1] || ''));
  // Nov 8: suggested with no surviving placement record is unknown, not a factual not-placed
  check('placed filter attribute set (suggested without placement record = unknown)', /data-placed="unknown"/.test(h) && !/data-placed="not-placed"/.test(h));
  check('result filter bar carries live counts', /All <span class="hp-n">3</.test(bar.innerHTML) && /Lost <span class="hp-n">2</.test(bar.innerHTML) && /Void <span class="hp-n">1</.test(bar.innerHTML), bar.innerHTML.slice(0, 200));
  check('original leg times retained in Full record, relative day words stripped', /Kiki Iriafen 16\+ Points - 4:00 PM PT/.test(cards[1] || '') && /Puka Nacua Anytime TD - 5:20 PM PT/.test(cards[1] || ''), (cards[1] || '').match(/Original leg times[^<]*/));
  check('stored entries untouched', JSON.stringify(ENTRIES) === frozen);
  if (failures) { console.error(failures + ' FAILURES'); process.exit(1); }
  console.log('past tickets stamp fixture: ALL PASS');
}, 30);
