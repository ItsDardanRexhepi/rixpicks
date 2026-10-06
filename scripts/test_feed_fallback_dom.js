#!/usr/bin/env node
/* Render-level regression fixture for zero-pair fallback mode (independent feeds class):
   drives the REAL renderNews/renderSocial/carStep/socStep from index_v2.js against a real
   jsdom DOM with a fresh ZERO-pair map, then asserts:
   (a) body.rp-nosync is set and the UltRix sync caption computes to display:none;
   (b) news and social carousels advance on SEPARATE clocks - invoking the news timer never
       moves social, invoking the social timer never moves news (no visual lockstep);
   (c) no PAIRS unit, no data-nkey on social slides, every badge 'Latest from the feed'.
   Run: node scripts/test_feed_fallback_dom.js */
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
let JSDOM;
try { ({ JSDOM } = require('jsdom')); } catch (e) { ({ JSDOM } = require('/tmp/node_modules/jsdom')); }
const src = fs.readFileSync(process.env.RP_FIXTURE_JS || path.join(__dirname, 'index_v2.js'), 'utf8');
const css = fs.readFileSync(process.env.RP_FIXTURE_CSS || path.join(__dirname, 'index_v2.css'), 'utf8');

function extract(name) {
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) { console.error('FAIL: ' + name + ' not found'); process.exit(1); }
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
  console.log((ok ? 'OK   ' : 'FAIL ') + label + (ok ? '' : '  [want ' + JSON.stringify(want) + ' got ' + JSON.stringify(got) + ']'));
}

const NOW = Date.now(), G1 = '2026-09-29T08:20:12.265768+00:00', G2 = '2026-09-29T08:20:27+00:00';
const stories = [];
const LG = ['NBA','NFL','MLB','NHL'];
for (let i = 1; i <= 12; i++) stories.push({ headline: LG[i%4] + ' playoff race shakes up after trade for star quarterback scorer ' + i, link: 'https://ex.com/s' + i, published: G1, source: 'CBS', blurb: 'basketball football baseball hockey ' + i, league: 'basketball/nba' });
const xitems = [];
for (let i = 1; i <= 12; i++) xitems.push({ id: String(900 + i), text: 'Post ' + i + ' about basketball hoops', created_at: G2, url: 'https://x.com/x/status/' + (900 + i), author_name: 'Feed' });
/* feed guard 1 (Sep 29): off-topic posts with valid format + clean authors must NEVER reach
   the zero-pair Social path - the fallback renders only genuine sports posts. */
const OFFTOPIC = [
 ['921', 'NASDAQ ripping today, passive income stock tips inside'],
 ['922', 'The president addressed congress on the election results tonight'],
 ['923', 'New fashion drop just hit the runway, shop the look now'],
 ['924', '18+ spicy content on my only fans page tonight'],
 ['925', 'Airline lost my luggage again, worst travel day ever'],
 ['926', 'Essay help and homework help, DM for rates'],
 ['927', 'Weight loss diet pills that actually work fast'],
 ['928', 'Thursday Silver Squarely NFL NBA MLB, big day'],
];
for (const [id, text] of OFFTOPIC) xitems.push({ id, text, created_at: G2, url: 'https://x.com/x/status/' + id, author_name: 'Feed' });

const dom = new JSDOM('<body class="tab-home"><div id="rpNewsCar"></div><div id="rpSocial"></div><div class="ultrix-sync-line home-only">*live sync connection between feeds powered by UltRix algorithm</div></body>', { pretendToBeVisual: true });
const styleEl = dom.window.document.createElement('style');
styleEl.textContent = css;
dom.window.document.head.appendChild(styleEl);

const timers = [];
const ctx = vm.createContext({
  Date, JSON, Intl, RegExp, String, Number, Array, Object, Math, isFinite, parseFloat, parseInt, encodeURIComponent,
  console, Promise,
  document: dom.window.document,
  window: { matchMedia: () => ({ matches: false }), addEventListener: () => {}, innerWidth: 400 },
  localStorage: { getItem: () => null, setItem: () => {} },
  location: { search: '', pathname: '/index.html' },
  navigator: { userAgent: 'fixture' },
  setInterval: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
  clearInterval: () => {}, setTimeout: () => 0, clearTimeout: () => {},
  requestAnimationFrame: (f) => 0, IntersectionObserver: function(){ this.observe=()=>{}; this.unobserve=()=>{}; this.disconnect=()=>{}; }, ResizeObserver: function(){ this.observe=()=>{}; this.unobserve=()=>{}; this.disconnect=()=>{}; },
  $: (id) => dom.window.document.getElementById(id),
  NEWSF: null, XFEED_GEN: null, SOC_MATCH: null, SOC_MATCH_OK: false, SOC_MATCH_PENDING: null,
  SOC_XIDX: {}, XNEWS: [], PAIRS: [], FEED_FALLBACK: false, SYNC_LAST: false,
  SOC_N: 0, CAR_N: 0, CAR_LAST: [], CAR_IDX: 0, SOC_IDX: 0, CAR_SIG: '', SOC_SIG: '', SOC_LAST: [], SOC_RIDX: {},
  CAR_ALL: [], CAR_UNIT: null, NEWS_READY: false, XFEED_DONE: true, SOC_MAP_DONE: true,
  CAR_PAUSED: false, CAR_RM: false, CAR_TIMER: null, SOC_TIMER: null, CAR_JUMP: 0, SOC_JUMP: 0, SOC_TIMER_SET: 0,
  SOC_MATCH_TRIES: 0, RP_BUILD: 'fixture', CAR_RZ: null, CAR_OBS: null, CAR_RO: null,
  newsBucket: () => stories,
  newsBucketAll: () => stories,
});
const NAMES = ['esc','unesc','pubT','ago','newsBlurb','normH','isNewIt','isPublishableNews','isPublishablePost','imgOpt','carKey',
 'rpMapFresh','buildPairs','zeroPairSocial','isSportsPost','carClonify','carCloned','carMove','carNoTrans','carApply','socApply',
 'socMove','carAdv','socAdv','socGo','carStep','socStep','carObserve','feedCacheSave','socSync','socMapRetry','socMatchMore','ingestX','renderNews','renderSocial','socMatchPair'];
/* real top-level RP_* constants (single-line regex/string decls) + league kw object */
const varLines = src.split('\n').filter(l => /^var RP_[A-Z_]+=/.test(l) && /;\s*$/.test(l));
function extractVar(name){
  const start = src.indexOf('var ' + name + '=');
  if (start < 0) return '';
  let depth = 0, i = start;
  for (; i < src.length; i++) {
    const c = src[i];
    if (c === '{' || c === '[') depth++;
    else if (c === '}' || c === ']') depth--;
    else if (c === ';' && depth === 0) return src.slice(start, i + 1);
  }
  return src.slice(start);
}
vm.runInContext(varLines.join('\n') + '\n' + extractVar('RP_NEWS_LEAGUE_KW') + '\n' + NAMES.map(extract).join('\n'), ctx);

/* drive: fresh ZERO-pair map + news + X generations */
ctx.NEWSF = { generated_at: G1, items: stories };
vm.runInContext('ingestX(XP);', Object.assign(ctx, { XP: { generated_at: G2, items: xitems } }));
vm.runInContext('if(rpMapFresh(MAP)){SOC_MATCH=MAP;SOC_MATCH_OK=true;}', Object.assign(ctx, {
  MAP: { built_at: new Date(NOW - 60000).toISOString(), pairs: {}, nearest: {}, more: {}, news_generated_at: G1, x_generated_at: G2 } }));
vm.runInContext('renderNews({key:"home"}, newsBucket());', ctx);

const doc = dom.window.document;
check('fallback engaged with zero-pair fresh map', ctx.FEED_FALLBACK, true);
check('no PAIRS unit in fallback', ctx.PAIRS.length, 0);
/* (a) sync caption hidden */
check('body carries rp-nosync in fallback', doc.body.classList.contains('rp-nosync'), true);
const syncEl = doc.querySelector('.ultrix-sync-line');
check('sync caption element exists exactly once', !!syncEl, true);
check('sync caption computes to display:none in fallback DOM', dom.window.getComputedStyle(syncEl).display, 'none');
/* (c) independence of content */
const newsSlides = [...doc.querySelectorAll('#rpNewsCar .carslide')].filter(s=>!s.classList.contains('carclone'));
const socSlides = [...doc.querySelectorAll('#rpSocial .socslide')].filter(s=>!s.classList.contains('carclone'));
check('news renders 12 independent stories', newsSlides.length, 12);
check('social renders 12 independent posts', socSlides.length, 12);
check('every news slide keyed', newsSlides.filter(s => s.getAttribute('data-nkey')).length, 12);
check('no social slide carries a story key (no positional link)', socSlides.filter(s => s.getAttribute('data-nkey')).length, 0);
const badges = [...doc.querySelectorAll('#rpSocial .syncbadge')].length;
const latest = [...doc.querySelectorAll('#rpSocial .socslide:not(.carclone) .synclatest')].length;
check('zero verified badges in fallback', badges, 0);
check('all social slides carry Latest-from-the-feed badge', latest, 12);
const socHTML = dom.window.document.getElementById('rpSocial').innerHTML;
check('fallback social shows sports post', socHTML.includes('Post 1 about basketball hoops'), true);
check('fallback social hides finance solicitation', !socHTML.includes('NASDAQ'), true);
check('fallback social hides politics', !socHTML.includes('president'), true);
check('fallback social hides fashion promo', !socHTML.includes('fashion drop'), true);
check('fallback social hides sexual solicitation', !socHTML.includes('spicy content'), true);
check('fallback social hides lost-luggage post', !socHTML.includes('luggage'), true);
check('fallback social hides essay spam', !socHTML.includes('homework help'), true);
check('fallback social hides diet spam', !socHTML.includes('diet pills'), true);
check('fallback social hides acronym-stuffer', !socHTML.includes('Silver Squarely'), true);
/* (b) separate clocks */
const carTimer = timers.filter(t => t.ms === 5500), socTimer = timers.filter(t => t.ms === 7000);
check('news clock (5500ms) registered', carTimer.length >= 1, true);
check('social own clock (7000ms) registered in fallback', socTimer.length, 1);
check('no second shared clock for social', timers.filter(t => t.ms === 5500).length, 1);
const carIdx0 = ctx.CAR_IDX, socIdx0 = ctx.SOC_IDX;
const socCount0 = (doc.getElementById('rpSocCount')||{textContent:''}).textContent;
vm.runInContext('carStep();', ctx);
check('news clock advances news', ctx.CAR_IDX === (carIdx0 + 1) % 12, true);
check('news clock does NOT move social index', ctx.SOC_IDX, socIdx0);
check('news clock does NOT move social counter', (doc.getElementById('rpSocCount')||{textContent:''}).textContent, socCount0);
vm.runInContext('socStep();', ctx);
check('social clock advances social', ctx.SOC_IDX === (socIdx0 + 1) % 12, true);
check('social clock does NOT move news index', ctx.CAR_IDX, (carIdx0 + 1) % 12);

/* feed guard 1 (9/30 12:04 AM pixel repro, build 1790750987): Social Next in fallback with equal
   feed counts must advance SOCIAL, not delegate to carAdv (which moved NEWS and stuck SOCIAL at 2/12). */
vm.runInContext('CAR_IDX=0;SOC_IDX=0;', ctx);
const carBefore = ctx.CAR_IDX, socBefore = ctx.SOC_IDX;
check('fixture feeds are equal-count (repro condition)', ctx.SOC_N > 0 && ctx.SOC_N === ctx.CAR_N, true);
vm.runInContext('socGo(1);', ctx);
check('fallback Social Next advances SOCIAL index', ctx.SOC_IDX, (socBefore + 1) % ctx.SOC_N);
check('fallback Social Next does NOT move NEWS index', ctx.CAR_IDX, carBefore);
vm.runInContext('socGo(-1);', ctx);
check('fallback Social Prev returns SOCIAL index', ctx.SOC_IDX, socBefore);
check('fallback Social Prev does NOT move NEWS index', ctx.CAR_IDX, carBefore);

check('zero-note caption present', !!dom.window.document.getElementById('rpZeroNote'), true);
check('zero-note caption visible in zero-pair', dom.window.document.getElementById('rpZeroNote') ? dom.window.document.getElementById('rpZeroNote').style.display!=='none' : false, true);
check('zero-note caption text honest', (dom.window.document.getElementById('rpZeroNote')||{textContent:''}).textContent, 'No verified matches yet - latest from the feeds');

/* feed down (10/1 12:13 AM visuals): zero AVAILABLE posts must say unavailable, no controls, no zero-note */
vm.runInContext('ingestX(XP0);XFEED_DONE=true;SOC_SIG="";renderNews({key:"home"}, newsBucket());', Object.assign(ctx, { XP0: { generated_at: G2, items: [] } }));
const sbox = dom.window.document.getElementById('rpSocial');
check('empty feed: unavailable message shown', !!dom.window.document.getElementById('rpSocUnavail') && /temporarily unavailable/.test(sbox.textContent), true);
check('empty feed: no carousel controls', sbox.querySelectorAll('button').length, 0);
check('empty feed: no "No verified matches" implication', /No verified matches/.test(sbox.textContent), false);
check('empty feed: zero-note hidden', (dom.window.document.getElementById('rpZeroNote')||{style:{display:'none'}}).style.display, 'none');
vm.runInContext('ingestX(XP);SOC_SIG="";renderNews({key:"home"}, newsBucket());', ctx);
check('feed back: posts and controls return', sbox.querySelectorAll('.socslide').length > 0 && sbox.querySelectorAll('button').length > 0 && !dom.window.document.getElementById('rpSocUnavail'), true);
/* guard 1 10/6 cold-load class (3:35 AM verified blank News+Social at rix-picks.com/#home):
   a map older than the rpMapFresh 2h window must NOT blank News - the served (aged) news snapshot
   renders as independent latest-content feeds, and Social says unavailable when X has no posts,
   independently of news inventory. Cold-load sim: every cache/unit/global cleared first. */
vm.runInContext(`CAR_LAST=[];CAR_ALL=[];CAR_UNIT=null;PAIRS=[];CAR_SIG='';SOC_SIG='';CAR_N=0;SOC_N=0;
FEED_FALLBACK=false;NEWS_READY=false;XFEED_DONE=false;SOC_MAP_DONE=false;SOC_MATCH=null;SOC_MATCH_OK=false;
document.getElementById('rpNewsCar').innerHTML='';document.getElementById('rpSocial').innerHTML='';
var STALE_MAP={built_at:new Date(Date.now()-3*3600*1000).toISOString(),pairs:{},nearest:{},more:{}};
if(rpMapFresh(STALE_MAP)){SOC_MATCH=STALE_MAP;SOC_MATCH_OK=true;}
NEWSF={generated_at:G1,items:newsBucket()};
ingestX(XP0);
XFEED_DONE=true;SOC_MAP_DONE=true;
renderNews({key:"home"}, newsBucket());`, Object.assign(ctx, { G1: G1 }));
check('stale map: rejected by rpMapFresh (no sync claimed)', ctx.SOC_MATCH_OK, false);
check('stale map: fallback engaged', ctx.FEED_FALLBACK, true);
const staleNewsSlides = [...doc.querySelectorAll('#rpNewsCar .carslide')].filter(s=>!s.classList.contains('carclone'));
check('stale map: News renders the served snapshot (12 latest stories)', staleNewsSlides.length, 12);
check('stale map: zero verified badges', doc.querySelectorAll('#rpSocial .syncbadge').length, 0);
check('stale map + empty X: Social says unavailable (not blank)', !!doc.getElementById('rpSocUnavail') && /temporarily unavailable/.test(doc.getElementById('rpSocial').textContent), true);
check('stale map + empty X: zero-note hidden beside unavailable', (doc.getElementById('rpZeroNote')||{style:{display:'none'}}).style.display, 'none');
/* stale map with posts available: Social renders the Latest tier, never a verified claim */
vm.runInContext(`ingestX(XP);SOC_SIG='';renderNews({key:"home"}, newsBucket());`, ctx);
const staleSocSlides = [...doc.querySelectorAll('#rpSocial .socslide')].filter(s=>!s.classList.contains('carclone'));
check('stale map + posts: Social renders latest tier', staleSocSlides.length > 0, true);
check('stale map + posts: still zero verified badges', doc.querySelectorAll('#rpSocial .syncbadge').length, 0);
check('stale map + posts: unavailable message cleared', !!doc.getElementById('rpSocUnavail'), false);
/* settled feeds with zero NEWS inventory: Social unavailable status is independent of the news carousel */
vm.runInContext(`CAR_LAST=[];PAIRS=[];NEWS_READY=true;XFEED_DONE=true;SOC_MAP_DONE=true;document.getElementById('rpSocial').innerHTML='';renderSocial();`, ctx);
check('zero news inventory: Social still says unavailable', !!doc.getElementById('rpSocUnavail') && /temporarily unavailable/.test(doc.getElementById('rpSocial').textContent), true);
console.log(failures ? ('FAILURES: ' + failures) : 'ALL CHECKS PASS');
process.exit(failures ? 1 : 0);
