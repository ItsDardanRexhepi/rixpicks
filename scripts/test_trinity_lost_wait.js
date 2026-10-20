// NOTHING WAITS FOR EVER on the page (owner, 2026-10-14, signed in on rix-picks.com: endless typing dots after
// Trinity's chat service restarted while his question was being answered). An id the Mac will never answer comes back
// `gone`; a question (signed in too, when the Mac says beside its id that it is one) is asked once more with the dots
// still showing, and nothing that may change something is ever sent twice; after six minutes on one id the dots stop,
// she says the answer did not come back, and "Ask again" sends the same question a tap away; a phone that slept past
// the limit asks once more first; a reload keeps all of it. STILL WRITING IS NEVER THROWN AWAY (2026-10-13 review: a
// 564-second answer finished after the page gave up at six minutes and was lost): while the Mac says `writing` beside
// a pending id the dots stay past six minutes, however long, and the answer lands.
// Runs trinity/trinity.js as shipped against a small DOM, a scripted endpoint and a clock this test drives.
// Run: node scripts/test_trinity_lost_wait.js
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
    // The edge's own thirty seconds running out on a line that dropped: a 503 after thirty seconds.
    if (step === 'edge-timeout') return new Promise(ok => setTimeoutF(() => ok({ status: 503, json: () => Promise.resolve({ error: 'not answering right now' }) }), 30000));
    // The Mac holding a question for its own wait (twenty seconds) before handing back the id.
    if (step === 'held-pending') return new Promise(ok => setTimeoutF(() => ok({ status: 200, json: () => Promise.resolve({ pending: 'P'.repeat(32) }) }), 20000));
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
  // The phone sleeps: the clock moves and no timer runs; then it wakes and the page hears that it is visible again.
  const sleep = (ms) => { now += ms; (docHandlers.visibilitychange || []).forEach(f => f()); };
  return { els, sent, script, advance, flush, her, typing, say, docHandlers, sleep };
}

let fails = 0;
const check = (c, l) => { console.log((c ? 'OK   ' : 'FAIL ') + l); if (!c) fails++; };
const P = 'P'.repeat(32), Q = 'Q'.repeat(32);
const SESSION = { trinity_session: 'S'.repeat(30), trinity_session_who: 'Sam' };
const asks = p => p.sent.filter(s => s.url.endsWith('/ask'));
const replies = p => p.sent.filter(s => s.url.endsWith('/reply'));
const last = p => p.her().slice(-1)[0] || '';
function againButton(p) {
  const rowsHer = p.els.trLog.children.filter(r => /\bher\b/.test(r.className));
  const r = rowsHer[rowsHer.length - 1];
  const b = r && r.children[0];
  return b ? b.children.find(c => /tr-again/.test(c.className)) : null;
}

(async () => {
  // ---- signed in: a QUESTION whose answer was lost (the Mac said it may be asked again) is asked once more
  {
    const p = page(Object.assign({}, SESSION));
    p.script.ask.push({ status: 200, body: { pending: P, again: true } }, { status: 200, body: { pending: Q, again: true } });
    p.script.reply.push({ status: 404, body: { error: 'no such answer', gone: true } },
                        { status: 200, body: { answer: 'No card for tomorrow yet: UltRix runs at 6:00 AM.', answered: true, cites: [], as: 'Sam' } });
    await p.say("What're some good picks for tomorrows games?");
    await p.advance(1);
    const a = asks(p);
    check(a.length === 2 && a[1].body.question === a[0].body.question && a[1].body.session === 'S'.repeat(30),
      `signed in, a lost question is asked once more, the same question, with the session (${a.length} asks)`);
    check(/No card for tomorrow yet/.test(last(p)) && !p.typing() && !p.her().some(h => /could not confirm/.test(h)),
      `and her answer lands with no word of the loss ("${last(p)}")`);
  }
  // ---- signed in: anything the Mac did not call a question is never sent twice
  {
    const p = page(Object.assign({}, SESSION));
    p.script.ask.push({ status: 200, body: { pending: P, again: false } });
    p.script.reply.push({ status: 404, body: { error: 'no such answer', gone: true } });
    await p.say('put a note on the tab saying hi');
    await p.advance(1);
    check(asks(p).length === 1 && /could not confirm/.test(last(p)) && !againButton(p) && !p.typing(),
      'signed in, an order whose answer was lost is said as unconfirmed, never sent twice, and not offered again');
  }
  // ---- `gone` in so many words is gone, whatever the status
  {
    const p = page({});
    p.script.ask.push({ status: 200, body: { pending: P, again: true } }, { status: 200, body: { answer: 'Here.', answered: true, cites: [] } });
    p.script.reply.push({ status: 200, body: { gone: true } });
    await p.say('a question');
    await p.advance(1);
    check(asks(p).length === 2 && last(p) === 'Here.', 'a reply that says gone is taken as gone, and the question asked once more');
  }
  // ---- the Mac says "still writing" for ever: after six minutes the dots stop and she says so, with Ask again
  {
    const p = page({});
    p.script.ask.push({ status: 200, body: { pending: P, again: true } });
    for (let i = 0; i < 40; i++) p.script.reply.push({ status: 200, body: { pending: P } });
    await p.say('what is on the card today?');
    await p.advance(5 * 60 * 1000);
    check(p.typing(), 'at five minutes she is still writing, the dots showing');
    await p.advance(2 * 60 * 1000);                     // six minutes, and the one ask still held on the Mac then
    const n = replies(p).length;
    check(!p.typing() && /did not come back/.test(last(p)) && !/cannot reach/.test(last(p)),
      `after six minutes the dots stop and she says plainly the answer did not come back ("${last(p)}")`);
    check(!p.els.trSend.disabled, 'and the box can send again');
    await p.advance(60 * 1000);
    check(replies(p).length === n, 'and the page stops asking for it');
    const btn = againButton(p);
    check(!!btn && btn.textContent === 'Ask again', 'she offers to ask again, a tap away');
    p.script.ask.push({ status: 200, body: { answer: "Today's card has two picks.", answered: true, cites: [] } });
    btn.handlers.click[0]();
    await p.advance(1);
    const a = asks(p);
    check(a.length === 2 && a[1].body.question === 'what is on the card today?' && last(p) === "Today's card has two picks.",
      'the tap sends the same question again, and her answer lands');
  }
  // ---- the Mac says she is STILL WRITING past six minutes: the dots stay and the answer lands, never thrown away
  {
    const store = {};
    const p = page(store);
    p.script.ask.push({ status: 200, body: { pending: P, again: true } });
    for (let i = 0; i < 30; i++) p.script.reply.push({ status: 200, body: { pending: P, writing: true } });
    p.script.reply.push({ status: 200, body: { answer: 'Here is the long one, 564 seconds in.', answered: true, cites: [] } });
    await p.say('which starting pitchers have the best ERA this postseason?');
    await p.advance(7 * 60 * 1000);
    check(p.typing() && !p.her().some(h => /did not come back/.test(h)),
      'at seven minutes, the Mac saying she is still writing, the dots are still there and nothing was given up');
    const kept = JSON.parse(store.trinity_wait || '{}');
    check(kept.id === P && now - kept.at < 60 * 1000, 'and the kept wait is fresh, so a reload picks it up');
    await p.advance(3 * 60 * 1000);
    check(last(p) === 'Here is the long one, 564 seconds in.' && !p.typing() && asks(p).length === 1,
      `at ten minutes her answer lands, asked once ("${last(p)}")`);
  }
  // ---- signed in, past the limit, an order is not offered again
  {
    const p = page(Object.assign({}, SESSION));
    p.script.ask.push({ status: 200, body: { pending: P, again: false } });
    for (let i = 0; i < 40; i++) p.script.reply.push({ status: 200, body: { pending: P } });
    await p.say('make the background blue');
    await p.advance(7 * 60 * 1000);
    check(!p.typing() && /cannot tell whether it went through/.test(last(p)) && !againButton(p),
      'signed in, an order that did not come back is said as unconfirmed, with no offer to send it again');
  }
  // ---- lost twice: said plainly, with the offer to ask again
  {
    const p = page({});
    p.script.ask.push({ status: 200, body: { pending: P, again: true } }, { status: 200, body: { pending: Q, again: true } });
    p.script.reply.push({ status: 404, body: { gone: true } }, { status: 404, body: { gone: true } });
    await p.say('a hard one');
    await p.advance(1);
    check(asks(p).length === 2 && /lost my place/.test(last(p)) && !!againButton(p) && !p.typing(),
      'lost twice, it is said plainly, not sent a third time by itself, and offered again');
  }
  // ---- a phone asleep past the limit asks once more before it gives up
  {
    const p = page({});
    p.script.ask.push({ status: 200, body: { pending: P, again: true } });
    p.script.reply.push({ status: 200, body: { pending: P } },
                        { status: 200, body: { answer: 'It finished while you were away.', answered: true, cites: [] } });
    await p.say('a long one');
    await p.advance(10000);                               // an ask is held on the Mac
    p.sleep(8 * 60 * 1000);                               // the phone sleeps eight minutes, then wakes
    await p.advance(1);
    check(last(p) === 'It finished while you were away.' && !p.typing(),
      `a phone that slept past the limit still gets the answer that finished meanwhile ("${last(p)}")`);
  }
  // ---- a reload keeps the question, so a loss after it is still asked once more
  {
    const store = {};
    const p = page(store);
    p.script.ask.push({ status: 200, body: { pending: P, again: true } });
    p.script.reply.push({ status: 200, body: { pending: P } });
    await p.say('the record this week?');
    await p.advance(1);
    const kept = JSON.parse(store.trinity_wait || '{}');
    check(kept.id === P && kept.q === 'the record this week?', 'the wait is kept with its question');
    const q2 = page(store);
    q2.script.reply.push({ status: 404, body: { gone: true } });
    q2.script.ask.push({ status: 200, body: { answer: 'This week: 3-1.', answered: true, cites: [] } });
    await q2.advance(1);
    check(asks(q2).length === 1 && asks(q2)[0].body.question === 'the record this week?' && last(q2) === 'This week: 3-1.',
      'after a reload a lost question is asked once more and her answer lands');
  }
  console.log(fails ? `trinity lost wait: ${fails} FAILED` : 'trinity lost wait: ALL PASS');
  process.exit(fails ? 1 : 0);
})();
