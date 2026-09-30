#!/usr/bin/env node
/* K19 fixture (9/30 midnight QA, Abushaar class): an MMA pick row with empty card eid must
   still paint its final result - the builder binds ceid (card event) and the live-score lane
   matches the FIGHT via data-comp, grading on the competitor winner flag (MMA has no score;
   a 0-0 read would paint every home-side pick L and show a fake 0-0).
   Bite-proof: red on builders without the fallback / winner-flag render.
   Run: node scripts/test_mma_winner_flag.js */
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
let failures = 0;
function check(label, got, want) {
  const ok = got === want;
  console.log((ok ? 'OK   ' : 'FAIL ') + label + (ok ? '' : ` (got ${JSON.stringify(got)}, want ${JSON.stringify(want)})`));
  if (!ok) failures++;
}
for (const B of ['build_gh_page_v2.py', '_build_nocanon_v2.py']) {
  const src = fs.readFileSync(path.join(__dirname, B), 'utf8');
  check(`${B}: builder binds ceid for mma rows with empty eid`,
        src.includes(`if not _eid and p.get('espn_league','')=='mma/ufc' and g.get('ceid'): _eid=str(g['ceid'])`), true);
  check(`${B}: combo legs carry data-comp`, src.includes('class="cxleg" data-espn="%s" data-eid="%s" data-comp="%s"'), true);
  check(`${B}: painter binds the fight via data-comp`, src.includes('_comps.find(c=>String(c.id)===String(pk.dataset.comp))'), true);
  check(`${B}: painter reads the competitor winner flag`, src.includes(`w:hm.winner===true?'h':(aw.winner===true?'a':'')`), true);

  // functional: rpLsRender post-state behavior, extracted from the real template
  const undoubled = src.replace(/\{\{/g, '{').replace(/\}\}/g, '}');
  const i = undoubled.indexOf('function rpLsRender(');
  check(`${B}: rpLsRender extractable`, i >= 0, true);
  let depth = 0, end = -1;
  for (let k = i; k < undoubled.length; k++) {
    if (undoubled[k] === '{') depth++;
    else if (undoubled[k] === '}') { depth--; if (depth === 0) { end = k + 1; break; } }
  }
  const ctx = vm.createContext({});
  vm.runInContext(undoubled.slice(i, end), ctx);
  function fakePick(side) {
    const el = { className: '', innerHTML: '' };
    return { dataset: { side }, querySelector: () => el, __el: el };
  }
  // the QA case: Abushaar (home) lost to Staines - winner flag away, no score
  let pk = fakePick('home');
  ctx.rpLsRender(pk, { a: 'Staines', h: 'Abushaar', as: 0, hs: 0, st: 'Final', state: 'post', w: 'a' });
  check(`${B}: MMA home-side loss paints lost`, pk.__el.className, 'ls on lost');
  check(`${B}: MMA verdict shows L + Final`, /^<b>L<\/b> &middot; Final$/.test(pk.__el.innerHTML), true);
  check(`${B}: MMA verdict never paints a fake 0-0`, pk.__el.innerHTML.includes('0 - 0'), false);
  // a WINNING home MMA pick must paint won (score-read would have said lost)
  pk = fakePick('home');
  ctx.rpLsRender(pk, { a: 'Staines', h: 'Abushaar', as: 0, hs: 0, st: 'Final', state: 'post', w: 'h' });
  check(`${B}: MMA home-side win paints won`, pk.__el.className, 'ls on won');
  // regression: score-based sports unchanged (away win by score)
  pk = fakePick('away');
  ctx.rpLsRender(pk, { a: 'PHI', h: 'ATL', as: 3, hs: 5, st: 'Final', state: 'post' });
  check(`${B}: score verdict keeps score text`, pk.__el.innerHTML.includes('PHI 3 - ATL 5 Final') && pk.__el.className === 'ls on lost', true);
}
console.log(failures ? 'FAILURES: ' + failures : 'ALL CHECKS PASS');
process.exit(failures ? 1 : 0);
