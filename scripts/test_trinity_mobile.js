// Trinity's chat on a phone: the passphrase stays masked and out of the conversation whatever happens to the send
// (a dropped line, a limit, a reload, storage that throws); on an iPhone the masked box is a fresh box, so the
// keyboard's autocorrect and capitals are really off; a sign-in that ends on its own says why; a change sent once is
// sent once; a change is followed past half an hour and never dropped in silence; a photo's failure says how far it
// got; a photo picked mid-answer is not lost; and signed in, the chat box does not widen the page.
// Runs trinity/trinity.js as shipped (or TRINITY_JS=<file>) against a small DOM, a scripted endpoint and a fake
// clock. Run: node scripts/test_trinity_mobile.js
const fs = require('fs');
const path = require('path');
const SRC = process.env.TRINITY_JS || path.join(__dirname, '..', 'trinity', 'trinity.js');
const code = fs.readFileSync(SRC, 'utf8');
const css = fs.readFileSync(path.join(__dirname, '..', 'trinity', 'trinity.css'), 'utf8');

function page(opts) {
  opts = opts || {};
  let clock = opts.clock || 1e12;
  const timers = [];
  let tid = 0;
  const setTimeout_ = (f, ms) => { const t = { id: ++tid, f, at: clock + (ms || 0) }; timers.push(t); return t.id; };
  const clearTimeout_ = (id) => { const i = timers.findIndex(t => t.id === id); if (i >= 0) timers.splice(i, 1); };
  const doc = { activeElement: null };
  function El(tag) {
    const e = { tagName: tag, id: '', children: [], parentNode: null, hidden: false, style: {}, attrs: {}, handlers: {},
      className: '', value: '', scrollTop: 0, scrollHeight: 0, clientHeight: 0, disabled: false, type: 'text', _text: '',
      spellcheck: true, placeholder: '', files: null, focusLog: [],
      appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
      insertBefore(c, ref) { const i = this.children.indexOf(ref); this.children.splice(i < 0 ? this.children.length : i, 0, c); c.parentNode = this; return c; },
      removeChild(c) { this.children = this.children.filter(x => x !== c); c.parentNode = null; if (doc.activeElement === c) doc.activeElement = null; return c; },
      addEventListener(t, f) { (this.handlers[t] = this.handlers[t] || []).push(f); },
      setAttribute(k, v) { this.attrs[k] = String(v); if (k === 'id') this.id = String(v); },
      getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
      removeAttribute(k) { delete this.attrs[k]; if (k === 'id') this.id = ''; },
      querySelector(sel) { return sel === '.tr-bub' ? (this.children[0] || El('q')) : El('q'); },
      focus() { doc.activeElement = this; this.focusLog.push({ ts: this.style.webkitTextSecurity || '', ac: this.attrs.autocorrect, cap: this.attrs.autocapitalize, sp: this.spellcheck }); },
      click() { (this.handlers.click || []).forEach(f => f({})); },
      cloneNode() { const n = El(this.tagName); n.id = this.id; n.attrs = Object.assign({}, this.attrs); n.style = Object.assign({}, this.style);
        n.type = this.type; n.spellcheck = this.spellcheck; n.placeholder = this.placeholder; n.value = this.value; n.className = this.className; return n; },
      getContext() { return { drawImage() {} }; },
      toBlob(cb) { cb({ size: 10, type: 'image/jpeg' }); },
      classList: { _s: new Set(), contains(c) { return this._s.has(c); }, add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); }, toggle(c, on) { on ? this._s.add(c) : this._s.delete(c); } } };
    Object.defineProperty(e, 'textContent', { get() { return this._text + this.children.map(c => c.textContent || '').join(''); }, set(v) { this._text = String(v); this.children.forEach(c => { c.parentNode = null; }); this.children = []; } });
    return e;
  }
  const els = {};
  ['st-trinity', 'trLog', 'trChips', 'trAsk', 'trInput', 'trSend', 'trWho', 'trPhoto', 'trFile'].forEach(i => { els[i] = El(i === 'trAsk' ? 'form' : 'div'); els[i].id = i; });
  els.trPhoto.hidden = true;
  els['st-trinity'].classList.add('on');
  els.trAsk.appendChild(els.trInput);
  els.trAsk.appendChild(els.trSend);
  els['st-trinity'].appendChild(els.trAsk);
  const store = opts.store || {};
  const sessionStorage = opts.throwingStorage ? {
    getItem() { throw new Error('SecurityError'); }, setItem() { throw new Error('SecurityError'); }, removeItem() { throw new Error('SecurityError'); }
  } : { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } };
  const byId = (i) => {
    if (i === 'trInput') { const f = (n) => n.id === 'trInput' ? n : n.children.map(f).find(Boolean); return f(els.trAsk) || null; }
    return els[i] || null;
  };
  const document = Object.assign(doc, { readyState: 'complete', hidden: false, body: El('body'), getElementById: byId,
    querySelector: () => null, querySelectorAll: () => [], createElement: t => El(t),
    createTextNode: t => { const n = El('#text'); n._text = String(t); return n; },
    addEventListener(t, f) { (doc._h = doc._h || {})[t] = (doc._h[t] || []).concat(f); } });
  const calls = [];
  const route = opts.route || (() => ({ status: 200, body: { answer: 'ok' } }));
  const fetch = (url, init) => {
    const body = init && init.body ? JSON.parse(init.body) : null;
    calls.push({ url, body });
    return new Promise((ok, no) => {
      const u = url.replace(/^.*\/trinity/, '');
      const r = u === '/about' ? { status: 404, body: {} } : route(u, body, calls);
      if (r === 'throw') return no(new TypeError('Load failed'));
      const res = { status: r.status, json: () => (r.raw !== undefined ? Promise.reject(new SyntaxError('bad')) : Promise.resolve(r.body)) };
      if (r.delay) setTimeout_(() => ok(res), r.delay); else ok(res);
    });
  };
  const window = { addEventListener(t, f) { (window._h = window._h || {})[t] = (window._h[t] || []).concat(f); }, CSS: { supports: () => true } };
  class Image { set src(v) { setTimeout_(() => { if (opts.decodes === false) this.onerror(); else { this.naturalWidth = 4000; this.naturalHeight = 3000; this.onload(); } }, 0); } }
  const URL_ = { createObjectURL: () => 'blob:x', revokeObjectURL() {} };
  class FileReader { readAsDataURL() { this.result = 'data:image/jpeg;base64,QUJD'; setTimeout_(() => this.onload(), 0); } }
  new Function('window', 'document', 'sessionStorage', 'fetch', 'location', 'setInterval', 'MutationObserver', 'AbortController',
    'setTimeout', 'clearTimeout', 'Date', 'CSS', 'Image', 'URL', 'FileReader', code)(
    window, document, sessionStorage, fetch, { reload() {} }, () => 1, undefined, undefined,
    setTimeout_, clearTimeout_, { now: () => clock }, window.CSS, Image, URL_, FileReader);
  const flush = async () => { for (let i = 0; i < 12; i++) await new Promise(r => setImmediate(r)); };
  const advance = async (ms) => {
    const end = clock + ms;
    for (;;) {
      await flush();
      timers.sort((a, b) => a.at - b.at || a.id - b.id);
      const t = timers[0];
      if (!t || t.at > end) break;
      timers.shift();
      clock = Math.max(clock, t.at);
      t.f();
    }
    clock = end;
    await flush();
  };
  const input = () => byId('trInput');
  const rows = () => els.trLog.children.map(r => r.children[0] ? r.children[0].textContent : r.textContent);
  // The passphrase box is its own form, put in the chat form's place while a passphrase is asked for.
  const secretForm = () => els['st-trinity'].children.find(c => /tr-secret/.test(c.className || '')) || null;
  const secret = () => { const f = secretForm(); return f ? f.children.find(c => c.tagName === 'input') : null; };
  const say = async (q, opts2) => {
    const f = secretForm(), i = f ? secret() : input();
    i.value = q;
    if (!(opts2 && opts2.blurred)) doc.activeElement = i;
    (f || els.trAsk).handlers.submit[0]({ preventDefault() {} });
    await advance(opts2 && opts2.wait != null ? opts2.wait : 30000);
  };
  const chatClean = () => { const i = input(); return !i.style.webkitTextSecurity && i.type === 'text' && i.placeholder !== 'Passphrase'; };
  const masked = () => { const sb = secret(); return !!sb && sb.style.webkitTextSecurity === 'disc' && sb.attrs.autocorrect === 'off' && sb.attrs.autocapitalize === 'off' && sb.spellcheck === false && els.trAsk.style.display === 'none' && chatClean(); };
  const pickPhoto = async (wait) => { els.trFile.files = [{ name: 'p.jpg' }]; els.trFile.handlers.change[0]({}); await advance(wait == null ? 30000 : wait); };
  return { els, store, calls, advance, say, rows, input, masked, secret, secretForm, chatClean, doc, document, window, pickPhoto, get clock() { return clock; } };
}

let fails = 0;
const check = (c, l) => { console.log((c ? 'OK   ' : 'FAIL ') + l); if (!c) fails++; };
const PASS = 'quiet meadow 42';
const CLAIM = { status: 200, body: { answer: 'Hi Matthew. What is your passphrase?', session: 'pend-token-0000000000000001', next: 'passphrase', answered: true } };
const WELCOME = { status: 200, body: { answer: 'Welcome, Matthew.', session: 'sess-token-00000000000000001', as: 'Matthew', answered: true } };
const keptHas = (p, t) => String(p.store.trinity_log || '').indexOf(t) >= 0;
const asks = (p) => p.calls.filter(c => c.url.endsWith('/ask'));

(async () => {
  // SI-1 / SI-05 (a): a dropped line on the passphrase send leaves the box masked and the token held
  {
    let n = 0;
    const p = page({ route: (u) => u === '/ask' ? [CLAIM, 'throw', WELCOME][n++] : { status: 200, body: {} } });
    await p.say('It’s Matthew');
    check(p.masked(), 'the name asks for a passphrase and the box is masked');
    await p.say(PASS);
    check(asks(p).length === 2, 'a passphrase sent with a sign-in token is sent once, never re-sent by the page');
    check(p.masked() && !!p.store.trinity_session, 'after the line drops the box is still masked and the sign-in is still held');
    check(/could not confirm/.test(p.rows().slice(-1)[0]), 'and she says she could not confirm it, not the offline line');
    await p.say(PASS);
    check(!p.rows().some(r => r.indexOf(PASS) >= 0) && !keptHas(p, PASS), 'the retyped passphrase is shown as dots and never kept');
    check(asks(p)[2].body.session === CLAIM.body.session, 'and it goes with the sign-in token');
    check(!p.masked() && p.els.trWho.hidden === false && p.els.trPhoto.hidden === false, 'signed in, the box is unmasked');
  }
  // SI-1 (b): a limit on the passphrase send
  {
    let n = 0;
    const p = page({ route: () => [CLAIM, { status: 429, body: { answer: 'Too many questions at once. Give it a moment.', answered: false } }][n++] });
    await p.say('It’s Matthew');
    await p.say(PASS);
    check(p.masked(), 'after a 429 on the passphrase the box is still masked');
  }
  // SI-1 (c) / L1: a reload at the prompt comes back masked
  {
    const store = {};
    const p1 = page({ store, route: () => CLAIM });
    await p1.say('It’s Matthew');
    const p2 = page({ store, route: () => WELCOME });
    p2.els.trInput.value = '';
    check(p2.masked(), 'a reload at the passphrase prompt comes back masked');
    await p2.say(PASS);
    check(!p2.rows().some(r => r.indexOf(PASS) >= 0) && !keptHas(p2, PASS), 'and the passphrase typed after it is dots and not kept');
  }
  // SI-1: an expired session that starts a new sign-in drops the old name, so the prompt is masked
  {
    let n = 0;
    const p = page({ route: () => [CLAIM, WELCOME, { status: 200, body: { answer: 'Hi Matthew. What is your passphrase?', session: 'pend-token-0000000000000002', next: 'passphrase' } }, 'throw'][n++] });
    await p.say('It’s Matthew'); await p.say(PASS);
    await p.say('It’s Matthew');
    check(p.els.trWho.hidden && p.els.trPhoto.hidden && !p.store.trinity_session_who, 'a new sign-in on an ended session drops the old name and the Photo button');
    await p.say(PASS);
    check(p.masked(), 'and its passphrase box stays masked after a dropped line');
  }
  // SI-3: storage that throws
  {
    let n = 0;
    const p = page({ throwingStorage: true, route: () => [CLAIM, WELCOME, { status: 200, body: { answer: 'Signed out. Talk soon, Matthew.', session: '' } }][n++] });
    await p.say('It’s Matthew');
    await p.say(PASS);
    check(asks(p)[1].body.session === CLAIM.body.session, 'with storage refused, the passphrase still goes with its sign-in token');
    check(!p.rows().some(r => r.indexOf(PASS) >= 0) && /Signed in as Matthew/.test(p.els.trWho.textContent), 'and the sign-in opens, the passphrase never shown');
    await p.say('sign out');
    check(p.rows().length === 1 && /Trinity/.test(p.rows()[0]), 'and signing out puts the chat back at her intro');
  }
  // The passphrase has a box of its own (Safari's keychain key, owner 2026-10-07): the chat box is never masked, the
  // passphrase box is a new element that takes the focus with the passphrase settings, and it is gone - not just
  // unmasked - the moment the sign-in opens or ends, the chat box back with its own settings and the focus.
  {
    let n = 0;
    const p = page({ route: () => [CLAIM, WELCOME, { status: 200, body: { answer: 'Signed out. Talk soon, Matthew.', session: '' } }][n++] });
    const chat = p.input();
    await p.say('It’s Matthew');
    const sb = p.secret(), sf = p.secretForm();
    check(!!sb && sb !== chat && p.chatClean() && chat.parentNode === p.els.trAsk, 'the passphrase gets its own box; the chat box is never masked');
    const f = sb.focusLog[0] || {};
    check(f.ts === 'disc' && f.ac === 'off' && f.cap === 'off' && f.sp === false && p.doc.activeElement === sb,
      'it takes the focus with the mask on and autocorrect, capitals and spell-check already off');
    await p.say(PASS);
    check(!p.secretForm() && !sf.parentNode && p.els.trAsk.style.display === '' && p.chatClean(), 'signed in, the passphrase box is gone and the chat box is back');
    const g = chat.focusLog.slice(-1)[0] || {};
    check(p.doc.activeElement === chat && g.ts === '' && g.ac === 'on', 'and the chat box has the focus with its own settings');
    await p.say('sign out');
    check(!p.secretForm() && p.chatClean() && p.els.trAsk.style.display === '', 'signed out, no passphrase box anywhere and the chat box untouched');
  }
  // SI-8 / SI-10: a session that ends on its own resets to the intro and says why
  {
    let n = 0;
    const GONE = 'That sign-in has closed, so I did not read what you just sent. Say your name and we can start again.';
    const p = page({ route: () => [CLAIM, WELCOME, { status: 200, body: { answer: 'Thirty-three and seventeen.', as: 'Matthew' } }, { status: 200, body: { answer: GONE, session: '' } }][n++] });
    await p.say('It’s Matthew'); await p.say(PASS); await p.say('what is the record?');
    await p.say('Add a line to the footer that says hello');
    const r = p.rows();
    check(r.length === 2 && /Trinity/.test(r[0]) && r[1] === GONE, 'an ended session goes back to the intro with her reason under it');
    check(!/Thirty-three/.test(p.store.trinity_log || ''), 'and nothing said while signed in is kept');
  }
  // SI-8 / SI-10: a /job 403 says the change is no longer followed
  {
    let n = 0;
    const JOB = '20261007-171153-matthew-cc51d3';
    const p = page({ route: (u) => u === '/ask' ? [CLAIM, WELCOME, { status: 200, body: { answer: 'Got it. I am making that change now.', as: 'Matthew', job: JOB } }][n++]
      : { status: 403, body: { answer: 'Sign in first.', answered: false } } });
    await p.say('It’s Matthew'); await p.say(PASS);
    await p.say('Add a line to the footer that says hello', { wait: 1000 });
    await p.advance(10000);
    const r = p.rows();
    check(r.length === 2 && /Trinity/.test(r[0]) && /stopped following that change/.test(r[1]), 'a change whose sign-in closed is reported, not dropped in silence');
    check(!p.store.trinity_jobs || p.store.trinity_jobs === '{}', 'and it is no longer kept');
  }
  // SI-08: one signed-in send is one POST, even when the line drops; a public question is still retried
  {
    let n = 0;
    const p = page({ route: (u) => u === '/ask' ? [CLAIM, WELCOME, { status: 503, body: { error: 'not answering right now' } }][Math.min(n++, 2)] : {} });
    await p.say('It’s Matthew'); await p.say(PASS);
    await p.say('Add a note on the Wooder Ice tab saying Gates open at six');
    check(asks(p).length === 3, 'a signed-in change that got a 503 is sent once');
    check(/my changes/.test(p.rows().slice(-1)[0]), 'and she says how to check before sending it again');
    const q = page({ route: () => ({ status: 503, body: { error: 'x' } }) });
    await q.say('what is the record?');
    check(asks(q).length === 3, 'a public question that never arrived is still tried three times');
  }
  // SI-13: a change is followed past thirty minutes, and let go with a word
  {
    const JOB = '20261007-164957-matthew-465758';
    const store = { trinity_session: 'sess-token-00000000000000001', trinity_session_who: 'Matthew' };
    const p0 = page({ store });
    store.trinity_jobs = JSON.stringify({ [JOB]: { s: 'Got it.', at: p0.clock - 31 * 60 * 1000 } });
    store.trinity_log = JSON.stringify([{ w: 'her', t: 'Got it.', c: null, x: '' }]);
    let state = 'working';
    const p = page({ store, clock: p0.clock, route: (u) => u === '/job' ? { status: 200, body: { answer: state === 'live' ? 'It is live.' : 'Still working on it.', done: state === 'live', as: 'Matthew' } } : {} });
    await p.advance(5000);
    check(p.calls.filter(c => c.url.endsWith('/job')).length >= 1, 'a change kept from 31 minutes ago is still asked about after a reload');
    state = 'live';
    await p.advance(120000);
    check(p.rows().some(r => r === 'It is live.') && JSON.parse(p.store.trinity_jobs || '{}')[JOB] === undefined, 'and its going live is shown, then it is let go');
    const store2 = { trinity_session: 'sess-token-00000000000000001', trinity_session_who: 'Matthew',
      trinity_jobs: JSON.stringify({ [JOB]: { s: 'Got it.', at: p0.clock - 3 * 60 * 60 * 1000 } }) };
    const p2 = page({ store: store2, clock: p0.clock, route: () => ({ status: 200, body: { answer: 'Still working on it.', done: false } }) });
    await p2.advance(5000);
    check(p2.calls.filter(c => c.url.endsWith('/job')).length === 1 && /still on its way/.test(p2.rows().slice(-1)[0])
      && JSON.parse(p2.store.trinity_jobs || '{}')[JOB] === undefined, 'past the window it asks once more, says it is still on its way and lets it go');
    let wakes = 0;
    const p3 = page({ store: { trinity_session: 's', trinity_session_who: 'Matthew', trinity_jobs: JSON.stringify({ [JOB]: { s: 'x', at: p0.clock } }) },
      clock: p0.clock, route: () => { wakes++; return { status: 200, body: { answer: 'Still working on it.', done: false } }; } });
    await p3.advance(2000);
    const before = wakes;
    (p3.document._h.visibilitychange || []).forEach(f => f());
    await p3.advance(10);
    check(wakes === before + 1, 'and the phone waking up asks about it at once');
  }
  // SI-09 / SI-14 / SI-16: photos
  {
    const signedInStore = () => ({ trinity_session: 'sess-token-00000000000000001', trinity_session_who: 'Matthew' });
    const p = page({ store: signedInStore(), route: (u) => u === '/upload' ? 'throw' : {} });
    await p.pickPhoto();
    check(/could not confirm that photo arrived/.test(p.rows().slice(-1)[0]), 'a photo sent whose reply was lost is not called "nothing was passed on"');
    const h = page({ store: signedInStore(), decodes: false });
    await h.pickPhoto();
    check(/cannot open that kind of photo/.test(h.rows().slice(-1)[0]) && !h.calls.some(c => c.url.endsWith('/upload')), 'a photo this browser cannot open says so, and nothing is sent');
    let upl = 0;
    const q = page({ store: signedInStore(), route: (u) => {
      if (u === '/upload') { upl++; return { status: 200, body: { answer: 'I have your photo.', as: 'Matthew' } }; }
      return { status: 200, delay: 5000, body: { answer: 'Thirty-three and seventeen.', as: 'Matthew' } };
    } });
    q.els.trPhoto.hidden = false;
    q.input().value = 'what is the record?';
    q.els.trAsk.handlers.submit[0]({ preventDefault() {} });
    await q.advance(0);
    check(q.els.trPhoto.disabled === true, 'the Photo button waits while an answer is on its way');
    await q.pickPhoto(0);
    check(upl === 0, 'a photo picked meanwhile is not sent over the answer');
    await q.advance(30000);
    check(upl === 1 && q.rows().slice(-1)[0] === 'I have your photo.', 'and it is sent once the answer is in, not lost');
  }
  // Enter sends from the text area; Shift+Enter does not; a keyboard still composing (229) does not
  {
    const p = page({ route: () => ({ status: 200, body: { answer: 'Hey.' } }) });
    const box = p.input();
    const press = (o) => box.handlers.keydown[0](Object.assign({ key: 'Enter', shiftKey: false, isComposing: false, keyCode: 13, preventDefault() {} }, o));
    box.value = 'hello'; press({ shiftKey: true }); press({ isComposing: true }); press({ keyCode: 229 });
    await p.advance(1000);
    check(asks(p).length === 0, 'Shift+Enter and a composing keyboard do not send');
    press({}); await p.advance(30000);
    check(asks(p).length === 1 && asks(p)[0].body.question === 'hello' && box.value === '', 'Enter sends the text area once and clears it');
  }
  // SI-04: the box takes the room left over, so the Photo button cannot widen the page on a phone
  {
    const m = css.match(/\.tr-ask input,\.tr-ask textarea\{([^}]*)\}/);
    check(!!m && /(^|;)\s*width:0\b/.test(m[1]) && /flex:1 1 auto/.test(m[1]), 'the chat box has width:0 with flex 1 1 auto, so its min-content cannot widen the page');
    const panel = fs.readFileSync(__dirname + '/../trinity/panel.html', 'utf8');
    check(/<textarea id="trInput"/.test(panel) && !/<input id="trInput"/.test(panel),
      'the chat box is a text area, where neither iOS nor Safari offers saved passwords or the keychain key');
  }
  // Changing a passphrase, signed in (owner, 2026-10-07: "so that its more secure for them"). Each step's reply
  // carries next: 'passphrase' and the change's own token; every answer goes in the passphrase box and shows as
  // dots, and the box stays up through a dropped line, an edge limit and a reload until a reply ends the change.
  {
    const CT = 'chng-token-0000000000000001', NEWP = 'river bend 19', OLDP = PASS;
    const START = { status: 200, body: { answer: 'First, type the passphrase you use now so I know it is you, or say "cancel" to stop. What is your current passphrase?', session: CT, as: 'Matthew', next: 'passphrase', answered: true } };
    const ASKNEW = { status: 200, body: { answer: 'Thank you. Choose a new one of at least 6 characters, where case and spacing do not count. What is your new passphrase?', as: 'Matthew', next: 'passphrase', answered: true } };
    const AGAIN = { status: 200, body: { answer: 'One more time, exactly the same, so I know it is right: what is your new passphrase?', as: 'Matthew', next: 'passphrase', answered: true } };
    const DONE = { status: 200, body: { answer: 'Done. Your passphrase is changed, and from now on only the new one opens your sign-in. You are still signed in here, and anywhere else you were signed in has been signed out.', session: 'sess-token-00000000000000002', as: 'Matthew', answered: true } };
    const CANCELLED = { status: 200, body: { answer: 'No problem, I stopped. Your passphrase is the same as before, and you are still signed in.', session: 'sess-token-00000000000000003', as: 'Matthew', answered: true } };
    const signedInStore = () => ({ trinity_session: 'sess-token-00000000000000001', trinity_session_who: 'Matthew' });
    let n = 0;
    const p = page({ store: signedInStore(), route: (u) => u === '/ask' ? [START, ASKNEW, AGAIN, DONE][n++] : {} });
    const chat = p.input();
    await p.say('Change my passphrase');
    check(p.masked() && p.secret() !== chat && p.store.trinity_session === CT && /Signed in as Matthew/.test(p.els.trWho.textContent),
      'asked to change it, the passphrase box takes the chat box\'s place, holding the change\'s token, still signed in');
    await p.say(OLDP);
    check(p.masked() && asks(p)[1].body.session === CT, 'the current one goes with the change\'s token, and the box stays for the new one');
    await p.say(NEWP);
    check(p.masked(), 'and stays for the new one again');
    await p.say(NEWP);
    check(!p.secretForm() && p.chatClean() && p.els.trAsk.style.display === '' && p.store.trinity_session === DONE.body.session
      && /Signed in as Matthew/.test(p.els.trWho.textContent), 'done: the passphrase box is gone, the chat box is back, signed in on the fresh session');
    check(!p.rows().some(r => r.indexOf(OLDP) >= 0 || r.indexOf(NEWP) >= 0) && !keptHas(p, OLDP) && !keptHas(p, NEWP)
      && p.rows().filter(r => r === '••••••').length === 3, 'every answer in the change is dots on screen and in what the tab keeps');
    // a dropped line in the middle: still masked, still the change's token, and she asks for it again
    let m = 0;
    const q = page({ store: signedInStore(), route: (u) => u === '/ask' ? [START, 'throw', ASKNEW][m++] : {} });
    await q.say('new passphrase');
    await q.say(OLDP);
    check(q.masked() && q.store.trinity_session === CT, 'a dropped line in the middle of a change leaves the passphrase box up and the token held');
    check(/Send the same again/.test(q.rows().slice(-1)[0]) && !/my changes|Try your passphrase/.test(q.rows().slice(-1)[0]),
      'and she asks for the same again (a passphrase or a cancel), not about "my changes"');
    await q.say(OLDP);
    check(!q.rows().some(r => r.indexOf(OLDP) >= 0) && !keptHas(q, OLDP) && asks(q)[2].body.session === CT, 'the retyped one is dots, not kept, and goes with the change\'s token');
    // the edge's own limit in the middle
    let k = 0;
    const l = page({ store: signedInStore(), route: (u) => u === '/ask' ? [START, { status: 429, body: { answer: 'Too many questions at once. Give it a moment.', answered: false, cites: [] } }][k++] : {} });
    await l.say('reset my password');
    await l.say(OLDP);
    check(l.masked(), 'a limit at the edge in the middle of a change leaves the passphrase box up');
    // a reload in the middle comes back masked
    const store = signedInStore();
    const r1 = page({ store, route: () => START });
    await r1.say('Change my passphrase');
    const r2 = page({ store, route: () => ASKNEW });
    check(r2.masked(), 'a reload in the middle of a change comes back with the passphrase box');
    await r2.say(OLDP);
    check(!r2.rows().some(r => r.indexOf(OLDP) >= 0) && !keptHas(r2, OLDP) && asks(r2)[0].body.session === CT, 'and what is typed after it is dots, not kept, with the change\'s token');
    // cancel puts the chat box back, signed in
    let c = 0;
    const x = page({ store: signedInStore(), route: (u) => u === '/ask' ? [START, CANCELLED, { status: 200, body: { answer: 'Thirty-three and seventeen.', as: 'Matthew' } }][c++] : {} });
    await x.say('Change my passphrase');
    await x.say('cancel');
    check(!x.secretForm() && x.chatClean() && /Signed in as Matthew/.test(x.els.trWho.textContent) && x.store.trinity_session === CANCELLED.body.session,
      'a cancel puts the chat box back, signed in');
    await x.say('what is the record?');
    check(x.rows().some(r => r === 'what is the record?'), 'and what is asked next is shown as typed again');
  }
  console.log(fails ? `trinity mobile: ${fails} FAILED` : 'trinity mobile: ALL PASS');
  process.exit(fails ? 1 : 0);
})();
