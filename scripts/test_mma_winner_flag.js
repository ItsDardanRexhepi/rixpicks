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
  // K19b: the resolution loop must handle the REAL ESPN MMA competitor shape - no homeAway,
  // no score, athletes keyed by displayName (serve-verified live shape, DWCS 600060739/401891663).
  // The original fixture mocked rpLsRender directly and never exercised resolution - the exact
  // blind spot that shipped the homeAway-only find. These checks close that class.

    const line = "const aw=cs.find(c=>c.homeAway==='away')||cs.find(c=>((c.athlete||{{}}).displayName||'')===(pk.dataset.away||'')),hm=cs.find(c=>c.homeAway==='home')||cs.find(c=>((c.athlete||{{}}).displayName||'')===(pk.dataset.home||''));";
    check(`${B}: resolution falls back to athlete-name match when homeAway is absent`, src.includes(line), true);
    // functional: run the real resolution expression against the live-shaped competitors
    const ctx2 = vm.createContext({});
    ctx2.cs = [
      { id: 'a1', type: 'athlete', order: 2, winner: true,  athlete: { displayName: 'George Staines', shortName: 'Staines' } },
      { id: 'a2', type: 'athlete', order: 1, winner: false, athlete: { displayName: 'Loai Abushaar', shortName: 'Abushaar' } }
    ];
    ctx2.pk = { dataset: { away: 'George Staines', home: 'Loai Abushaar' } };
    const expr = line.replace(/^const /, '').replace(/;$/, '').replace(/\{\{/g, '{').replace(/\}\}/g, '}');  // raw source carries Python-template doubled braces
    vm.runInContext('var ' + expr + ';', ctx2);  // var binds to the vm context; const/let stay script-scoped
    check(`${B}: away resolves to Staines`, ctx2.aw && ctx2.aw.athlete.displayName, 'George Staines');
    check(`${B}: home resolves to Abushaar`, ctx2.hm && ctx2.hm.athlete.displayName, 'Loai Abushaar');
    check(`${B}: winner flag maps away (home-side pick loses)`, (ctx2.hm.winner===true?'h':(ctx2.aw.winner===true?'a':'')), 'a');
    check(`${B}: unresolved names stay null (fail-closed, no paint)`, (() => {
      const c3 = vm.createContext({});
      c3.cs = ctx2.cs; c3.pk = { dataset: { away: 'Nobody', home: 'No One' } };
      vm.runInContext('var ' + expr + ';', c3);
      return !c3.aw && !c3.hm;
    })(), true);
}
console.log(failures ? 'FAILURES: ' + failures : 'ALL CHECKS PASS');
process.exit(failures ? 1 : 0);
