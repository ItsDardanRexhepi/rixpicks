/* RixPicks slip adapter.
   Maps the site's ticket data onto the documented RPSlip ticket schema and renders it ONLY through
   RPSlip.mount (rp-slip-core.js, supplied block, unmodified). No slip HTML is written here.
   Also owns the shared live layer: DATA ONLY (verified startsAt ISO, source-confirmed clock fields, per-leg stats). The countdown, its wording and the live-clock wording are rendered by the supplied RPSlip block.
   Fail-closed: a timer reaching zero never asserts a game started; feed failure shows unavailable, never an invented clock/stat. */
(function () {
  'use strict';
  if (!window.RPSlip || window.RPApp) return;

  var PT = 'America/Los_Angeles';

  function has(v) { return v !== undefined && v !== null && v !== ''; }
  function esc(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function ptFmt(ms, opt) { try { return new Date(ms).toLocaleString('en-US', Object.assign({ timeZone: PT }, opt)); } catch (e) { return ''; } }
  function ptDay(ms) {
    var p = {};
    new Intl.DateTimeFormat('en-US', { timeZone: PT, year: 'numeric', month: '2-digit', day: '2-digit' })
      .formatToParts(new Date(ms == null ? Date.now() : ms)).forEach(function (x) { p[x.type] = x.value; });
    return p.year + '-' + p.month + '-' + p.day;
  }
  function whenLabel(ms) { return isFinite(ms) ? ptFmt(ms, { weekday: 'short', hour: 'numeric', minute: '2-digit' }).replace(',', '') : ''; }
  function pad(n) { return String(n).padStart(2, '0'); }

  function isoOf(ms) { return isFinite(ms) ? new Date(ms).toISOString() : ''; }

  /* ---------- league + phase labels (one grounded feed: ESPN summary status; NHL api-web first for NHL) ---------- */
  function leagueOfUrl(u) {
    var m = String(u || '').match(/\/sports\/([a-z]+)\/([a-z0-9.-]+)/i);
    if (!m) return '';
    var s = m[1].toLowerCase(), l = m[2].toLowerCase();
    if (s === 'football') return l === 'nfl' ? 'nfl' : 'ncaaf';
    if (s === 'basketball') return l === 'nba' ? 'nba' : (l === 'wnba' ? 'wnba' : (/^womens/.test(l) ? 'ncaaw' : 'ncaab'));
    if (s === 'hockey') return 'nhl';
    if (s === 'baseball') return 'mlb';
    if (s === 'soccer') return 'soc';
    return '';
  }
  function ord(n) { var v = n % 100; return n + (['th', 'st', 'nd', 'rd'][(v - 20) % 10] || ['th', 'st', 'nd', 'rd'][v] || 'th'); }
  function phaseOf(league, st) {
    var ty = st.type || {}, p = Number(st.period) || 0, clk = st.displayClock || '', nm = ty.name || '';
    if (/HALFTIME/.test(nm)) return 'Halftime';
    var short = ty.shortDetail || ty.detail || '';
    var c = clk && clk !== '0:00' ? ' ' + clk : (clk === '0:00' ? ' 0:00' : '');
    if (league === 'nfl' || league === 'ncaaf') {
      if (!p) return short || '';
      return (p <= 4 ? 'Q' + p : (p === 5 ? 'OT' : 'OT' + (p - 4))) + c;
    }
    if (league === 'nba' || league === 'wnba' || league === 'ncaaw') {
      if (!p) return short || '';
      return (p <= 4 ? 'Q' + p : (p === 5 ? 'OT' : 'OT' + (p - 4))) + c;
    }
    if (league === 'ncaab') {
      if (!p) return short || '';
      return (p === 1 ? 'H1' : (p === 2 ? 'H2' : (p === 3 ? 'OT' : 'OT' + (p - 2)))) + c;
    }
    if (league === 'nhl') {
      if (!p) return short || '';
      return (p <= 3 ? 'P' + p : (p === 4 ? 'OT' : 'SO')) + (p === 5 ? '' : c);
    }
    if (league === 'mlb') return short || (p ? 'Inning ' + ord(p) : '');
    if (league === 'soc') {
      if (!p) return short || '';
      return (p === 1 ? '1H' : (p === 2 ? '2H' : 'ET')) + (clk ? ' ' + clk : '');
    }
    return short || '';
  }
  function normTeam(t) { return ({ NJD: 'NJ', TBL: 'TB', SJS: 'SJ', LAK: 'LA', WAS: 'WSH' })[t] || t; }

  /* ---------- game records ---------- */
  var games = {};          /* key -> {state:'pre'|'in'|'post'|'unavail', score, phase, src, stat:function(x), ts} */

  function espnHR(j, x) {
    var vals = [], want = String(x.name || '').toLowerCase();
    ((j.boxscore || {}).players || []).forEach(function (t) {
      (t.statistics || []).forEach(function (cat) {
        var keys = cat.keys || [];
        if (keys.indexOf('atBats') < 0) return;
        var hi = keys.indexOf('homeRuns'); if (hi < 0) hi = keys.indexOf('HR'); if (hi < 0) return;
        (cat.athletes || []).forEach(function (a) {
          if (String((a.athlete || {}).displayName || '').toLowerCase() !== want) return;
          var v = parseInt((a.stats || [])[hi], 10);
          if (!isNaN(v)) vals.push(v);
        });
      });
    });
    if (vals.length !== 1) return null; /* exact name, exactly one batting line */
    return vals[0];
  }
  function nameKey(n) { return String(n || '').toLowerCase().replace(/[.']/g, '').replace(/\s+(jr|sr|ii|iii|iv)$/, '').trim(); }
  function tdMissProven(j, x) {
    try {
      var comp = ((j.header || {}).competitions || [])[0] || {}, st = comp.status && comp.status.type;
      if (!st || st.state !== 'post' || st.completed !== true) return false;
      var sp = j.scoringPlays; if (!Array.isArray(sp) || !sp.length) return false;
      var hs = null, as = null;
      (comp.competitors || []).forEach(function (c) { if (c.homeAway === 'home') hs = Number(c.score); else if (c.homeAway === 'away') as = Number(c.score); });
      if (!isFinite(hs) || !isFinite(as)) return false;
      /* completeness: the scoring list must chain from 0-0 to the exact final score, every step a legal scoring increment */
      var ph = 0, pa = 0, tds = [];
      for (var i = 0; i < sp.length; i++) {
        var p = sp[i], h = Number(p.homeScore), a = Number(p.awayScore);
        if (!p.text || !isFinite(h) || !isFinite(a)) return false;
        var dh = h - ph, da = a - pa;
        if (dh < 0 || da < 0 || (dh > 0 && da > 0) || (dh === 0 && da === 0)) return false;
        var d = dh || da;
        if (d > 8 || d === 4 || d === 5) return false;
        if (d >= 6 || /touchdown/i.test(String((p.type || {}).text || ''))) tds.push(p);
        ph = h; pa = a;
      }
      if (ph !== hs || pa !== as) return false;
      var nm = nameKey(x.name || ''), sur = nm.split(' ').slice(-1)[0];
      if (!sur || sur.length < 3) return false;
      return !tds.some(function (p) { return nameKey(p.text).indexOf(sur) >= 0; });
    } catch (e) { return false; }
  }
  function espnStat(j, x) {
    var found = false, value = 0, keys = x.keys || [];
    var single = !x.anytime && keys.length <= 1;
    var sum = {}, ids = {};
    ((j.boxscore || {}).players || []).forEach(function (t) {
      (t.statistics || []).forEach(function (cat) {
        (cat.athletes || []).forEach(function (a) {
          if (x.athlete ? String((a.athlete || {}).id) !== String(x.athlete) : !(x.name && nameKey((a.athlete || {}).displayName) === nameKey(x.name))) return;
          var ck = cat.keys || [];
          ids[String((a.athlete || {}).id)] = 1;
          var want = x.anytime ? ['rushingTouchdowns', 'receivingTouchdowns', 'kickReturnTouchdowns', 'puntReturnTouchdowns', 'fumbleReturnTouchdowns'] : keys;
          want.forEach(function (k) {
            var ix = ck.indexOf(k);
            if (ix < 0 || !a.stats) return;
            var raw = String(a.stats[ix]).split('-')[0];
            if (raw === '' || !isFinite(Number(raw))) return;
            if (x.anytime || !(k in sum)) { sum[k] = Number(raw); }
          });
        });
      });
    });
    var ks = Object.keys(sum);
    if (!ks.length) return null;
    if (!x.athlete && Object.keys(ids).length !== 1) return null; /* name match must be a single athlete */
    if (x.anytime) { ks.forEach(function (k) { value += sum[k]; }); found = true; if (value < 1) return tdMissProven(j, x) ? 0 : null; /* a zero resolves only on a completed game whose full scoring-play list never names the player; otherwise unknown */ return value; }
    if (single) return sum[keys[0]];
    if (ks.length !== keys.length) return null;
    ks.forEach(function (k) { value += sum[k]; });
    return value;
  }
  function espnGoals(j, x) {
    var values = [];
    ((j.boxscore || {}).players || []).forEach(function (t) {
      (t.statistics || []).forEach(function (cat) {
        var ix = (cat.keys || []).indexOf('goals');
        if (ix < 0) return;
        (cat.athletes || []).forEach(function (a) {
          if (String((a.athlete || {}).id) !== String(x.athlete)) return;
          var v = (a.stats || [])[ix];
          if (v == null || String(v).trim() === '' || !/^[0-9]+$/.test(String(v))) return;
          values.push(Number(v));
        });
      });
    });
    if (!values.length || !values.every(function (v) { return v === values[0]; })) return null;
    return values[0];
  }

  /* Structured clock for the supplied renderer, only from fields the source actually returned. */
  function clkOfEspn(lg, st, j) {
    var ty = st.type || {}, nm = String(ty.name || ''), p = Number(st.period) || 0, dc = st.displayClock == null ? '' : String(st.displayClock);
    if (/DELAY|SUSPEND|POSTPONE/.test(nm)) return { state: 'delay' };
    if (lg === 'mlb') {
      var m = String(ty.shortDetail || ty.detail || '').match(/^(Top|Bot|Mid|End)\s+(?:of\s+the\s+)?(\d+)/i);
      if (!m) return null;
      var w = m[1].toLowerCase(), o = {};
      o.period = Number(m[2]);
      if (w === 'top' || w === 'bot') { o.half = w; var sit = (j && (j.situation || ((j.header || {}).competitions || [])[0] && ((j.header.competitions[0] || {}).situation))) || null; if (sit && typeof sit.outs === 'number') o.outs = sit.outs; }
      else { o.state = 'break'; o.half = w === 'mid' ? 'top' : 'bot'; }
      return o;
    }
    if (/HALFTIME/.test(nm)) return { period: p || 2, state: 'break' };
    if (/END_PERIOD|END_OF/.test(nm)) return p ? { period: p, state: 'break' } : null;
    if (!p) return null;
    var o2 = { period: p };
    if (lg === 'soc') { var mm = dc.match(/^(\d+(?:\+\d+)?)/); if (mm) o2.time = mm[1]; else return null; }
    else if (dc) o2.time = dc;
    return o2;
  }

  function gameFromEspn(j, x) {
    var hdr = j.header || {};
    if (String(hdr.id) !== String(x.event)) throw new Error('Wrong event');
    var comp = (hdr.competitions || [])[0] || {}, cs = comp.competitors || [], st = comp.status || {}, ty = st.type || {};
    if (x.away && x.home) {
      var okA = cs.some(function (c) { return c.homeAway === 'away' && normTeam((c.team || {}).abbreviation) === normTeam(x.away); });
      var okH = cs.some(function (c) { return c.homeAway === 'home' && normTeam((c.team || {}).abbreviation) === normTeam(x.home); });
      if (!okA || !okH) throw new Error('Wrong matchup');
    }
    var state = ty.state === 'pre' ? 'pre' : (ty.state === 'in' ? 'in' : (ty.completed === true && ty.state === 'post' ? 'post' : 'unavail'));
    var order = cs.slice().sort(function (a, b) { return a.homeAway === 'away' ? -1 : 1; });
    var score = order.map(function (c) { return ((c.team || {}).abbreviation || '') + ' ' + (c.score == null ? '?' : c.score); }).join(' \u2013 ');
    var lg = x.league || leagueOfUrl(x.espnUrl);
    return {
      state: state, score: score, phase: state === 'in' ? phaseOf(lg, st) : (state === 'post' ? 'Final' : ''), clk: state === 'in' ? clkOfEspn(lg, st, j) : null,
      src: 'ESPN', ts: Date.now(),
      stat: function (leg) {
        if (leg.hr) return espnHR(j, leg);
        if (leg.ml) {
          var me = cs.filter(function (c) { return (c.team || {}).displayName === leg.ml && (!leg.mlAbbr || (c.team || {}).abbreviation === leg.mlAbbr); })[0];
          if (!me) return null;
          if (state === 'post') return me.winner === true ? 1 : (me.winner === false ? 0 : null);
          return state === 'in' ? 0 : null;
        }
        if (leg.spreadTeam) {
          var sm = cs.filter(function (c) { return (c.team || {}).abbreviation === leg.spreadTeam; })[0], so = cs.filter(function (c) { return c !== sm; })[0];
          if (!sm || !so || typeof leg.spreadLine !== 'number') return null;
          if (state === 'post') { var a = Number(sm.score), b = Number(so.score); if (!isFinite(a) || !isFinite(b)) return null; return (a - b + leg.spreadLine) > 0 ? 1 : 0; }
          return state === 'in' ? 0 : null;
        }
        return leg.goals ? espnGoals(j, leg) : espnStat(j, leg);
      }
    };
  }
  function gameFromNhl(g, x) {
    if (String(g.id) !== String(x.nhlGame)) throw new Error('Wrong game');
    var s = g.gameState;
    var state;
    if (s === 'FUT' || s === 'PRE') state = 'pre';
    else if (s === 'LIVE' || s === 'CRIT') state = 'in';
    else if (s === 'OFF' || s === 'FINAL') state = 'post';
    else throw new Error('Unknown state');
    var a = g.awayTeam || {}, h = g.homeTeam || {};
    var per = (g.periodDescriptor || {}).number || 0;
    var rem = (g.clock || {}).timeRemaining || '';
    var phase = state === 'in' ? ((per <= 3 ? 'P' + per : (per === 4 ? 'OT' : 'SO')) + (per === 5 ? '' : (rem ? ' ' + rem : ''))) : (state === 'post' ? 'Final' : '');
    var ps = g.playerByGameStats || {}, players = [];
    Object.keys(ps).forEach(function (t) { var team = ps[t] || {}; Object.keys(team).forEach(function (k) { if (Array.isArray(team[k])) players = players.concat(team[k]); }); });
    return {
      state: state, score: (a.abbrev + ' ' + a.score) + ' \u2013 ' + (h.abbrev + ' ' + h.score), phase: phase, clk: state === 'in' && per ? ((g.clock || {}).inIntermission ? { period: per, state: 'break' } : (rem ? { period: per, time: rem } : null)) : null, src: 'NHL', ts: Date.now(),
      stat: function (leg) {
        var p = players.find(function (q) { return String(q.playerId) === String(leg.nhlPlayer); });
        return p && typeof p.goals === 'number' ? p.goals : null;
      }
    };
  }

  /* ---------- registry of mounted slips ---------- */
  var handles = [];

  function keyOf(x) { return x && x.nhlGame ? 'nhl:' + x.nhlGame : (x && x.event ? 'espn:' + x.event : ''); }

  /* A successful fetch is not a fresh clock by itself: providers return no update timestamp in the fields used, so freshness is our own fetch age. A live clock older than 2 minutes is dropped (score stays) until the next successful poll. */
  function fresh(g) { return g && g.ts && Date.now() - g.ts <= 120000; }
  var kquotes = null;
  function booksOf(spec) {
    if (!spec.kalTicker) return spec.books;
    var q = kquotes && kquotes.fresh ? kquotes.quotes[spec.kalTicker] : null, fin = q && q.status && q.status !== 'active', qok = false;
    if (q && q.status === 'active' && typeof q.yes_ask === 'number' && q.yes_ask >= 1 && q.yes_ask <= 99 && q.quoted_at) { var qa = Date.now() - Date.parse(q.quoted_at); qok = qa >= 0 && qa <= 21600000; }
    var kal = null, c = spec.kalCard;
    if (qok) kal = { name: 'KAL', odds: aml(q.yes_ask), url: c ? c.u : undefined };
    else if (fin) kal = { name: 'KAL', odds: 'Final' };
    else if (c && c.ctm && aml(c.c)) kal = { name: 'KAL', odds: aml(c.c) + ' \u00b7 ' + c.ctm, url: c.u };
    var out = (spec.books || []).filter(function (b) { return b.name !== 'KAL'; });
    if (kal && (kal.url || kal.odds === 'Final')) out.push(kal);
    return out;
  }
  function loadQuotes() {
    var any = handles.some(function (h) { return h.spec.kalTicker; });
    if (!any) return Promise.resolve();
    return fetchJ2('slates/nfl_kalshi_quotes.json').then(function (qj) {
      var age = Date.now() - Date.parse(qj.quoted_at);
      kquotes = { fresh: !!(qj && qj.quoted_at && age >= 0 && age <= 600000), quotes: (qj && qj.quotes) || {} };
    }, function () { kquotes = null; });
  }
  function derive(spec, now) {
    var legsOut = [], gset = {}, anyStarted = false, anyLive = false, anyUnavail = false, started = 0;
    var multi = (function () { var m = {}; spec.legs.forEach(function (l) { if (l.x && keyOf(l.x)) m[keyOf(l.x)] = 1; else if (l.matchup) m['m:' + l.matchup] = 1; }); return Object.keys(m).length > 1; })();
    spec.legs.forEach(function (l) {
      var o = { player: l.player, market: l.market, line: l.line, lineText: l.lineText, dir: l.dir, odds: l.odds, status: l.status || 'open' };
      var x = l.x;
      if (has(l.final)) o.final = l.final;
      if (has(l.finalText)) o.finalText = l.finalText;
      if (has(l.margin)) o.margin = l.margin;
      if (has(l.when)) o.when = l.when;
      if (x && keyOf(x) && !l.archived) {
        var k = keyOf(x), g = games[k], commence = Date.parse(x.commence);
        gset[k] = g || 1;
        var past = isFinite(commence) && now >= commence;
        if (g && g.state === 'pre') {
          o.status = 'open'; o.when = whenLabel(commence); if (isFinite(commence)) o.startsAt = isoOf(commence);
        } else if (g && (g.state === 'in' || g.state === 'post')) {
          anyStarted = true; started++; if (g.state === 'in') anyLive = true;
          var v = g.stat ? g.stat(x) : null;
          var tgt = has(l.line) ? Number(l.line) : null;
          if (v == null || tgt == null) {
            o.status = g.state === 'post' ? 'open' : 'live';
            o.when = g.state === 'post' ? 'Final \u00b7 stat unavailable' : 'Stat unavailable';
            if (g.state === 'in' && fresh(g) && g.clk) o.clock = g.clk;
            anyUnavail = true;
          } else {
            if (x.ml || x.spreadTeam) { if (g.state === 'post') o.finalText = v ? 'W' : 'L'; } else o.final = v;
            var under = l.dir === 'under';
            if (!under) o.status = v >= tgt ? 'hit' : (g.state === 'post' ? 'miss' : 'live');
            else o.status = v >= tgt ? 'miss' : (g.state === 'post' ? 'hit' : 'live');
            o.when = '';
          }
          if (g.state === 'in' && fresh(g) && g.clk && multi) o.clock = g.clk;
          if (multi && g.state === 'post') o.market = (l.market || '') + ' \u00b7 Final';
        } else {
          /* no confirmed state: pregame timer, or honest unavailable after a feed failure past start */
          if (g && g.state === 'unavail' && past) { o.status = 'open'; o.when = 'Live sources unavailable'; anyUnavail = true; }
          else if (isFinite(commence)) { o.status = 'open'; o.when = whenLabel(commence); o.startsAt = isoOf(commence); }
          else { o.status = 'open'; o.when = l.timeLabel || '\u2014'; }
        }
      }
      if (x && x.hr && !keyOf(x) && !l.archived) { o.status = 'open'; o.when = x.unres ? (l.timeLabel ? l.timeLabel + ' \u00b7 ' : '') + 'Live status unavailable' : (l.timeLabel || '\u2014'); }
      if (x && !keyOf(x) && !l.archived && !x.hr && !x.nflLive && isFinite(Date.parse(x.commence || ''))) { o.status = 'open'; o.when = whenLabel(Date.parse(x.commence)); o.startsAt = isoOf(Date.parse(x.commence)); }
      if (x && x.nflLive && !keyOf(x) && !l.archived) { o.status = 'open'; o.when = l.timeLabel || 'Start time unavailable'; }
      legsOut.push(o);
    });
    var gk = Object.keys(gset);
    var live = spec.status ? null : (anyLive ? 'live' : 'open');
    var t = {
      status: spec.status || live, sport: spec.sport, type: spec.type, title: spec.title,
      date: spec.date, source: spec.source, oddsLabel: spec.oddsLabel, total: spec.total, books: booksOf(spec), legs: legsOut
    };
    if (spec.sources && spec.sources.length) t.sources = spec.sources;
    if (has(spec.details)) t.details = spec.details;
    if (spec.game) t.game = spec.game;
    /* verified start of a single-game slip. Multi-game slips carry each leg's own startsAt instead (own countdown, then own source clock). Never invented: omitted when no verified start exists. */
    var starts = legsOut.map(function (o) { return o.startsAt ? Date.parse(o.startsAt) : NaN; }).filter(isFinite);
    spec.legs.forEach(function (l) { var k = l.x ? keyOf(l.x) : '', gg = k ? games[k] : null, c = l.x && !l.archived && !(gg && (gg.state === 'in' || gg.state === 'post')) ? Date.parse(l.x.commence || '') : NaN; if (isFinite(c)) starts.push(c); });
    if (starts.length && !multi && (t.status === 'open' || t.status === 'live') && !(gk.length === 1 && games[gk[0]] && games[gk[0]].state === 'in')) t.startsAt = isoOf(Math.min.apply(null, starts));
    var note = spec.note || '';
    if (note) t.note = note;
    if (!spec.status && gk.length === 1 && games[gk[0]] && (games[gk[0]].state === 'in' || games[gk[0]].state === 'post')) {
      var g1 = games[gk[0]];
      t.final = g1.score;
      if (g1.state === 'in' && fresh(g1) && g1.clk) t.clock = g1.clk;
      if (!t.game && spec.legs[0] && spec.legs[0].matchup) t.game = spec.legs[0].matchup;
    } else if (has(spec.final)) t.final = spec.final;
    return t;
  }

  function repaint(h, now) {
    var t = derive(h.spec, now == null ? Date.now() : now);
    var sig = JSON.stringify(t);
    if (sig === h.sig) return;
    h.sig = sig;
    window.RPSlip.mount(h.slipEl, [t]);
  }

  /* mount one cell per spec inside a .rp-slip-grid. Returns the handles. */
  function pageKey(grid) {
    if (!grid.closest) return '';
    var sec = grid.closest('[id^="st-"]');
    if ((sec && sec.id === 'st-home') || grid.closest('#rpHomeWin')) return 'home';
    return sec ? sec.id : '';
  }
  function ensurePanel(grid) {
    var key = pageKey(grid);
    if (!key) return;
    var pid = 'rpxVerify-' + key;
    if (document.getElementById(pid)) return;
    var scopes = key === 'home' ? [document.getElementById('st-home'), document.getElementById('rpHomeWin')] : [document.getElementById(key)];
    var cands = []; scopes.forEach(function (sc) { if (sc) cands = cands.concat(Array.prototype.slice.call(sc.querySelectorAll('details'))); });
    var ex = cands.filter( function (d) { var sm = d.querySelector('summary'); return sm && /how we verify/i.test(sm.textContent) && !d.classList.contains('rpx-verify'); })[0];
    if (ex) {
      if (!ex.querySelector('.rpx-verify-add')) { var ul = document.createElement('ul'); ul.className = 'rpx-verify-add'; ul.id = pid; ul.innerHTML = '<li>' + VERIFY_ITEMS.join('</li><li>') + '</li>'; ex.appendChild(ul); }
      return;
    }
    grid.insertAdjacentElement('afterend', verifyPanel(pid));
  }
  function mountSpecs(grid, specs) {
    var out = [];
    ensurePanel(grid);
    specs.forEach(function (spec) {
      var cell = document.createElement('div');
      cell.className = 'rpx-cell';
      var slipEl = document.createElement('div');
      cell.appendChild(slipEl);
      grid.appendChild(cell);
      var h = { spec: spec, slipEl: slipEl, cell: cell, sig: '' };
      handles.push(h); out.push(h);
      repaint(h);
    });
    return out;
  }

  /* ---------- live polling (only slips with trackable, not-yet-final games) ---------- */
  var polling = false;
  function liveKeys() {
    var m = {};
    handles.forEach(function (h) {
      if (h.spec.status) return;
      h.spec.legs.forEach(function (l) {
        if (l.archived || !l.x) return;
        var k = keyOf(l.x);
        if (k && !(games[k] && games[k].state === 'post')) m[k] = l.x;
      });
    });
    return m;
  }
  function fetchJson(u) {
    var ac = window.AbortController ? new AbortController() : null, to = ac ? setTimeout(function () { ac.abort(); }, 10000) : 0;
    return fetch(u, ac ? { cache: 'no-store', signal: ac.signal } : { cache: 'no-store' }).then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
      .then(function (j) { clearTimeout(to); return j; }, function (e) { clearTimeout(to); throw e; });
  }
  function pollOne(k, x) {
    var p;
    if (x.nhlGame) {
      p = fetchJson('https://api-web.nhle.com/v1/gamecenter/' + x.nhlGame + '/boxscore').then(function (g) { return gameFromNhl(g, x); })
        .catch(function () { return x.espnUrl ? fetchJson(x.espnUrl).then(function (j) { return gameFromEspn(j, x); }) : Promise.reject(); });
    } else if (x.espnUrl) {
      p = fetchJson(x.espnUrl).then(function (j) { return gameFromEspn(j, x); });
    } else p = Promise.reject();
    /* ESPN summary headers carry no period/clock on some games (observed on a final NHL game); for a live game with no clock, the league scoreboard status is the source. Missing there too = no clock shown. */
    p = p.then(function (rec) {
      if (rec.state !== 'in' || rec.clk || rec.src !== 'ESPN' || !x.espnUrl || !/\/summary\?event=/.test(x.espnUrl)) return rec;
      return fetchJson(x.espnUrl.replace(/\/summary\?event=.*$/, '/scoreboard')).then(function (sb) {
        var ev = (sb.events || []).filter(function (e) { return String(e.id) === String(x.event); })[0];
        var cmp = ev && (ev.competitions || [])[0];
        var st = ev && ev.status;
        if (st) { var lg = x.league || leagueOfUrl(x.espnUrl); rec.clk = clkOfEspn(lg, st, cmp ? { situation: cmp.situation } : null); }
        return rec;
      }, function () { return rec; });
    });
    return p.then(function (rec) { games[k] = rec; }, function () { games[k] = { state: 'unavail', ts: Date.now() }; });
  }
  var MLB_ALIAS = { CWS: 'CHW', CHW: 'CWS' };
  function resolveMlb() {
    var need = [];
    handles.forEach(function (h) { h.spec.legs.forEach(function (l) { if (l.x && l.x.hr && !l.x.event && !l.x.resolved) need.push(l.x); }); });
    if (!need.length) return Promise.resolve();
    return fetchJson('https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard').then(function (sb) {
      var evs = (sb.events || []).map(function (ev) {
        var cmp = (ev.competitions || [])[0] || {}, o = { id: ev.id, date: ev.date };
        (cmp.competitors || []).forEach(function (c) { o[c.homeAway] = String((c.team || {}).abbreviation || '').toUpperCase(); });
        return o;
      });
      need.forEach(function (x) {
        var m = evs.filter(function (e) { return (e.away === x.mlbAway || e.away === MLB_ALIAS[x.mlbAway]) && (e.home === x.mlbHome || e.home === MLB_ALIAS[x.mlbHome]); });
        if (m.length === 1) { x.event = m[0].id; x.espnUrl = 'https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/summary?event=' + m[0].id; x.commence = m[0].date; x.away = m[0].away; x.home = m[0].home; x.resolved = 1; }
        else x.unres = true; /* none or ambiguous (doubleheader): fail closed */
      });
    }, function () { need.forEach(function (x) { x.unres = true; }); });
  }
  function poll() {
    if (polling) return;
    polling = true;
    Promise.all([resolveMlb(), resolveNfl(), loadQuotes()]).then(pollAll, function () { pollAll(); });
  }
  function pollAll() {
    var ks = liveKeys(), names = Object.keys(ks);
    if (!names.length) { polling = false; handles.forEach(function (h) { if (!h.spec.status) repaint(h, Date.now()); }); return; }
    Promise.all(names.map(function (k) { return pollOne(k, ks[k]); })).then(function () {
      polling = false;
      var now = Date.now();
      handles.forEach(function (h) { if (!h.spec.status) repaint(h, now); });
    }, function () { polling = false; });
  }
  function visible(h) { return h.cell && h.cell.isConnected && h.cell.offsetParent !== null; }
  /* Fresh source data: remount every 30s while a game is live or within 3 min of its verified start (public ESPN/NHL feeds), otherwise every 60s. */
  var lastPoll = 0;
  function nearLive() {
    var now = Date.now();
    return handles.some(function (h) {
      return !h.spec.status && h.spec.legs.some(function (l) {
        var k = l.x ? keyOf(l.x) : '', g = k ? games[k] : null, c = l.x ? Date.parse(l.x.commence || '') : NaN;
        return (g && g.state === 'in') || (isFinite(c) && now >= c - 180000 && !(g && g.state === 'post'));
      });
    });
  }
  setInterval(function () {
    if (document.hidden) return;
    var age = Date.now() - lastPoll;
    if (age >= 60000 || (age >= 30000 && nearLive())) { lastPoll = Date.now(); poll(); }
    else if (nearLive()) { var nw = Date.now(); handles.forEach(function (h) { if (!h.spec.status) repaint(h, nw); }); }
  }, 5000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) poll(); });

  /* ---------- mappers ---------- */
  var SLBL = { nfl: 'NFL', nba: 'NBA', ncaaf: 'NCAAF', ncaab: 'NCAAB', mlb: 'MLB', nhl: 'NHL', wnba: 'WNBA', soc: 'SOCCER', multi: 'MULTI', other: 'OTHER' };
  var MONEY = /\$\s?\d/;
  function pub(s) {
    s = String(s == null ? '' : s);
    if (MONEY.test(s)) s = s.split(' - ').filter(function (p) { return !MONEY.test(p); }).join(' - ');
    return s.replace(/\bbankroll\s+builder\b/gi, 'Combo').replace(/\s*\bbankroll\b\s*/gi, ' ').replace(/\s{2,}/g, ' ').trim();
  }
  /* Generic grading disclaimers live once per page in the verification panel; the slip note keeps only the real reason. The full original text stays in Sources & details. */
  function stripDisc(s) {
    return String(s || '').replace(/(?:^|\s)(?:This is ticket )?[Ss]election grading[^.]*\.?/g, ' ').replace(/\s{2,}/g, ' ').replace(/^[\s\-\u2013\u00b7]+|[\s\-\u2013\u00b7]+$/g, '').trim();
  }
  function parseMarket(mk) {
    mk = String(mk || '');
    var m = mk.match(/^(\d+(?:\.\d+)?)\+\s*(.*)$/);
    if (m) return { line: Number(m[1]), lineText: m[1] + '+', market: m[2] || mk };
    m = mk.match(/^(over|under|o|u)\s*(\d+(?:\.\d+)?)\s*(.*)$/i);
    if (m) { var u = /^u/i.test(m[1]); return { line: Number(m[2]), lineText: (u ? 'U ' : 'o') + m[2], dir: u ? 'under' : 'over', market: m[3] || mk }; }
    if (/^(moneyline|ml)$/i.test(mk)) return { lineText: 'ML', market: 'Moneyline' };
    return { market: mk, lineText: '\u2014' };
  }

  /* History / archived entries */
  function hDay(e) {
    var d = String(e.date || e.original_date || '');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) d = String(e.archived_at || '').slice(0, 10);
    return /^\d{4}-\d{2}-\d{2}$/.test(d) ? d : '';
  }
  function hDayShort(d) {
    if (!d) return 'Earlier';
    var p = d.split('-');
    return new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])).toLocaleDateString('en-US', { timeZone: 'UTC', weekday: 'short', month: 'short', day: 'numeric' }).replace(',', '');
  }
  function hSport(e) {
    var lg = {}, n = 0, k;
    (e.legs || []).forEach(function (l) {
      k = String(l.league || '').toLowerCase(); if (k === 'cfb') k = 'ncaaf';
      if (!k) k = leagueOfUrl(l.game_source_url);
      if (k && !lg[k]) { lg[k] = 1; n++; }
    });
    if (n > 1) return 'multi';
    if (n === 1) return Object.keys(lg)[0];
    (e.source_urls || []).forEach(function (u) { k = leagueOfUrl(u); if (k && !lg[k]) { lg[k] = 1; n++; } });
    if (n > 1) return 'multi';
    if (n === 1) return Object.keys(lg)[0];
    var t = String(e.title || '').toLowerCase();
    if (/^multisport/.test(t)) return 'multi';
    var m = t.match(/^(nfl|nba|ncaaf|nhl|mlb|wnba|soccer)\b/);
    if (m) return m[1] === 'soccer' ? 'soc' : m[1];
    var p = String(e.provenance || '').toLowerCase();
    if (/dingers|home run|mlb|baseball/.test(p) || /home run/.test(t)) return 'mlb';
    if (/wnba/.test(p)) return 'wnba'; if (/nba/.test(p)) return 'nba'; if (/nfl|football/.test(p)) return 'nfl';
    if (/nhl|hockey/.test(p)) return 'nhl'; if (/soccer/.test(p)) return 'soc';
    if (/touchdown|\btd\b/i.test(t)) return 'nfl';
    return 'other';
  }
  function hPlaced(e) {
    var st = String(e.status || '');
    if (e.origin === 'bought') return (/reported/i.test(st) || e.placement_reported === true) ? 'Bought' : 'Legacy bought';
    var blob = st + ' ' + String(e.title || '') + ' ' + String(e.detail || '') + ' ' + String(e.placement_note || '') + ' ' + String(e.reason || '');
    if (/\bnot placed\b/i.test(blob)) return 'Not placed';
    if (e.placement_reported === true || /\bplaced\s*-\s*reported\b/i.test(blob) || /\breported[-\s]placed\b/i.test(blob) || /reported|placed/i.test(String(e.origin || ''))) return 'Placed';
    return 'Placement unknown';
  }
  function hTitle(e) {
    var t = String(e.title || 'Archived pick');
    var m = t.match(/^(NFL|NBA|NCAAF|MLB|NHL|WNBA|MULTISPORT|SOCCER)\s+-\s+/);
    if (m) t = t.slice(m[0].length);
    var total = '';
    var i = t.indexOf(' | ');
    if (i > -1) {
      var r = t.slice(i + 3).trim(); t = t.slice(0, i).trim();
      var om = r.match(/^((?:approx\s*)?[+\u2212-]\d+)/i);
      if (om) total = om[1].replace(/^approx\s*/i, 'approx ');
    }
    var short = t.replace(/^\d+-leg\s+/i, '').replace(/\s+parlay$/i, '').trim();
    return { title: (short || 'PARLAY').toUpperCase(), total: total };
  }
  function mapHistory(e) {
    var res = String(e.result || '').toLowerCase();
    var status = (res === 'won' || res === 'lost' || res === 'void') ? res : 'void';
    var legs = e.legs || [], sp = hSport(e), derivedLeg = false;
    if (!legs.length) {
      /* Legless archive rows: recover the single named selection from the entry's own title / original_pick. */
      var op = e.original_pick || null, tm = String(e.title || '').match(/^(.+?) - (.+)$/);
      var dm = String(e.detail || '').match(/^([A-Z]{2,4}) (?:at|AT|@) ([A-Z]{2,4})/);
      var pl = op && op.player ? op.player : (tm ? tm[1] : ''), mk = op && op.market ? op.market : (tm ? tm[2] : '');
      var mt = op && op.matchup ? op.matchup : (dm ? dm[1] + ' @ ' + dm[2] : '');
      if (pl && mk) { legs = [{ player: pl, market: mk, matchup: mt, status: (String(e.result || '').toLowerCase() === 'won' ? 'won' : (String(e.result || '').toLowerCase() === 'lost' ? 'lost' : (String(e.result || '').toLowerCase() === 'void' ? 'void' : ''))) }]; derivedLeg = true; }
    }
    var mu = {}; legs.forEach(function (l) { if (l.matchup) mu[l.matchup] = 1; });
    var ms = Object.keys(mu), multi = ms.length > 1;
    var tt = hTitle(e), d = hDay(e);
    var anyKal = legs.some(function (l) { return has(l.kalshi_american); });
    var spec = {
      status: status, sport: SLBL[sp] || 'OTHER',
      type: legs.length ? (legs.length > 1 ? legs.length + '-leg parlay' : 'Straight') : 'Archived',
      title: tt.title, date: hDayShort(d), source: hPlaced(e) + ' \u00b7 ' + (e.author || 'Wooder Ice'),
      legs: [], sources: [], record: []
    };
    if (tt.total) spec.total = tt.total;
    if (anyKal) spec.oddsLabel = 'KAL ref';
    if (ms.length === 1) spec.game = ms[0];
    var fs = legs.map(function (l) { return l.final_score; }).filter(has);
    if (ms.length === 1 && fs.length) spec.final = String(fs[0]);
    var noteRaw = pub(e.reason || ''), note = stripDisc(noteRaw);
    if (!note && !noteRaw && !legs.length && !derivedLeg) { noteRaw = pub(e.detail || ''); note = stripDisc(noteRaw); }
    if (noteRaw && note !== noteRaw) spec.record.push('Original note: ' + noteRaw);
    if (!note && status === 'void' && res && res !== 'void') note = 'Archived \u00b7 result: ' + String(e.result).toUpperCase();
    if (note) spec.note = note;
    legs.forEach(function (l) {
      var pm = parseMarket(l.market);
      var ls = String(l.status || '').toLowerCase();
      var o = { player: l.player, market: pm.market, line: pm.line, lineText: pm.lineText, dir: pm.dir, archived: true,
        status: ls === 'won' ? 'hit' : (ls === 'lost' ? 'miss' : (ls === 'void' ? 'void' : 'open')) };
      if (has(l.kalshi_american)) o.odds = String(l.kalshi_american); else if (has(l.odds)) o.odds = String(l.odds);
      var fv = l.final_stat;
      if (has(fv) && /^\d+(?:\.\d+)?$/.test(String(fv))) o.final = Number(fv);
      else if (pm.lineText === 'ML' && (o.status === 'hit' || o.status === 'miss')) o.finalText = o.status === 'hit' ? 'W' : 'L';
      if (o.final == null && (o.status === 'hit' || o.status === 'miss')) {
        /* final stat grounded only in the entry's own pick-level reason naming this exact player */
        var rs = String(e.reason || ''), pn = String(l.player || ''), m1 = rs.match(/^(.+?) finished with (\d+(?:\.\d+)?) (?:receiving|rushing|passing) yards/), m2 = rs.match(/^(.+?) (?:had no qualifying touchdown|had 0 qualifying touchdowns)/);
        if (m1 && m1[1] === pn && /yards/i.test(l.market || '')) o.final = Number(m1[2]);
        else if (m2 && m2[1] === pn && /touchdown|\bTD\b/i.test(l.market || '')) o.final = 0;
      }
      if (multi && l.matchup) o.market = (o.market || '') + ' \u00b7 ' + l.matchup;
      spec.legs.push(o);
    });
    if (derivedLeg && pub(e.detail || '')) spec.record.push(pub(e.detail));
    if (pub(e.placement_note || '')) spec.record.push(pub(e.placement_note));
    var rm = e.removed_label || e.archived_at; if (rm) spec.record.push('Removed ' + rm);
    if (pub(e.provenance || '')) spec.record.push('Source: ' + pub(e.provenance));
    var lt = legs.map(function (l) { return l.time ? (String(l.player || '') + (l.market ? ' ' + String(l.market) : '') + ' - ' + String(l.time).replace(/^(today|tonight|tomorrow)\s+/i, '')) : ''; }).filter(function (s) { return s; });
    if (lt.length) spec.record.push('Original leg times (PT, as archived): ' + lt.join(' \u00b7 '));
    var seen = {};
    (e.source_urls || []).forEach(function (u) { u = String(u || ''); if (u.indexOf('https://') === 0 && !seen[u]) { seen[u] = 1; spec.sources.push({ label: /espn/i.test(u) ? 'ESPN' : (/kalshi/i.test(u) ? 'Kalshi' : 'Source'), url: u }); } });
    if (spec.record.length) spec.details = spec.record.join('\n');
    return { spec: spec, sport: sp, result: status === 'void' && res !== 'void' ? 'other' : status, placed: hPlaced(e), day: d };
  }

  /* Recent winners (data is already slip-shaped) */
  function mapWinner(w) {
    var legs = w.legs || [];
    var spec = {
      status: 'won', sport: w.sport || String(w.title || '').split(' - ')[0] || 'NFL',
      type: legs.length + '-leg parlay', title: w.short_title || w.title, date: w.game_date || '',
      source: /placed/i.test(w.status || '') ? 'Placed \u00b7 Wooder Ice' : 'Wooder Ice', oddsLabel: 'KAL ref',
      legs: [], sources: [], record: []
    };
    if (w.game_label && !/^\d+ games?$/.test(w.game_label)) spec.game = w.game_label;
    if (w.final_strip) spec.final = w.final_strip;
    legs.forEach(function (l) {
      var o = { player: l.name || l.player, market: l.mkt || l.market, archived: true, status: 'hit' };
      if (l.line === 'ML') { o.lineText = 'ML'; o.finalText = l.final; o.margin = l.diff; o.market = (l.mkt || l.market) + ' \u00b7 ' + l.matchup + (l.score ? ' \u00b7 ' + l.score : ''); }
      else { o.line = l.line_n; o.lineText = l.line; o.final = l.final_n; }
      if (has(l.kal_ref)) o.odds = String(l.kal_ref).replace('\u2212', '-');
      spec.legs.push(o);
      if (l.kalshi_source_url) spec.sources.push({ label: 'Kalshi market', url: l.kalshi_source_url });
      if (l.espn_source_url) spec.sources.push({ label: 'ESPN final', url: l.espn_source_url });
    });
    var seen = {}; spec.sources = spec.sources.filter(function (s) { if (seen[s.url]) return false; seen[s.url] = 1; return true; });
    if (w.note) spec.details = w.note;
    return spec;
  }

  /* ---------- DOM helpers ---------- */
  function makeGrid(after, id) {
    var g = document.getElementById(id);
    if (g) return g;
    g = document.createElement('div');
    g.className = 'rp-slip-grid';
    g.id = id;
    after.insertAdjacentElement('afterend', g);
    return g;
  }
  function onReady(fn) { if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn); else fn(); }
  function hideOld(el) { if (el) el.setAttribute('data-rpx-old', '1'); }

  var css = document.createElement('style');
  css.textContent = '[data-rpx-old]{display:none!important}' +
    '.rpx-cell{min-width:0}' +
    '#st-wooder .wi-future .progress,#st-wooder .wi-future .price{font-variant-numeric:tabular-nums}' +
    '.rpx-verify{margin:16px 0 0;border:1px solid #1d2426;border-radius:14px;background:#0f1516;color:#f2f5f4;font-family:Inter,system-ui,sans-serif}' +
    '.rpx-verify summary{cursor:pointer;padding:14px 18px;font-weight:800;font-size:15px}' +
    '.rpx-verify ul{margin:0;padding:0 18px 14px 36px;color:#a7b4b1;font-size:13px;line-height:1.55}' +
    '.rpx-head{margin:8px 0 12px;font:800 13px/1 Inter,system-ui,sans-serif;letter-spacing:.12em;text-transform:uppercase;color:#a7b4b1}';
  document.head.appendChild(css);

  var VERIFY_ITEMS = [
    '<strong>Not placed</strong> means no wager was reported on the ticket. <strong>Placed</strong> means Wooder Ice reported placing it; stake, fill and settlement are not independently verified.',
    'Leg prices are reference snapshots (Kalshi YES asks or screenshot multipliers), not fills or executable quotes. Combined parlay odds are left out unless a native quote exists.',
    'Leg progress comes from official game feeds (NHL where available, otherwise ESPN). It tracks the selection only: results grade the selection, not placement, fill, payout or settlement, and are not a Kalshi settlement claim.',
    'Pregame countdowns run to each game\u2019s verified start time. At zero a slip says Starting until the game feed confirms the game is underway; then it shows the feed\u2019s own clock and period. If a feed is unavailable the slip says so and infers nothing.'
  ];
  function verifyPanel(id) {
    var d = document.createElement('details');
    d.className = 'rpx-verify'; d.id = id;
    d.innerHTML = '<summary>How we verify</summary><ul><li>' + VERIFY_ITEMS.join('</li><li>') + '</li></ul>';
    return d;
  }

  /* ---------- surface: History (mirrors the existing filters/paging/date headings) ---------- */
  function surfaceHistory() {
    var box = document.getElementById('rpPastBox');
    if (!box) return;
    var grid = null, started = false;
    function build() {
      if (started || !box.children.length) return;
      started = true;
      window.fetch('slates/past_tickets.json?cb=' + Date.now(), { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (j) {
        var all = ((j && j.entries) || []).slice().sort(function (a, b) { var x = hDay(a), y = hDay(b); return x < y ? 1 : (x > y ? -1 : 0); });
        var olds = Array.prototype.slice.call(box.children);
        var tks = olds.filter(function (el) { return el.classList.contains('hp-tk'); });
        if (tks.length !== all.length) { started = false; return; }
        hideOld(box);
        grid = makeGrid(box, 'rpxPastGrid');
        grid.innerHTML = '';
        var map = [], ti = 0, hs = [];
        olds.forEach(function (el) {
          if (el.classList.contains('hp-date')) {
            var h3 = el.cloneNode(true); h3.style.gridColumn = '1 / -1'; grid.appendChild(h3); map.push([el, h3]);
          } else if (el.classList.contains('hp-tk')) {
            var m = mapHistory(all[ti++]);
            var created = mountSpecs(grid, [m.spec])[0];
            map.push([el, created.cell]);
          }
        });
        function sync() { map.forEach(function (p) { p[1].hidden = p[0].hidden; }); }
        sync();
        new MutationObserver(sync).observe(box, { attributes: true, attributeFilter: ['hidden'], subtree: true });
      }).catch(function () { started = false; });
    }
    new MutationObserver(build).observe(box, { childList: true });
    build();
  }

  /* ---------- surface: Recent winners on Home and Wooder ---------- */
  function surfaceWinners() {
    var homeOld = document.getElementById('rpHomeWinGrid');
    var wooOld = document.getElementById('rpWinBox');
    if (!homeOld && !wooOld) return;
    window.fetch('slates/recent_winners.json?cb=' + Date.now(), { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (j) {
      var specs = ((j && j.winners) || []).map(mapWinner);
      if (!specs.length) return;
      if (homeOld) { hideOld(homeOld); mountSpecs(makeGrid(homeOld, 'rpxHomeWin'), specs); }
      if (wooOld) {
        hideOld(wooOld);
        mountSpecs(makeGrid(wooOld, 'rpxWooWin'), specs);
        var wrap = document.getElementById('rpWinWrap'); if (wrap) wrap.style.display = '';
      }
    }).catch(function () { });
  }

  /* ---------- surfaces: Wooder tickets, Dingers, combos (populated only on their active day; active-day.js filters stale items) ---------- */
  var TKMAP = {
    nfl: { 'receptions': ['receptions'], 'receiving yards': ['receivingYards'], 'rushing yards': ['rushingYards'], 'passing yards': ['passingYards'], 'rushing + receiving yards': ['rushingYards', 'receivingYards'] },
    mlb: { 'hits': ['hits'], 'home runs': ['homeRuns'], 'home run': ['homeRuns'], 'strikeouts': ['strikeouts'] },
    nba: { 'made threes': ['threePointFieldGoalsMade-threePointFieldGoalsAttempted'], 'points': ['points'], 'rebounds': ['rebounds'], 'assists': ['assists'] }
  };
  function tkLeg(l, fallbackLeague) {
    var lg = String(l.league || fallbackLeague || '').toLowerCase();
    var mk = String(l.market || ''), m = mk.match(/^(\d+(?:\.\d+)?)\+\s*(.*)$/);
    var o = { player: l.player, market: (m ? m[2] : mk) + (l.matchup ? ' \u00b7 ' + l.matchup : ''), matchup: l.matchup, timeLabel: l.time };
    if (has(l.kalshi_american)) o.odds = String(l.kalshi_american);
    var parts = String(l.matchup || '').split(' @ ');
    var x = { commence: l.commence, league: lg, event: l.event_id, espnUrl: l.game_source_url, away: parts[1] ? parts[0] : '', home: parts[1] || '', name: l.player };
    if (/^anytime td$/i.test(mk)) { o.line = 1; o.lineText = '1+'; o.market = 'Anytime TD \u00b7 ' + (l.matchup || ''); x.anytime = true; }
    else if (/^moneyline$/i.test(mk)) { o.lineText = 'ML'; o.line = 1; x.ml = String(l.player || ''); }
    else if (m) {
      var k = (TKMAP[lg] || {})[m[2].toLowerCase()];
      o.line = Number(m[1]); o.lineText = m[1] + '+';
      if (k) x.keys = k;
    }
    if (String(l.side || '').toLowerCase() === 'no') { o.dir = 'under'; if (has(o.line)) o.lineText = 'U ' + o.line; }
    if (x.ml) { if (typeof l.ml_display === 'string' && l.ml_display) x.ml = l.ml_display; if (typeof l.ml_abbr === 'string' && l.ml_abbr) x.mlAbbr = l.ml_abbr; }
    o.x = x;
    return o;
  }
  function mapTicket(t) {
    var legs = t.legs || [], lg0 = (legs[0] || {}).league || '';
    var sp = String(t.title || '').split(' - ')[0] || String(lg0).toUpperCase();
    var title = String(t.title || '').replace(/^[A-Za-z/]+\s+-\s+/, '');
    var placed = t.bought === true || /^PLACED/i.test(String(t.status || '')) ? 'Placed' : (/^NOT PLACED/i.test(String(t.status || '')) ? 'Not placed' : 'Placement unknown');
    var spec = { sport: sp, type: legs.length > 1 ? legs.length + '-leg parlay' : 'Straight', title: title, date: t.date ? hDayShort(t.date) : '',
      source: placed + ' \u00b7 ' + (t.author || 'Wooder Ice'), oddsLabel: 'KAL ref', legs: legs.map(function (l) { return tkLeg(l); }), sources: [], record: [] };
    var seen = {};
    legs.forEach(function (l) {
      if (l.kalshi_source_url && !seen[l.kalshi_source_url]) { seen[l.kalshi_source_url] = 1; spec.sources.push({ label: l.player + ' Kalshi market', url: l.kalshi_source_url }); }
      if (l.game_source_url && !seen[l.game_source_url]) { seen[l.game_source_url] = 1; spec.sources.push({ label: (l.matchup || 'Game') + ' ESPN', url: l.game_source_url }); }
    });
    if (has(t.combo_american)) spec.total = String(t.combo_american);
    if (t.source_url && !seen[t.source_url]) { seen[t.source_url] = 1; spec.sources.push({ label: 'Kalshi combo market', url: String(t.source_url) }); }
    if (pub(t.placement_note || '')) spec.record.push(pub(t.placement_note));
    legs.forEach(function (l) { if (pub(l.note || '')) spec.record.push(l.player + ' \u00b7 ' + l.market + ': ' + pub(l.note)); });
    if (spec.record.length) spec.details = spec.record.join('\n');
    return spec;
  }
  function mapDinger(p, date) {
    var parts = String(p.matchup || '').toUpperCase().split(/ AT | @ /);
    var ptd = String(p.time || '');
    return { sport: 'MLB', type: 'Straight', title: 'HOME RUN', date: date ? hDayShort(date) : '', source: 'Not placed \u00b7 Wooder Ice',
      legs: [{ player: p.player, market: 'Home Run \u00b7 ' + p.matchup, matchup: p.matchup, timeLabel: ptd, line: 1, lineText: '1+',
        x: { league: 'mlb', name: p.player, hr: true, mlbAway: parts[0] || '', mlbHome: parts[1] || '' } }] };
  }
  function mapCombo(c) {
    var spec = { sport: c.league || String(c.sport || '').toUpperCase(), type: (c.legs || []).length + '-leg idea', title: String(c.title || '').toUpperCase(), date: c.time || '',
      source: 'Not placed \u00b7 Wooder Ice', oddsLabel: 'DK / KAL ref', game: c.matchup || undefined, record: [] };
    spec.legs = (c.legs || []).map(function (l) {
      var m = String(l.market || '').match(/^(\d+(?:\.\d+)?)\+\s*(.*)$/);
      var o = { player: l.player, market: m ? m[2] : l.market, line: m ? Number(m[1]) : undefined, lineText: m ? m[1] + '+' : undefined };
      var od = has(l.dk) ? l.dk : l.kalshi; if (has(od)) o.odds = String(od);
      o.when = l.kalshi_note || l.tag || '';
      return o;
    });
    [c.estimate, c.estimate_note, c.prices_note].forEach(function (s) { if (pub(s || '')) spec.record.push(pub(s)); });
    if (spec.record.length) spec.details = spec.record.join('\n');
    return spec;
  }
  function fetchJ(u) { return window.fetch(u + '?cb=' + Date.now(), { cache: 'no-store' }).then(function (r) { if (!r.ok) throw 0; return r.json(); }); }
  function surfaceWooder() {
    var tab = document.getElementById('st-wooder');
    if (!tab) return;
    function put(id, specs, anchor, cls) {
      if (!specs.length || !anchor) return;
      hideOld(anchor);
      var g = makeGrid(anchor, id); mountSpecs(g, specs);
    }
    fetchJ('slates/wooder_tickets.json').then(function (j) {
      var T = (j && j.tickets) || []; if (!T.length) return;
      var old = document.getElementById('rpTix'); put('rpxWooTix', T.map(mapTicket), old && (old.closest('section') || old.parentNode));
      poll();
    }).catch(function () { });
    fetchJ('slates/wooder_dingers.json').then(function (j) {
      var P = (j && j.picks) || []; if (!P.length || j.date !== ptDay()) return;
      var old = document.getElementById('rpDing'); put('rpxWooDing', P.map(function (p) { return mapDinger(p, j.date); }), old);
    }).catch(function () { });
    fetchJ('slates/wooder_combos.json').then(function (j) {
      var C = ((j && j.combos) || []).filter(function (c) { return !(c && c.futures === true); }); if (!C.length) return;
      var old = document.getElementById('rpCmb'); put('rpxWooCmb', C.map(mapCombo), old);
    }).catch(function () { });
  }

  /* ---------- surface: NFL official picks (slates/nfl_latest.json + nfl_chips.json; live binding from slates/nfl_live.json) ---------- */
  function okUrl(u) { return (typeof u === 'string' && /^https:\/\/([a-z0-9-]+\.)*(draftkings\.com|kalshi\.com)(\/[A-Za-z0-9\-._~:/?&=%,+@!$()*;]*)?$/i.test(u)) ? u : null; }
  function aml(c) { var q = c / 100; if (!(q > 0 && q < 1)) return ''; return q >= 0.5 ? String(Math.round(-100 * q / (1 - q))) : '+' + String(Math.round(100 * (1 - q) / q)); }
  function legPx(o) {
    var hasA = (o.odds !== undefined && o.odds !== null && String(o.odds) !== '');
    var hasC = (typeof o.price_c === 'number' && o.price_c >= 1 && o.price_c <= 99 && o.price_type === 'contract_cents');
    if (hasA === hasC) return null;
    return hasC ? { label: 'DKP', head: aml(o.price_c) } : { label: 'DK', head: String(o.odds) };
  }
  function nflLeg(l, px) {
    var o = { player: l.player, market: 'Anytime TD' + (l.matchup ? ' \u00b7 ' + l.matchup : ''), matchup: l.matchup, line: 1, lineText: '1+', odds: px.head,
      x: { league: 'nfl', name: l.player, nflTeam: l.team || '', nflLive: true, anytime: true } };
    return o;
  }
  function mapNfl(j, chips) {
    var out = [], singles = ((j.dk || {}).singles) || [], parlays = ((j.dk || {}).parlays) || [], kal = j.kalshi || {}, top = kal.top10 || [], bb = kal.bankroll_builder;
    var WM = { 'sun-early': 'Early', 'sun-afternoon': 'Afternoon', 'sun-night': 'Night', 'mon-night': 'Monday night', 'thu-night': 'Thursday night' };
    var ctm = j.generated_at ? new Date(j.generated_at).toLocaleString('en-US', { timeZone: 'America/Los_Angeles', hour: 'numeric', minute: '2-digit' }).toLowerCase().replace(/\s/g, '') : '';
    var win = WM[j.window] || '';
    var dl = j.generated_at ? hDayShort(ptDay(Date.parse(j.generated_at))) : '';
    var details = (j.window_label ? j.window_label + '\n' : '') + (j.generated_at ? 'Posted ' + j.generated_at : '');
    singles.forEach(function (s) {
      var px = legPx(s); if (!px) return;
      var books = [], dk = okUrl(s.link);
      if (dk) books.push({ name: px.label, odds: px.head, url: dk });
      var kc = chips[((s.player || '') + '|' + (s.team || '')).toLowerCase()], kl = top.filter(function (t) { return String(t.player || '').toLowerCase() === String(s.player || '').toLowerCase() && (t.matchup || '') === (s.matchup || ''); })[0];
      var ka = kc && typeof kc.ask_c === 'number' ? { c: kc.ask_c, u: okUrl(kc.url) } : (kl ? { c: kl.price_c, u: okUrl(kl.link) } : null);
      if (ka && ka.u && ctm && aml(ka.c)) books.push({ name: 'KAL', odds: aml(ka.c) + ' \u00b7 ' + ctm, url: ka.u });
      var kT = kc && kc.ticker ? kc.ticker : null;
      out.push({ sport: 'NFL', type: 'Straight', title: 'ANYTIME TD SCORER', date: dl, source: 'Not placed \u00b7 RixPicks', oddsLabel: px.label + ' ref',
        books: books, kalTicker: kT, kalCard: ka && ka.u ? { c: ka.c, u: ka.u, ctm: ctm } : null, legs: [nflLeg(s, px)], details: details + (win ? '\n' + win + ' slate' : '') });
    });
    parlays.forEach(function (p) {
      var bad = false, legs = (p.legs || []).map(function (l) { var lp = legPx(l); if (!lp) { bad = true; return null; } return nflLeg(l, lp); });
      if (bad) return;
      var co = p.combined_odds, cc = p.combined_price_c, hasCO = (co !== undefined && co !== null && String(co) !== ''), hasCC = (typeof cc === 'number' && cc >= 1 && cc <= 99 && p.price_type === 'contract_cents');
      if (hasCO === hasCC) return;
      var head = hasCC ? aml(cc) : String(co), u = okUrl(p.link);
      out.push({ sport: 'NFL', type: legs.length + '-leg parlay', title: 'ANYTIME TD PARLAY', date: dl, source: 'Not placed \u00b7 RixPicks', oddsLabel: 'DK ref',
        total: head, books: u ? [{ name: hasCC ? 'DKP' : 'DK', odds: head, url: u }] : [], legs: legs, details: details + (p.est_payout ? '\nEst. payout ' + p.est_payout : '') });
    });
    top.forEach(function (t) {
      var u = okUrl(t.link), a = aml(t.price_c); if (!a) return;
      out.push({ sport: 'NFL', type: 'Kalshi pick', title: 'ANYTIME TD SCORER', date: dl, source: 'Not placed \u00b7 RixPicks', oddsLabel: 'KAL ref',
        books: u ? [{ name: 'KAL', odds: a, url: u }] : [], legs: [{ player: t.player, market: 'Anytime TD \u00b7 ' + (t.matchup || ''), matchup: t.matchup, line: 1, lineText: '1+', odds: a, x: { league: 'nfl', name: t.player, nflTeam: t.team || '', nflLive: true, anytime: true } }],
        details: details + '\nImplied probability ' + Math.round((t.prob || 0) * 100) + '%' });
    });
    if (bb && (bb.picks || []).length) {
      out.push({ sport: 'NFL', type: bb.picks.length + '-leg combo', title: 'COMBO', date: dl, source: 'Not placed \u00b7 RixPicks', oddsLabel: 'KAL ref', game: bb.matchup || undefined,
        legs: bb.picks.map(function (b) { return { player: b.player, market: 'Anytime TD', line: 1, lineText: '1+', odds: aml(b.price_c), x: { league: 'nfl', name: b.player, nflTeam: b.team || '', nflLive: true, anytime: true } }; }),
        books: bb.picks.map(function (b) { return okUrl(b.link) ? { name: 'KAL', odds: aml(b.price_c), url: okUrl(b.link) } : null; }).filter(Boolean),
        details: details + (bb.est_cost_c ? '\nSum of individual asks ' + bb.est_cost_c + 'c (not a combined quote).' : '') });
    }
    return out;
  }
  function surfaceNfl() {
    var box = document.getElementById('rpNfl');
    if (!box) return;
    fetchJ('slates/nfl_chips.json').catch(function () { return null; }).then(function (cj) {
      var chips = {};
      ((cj && cj.legs) || []).forEach(function (l) { if (l.kalshi && typeof l.kalshi.ask_c === 'number') chips[((l.player || '') + '|' + (l.team || '')).toLowerCase()] = { ask_c: l.kalshi.ask_c, url: l.kalshi.url, ticker: typeof l.kalshi.ticker === 'string' ? l.kalshi.ticker : null }; });
      return fetchJ('slates/nfl_latest.json').then(function (j) {
        if (!j || j.version !== 1) return;
        try { if (j.generated_at && Date.now() - Date.parse(j.generated_at) > 4 * 24 * 3600 * 1000) return; } catch (e) { return; }
        var specs = mapNfl(j, chips); if (!specs.length) return;
        hideOld(box); mountSpecs(makeGrid(box, 'rpxNflGrid'), specs); poll();
      });
    }).catch(function () { });
  }
  /* night slate (slates/nfl_night.json): DK singles, Kalshi game lines (moneyline/spread) and the SGP idea */
  function mapNight(j) {
    var out = mapNfl(j, {}), singles = ((j.dk || {}).singles) || [], gl = ((j.kalshi || {}).game_lines) || [], sgp = j.sgp_idea;
    var ms = {}; singles.forEach(function (x) { if (x.matchup) ms[x.matchup] = 1; });
    var mu = Object.keys(ms).length === 1 ? Object.keys(ms)[0] : ((sgp && sgp.matchup) || '');
    var ko = j.kickoff ? Date.parse(j.kickoff) : NaN, ko2 = isFinite(ko) ? new Date(ko).toISOString() : undefined;
    var koL = isFinite(ko) ? new Date(ko).toLocaleString('en-US', { timeZone: 'America/Los_Angeles', weekday: 'short', hour: 'numeric', minute: '2-digit' }) + ' PT' : undefined;
    var dl = j.generated_at ? hDayShort(ptDay(Date.parse(j.generated_at))) : '';
    var details = (j.window_label ? j.window_label + '\n' : '') + (j.generated_at ? 'Posted ' + j.generated_at : '');
    gl.forEach(function (g) {
      var pc = (typeof g.price_c === 'number' && g.price_c >= 1 && g.price_c <= 99) ? g.price_c : null; if (pc === null) return;
      var a = aml(pc), u = okUrl(g.link), tk = String(g.ticker || ''), ab = (tk.match(/-([A-Z]{2,4})\d*$/) || [])[1] || '';
      var cap = g.captured_at ? new Date(g.captured_at).toLocaleString('en-US', { timeZone: 'America/Los_Angeles', hour: 'numeric', minute: '2-digit' }).toLowerCase().replace(/\s/g, '') : '';
      var x = { league: 'nfl', nflTeam: ab, nflLive: true, gameLine: true, commence: ko2 }, leg;
      if (/^winner$/i.test(g.market || '') && /\smoneyline$/i.test(g.title || '')) {
        var tn = String(g.title).replace(/\s+moneyline$/i, ''); x.ml = tn; x.mlAbbr = ab;
        leg = { player: tn, market: 'Moneyline' + (mu ? ' \u00b7 ' + mu : ''), matchup: mu || undefined, line: 1, lineText: 'ML', odds: a, timeLabel: koL, x: x };
      } else {
        var sm = String(g.title || '').match(/^(.+?)\s([+-]\d+(?:\.\d+)?)\s*\((?:wins by over|loses by less than|wins or loses by less than)\s[\d.]+\)$/i);
        if (/^spread$/i.test(g.market || '') && sm && ab) { x.spreadTeam = ab; x.spreadLine = Number(sm[2]); leg = { player: sm[1], market: 'Spread ' + sm[2] + (mu ? ' \u00b7 ' + mu : ''), matchup: mu || undefined, line: 1, lineText: sm[2], odds: a, timeLabel: koL, x: x }; }
        else { x.nflLive = false; delete x.gameLine; leg = { player: g.title, market: (g.market || '') + (mu ? ' \u00b7 ' + mu : ''), matchup: mu || undefined, odds: a, timeLabel: koL, x: x }; }
      }
      out.push({ sport: 'NFL', type: 'Game line', title: /^winner$/i.test(g.market || '') ? 'MONEYLINE' : (/^spread$/i.test(g.market || '') ? 'SPREAD' : String(g.market || 'GAME LINE').toUpperCase()), date: dl, source: 'Not placed \u00b7 RixPicks', oddsLabel: 'KAL ref', books: u ? [{ name: 'KAL', odds: a + (cap ? ' \u00b7 ' + cap : ''), url: u }] : [], legs: [leg], details: details + '\nKalshi ' + (g.market || 'game line') + ' reference price' });
    });
    if (sgp && (sgp.legs || []).length) {
      out.push({ sport: 'NFL', type: sgp.legs.length + '-leg parlay', title: 'SAME GAME PARLAY', date: dl, source: 'Idea only \u00b7 RixPicks', oddsLabel: 'No combined quote', game: mu || undefined,
        legs: sgp.legs.map(function (l) { return { player: l.player, market: 'Anytime TD' + (mu ? ' \u00b7 ' + mu : ''), matchup: mu || undefined, line: 1, lineText: '1+', timeLabel: koL, x: { league: 'nfl', name: l.player, nflTeam: l.team || '', nflLive: true, anytime: true, commence: ko2 } }; }),
        books: [], details: details + (sgp.note ? '\n' + sgp.note : '') });
    }
    return out;
  }
  function surfaceNight() {
    var box = document.getElementById('rpNight');
    if (!box) return;
    fetchJ('slates/nfl_night.json').then(function (j) {
      if (!j || j.version !== 1 || j.window !== 'sun-night') return;
      var specs = mapNight(j); if (!specs.length) return;
      hideOld(box); mountSpecs(makeGrid(box, 'rpxNightGrid'), specs); poll();
    }).catch(function () { });
  }
  /* live binding for NFL legs: the existing server-side feed (slates/nfl_live.json) names the ESPN event; box-score stat then comes from ESPN */
  function resolveNfl() {
    var need = [];
    handles.forEach(function (h) { h.spec.legs.forEach(function (l) { if (l.x && l.x.nflLive && !l.x.event && !l.x.resolved) need.push(l.x); }); });
    if (!need.length) return Promise.resolve();
    return fetchJ2('slates/nfl_live.json').then(function (j) {
      var gm = {}; (j.games || []).forEach(function (g) { gm[String(g.espn_event_id)] = g; });
      need.forEach(function (x) {
        var m = (j.legs || []).filter(function (l) { return x.gameLine ? l.team === x.nflTeam : (String(l.player || '').toLowerCase() === String(x.name || '').toLowerCase() && (!x.nflTeam || l.team === x.nflTeam)); });
        var evs = {}; m.forEach(function (l) { evs[String(l.espn_event_id)] = l; });
        var g = x.gameLine ? (Object.keys(evs).length === 1 ? gm[Object.keys(evs)[0]] : null) : (m.length === 1 ? gm[String(m[0].espn_event_id)] : null);
        if (g && isFinite(Date.parse(g.commence || ''))) { x.event = String(g.espn_event_id); x.espnUrl = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event=' + x.event; x.commence = g.commence; x.resolved = 1; }
      });
    }, function () { });
  }
  function fetchJ2(u) { return window.fetch(u + '?cb=' + Date.now(), { cache: 'no-store' }).then(function (r) { if (!r.ok) throw 0; return r.json(); }); }

  /* ---------- surface: screenshot-sourced NFL cards (slates/nfl_ideas.json) rendered by active-day.js; each .rx-card article is swapped in place ---------- */
  function mapIdea(c, omitPlacementLabel) {
    var legs = c.legs || [], tt = hTitle({ title: c.title });
    var placed = /^PLACED/i.test(String(c.status || '')) ? 'Placed' : 'Placement unknown';
    var spec = { sport: String(c.title || '').split(' - ')[0] || 'NFL', type: legs.length > 1 ? legs.length + '-leg parlay' : 'Straight', title: tt.title, date: legs[0] && legs[0].date ? hDayShort(legs[0].date) : '',
      source: (omitPlacementLabel ? '' : placed + ' \u00b7 ') + (/^rix-/.test(String(c.id)) ? 'RixPicks' : 'Wooder Ice'), oddsLabel: 'Screenshot ref', sources: [], record: [] };
    if (tt.total) spec.total = tt.total;
    var seen = {}, groups = {};
    spec.legs = legs.map(function (l) {
      var pm = parseMarket(l.market), parts = String(l.matchup || '').split(' @ ');
      var o = { player: l.player, market: pm.market + (l.matchup ? ' \u00b7 ' + l.matchup : ''), matchup: l.matchup, line: has(l.target) ? Number(l.target) : pm.line, lineText: has(l.target) ? l.target + '+' : pm.lineText, timeLabel: l.time };
      if (has(l.odds)) o.odds = String(l.odds);
      o.x = { league: String(l.league || 'nfl').toLowerCase(), commence: l.commence, event: String(l.event_id || ''), espnUrl: l.game_source_url, athlete: l.espn_athlete_id, anytime: l.stat === 'anytimeTD', keys: l.stat && l.stat !== 'anytimeTD' ? [l.stat] : undefined, away: parts[1] ? parts[0] : '', home: parts[1] || '' };
      if (l.game_source_url && !seen[l.game_source_url]) { seen[l.game_source_url] = 1; spec.sources.push({ label: (l.matchup || 'Game') + ' ESPN', url: l.game_source_url }); }
      if (l.group) groups[l.group] = 1;
      return o;
    });
    [c.status, c.quote_note, c.quote_source].forEach(function (t) { if (pub(t || '')) spec.record.push(pub(t)); });
    Object.keys(groups).forEach(function (g) { spec.record.push(g + ' \u00b7 group quote only'); });
    spec.details = spec.record.join('\n');
    return spec;
  }
  function surfaceIdeas() {
    fetchJ('slates/nfl_ideas.json').then(function (j) {
      var cards = ((j && j.cards) || []).filter(function (c) { return c.quote_source && c.status !== 'archived' && ['rix-20261108-a', 'rix-20261108-b', 'rix-20261108-c'].indexOf(c.id) < 0; });
      if (!cards.length) return;
      var by = {}; cards.forEach(function (c) { by[c.id] = c; });
      function swap() {
        Array.prototype.forEach.call(document.querySelectorAll('article.rx-card[data-card]:not([data-rpx-old])'), function (a) {
          var c = by[a.getAttribute('data-card')]; if (!c) return;
          hideOld(a);
          var g = document.createElement('div'); g.className = 'rp-slip-grid'; a.insertAdjacentElement('afterend', g);
          var omitPlacementLabel = !!a.closest('#st-home') && ['rix-20261112-wasnyg-atd4', 'rix-20261112-wasnyg-atd2', 'rix-20261112-nba14'].indexOf(c.id) >= 0;
          mountSpecs(g, [mapIdea(c, omitPlacementLabel)]);
        });
        poll();
      }
      swap();
      new MutationObserver(swap).observe(document.body, { childList: true, subtree: true });
    }).catch(function () { });
  }

  /* ---------- surfaces: first TD picks, batch ideas, night SGP idea (no event binding in their data; same sources as before) ---------- */
  function ptStr(iso) { var t = Date.parse(iso); return isFinite(t) ? whenLabel(t) + ' PT' : ''; }
  function mapFtd(p) {
    return { sport: 'NFL', type: 'Straight', title: 'FIRST TD SCORER', date: '', source: 'Placement unknown \u00b7 Wooder Ice', oddsLabel: 'Odds',
      legs: [{ player: p.player, market: String(p.market || '') + (p.matchup ? ' \u00b7 ' + p.matchup : ''), matchup: p.matchup, odds: String(p.american), timeLabel: ptStr(p.commence),
        x: { league: 'nfl', commence: p.commence } }], details: 'Personal pick from Wooder Ice.' };
  }
  function mapBatch(cd) {
    var v = { KAL: 1, POLY: 1, DKP: 1 }, rec = [];
    var legs = (cd.legs || []).filter(function (lg) { return lg.player && lg.market; }).map(function (lg) {
      var ps = [];
      (lg.links || []).forEach(function (l) { var c = +l.cents; if (!v[l.venue] || l.cents == null || !(c > 0 && c < 100)) return; var a = aml(c); if (a) ps.push(l.venue + ' ' + a); });
      var o = { player: lg.player, market: lg.market, timeLabel: cd.time || '' };
      if (ps.length) o.odds = ps[0].split(' ')[1];
      rec.push(lg.player + ' \u00b7 ' + lg.market + (ps.length ? ': ' + ps.join(' \u00b7 ') : '') + ((lg.unlisted || []).length ? ' \u00b7 Not listed on ' + lg.unlisted.join(', ') : '') + (lg.note ? ' \u00b7 ' + lg.note : ''));
      return o;
    });
    if (cd.asof) rec.push(cd.asof); if (cd.assumptions) rec.push(cd.assumptions);
    return { sport: 'NFL', type: legs.length + '-leg idea', title: String(cd.title || '').replace(/^\d+-leg\s+/i, '').toUpperCase(), date: cd.time || '', game: cd.matchup || undefined,
      source: 'Not placed \u00b7 Wooder Ice', oddsLabel: 'First listed ref', legs: legs, details: rec.join('\n') };
  }
  function mapSgp(j) {
    var rec = [];
    var legs = j.legs.map(function (l) {
      var a = aml(l.price_c);
      rec.push(l.player + ' ' + l.market + ' \u00b7 DK Predictions ' + a + ' as of ' + ptStr(l.captured_at) + (typeof l.source_snapshot_c === 'number' && l.source_snapshot_c !== l.price_c ? ' \u00b7 Wooder Ice snapshot ' + l.source_snapshot_c + 'c; live DK ' + l.price_c + '% at capture' : '') + ' \u00b7 selection link unavailable');
      var pm = parseMarket(l.market);
      return { player: l.player, market: pm.market, line: pm.line, lineText: pm.lineText, odds: a };
    });
    rec.push('Individual DK displayed percentages converted to American-style equivalents at capture. Prices can move. No combined DK quote or wager posted. Event page is not an exact-selection link, so these rows are unlinked.');
    return { sport: 'NFL', type: legs.length + '-leg SGP idea', title: 'SAME GAME PARLAY', date: 'Sunday 5:20 PM PT', game: 'LAR @ DEN', source: 'Not placed \u00b7 idea only', oddsLabel: 'DKP ref', legs: legs, details: rec.join('\n') };
  }
  function surfaceMisc() {
    function put(id, specs, old) { if (!specs.length || !old) return; hideOld(old); mountSpecs(makeGrid(old, id), specs); poll(); }
    fetchJ('slates/wooder_first_td.json').then(function (j) {
      var P = ((j && j.picks) || []).filter(function (p) { return p && p.player && p.market && p.american; });
      put('rpxFtd', P.map(mapFtd), document.getElementById('rpFtd'));
    }).catch(function () { });
    fetchJ('slates/wooder_batch.json').then(function (j) {
      var C = (j && j.cards) || []; if (!C.length || j.date !== ptDay()) return;
      var specs = C.slice(0, 10).filter(function (c) { return c.title && (c.legs || []).length; }).map(mapBatch).filter(function (s) { return s.legs.length; });
      put('rpxBatch', specs, document.getElementById('rpBatchIdeas'));
    }).catch(function () { });
    fetchJ('slates/nfl_night_sgp.json').then(function (j) {
      if (!j || j.version !== 1 || j.kind !== 'nfl-sgp-idea' || j.status !== 'idea_only' || j.combined_price !== null || !Array.isArray(j.legs) || j.legs.length !== 8 || j.matchup !== 'LAR @ DEN') return;
      if (j.legs.some(function (l) { return !aml(l.price_c) || !l.player || !l.market || !l.captured_at || l.price_type !== 'displayed_probability_percent'; })) return;
      var old = document.getElementById('rpNightSgp'), card = document.getElementById('rpNightSgpCard'); if (!old || !card) return;
      hideOld(old); mountSpecs(makeGrid(old, 'rpxSgp'), [mapSgp(j)]); card.hidden = false; poll();
    }).catch(function () { });
  }

  /* ---------- surface: Trinity ticket overrides (cards built by the page into #rpOvTix); swapped in place, removed when the override is withdrawn ---------- */
  function mapOv(card) {
    function T(n) { return n ? n.textContent : ''; }
    var title = T(card.querySelector('.ov-ticket-title')), subs = [], legs = [], lines = [];
    Array.prototype.forEach.call(card.children, function (ch) {
      var cl = ch.className || '';
      if (/ov-leg/.test(cl)) {
        var p = ch.textContent.split(' \u00b7 '), pl = p[0] || '', mk = p[1] || '', odds = '';
        for (var i = 2; i < p.length; i++) { var m = p[i].match(/^([A-Z]+)\s+(\d+(?:\.\d+)?)c$/); if (m && !odds) { var a = aml(Number(m[2])); if (a) odds = a; } }
        var pm = parseMarket(mk), o = { player: pl, market: pm.market, line: pm.line, lineText: pm.lineText };
        if (odds) o.odds = odds;
        legs.push(o); lines.push(ch.textContent);
      } else if (/(^|\s)sub(\s|$)/.test(cl)) { subs.push(ch.textContent); lines.push(ch.textContent); }
    });
    var pre = (title.match(/^(NFL|NBA|NCAAF|MLB|NHL|WNBA|NCAAB)\b/) || [])[1] || '';
    var tt = hTitle({ title: title });
    return { sport: pre || 'TICKET', type: legs.length > 1 ? legs.length + '-leg parlay' : 'Straight', title: tt.title, date: '', source: 'Placement unknown \u00b7 RixPicks', oddsLabel: 'Ref', legs: legs, details: lines.join('\n') };
  }
  function surfaceOv() {
    var pairs = [];
    function sync() {
      pairs = pairs.filter(function (p) { if (p.card.isConnected) return true; if (p.grid.parentNode) p.grid.parentNode.removeChild(p.grid); return false; });
      var any = false;
      Array.prototype.forEach.call(document.querySelectorAll('#rpOvTix .ov-ticket:not([data-rpx-old])'), function (card) {
        var spec = mapOv(card); if (!spec.legs.length) return;
        hideOld(card); any = true;
        var g = document.createElement('div'); g.className = 'rp-slip-grid'; card.insertAdjacentElement('afterend', g);
        mountSpecs(g, [spec]); pairs.push({ card: card, grid: g });
      });
      if (any) poll();
    }
    new MutationObserver(sync).observe(document.body, { childList: true, subtree: true });
    sync();
  }

  window.RPApp = {
    mountSpecs: mountSpecs, makeGrid: makeGrid, verifyPanel: verifyPanel, hideOld: hideOld, poll: poll,
    whenLabel: whenLabel, phaseOf: phaseOf, leagueOfUrl: leagueOfUrl, ptDay: ptDay,
    _games: games, _derive: derive, _gameFromEspn: gameFromEspn, _gameFromNhl: gameFromNhl, _mapHistory: mapHistory, _mapWinner: mapWinner, _mapTicket: mapTicket, _mapNfl: mapNfl, _mapNight: mapNight, _mapIdea: mapIdea, _mapOv: mapOv, _mapFtd: mapFtd, _mapBatch: mapBatch, _mapSgp: mapSgp, _mapDinger: mapDinger, _mapCombo: mapCombo,
    register: function (grid, specs) { var hs = mountSpecs(grid, specs); poll(); return hs; }
  };
  onReady(function () { surfaceHistory(); surfaceWinners(); surfaceWooder(); surfaceNfl(); surfaceNight(); surfaceIdeas(); surfaceMisc(); surfaceOv(); });
  window.dispatchEvent(new Event('rp-slip-ready'));
})();
