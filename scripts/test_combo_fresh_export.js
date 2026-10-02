#!/usr/bin/env node
/* Standing regression fixture (Sep 30 strikeouts-idea incident): the Same Game Parlays
   module reads rpComboFresh as a GLOBAL from inside its async fetch callback, but
   index_v2.js wraps everything in IIFEs - without an explicit window export the function
   is undefined at callback time, the module throws, its .catch fail-closes hidden, and
   every combo (type idea or link) silently never renders. A hidden module is visually
   identical to "no fresh combos", so this went unnoticed until a dated idea had to render.
   Guards: (1) the export line exists in index_v2.js, (2) document-order simulation - a
   consumer callback registered BEFORE the utils script executes still resolves the global
   afterwards, (3) the built page carries the export. Run: node scripts/test_combo_fresh_export.js */
'use strict';
/* Pinned test clock: every card/feed date below is the fixed day 2026-09-30, so the suite must run
   at a fixed instant, not the real wall clock (13 false FAILs at the Oct 1 rollover froze the gate).
   Override with RP_FIXTURE_NOW to probe other instants. */
const PINNED_NOW = Date.parse(process.env.RP_FIXTURE_NOW || '2026-09-30T18:30:00Z');
const RealDate = Date;
class PinnedDate extends RealDate {
  constructor(...a) { if (a.length === 0) super(PINNED_NOW); else super(...a); }
  static now() { return PINNED_NOW; }
}

const fs = require('fs'), path = require('path'), vm = require('vm');
let failures = 0;
function check(label, ok) { if (!ok) failures++; console.log((ok ? 'OK   ' : 'FAIL ') + label); }

const src = fs.readFileSync(path.join(__dirname, 'index_v2.js'), 'utf8');

// (1) export exists, exactly once, after the def
const defIdx = src.indexOf('function rpComboFresh(');
check('rpComboFresh defined in index_v2.js', defIdx > 0);
const expCount = (src.match(/window\.rpComboFresh=rpComboFresh;/g) || []).length;
check('window.rpComboFresh export present exactly once', expCount === 1);
check('export comes after the definition', expCount === 1 && src.indexOf('window.rpComboFresh=rpComboFresh;') > defIdx);

// (2) document-order simulation: the page emits the consumer module BEFORE the utils script.
// The consumer's filter runs in a later (async) turn - it must find the global by then.
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
const ctx = vm.createContext({ Date: PinnedDate, JSON, RegExp, String, Number });
ctx.window = ctx; // classic-script global proxy
vm.runInContext(`var later=null; function consumer(){ later=function(){ return (([{id:'idea-x-20990101'}]).filter(rpComboFresh)).length; }; } consumer();`, ctx);
// the utils script's relevant slice: the def, then (per the patch) the export line
const exportLine = src.includes('window.rpComboFresh=rpComboFresh;') ? 'window.rpComboFresh=rpComboFresh;' : '';
vm.runInContext(extract('rpComboFresh') + '\n' + exportLine, ctx);
let got = 'threw';
try { got = vm.runInContext('later()', ctx); } catch (e) { got = 'threw:' + e.message; }
check('consumer callback registered before utils script resolves rpComboFresh after it runs', got === 1);

// (3) built page carries the export (gate on the committed artifact)
const page = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
check('built index.html contains the window.rpComboFresh export', page.includes('window.rpComboFresh=rpComboFresh;'));


// (4) behavioral race simulation: the module's fetch chain must not run before the page's
// last script can define rpComboFresh. Simulates a cache-hit fetch (resolves immediately,
// .then runs in the between-scripts microtask checkpoint) with rpComboFresh NOT yet defined,
// then fires load and asserts the module renders. Old (ungated) module: filter throws
// ReferenceError -> catch hides -> FAIL here.
const comboPage = fs.readFileSync(process.argv[2] || path.join(__dirname, '..', 'index.html'), 'utf8');
const modMatch = comboPage.match(/<script>\(function\(\)\{var box=document\.getElementById\("rpCmb"\)[\s\S]*?<\/script>/);
check('combos module script found in page', !!modMatch);
(async () => {
  let sandboxFeed = null;
  async function runSim(sample, feedPayload) {
    sandboxFeed = feedPayload ? () => Promise.resolve(feedPayload) : undefined;
    const modSrc = modMatch[0].replace(/^<script>/, '').replace(/<\/script>$/, '');
    const listeners = {}, timers = [];
    const style = { display: '' };
    const box = { innerHTML: '', parentNode: { style } };
    box.querySelector = () => (box.innerHTML.includes('class="rpfeedtrk"') ? {} : null);
    box.querySelectorAll = () => {
      const out = [];
      const re = /<div class="rpfeedtrk" data-p="([^"]*)"><\/div>/g;
      let m;
      while ((m = re.exec(box.innerHTML))) {
        const el = { _p: m[1].replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>'), innerHTML: '', getAttribute(k) { return k === 'data-p' ? this._p : null; } };
        out.push(el);
      }
      box._trk = out;
      return out;
    };
    const sandbox = {
      document: { getElementById: () => box, readyState: 'loading', createElement: () => ({ set src(v) {}, set onload(f) {} }), head: { appendChild() {} } },
      addEventListener: (ev, fn) => { (listeners[ev] = listeners[ev] || []).push(fn); },
      fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve(sample) }),
      setTimeout: (fn) => { timers.push(fn); return 1; },
      setInterval: () => 1,
      rpTicketFeed: sandboxFeed,
      Date: PinnedDate, JSON, console,
    };
    sandbox.window = sandbox;
    vm.createContext(sandbox);
    vm.runInContext(modSrc, sandbox); // rpComboFresh intentionally NOT defined yet
    for (let i = 0; i < 8; i++) await new Promise(r => setImmediate(r));
    const renderedEarly = box.innerHTML.length > 0;
    vm.runInContext(extract('rpComboFresh') + '\nwindow.rpComboFresh=rpComboFresh;', sandbox);
    (listeners.load || []).forEach(fn => fn());
    timers.forEach(fn => fn());
    for (let i = 0; i < 8; i++) await new Promise(r => setImmediate(r));
    return { box, style, renderedEarly };
  }
  if (modMatch) {
    const s1 = { combos: [{ id: 'idea-mlb-ks-20260930', type: 'idea', date: '2026-09-30',
      title: 'Strikeouts Parlay (4 legs)', badge: 'PLACED - reported by Wooder Ice',
      matchup: 'PHI@ATL', time: 'from 11:00 AM PT',
      legs: [{ player: 'Cristopher Sanchez', market: '7+ strikeouts vs ATL', kalshi: '+138 · 42c' }],
      estimate_note: 'note', prices_note: 'snap' }] };
    s1.combos[0].legs = [
      { player: 'Cristopher Sanchez', market: '7+ strikeouts vs ATL', kalshi: '+138 · 42c' },
      { player: 'Hunter Brown', market: '7+ strikeouts vs CWS', kalshi: '+117 · 46c' },
      { player: 'Max Fried', market: '6+ strikeouts vs BOS', kalshi: '+117 · 46c' },
      { player: 'Kevin Gausman', market: '5+ strikeouts at SD', kalshi: '+117 · 46c' },
      { player: 'Zac Gallen', market: '7+ strikeouts at LAD', kalshi: '+120' },
      { player: 'Nobody Feedless', market: '9+ strikeouts', kalshi: '+200' }];
    const feed = { generatedAt: '2026-09-30T18:00:00Z', tickets: [{ id: 'k-parlay-2026-09-30', legs: [
      { legId: 'k-sanchez', kind: 'pitcher_strikeouts', threshold: 7, player: { name: 'Cristopher Sánchez' }, current: 3, status: 'pending', freshness: { sourceTs: '2026-09-30T17:59:50Z' } },
      { legId: 'k-brown', kind: 'pitcher_strikeouts', threshold: 7, player: { name: 'Hunter Brown' }, current: 7, status: 'hit', freshness: { sourceTs: '2026-09-30T17:59:50Z' } },
      { legId: 'k-gallen', kind: 'pitcher_strikeouts', threshold: 7, player: { name: 'Zac Gallen' }, current: 4, status: 'final_miss', freshness: { sourceTs: '20260930_183550' } },
      { legId: 'k-fried', kind: 'pitcher_strikeouts', threshold: 6, player: { name: 'Max Fried' }, current: null, status: 'pre', freshness: { sourceTs: null } },
      { legId: 'k-gausman', kind: 'pitcher_strikeouts', threshold: 5, player: { name: 'Kevin Gausman' }, current: null, status: 'unavailable', freshness: { sourceTs: null, fetchedAt: '2026-09-30T18:00:00Z' } }] },
      { id: 'hits-tracker-2026-09-30', legs: [
      { legId: 'h-turner', kind: 'batter_hits', threshold: 1, player: { name: 'Trea Turner' }, current: 2, status: 'hit', freshness: { sourceTs: '2026-09-30T18:25:00Z' } }] }] };
    const r1 = await runSim(s1, feed);
    check('module does not render before load when fetch resolves instantly', !r1.renderedEarly);
    check('module renders Strikeouts card after load with global present', r1.box.innerHTML.includes('Strikeouts Parlay (4 legs)'));
    check('module parent not hidden after successful render', r1.style.display !== 'none');
    check('badge override renders (PLACED - reported by Wooder Ice)', r1.box.innerHTML.includes('PLACED - reported by Wooder Ice'));
    check('badge override replaces the default (no NOT BOUGHT)', !r1.box.innerHTML.includes('NOT BOUGHT'));
    const trk1 = r1.box._trk || [];
    const byName = n => { const e = trk1.find(x => x._p === n); return e ? e.innerHTML : null; };
    const allPainted = () => trk1.map(e => e._p + '=>' + e.innerHTML).join('|');
    check('met leg: midnight-green pill + "7 of 7 Ks - CASHED"', (byName('Hunter Brown') || '').includes('#0b3d2e') && (byName('Hunter Brown') || '').includes('7 of 7 Ks - CASHED'));
    check('active below-threshold: bare "3 of 7 Ks", neutral (no pill, no CASHED, no Pending)', (byName('Cristopher Sanchez') || '').includes('3 of 7 Ks') && !(byName('Cristopher Sanchez') || '').includes('- Pending') && !(byName('Cristopher Sanchez') || '').includes('#0b3d2e') && !(byName('Cristopher Sanchez') || '').includes('CASHED'));
    check('pregame leg renders blank (no Game-not-started text, no counts)', byName('Max Fried') !== null && !byName('Max Fried').includes('Game not started') && !byName('Max Fried').includes(' of '));
    check('stale/unknown leg: explicit Unavailable marker (never 0, never blank)', (byName('Kevin Gausman') || '').includes('Unavailable'));
    check('fetchedAt alone never renders a stamp or data', !(byName('Kevin Gausman') || '').includes('2026'));
    check('final-missed leg: red + "Missed · Final 4 of 7 Ks"', (byName('Zac Gallen') || '').includes('Missed \u00b7 Final 4 of 7 Ks') && (byName('Zac Gallen') || '').includes('229,72,77'));
    check('no visible timestamp anywhere on painted legs', !allPainted().includes('Updated') && !allPainted().includes('2026-09-30T'));
    check('accent-insensitive player match (Sanchez)', (byName('Cristopher Sanchez') || '').includes('3 of 7 Ks'));
    check('paint poll cadence is 15s (statsapi sanctioned 10s + margin)', modMatch[0].includes('setInterval(paint,15000)') && !modMatch[0].includes('setInterval(paint,60000)'));
    check('unmatched leg stays empty (fail-closed)', trk1.some(e => e._p === 'Nobody Feedless' && e.innerHTML === ''));
    check('card-level CASHED explainer removed (consolidated into the page note)', !r1.box.innerHTML.includes('CASHED = live stat threshold met'));
    check('consolidated page note carries CASHED/price/PLACED/hit distinctions', /id="rpWNote"[^>]*>CASHED = live stat threshold met, not a verified payout\. Prices are reference snapshots, not executable quotes, and combined odds are estimates\. PLACED = reported by Wooder Ice/.test(require('fs').readFileSync(__dirname+'/../index.html','utf8')));
    const s4 = { combos: [{ id: 'idea-mlb-hits-20260930b', type: 'idea', date: '2026-09-30',
      title: 'Hits', matchup: 'PHI@ATL', legs: [{ player: 'Trea Turner', market: '1+ hit', kalshi: '-233' }] }] };
    const r4 = await runSim(s4, feed);
    const painted4 = () => (r4.box._trk || []).map(e => e._p + '=>' + e.innerHTML).join('|');
    check('over-threshold met count truthful: "2 of 1 Hit - CASHED", never HR', painted4().includes('2 of 1 Hit - CASHED') && !painted4().includes('HR'));
    const s2 = { combos: [{ id: 'idea-mlb-hits-20260930', type: 'idea', date: '2026-09-30',
      title: 'Hits Parlay Tracker (4 legs)', matchup: 'PHI@ATL', time: 'from 11:00 AM PT',
      legs: [{ player: 'Trea Turner', market: '1+ hit at ATL', kalshi: '-233 · 70c', tag: 'Confirmed leadoff' }] }] };
    const r2 = await runSim(s2);
    check('default badge renders without override (IDEA · NOT BOUGHT)', r2.box.innerHTML.includes('IDEA · NOT BOUGHT'));
    check('leg tag renders (Confirmed leadoff)', r2.box.innerHTML.includes('Confirmed leadoff'));
    const s3 = { combos: [{ id: 'idea-plain-20260930', type: 'idea', date: '2026-09-30',
      title: 'Plain', matchup: 'X', legs: [{ player: 'P', market: 'm', kalshi: '+100' }] }] };
    const r3 = await runSim(s3);
    check('no tag field renders no tag', !r3.box.innerHTML.includes('Confirmed leadoff'));
  }
  // Dingers + anytime-TD trackers: unknown-not-zero rule (null count at in/post = Unavailable, never "No HR yet")
  {
    const pageSrc2 = fs.readFileSync('index.html', 'utf8');
    const extractFn = (src, sig) => {
      const i = src.indexOf(sig);
      if (i < 0) return null;
      let d = 0; const j = src.indexOf('{', i);
      for (let k = j; k < src.length; k++) {
        if (src[k] === '{') d++;
        else if (src[k] === '}') { d--; if (!d) return src.slice(i, k + 1); }
      }
      return null;
    };
    const dotSrc = extractFn(pageSrc2, 'function dot(c)');
    const dingSrc = extractFn(pageSrc2, 'function tS(count,state,det)');
    const tdSrc = extractFn(pageSrc2, 'function tS(spec,count,state,det)');
    check('dingers + TD tS functions extractable from built page', !!(dotSrc && dingSrc && tdSrc));
    if (dotSrc && dingSrc && tdSrc) {
      const sb2 = {};
      vm.createContext(sb2);
      vm.runInContext(dotSrc + '\n' + dingSrc, sb2);
      const dPre = vm.runInContext('tS(null,"pre","")', sb2);
      const dIn = vm.runInContext('tS(null,"in","")', sb2);
      const dPost = vm.runInContext('tS(null,"post","")', sb2);
      const dZero = vm.runInContext('tS(0,"in","")', sb2);
      const dHit = vm.runInContext('tS(1,"in","")', sb2);
      const dZeroPre = vm.runInContext('tS(0,"pre","")', sb2);
      check('dingers: pregame renders blank, never "Game not started" (blank-pregame spec)', dPre === '' && dZeroPre === '' && !dPre.includes('Game not started'));
      check('dingers: null count in-game renders Unavailable (never invented zero)', dIn.includes('Unavailable') && !dIn.includes('No HR'));
      check('dingers: null count at final renders Unavailable (never "No HR · Final")', dPost.includes('Unavailable') && !dPost.includes('No HR'));
      check('dingers: live 0 HR honestly renders "No HR yet"', dZero.includes('No HR yet'));
      const dOver = vm.runInContext('tS(2,"in","")', sb2);
      const dPostHit = vm.runInContext('tS(1,"post","")', sb2);
      check('dingers: met threshold renders "1 of 1 HR - CASHED" midnight-green pill (no check char, no Pending)', dHit.includes('1 of 1 HR - CASHED') && dHit.includes('#0b3d2e') && dHit.includes('#8ff0c8') && !dHit.includes('10003') && !/pending/i.test(dHit));
      check('dingers: over-threshold truthful "2 of 1 HR - CASHED"', dOver.includes('2 of 1 HR - CASHED'));
      check('dingers: met at final still renders the CASHED pill', dPostHit.includes('1 of 1 HR - CASHED'));
      vm.runInContext(tdSrc, sb2);
      const tdIn = vm.runInContext('tS({target:1,label:"TD",td:true},null,"in","")', sb2);
      const tdZero = vm.runInContext('tS({target:1,label:"TD",td:true},0,"in","")', sb2);
      check('TD tracker: null count in-game renders Unavailable', tdIn.includes('Unavailable') && !tdIn.includes('No TD'));
      check('TD tracker: live 0 TD honestly renders "No TD yet"', tdZero.includes('No TD yet'));
      const tdPre = vm.runInContext('tS({target:1,label:"TD",td:true},null,"pre","")', sb2);
      check('TD tracker: pregame renders blank, never "Game not started"', tdPre === '');
      const tdHit = vm.runInContext('tS({target:1,label:"TD",td:true},1,"in","")', sb2);
      const tdOver = vm.runInContext('tS({target:1,label:"TD",td:true},2,"in","")', sb2);
      check('TD tracker: met threshold renders "1 of 1 TD - CASHED" midnight-green pill', tdHit.includes('1 of 1 TD - CASHED') && tdHit.includes('#0b3d2e') && !tdHit.includes('10003'));
      check('TD tracker: over-threshold truthful "2 of 1 TD - CASHED"', tdOver.includes('2 of 1 TD - CASHED'));
    }
  }
  // futures bypass: season-long items (c.futures===true) survive day roll; expired still drops
  {
    const futLen = vm.runInContext('([{id:"idea-x-20200101",futures:true}]).filter(rpComboFresh).length', ctx);
    const futExp = vm.runInContext('([{id:"idea-x-20200101",futures:true,status:"expired"}]).filter(rpComboFresh).length', ctx);
    const staleIdea = vm.runInContext('([{id:"idea-x-20200101"}]).filter(rpComboFresh).length', ctx);
    check('rpComboFresh: futures:true bypasses day-roll (stale-dated futures item stays)', futLen === 1);
    check('rpComboFresh: expired still drops even with futures:true', futExp === 0);
    check('rpComboFresh: non-futures stale-dated idea still drops', staleIdea === 0);
  }
  if (failures) { console.error(failures + ' FAIL'); process.exit(1); }
  console.log('ALL OK (incl. race sim + badge/tag)');
})();

