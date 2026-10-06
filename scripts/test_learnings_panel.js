#!/usr/bin/env node
/* What the system is learning - the Home panel's live repaint (rpLearnPanel in index_v2.js).
   The builder bakes the first paint; the page re-reads history.json on load and every 120 s while
   visible, cache-busted and no-store, and repaints #rpLearn only when its content changed:
     - same content as on the page: no repaint;
     - changed content: one repaint, escaped (a hostile note is text, never markup), each day under
       its own label with its own brief;
     - a pick graded later by the chain (its lesson as `learning`, no note) repaints at the top of its day;
     - a failed read, an HTTP error, unparseable or wrong-shaped JSON: the page keeps what it shows;
     - a readable ledger with nothing to show: heading and box hidden, shown again when there is;
     - no #rpLearn on the page (the build had nothing to show): nothing fetched.
   Extracts the real functions from scripts/index_v2.js and runs them in a vm sandbox with a fake
   DOM and fetch (no jsdom). The builder/client markup parity lives in test_learnings_panel.py.
   Run: node scripts/test_learnings_panel.js */
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
const code = ['$', 'esc', 'rpLearnHtml', 'rpLearnPanel'].map(extract).join('\n');
check('index_v2.js runs the panel on load and every 120 s while visible',
  /\nrpLearnPanel\(\);setInterval\(function\(\)\{if\(!document\.hidden\)rpLearnPanel\(\);\},120000\);/.test(src));

const flush = () => new Promise(r => setImmediate(r));
const pk = (name, result, note, extra) => Object.assign({ name, game: 'vs X', odds: '-110', units: '5u', result, score: '1-0', note }, extra || {});
const LEDGER_A = { days: [{ date: '2026-10-01', label: 'Thursday, Oct 1', record: '1-0', units: '+1.00u', brief: 'First brief.',
  picks: [pk('Devils ML', 'W', 'Form read held.')] }] };
const LEDGER_B = { days: LEDGER_A.days.concat([{ date: '2026-10-02', label: 'Friday, Oct 2', record: '0-1', units: '-5.00u', brief: '',
  picks: [pk('Rangers ML', 'L', '<img src=x onerror=alert(1)>', { added_after_kickoff: true })] }]) };
// the record_final chain appends a later-graded row to Oct 2: its lesson rides as `learning`, no note
const LEDGER_C = { days: [LEDGER_B.days[0], Object.assign({}, LEDGER_B.days[1], { record: '1-1', units: '0.00u',
  picks: LEDGER_B.days[1].picks.concat([{ name: 'Knicks ML', game: 'vs Celtics', odds: '+120', units: '5u', result: 'W', score: 'BOS 99, NYK 104',
    _delta: '6.0', learning: 'Chain lesson: the pace read held.' }]) })] };
const LEDGER_QUIET = { days: [{ date: '2026-10-02', label: 'Friday, Oct 2', record: '1-0', units: '+1.00u', brief: '', picks: [pk('Quiet ML', 'W')] }] };

function page(opts) {
  const o = opts || {};
  let html = o.initial || '', sets = 0;
  const box = { style: {}, get innerHTML() { return html; }, set innerHTML(v) { html = String(v); sets++; } };
  const hd = { style: {} };
  const els = o.noMount ? {} : { rpLearn: box, rpLearnHead: hd };
  const asked = [];
  const document = {
    hidden: false,
    getElementById: id => els[id] || null,
    // a template parses and re-serializes; identity stands in for the browser's serializer here
    createElement: tag => { const t = { tag, _h: '' }; Object.defineProperty(t, 'innerHTML', { get() { return this._h; }, set(v) { this._h = String(v); } }); return t; },
  };
  let answer = o.answer;
  const fetch = (url, init) => {
    asked.push({ url, init });
    const a = typeof answer === 'function' ? answer() : answer;
    if (a === 'reject') return Promise.reject(new Error('offline'));
    if (a === 'http500') return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) });
    if (a === 'badjson') return Promise.resolve({ ok: true, status: 200, json: () => Promise.reject(new SyntaxError('bad json')) });
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(JSON.stringify(a))) });
  };
  const ctx = vm.createContext({ document, fetch, Date, Promise, String, Array, JSON });
  vm.runInContext(code, ctx);
  return {
    ctx, box, hd, asked,
    set answer(v) { answer = v; },
    get html() { return html; }, get sets() { return sets; },
    async run() { vm.runInContext('rpLearnPanel();', ctx); for (let i = 0; i < 5; i++) await flush(); },
  };
}

(async () => {
  const htmlA = page().ctx.rpLearnHtml(LEDGER_A), htmlB = page().ctx.rpLearnHtml(LEDGER_B);
  check('fixture ledgers render', !!htmlA && !!htmlB && htmlA !== htmlB);

  // the baked first paint already shows ledger A: nothing to repaint
  let p = page({ initial: htmlA, answer: LEDGER_A });
  await p.run();
  check('same content as the page: no repaint', p.sets === 0 && p.html === htmlA, p.sets);
  check('reads history.json cache-busted, no-store', p.asked.length === 1 && /^history\.json\?cb=\d+$/.test(p.asked[0].url) && p.asked[0].init && p.asked[0].init.cache === 'no-store',
    JSON.stringify(p.asked));
  check('section left shown', p.box.style.display === '' && p.hd.style.display === '');

  // a pick grades: the ledger gains a day - one repaint, newest first, escaped, tagged
  p.answer = LEDGER_B;
  await p.run();
  check('changed content: one repaint', p.sets === 1 && p.html === htmlB, p.sets);
  check('newest day first after the repaint', p.html.indexOf('Friday, Oct 2') >= 0 && p.html.indexOf('Friday, Oct 2') < p.html.indexOf('Thursday, Oct 1'));
  check('hostile note is text, never markup', p.html.indexOf('<img') < 0 && p.html.indexOf('&lt;img src=x onerror=alert(1)&gt;') >= 0);
  check('added-after-kickoff tag shown', p.html.indexOf('<span class="lntag">added after kickoff</span>') >= 0);
  check('each day shows its own brief: Oct 1 its own under its label, Oct 2 (none filed) none',
    p.html.indexOf('<div class="lnday">Thursday, Oct 1</div><div class="lnbrief">First brief.</div>') >= 0
    && p.html.indexOf('<div class="lnday">Friday, Oct 2</div><div class="lnitem">') >= 0 && p.html.split('lnbrief').length === 2);
  await p.run();
  check('next tick, same ledger: no further repaint', p.sets === 1, p.sets);

  // the chain grades another Oct 2 pick (learning, no note): one repaint, newest-graded first in its day
  p.answer = LEDGER_C;
  await p.run();
  const kn = p.html.indexOf('Knicks ML'), rg = p.html.indexOf('Rangers ML');
  check('chain-graded pick: one more repaint, its learning shown', p.sets === 2 && p.html.indexOf('Chain lesson: the pace read held.') >= 0, p.sets);
  check('chain-graded pick sits first in its day (newest graded first)', kn >= 0 && rg > kn && rg < p.html.indexOf('Thursday, Oct 1'));

  // failures keep what the page shows
  for (const [why, ans] of [['fetch rejected', 'reject'], ['HTTP 500', 'http500'], ['unparseable JSON', 'badjson'],
                            ['JSON not a ledger (list)', []], ['days not a list', { days: 'x' }], ['null body', null]]) {
    const q = page({ initial: htmlA, answer: ans });
    await q.run();
    check(why + ': page keeps the baked content, section shown', q.sets === 0 && q.html === htmlA && q.box.style.display !== 'none' && q.hd.style.display !== 'none',
      q.sets + ' ' + q.box.style.display);
  }

  // a readable ledger with nothing to show hides the section; it comes back when there is
  p = page({ initial: htmlA, answer: LEDGER_QUIET });
  await p.run();
  check('nothing to show: heading and box hidden, content untouched', p.box.style.display === 'none' && p.hd.style.display === 'none' && p.sets === 0);
  p.answer = LEDGER_B;
  await p.run();
  check('learnings again: heading and box shown, repainted', p.box.style.display === '' && p.hd.style.display === '' && p.sets === 1 && p.html === htmlB);

  // the build had nothing to show (no #rpLearn): nothing is fetched
  p = page({ noMount: true, answer: LEDGER_B });
  await p.run();
  check('no mount on the page: nothing fetched', p.asked.length === 0);

  console.log(failures ? failures + ' FAIL' : 'ALL OK');
  process.exit(failures ? 1 : 0);
})();
