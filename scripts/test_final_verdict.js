#!/usr/bin/env node
/* CP-03 fixture (Oct 1 card): the page's final verdict graded every pick as a straight-up winner
   keyed on away/home. The losing Under 38.5 (PIT 24 @ CLE 27 = 51) painted W, a 2-point Aces win
   on -4.5 painted W, and the Under/Aces/Devils parlay announced "Combo cashed" although it lost.
   Totals grade the combined score against the line, spreads the pick-side margin plus the line,
   an exact landing is a push, a market the page cannot grade shows the final with no verdict,
   and a pushed leg never counts as home in the combo status.
   Functions are extracted from the real builder template (both twins).
   Run: node scripts/test_final_verdict.js [builder.py ...] */
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm');
let failures = 0;
function check(label, got, want) {
  const ok = got === want;
  console.log((ok ? 'OK   ' : 'FAIL ') + label + (ok ? '' : ` (got ${JSON.stringify(got)}, want ${JSON.stringify(want)})`));
  if (!ok) failures++;
}
const builders = process.argv.slice(2).length ? process.argv.slice(2) : ['build_gh_page_v2.py', '_build_nocanon_v2.py'].map(b => path.join(__dirname, b));
function fn(src, name) {
  const i = src.indexOf('function ' + name + '(');
  if (i < 0) return '';
  let d = 0;
  for (let k = src.indexOf('{', i); k < src.length; k++) {
    if (src[k] === '{') d++;
    else if (src[k] === '}') { d--; if (!d) return src.slice(i, k + 1); }
  }
  return '';
}
for (const B of builders) {
  const tag = path.basename(B);
  const src = fs.readFileSync(B, 'utf8').replace(/\{\{/g, '{').replace(/\}\}/g, '}');  // page template is a Python f-string
  const code = ['rpGrade', 'rpLsRender', 'rpCxLive'].map(n => fn(src, n)).join('\n');
  check(`${tag}: rpLsRender + rpCxLive extractable`, /function rpLsRender\(/.test(code) && /function rpCxLive\(/.test(code), true);
  const ctx = vm.createContext({});
  try { vm.runInContext(code, ctx); } catch (e) { check(`${tag}: verdict code runs`, e.message, ''); continue; }
  function pick(ds) { const el = { className: '', innerHTML: '' }; return { dataset: ds, querySelector: () => el, el }; }
  function verdict(ds, g) { const p = pick(ds); ctx.rpLsRender(p, Object.assign({ state: 'post', st: 'Final' }, g)); return p.el; }
  const PITCLE = { a: 'PIT', h: 'CLE', as: 24, hs: 27, w: 'h' };   // ESPN also flags the winner on score sports
  const INDLV = { a: 'IND', h: 'LV', as: 83, hs: 94, w: 'h' };
  const PHINJ = { a: 'PHI', h: 'NJ', as: 2, hs: 3, w: 'h' };
  // totals
  let el = verdict({ side: 'under', market: 'total', line: '38.5' }, PITCLE);
  check(`${tag}: Under 38.5 at 24-27 (51) is a loss`, el.className, 'ls on lost');
  check(`${tag}: Under 38.5 verdict text`, el.innerHTML, '<b>L</b> &middot; PIT 24 - CLE 27 Final');
  check(`${tag}: Over 38.5 at 24-27 is a win`, verdict({ side: 'over', market: 'total', line: '38.5' }, PITCLE).className, 'ls on won');
  check(`${tag}: Under 52.5 at 24-27 is a win`, verdict({ side: 'under', market: 'total', line: '52.5' }, PITCLE).className, 'ls on won');
  el = verdict({ side: 'over', market: 'total', line: '51' }, PITCLE);
  check(`${tag}: total landing exactly on 51 is a push`, el.className + '|' + el.innerHTML.slice(0, 8), 'ls on push|<b>P</b>');
  // spreads
  check(`${tag}: Aces -4.5 winning 94-83 covers`, verdict({ side: 'home', market: 'spread', line: '-4.5' }, INDLV).className, 'ls on won');
  check(`${tag}: Aces -4.5 winning by 2 (92-94) does not cover`, verdict({ side: 'home', market: 'spread', line: '-4.5' }, { a: 'IND', h: 'LV', as: 92, hs: 94, w: 'h' }).className, 'ls on lost');
  check(`${tag}: Fever +4.5 losing by 2 covers`, verdict({ side: 'away', market: 'spread', line: '4.5' }, { a: 'IND', h: 'LV', as: 92, hs: 94, w: 'h' }).className, 'ls on won');
  check(`${tag}: Aces -2 winning by 2 pushes`, verdict({ side: 'home', market: 'spread', line: '-2' }, { a: 'IND', h: 'LV', as: 92, hs: 94, w: 'h' }).className, 'ls on push');
  // moneyline unchanged
  check(`${tag}: Devils ML winning 3-2 is a win`, verdict({ side: 'home', market: 'ml' }, PHINJ).className, 'ls on won');
  check(`${tag}: away ML losing by score (no flag) stays a loss`, verdict({ side: 'away' }, { a: 'PHI', h: 'ATL', as: 3, hs: 5 }).className, 'ls on lost');
  // no gradable market
  el = verdict({ side: 'over', market: 'prop' }, PITCLE);
  check(`${tag}: prop pick shows the final with no W/L`, el.className + '|' + el.innerHTML, 'ls on fin|PIT 24 - CLE 27 Final');
  check(`${tag}: spread without a line shows no verdict`, verdict({ side: 'home', market: 'spread' }, INDLV).className, 'ls on fin');

  // combo status over the real Oct 1 parlay legs (Under 38.5 + Aces -4.5 + Devils ML)
  function combo(legSpecs) {
    const out = { innerHTML: '', textContent: '', style: { display: '' } };
    const legs = legSpecs.map(([ds, g]) => { const p = pick(ds); if (g) ctx.rpLsRender(p, Object.assign({ state: 'post', st: 'Final' }, g)); return p; });
    const els = legs.map(p => ({ querySelector: () => ({ classList: { contains: c => p.el.className.split(' ').includes(c) } }) }));
    ctx.document = { querySelectorAll: () => els, getElementById: () => out };
    ctx.rpCxLive();
    return out.innerHTML || out.textContent;
  }
  const UNDER = { side: 'under', market: 'total', line: '38.5' }, ACES = { side: 'home', market: 'spread', line: '-4.5' }, DEVILS = { side: 'home', market: 'ml' };
  check(`${tag}: Oct 1 parlay (losing Under) is dead, never cashed`, /Combo dead/.test(combo([[UNDER, PITCLE], [ACES, INDLV], [DEVILS, PHINJ]])), true);
  check(`${tag}: all legs home is cashed`, /Combo cashed<\/span> - all 3 legs home/.test(combo([[{ side: 'over', market: 'total', line: '38.5' }, PITCLE], [ACES, INDLV], [DEVILS, PHINJ]])), true);
  const withPush = combo([[{ side: 'over', market: 'total', line: '51' }, PITCLE], [ACES, INDLV], [DEVILS, PHINJ]]);
  check(`${tag}: a pushed leg is not counted home`, /Combo cashed<\/span> - 2 of 3 legs home, 1 push/.test(withPush), true);
  check(`${tag}: every leg pushed reads as a push`, /Combo push/.test(combo([[{ side: 'over', market: 'total', line: '51' }, PITCLE]])), true);
  const withFin = combo([[{ side: 'over', market: 'prop' }, PITCLE], [ACES, INDLV], [DEVILS, null]]);
  check(`${tag}: an ungraded final leg never lets the combo read cashed`, !/cashed/.test(withFin) && /final, not graded here/.test(withFin), true);
}
console.log(failures ? 'FAILURES: ' + failures : 'ALL CHECKS PASS');
process.exit(failures ? 1 : 0);
