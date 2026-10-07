// A signed-in change is followed quickly while it is young: the page asks how it is going two seconds after she takes
// it and every two seconds for its first half minute, then backs off as before (8 s, 20 s, a minute). Runs
// trinity/trinity.js as shipped against a small DOM, a scripted endpoint, and a clock and timers this test drives.
const fs = require('fs');
const code = fs.readFileSync(__dirname + '/../trinity/trinity.js', 'utf8');
function El(id) {
  const e = { id, children: [], parentNode: null, hidden: false, style: {}, attrs: {}, handlers: {}, className: '', value: '',
    scrollTop: 0, scrollHeight: 0, clientHeight: 0, disabled: false, type: 'text', _text: '',
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
    removeChild(c) { this.children = this.children.filter(x => x !== c); c.parentNode = null; return c; },
    addEventListener(t, f) { (this.handlers[t] = this.handlers[t] || []).push(f); },
    setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; },
    querySelector() { return El('q'); }, focus() {}, click() {},
    classList: { _s: new Set(), contains(c) { return this._s.has(c); }, add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); }, toggle(c, on) { on ? this._s.add(c) : this._s.delete(c); } } };
  Object.defineProperty(e, 'textContent', { get() { return this._text + this.children.map(c => c.textContent || '').join(''); }, set(v) { this._text = String(v); this.children = []; } });
  return e;
}
const els = {}; ['st-trinity', 'trLog', 'trChips', 'trAsk', 'trInput', 'trSend', 'trWho', 'trPhoto', 'trFile'].forEach(i => { els[i] = El(i); });
els['st-trinity'].classList.add('on');
const mem = {}; const sessionStorage = { getItem: k => (k in mem ? mem[k] : null), setItem: (k, v) => { mem[k] = String(v); }, removeItem: k => { delete mem[k]; } };
const document = { readyState: 'complete', body: El('body'), getElementById: i => els[i] || null, querySelector: () => null, querySelectorAll: () => [],
  createElement: t => El(t), createTextNode: t => { const n = El('#text'); n._text = String(t); return n; }, addEventListener() {} };
let now = 1000000;
class FakeDate extends Date { static now() { return now; } }
let timers = [], tid = 0;
const setTimeoutF = (f, ms) => { timers.push({ f, ms, id: ++tid }); return tid; };
const clearTimeoutF = id => { timers = timers.filter(t => t.id !== id); };
const replies = []; const jobs = [];
const fetch = (url, opts) => {
  const body = url.endsWith('/ask') ? (replies.shift() || { answer: 'ok' }) : url.endsWith('/job') ? (jobs.shift() || { answer: 'Working on it.', done: false }) : {};
  return Promise.resolve({ status: 200, json: () => Promise.resolve(body) });
};
const window = { addEventListener() {} };
new Function('window', 'document', 'sessionStorage', 'fetch', 'location', 'setInterval', 'MutationObserver', 'AbortController', 'setTimeout', 'clearTimeout', 'Date', code)(
  window, document, sessionStorage, fetch, { reload() {} }, () => 1, undefined, undefined, setTimeoutF, clearTimeoutF, FakeDate);
const flush = async () => { for (let i = 0; i < 12; i++) await new Promise(r => setImmediate(r)); };
const say = async (q, reply) => { replies.push(reply); els.trInput.value = q; els.trAsk.handlers.submit[0]({ preventDefault() {} }); await flush(); };
const pollTimer = () => timers.filter(t => t.ms !== 45000).slice(-1)[0];
const run = async (t) => { timers = timers.filter(x => x !== t); t.f(); await flush(); };
let fails = 0; const check = (c, l) => { console.log((c ? 'OK   ' : 'FAIL ') + l); if (!c) fails++; };
(async () => {
  await say("It's Sam", { answer: 'Hi Sam. What is your passphrase?', session: 'pending-1', next: 'passphrase' });
  await say('invented passphrase', { answer: 'Welcome back, Sam.', session: 'sess-abcdefghijklmnopqrstuvwx', as: 'Sam' });
  timers = [];
  await say('make the banner slightly more blue', { answer: 'Queued.', job: '20261007-120000-owner-abcdef', as: 'Sam' });
  let t = pollTimer();
  check(t && t.ms === 2000, `the first ask about a new change is two seconds after she takes it (${t && t.ms})`);
  now += 2000; await run(t);
  t = pollTimer();
  check(t && t.ms === 2000, `while the change is young it is asked about every two seconds (${t && t.ms})`);
  now += 25000; await run(t);
  t = pollTimer();
  check(t && t.ms === 2000, `still young at twenty-seven seconds (${t && t.ms})`);
  now += 10000; await run(t);
  t = pollTimer();
  check(t && t.ms === 8000, `past half a minute the asking backs off to eight seconds (${t && t.ms})`);
  now += 200000; await run(t);
  t = pollTimer();
  check(t && t.ms === 20000, `and further after two minutes (${t && t.ms})`);
  jobs.push({ answer: 'It is live.', done: true });
  now += 20000; await run(t);
  check(!pollTimer() || pollTimer().ms === 45000, 'a finished change is not asked about again');
  console.log(fails ? `trinity follow: ${fails} FAILED` : 'trinity follow: ALL PASS');
  process.exit(fails ? 1 : 0);
})();
