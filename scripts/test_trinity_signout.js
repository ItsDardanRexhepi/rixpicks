// Signing out of Trinity's chat puts it back at her intro: the greeting and the suggestions, nothing said while signed
// in left on the page or in the tab's storage. A sign-in that was asked for and never opened is not a sign-out and
// clears nothing. The conversation she is sent (`turns`) never carries a row from a sign-in, a passphrase or a
// signed-in conversation, and nothing at all is sent with it while a sign-in is open or asked for. Runs
// trinity/trinity.js as shipped against a small DOM and a scripted endpoint.
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
let replies = [];
const sent = [];
const fetch = (url, opts) => { if (url.endsWith('/ask')) sent.push(JSON.parse(opts.body)); const body = url.endsWith('/ask') ? (replies.shift() || { answer: 'ok' }) : {}; return Promise.resolve({ status: 200, json: () => Promise.resolve(body) }); };
const last = () => sent[sent.length - 1];
const turnText = b => (b.turns || []).map(t => t.who + ':' + t.text).join(' | ');
const window = { addEventListener() {} };
const timers = [];
new Function('window', 'document', 'sessionStorage', 'fetch', 'location', 'setInterval', 'MutationObserver', 'AbortController', code)(
  window, document, sessionStorage, fetch, { reload() {} }, (f, t) => { timers.push(f); return 1; }, undefined, undefined);
const log = els.trLog, rows = () => log.children.map(r => r.children[0] ? r.children[0].textContent : r.textContent);
const say = async (q, reply) => { replies.push(reply); els.trInput.value = q; els.trAsk.handlers.submit[0]({ preventDefault() {} }); for (let i = 0; i < 10; i++) await new Promise(r => setImmediate(r)); };
let fails = 0; const check = (c, l) => { console.log((c ? 'OK   ' : 'FAIL ') + l); if (!c) fails++; };
(async () => {
  check(rows().length === 1 && /Trinity/.test(rows()[0]), 'the tab opens on her greeting');
  await say('what is on the card?', { answer: 'Nothing carded yet today.' });
  check(Array.isArray(last().turns) && last().turns.length === 1 && last().turns[0].who === 'her' && /Trinity/.test(last().turns[0].text),
        'a public question goes with what was said before it, her greeting included');
  check(!turnText(last()).includes('what is on the card'), 'and not with itself');
  await say("It’s Sam", { answer: 'Hi Sam. What is your passphrase?', session: 'pending-1', next: 'passphrase' });
  check(Array.isArray(last().turns) && !last().session, 'saying a name is still a public message');
  await say('invented passphrase', { answer: 'Welcome back, Sam.', session: 'sess-1', as: 'Sam' });
  check(!('turns' in last()) && last().session === 'pending-1', 'a passphrase is sent with its token and no conversation');
  await say('what is the record?', { answer: 'Thirty-three and seventeen.' });
  check(!('turns' in last()) && last().session === 'sess-1', 'signed in, no conversation is sent: the Mac keeps their own');
  check(rows().length === 9 && sessionStorage.getItem('trinity_session') === 'sess-1', 'signed in, the conversation is on the page');
  await say('sign out', { answer: 'Signed out. Talk soon, Sam.', session: '' });
  check(rows().length === 1 && /Trinity/.test(rows()[0]), 'after sign-out only her greeting is on the page');
  check(!els.trChips.hidden, 'and the suggestions are back');
  check(JSON.parse(sessionStorage.getItem('trinity_log')).length === 1, "the tab's stored conversation holds only the greeting");
  check(!sessionStorage.getItem('trinity_session') && !sessionStorage.getItem('trinity_session_who') && els.trWho.hidden, 'and nobody is signed in');
  await say('hello', { answer: 'Hey.' });
  check(!/Sam|what is the record|Thirty|passphrase|on the card/i.test(turnText(last())), 'after sign-out nothing said before or while signed in is sent');
  await say("It’s Sam", { answer: 'Hi Sam. What is your passphrase?', session: 'pending-2', next: 'passphrase' });
  await say('wrong one', { answer: 'That did not match, so nothing is open.', session: '' });
  check(rows().length === 7, 'a sign-in that never opened clears nothing');
  await say('and yesterday?', { answer: 'Yesterday was quiet too.' });
  const t = turnText(last());
  check(/me:hello/.test(t) && /her:Hey\./.test(t), 'the next public question goes with the public conversation before it');
  check(!/Sam|passphrase|wrong one|did not match|\u2022/i.test(t), `and with no row of the sign-in that failed (${t})`);
  const stored = JSON.parse(sessionStorage.getItem('trinity_log'));
  check(stored.filter(m => m.p).length === 4, 'the four rows of that sign-in are kept as private in the tab');
  console.log(fails ? `trinity sign-out: ${fails} FAILED` : 'trinity sign-out: ALL PASS');
  process.exit(fails ? 1 : 0);
})();
