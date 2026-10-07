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

  /* The page's own copy is what it goes by. Storage is read once, when the page loads, and written after every
     change, so a reload keeps the sign-in; a browser that refuses storage (Safari with every cookie blocked, a
     private window that throws) still signs in and out for the life of the page, and a passphrase is never sent
     without the sign-in it belongs to. */
  var mem = { s: '', who: '' };
  try {
    mem.s = sessionStorage.getItem(SESSION) || '';
    mem.who = mem.s ? (sessionStorage.getItem(SESSION + '_who') || '') : '';
  } catch (e) {}

  function getSession() { return mem.s; }

  function setSession(v) {
    mem.s = v || '';
    try {
      if (v) sessionStorage.setItem(SESSION, v); else sessionStorage.removeItem(SESSION);
    } catch (e) {}
  }

  /* Signed in: a session and a name. A token with no name is a sign-in she has asked a passphrase for, and while
     one is held the next thing typed is the passphrase - after a failed send, a limit, a dropped line or a reload
     as much as after her prompt. */
  function signedIn() { return !!(mem.s && mem.who); }
  function pending() { return !!mem.s && !mem.who; }

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

  /* The passphrase is hidden with a text mask, not by turning the box into a password field: once a box has been a
     password field, Safari keeps its keychain key on it and offers to save "passwords" for the rest of the
     conversation. Only a browser without the mask falls back to a password field. Autocorrect, capitals and
     spelling are off while a passphrase is typed, so it never lands in the keyboard's dictionary.

     A phone's keyboard reads those settings when a box GAINS focus, and an iPhone (Safari and Chrome alike) never
     reads them again while that box keeps it - and the box does keep it when the name is sent with the keyboard's
     Send key. So when the box has the focus and the mask goes on or off, a fresh box with the new settings takes
     its place and the focus moves to it, which an iPhone treats as a new box and reloads the keyboard for. */
  var TEXT_MASK = !!(window.CSS && CSS.supports && CSS.supports('-webkit-text-security', 'disc'));
  function traits(n, on) {
    if (TEXT_MASK) {
      n.type = 'text';
      n.style.webkitTextSecurity = on ? 'disc' : '';
    } else {
      n.type = on ? 'password' : 'text';
    }
    n.setAttribute('autocomplete', 'off');
    n.setAttribute('autocapitalize', on ? 'off' : 'sentences');
    n.setAttribute('autocorrect', on ? 'off' : 'on');
    n.spellcheck = !on;
    n.placeholder = on ? 'Passphrase' : 'Ask about a pick, a refusal or the record';
  }
  function maskInput(on) {
    on = !!on;
    var changed = on !== secretNext;
    secretNext = on;
    if (!input) return;
    var old = input, parent = old.parentNode;
    if (changed && parent && document.activeElement === old && typeof old.cloneNode === 'function') {
      var n = old.cloneNode(false);
      n.value = '';
      traits(n, on);
      old.removeAttribute('id');
      parent.insertBefore(n, old);
      try { n.focus({ preventScroll: true }); } catch (e) { n.focus(); }
      parent.removeChild(old);
      input = n;
      return;
    }
    traits(old, on);
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
    kept.push({ w: who, t: String(text).slice(0, 4000), c: cites && cites.length ? cites : null, x: extra || '' });
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
  function jobsKept() {
    try { var j = JSON.parse(sessionStorage.getItem(JOBS) || '{}'); return (j && typeof j === 'object') ? j : {}; }
    catch (e) { return {}; }
  }
  function keepJob(job, said, done) {
    var j = jobsKept();
    if (done) delete j[job]; else j[job] = { s: String(said || ''), at: j[job] ? j[job].at : Date.now() };
    try { sessionStorage.setItem(JOBS, JSON.stringify(j)); } catch (e) {}
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
    try { sessionStorage.removeItem(HISTORY); sessionStorage.removeItem(JOBS); } catch (e) {}
    if (log) log.textContent = '';
    maskInput(false);
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
          row('her', d.answer, null, '', false);
          keepJob(job, last, false);
        }
        if (d.done) { stop(); return; }
        if (last_call) { letGo(); return; }
        var age = Date.now() - started;
        later(age < 120000 ? 8000 : age < 600000 ? 20000 : 60000);
      }).catch(function () {
        f.busy = false;
        if (!mine()) return;
        if (last_call) letGo(); else later(30000);
      });
    };
    f.wake = function () { if (mine() && !f.busy) { clearTimeout(f.timer); tick(); } };
    later(since ? 1000 : 8000);
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

  function ask(q) {
    q = String(q || '').replace(/\s+/g, ' ').trim().slice(0, MAX_Q);
    if (!q || inFlight) return;
    if (chips) chips.hidden = true;
    var wasSecret = secretNext || pending();
    var held = !!getSession();
    var unsure = signedIn() ? UNSURE_IN : UNSURE_SIGNIN;
    row('me', wasSecret ? '\u2022\u2022\u2022\u2022\u2022\u2022' : q, null, '', true);
    if (input) input.value = '';
    lock(true);
    var pend = row('her', PENDING, null, 'tr-pending', true);

    /* The mask is never switched off on a send: after every outcome (an answer, a limit, a dropped line, the
       timeout) it is worked out again from what the page holds, so a passphrase asked for stays masked until the
       sign-in opens or ends. */
    var done = false, wantSecret = false;
    var finish = function (text, cites, declined) {
      if (done) { maskInput(pending() || wantSecret); return; }
      done = true;
      if (pend && pend.parentNode) pend.parentNode.removeChild(pend);
      if (text != null) row('her', text, cites, declined ? 'declined' : '', true);
      lock(false);
      maskInput(pending() || wantSecret);
      if (input) input.focus();
    };
    var lost = function () { finish(held ? unsure : OFFLINE, null, false); };

    var ctrl = (typeof AbortController === 'function') ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctrl) ctrl.abort(); lost(); }, 45000);
    var body = JSON.stringify(held ? { question: q, session: getSession() } : { question: q });

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
      /* A token without a name is a sign-in in progress: whoever was signed in before is not any more. */
      if (typeof d.session === 'string') { setSession(d.session); if (!d.session || !d.as) showWho(''); }
      if (typeof d.as === 'string' && d.as && getSession()) showWho(d.as);
      wantSecret = d.next === 'passphrase' || (typeof d.answer === 'string' && /passphrase\?\s*$/i.test(d.answer));
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
        finish(said, cites, d.answered === false);
        if (d.job) follow(d.job, said);
      } else {
        finish(OFFLINE, null, false);
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
    if (t === input || (t && t.closest && t.closest('input,textarea,select,button,a,[contenteditable],[tabindex]'))) return;
    if (!e.key || e.key.length !== 1) return;
    e.preventDefault();
    input.focus();
    var v = input.value;
    if (v.length >= MAX_Q) return;
    var a = typeof input.selectionStart === 'number' ? input.selectionStart : v.length;
    var b = typeof input.selectionEnd === 'number' ? input.selectionEnd : v.length;
    input.value = v.slice(0, a) + e.key + v.slice(b);
    try { input.setSelectionRange(a + 1, a + 1); } catch (err) {}
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
    /* A reload in the middle of a sign-in (an iPhone drops a tab in the background while the passphrase is copied
       from another app) comes back masked. */
    if (input) maskInput(pending());
    if (!log || !form || !input) return;

    form.addEventListener('submit', function (e) { e.preventDefault(); ask(input.value); });
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
  } else {
    wire();
  }
})();
