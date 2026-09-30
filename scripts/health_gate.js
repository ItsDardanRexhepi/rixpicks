#!/usr/bin/env node
/* RixPicks pre-publish health gate (Julian 9/30 order-of-operations: "Things need to be
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

const SERVE = process.argv.includes('--serve');
const BASE = (process.argv.find(a => a.startsWith('--base=')) || '').slice(7) || 'https://rix-picks.com';

async function fetchText(u) {
  const r = await fetch(u + (u.includes('?') ? '&' : '?') + 'cb=' + Date.now(), { cache: 'no-store' });
  if (!r.ok) throw new Error('HTTP ' + r.status + ' ' + u);
  return r.text();
}

(async () => {
  if (!SERVE) {
    // 1. fixture suite (combo freshness, feed wire, CASHED spec, dingers/TD trackers, futures bypass)
    let fx = '';
    try { fx = execFileSync('node', ['scripts/test_combo_fresh_export.js'], { encoding: 'utf8' }); }
    catch (e) { fx = (e.stdout || '') + (e.stderr || ''); }
    check('fixture suite ALL OK', /ALL OK/.test(fx) && !/^\d+ FAIL/m.test(fx), 'a tested display/data regression would ship');
    // 2. builder twins byte-identical
    let same = false;
    try { execSync('cmp -s scripts/build_gh_page_v2.py scripts/_build_nocanon_v2.py'); same = true; } catch (e) {}
    check('builder twins byte-identical', same, 'canonical/nocanon pages would drift apart silently');
    // 3. built pages: every script block parses
    for (const f of ['index.html', 'index_nocanon.html']) {
      let ok = true, n = 0;
      if (fs.existsSync(f)) {
        const s = fs.readFileSync(f, 'utf8'), re = /<script>([\s\S]*?)<\/script>/g; let m;
        while ((m = re.exec(s))) { n++; try { new Function(m[1]); } catch (e) { ok = false; } }
      } else ok = false;
      check(f + ': all ' + n + ' script blocks parse', ok && n > 0, 'a syntax error blanks whole page modules');
    }
    // 4. critical functionality markers in the built page
    const page = fs.existsSync('index.html') ? fs.readFileSync('index.html', 'utf8') : '';
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
  } else {
    // --serve: cold checks against the live site
    let page = '';
    try { page = await fetchText(BASE + '/'); } catch (e) { check('home page serves', false, 'site down: ' + e.message); }
    if (page) {
      check('home page serves (>100KB)', page.length > 100000, 'site down or truncated');
      check('served: combos module present', page.includes('rpCmbGo'), 'Wooder Ice ideas/combos card hidden on live site');
      check('served: feed wire present', page.includes('rpFeedWire'), 'live trackers dead on live site');
      check('served: no Game-not-started text', !page.includes('Game not started'), 'pregame spec regression live');
      check('served: unknown-not-zero guard live', page.includes('if(count==null&&(state==="in"||state==="post"))'), 'invented-zero regression live');
    }
    try {
      const combos = JSON.parse(await fetchText(BASE + '/slates/wooder_combos.json'));
      const n = (combos.combos || []).length;
      check('combos slate parses with entries (' + n + ')', n > 0, 'ideas/combos card empty');
    } catch (e) { check('combos slate parses', false, 'ideas/combos card broken: ' + e.message); }
    try {
      const fut = JSON.parse(await fetchText(BASE + '/futures.json'));
      const qs = (Array.isArray(fut) ? fut : []).map(r => (r.kalshi_quote || {}).quoted_at).filter(Boolean).sort().reverse();
      const ageMin = qs.length ? (Date.now() - new Date(qs[0]).getTime()) / 60000 : Infinity;
      check('futures.json quoted_at fresh (' + (qs.length ? ageMin.toFixed(1) + ' min' : 'no quotes') + ')', qs.length > 0 && ageMin < 20, 'futures quotes stale beyond the 12-min gate pattern');
    } catch (e) { check('futures.json parses', false, 'futures page broken: ' + e.message); }
    try {
      const tf = await fetchText(BASE + '/ticket-feed.js');
      check('ticket-feed.js serves', tf.length > 5000, 'live ticket trackers dead');
    } catch (e) { check('ticket-feed.js serves', false, 'live ticket trackers dead: ' + e.message); }
    try {
      const pt = JSON.parse(await fetchText(BASE + '/slates/past_tickets.json'));
      check('past_tickets parses (' + (pt.entries || []).length + ' entries)', (pt.entries || []).length > 0, 'past tickets page broken');
    } catch (e) { check('past_tickets parses', false, 'past tickets page broken: ' + e.message); }
  }
  console.log(failures.length ? failures.length + ' FAIL - HOLD ALL PUBLISHES (fixes excepted)' : 'HEALTH GATE PASS');
  process.exit(failures.length ? 1 : 0);
})();
