#!/usr/bin/env node
/* Standing regression fixture for two first-load classes (guard 1, 1:28 9/29 +
   rolled-dates phonemsg-01M3M8JV437ST9S8NV18WYAH66):
   A. A generation-stamped map fetched before the news/X generations exist must NOT be
      discarded - it promotes the moment both generations arrive (no ~45s blank wait).
   B. The baked .rpdate header rolls to the current PT day at midnight; yesterday's card
      never wears today's date.
   Extracts the real functions from scripts/index_v2.js and runs them in a vm sandbox.
   Run: node scripts/test_feed_boot_class.js  (wired into x_feed.yml) */
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const src = fs.readFileSync(process.argv[2] || path.join(__dirname, 'index_v2.js'), 'utf8');

function extract(name) {
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) { console.error('FAIL: ' + name + ' not found in index_v2.js'); process.exit(1); }
  let depth = 0;
  for (let i = start; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) return src.slice(start, i + 1); }
  }
  console.error('FAIL: unbalanced ' + name); process.exit(1);
}

let failures = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'OK   ' : 'FAIL ') + label + (ok ? '' : `  [want ${JSON.stringify(want)} got ${JSON.stringify(got)}]`));
}

const NOW = Date.now();
const G1 = '2026-09-29T08:20:12.265768+00:00', G2 = '2026-09-29T08:20:27+00:00';
const story = { headline: 'Kansas joins early Top 25', link: 'https://ex.com/k', published: G1, source: 'CBS' };
const map = {
  built_at: new Date(NOW - 60000).toISOString(),
  pairs: { 'https://ex.com/k': { verified: true, post_id: '900' } },
  news_generated_at: G1, x_generated_at: G2,
};
const xpayload = { generated_at: G2, items: [
  { id: '900', text: 'Kansas joins the early Top 25 And 1 after the court ruling #kansasjayhawks',
    created_at: G2, url: 'https://x.com/cbbcentral/status/900', author_name: 'CBB Central' },
] };

const rendered = [];
const ctx = vm.createContext({
  Date, JSON, Intl, RegExp, String, Number, Array, Object, isFinite, parseFloat, parseInt,
  NEWSF: null, XFEED_GEN: null,
  SOC_MATCH: null, SOC_MATCH_OK: false, SOC_MATCH_PENDING: null,
  SOC_XIDX: {}, XNEWS: [], PAIRS: [],
  renderNews: () => rendered.push('news'), renderSocial: () => rendered.push('social'),
  socSync: () => rendered.push('sync'),
  newsBucket: () => [story],
  carKey: a => a.link,
  isPublishablePost: p => !!p,
  document: { querySelector: () => null, getElementById: () => null },
});
vm.runInContext([
  extract('rpMapFresh'), extract('socMapRetry'), extract('ingestX'), extract('buildPairs'),
].join('\n'), ctx);

// A1: map fetched first, generations absent -> held, not promoted, not discarded
vm.runInContext(`if(rpMapFresh(MAP)){SOC_MATCH=MAP;SOC_MATCH_OK=true;}else{SOC_MATCH_PENDING=MAP;}`, Object.assign(ctx, { MAP: map }));
check('stamped map with no generations is held pending, not promoted', [ctx.SOC_MATCH_OK, !!ctx.SOC_MATCH_PENDING], [false, true]);

// A2: news generation arrives alone -> still no promote
vm.runInContext(`NEWSF={generated_at:G1};socMapRetry();`, Object.assign(ctx, { G1 }));
check('news-only arrival does not promote (X generation still missing)', ctx.SOC_MATCH_OK, false);

// A3: X generation arrives via ingestX -> promote + both carousels repaint once
vm.runInContext(`ingestX(XP);`, Object.assign(ctx, { XP: xpayload }));
check('map promotes the moment both generations exist', ctx.SOC_MATCH_OK, true);
check('promotion repaints the feeds', rendered.length >= 2, true);

// A4: promoted map pairs the story against the ingested post index
vm.runInContext(`buildPairs([STORY]);`, Object.assign(ctx, { STORY: story }));
check('coherent PAIRS unit publishes from the promoted map', ctx.PAIRS.length, 1);
check('paired post is the mapped post', ctx.PAIRS[0] && ctx.PAIRS[0].post.id, '900');

// B1: stale map (3h old) never promotes even with matching generations
const ctx2 = vm.createContext(Object.assign({}, ctx, {
  NEWSF: { generated_at: G1 }, XFEED_GEN: G2,
  SOC_MATCH: null, SOC_MATCH_OK: false, SOC_MATCH_PENDING: null,
  renderNews: () => {}, renderSocial: () => {}, socSync: () => {},
}));
vm.runInContext(`SOC_MATCH_PENDING=OLDMAP;socMapRetry();`,
  Object.assign(ctx2, { OLDMAP: Object.assign({}, map, { built_at: new Date(NOW - 3 * 3600 * 1000).toISOString() }) }));
check('stale held map fails closed', ctx2.SOC_MATCH_OK, false);

// B2: generation-mismatched held map never promotes
const ctx3 = vm.createContext(Object.assign({}, ctx, {
  NEWSF: { generated_at: '2026-09-29T09:55:00+00:00' }, XFEED_GEN: G2,
  SOC_MATCH: null, SOC_MATCH_OK: false, SOC_MATCH_PENDING: null,
  renderNews: () => {}, renderSocial: () => {}, socSync: () => {},
}));
vm.runInContext(`SOC_MATCH_PENDING=MAP;socMapRetry();`, Object.assign(ctx3, { MAP: map }));
check('generation-mismatched held map fails closed', ctx3.SOC_MATCH_OK, false);

// C: rolled dates - stale baked header rolls to current PT day with honest state
const ptToday = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Los_Angeles', weekday: 'long', month: 'short', day: 'numeric' }).format(new Date());
const el = { textContent: 'Monday, Sep 28' };
const stHome = { innerHTML: '<div class="pick rp-empty"><div class="pick-head"><span class="name">No picks today</span></div><div class="sub cnote">MNF Eagles @ Bears, 5:15 PM PT.</div></div>' };
const ctx4 = vm.createContext({
  Date, JSON, Intl,
  document: {
    querySelector: sel => (sel === '.rpdate' ? el : null),
    getElementById: id => (id === 'st-home' ? stHome : null),
  },
});
vm.runInContext(extract('rpDateRoll'), ctx4);
const before = el.textContent === ptToday ? 'same-day' : 'stale';
vm.runInContext('rpDateRoll();', ctx4);
if (before === 'stale') {
  check('stale header rolls to current PT day', el.textContent, ptToday);
  check('stale card replaced with honest not-published state', /has not published yet/.test(stHome.innerHTML), true);
  check('stale game note is gone', /MNF Eagles/.test(stHome.innerHTML), false);
} else {
  check('same-day header is a no-op', el.textContent, ptToday);
  check('same-day card area untouched', /MNF Eagles/.test(stHome.innerHTML), true);
}
// idempotence: second roll changes nothing
const h1 = el.textContent, s1 = stHome.innerHTML;
vm.runInContext('rpDateRoll();', ctx4);
check('second roll is a no-op', [el.textContent === h1, stHome.innerHTML === s1], [true, true]);

if (failures) { console.error(failures + ' FAILURES'); process.exit(1); }
console.log('feed boot + date-roll class fixture: ALL PASS');
