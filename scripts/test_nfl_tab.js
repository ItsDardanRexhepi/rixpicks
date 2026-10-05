/* NFL tab (Oct 5): shows ONLY on days with NFL content (card pick or dated non-empty slates/nfl_ideas.json).
   The synthetic tab link ships hidden; the hydrate script reveals it only for a valid today-dated file, and
   renders per-leg KAL/DKP chips converted cents->American, never a combined price.
   Run: node scripts/test_nfl_tab.js [index.html]   (exit 1 on any failure) */
'use strict';
const fs = require('fs'), vm = require('vm');
const file = process.argv[2] || 'index.html';
const html = fs.readFileSync(file, 'utf8');
let bad = 0;
const check = (l, ok, d) => { if (!ok) bad++; console.log((ok ? 'OK   ' : 'FAIL ') + l + (ok ? '' : '  [' + d + ']')); };
const hasPick = /data-tab="nfl"/.test(html) && !/id="rpNflTab"/.test(html);
const tabM = html.match(/<a class="tab"[^>]*id="rpNflTab"[^>]*>/);
check('NFL tab link present exactly once', (html.match(/data-tab="nfl"/g) || []).length === 1, (html.match(/data-tab="nfl"/g) || []).length);
if (tabM) check('synthetic NFL tab ships hidden (display:none) until content is verified', /display:none/.test(tabM[0]), tabM[0]);
const i = html.indexOf('id="rpNflIdeas"'); check('ideas container present', i > 0, 'missing');
const j = html.indexOf('<script>', i), k = html.indexOf('</script>', j);
const src = html.slice(j + 8, k);
function run(data, now) {
  const box = { innerHTML: '' }, tab = { style: { display: 'none' } };
  const doc = { getElementById: id => id === 'rpNflIdeas' ? box : id === 'rpNflTab' ? tab : null };
  const D = class extends Date { toLocaleDateString() { return now; } };
  const ctx = { document: doc, Date: D, Math, String, Array, fetch: () => Promise.resolve({ ok: !!data, json: () => Promise.resolve(data) }) };
  vm.createContext(ctx); vm.runInContext(src, ctx);
  return new Promise(r => setTimeout(() => r({ box, tab }), 30));
}
const leg = { player: 'Juwan Johnson', market: 'Anytime touchdown', links: [{ venue: 'KAL', cents: 27 }, { venue: 'DKP', cents: 29 }, { venue: 'FD', cents: 50 }] };
const good = { date: '2026-10-05', cards: [{ title: 'T', legs: [leg, { player: 'X', market: 'm', links: [], unlisted: ['Kalshi'] }] }] };
(async () => {
  let r = await run(good, '2026-10-05');
  check('valid today file reveals the tab', r.tab.style.display === '', r.tab.style.display);
  check('KAL 27c renders +270, DKP 29c renders +245', /KAL \+270/.test(r.box.innerHTML) && /DKP \+245/.test(r.box.innerHTML), r.box.innerHTML.slice(0, 200));
  check('sportsbook venue (FD) chip is dropped', !/FD /.test(r.box.innerHTML), 'FD chip');
  check('unlisted note renders and no NOT PLACED badge', !/NOT PLACED/.test(r.box.innerHTML) && /Not listed on Kalshi/.test(r.box.innerHTML), 'labels');
  check('no combined price text', !/parlay|combined odds|payout|stake/i.test(r.box.innerHTML), 'combo text');
  r = await run(good, '2026-10-06'); check('wrong-date file keeps the tab hidden', r.tab.style.display === 'none', r.tab.style.display);
  r = await run({ date: '2026-10-05', cards: [] }, '2026-10-05'); check('empty file keeps the tab hidden', r.tab.style.display === 'none', r.tab.style.display);
  r = await run(null, '2026-10-05'); check('missing file keeps the tab hidden', r.tab.style.display === 'none', r.tab.style.display);
  if (bad) { console.log('\nFAILED ' + bad); process.exit(1); }
  console.log('\nall checks passed');
})();
