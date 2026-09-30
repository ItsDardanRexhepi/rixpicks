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
// zeroPairSocial gates through isSportsPost (feed guard 3, commit 4): the vm sandbox needs
// the real classifier and its RP_ constants, same extraction as test_social_sports_gate.js.
const rpVars = src.split('\n').filter(l => /^var (RP_AD_KW|RP_TOUT_KW|RP_OPERATOR|RP_NONSPORT_KILL|RP_SPORT_ACRO|RP_SPORT_STRONG|RP_SPORT_TEAMS|RP_SPORT_WEAK)=/.test(l) && /;\s*$/.test(l));
if (rpVars.length !== 8) { console.error('FAIL: expected 8 RP_ vars, got ' + rpVars.length); process.exit(1); }

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
  SOC_XIDX: {}, XNEWS: [], PAIRS: [], FEED_FALLBACK: false, SYNC_LAST: false, SOC_N: 0, CAR_N: 0, CAR_LAST: [], CAR_IDX: 0, SOC_IDX: 0,
  renderNews: () => rendered.push('news'), renderSocial: () => rendered.push('social'),
  socSync: () => rendered.push('sync'),
  newsBucket: () => [story],
  carKey: a => a.link,
  isPublishablePost: p => !!p,
  document: { querySelector: () => null, getElementById: () => null },
});
vm.runInContext(rpVars.join('\n') + '\n' + [
  extract('rpMapFresh'), extract('socMapRetry'), extract('ingestX'), extract('buildPairs'),
extract('isSportsPost'), extract('zeroPairSocial'), extract('rpComboFresh')].join('\n'), ctx);
vm.runInContext(extract('socSync').replace('function socSync(', 'function socSyncReal('), ctx);

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

// C: zero-pair mode = independent feeds, never positional pairing
vm.runInContext(`XNEWS=[{id:'p1'},{id:'p2'},{id:'p1'},{id:'p3'}];var ZS=zeroPairSocial(12);`, ctx);
check('zero-pair social shows latest distinct publishable posts', vm.runInContext(`ZS.map(p=>p.post.id).join(',')`, ctx), 'p1,p2,p3');
check('fallback slides carry only the muted kind', vm.runInContext(`ZS.every(p=>p.kind==='latest')`, ctx), true);
check('fallback slides carry NO story key (no positional correspondence)', vm.runInContext(`ZS.every(p=>p.nkey==='')`, ctx), true);
vm.runInContext(`XNEWS=[];var ZS2=zeroPairSocial(12);`, ctx);
check('empty X pool fails closed (no placeholders)', vm.runInContext(`ZS2.length`, ctx), 0);
vm.runInContext(`XNEWS=[{id:'p9'},{id:'p8'}];var ZS3=zeroPairSocial(1);`, ctx);
check('social list respects the cap independently', vm.runInContext(`ZS3.length`, ctx), 1);
// C6: socSync never locks positions in fallback mode, even when counts coincide
vm.runInContext(`FEED_FALLBACK=true;SYNC_LAST=true;SOC_N=3;CAR_N=3;CAR_LAST=[{link:'a'}];CAR_IDX=1;SOC_IDX=0;var r1=socSyncReal();`, Object.assign(ctx,{socApply:()=>{ctx.__applied=(ctx.__applied||0)+1;},socMatchPair:()=>-1}));
check('fallback mode: socSync abstains even with equal counts', vm.runInContext(`r1`, ctx), false);
check('fallback mode: no positional sync applied', vm.runInContext(`SYNC_LAST`, ctx), false);
check('fallback mode: social index untouched', vm.runInContext(`SOC_IDX`, ctx), 0);
vm.runInContext(`FEED_FALLBACK=false;var r2=socSyncReal();`, ctx);
check('paired mode: socSync still aligns (existing behavior preserved)', [vm.runInContext(`r2`, ctx), vm.runInContext(`SOC_IDX`, ctx)], [true, 1]);
// C7: combo freshness, fail closed
const pt = new Date(new Date().toLocaleString('en-US',{timeZone:'America/Los_Angeles'}));
const ymd = d => `${d.getFullYear()}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}`;
const y0 = new Date(pt); y0.setDate(y0.getDate()-1);
const tmr = new Date(pt); tmr.setDate(tmr.getDate()+1);
vm.runInContext(`var F1=rpComboFresh({id:'idea-x-${y0.getFullYear()}${String(y0.getMonth()+1).padStart(2,'0')}${String(y0.getDate()).padStart(2,'0')}'});`, ctx);
check('yesterday combo hidden', vm.runInContext(`F1`, ctx), false);
vm.runInContext(`var F2=rpComboFresh({id:'idea-x-${ymd(pt)}'});`, ctx);
check('today combo shown', vm.runInContext(`F2`, ctx), true);
vm.runInContext(`var F3=rpComboFresh({id:'idea-x-${ymd(tmr)}'});`, ctx);
check('future combo shown', vm.runInContext(`F3`, ctx), true);
vm.runInContext(`var F4=rpComboFresh({id:'idea-mnf',date:'${tmr.getFullYear()}-${String(tmr.getMonth()+1).padStart(2,'0')}-${String(tmr.getDate()).padStart(2,'0')}'});`, ctx);
check('explicit date field wins over id', vm.runInContext(`F4`, ctx), true);
vm.runInContext(`var F5=rpComboFresh({id:'idea-nodate'});`, ctx);
check('unparseable date fails closed (hidden)', vm.runInContext(`F5`, ctx), false);
vm.runInContext(`var F6=rpComboFresh({id:'idea-x-${ymd(pt)}',status:'expired'});`, ctx);
check('writer-expired combo hidden even with today date', vm.runInContext(`F6`, ctx), false);
console.log('feed boot + date-roll class fixture: ALL PASS');
