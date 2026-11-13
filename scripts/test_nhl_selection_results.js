/* Deterministic policy regression, not evidence of live-feed availability. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const window = { RPSlip: {}, dispatchEvent() {} };
const document = { readyState: 'loading', createElement: () => ({}), head: { appendChild() {} }, addEventListener() {} };
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', 'rp-slip-adapter.js'), 'utf8'), {
  window, document, Date, Intl, Event: function () {}, setInterval() {}, setTimeout, clearTimeout
});
const app = window.RPApp, games = app._games;
const spec = { sport: 'NHL', resolveFinal: true, selectionOnly: true, source: 'Not placed · RixPicks',
  legs: [1, 2, 3].map(id => ({ player: 'Fixture player ' + id, market: 'goals', line: 1,
    x: { nhlGame: id, nhlPlayer: id, commence: '2026-11-13T00:30:00Z' } })) };
const now = Date.parse('2026-11-13T01:30:00Z');
let passed = 0;
function test(name, fn) { Object.keys(games).forEach(k => delete games[k]); fn(); passed++; console.log('PASS ' + name); }
function game(id, state, value) { games['nhl:' + id] = { state, ts: now, stat: () => value, score: 'A 1 – B 0' }; }
function derive(s = spec) { return app._derive(s, now); }
test('unknown feed does not invent a final stat or result', () => {
  const out = derive(); assert.equal(out.status, 'open'); assert(out.legs.every(l => l.final === undefined));
});
test('pregame stays open with original verified start', () => {
  [1, 2, 3].forEach(id => game(id, 'pre', null));
  const out = app._derive(spec, now - 7200000); assert.equal(out.status, 'open');
  assert(out.legs.every(l => l.startsAt === '2026-11-13T00:30:00.000Z' && l.final === undefined));
});
test('live zero is not a confirmed failure', () => {
  [1, 2, 3].forEach(id => game(id, 'in', 0)); assert.equal(derive().status, 'live');
});
test('one confirmed final miss ends an opted-in selection immediately', () => {
  game(1, 'post', 0); game(2, 'in', 1); game(3, 'pre', null);
  const out = derive(); assert.equal(out.status, 'lost'); assert.equal(out.legs[0].status, 'miss');
  assert.equal(out.legs[2].final, undefined);
});
test('all final mixed legs resolve failed without financial totals', () => {
  game(1, 'post', 1); game(2, 'post', 0); game(3, 'post', 0);
  const out = derive(); assert.equal(out.status, 'lost'); assert.equal(out.total, undefined);
  assert.equal(out.source, 'Not placed · RixPicks');
});
test('all hits while live do not assert a final win', () => {
  [1, 2, 3].forEach(id => game(id, 'in', 1)); assert.equal(derive().status, 'live');
});
test('all exact final hits resolve a win', () => {
  [1, 2, 3].forEach(id => game(id, 'post', 1)); assert.equal(derive().status, 'won');
});
test('missing final athlete stat keeps unresolved selection open', () => {
  game(1, 'post', 1); game(2, 'post', null); game(3, 'post', 1);
  const out = derive(); assert.equal(out.status, 'open'); assert.equal(out.legs[1].final, undefined);
});
test('other card policies remain unchanged without opt-in', () => {
  [1, 2, 3].forEach(id => game(id, 'post', 0));
  assert.equal(derive({ ...spec, resolveFinal: false }).status, 'open');
});
test('explicit archived status remains authoritative', () => {
  [1, 2, 3].forEach(id => game(id, 'post', 1)); assert.equal(derive({ ...spec, status: 'lost' }).status, 'lost');
});
test('selection-only archive label is limited to explicitly unplaced rows', () => {
  const entry = { id: 'fixture', title: 'NHL - fixture', result: 'lost', game_date: '2026-11-12',
    selection_only: true, status: 'NOT PLACED', legs: [{ player: 'Fixture', market: '1+ goals', status: 'lost', final_stat: 0 }] };
  assert.equal(app._mapHistory(entry).spec.selectionOnly, true);
  assert.equal(app._mapHistory({ ...entry, status: 'PLACED - reported' }).spec.selectionOnly, undefined);
});
console.log(passed + ' NHL selection policy checks passed');
