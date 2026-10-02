#!/usr/bin/env node
/* News time + blurb display fixture (Oct 1 sweep, LS-06 / OS-13).
   ESPN RSS stamps many stories with its feed-refresh time labelled EST, 30-60 min ahead of the
   real clock; the page showed them as '1m ago' with the NEW marker and sorted them first. A feed
   blurb of the literal string 'null' rendered as content. Display rules under test:
   - a published time more than 5 min in the future is unknown: no age, no NEW, sorted as undated
   - small clock skew (<= 5 min ahead) still reads '1m ago'
   - a 'null' / 'undefined' / 'none' blurb is no blurb
   Extracts the real helpers from scripts/index_v2.js and runs them in a vm sandbox.
   Run: node scripts/test_news_time_guard.js */
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
const src = fs.readFileSync(process.argv[2] || path.join(__dirname, 'index_v2.js'), 'utf8');

let failures = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'OK   ' : 'FAIL ') + label + (ok ? '' : `  [want ${JSON.stringify(want)} got ${JSON.stringify(got)}]`));
}
function extract(name) {
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) { failures++; console.log('FAIL ' + name + ' present in index_v2.js'); return ''; }
  let depth = 0;
  for (let i = start; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) return src.slice(start, i + 1); }
  }
  failures++; console.log('FAIL ' + name + ' balanced'); return '';
}
const skew = (src.match(/^var RP_FUTURE_SKEW=\d+;/m) || [''])[0];
if (!skew) { failures++; console.log('FAIL RP_FUTURE_SKEW present in index_v2.js'); }

const NOW = Date.now(), M = 60000;
const iso = t => new Date(t).toISOString();
const ctx = vm.createContext({ Date, JSON, Math, String, Number, Object, Array, RegExp, isFinite,
  RP_LOAD: NOW - 10 * M, NEWSF: null, DNEWS: {}, isPublishableNews: () => true });
vm.runInContext([skew, extract('pubT'), extract('ago'), extract('isNewIt'), extract('newsBlurb'),
  extract('normH'), extract('newsBucket')].join('\n'), ctx);
const call = (fn, ...a) => { try { return ctx[fn](...a); } catch (e) { return 'THROW ' + e.message; } };

// ages
check('future story (+30 min, RSS refresh stamp) shows no age', call('ago', iso(NOW + 30 * M)), '');
check('future story (+60 min) shows no age', call('ago', iso(NOW + 60 * M)), '');
check('small clock skew (+2 min) still reads 1m ago', call('ago', iso(NOW + 2 * M)), '1m ago');
check('real 10-min-old story reads 10m ago', call('ago', iso(NOW - 10 * M)), '10m ago');
check('real 3-hour-old story reads 3h ago', call('ago', iso(NOW - 180 * M)), '3h ago');
check('missing time shows no age', call('ago', ''), '');
// NEW marker
check('future story carries no NEW marker', !!call('isNewIt', { published: iso(NOW + 30 * M) }), false);
check('story published after page load is NEW', !!call('isNewIt', { published: iso(NOW - 2 * M) }), true);
check('story published before page load is not NEW', !!call('isNewIt', { published: iso(NOW - 20 * M) }), false);
// ordering: a future-stamped story never sorts ahead of real recent ones
ctx.NEWSF = { leagues: { 'hockey/nhl': [
  { headline: 'Bettman eyes no-trade clauses', published: iso(NOW + 30 * M), source: 'ESPN' },
  { headline: 'Barkov exits early at Sharks', published: iso(NOW - 5 * M), source: 'ESPN' },
  { headline: 'Kraken top Flames behind Dunn', published: iso(NOW - 25 * M), source: 'CBS' },
] } };
const order = call('newsBucket', { key: 'home', espn: '' });
check('future-stamped story sorts as undated (last), real times first',
  Array.isArray(order) ? order.map(a => a.headline.split(' ')[0]) : order, ['Barkov', 'Kraken', 'Bettman']);
// blurbs
check("literal 'null' blurb is no blurb", call('newsBlurb', { blurb: 'null' }), '');
check("' NULL ' blurb is no blurb", call('newsBlurb', { blurb: ' NULL ' }), '');
check("'undefined' blurb is no blurb", call('newsBlurb', { blurb: 'undefined' }), '');
check('JSON null blurb is no blurb', call('newsBlurb', { blurb: null }), '');
check('real blurb is kept', call('newsBlurb', { blurb: 'Browns cement win over Steelers.' }), 'Browns cement win over Steelers.');
check("blurb that merely contains 'null' is kept", call('newsBlurb', { blurb: 'Goal nullified by review' }), 'Goal nullified by review');
// the carousel reads both through the helpers
check('carousel uses newsBlurb for the blurb', /var blurb=newsBlurb\(a\)/.test(src), true);
check('carousel drops the separator when there is no age', /\(_age\?' \\u00b7 '\+esc\(_age\):''\)/.test(src), true);

if (failures) { console.error(failures + ' FAILURES'); process.exit(1); }
console.log('news time guard fixture: ALL PASS');
