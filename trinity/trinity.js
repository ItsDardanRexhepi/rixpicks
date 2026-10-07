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
     * It sends one question at a time and never retries a send on its own.

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
  var PENDING = 'Reading the record';

  var log, chips, form, input, send, who, booted = false, inFlight = false;

  /* SIGNING IN. Two people may sign in here, and only on her prompt. The session lives in sessionStorage, so it
     belongs to this tab alone and is gone when the tab closes. When she has just asked for a passphrase, the next
     thing typed is masked as it is typed, and shown in the conversation as dots - the passphrase is never on the
     screen and never in the log. */
  var SESSION = 'trinity_session';
  var secretNext = false;

  function getSession() {
    try { return sessionStorage.getItem(SESSION) || ''; } catch (e) { return ''; }
  }

  function setSession(v) {
    try {
      if (v) sessionStorage.setItem(SESSION, v); else sessionStorage.removeItem(SESSION);
    } catch (e) {}
  }

  function showWho(name) {
    try { if (name) sessionStorage.setItem(SESSION + '_who', name); else sessionStorage.removeItem(SESSION + '_who'); }
    catch (e) {}
    var pb = document.getElementById('trPhoto');
    if (pb) pb.hidden = !name;
    if (!who) return;
    if (name) { who.textContent = 'Signed in as ' + name + '. Say "sign out" when you are done.'; who.hidden = false; }
    else { who.textContent = ''; who.hidden = true; }
  }

  function maskInput(on) {
    secretNext = on;
    if (!input) return;
    input.type = on ? 'password' : 'text';
    input.placeholder = on ? 'Passphrase' : 'Ask about a pick, a refusal or the record';
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
  function row(who, text, cites, extra, force) {
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

  /* Once per visit, not once per browser: the conversation is not kept between visits, so a returning visitor who
     was greeted before would otherwise open the tab to an empty box with no greeting and no suggestions. */
  var greeted = false;
  function greetOnce() {
    if (greeted || (log && log.children.length)) return;
    greeted = true;
    row('her', GREETING);
    if (chips) chips.hidden = false;
  }

  function lock(on) {
    inFlight = on;
    if (input) input.disabled = on;
    if (send) send.disabled = on;
  }

  /* A SITE CHANGE ON ITS WAY. When a signed-in request becomes a change to the site, the reply carries the change's
     id, and the page asks how it is going until it is live (or will not be), saying each new step once. Only the
     person who asked is told: the Mac answers a change that is not theirs exactly like one that does not exist. */
  var JOB_RE = /^[0-9]{8}-[0-9]{6}-[a-z]+-[0-9a-f]{6}$/;
  var FOLLOW_FOR_MS = 30 * 60 * 1000;

  function follow(job, said) {
    if (typeof job !== 'string' || !JOB_RE.test(job)) return;
    var started = Date.now(), last = String(said || '');
    var tick = function () {
      if (!getSession() || Date.now() - started > FOLLOW_FOR_MS) return;
      fetch(TRINITY_ENDPOINT + '/job', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ session: getSession(), job: job }),
        cache: 'no-store'
      }).then(function (r) {
        return r.json().then(function (d) { return { status: r.status, body: d }; });
      }).then(function (res) {
        var d = res.body || {};
        if (res.status === 403) { setSession(''); showWho(''); return; }
        if (res.status === 404) return;
        if (res.status !== 200) { setTimeout(tick, 30000); return; }
        if (typeof d.answer === 'string' && d.answer && d.answer !== last) {
          last = d.answer;
          row('her', d.answer, null, '', false);
        }
        if (!d.done) setTimeout(tick, Date.now() - started < 120000 ? 8000 : 20000);
      }).catch(function () { setTimeout(tick, 30000); });
    };
    setTimeout(tick, 8000);
  }

  function ask(q) {
    q = String(q || '').replace(/\s+/g, ' ').trim().slice(0, MAX_Q);
    if (!q || inFlight) return;
    if (chips) chips.hidden = true;
    var wasSecret = secretNext;
    row('me', wasSecret ? '\u2022\u2022\u2022\u2022\u2022\u2022' : q, null, '', true);
    maskInput(false);
    if (input) input.value = '';
    lock(true);
    var pend = row('her', PENDING, null, 'tr-pending', true);

    var done = false;
    var finish = function (text, cites, declined) {
      if (done) return;
      done = true;
      if (pend && pend.parentNode) pend.parentNode.removeChild(pend);
      row('her', text, cites, declined ? 'declined' : '', true);
      lock(false);
      if (input) input.focus();
    };

    var ctrl = (typeof AbortController === 'function') ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctrl) ctrl.abort(); finish(OFFLINE, null, false); }, 30000);

    fetch(TRINITY_ENDPOINT + '/ask', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(getSession() ? { question: q, session: getSession() } : { question: q }),
      signal: ctrl ? ctrl.signal : undefined,
      cache: 'no-store'
    }).then(function (r) {
      return r.json().then(function (d) { return { status: r.status, body: d }; });
    }).then(function (res) {
      clearTimeout(timer);
      var d = res.body || {};
      if (typeof d.session === 'string') { setSession(d.session); if (!d.session) showWho(''); }
      if (typeof d.as === 'string' && d.as) showWho(d.as);
      if (d.next === 'passphrase' || (typeof d.answer === 'string' && /passphrase\?\s*$/i.test(d.answer))) {
        maskInput(true);
      }
      /* 429 carries an answer in her voice, so it renders like any other reply. */
      if (typeof d.answer === 'string' && d.answer) {
        var cites = Array.isArray(d.cites) ? d.cites.filter(function (c) {
          /* A citation is a store NAME. Anything that looks like a path is a defect upstream and is
             not shown, so a leak can never be displayed by this page. */
          return typeof c === 'string' && c && c.indexOf('/') === -1 && c.indexOf('\\') === -1;
        }) : [];
        finish(d.answer, cites, d.answered === false);
        if (d.job) follow(d.job, d.answer);
      } else {
        finish(OFFLINE, null, false);
      }
    }).catch(function () {
      clearTimeout(timer);
      finish(OFFLINE, null, false);
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
      img.onerror = function () { URL.revokeObjectURL(url); reject(new Error('not an image')); };
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

  function sendPhoto(file) {
    if (!file || inFlight || !getSession()) return;
    var caption = (input && input.value || '').replace(/\s+/g, ' ').trim().slice(0, MAX_Q);
    lock(true);
    var mine = row('me', caption || 'Photo', null, '', true);
    var pend = row('her', 'Sending the photo', null, 'tr-pending', true);
    var done = function (text, declined) {
      if (pend && pend.parentNode) pend.parentNode.removeChild(pend);
      row('her', text, null, declined ? 'declined' : '', true);
      if (input) input.value = '';
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
      return fetch(TRINITY_ENDPOINT + '/upload', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ session: getSession(), caption: caption, image: b64 }),
        cache: 'no-store'
      });
    }).then(function (r) {
      return r.json().then(function (d) { return { status: r.status, body: d }; });
    }).then(function (res) {
      var d = res.body || {};
      if (res.status === 403) { setSession(''); showWho(''); }
      done(typeof d.answer === 'string' && d.answer ? d.answer : OFFLINE, d.answered === false);
      if (d.job) follow(d.job, d.answer);
    }).catch(function () {
      done('That photo did not go through, so nothing was passed on. Try it again in a moment.', true);
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

  /* Nothing runs until the tab is opened, so a visitor who never opens it pays nothing. */
  function boot() {
    if (booted) return;
    booted = true;
    greetOnce();
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
    if (getSession()) {
      var n = '';
      try { n = sessionStorage.getItem(SESSION + '_who') || ''; } catch (e) {}
      if (n) showWho(n);
    }
    if (!log || !form || !input) return;

    form.addEventListener('submit', function (e) { e.preventDefault(); ask(input.value); });
    var pbtn = document.getElementById('trPhoto'), pfile = document.getElementById('trFile');
    if (pbtn && pfile) {
      pbtn.addEventListener('click', function () { if (getSession()) pfile.click(); });
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

    var open = function () { if (sect.classList.contains('on')) boot(); };
    open();
    document.querySelectorAll('nav.rpnav .tab[data-tab="trinity"]').forEach(function (a) {
      a.addEventListener('click', function () { setTimeout(open, 0); });
    });
    window.addEventListener('hashchange', function () { setTimeout(open, 0); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
})();
