'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(process.argv[2] || path.join(__dirname, '..', 'index.html'), 'utf8');
const script = Array.from(html.matchAll(/<script>([\s\S]*?)<\/script>/g), m => m[1])
  .find(source => source.includes('var tb=document.getElementById("rpNflFutBody")'));
assert.ok(script, 'NFL futures renderer must be present');
assert.match(html, /Recorded quote<\/th>/);

const observed = '2025-03-01T12:10:00Z';
const newer = '2025-04-01T12:20:00Z';
const upcoming = '2099-01-01T12:00:00Z';
const kalshi = (at, cents) => ({status: 'active', quoted_at: at, ask_c: cents});
const poly = (at, cents, verified = true) => ({verified, quoted_at: at, cents});
const pick = (team, kq, pm, extra) => ({
  team, market: 'Example market', league: 'NFL', odds: '+100', kalshi_quote: kq, polymarket_com: pm, ...extra
});

async function render(data, ok = true) {
  const body = {innerHTML: ''}, note = {textContent: ''};
  const document = {getElementById: id => id === 'rpNflFutBody' ? body : note};
  const fetch = async url => {
    assert.match(url, /^futures\.json\?/);
    return {ok, json: async () => data};
  };
  vm.runInNewContext(script, {document, fetch, Date, Intl}, {timeout: 1000});
  await new Promise(resolve => setImmediate(resolve));
  return {rows: Array.from(body.innerHTML.matchAll(/<tr>(.*?)<\/tr>/gs), m => m[1]), note: note.textContent};
}

(async () => {
  const input = [
    pick('A', kalshi(observed, 50), poly(newer, 25)),
    pick('B', kalshi(upcoming, 80), poly(newer, 25)),
    pick('C', kalshi(null, 70), poly(observed, 25, false)),
    pick('D', kalshi('2025-03-01T12:10:00', 70)),
    pick('E', kalshi('invalidZ', 80), poly(upcoming, 50)),
    pick('F', kalshi(observed, 100), poly(newer, -1)),
    pick('G', kalshi(observed, 75)),
    pick('H', kalshi(observed, 50), null, {settlement: {status: 'SETTLED'}}),
    pick('I', kalshi(observed, 50), null, {league: 'WNBA'})
  ];
  const {rows, note} = await render({futures: input});
  assert.equal(rows.length, 7, 'only open NFL futures belong in the table');
  assert.match(rows[0], /Kalshi ask/);
  assert.ok(rows[0].includes(new Date(observed).toISOString()));
  assert.match(rows[0], /Mar 1, 2025.*4:10.*PST/);
  assert.match(rows[0], /Unchanged · 50.0%/);
  assert.doesNotMatch(rows[0], /Polymarket|▲|▼/);
  assert.match(rows[1], /Polymarket/);
  assert.match(rows[1], /Apr 1, 2025.*5:20.*PDT/);
  assert.match(rows[1], /▼ 50.0% → 25.0%/);
  for (const row of rows.slice(2, 6)) {
    assert.match(row, /Unavailable/);
    assert.doesNotMatch(row, /<time|nx-move|Kalshi ask|Polymarket/);
  }
  assert.match(rows[6], /▲ 50.0% → 75.0%/);
  assert.match(note, /observation time/);
  assert.doesNotMatch(note, /current market price/);
  assert.match((await render([])).rows[0], /No open NFL futures/);
  assert.match((await render(null, false)).rows[0], /Futures unavailable/);
  console.log('NFL futures passed for dated quotes, source fallback, unavailable data, direction, empty and offline states');
})().catch(error => { console.error(error); process.exitCode = 1; });
