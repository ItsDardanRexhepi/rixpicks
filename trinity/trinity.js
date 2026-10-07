/* ================================================================================================
   THE TRINITY TAB, the chat client. Into the existing script block in rixpicks/index.html, or as
   rixpicks/trinity.js loaded after it.

   WHAT THIS FILE IS NOT ALLOWED TO DO, and the reasons are the same ones the answering system runs on:

     * It holds no answers. There are no canned replies here and no cache served as current. When the
       endpoint cannot answer, she says so, in her own words, and that is the whole fallback.
     * It computes nothing. It does not total, round, average, restate or join two answers into a
       third claim. Every figure a visitor reads was produced by the engine and verified before it
       left his machine; arithmetic in the page would be a figure nothing verified.
     * It does not stream or animate thinking. The endpoint answers once, whole. A typing effect would
       imply she is reasoning out loud when she is not, and the honesty of the surface is the product.
     * It renders a refusal as an answer. `answered:false` is a true statement about what is not
       public, so it gets the same bubble and no red, no icon and no apology.
     * It sends one question at a time. Only a public question that never arrived is tried again; anything sent
       while a sign-in is open or asked for is sent once, because a second copy of a change is a second change.
     * On every visit it reads the chat's instant site changes (typed keys and plain values, never markup) and
       applies them: a colour, a note, a picture, a word, a section shown or hidden, a Wooder Ice ticket.
     * Signed in, a reply may carry a picture the Mac made (the card image) and notices from a watch they
       set. The picture is shown only when it really is a PNG or JPEG, and a notice is text like any reply.
     * It sends the conversation only as it is shown: the last few turns, capped, and only while nobody is signed
       in or signing in. A turn is context for her, never a fact: every figure she says is still checked against
       what the engine computed, and a figure that is only in a turn is refused. A row from a sign-in, a passphrase
       or a signed-in conversation is never sent; signed in, the Mac keeps that person's conversation itself.

   The greeting fires once per visitor and then she waits: no buttons, no prompts, no follow-up.
   ================================================================================================ */
(function () {
  'use strict';

  /* Set this to the live route. Until it answers, the tab shows her offline line. */
  var TRINITY_ENDPOINT = 'https://api.rix-picks.com/trinity';

  var MAX_Q = 400;

  /* Hers, both of them, and neither is improvised here: the greeting is the one the system ships, and
     the offline line is the shape every limit of hers takes - the limit, the reason, the refusal to
     guess, the next step. */
  var GREETING = 'Hi, my name is Trinity. I run on UltRix, the algorithm behind these picks, and I can ' +
                 'only tell you what its record actually shows. Ask me about a pick and I will show you ' +
                 'the bar it cleared.';
  var OFFLINE = 'I cannot reach my own records from here just now, so I will not answer from anything ' +
                'else. Try me again in a moment.';
  /* While she is answering: a typing bubble, three dots, like any chat - no words (the owner, 2026-10-07). */
  var PENDING = '';

  /* THE CONVERSATION SHE IS SENT. The last TURNS_MAX rows of it, each cut to TURN_MAX characters, and the whole body
     held under BODY_MAX bytes by dropping the oldest turn first (the edge refuses a body over 6144). Rows from a
     signed-in conversation, a sign-in or a masked passphrase are never sent: they are flagged private when kept. */
  var TURNS_MAX = 6, TURN_MAX = 480, BODY_MAX = 6000;

  var log, chips, form, input, send, who, booted = false, inFlight = false;

  /* SIGNING IN. Two people may sign in here, and only on her prompt. The session lives in sessionStorage, so it
     belongs to this tab alone and is gone when the tab closes. When she has just asked for a passphrase, the next
     thing typed is masked as it is typed, and shown in the conversation as dots - the passphrase is never on the
     screen and never in the log. The same holds at every step of changing a passphrase while signed in. */
  var SESSION = 'trinity_session';
  var secretNext = false;

  /* The page's own copy is what it goes by. Storage is read once, when the page loads, and written after every
     change, so a reload keeps the sign-in; a browser that refuses storage (Safari with every cookie blocked, a
     private window that throws) still signs in and out for the life of the page, and a passphrase is never sent
     without the sign-in it belongs to. */
  var mem = { s: '', who: '', asked: false };
  try {
    mem.s = sessionStorage.getItem(SESSION) || '';
    mem.who = mem.s ? (sessionStorage.getItem(SESSION + '_who') || '') : '';
    mem.asked = !!mem.s && sessionStorage.getItem(SESSION + '_asked') === '1';
  } catch (e) {}

  function getSession() { return mem.s; }

  function setSession(v) {
    mem.s = v || '';
    try {
      if (v) sessionStorage.setItem(SESSION, v); else sessionStorage.removeItem(SESSION);
    } catch (e) {}
    if (!v) setAsked(false);
  }

  /* Signed in, she asks for a passphrase at every step of CHANGING one, and the page holds that she asked until a
     reply from the Mac says otherwise - the same as a sign-in in progress holds its token. A dropped line, a limit at
     the edge or a reload in the middle of a change never puts the chat box back while the change's token is held. */
  function setAsked(on) {
    mem.asked = !!on;
    try { if (on) sessionStorage.setItem(SESSION + '_asked', '1'); else sessionStorage.removeItem(SESSION + '_asked'); }
    catch (e) {}
  }

  /* Signed in: a session and a name. A token with no name is a sign-in she has asked a passphrase for, and while
     one is held the next thing typed is the passphrase - after a failed send, a limit, a dropped line or a reload
     as much as after her prompt. */
  function signedIn() { return !!(mem.s && mem.who); }
  function pending() { return !!mem.s && !mem.who; }
  function secretWanted() { return pending() || (!!mem.s && mem.asked); }

  function showWho(name) {
    mem.who = name || '';
    try { if (name) sessionStorage.setItem(SESSION + '_who', name); else sessionStorage.removeItem(SESSION + '_who'); }
    catch (e) {}
    var pb = document.getElementById('trPhoto');
    if (pb) pb.hidden = !name;
    if (!who) return;
    if (name) { who.textContent = 'Signed in as ' + name + '. Say "sign out" when you are done.'; who.hidden = false; }
    else { who.textContent = ''; who.hidden = true; }
  }

  /* THE PASSPHRASE HAS A BOX OF ITS OWN. The chat box is never the passphrase box. When she asks for a passphrase, a
     separate small form takes the chat box's place - its own box, masked as it is typed, autocorrect, capitals and
     spell-check off - and the moment the sign-in opens, fails or ends, that form is deleted and the chat box is back.
     The reason is Safari: once a box on the page has held a masked passphrase, Safari treats that box (and its form)
     as a login field and keeps its keychain key in it for the rest of the visit - after the passphrase, after signing
     in, after signing out (owner, 2026-10-07). A box that only ever held a passphrase, and no longer exists, leaves
     nothing for it to hold on to. A brand-new box also makes an iPhone reload its keyboard with the right settings.
     The mask is a text mask, not a password field; only a browser without one falls back to a password field. */
  var TEXT_MASK = !!(window.CSS && CSS.supports && CSS.supports('-webkit-text-security', 'disc'));
  var CHAT_HINT = 'Ask Trinity anything';
  var secretForm = null, secretBox = null, secretBtn = null;
  function box() { return secretBox || input; }
  /* The chat box is a text area, not a single-line field: neither iOS nor Safari ever offers saved passwords or puts
     the keychain key in a text area, where both did in the chat box once the page had held a passphrase (the owner's
     iPhone showed "Passwords" over it while he was signed in, 2026-10-07). Enter sends; Shift+Enter is a new line. */
  function chatTraits(n) {
    if (String(n.tagName || '').toUpperCase() === 'INPUT') n.type = 'text';
    if (n.style) n.style.webkitTextSecurity = '';
    n.setAttribute('autocomplete', 'off');
    n.setAttribute('autocapitalize', 'sentences');
    n.setAttribute('autocorrect', 'on');
    n.spellcheck = true;
    n.placeholder = CHAT_HINT;
  }
  function secretTraits(n) {
    if (TEXT_MASK) { n.type = 'text'; n.style.webkitTextSecurity = 'disc'; } else { n.type = 'password'; }
    n.setAttribute('autocomplete', 'off');
    n.setAttribute('autocapitalize', 'off');
    n.setAttribute('autocorrect', 'off');
    n.spellcheck = false;
    n.placeholder = 'Passphrase';
    n.setAttribute('maxlength', '400');
    n.setAttribute('enterkeyhint', 'send');
    n.setAttribute('aria-label', 'Your passphrase');
  }
  function focusBox() {
    var n = box();
    if (!n) return;
    try { n.focus({ preventScroll: true }); } catch (e) { n.focus(); }
  }
  function maskInput(on) {
    on = !!on;
    secretNext = on;
    if (!input) return;
    if (on) {
      if (secretForm) return;
      var parent = form && form.parentNode;
      if (!parent) { secretNext = false; return; }
      var hadFocus = document.activeElement === input || (send && document.activeElement === send);
      secretForm = document.createElement('form');
      secretForm.className = 'tr-ask tr-secret';
      secretForm.setAttribute('autocomplete', 'off');
      secretBox = document.createElement('input');
      secretBox.className = input.className || '';
      secretTraits(secretBox);
      secretBtn = document.createElement('button');
      secretBtn.type = 'submit';
      secretBtn.textContent = send ? send.textContent : 'Ask';
      if (send && send.className) secretBtn.className = send.className;
      secretBtn.disabled = inFlight;
      secretForm.appendChild(secretBox);
      secretForm.appendChild(secretBtn);
      secretForm.addEventListener('submit', function (e) { e.preventDefault(); ask(secretBox ? secretBox.value : ''); });
      parent.insertBefore(secretForm, form);
      form.style.display = 'none';
      if (hadFocus) focusBox();
      return;
    }
    if (!secretForm) { chatTraits(input); return; }
    var focused = document.activeElement === secretBox || document.activeElement === secretBtn;
    if (secretBox) secretBox.value = '';
    if (secretForm.parentNode) secretForm.parentNode.removeChild(secretForm);
    secretForm = secretBox = secretBtn = null;
    form.style.display = '';
    chatTraits(input);
    if (focused) focusBox();
  }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function atBottom() {
    return log.scrollHeight - log.scrollTop - log.clientHeight < 40;
  }

  /* textContent everywhere. Nothing from the endpoint is ever parsed as markup.

     `force` is for the rows a visitor caused: what they just sent, and the reply to it, are always scrolled
     into view. Sticking to the bottom only when already there is the right rule for a passive update and the
     wrong one here, because a visitor who has scrolled up to re-read an answer still wants to see the one they
     just asked for. */
  /* THE CONVERSATION OUTLIVES A RELOAD. The site reloads itself when a new build is published (every few minutes)
     and when the card changes; the conversation is kept for this browser tab in sessionStorage, as the sign-in
     already is, and put back when the page comes back. A pending "..." row is never kept, and a passphrase was
     never shown here in the first place (it is shown as dots). */
  var HISTORY = 'trinity_log', JOBS = 'trinity_jobs', MAX_KEPT = 80;
  var kept = [];
  function keep(who, text, cites, extra) {
    if (extra && /tr-pending/.test(extra)) return;
    kept.push({ w: who, t: String(text).slice(0, 4000), c: cites && cites.length ? cites : null, x: extra || '',
                p: getSession() || secretNext || pending() ? 1 : 0 });
    if (kept.length > MAX_KEPT) kept = kept.slice(-MAX_KEPT);
    try { sessionStorage.setItem(HISTORY, JSON.stringify(kept)); } catch (e) {}
  }
  function restore() {
    var got = [];
    try { got = JSON.parse(sessionStorage.getItem(HISTORY) || '[]'); } catch (e) { got = []; }
    if (!Array.isArray(got) || !got.length) return false;
    kept = got.slice(-MAX_KEPT);
    got.forEach(function (m) {
      if (m && typeof m.t === 'string' && (m.w === 'me' || m.w === 'her')) {
        restoring = true;
        row(m.w, m.t, Array.isArray(m.c) ? m.c : null, typeof m.x === 'string' ? m.x : '', true);
        restoring = false;
      }
    });
    return log.children.length > 0;
  }
  /* A message that opened, asked for or ended a sign-in, and everything after it, is the door's and not the
     conversation's: it is never sent back to her as a turn. */
  function markPrivate(first) {
    var at = kept.indexOf(first);
    if (at < 0) return;
    for (var i = at; i < kept.length; i++) if (kept[i]) kept[i].p = 1;
    try { sessionStorage.setItem(HISTORY, JSON.stringify(kept)); } catch (e) {}
  }
  function recentTurns() {
    var out = [];
    for (var i = kept.length - 1; i >= 0 && out.length < TURNS_MAX; i--) {
      var m = kept[i];
      if (!m || m.p || (m.w !== 'me' && m.w !== 'her') || typeof m.t !== 'string') continue;
      if (typeof m.x === 'string' && /tr-pending/.test(m.x)) continue;
      var t = m.t.replace(/\s+/g, ' ').trim();
      /* A long reply of hers keeps its opening and its last sentence, which says what the answer was. */
      if (t.length > TURN_MAX) {
        t = m.w === 'her' ? t.slice(0, TURN_MAX - 140) + ' ... ' + t.slice(-135) : t.slice(0, TURN_MAX);
      }
      t = whole(t);
      if (t) out.unshift({ who: m.w, text: t });
    }
    return out;
  }
  /* A cut never splits a character. A slice counts UTF-16 units, so it can end between the two halves of an emoji,
     and half a character is not text: the model on the Mac refuses a whole prompt over one. A lone half is dropped;
     a whole character is kept. (No lookbehind here: an older Safari would refuse the whole script over one.) */
  function whole(s) {
    var out = '';
    for (var i = 0; i < s.length; i++) {
      var c = s.charCodeAt(i);
      if (c >= 0xd800 && c <= 0xdbff) {
        var d = s.charCodeAt(i + 1);
        if (d >= 0xdc00 && d <= 0xdfff) { out += s.charAt(i) + s.charAt(i + 1); i++; }
        continue;
      }
      if (c >= 0xdc00 && c <= 0xdfff) continue;
      out += s.charAt(i);
    }
    return out;
  }
  function bytes(s) {
    try { return new Blob([s]).size; } catch (e) { return unescape(encodeURIComponent(s)).length; }
  }
  /* What goes to /ask: signed in or signing in, the question and the token and nothing else; otherwise the question
     and the turns, oldest dropped first until the body fits. */
  function askBody(q, turns) {
    if (getSession()) return JSON.stringify({ question: q, session: getSession() });
    for (;;) {
      var b = JSON.stringify(turns.length ? { question: q, turns: turns } : { question: q });
      if (!turns.length || bytes(b) <= BODY_MAX) return b;
      turns = turns.slice(1);
    }
  }
  function jobsKept() {
    try { var j = JSON.parse(sessionStorage.getItem(JOBS) || '{}'); return (j && typeof j === 'object') ? j : {}; }
    catch (e) { return {}; }
  }
  function keepJob(job, said, done) {
    var j = jobsKept();
    if (done) delete j[job]; else j[job] = { s: String(said || ''), at: j[job] ? j[job].at : Date.now() };
    try { sessionStorage.setItem(JOBS, JSON.stringify(j)); } catch (e) {}
  }

  /* A PICTURE IN A REPLY, signed in only: the card image she made on the Mac. It arrives as base64 in the reply
     and is shown only when it is what it says it is - a PNG or a JPEG by its own first bytes, base64 and nothing
     else, under a size cap - so a reply can never put anything but a picture here. The picture is not kept in this
     tab's storage (it is large); its change id is, and a reload asks the Mac for it again. */
  var SHOTS = 'trinity_shots', B64_RE = /^[A-Za-z0-9+\/]+={0,2}$/, SHOT_MAX = 8 * 1024 * 1024;
  function shotUrl(im) {
    if (!im || typeof im.b64 !== 'string' || !im.b64 || im.b64.length > SHOT_MAX || im.b64.length % 4) return '';
    var mime = (im.mime === 'image/png' || im.mime === 'image/jpeg') ? im.mime : '';
    if (!mime || !B64_RE.test(im.b64)) return '';
    var h = '';
    try { h = atob(im.b64.slice(0, 12)); } catch (e) { return ''; }
    var png = h.charCodeAt(0) === 0x89 && h.slice(1, 4) === 'PNG';
    var jpg = h.charCodeAt(0) === 0xFF && h.charCodeAt(1) === 0xD8;
    if (mime === 'image/png' ? !png : !jpg) return '';
    return 'data:' + mime + ';base64,' + im.b64;
  }
  function shotsKept() {
    try { var s = JSON.parse(sessionStorage.getItem(SHOTS) || '[]'); return Array.isArray(s) ? s : []; }
    catch (e) { return []; }
  }
  function keepShot(job, text) {
    var s = shotsKept().filter(function (x) { return x && x.j !== job; });
    s.push({ j: job, t: String(text || '').slice(0, 4000) });
    try { sessionStorage.setItem(SHOTS, JSON.stringify(s.slice(-10))); } catch (e) {}
  }
  function showShot(r, im, job, text) {
    var url = shotUrl(im), b = r && r.querySelector ? r.querySelector('.tr-bub') : null;
    if (!url || !b || b.querySelector('.tr-shot')) return;
    var img = el('img', 'tr-shot');
    img.alt = (typeof im.alt === 'string' && im.alt) ? im.alt.slice(0, 120) : 'The card image';
    img.src = url;
    b.appendChild(img);
    var a = el('a', 'tr-save', 'Save the image');
    a.href = url;
    a.download = (typeof im.name === 'string' && /^[A-Za-z0-9._-]{1,60}\.(png|jpe?g)$/.test(im.name)) ? im.name : 'rixpicks-card.png';
    b.appendChild(a);
    if (typeof job === 'string' && JOB_RE.test(job)) keepShot(job, text);
  }
  /* After a reload the conversation comes back as text; each picture it held is asked for again, once, by its
     change id, and put back on the reply it belonged to. Signed out, nothing is asked. */
  function resumeShots() {
    if (!getSession()) return;
    shotsKept().forEach(function (x) {
      if (!x || typeof x.j !== 'string' || !JOB_RE.test(x.j)) return;
      var rows = log ? log.querySelectorAll('.tr-row.her') : [], at = null;
      for (var i = rows.length - 1; i >= 0; i--) {
        var bub = rows[i].querySelector('.tr-bub');
        if (bub && bub.firstChild && bub.firstChild.nodeValue === x.t) { at = rows[i]; break; }
      }
      if (!at) return;
      fetch(TRINITY_ENDPOINT + '/job', {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ session: getSession(), job: x.j }), cache: 'no-store'
      }).then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) { if (d && d.image) showShot(at, d.image, x.j, x.t); })
        .catch(function () { /* the words stand without the picture */ });
    });
  }
  /* What a watch they set found while they were away, said before the answer to what they just sent. */
  function notices(list) {
    if (!Array.isArray(list)) return;
    list.slice(0, 5).forEach(function (n) {
      if (typeof n === 'string' && n) row('her', n.slice(0, 1000), null, 'tr-notice', true);
    });
  }

  /* INSTANT CHANGES, for every visitor. What the people signed in here ask for most - a colour, a note or a
     banner, a picture they sent, a word changed, a section shown or hidden, a Wooder Ice ticket - is applied on the
     Mac to a small document of TYPED changes, and this page reads it on load and every few seconds, so the change
     shows within seconds instead of after a rebuild. The same changes are written into the site's own files in the
     background, so the next build carries them.

     The document can never put anything on this page that runs:
       * it carries KEYS and plain values, never a selector, a URL or markup. Every key is looked up in the maps below,
         which are this page's own, and a key that is not there is ignored;
       * a value is checked here again by pattern (a colour is #rrggbb, a size is a bounded px value) before it is
         set, and it is set as one property with setProperty, never written into a style sheet;
       * words are written with textContent, never parsed, and never inside her tab, the record or the unit line;
       * a picture is shown only when its own bytes are a PNG or a JPEG (shotUrl, above).
     A failed fetch changes nothing, and a change that is taken back is taken off at the next read. */
  var OV_VARS = { '--bg': 1, '--panel': 1, '--panel2': 1, '--line': 1, '--txt': 1, '--mut': 1, '--acc': 1,
                  '--acc-deep': 1, '--live': 1, '--amber': 1, '--red': 1 };
  var OV_TARGETS = { nav: 'nav.rpnav', logo: 'nav.rpnav .logo', tabs: 'nav.rpnav .tab', record: '#rpNavRec',
                     titles: '.sect', footer: '.foot', body: '.wrap' };
  var OV_PROPS = { 'color': /^#[0-9a-f]{6}$/, 'background-color': /^#[0-9a-f]{6}$/,
                   'font-weight': /^(400|500|600|700|800)$/, 'font-size': /^(1[0-9]|2[0-9]|3[0-9]|40)px$/,
                   'text-align': /^(left|center|right)$/, 'border-radius': /^([0-9]|1[0-9]|2[0-4])px$/ };
  var OV_HIDE = { news: '#rpNewsCar', social: '#rpSocial,#rpSocialHead', ticker: '#rpTickBar', games: '#rpGames',
                  predictions: '#rpPredWrap', dingers: '#rpDing', first_td: '#rpFtd', night: '#rpNight',
                  futures: '#rpCmbFutWrap', intro: '#rpIntro', parlays: '#rpCmb' };
  var OV_SLOTS = { 'home-top': 'home', 'nfl-top': 'nfl', 'wooder-top': 'wooder', 'past-top': 'past', 'footer': '' };
  var OV_ID = /^[0-9a-f]{12}$/, OV_TICKET = /^t[0-9a-z]{1,8}$/, OV_DAY = /^20\d\d-\d\d-\d\d$/;
  /* never reworded: her tab, the record and its pop-up, the unit line, the official card (.pick), the yesterday line
     (.rphead, .yesrec) and the past tickets. The card changes when Dardan lands it; results only through grading. */
  var OV_KEEP_OUT = '#st-trinity,#rpNavRec,#rpRecPop,.recpop,.unitmath,.unitbasis,.rphead,.yesrec,.pick,#st-past,' +
                    'script,style,noscript,textarea,input,select';
  var OV_POLL_MS = 15000;

  function ovStr(s, n) { return (typeof s === 'string' && s && s.length <= n && !/[<>{}\\`]/.test(s)) ? s : ''; }

  /* The document, checked: what survives is a list of plain operations. Pure, so it is tested on its own. */
  function ovPlan(doc) {
    var out = { ops: [], gone: [] };
    if (!doc || typeof doc !== 'object' || doc.v !== 1 || !Array.isArray(doc.items)) return out;
    doc.items.slice(0, 60).forEach(function (it) {
      if (!it || typeof it !== 'object' || !OV_ID.test(String(it.id || ''))) return;
      var id = it.id;
      if (it.k === 'var' && OV_VARS[it.var] === 1 && /^#[0-9a-f]{6}$/.test(String(it.value))) {
        out.ops.push({ id: id, k: 'var', name: it.var, value: it.value });
      } else if (it.k === 'style' && OV_TARGETS.hasOwnProperty(it.target) && OV_PROPS.hasOwnProperty(it.prop) &&
                 OV_PROPS[it.prop].test(String(it.value))) {
        out.ops.push({ id: id, k: 'style', sel: OV_TARGETS[it.target], prop: it.prop, value: it.value });
      } else if (it.k === 'hide' && OV_HIDE.hasOwnProperty(it.section)) {
        out.ops.push({ id: id, k: 'hide', sel: OV_HIDE[it.section] });
      } else if (it.k === 'text' && ovStr(it.find, 300) && ovStr(it.replace, 300) && !/\d/.test(it.find) &&
                 it.replace.indexOf(it.find) === -1) {
        out.ops.push({ id: id, k: 'text', find: it.find, replace: it.replace });
      } else if (it.k === 'note' && OV_SLOTS.hasOwnProperty(it.slot) && ovStr(it.text, 600)) {
        out.ops.push({ id: id, k: 'note', slot: it.slot, text: it.text, tone: it.tone === 'banner' ? 'banner' : 'note' });
      } else if (it.k === 'img' && OV_SLOTS.hasOwnProperty(it.slot)) {
        out.ops.push({ id: id, k: 'img', slot: it.slot, alt: ovStr(it.alt, 120) || 'A picture' });
      } else if ((it.k === 'ticket' || it.k === 'untix') && OV_DAY.test(String(it.date || '')) && it.card &&
                 OV_TICKET.test(String(it.k === 'untix' ? it.ticket_id : it.card.id || ''))) {
        if (it.k === 'untix') { out.ops.push({ id: id, k: 'untix', date: it.date, tid: it.ticket_id }); return; }
        var c = it.card, legs = [];
        (Array.isArray(c.legs) ? c.legs : []).slice(0, 6).forEach(function (lg) {
          if (!lg || !ovStr(lg.player, 60) || !ovStr(lg.market, 60)) return;
          var kal = (Array.isArray(lg.links) ? lg.links : []).filter(function (x) {
            return x && (x.venue === 'KAL' || x.venue === 'DKP') && typeof x.cents === 'number' && x.cents >= 1 &&
                   x.cents <= 99 && Math.floor(x.cents) === x.cents;
          });
          legs.push({ player: lg.player, market: lg.market, links: kal, note: ovStr(lg.note, 300) });
        });
        if (!legs.length || !ovStr(c.title, 120)) return;
        out.ops.push({ id: id, k: 'ticket', date: it.date, tid: c.id, title: c.title, matchup: ovStr(c.matchup, 120),
                       time: ovStr(c.time, 200), asof: ovStr(c.asof, 400), legs: legs });
      }
    });
    /* a change taken back after the site's own files carried it: by its id alone, switched off by its class */
    (Array.isArray(doc.gone) ? doc.gone : []).slice(0, 60).forEach(function (g) {
      if (!g || !OV_ID.test(String(g.id || ''))) return;
      out.gone.push({ id: g.id, k: String(g.k || '') });
    });
    return out;
  }

  var ovDone = {}, ovImg = {}, ovTxt = {}, ovRev = -1;
  function ovToday() {
    try { return new Date().toLocaleDateString('en-CA', { timeZone: 'America/Los_Angeles' }); } catch (e) { return ''; }
  }
  function ovEach(sel, fn) {
    try { Array.prototype.forEach.call(document.querySelectorAll(sel), fn); } catch (e) {}
  }
  function ovTextNodes(fn) {
    if (!document.body || !document.createTreeWalker) return;
    var w = document.createTreeWalker(document.body, 4, null), n, all = [];
    while ((n = w.nextNode())) all.push(n);
    all.forEach(function (t) {
      var p = t.parentNode;
      if (p && p.closest && p.closest(OV_KEEP_OUT)) return;
      fn(t);
    });
  }
  /* -> the text nodes it changed, each with its words before and after, so the change can be taken back on exactly
     those nodes and nowhere else */
  function ovReplaceText(find, rep) {
    var changed = [];
    ovTextNodes(function (t) {
      if (t.nodeValue && t.nodeValue.indexOf(find) !== -1) {
        var was = t.nodeValue;
        t.nodeValue = was.split(find).join(rep);
        changed.push({ n: t, was: was, now: t.nodeValue });
      }
    });
    return changed;
  }
  function ovUnreplace(changed) {
    (changed || []).forEach(function (c) { if (c.n && c.n.nodeValue === c.now) c.n.nodeValue = c.was; });
  }
  function ovHolder(slot) {
    var hold = document.querySelector('.ov-blocks[data-slot="' + slot + '"]');
    if (hold) return hold;
    hold = el('div', 'ov-blocks');
    hold.setAttribute('data-slot', slot);
    if (slot === 'footer') {
      var foot = document.querySelector('.foot');
      if (!foot || !foot.parentNode) return null;
      foot.parentNode.insertBefore(hold, foot);
    } else {
      var st = document.getElementById('st-' + OV_SLOTS[slot]);
      if (!st) return null;
      st.insertBefore(hold, st.firstChild);
    }
    return hold;
  }
  function ovTicketBox() {
    var box = document.getElementById('rpOvTix');
    if (box) return box;
    var st = document.getElementById('st-wooder');
    if (!st) return null;
    box = el('div', 'ov-tix');
    box.id = 'rpOvTix';
    var anchor = document.getElementById('rpBatchIdeas');
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(box, anchor); else st.appendChild(box);
    return box;
  }
  function ovTicket(op) {
    var card = el('div', 'rpnpick ov-ticket ov-' + op.id);
    card.appendChild(el('div', 'ov-ticket-title', op.title));
    if (op.matchup) card.appendChild(el('div', 'sub', op.matchup + (op.time ? ' · ' + op.time : '')));
    op.legs.forEach(function (lg) {
      var line = lg.player + ' · ' + lg.market;
      lg.links.forEach(function (x) { line += ' · ' + x.venue + ' ' + x.cents + 'c'; });
      card.appendChild(el('div', 'ov-leg', line));
      if (lg.note) card.appendChild(el('div', 'sub', lg.note));
    });
    if (op.asof) card.appendChild(el('div', 'sub', op.asof));
    return card;
  }

  function ovApply(doc) {
    var plan = ovPlan(doc), now = {}, day = ovToday(), tix = {};
    plan.ops.forEach(function (op) { now[op.id] = op; if (op.k === 'ticket' || op.k === 'untix') tix[op.tid] = op; });
    /* what was applied and is no longer in the document is taken off */
    Object.keys(ovDone).forEach(function (id) {
      if (now[id]) return;
      try { ovDone[id](); } catch (e) {}
      delete ovDone[id];
    });
    plan.ops.forEach(function (op) {
      if (ovDone[op.id] && op.k !== 'style' && op.k !== 'hide' && op.k !== 'text') return;
      try {
        if (op.k === 'var') {
          var root = document.documentElement, was = root.style.getPropertyValue(op.name);
          root.style.setProperty(op.name, op.value);
          ovDone[op.id] = function () { if (was) root.style.setProperty(op.name, was); else root.style.removeProperty(op.name); };
        } else if (op.k === 'style' || op.k === 'hide') {
          var prop = op.k === 'hide' ? 'display' : op.prop, val = op.k === 'hide' ? 'none' : op.value;
          ovEach(op.sel, function (n) {
            if (n.closest && n.closest(op.k === 'hide' ? '#st-trinity' : OV_KEEP_OUT.replace('#rpNavRec,', ''))) return;
            if (n.getAttribute('data-ov-' + op.id)) return;
            n.setAttribute('data-ov-' + op.id, n.style.getPropertyValue(prop) || '-');
            n.style.setProperty(prop, val, 'important');
          });
          ovDone[op.id] = function () {
            ovEach('[data-ov-' + op.id + ']', function (n) {
              var was = n.getAttribute('data-ov-' + op.id);
              n.removeAttribute('data-ov-' + op.id);
              if (was && was !== '-') n.style.setProperty(prop, was); else n.style.removeProperty(prop);
            });
          };
        } else if (op.k === 'text') {
          ovTxt[op.id] = (ovTxt[op.id] || []).concat(ovReplaceText(op.find, op.replace));
          ovDone[op.id] = function () { ovUnreplace(ovTxt[op.id]); delete ovTxt[op.id]; };
        } else if ((op.k === 'note' || op.k === 'img') && !document.querySelector('.ov-' + op.id)) {
          var hold = ovHolder(op.slot);
          if (!hold) return;
          var b = el('div', 'ov-block ov-' + op.tone + ' ov-' + op.id + (op.k === 'img' ? ' ov-img' : ''),
                     op.k === 'note' ? op.text : null);
          if (op.k === 'img') {
            var put = function (im) {
              var url = shotUrl(im);
              if (!url) return;
              var img = el('img');
              img.alt = op.alt;
              img.src = url;
              b.appendChild(img);
            };
            if (ovImg[op.id]) put(ovImg[op.id]);
            else fetch(TRINITY_ENDPOINT + '/overrides?img=' + op.id, { cache: 'no-store' })
              .then(function (r) { return r.ok ? r.json() : null; })
              .then(function (im) { if (im) { ovImg[op.id] = im; put(im); } })
              .catch(function () { /* no picture, nothing else changes */ });
          }
          hold.appendChild(b);
          ovDone[op.id] = function () { if (b.parentNode) b.parentNode.removeChild(b); };
        } else if (op.k === 'ticket' && op.date === day && tix[op.tid] === op) {
          var built = document.getElementById('tk-' + op.tid);
          if (built && !(built.closest && built.closest('#rpOvTix'))) return;      /* the site's own build has it */
          var box = ovTicketBox();
          if (!box) return;
          var c = ovTicket(op);
          c.id = 'tk-' + op.tid;
          ovEach('#rpOvTix #tk-' + op.tid, function (n) { if (n.parentNode) n.parentNode.removeChild(n); });
          box.appendChild(c);
          ovDone[op.id] = function () { if (c.parentNode) c.parentNode.removeChild(c); };
        } else if (op.k === 'untix' && op.date === day) {
          ovEach('#tk-' + op.tid, function (n) { n.style.setProperty('display', 'none', 'important'); });
          ovDone[op.id] = function () { ovEach('#tk-' + op.tid, function (n) { n.style.removeProperty('display'); }); };
        }
      } catch (e) { /* one change that cannot be shown leaves every other one standing */ }
    });
    /* taken back after the site's own files carry it: switched off by class, and words put back */
    plan.gone.forEach(function (g) {
      try {
        document.documentElement.classList.add('ov-off-' + g.id);
        ovEach('.ov-' + g.id, function (n) { n.style.setProperty('display', 'none', 'important'); });
      } catch (e) {}
    });
  }

  function ovLoad(fresh) {
    if (typeof fetch !== 'function') return;
    fetch(TRINITY_ENDPOINT + '/overrides' + (fresh ? '?v=' + Date.now() : ''), { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || typeof d.rev !== 'number') return;
        if (d.rev === ovRev) { ovApply(d); return; }               /* same document: reapply to new elements */
        ovRev = d.rev;
        ovApply(d);
      })
      .catch(function () { /* the page stays exactly as it was built */ });
  }
  function ovStart() {
    ovLoad(false);
    setInterval(function () { if (!document.hidden) ovLoad(false); }, OV_POLL_MS);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) ovLoad(false); });
  }

  var restoring = false;
  function row(who, text, cites, extra, force) {
    if (!restoring) keep(who, text, cites, extra);
    var stick = force || atBottom();
    var r = el('div', 'tr-row ' + who + (extra ? ' ' + extra : ''));
    var b = el('div', 'tr-bub');
    b.appendChild(document.createTextNode(text));
    if (cites && cites.length) {
      var c = el('div', 'tr-cites', 'From: ' + cites.join(', '));
      b.appendChild(c);
    }
    r.appendChild(b);
    log.appendChild(r);
    if (stick) log.scrollTop = log.scrollHeight;
    return r;
  }

  /* SIGNING OUT STARTS THE CONVERSATION OVER. When a signed-in person signs out (or their session ends), everything
     said while signed in is cleared from the page and from this tab's storage, and the chat is back at her intro:
     the greeting and the suggestions, as a new visitor sees it. A sign-in that was only asked for and never opened
     is not a sign-out and clears nothing. */
  function resetToIntro() {
    stopFollowing();
    kept = [];
    try { sessionStorage.removeItem(HISTORY); sessionStorage.removeItem(JOBS); sessionStorage.removeItem(SHOTS); } catch (e) {}
    if (log) log.textContent = '';
    maskInput(false);
    if (input && input.style) input.style.height = '';
    greeted = false;
    greetOnce();
    if (input) input.value = '';
  }
  /* A sign-in that ended without the person asking (the Mac restarted, an hour idle, the twelve-hour cap) also
     starts the conversation over, and then she says why under her greeting, so the last thing they sent is not
     silently gone and a change they were waiting on is not silently dropped. */
  var FOLLOW_ENDED = 'Your sign-in has closed, so I stopped following that change. Say your name to sign in ' +
                     'again, and ask "my changes" to see how it went.';
  function sessionClosed(note) {
    var was = signedIn();
    setSession('');
    showWho('');
    if (was) startOver(note);
  }
  function startOver(note) {
    var wasFollowing = Object.keys(following).length > 0;
    resetToIntro();
    if (note) row('her', note, null, '', true);
    if (wasFollowing && note !== FOLLOW_ENDED) row('her', FOLLOW_ENDED, null, '', true);
  }

  /* Once per visit, not once per browser: the conversation is not kept between visits, so a returning visitor who
     was greeted before would otherwise open the tab to an empty box with no greeting and no suggestions. */
  var greeted = false;
  function greetOnce() {
    if (greeted || (log && log.children.length)) return;
    greeted = true;
    row('her', GREETING);
    if (chips) chips.hidden = false;
  }

  /* While an answer is on its way only SENDING waits: the box stays live and keeps its focus, so the next question
     can be typed and a space bar press never falls through to the page and scrolls it away. */
  var queuedPhoto = null;
  function lock(on) {
    inFlight = on;
    if (send) send.disabled = on;
    if (secretBtn) secretBtn.disabled = on;
    var pb = document.getElementById('trPhoto');
    if (pb) pb.disabled = on;
    if (on) return;
    if (queuedPhoto) {                          /* a photo picked while she was answering goes now, not nowhere */
      var f = queuedPhoto;
      queuedPhoto = null;
      setTimeout(function () { sendPhoto(f); }, 0);
      return;
    }
    holdReloadCheck();
  }

  /* A SITE CHANGE ON ITS WAY. When a signed-in request becomes a change to the site, the reply carries the change's
     id, and the page asks how it is going until it is live (or will not be), saying each new step once. Only the
     person who asked is told: the Mac answers a change that is not theirs exactly like one that does not exist. */
  var JOB_RE = /^[0-9]{8}-[0-9]{6}-[a-z]+-[0-9a-f]{6}$/;
  /* A change can take longer than half an hour (the coder, the checks and the wait for it to go live each have
     their own limits), so the page keeps asking for two hours, less often as it goes, and asks at once when the
     phone wakes up. When the window closes it asks one last time and, if the change is still on its way, says so
     and lets it go, instead of going quiet. */
  var FOLLOW_FOR_MS = 2 * 60 * 60 * 1000;
  var YOUNG_MS = 30 * 1000;
  var STILL_GOING = 'That change is still on its way. Ask me "is it live?" any time and I will tell you where it is.';
  var following = {};

  function stopFollowing() {
    Object.keys(following).forEach(function (job) { clearTimeout(following[job].timer); });
    following = {};
  }

  function follow(job, said, since) {
    if (typeof job !== 'string' || !JOB_RE.test(job) || following[job]) return;
    var started = since || Date.now(), last = String(said || '');
    var f = following[job] = { timer: 0, busy: false, wake: null };
    keepJob(job, last, false);
    var mine = function () { return following[job] === f; };
    var stop = function () { clearTimeout(f.timer); if (mine()) delete following[job]; keepJob(job, '', true); };
    var later = function (ms) { clearTimeout(f.timer); f.timer = setTimeout(tick, ms); };
    var letGo = function () { stop(); row('her', STILL_GOING, null, '', false); };
    var tick = function () {
      if (!mine() || f.busy) return;
      if (!getSession()) { stop(); return; }
      var last_call = Date.now() - started > FOLLOW_FOR_MS;
      f.busy = true;
      fetch(TRINITY_ENDPOINT + '/job', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ session: getSession(), job: job }),
        cache: 'no-store'
      }).then(function (r) {
        return r.json().then(function (d) { return { status: r.status, body: d }; });
      }).then(function (res) {
        f.busy = false;
        if (!mine()) return;
        var d = res.body || {};
        if (res.status === 403) { stop(); sessionClosed(FOLLOW_ENDED); return; }
        if (res.status === 404) { stop(); return; }
        if (res.status !== 200) { if (last_call) letGo(); else later(30000); return; }
        if (typeof d.answer === 'string' && d.answer && d.answer !== last) {
          last = d.answer;
          var jr = row('her', d.answer, null, '', false);
          if (d.image) showShot(jr, d.image, job, d.answer);
          keepJob(job, last, false);
        }
        if (d.done) { stop(); return; }
        if (last_call) { letGo(); return; }
        // A young change is asked about every two seconds, so the moment it is live is the moment she says so;
        // after half a minute the asking backs off as before. The edge keeps no counter for these asks.
        var age = Date.now() - started;
        later(age < YOUNG_MS ? 2000 : age < 120000 ? 8000 : age < 600000 ? 20000 : 60000);
      }).catch(function () {
        f.busy = false;
        if (!mine()) return;
        if (last_call) letGo(); else later(30000);
      });
    };
    f.wake = function () { if (mine() && !f.busy) { clearTimeout(f.timer); tick(); } };
    later(since ? 1000 : 2000);
  }

  function wakeFollowers() {
    Object.keys(following).forEach(function (job) { if (following[job].wake) following[job].wake(); });
  }
  document.addEventListener('visibilitychange', function () { if (!document.hidden) wakeFollowers(); });
  window.addEventListener('pageshow', wakeFollowers);

  /* Sent while a sign-in is open or asked for, a message that may have arrived is never sent again by the page:
     a change sent twice is two changes. She says she could not confirm it instead, and how to find out. */
  var UNSURE_IN = 'I could not confirm that reached me, so it may or may not have gone through. If it was a change ' +
                  'to the site, ask me "my changes" before sending it again.';
  var UNSURE_SIGNIN = 'I could not confirm that reached me. Try your passphrase again in a moment.';
  /* In the middle of changing a passphrase what was sent may have been a passphrase or a "cancel": sent again, the
     Mac says where the change stands, even when it had already ended. */
  var UNSURE_CHANGE = 'I could not confirm that reached me. Send the same again in a moment and I will tell you where it stands.';

  function ask(q) {
    q = whole(String(q || '').replace(/\s+/g, ' ').trim().slice(0, MAX_Q));
    if (!q || inFlight) return;
    if (chips) chips.hidden = true;
    var wasSecret = secretNext || secretWanted();
    var held = !!getSession();
    var unsure = signedIn() ? (wasSecret ? UNSURE_CHANGE : UNSURE_IN) : UNSURE_SIGNIN;
    /* Read before this message is shown, so the turns are what came before it; none at all while a sign-in is open
       or asked for. */
    var turns = (held || wasSecret) ? [] : recentTurns();
    row('me', wasSecret ? '••••••' : q, null, '', true);
    var mine = kept[kept.length - 1];
    if (input) { input.value = ''; if (input.style) input.style.height = ''; }
    if (secretBox) secretBox.value = '';
    lock(true);
    var pend = row('her', PENDING, null, 'tr-pending', true);

    /* The mask is never switched off on a send: after every outcome (an answer, a limit, a dropped line, the
       timeout) it is worked out again from what the page holds, so a passphrase asked for stays masked until the
       sign-in opens or ends. */
    var done = false, wantSecret = false;
    var finish = function (text, cites, declined) {
      if (done) { maskInput(secretWanted() || wantSecret); return null; }
      done = true;
      if (pend && pend.parentNode) pend.parentNode.removeChild(pend);
      var added = text != null ? row('her', text, cites, declined ? 'declined' : '', true) : null;
      lock(false);
      maskInput(secretWanted() || wantSecret);
      focusBox();
      return added;
    };
    var lost = function () { finish(held ? unsure : OFFLINE, null, false); };

    var ctrl = (typeof AbortController === 'function') ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctrl) ctrl.abort(); lost(); }, 45000);
    var body = held ? JSON.stringify({ question: q, session: getSession() }) : askBody(q, turns);

    /* A dropped connection (the line to the Mac reconnects in seconds) is tried again twice before she says she
       is not answering - for a public question only. Only a failure to ARRIVE is retried; an answer of any kind is
       never asked twice. */
    var post = function (tries) {
      return fetch(TRINITY_ENDPOINT + '/ask', {
        method: 'POST', headers: { 'content-type': 'application/json' }, body: body,
        signal: ctrl ? ctrl.signal : undefined, cache: 'no-store'
      }).then(function (r) {
        if ((r.status === 502 || r.status === 503 || r.status === 504) && tries < 2 && !held) {
          return new Promise(function (ok) { setTimeout(ok, 4000 * (tries + 1)); }).then(function () { return post(tries + 1); });
        }
        return r;
      }, function (err) {
        if (held || done || tries >= 2 || (err && err.name === 'AbortError')) throw err;
        return new Promise(function (ok) { setTimeout(ok, 4000 * (tries + 1)); }).then(function () { return post(tries + 1); });
      });
    };

    post(0).then(function (r) {
      if (held && r.status >= 500) return { status: r.status, body: null };
      return r.json().then(function (d) { return { status: r.status, body: d }; });
    }).then(function (res) {
      clearTimeout(timer);
      if (res.body === null) { lost(); return; }
      var d = res.body || {};
      var wasIn = signedIn();
      /* A reply that opened, asked for or ended a sign-in makes the message that caused it, and the reply, the
         door's: neither is ever sent back to her as a turn. */
      var door = typeof d.session === 'string' || !!d.next || (typeof d.as === 'string' && !!d.as);
      /* A token without a name is a sign-in in progress: whoever was signed in before is not any more. */
      if (typeof d.session === 'string') { setSession(d.session); if (!d.session || !d.as) showWho(''); }
      if (typeof d.as === 'string' && d.as && getSession()) showWho(d.as);
      wantSecret = d.next === 'passphrase' || (typeof d.answer === 'string' && /passphrase\?\s*$/i.test(d.answer));
      if (res.status === 200) setAsked(wantSecret && !!getSession());   /* a limit is not an answer: it keeps the box */
      var said = typeof d.answer === 'string' && d.answer ? d.answer : '';
      if (wasIn && !signedIn()) {
        /* Signed out because they said so: back to her intro and nothing more. Ended any other way: back to her
           intro, and her reply under it says what happened to what they just sent. */
        var asked = /^\s*(Signed out|You are signed out)\b/i.test(said);
        startOver(asked ? '' : said);
        finish(null);
        return;
      }
      /* 429 carries an answer in her voice, so it renders like any other reply. */
      if (said) {
        var cites = Array.isArray(d.cites) ? d.cites.filter(function (c) {
          /* A citation is a store NAME. Anything that looks like a path is a defect upstream and is
             not shown, so a leak can never be displayed by this page. */
          return typeof c === 'string' && c && c.indexOf('/') === -1 && c.indexOf('\\') === -1;
        }) : [];
        notices(d.notices);
        var fr = finish(said, cites, d.answered === false);
        if (door) markPrivate(mine);
        if (d.image) showShot(fr, d.image, d.job, said);
        if (d.overrides) ovLoad(true);
        if (d.job) follow(d.job, said);
      } else {
        finish(OFFLINE, null, false);
        if (door) markPrivate(mine);
      }
    }).catch(function () {
      clearTimeout(timer);
      lost();
    });
  }

  /* PHOTOS, signed in only. The photo is redrawn on a canvas before it leaves the phone: that drops every byte of
     metadata a camera writes (the location first of all), applies the rotation the camera recorded so it is not
     sent sideways, and caps the long edge so a full-resolution photo does not crawl over a phone connection. The
     server strips metadata again regardless, because a server does not trust a browser to have done it. */
  var MAX_EDGE = 2560;

  function toJpeg(file) {
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () {
        var w = img.naturalWidth, h = img.naturalHeight, k = Math.min(1, MAX_EDGE / Math.max(w, h));
        var c = document.createElement('canvas');
        c.width = Math.max(1, Math.round(w * k));
        c.height = Math.max(1, Math.round(h * k));
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url);
        c.toBlob(function (b) { b ? resolve(b) : reject(new Error('could not encode')); }, 'image/jpeg', 0.9);
      };
      img.onerror = function () {
        URL.revokeObjectURL(url);
        var e = new Error('cannot open');
        e.unreadable = true;
        reject(e);
      };
      img.src = url;
    });
  }

  function blobToBase64(b) {
    return new Promise(function (resolve, reject) {
      var r = new FileReader();
      r.onload = function () { resolve(String(r.result).split(',')[1] || ''); };
      r.onerror = reject;
      r.readAsDataURL(b);
    });
  }

  /* What she says when a photo fails depends on how far it got. Before it is sent, nothing was passed on, and a
     kind of photo this browser cannot open (an iPhone's HEIC on Android) will never go, so she says so instead of
     "try again". Once it is sent, a lost reply may hide a photo that arrived and a request already taken, so she
     says she could not confirm it and how to check, and it is not sent a second time. */
  var PHOTO_NOT_SENT = 'That photo did not go through, so nothing was passed on. Try it again in a moment.';
  var PHOTO_UNREADABLE = 'I cannot open that kind of photo on this phone, so nothing was passed on. Try a JPEG or a ' +
                         'screenshot.';
  var PHOTO_UNSURE = 'I could not confirm that photo arrived, so it may or may not have gone through. Ask me ' +
                     '"my changes" before sending it again.';

  function sendPhoto(file) {
    if (!file || !signedIn()) return;
    if (inFlight) { queuedPhoto = file; return; }
    var caption = (input && input.value || '').replace(/\s+/g, ' ').trim().slice(0, MAX_Q);
    lock(true);
    var mine = row('me', caption || 'Photo', null, '', true);
    var pend = row('her', 'Sending the photo', null, 'tr-pending', true);
    var sent = false;
    var done = function (text, declined) {
      if (pend && pend.parentNode) pend.parentNode.removeChild(pend);
      if (text != null) row('her', text, null, declined ? 'declined' : '', true);
      if (input) { input.value = ''; input.focus(); }
      lock(false);
    };
    toJpeg(file).then(function (jpg) {
      var thumb = document.createElement('img');
      thumb.className = 'tr-thumb';
      thumb.alt = 'the photo you sent';
      thumb.src = URL.createObjectURL(jpg);
      mine.querySelector('.tr-bub').appendChild(thumb);
      return blobToBase64(jpg);
    }).then(function (b64) {
      sent = true;
      return fetch(TRINITY_ENDPOINT + '/upload', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ session: getSession(), caption: caption, image: b64 }),
        cache: 'no-store'
      });
    }).then(function (r) {
      if (r.status >= 500) return { status: r.status, body: null };
      return r.json().then(function (d) { return { status: r.status, body: d }; });
    }).then(function (res) {
      var d = res.body || {};
      var said = typeof d.answer === 'string' && d.answer ? d.answer : '';
      if (res.status === 403) {
        done(null);
        sessionClosed(said || 'Your sign-in has closed, so that photo was not passed on. Say your name to sign in again.');
        return;
      }
      if (res.body === null) { done(PHOTO_UNSURE, true); return; }
      done(said || PHOTO_UNSURE, d.answered === false);
      if (d.overrides) ovLoad(true);
      if (d.job) follow(d.job, said);
    }).catch(function (e) {
      done(sent ? PHOTO_UNSURE : (e && e.unreadable ? PHOTO_UNREADABLE : PHOTO_NOT_SENT), true);
    });
  }

  /* The five lists on the page are served by the endpoint, so they can never drift from the lookups
     that actually exist. The markup ships them inline as the no-JavaScript fallback; this replaces
     them when /about answers, and leaves them alone when it does not. */
  function fillAbout() {
    fetch(TRINITY_ENDPOINT + '/about', { cache: 'no-store' }).then(function (r) {
      return r.json();
    }).then(function (d) {
      if (!d) return;
      var set = function (id, text) {
        var n = document.getElementById(id);
        if (n && typeof text === 'string' && text) n.textContent = text;
      };
      var list = function (id, items) {
        var n = document.getElementById(id);
        if (!n || !Array.isArray(items) || !items.length) return;
        n.textContent = '';
        items.forEach(function (t) {
          if (typeof t === 'string' && t) n.appendChild(el('li', null, t));
        });
      };
      set('trWhat', d.what_it_is);
      set('trHow', d.how_to_read_an_answer);
      set('trObj', d.the_objective);
      var lede = document.querySelector('#st-trinity .tr-lede');
      if (lede && typeof d.who_she_is === 'string' && d.who_she_is) lede.textContent = d.who_she_is;
      list('trCan', d.what_you_can_ask);
      list('trWont', d.what_she_will_not_do);
    }).catch(function () { /* the inline copy stands */ });
  }

  /* THE SITE'S OWN RELOADS WAIT WHILE SHE IS OPEN. The page reloads itself when a new build is published and when
     the card changes (it calls window.rpReload, which falls back to location.reload). While her tab is open, or an
     answer is on its way, the reload is held and happens the moment the visitor leaves her tab - so nobody is
     thrown out in the middle of a conversation, and nothing they typed is lost. */
  var reloadWanted = false;
  function trinityOpen() {
    var sect = document.getElementById('st-trinity');
    return !!(sect && sect.classList.contains('on'));
  }
  window.rpReload = function () {
    if (inFlight || trinityOpen()) { reloadWanted = true; return; }
    location.reload();
  };
  function holdReloadCheck() {
    if (reloadWanted && !inFlight && !trinityOpen()) { reloadWanted = false; location.reload(); }
  }
  setInterval(holdReloadCheck, 2000);

  /* For a browser without :has(), the page knows when her tab is open (trinity.css hides the account button). */
  function markOpen() { if (document.body) document.body.classList.toggle('tr-open', trinityOpen()); }
  (function watchTab() {
    var sect = document.getElementById('st-trinity');
    if (!sect || typeof MutationObserver !== 'function') return;
    new MutationObserver(markOpen).observe(sect, { attributes: true, attributeFilter: ['class'] });
    markOpen();
  })();

  /* A KEY PRESSED WITH THE FOCUS OFF THE BOX GOES INTO THE BOX. With her tab open, a space bar press (or any letter)
     on the page itself - not on a link, a button or another field - is typed into her box instead of scrolling the
     page to its bottom. */
  document.addEventListener('keydown', function (e) {
    if (!trinityOpen() || !input || e.defaultPrevented || e.isComposing || e.metaKey || e.ctrlKey || e.altKey) return;
    var t = e.target;
    var n = box();
    if (t === n || (t && t.closest && t.closest('input,textarea,select,button,a,[contenteditable],[tabindex]'))) return;
    if (!e.key || e.key.length !== 1) return;
    e.preventDefault();
    n.focus();
    var v = n.value;
    if (v.length >= MAX_Q) return;
    var a = typeof n.selectionStart === 'number' ? n.selectionStart : v.length;
    var b = typeof n.selectionEnd === 'number' ? n.selectionEnd : v.length;
    n.value = v.slice(0, a) + e.key + v.slice(b);
    try { n.setSelectionRange(a + 1, a + 1); } catch (err) {}
  });

  function resumeJobs() {
    if (!getSession()) return;
    var j = jobsKept();
    Object.keys(j).forEach(function (job) { follow(job, j[job] && j[job].s, j[job] && j[job].at); });
  }

  /* Nothing runs until the tab is opened, so a visitor who never opens it pays nothing. */
  function boot() {
    if (booted) return;
    booted = true;
    if (restore()) {
      greeted = true;
      if (chips) chips.hidden = kept.some(function (m) { return m.w === 'me'; });
    } else {
      greetOnce();
    }
    resumeJobs();
    resumeShots();
    fillAbout();
  }

  function wire() {
    var sect = document.getElementById('st-trinity');
    if (!sect) return;
    log = document.getElementById('trLog');
    chips = document.getElementById('trChips');
    form = document.getElementById('trAsk');
    input = document.getElementById('trInput');
    send = document.getElementById('trSend');
    who = document.getElementById('trWho');
    if (signedIn()) showWho(mem.who);
    /* A reload in the middle of a sign-in or of a passphrase change (an iPhone drops a tab in the background while
       the passphrase is copied from another app) comes back masked. */
    if (input) maskInput(secretWanted());
    if (!log || !form || !input) return;

    form.addEventListener('submit', function (e) { e.preventDefault(); ask(input.value); });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) { e.preventDefault(); ask(input.value); }
    });
    var grow = function () {
      if (!input.style || typeof input.scrollHeight !== 'number') return;
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight + 2, 132) + 'px';
    };
    input.addEventListener('input', grow);
    var pbtn = document.getElementById('trPhoto'), pfile = document.getElementById('trFile');
    if (pbtn && pfile) {
      pbtn.addEventListener('click', function () { if (signedIn() && !inFlight) pfile.click(); });
      pfile.addEventListener('change', function () {
        var f = pfile.files && pfile.files[0];
        pfile.value = '';
        if (f) sendPhoto(f);
      });
    }
    if (chips) {
      chips.addEventListener('click', function (e) {
        var b = e.target.closest ? e.target.closest('.tr-chip') : null;
        if (b) ask(b.textContent);
      });
    }

    var open = function () { if (sect.classList.contains('on')) boot(); holdReloadCheck(); };
    open();
    document.querySelectorAll('nav.rpnav .tab[data-tab="trinity"]').forEach(function (a) {
      a.addEventListener('click', function () { setTimeout(open, 0); });
    });
    window.addEventListener('hashchange', function () { setTimeout(open, 0); });
  }

  /* THE NAV'S TWO RULES, held the moment anything changes it (owner, 2026-10-07): her tab is the LAST one, always,
     and a league never has two tabs. The page builds it that way; a script that adds a tab of its own later (a module
     once appended a second WNBA tab after hers) does not get to break either: a repeated tab is removed, the first
     one kept, and her tab goes back to the end. */
  function keepLast() {
    var bar = document.querySelector('nav.rpnav .tabs');
    if (!bar) return;
    var fix = function () {
      var seen = {}, kids = Array.prototype.slice.call(bar.children || []);
      kids.forEach(function (a) {
        var k = a.getAttribute && a.getAttribute('data-tab');
        if (!k) return;
        if (seen[k]) { if (a.parentNode) a.parentNode.removeChild(a); } else seen[k] = true;
      });
      var t = bar.querySelector('.tab[data-tab="trinity"]');
      if (t && t !== bar.lastElementChild) bar.appendChild(t);
    };
    fix();
    if (typeof MutationObserver === 'function') new MutationObserver(fix).observe(bar, { childList: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', keepLast);
  else keepLast();

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
    document.addEventListener('DOMContentLoaded', ovStart);
  } else {
    wire();
    ovStart();
  }
})();
