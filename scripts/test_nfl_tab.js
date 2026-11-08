/* NFL tab (Nov 8 Wooder Ice redesign): the NFL tab is now a full page - picks day-state, futures table
   with a single pricing fine line, weekly slate and the Wooder Ice top-5 ideas list - so the tab always
   shows; the old synthetic "hidden until a dated ideas file" gate is retired. The legacy NFL-ideas module
   no longer mounts on the NFL tab; its chip code (cents->American, venue filter, never a combined price)
   ships as the Wooder Ice batch twin (rpBatchIdeas) and is exercised here against that twin.
   Run: node scripts/test_nfl_tab.js [index.html]   (exit 1 on any failure) */
'use strict';
const fs = require('fs'), vm = require('vm');
const file = process.argv[2] || 'index.html';
const html = fs.readFileSync(file, 'utf8');
let bad = 0;
const check = (l, ok, d) => { if (!ok) bad++; console.log((ok ? 'OK   ' : 'FAIL ') + l + (ok ? '' : '  [' + d + ']')); };
check('NFL tab link present exactly once', (html.match(/data-tab="nfl"/g) || []).length === 1, (html.match(/data-tab="nfl"/g) || []).length);
const tabM = html.match(/<a class="tab"[^>]*data-tab="nfl"[^>]*>/);
if (tabM) check('NFL tab ships visible (full page even on off days)', !/display\s*:\s*none/.test(tabM[0]), tabM[0]);
check('picks day-state section present', html.includes('id="rpNflPicks"'), 'rpNflPicks');
check('off-day panel present', html.includes('No NFL card today'), 'offday');
check('futures table body present', html.includes('id="rpNflFutBody"'), 'rpNflFutBody');
check('single pricing fine line element present', html.includes('id="rpNflFutFine"'), 'rpNflFutFine');
check('weekly slate mount present', html.includes('id="rpNflSlate"'), 'rpNflSlate');
check('Wooder Ice top-5 ideas mount present', html.includes('id="rpNflWi"'), 'rpNflWi');
check('legacy NFL-ideas module no longer on the page', !html.includes('id="rpNflIdeas"'), 'rpNflIdeas still present');

// Chip conversion safety, exercised on the Wooder batch twin of the retired module.
const i = html.indexOf('id="rpBatchIdeas"'); check('Wooder batch ideas container present', i > 0, 'missing');
const j = html.indexOf('<script>', i), k = html.indexOf('</script>', j);
const src = html.slice(j + 8, k);
function run(data) {
  const box = { innerHTML: '' };
  const doc = { getElementById: id => id === 'rpBatchIdeas' ? box : null };
  const ctx = { document: doc, Date, Math, String, Array, fetch: () => Promise.resolve({ ok: !!data, json: () => Promise.resolve(data) }) };
  vm.createContext(ctx); vm.runInContext(src, ctx);
  return new Promise(r => setTimeout(() => r({ box }), 30));
}
const today = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Los_Angeles' });
const leg = { player: 'Juwan Johnson', market: 'Anytime touchdown', links: [{ venue: 'KAL', cents: 27 }, { venue: 'DKP', cents: 29 }, { venue: 'FD', cents: 50 }] };
const good = { date: today, cards: [{ title: 'T', legs: [leg, { player: 'X', market: 'm', links: [], unlisted: ['Kalshi'] }] }] };
(async () => {
  const r = await run(good);
  check('KAL 27c renders +270, DKP 29c renders +245', /KAL \+270/.test(r.box.innerHTML) && /DKP \+245/.test(r.box.innerHTML), r.box.innerHTML.slice(0, 200));
  check('sportsbook venue (FD) chip is dropped', !/FD /.test(r.box.innerHTML), 'FD chip');
  check('unlisted note renders and no NOT PLACED badge', !/NOT PLACED/.test(r.box.innerHTML) && /Not listed on Kalshi/.test(r.box.innerHTML), 'labels');
  check('no combined price text', !/parlay|combined odds|payout|stake/i.test(r.box.innerHTML), 'combo text');
  if (bad) { console.log('\nFAILED ' + bad); process.exit(1); }
  console.log('\nall checks passed');
})();
