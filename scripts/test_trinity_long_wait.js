// THE LONG WAIT on the page (owner, 2026-10-13: full Fable 5.1 capability on the site). At her highest effort with her
// web tools an answer can take minutes; the page used to give up at 45 seconds and say she was offline. Now every
// question says it can wait; an answer not ready inside the Mac's own wait comes back as an id, and the page asks
// /reply with it until her answer is there, showing her typing dots the whole time, never timing out while the Mac
// says she is still working, asking again after a dropped line, and picking the wait back up after a reload.
// Runs trinity/trinity.js as shipped against a small DOM, a scripted endpoint and a clock this test drives.
// Run: node scripts/test_trinity_long_wait.js
const fs = require('fs');
const code = fs.readFileSync(__dirname + '/../trinity/trinity.js', 'utf8');

function El(id) {
  const e = { id, children: [], parentNode: null, hidden: false, style: {}, attrs: {}, handlers: {}, className: '', value: '',
    scrollTop: 0, scrollHeight: 0, clientHeight: 0, disabled: false, type: 'text', _text: '',
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
    removeChild(c) { this.children = this.children.filter(x => x !== c); c.parentNode = null; return c; },
    insertBefore(c) { this.children.unshift(c); c.parentNode = this; return c; },
    addEventListener(t, f) { (this.handlers[t] = this.handlers[t] || []).push(f); },
    setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; }, removeAttribute(k) { delete this.attrs[k]; },
    querySelector() { return El('q'); }, focus() {}, click() {},
    classList: { _s: new Set(), contains(c) { return this._s.has(c); }, add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); }, toggle(c, on) { on ? this._s.add(c) : this._s.delete(c); } } };
  Object.defineProperty(e, 'textContent', { get() { return this._text + this.children.map(c => c.textContent || '').join(''); }, set(v) { this._text = String(v); this.children = []; } });
  return e;
}

let now = 1_000_000;
class FakeDate extends Date { static now() { return now; } }

function page(store) {
  const els = {};
  ['st-trinity', 'trLog', 'trChips', 'trAsk', 'trInput', 'trSend', 'trWho', 'trPhoto', 'trFile'].forEach(i => { els[i] = El(i); });
  els['st-trinity'].classList.add('on');
  const sessionStorage = { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } };
  const docHandlers = {};
  const document = { readyState: 'complete', body: El('body'), activeElement: null, getElementById: i => els[i] || null,
    querySelector: () => null, querySelectorAll: () => [], createElement: t => El(t),
    createTextNode: t => { const n = El('#text'); n._text = String(t); return n; },
    addEventListener(t, f) { (docHandlers[t] = docHandlers[t] || []).push(f); }, hidden: false };
  let timers = [], tid = 0;
  const setTimeoutF = (f, ms) => { timers.push({ f, at: now + (ms || 0), id: ++tid }); return tid; };
  const clearTimeoutF = id => { timers = timers.filter(t => t.id !== id); };
  const sent = [];
  const script = { ask: [], reply: [] };
  const fetch = (url, opts) => {
    const body = opts && opts.body ? JSON.parse(opts.body) : null;
    sent.push({ url, body });
    const route = url.endsWith('/ask') ? 'ask' : url.endsWith('/reply') ? 'reply' : url.endsWith('/upload') ? 'ask' : 'other';
    if (route === 'other') return Promise.resolve({ status: 200, json: () => Promise.resolve({ v: 1, rev: 0, items: [], gone: [] }) });
    const step = script[route].shift();
    if (step === 'drop') return Promise.reject(new TypeError('Load failed'));
    const s = step || { status: 200, body: { pending: 'P'.repeat(32) } };
    const res = { status: s.status, json: () => Promise.resolve(s.body) };
    // The Mac holds an ask for an answer still being written for its own wait (twenty seconds) before it says so.
    if (route === 'reply' && s.body && s.body.pending) return new Promise(ok => setTimeoutF(() => ok(res), 20000));
    return Promise.resolve(res);
  };
  const window = { addEventListener() {}, CSS: undefined };
  new Function('window', 'document', 'sessionStorage', 'fetch', 'location', 'setInterval', 'MutationObserver', 'AbortController',
    'setTimeout', 'clearTimeout', 'Date', 'URL', code)(
    window, document, sessionStorage, fetch, { reload() {} }, () => 1, undefined, undefined, setTimeoutF, clearTimeoutF, FakeDate,
    { createObjectURL: () => 'blob:x', revokeObjectURL() {} });
  const flush = async () => { for (let i = 0; i < 20; i++) await new Promise(r => setImmediate(r)); };
  // Move the clock forward, running every timer that falls due on the way, in order.
  const advance = async (ms) => {
    const until = now + ms;
    for (;;) {
      await flush();
      const due = timers.filter(t => t.at <= until).sort((a, b) => a.at - b.at)[0];
      if (!due) break;
      timers = timers.filter(t => t !== due);
      now = Math.max(now, due.at);
      due.f();
    }
    now = until;
    await flush();
  };
  const rows = () => els.trLog.children.map(r => ({ cls: r.className, text: r.textContent }));
  const her = () => rows().filter(r => /\bher\b/.test(r.cls) && !/tr-pending/.test(r.cls)).map(r => r.text);
  const typing = () => rows().some(r => /tr-pending/.test(r.cls));
  const say = async (q) => { els.trInput.value = q; els.trAsk.handlers.submit[0]({ preventDefault() {} }); await flush(); };
  return { els, sent, script, advance, flush, her, typing, say, docHandlers };
}

let fails = 0;
const check = (c, l) => { console.log((c ? 'OK   ' : 'FAIL ') + l); if (!c) fails++; };
const P = 'P'.repeat(32);

(async () => {
  // ---- a public question whose answer takes two and a half minutes
  {
    const store = {};
    const p = page(store);
    p.script.ask.push({ status: 200, body: { pending: P } });
    for (let i = 0; i < 7; i++) p.script.reply.push({ status: 200, body: { pending: P } });
    p.script.reply.push({ status: 200, body: { answer: 'The total is 8.5, per ESPN.', answered: true, cites: [] } });
    await p.say("what's the total on the Dodgers game tonight?");
    const ask = p.sent.find(s => s.url.endsWith('/ask'));
    check(ask && ask.body.wait === true, 'every question says it can wait for a long answer');
    check(p.typing(), 'her typing dots show while she works');
    let polls = 0;
    for (let t = 0; t < 6; t++) { await p.advance(20000); }
    polls = p.sent.filter(s => s.url.endsWith('/reply')).length;
    check(p.typing() && !p.her().some(h => /cannot reach/.test(h)) && polls >= 6,
      `still waiting with the dots after two minutes, past the old 45 s limit, and never "offline" (${polls} asks)`);
    check(p.sent.filter(s => s.url.endsWith('/reply')).every(s => s.body.pending === P && !('session' in s.body)),
      'each ask names the id, and a visitor sends no session');
    check(p.els.trSend.disabled, 'one message at a time: sending waits while she is writing');
    await p.advance(40000);
    check(!p.typing() && p.her().slice(-1)[0] === 'The total is 8.5, per ESPN.', 'her answer lands when it is ready');
    check(!p.els.trSend.disabled, 'and the box can send again');
    check(!('trinity_wait' in store), 'the wait is cleared once the answer is in');
    // the follow-up carries the conversation
    p.script.ask.push({ status: 200, body: { answer: 'The under is -105.', answered: true, cites: [] } });
    await p.say('and the under?');
    const ask2 = p.sent.filter(s => s.url.endsWith('/ask')).slice(-1)[0];
    check(ask2 && Array.isArray(ask2.body.turns) && ask2.body.turns.some(t => t.who === 'her' && /8\.5/.test(t.text)),
      '"and the under?" goes with the conversation so far, her long answer in it');
    check(p.her().slice(-1)[0] === 'The under is -105.', 'and a quick answer comes in the first request');
  }
  // ---- a dropped line while waiting is asked again; a phone waking asks at once
  {
    const p = page({});
    p.script.ask.push({ status: 200, body: { pending: P } });
    p.script.reply.push('drop', 'drop', { status: 200, body: { answer: 'Here it is.', answered: true, cites: [] } });
    await p.say('a hard one');
    await p.advance(1);
    await p.advance(3000);
    await p.advance(5000);
    check(p.her().slice(-1)[0] === 'Here it is.', 'a dropped ask is tried again, and the answer still lands');
  }
  // ---- an id the Mac no longer holds is said plainly
  {
    const p = page({});
    p.script.ask.push({ status: 200, body: { pending: P } });
    p.script.reply.push({ status: 404, body: { error: 'no such answer' } });
    await p.say('a hard one');
    await p.advance(1);
    const last = p.her().slice(-1)[0] || '';
    check(/lost my place/.test(last) && !p.typing(), `a lost answer is said plainly ("${last}")`);
  }
  // ---- a reload in the middle of the wait picks it back up
  {
    const store = {};
    const p = page(store);
    p.script.ask.push({ status: 200, body: { pending: P } });
    p.script.reply.push({ status: 200, body: { pending: P } });
    await p.say('a long one');
    await p.advance(1);
    check(store.trinity_wait && JSON.parse(store.trinity_wait).id === P, 'the wait is kept for this tab while she works');
    const q = page(store);                                 // the same tab, reloaded
    q.script.reply.push({ status: 200, body: { answer: 'Back with it.', answered: true, cites: [] } });
    await q.advance(1);
    check(q.her().slice(-1)[0] === 'Back with it.', 'after a reload the page goes on waiting and her answer lands');
  }
  // ---- signed in: the session goes with each ask
  {
    const store = { trinity_session: 'S'.repeat(30), trinity_session_who: 'Sam' };
    const p = page(store);
    p.script.ask.push({ status: 200, body: { pending: P } });
    p.script.reply.push({ status: 200, body: { answer: 'For you.', answered: true, cites: [], as: 'Sam' } });
    await p.say('my question');
    await p.advance(1);
    const asks = p.sent.filter(s => s.url.endsWith('/ask'));
    const reps = p.sent.filter(s => s.url.endsWith('/reply'));
    check(asks[0].body.wait === true && asks[0].body.session === 'S'.repeat(30), 'signed in, the question says it can wait too');
    check(reps.length && reps.every(s => s.body.session === 'S'.repeat(30)), 'and each ask for the answer carries the session');
    check(p.her().slice(-1)[0] === 'For you.', 'her answer lands');
  }
  console.log(fails ? `trinity long wait: ${fails} FAILED` : 'trinity long wait: ALL PASS');
  process.exit(fails ? 1 : 0);
})();
