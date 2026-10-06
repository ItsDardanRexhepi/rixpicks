#!/usr/bin/env node
/* RixPicks pre-publish health gate (9/30 order-of-operations: "Things need to be
   fixed before updates push. We cant be trying to push changes to a broke site. The site
   functionality comes first").
   TWO MODES:
   - pre-publish (default): runs against the LOCAL build before any push. A publish is
     blocked unless every check passes.
   - --serve: cold-fetches the LIVE site and verifies served functionality (post-deploy
     verification + broken-site detection for the hold rule).
   Exit 0 = healthy. Exit 1 = one or more FAIL lines (each names what broke and what the
   user cannot see). Never exits 0 with an untested surface. */
const fs = require('fs'), vm = require('vm'), { execSync, execFileSync } = require('child_process');
const failures = [];
const check = (name, cond, impact) => { console.log((cond ? 'OK   ' : 'FAIL ') + name + (cond ? '' : (impact ? '  [user impact: ' + impact + ']' : ''))); if (!cond) failures.push(name); };

const SERVE = process.argv.includes('--serve') || process.argv.includes('--hold');
// --hold (workflow auto-hold, 9/30 6:25 PM: structural failures only; data outages such as a
// blank X feed or stale quotes are alert-only and must never stop posting). Implies --serve.
// Exit 0 pass/unknown, 1 = proven structural FAIL (hold), 2 = gate error (never holds).
const HOLD = process.argv.includes('--hold');
const BASE = (process.argv.find(a => a.startsWith('--base=')) || '').slice(7) || 'https://rix-picks.com';

async function fetchText(u) {
  let last;
  for (let i = 0; i < 3; i++) {
    try {
      const r = await fetch(u + (u.includes('?') ? '&' : '?') + 'cb=' + Date.now(), { cache: 'no-store' });
      if (r.status >= 500) { last = new Error('HTTP ' + r.status + ' ' + u); last.net = true; }
      else if (!r.ok) throw new Error('HTTP ' + r.status + ' ' + u);
      else return await r.text();
    } catch (e) { if (e.message.startsWith('HTTP ') && !e.net) throw e; last = last || e; last.net = true; }
    await new Promise(res => setTimeout(res, 2000));
  }
  throw last;
}
// transient network/5xx = UNKNOWN (never a hold: holding cannot fix a host outage); proven bad content/404 = FAIL
const failOrUnknown = (e, name, impact) => { if (e && e.net) console.log('UNKNOWN ' + name + ' (' + e.message + ') - not counted as a failure'); else check(name, false, impact); };
// What the system is learning (Home, builder _learnings_html): the #rpLearnHead heading and the #rpLearn
// box carry ledger text - day briefs and per-pick notes - that may hold any phrase ('Game not started',
// a module name). The substring checks below are about the page's own code and markup, so they read
// the page with that section cut out (local build and served site alike). The builder emits only div
// and span tags there and HTML-escapes every ledger value, so each <div>/</div> inside is its own and a
// depth count finds the end. Each id is cut at most once; an unclosed section, or a cut that would take
// any other tag (a </main>, a <script>), leaves the page whole (the stricter reading).
// scripts/test_health_gate_learn.js holds both modes to this; test_learnings_panel.py a real build.
function rpStripLearn(s) {
  const whole = String(s);
  let out = whole;
  for (const id of ['rpLearnHead', 'rpLearn']) {
    const m = new RegExp('<div\\s(?:[^>]*\\s)?id="' + id + '"[^>]*>').exec(out);
    if (!m) continue;
    const tag = /<div\b|<\/div>/g;
    tag.lastIndex = m.index + m[0].length;
    let depth = 1, t, end = -1;
    while ((t = tag.exec(out))) { depth += t[0] === '</div>' ? -1 : 1; if (!depth) { end = tag.lastIndex; break; } }
    if (end < 0 || /<(?!\/?(?:div|span)\b)/i.test(out.slice(m.index, end))) return whole;
    out = out.slice(0, m.index) + out.slice(end);
  }
  return out;
}

(async () => {
  if (process.env.HOLD_SELFTEST_ERROR === '1') throw new Error('forced gate error (selftest hook)');
  if (!SERVE || HOLD) {
    // 1. fixture suite (combo freshness, feed wire, CASHED spec, dingers/TD trackers, futures bypass)
    let fx = '';
    try { fx = execFileSync('node', ['scripts/test_combo_fresh_export.js'], { encoding: 'utf8' }); }
    catch (e) { fx = (e.stdout || '') + (e.stderr || ''); }
    let yx = '';
    try { yx = execFileSync('node', ['scripts/test_nfl_yards_counter.js'], { encoding: 'utf8' }); }
    catch (e) { yx = (e.stdout || '') + (e.stderr || ''); }
    let vz = '';
    try { vz = execFileSync('node', ['scripts/test_news_verified_zero.js'], { encoding: 'utf8' }); }
    catch (e) { vz = (e.stdout || '') + (e.stderr || ''); }
    check('news verified-zero fixture ALL OK', /ALL OK/.test(vz) && !/FAIL/.test(vz), 'the news bucket skip rule could pass on an unverified read');
    check('yards counter fixture ALL OK', /ALL OK/.test(yx) && !/FAIL/.test(yx), 'NFL futures yards could render an invented number');
    try { const yd = JSON.parse(fs.readFileSync('slates/nfl_rec_yards.json', 'utf8')); check('nfl_rec_yards.json parses with numeric players', Object.values(yd.players || {}).length > 0 && Object.values(yd.players).every(p => typeof p.yards === 'number'), 'yards counters would all show Unavailable'); }
    catch (e) { check('nfl_rec_yards.json parses', false, 'yards counters would all show Unavailable: ' + e.message); }
    try { const ix = rpStripLearn(fs.readFileSync('index.html', 'utf8'));
      check('no literal \\n text leak at page bottom', !ix.includes('</div>\\n<script>'), 'a stray backslash-n shows above the ticker');
      check('ticket boxes carry no repeated fine print (one note above Rolling Record)', !ix.includes('c.estimate_note') && !ix.includes('c.prices_note') && ix.includes('id="rpWNote"') && ix.indexOf('id="rpWNote"') < ix.indexOf('id="rpWRecWrap"'), 'cluttered ticket boxes or the consolidated note missing'); }
    catch (e) { check('index.html readable for clutter check', false, e.message); }
    check('fixture suite ALL OK', /ALL OK/.test(fx) && !/^\d+ FAIL/m.test(fx), 'a tested display/data regression would ship');
    // 2. builder twins byte-identical
    let same = false;
    try { execSync('cmp -s scripts/build_gh_page_v2.py scripts/_build_nocanon_v2.py'); same = true; } catch (e) {}
    check('builder twins byte-identical', same, 'canonical/nocanon pages would drift apart silently');
    // 3. built page: every script block parses
    for (const f of ['index.html']) {
      let ok = true, n = 0;
      if (fs.existsSync(f)) {
        const s = fs.readFileSync(f, 'utf8'), re = /<script>([\s\S]*?)<\/script>/g; let m;
        while ((m = re.exec(s))) { n++; try { new Function(m[1]); } catch (e) { ok = false; } }
      } else ok = false;
      check(f + ': all ' + n + ' script blocks parse', ok && n > 0, 'a syntax error blanks whole page modules');
    }
    // index_nocanon.html is retired (Oct 2): an orphaned second copy of the homepage, served publicly.
    // The builder writes a fixed noindex notice canonical to / for that path; absent is fine too.
    // A full homepage there again is a duplicate of the home page that search engines can index.
    if (fs.existsSync('index_nocanon.html')) {
      const nc = fs.readFileSync('index_nocanon.html', 'utf8');
      check('index_nocanon.html is the retired notice (noindex, canonical to /, no homepage)',
        nc.includes('<meta name="robots" content="noindex">') && nc.includes('<link rel="canonical" href="https://rix-picks.com/">') && !/<script/i.test(nc),
        'a duplicate homepage is served at /index_nocanon.html and can be indexed');
    } else check('index_nocanon.html retired (absent)', true);
    // 4. critical functionality markers in the built page
    const page = fs.existsSync('index.html') ? rpStripLearn(fs.readFileSync('index.html', 'utf8')) : '';
    const markers = [
      ['combos module (Same Game Parlays)', 'rpCmbGo', 'Wooder Ice ideas/combos card hidden'],
      ['rpComboFresh exported global', 'window.rpComboFresh=rpComboFresh;', 'combos module fail-closes hidden (Sep 30 regression class)'],
      ['feed wire (live tracker paint)', 'rpFeedWire', 'K/hits live trackers never paint'],
      ['futures bypass present', 'c.futures===true', 'season-long futures items expire off at day roll'],
      ['dingers module fetch', 'slates/wooder_dingers.json', 'Dingers card hidden'],
      ['tickets module fetch', 'slates/wooder_tickets.json', 'anytime-TD/tickets card hidden'],
      ['unknown-not-zero guard', 'if(count==null&&(state==="in"||state==="post"))', 'missing data paints invented zeros'],
      ['blank-pregame spec (no Game-not-started text)', null, 'pregame legs show stale text instead of blank'],
      ['CASHED explainer', 'CASHED = live stat threshold met', 'threshold/payout distinction lost'],
      ['ticket feed client', 'ticket-feed.js', 'live ticket trackers dead'],
    ];
    for (const [name, needle, impact] of markers) {
      if (name.startsWith('blank-pregame')) check(name, !page.includes('Game not started'), impact);
      else check(name, needle ? page.includes(needle) : false, impact);
    }
    // Dingers mounts exactly once on every card: on the MLB tab when the card has an MLB pick,
    // otherwise as a Home panel (a non-MLB card is a normal card, never a hold).
    check('dingers module mounted exactly once', (page.match(/slates\/wooder_dingers\.json/g) || []).length === 1, 'Dingers card missing or rendered twice');
  }
  if (SERVE) {
    // --serve: cold checks against the live site
    let raw = '';
    try { raw = await fetchText(BASE + '/'); } catch (e) { failOrUnknown(e, 'home page serves', 'site down: ' + e.message); }
    const page = rpStripLearn(raw);
    if (raw) {
      check('home page serves (>100KB)', raw.length > 100000, 'site down or truncated');
      check('served: combos module present', page.includes('rpCmbGo'), 'Wooder Ice ideas/combos card hidden on live site');
      check('served: feed wire present', page.includes('rpFeedWire'), 'live trackers dead on live site');
      check('served: no Game-not-started text', !page.includes('Game not started'), 'pregame spec regression live');
      check('served: unknown-not-zero guard live', page.includes('if(count==null&&(state==="in"||state==="post"))'), 'invented-zero regression live');
      { let ok = true, n = 0; const re = /<script>([\s\S]*?)<\/script>/g; let m;
        while ((m = re.exec(page))) { n++; try { new Function(m[1]); } catch (e) { ok = false; } }
        check('served: all ' + n + ' script blocks parse', ok && n > 0, 'a syntax error blanks whole page modules on the live site'); }
    }
    try {
      const combos = JSON.parse(await fetchText(BASE + '/slates/wooder_combos.json'));
      const n = (combos.combos || []).length;
      check('combos slate parses' + (HOLD ? '' : ' with entries (' + n + ')'), HOLD ? true : n > 0, 'ideas/combos card empty');
    } catch (e) { failOrUnknown(e, 'combos slate parses', 'ideas/combos card broken: ' + e.message); }
    if (!HOLD) try {
      const fut = JSON.parse(await fetchText(BASE + '/futures.json'));
      const qs = (Array.isArray(fut) ? fut : []).map(r => (r.kalshi_quote || {}).quoted_at).filter(Boolean).sort().reverse();
      const ageMin = qs.length ? (Date.now() - new Date(qs[0]).getTime()) / 60000 : Infinity;
      check('futures.json quoted_at fresh (' + (qs.length ? ageMin.toFixed(1) + ' min' : 'no quotes') + ')', qs.length > 0 && require('./futures_window.js').futuresFresh(Date.now(), qs.length ? new Date(qs[0]).getTime() : NaN), 'futures quotes stale beyond the 12-min gate pattern (window-aware: quoter runs 9 AM-11:59 PM PT)');
    } catch (e) { check('futures.json parses', false, 'futures page broken: ' + e.message); }
    try {
      const tf = await fetchText(BASE + '/ticket-feed.js');
      check('ticket-feed.js serves', tf.length > 5000, 'live ticket trackers dead');
    } catch (e) { failOrUnknown(e, 'ticket-feed.js serves', 'live ticket trackers dead: ' + e.message); }
    try {
      const pt = JSON.parse(await fetchText(BASE + '/slates/past_tickets.json'));
      check('past_tickets parses (' + (pt.entries || []).length + ' entries)', HOLD ? Array.isArray(pt.entries) : (pt.entries || []).length > 0, 'past tickets page broken');
    } catch (e) { failOrUnknown(e, 'past_tickets parses', 'past tickets page broken: ' + e.message); }
    if (!HOLD) try {
      const yd = JSON.parse(await fetchText(BASE + '/slates/nfl_rec_yards.json'));
      const ageH = (Date.now() - new Date(yd.fetched_at).getTime()) / 3600000;
      check('served: nfl_rec_yards.json numeric + fresh (' + ageH.toFixed(1) + ' h)', Object.values(yd.players || {}).length > 0 && Object.values(yd.players).every(p => typeof p.yards === 'number') && ageH < 48, 'NFL futures yards counters show Unavailable');
    } catch (e) { check('served: nfl_rec_yards.json', false, 'NFL futures yards counters show Unavailable: ' + e.message); }
    // X feed emptiness (guard 4, 9/30 6:07 PM PT): alert-only class check, no behavior change.
    // The served pool legitimately ages to 0 under the owner's 24h horizon when X pulls are
    // walled (402). FAIL loud only on the TRANSITION (latest x_feed.json commit emptied a
    // non-empty prior within the last 60 min); otherwise a standing ALERT line, never a hold.
    if (!HOLD) try {
      const xf = JSON.parse(await fetchText(BASE + '/slates/x_feed.json'));
      const nItems = (xf.items || []).length;
      let msg = 'served: x_feed.json items=' + nItems;
      if (nItems > 0) { check(msg + ' (non-empty)', true); }
      else {
        let dropped = false, detail = 'no git history available';
        try {
          const lg = execFileSync('git', ['log', '-2', '--format=%H %ct', '--', 'slates/x_feed.json'], { encoding: 'utf8' }).trim().split('\n');
          if (lg.length === 2) {
            const [newH, newT] = lg[0].split(' '), prevH = lg[1].split(' ')[0];
            const prevN = (JSON.parse(execFileSync('git', ['show', prevH + ':slates/x_feed.json'], { encoding: 'utf8', maxBuffer: 1 << 26 })).items || []).length;
            const ageMin = (Date.now() / 1000 - Number(newT)) / 60;
            dropped = prevN > 0 && ageMin < 60;
            detail = 'prior x_feed.json commit ' + prevH.slice(0, 8) + ' had ' + prevN + ' items; latest change ' + newH.slice(0, 8) + ' ' + ageMin.toFixed(0) + ' min ago';
          }
        } catch (e) { detail = 'git history check failed: ' + e.message.split('\n')[0]; }
        // 9/30 6:25 PM: "X feed being out shouldn't stop posting. That's not core site functionality." Alert-only always.
        if (dropped) console.log('ALERT served: x_feed.json items=0 JUST EMPTIED (not a hold; ' + detail + '). X posts column empty; pool aged out past the 24h horizon or the ingest wiped it - check X 402 wall vs ingest before assuming.');
        else console.log('ALERT served: x_feed.json items=0 - X posts column empty (not a hold; ' + detail + '). Known cause 9/30: X 402 billing wall + 24h horizon age-out.');
      }
    } catch (e) { console.log('ALERT served: x_feed.json unreadable (not a hold): ' + e.message); }
  }
  console.log(failures.length ? failures.length + ' FAIL - HOLD ALL PUBLISHES (fixes excepted)' : 'HEALTH GATE PASS');
  process.exit(failures.length ? 1 : 0);
})().catch(e => { console.log('GATE ERROR (not a hold): ' + e.message); process.exit(2); });
