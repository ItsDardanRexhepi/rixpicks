#!/usr/bin/env node
/* Standing regression fixture for the guard-3 (1:08 9/29) class kill: buildPairs must
   match BEFORE slicing. Extracts the real buildPairs from scripts/index_v2.js and runs it
   offline against stubbed feed state. Run: node scripts/test_buildpairs_class.js
   Wired into x_feed.yml beside soc_fixtures.py - a failure aborts the chain. */
'use strict';
const fs = require('fs'), path = require('path');
const src = fs.readFileSync(process.argv[2] || path.join(__dirname, 'index_v2.js'), 'utf8');

// extract the exact production function by brace matching
const start = src.indexOf('function buildPairs(base){');
if (start < 0) { console.error('FAIL: buildPairs not found in index_v2.js'); process.exit(1); }
let depth = 0, end = -1;
for (let i = start; i < src.length; i++) {
  if (src[i] === '{') depth++;
  else if (src[i] === '}') { depth--; if (depth === 0) { end = i + 1; break; } }
}
const fnSrc = src.slice(start, end);

let failures = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'OK   ' : 'FAIL ') + label + (ok ? '' : `  [want ${JSON.stringify(want)} got ${JSON.stringify(got)}]`));
}

function mkStories(n) {
  const out = [];
  for (let i = 0; i < n; i++) out.push({ headline: 'Story ' + i, link: 'https://ex.com/s' + i, published: '2026-09-29T08:0' + (59 - i) + ':00Z', source: 'ESPN' });
  return out;
}
function mkPosts(ids) {
  return ids.map(id => ({ id: String(id), headline: 'post ' + id, link: 'https://x.com/a/status/' + id, published: '2026-09-29T08:00:00Z', source: 'X', author: 'a' }));
}

function run(base, match, mapFresh) {
  const env = {
    PAIRS: [],
    SOC_MATCH: match,
    SOC_XIDX: {},
    XNEWS: mkPosts(match.__postIds || ['900']),
    rpMapFresh: () => mapFresh,
    carKey: a => a.link,
    isPublishablePost: p => !!p,
  };
  (match.__postIds || ['900']).forEach((pid, i) => { env.SOC_XIDX[pid] = i; });
  const fn = new Function('PAIRS', 'SOC_MATCH', 'SOC_XIDX', 'XNEWS', 'rpMapFresh', 'carKey', 'isPublishablePost',
    fnSrc + '; return buildPairs(arguments[7]);');
  // PAIRS is assigned (PAIRS=[]) inside buildPairs - rebind via object trick: use a holder
  const holder = { PAIRS: [] };
  const fn2 = new Function('h', 'SOC_MATCH', 'SOC_XIDX', 'XNEWS', 'rpMapFresh', 'carKey', 'isPublishablePost',
    'var PAIRS=h.PAIRS;' + fnSrc + '; buildPairs(arguments[7]); h.PAIRS=PAIRS;');
  fn2(holder, env.SOC_MATCH, env.SOC_XIDX, env.XNEWS, env.rpMapFresh, env.carKey, env.isPublishablePost, base);
  return holder.PAIRS;
}

// 1. REGRESSION (the 1:08 incident): 15 fresh stories, first 12 unmatched, a verified pair
//    at story index 13 - the pair MUST be found (old code sliced it away and blanked both feeds).
{
  const base = mkStories(15);
  const match = { pairs: { 'https://ex.com/s13': { verified: true, post_id: '900' } }, __postIds: ['900'] };
  const pairs = run(base, match, true);
  check('pair at story index 13 is found past the old 12-slice', pairs.length, 1);
  check('paired story is the index-13 story', pairs[0] && pairs[0].a.link, 'https://ex.com/s13');
  check('pair kind is verified', pairs[0] && pairs[0].kind, 'verified');
  check('paired post is the mapped post, not an unrelated fallback', pairs[0] && pairs[0].post.id, '900');
}

// 2. CAP AFTER PAIRING: 14 matched stories -> exactly 12 pairs, freshest first.
{
  const base = mkStories(14);
  const pairsMap = {}; const ids = [];
  base.forEach((a, i) => { const pid = String(1000 + i); pairsMap[a.link] = { verified: true, post_id: pid }; ids.push(pid); });
  const pairs = run(base, { pairs: pairsMap, __postIds: ids }, true);
  check('14 matches cap at 12 pairs', pairs.length, 12);
  check('cap keeps the freshest (index 0 first)', pairs[0] && pairs[0].a.link, 'https://ex.com/s0');
  check('cap drops the oldest (index 12/13)', pairs.some(p => p.a.link === 'https://ex.com/s12' || p.a.link === 'https://ex.com/s13'), false);
}

// 3. FAIL CLOSED: stale/mismatched map -> zero pairs, never unpaired news.
{
  const base = mkStories(15);
  const match = { pairs: { 'https://ex.com/s13': { verified: true, post_id: '900' } }, __postIds: ['900'] };
  check('stale map fails closed', run(base, match, false).length, 0);
  check('empty map fails closed', run(base, { pairs: {}, __postIds: ['900'] }, true).length, 0);
}

// 4. DISTINCT POSTS: two stories claiming the same post - only the first keeps it.
{
  const base = mkStories(3);
  const match = { pairs: {
      'https://ex.com/s0': { verified: true, post_id: '900' },
      'https://ex.com/s1': { verified: true, post_id: '900' } }, __postIds: ['900'] };
  const pairs = run(base, match, true);
  check('a post pairs with at most one story', pairs.length, 1);
  check('the freshest story keeps the post', pairs[0] && pairs[0].a.link, 'https://ex.com/s0');
}

if (failures) { console.error(failures + ' FAILURES'); process.exit(1); }
console.log('buildPairs class fixture: ALL PASS');
