#!/usr/bin/env node
/* Record pages, view-time behaviour (sweep LS-18, DI-03/LS-03/OS-06, DI-M2, DI-12/CP-06).
   - record_today.js asks for the optional today_record.json, and after a 404 does not ask
     again for 10 minutes (it was re-requested every 15 s from every open record page);
   - record.html lists every graded day statically; record_today.js hides the static block
     for the date it paints live (only while it shows picks), so no day is shown twice or lost;
   - a pick's display-only learning shows in the live Today section too;
   - yesterday.html picks the viewer's PT yesterday at view time; with no row it says the day's
     results are pending when that date carried official picks (the card dates build_history bakes
     from manifests/ snapshots and the live card, the ones the Home page carries, or the live card
     itself by the builder's date rule), else - once the Home page's dates were read - that it had
     no official picks, and shows the last graded day under its own name.
   Offline: fake DOM, fetch and clock. Bite-proof: red on the pre-fix record_today.js and
   build_history.py. Run: node scripts/test_record_pages.js */
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm'), os = require('os');
const { execFileSync } = require('child_process');
let failures = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  console.log((ok ? 'OK   ' : 'FAIL ') + label + (ok ? '' : ` (got ${JSON.stringify(got)}, want ${JSON.stringify(want)})`));
  if (!ok) failures++;
}
const flush = () => new Promise(r => setImmediate(r));

function el(tag) {
  return { tag, className: '', textContent: '', children: [], style: {}, attrs: {}, hidden: false,
    appendChild(c) { this.children.push(c); return c; }, setAttribute(k, v) { this.attrs[k] = v; },
    getAttribute(k) { return this.attrs[k] == null ? null : this.attrs[k]; },
    replaceChildren(...c) { this.children = c; } };
}
function textOf(n) { return (n.textContent || '') + ' ' + (n.children || []).map(textOf).join(' '); }
function block(date, label, record) { const b = el('div'); Object.assign(b.attrs, { 'data-date': date, 'data-label': label, 'data-record': record }); return b; }
function clockAt(iso) {
  const c = { now: Date.parse(iso) };
  class FakeDate extends Date {
    constructor(...a) { if (a.length) super(...a); else super(c.now); }
    static now() { return c.now; }
  }
  c.Date = FakeDate;
  return c;
}

/* ---------- record_today.js ---------- */
const TODAY_SRC = fs.readFileSync(path.join(__dirname, 'record_today.js'), 'utf8');
const DEVILS = { name: 'Devils ML', market: 'ml', side: 'home', odds: '-162', card_american: -162, units: '5u',
  espn_league: 'hockey/nhl', game: { eid: '401891817', away: 'Philadelphia Flyers', home: 'New Jersey Devils' } };
function runToday({ manifest, history, liveStatus = 404, at = '2026-10-01T20:00:00Z',
                   blocks = [block('2026-10-01', 'Thursday, Oct 1', '1-0'), block('2026-09-30', 'Wednesday, Sep 30', '1-0')] }) {
  const clock = clockAt(at), log = [];
  const mount = el('section'); let tick = null;
  const files = { 'manifest.json': manifest, 'history.json': history };
  const document = {
    hidden: false, getElementById: id => (id === 'rpToday' ? mount : null),
    createDocumentFragment: () => el('#frag'), createElement: el,
    querySelectorAll: sel => (sel === '.rpday[data-date]' ? blocks : []), addEventListener() {} };
  const fetch = url => {
    const f = url.split('?')[0]; log.push(f);
    if (f === 'today_record.json') return Promise.resolve({ ok: liveStatus === 200, status: liveStatus, json: () => Promise.resolve({ date: '', picks: [] }) });
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(JSON.stringify(files[f]))) });
  };
  const ctx = vm.createContext({ document, fetch, Date: clock.Date, Intl, setInterval: fn => { tick = fn; }, console });
  vm.runInContext(TODAY_SRC, ctx);
  return { clock, log, blocks, mount, tick: () => tick() };
}
const HIST_TODAY = { days: [
  { date: '2026-09-30', label: 'Wednesday, Sep 30', record: '1-0', units: '+6.90u', brief: '', picks: [{ name: 'White Sox ML', result: 'W', score: 'CHW 7, HOU 3', _delta: '6.9' }] },
  { date: '2026-10-01', label: 'Thursday, Oct 1', record: '1-0', units: '+3.09u', brief: '',
    picks: [{ name: 'Devils ML', result: 'W', score: 'PHI 2, NJ 3', _delta: '3.0864197530864197', learning: 'Owner-carded override: one data point.' }] }] };

(async () => {
  // LS-18: a 404 on today_record.json is not re-requested every 15 s
  let r = runToday({ manifest: { date: '2026-10-01', picks: [DEVILS] }, history: HIST_TODAY });
  await flush();
  for (let i = 0; i < 3; i++) { r.clock.now += 15000; r.tick(); await flush(); }
  check('LS-18 four polls inside a minute ask for the absent today_record.json once', r.log.filter(f => f === 'today_record.json').length, 1);
  check('LS-18 manifest and history still polled every cycle', r.log.filter(f => f === 'manifest.json').length, 4);
  r.clock.now += 11 * 60000; r.tick(); await flush();
  check('LS-18 asked again after the 10-minute back-off', r.log.filter(f => f === 'today_record.json').length, 2);
  // DI-03: the static block for the painted date is hidden; other days stay listed
  check('DI-03 static Oct 1 block hidden while Today paints Oct 1 picks', r.blocks[0].hidden, true);
  check('DI-03 static Sep 30 block stays visible', r.blocks[1].hidden, false);
  // DI-M2: the pick's learning shows in the Today section
  check('DI-M2 learning shown under the graded pick in Today', textOf(r.mount).includes('Owner-carded override: one data point.'), true);
  // a 200 today_record.json keeps being read every cycle
  r = runToday({ manifest: { date: '2026-10-01', picks: [DEVILS] }, history: HIST_TODAY, liveStatus: 200 });
  await flush(); r.clock.now += 15000; r.tick(); await flush();
  check('LS-18 a present today_record.json is still read every cycle', r.log.filter(f => f === 'today_record.json').length, 2);
  // no carded picks today: the graded static block must stay visible (never in neither place)
  r = runToday({ manifest: { date: '2026-10-01', picks: [] }, history: HIST_TODAY });
  await flush();
  check('DI-03 Today shows no picks -> static Oct 1 block stays visible', r.blocks.map(b => b.hidden), [false, false]);
  // after midnight, before the new card: nothing hidden
  r = runToday({ manifest: { date: '2026-10-01', picks: [DEVILS] }, history: HIST_TODAY, at: '2026-10-02T08:00:00Z' });
  await flush();
  check('DI-03 card not yet published -> every static block visible', r.blocks.map(b => b.hidden), [false, false]);

  // Oct 2 review: an MMA pick carries no event id (before K19). Today dropped it while still hiding
  // that day's static block, so the graded Abushaar L vanished from the page (Today read 2-2, the
  // record 2-3). Rows without an event id are keyed by league + name, and the static block is hidden
  // only while Today paints every graded row of that day.
  const sep29 = (name, eid, league, side, odds) => ({ name, market: 'ml', side, odds, card_american: Number(odds), units: '5u',
    espn_league: league, game: { eid, away: 'A', home: 'B' } });
  const SEP29_CARD = { date: '2026-09-29', picks: [sep29('Braves ML', '401907965', 'baseball/mlb', 'home', '-125'),
    { name: 'Yordan Alvarez over 1.5 hits', market: 'bat_hits', market_class: 'prop', side: 'over', line: 1.5, player: 'Yordan Alvarez',
      odds: '+270', card_american: 270, units: '5u', espn_league: 'baseball/mlb', game: { eid: '401907896', away: 'Chicago White Sox', home: 'Houston Astros' } },
    sep29('Loai Abushaar ML', null, 'mma/ufc', 'home', '+285'), sep29('Maple Leafs ML', '401891811', 'hockey/nhl', 'home', '-150'),
    sep29('Bruins ML', '401891812', 'hockey/nhl', 'home', '-140')] };
  const row29 = (name, result, score) => ({ name, result, score, _delta: '0' });
  const HIST_29 = { days: [{ date: '2026-09-29', label: 'Tuesday, Sep 29', record: '2-3', units: '-0.00u', brief: '', picks: [
    row29('Braves ML', 'W', 'PHI 3, ATL 5'), row29('Yordan Alvarez over 1.5 hits', 'L', 'CHW 6, HOU 3'),
    row29('Loai Abushaar ML', 'L', 'Staines def. Abushaar'), row29('Maple Leafs ML', 'L', 'MTL 3, TOR 2'), row29('Bruins ML', 'W', 'NYR 0, BOS 3')] }] };
  const blocks29 = () => [block('2026-09-29', 'Tuesday, Sep 29', '2-3'), block('2026-09-27', 'Sunday, Sep 27', '5-2')];
  const head = m => { const f = m.children[0] || { children: [] }; const h = f.children[0] || { children: [] }; return (h.children[1] || {}).textContent; };
  r = runToday({ manifest: SEP29_CARD, history: HIST_29, at: '2026-09-30T05:30:00Z', blocks: blocks29() });
  await flush();
  check('MMA row without an event id is painted in Today with its graded L', textOf(r.mount).includes('Loai Abushaar ML') &&
    textOf(r.mount).includes('Staines def. Abushaar'), true);
  check("Today's record equals the graded day (2-3, not 2-2)", head(r.mount), '2-3');
  check('every graded row painted -> the static Sep 29 block is hidden', r.blocks.map(b => b.hidden), [true, false]);
  // a graded row Today cannot paint (two card picks share its name) keeps the static block visible
  const dup = JSON.parse(JSON.stringify(SEP29_CARD));
  dup.picks.push(Object.assign(sep29('Bruins ML', '401891813', 'hockey/nhl', 'away', '+120')));
  r = runToday({ manifest: dup, history: HIST_29, at: '2026-09-30T05:30:00Z', blocks: blocks29() });
  await flush();
  check('a graded row Today cannot paint -> the static Sep 29 block stays visible', r.blocks.map(b => b.hidden), [false, false]);

  /* ---------- yesterday.html view-time selector (built by build_history.py) ---------- */
  const day = (date, label, record, name) => ({ date, label, record, units: '+0.00u', brief: '', picks: [{ name, result: 'W', score: 'A 1, B 2' }] });
  // files: other repo files present when build_history runs (manifests/ snapshots, manifest.json)
  const yesterdayPage = (days, files = {}) => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'rp_pages_'));
    try {
      fs.writeFileSync(path.join(tmp, 'history.json'), JSON.stringify({ days }));
      for (const [rel, obj] of Object.entries(files)) {
        fs.mkdirSync(path.dirname(path.join(tmp, rel)), { recursive: true });
        fs.writeFileSync(path.join(tmp, rel), typeof obj === 'string' ? obj : JSON.stringify(obj));
      }
      execFileSync('python3', [path.join(__dirname, 'build_history.py'), 'history.json'], { cwd: tmp, stdio: 'ignore' });
      return fs.readFileSync(path.join(tmp, 'yesterday.html'), 'utf8');
    } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
  };
  const viewer = yhtml => {
    const script = (yhtml.match(/<script>(\(function\(\)\{var bs=[\s\S]*?)<\/script>/) || [])[1];
    // manifest: what same-origin manifest.json serves at view time (null = the fetch fails);
    // index: what index.html serves (null = the fetch fails)
    return { script, run: async (at, manifest = { date: at.slice(0, 10), picks: [] }, index = null) => {
      const clock = clockAt(at), status = el('div'), none = el('div'); none.hidden = true;
      const pend = yhtml.match(/<div class="nt" id="rpYdNone"([^>]*)>/);
      const pm = pend && pend[1].match(/data-pending="([^"]*)"/);
      if (pm) none.attrs['data-pending'] = pm[1];
      status.textContent = (yhtml.match(/<div class="status">([^<]*)<\/div>/) || [])[1];
      const blocks = [...yhtml.matchAll(/<div class="rpday" data-date="([^"]*)" data-label="([^"]*)" data-record="([^"]*)"( hidden)?>/g)]
        .map(m => Object.assign(block(m[1], m[2], m[3]), { hidden: !!m[4] }));
      const document = { title: '', querySelectorAll: s => (s === '.rpday[data-date]' ? blocks : []),
        querySelector: s => (s === '.status' ? status : null), getElementById: id => (id === 'rpYdNone' ? none : null) };
      const fetch = url => (url.split('?')[0] === 'manifest.json' && manifest
        ? Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(JSON.stringify(manifest))) })
        : url.split('?')[0] === 'index.html' && index != null
        ? Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve(index) })
        : Promise.reject(new Error('offline')));
      if (script) vm.runInContext(script, vm.createContext({ document, fetch, Date: clock.Date, Intl }));
      await flush(); await flush();
      return { status: status.textContent, title: document.title, none: none.hidden ? '' : none.textContent,
               shown: blocks.filter(b => !b.hidden).map(b => b.attrs['data-date']) };
    } };
  };
  // index.html as the builder serves it: its Home line carries the card dates still waiting for grades
  // (data-pending); yesterday.html says '0-0 - no official picks' only once it has read them
  const homePage = pend => '<div class="rphead"><a class="yesrec home-yes" href="record.html" data-ydate="2026-10-01" data-pending="' + pend + '">Yesterday: x</a></div>';
  {
    const { script, run } = viewer(yesterdayPage([day('2026-09-29', 'Tuesday, Sep 29', '2-3', 'Braves ML'), day('2026-09-30', 'Wednesday, Sep 30', '1-0', 'White Sox ML')]));
    check('yesterday.html carries the view-time selector', !!script, true);
    check('yesterday.html on Oct 1 PT shows Sep 30 as Yesterday', await run('2026-10-01T19:00:00Z'),
      { status: 'Yesterday - Wednesday, Sep 30', title: "Yesterday: 1-0 - 'RixPicks", none: '', shown: ['2026-09-30'] });
    check('yesterday.html on Oct 2 PT says Oct 1 had no official picks, Sep 30 as last graded day', await run('2026-10-02T19:00:00Z', undefined, homePage('')),
      { status: 'Last graded day - Wednesday, Sep 30', title: '', none: 'Yesterday, Thursday, Oct 1: 0-0 - no official picks.', shown: ['2026-09-30'] });
    check('yesterday.html on Sep 30 PT evening (Sep 30 already graded) shows Sep 29, never today', await run('2026-10-01T02:00:00Z'),
      { status: 'Yesterday - Tuesday, Sep 29', title: "Yesterday: 2-3 - 'RixPicks", none: '', shown: ['2026-09-29'] });
    // Oct 2 review: no row for yesterday is not proof of no official picks. While manifest.json is
    // still yesterday's card and carries picks, those picks are ungraded: results pending.
    check('yesterday.html on Oct 2 PT, manifest still the Oct 1 card with picks: results pending', await run('2026-10-02T07:30:00Z',
      { date: '2026-10-01', picks: [{ name: 'Devils ML' }, { name: 'Kraken ML' }] }),
      { status: 'Last graded day - Wednesday, Sep 30', title: '', none: 'Yesterday, Thursday, Oct 1: results pending.', shown: ['2026-09-30'] });
    check('yesterday.html on Oct 2 PT, manifest the Oct 1 card with no picks: no official picks', await run('2026-10-02T07:30:00Z',
      { date: '2026-10-01', picks: [] }, homePage('2026-10-02')),
      { status: 'Last graded day - Wednesday, Sep 30', title: '', none: 'Yesterday, Thursday, Oct 1: 0-0 - no official picks.', shown: ['2026-09-30'] });
    check('yesterday.html on Oct 2 PT, manifest unreadable: no claim about Oct 1 either way', await run('2026-10-02T07:30:00Z', null),
      { status: 'Last graded day - Wednesday, Sep 30', title: '', none: '', shown: ['2026-09-30'] });
    // the live card alone is not proof of no picks (the card that had them may be gone already): with the
    // Home page unreadable, or carrying no dates, no '0-0' claim is made
    check('yesterday.html on Oct 2 PT, the Oct 2 card live, Home page unreadable: no 0-0 claim', await run('2026-10-02T19:00:00Z',
      { date: '2026-10-02', picks: [{ name: 'Rangers ML' }] }, null),
      { status: 'Last graded day - Wednesday, Sep 30', title: '', none: '', shown: ['2026-09-30'] });
    check('yesterday.html on Oct 2 PT, the Home line carries no dates (an older build): no 0-0 claim', await run('2026-10-02T19:00:00Z',
      { date: '2026-10-02', picks: [{ name: 'Rangers ML' }] }, '<a class="yesrec home-yes" href="record.html">Yesterday: x</a>'),
      { status: 'Last graded day - Wednesday, Sep 30', title: '', none: '', shown: ['2026-09-30'] });
  }
  {
    // r3 review (yday-2): once the next card replaced manifest.json, an ungraded yesterday read '0-0 - no
    // official picks'. build_history bakes the card dates that carried picks with no graded row (manifests/
    // snapshots, each dated by the builder's rule, plus the live card) into the page; at view time the Home
    // page's own baked dates (index.html, rebuilt by every build) and the live card count too.
    const sox = { name: 'White Sox ML', game: { commence: '2026-09-30T21:00Z' } };
    const files = { 'manifests/manifest-0930aaaaaaaa.json': { date: '2026-09-30', picks: [sox] },
                    'manifests/manifest-0928bbbbbbbb.json': { date: '2026-09-28', picks: [] },
                    'manifests/manifest-1004cccccccc.json': { date: '2026-10-04', preview: true, picks: [{ name: 'Jets ML', game: { commence: '2026-10-04T17:00Z' } }] },
                    'manifest.json': { date: '2026-09-30', picks: [sox] } };
    const yh = yesterdayPage([day('2026-09-29', 'Tuesday, Sep 29', '2-3', 'Braves ML')], files);
    const { run } = viewer(yh);
    const OCT1 = { date: '2026-10-01', picks: [{ name: 'Devils ML', game: { commence: '2026-10-01T23:00Z' } }] };
    check('yesterday.html bakes the pending card dates (Sep 30: carded, no row; no empty card, no preview)',
      (yh.match(/id="rpYdNone" data-pending="([^"]*)"/) || [])[1], '2026-09-30');
    check('yesterday.html on Oct 1 PT, the Oct 1 card live, Sep 30 carded and ungraded: results pending', await run('2026-10-01T17:00:00Z', OCT1),
      { status: 'Last graded day - Tuesday, Sep 29', title: '', none: 'Yesterday, Wednesday, Sep 30: results pending.', shown: ['2026-09-29'] });
    check('yesterday.html on Oct 1 PT, nothing fetchable: the baked dates still say results pending', await run('2026-10-01T17:00:00Z', null),
      { status: 'Last graded day - Tuesday, Sep 29', title: '', none: 'Yesterday, Wednesday, Sep 30: results pending.', shown: ['2026-09-29'] });
    check('yesterday.html on Sep 29 PT (Sep 28 had only an empty card): no official picks', await run('2026-09-29T17:00:00Z', OCT1, homePage('2026-09-30')),
      { status: 'No graded day before today', title: '', none: 'Yesterday, Monday, Sep 28: 0-0 - no official picks.', shown: [] });
    check('yesterday.html on Oct 5 PT (Oct 4 had only a preview): no official picks', await run('2026-10-05T17:00:00Z', OCT1, homePage('2026-09-30')),
      { status: 'Last graded day - Tuesday, Sep 29', title: '', none: 'Yesterday, Sunday, Oct 4: 0-0 - no official picks.', shown: ['2026-09-29'] });
    // a card published after this page was built, and already replaced by the next card: the Home
    // page's baked dates say so (its line carries them, rebuilt by every build)
    const HOME = d => '<a class="yesrec home-yes" href="record.html" data-ydate="2026-10-01" data-pending="' + d + '">Yesterday: results pending</a>';
    const OCT3 = { date: '2026-10-03', picks: [{ name: 'Rangers ML', game: { commence: '2026-10-03T23:00Z' } }] };
    check('yesterday.html on Oct 3 PT, Oct 2 carded after this page was built and replaced by Oct 3: the Home page\'s dates say results pending',
      await run('2026-10-03T17:00:00Z', OCT3, HOME('2026-09-30 2026-10-02 2026-10-03')),
      { status: 'Last graded day - Tuesday, Sep 29', title: '', none: 'Yesterday, Friday, Oct 2: results pending.', shown: ['2026-09-29'] });
    check('yesterday.html on Oct 3 PT, the Home page lists no Oct 2 card: no official picks', await run('2026-10-03T17:00:00Z', OCT3, HOME('2026-09-30 2026-10-03')),
      { status: 'Last graded day - Tuesday, Sep 29', title: '', none: 'Yesterday, Friday, Oct 2: 0-0 - no official picks.', shown: ['2026-09-29'] });
    // the live card's date is the builder's: the most common PT date across its picks (a late game after
    // PT midnight stays on its card), its ISO date only when no pick has a readable start
    const LATE = { date: '2026-10-02', picks: [{ name: 'Devils ML', game: { commence: '2026-10-02T02:00Z' } }, { name: 'Kraken ML', game: { commence: '2026-10-02T03:00Z' } },
                                              { name: 'Sharks ML', game: { commence: '2026-10-02T07:30Z' } }] };
    check('yesterday.html on Oct 2 PT, the live card is the Oct 1 card by its picks (dated Oct 2): results pending', await run('2026-10-02T17:00:00Z', LATE, ''),
      { status: 'Last graded day - Tuesday, Sep 29', title: '', none: 'Yesterday, Thursday, Oct 1: results pending.', shown: ['2026-09-29'] });
  }
  {
    // today graded already and yesterday had no card: the last graded day BEFORE today is shown
    const { run } = viewer(yesterdayPage([day('2026-09-27', 'Sunday, Sep 27', '5-2', 'Lions ML'), day('2026-09-30', 'Wednesday, Sep 30', '1-0', 'White Sox ML')]));
    check('yesterday.html on Sep 30 PT evening, no Sep 29 card: says so, shows Sep 27, never today', await run('2026-10-01T02:00:00Z', { date: '2026-09-30', picks: [{ name: 'White Sox ML' }] }, homePage('2026-09-30')),
      { status: 'Last graded day - Sunday, Sep 27', title: '', none: 'Yesterday, Tuesday, Sep 29: 0-0 - no official picks.', shown: ['2026-09-27'] });
  }

  console.log(failures ? 'FAILURES: ' + failures : 'ALL CHECKS PASS');
  process.exit(failures ? 1 : 0);
})();
