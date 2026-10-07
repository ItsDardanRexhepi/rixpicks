#!/usr/bin/env node
/* Upcoming Events panel fixture (Oct 1 sweep, LS-04 + LS-05).
   LS-04: Home -> another tab -> Home inside the 5-min refetch guard must repaint the rows already
          fetched; the panel was left on the other tab's 'Loading upcoming events...' (or its rows).
   LS-05: day-scoped leagues (MLB/NHL/...) must be read one ESPN day per request, today through +3
          - the bare scoreboard still serves yesterday's finals after midnight ET and a dates=A-B
          range answers 400 - and NASCAR must use racing/nascar-premier (racing/nascar is a 400).
   Extracts the real loadSide/renderGames/helpers from scripts/index_v2.js and runs them in a vm
   sandbox against a stub fetch shaped like ESPN's live answers. No DOM needed.
   Run: node scripts/test_home_games_panel.js */
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const src = fs.readFileSync(process.argv[2] || path.join(__dirname, 'index_v2.js'), 'utf8');

let failures = 0;
function check(label, cond, extra) {
  if (!cond) failures++;
  console.log((cond ? 'OK   ' : 'FAIL ') + label + (cond || extra === undefined ? '' : '  [' + extra + ']'));
}
function extract(name) {
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) { check(name + ' present in index_v2.js', false); return ''; }
  let depth = 0;
  for (let i = start; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) return src.slice(start, i + 1); }
  }
  check(name + ' balanced', false); return '';
}

const NOW = Date.now(), H = 3600000;
const ev = (id, state, at, a, h) => ({ id, date: new Date(at).toISOString(), shortName: a + ' @ ' + h,
  competitions: [{ status: { type: { state } }, competitors: [
    { homeAway: 'away', team: { abbreviation: a } }, { homeAway: 'home', team: { abbreviation: h } }] }] });
const etDay = (() => { const p = {}; new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date()).forEach(x => { p[x.type] = x.value; }); return p.year + p.month + p.day; })();

const urls = [];
function stubFetch(u) {
  urls.push(u);
  const ok = body => Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
  const bad = () => Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve({ code: 400 }) });
  if (/[?&]dates=\d{8}-/.test(u)) return bad();                       // ESPN: ranges answer 400
  if (u.includes('/sports/racing/nascar/')) return bad();             // ESPN: racing/nascar answers 400
  if (u.includes('/sports/racing/nascar-premier/')) return ok({ events: [ev('nas1', 'pre', NOW + 50 * H, 'Cup', 'Charlotte')] });
  const day = (u.match(/[?&]dates=(\d{8})/) || [])[1];
  if (u.includes('/baseball/mlb/')) {
    if (!day) return ok({ events: [ev('mlbF', 'post', NOW - 10 * H, 'ATL', 'SD')] });   // bare board: yesterday's final only
    return ok({ events: day === etDay ? [] : [ev('mlb' + day, 'pre', NOW + 30 * H, 'ATL', 'LAD')] });
  }
  if (u.includes('/hockey/nhl/')) {
    if (!day) return ok({ events: [ev('nhlF', 'post', NOW - 3 * H, 'TB', 'NYR')] });
    return ok({ events: [ev('nhl1', 'pre', NOW + 20 * H, 'NYR', 'DET')] });   // same game on every day board
  }
  if (u.includes('/football/nfl/')) return ok({ events: [ev('nfl1', 'pre', NOW + 60 * H, 'KC', 'BUF')] });
  return ok({ events: [] });
}

function el() {
  const cls = new Set();
  return { innerHTML: '', classList: { add: c => cls.add(c), remove: c => cls.delete(c), contains: c => cls.has(c),
    toggle: (c, on) => (on === undefined ? (cls.has(c) ? cls.delete(c) : cls.add(c)) : (on ? cls.add(c) : cls.delete(c))) } };
}
const gb = el();
const TABS = { home: { key: 'home', label: 'Home', espn: '' }, wooder: { key: 'wooder', label: 'Picks from Wooder Ice', espn: '' }, past: { key: 'past', label: 'Past Tickets', espn: '' }, trinity: { key: 'trinity', label: 'Trinity', espn: '' } };
const ctx = vm.createContext({
  Date, JSON, Intl, Math, String, Number, Array, Object, parseInt, parseFloat, isFinite, Promise,
  setTimeout, clearTimeout, AbortController, encodeURIComponent,
  fetch: stubFetch,
  $: id => (id === 'rpGames' ? gb : null),
  refreshX: () => {}, renderSocial: () => {}, renderNews: () => {}, newsBucket: () => [], tickRender: () => {},
  socMapRetry: () => {}, rpMapFresh: () => true, rpNewsOk: () => true, isPublishableNews: () => true,
  RP_LIVE_OK: {}, RP_GAME_ROUTES: {}, SB: {}, SB_TS: {}, DNEWS: {}, DNEWS_TS: {},
  NEWSF: { generated_at: 'x' }, NEWSF_TS: NOW + 3600000, SOC_MATCH_OK: false,
  HOME_GAMES_TS: 0, HOME_GAMES_PAINT: null, cur: null, TABS,
});
vm.runInContext(['esc', 'lgpath', 'until', 'dayTime', 'renderGames', 'rpEspnDays', 'loadSide'].map(extract).join('\n'), ctx);
const settle = () => new Promise(r => setTimeout(r, 30));
const rows = () => (gb.innerHTML.match(/class="grow"/g) || []).length;

(async () => {
  // first Home load
  ctx.cur = TABS.home; vm.runInContext('loadSide(TABS.home)', ctx); await settle();
  const first = gb.innerHTML, n0 = urls.length;
  check('Home lists upcoming rows', rows() > 0, rows());
  check('no request goes to racing/nascar (400 route)', !urls.some(u => u.includes('/sports/racing/nascar/')));
  check('NASCAR reads racing/nascar-premier', urls.some(u => u.includes('/sports/racing/nascar-premier/scoreboard')));
  check('no dates=A-B range request (ESPN answers 400)', !urls.some(u => /dates=\d{8}-/.test(u)));
  const mlbDays = urls.filter(u => u.includes('/baseball/mlb/')).map(u => (u.match(/dates=(\d{8})/) || [])[1]);
  check('MLB is read one ESPN day per request, today (ET) through +3', mlbDays.length === 4 && mlbDays[0] === etDay && mlbDays.every(Boolean), JSON.stringify(mlbDays));
  check('NHL is read one ESPN day per request', urls.filter(u => /\/hockey\/nhl\/scoreboard\?limit=50&dates=\d{8}$/.test(u)).length === 4);
  check('NFL stays one week-board request', urls.filter(u => u.includes('/football/nfl/')).length === 1);
  check('MLB games inside 72h are listed', /MLB &middot; ATL @ LAD/.test(first));
  check('NHL games inside 72h are listed', /NHL &middot; NYR @ DET/.test(first));
  check('NASCAR event is listed', /NASCAR &middot; Cup @ Charlotte/.test(first));
  check('an event seen on several day boards lists once', (first.match(/NYR @ DET/g) || []).length === 1, (first.match(/NYR @ DET/g) || []).length);

  // LS-04: Past Tickets, then back to Home inside the 5-min guard
  ctx.cur = TABS.past; vm.runInContext('loadSide(TABS.past)', ctx); await settle();
  // Past Tickets and Trinity have no league of their own and show Home's every-league list (2026-10-07: both sat
  // on 'Loading upcoming events' for good, which an earlier check here expected).
  check('on Past Tickets: the every-league list, never a stuck Loading', gb.innerHTML === first, gb.innerHTML.slice(0, 80));
  ctx.cur = TABS.trinity; vm.runInContext('loadSide(TABS.trinity)', ctx); await settle();
  check('on Trinity: the every-league list, never a stuck Loading', gb.innerHTML === first, gb.innerHTML.slice(0, 80));
  ctx.cur = TABS.home; vm.runInContext('loadSide(TABS.home)', ctx); await settle();
  check('back on Home: fetched rows repaint (no stuck Loading)', gb.innerHTML === first, gb.innerHTML.slice(0, 80));
  check('back on Home: panel is the all-league list again (homeall)', gb.classList.contains('homeall'));
  check('back on Home inside the guard: no refetch', urls.length === n0, urls.length - n0);

  // Wooder Ice (NFL scoreboard in the same panel), then Home again
  ctx.cur = TABS.wooder; vm.runInContext('loadSide(TABS.wooder)', ctx); await settle();
  check('Wooder tab shows its NFL board', /KC @ BUF/.test(gb.innerHTML) && !/MLB &middot;/.test(gb.innerHTML));
  ctx.cur = TABS.home; vm.runInContext('loadSide(TABS.home)', ctx); await settle();
  check('back on Home after Wooder: Home rows, not the NFL board', gb.innerHTML === first);

  // steady Home: the 30s tick must not re-render rows already showing
  gb.innerHTML = first + '<!--marker-->';
  vm.runInContext('loadSide(TABS.home)', ctx); await settle();
  check('30s tick on Home leaves the painted panel alone', gb.innerHTML.endsWith('<!--marker-->'));

  if (failures) { console.error(failures + ' FAILURES'); process.exit(1); }
  console.log('home games panel fixture: ALL PASS');
})();
