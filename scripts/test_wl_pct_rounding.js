#!/usr/bin/env node
/* W/L % rounding parity fixture (Oct 1 sweep, LS-17 / DI-13).
   The builder bakes the nav W/L % with Python '%.2f' (21-11 = 65.625 -> '65.62%'); the page's
   navRec() then rewrote it with toFixed(2) -> '65.63%', so the figure changed on load. Python
   rounds an exact binary tie to even, toFixed rounds it up. One rule everywhere: the page must
   print the digits the builder bakes for every record.
   Extracts the real rpFixed/navRec from scripts/index_v2.js (vm sandbox) and compares against
   python3 '%.1f' / '%.2f' over every W-L record up to 120-120.
   Run: node scripts/test_wl_pct_rounding.js */
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm'), { execFileSync } = require('child_process');
const src = fs.readFileSync(process.argv[2] || path.join(__dirname, 'index_v2.js'), 'utf8');

let failures = 0;
function check(label, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'OK   ' : 'FAIL ') + label + (ok ? '' : `  [want ${JSON.stringify(want)} got ${JSON.stringify(got)}]`));
}
function extract(name) {
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) { failures++; console.log('FAIL ' + name + ' present in index_v2.js'); return ''; }
  let depth = 0;
  for (let i = start; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) return src.slice(start, i + 1); }
  }
  failures++; console.log('FAIL ' + name + ' balanced'); return '';
}

// navRec as the page runs it: #rpRec carries the canonical counts, #rpNavPct shows the percent
const els = {
  rpRec: { dataset: { bw: '21', bl: '11' } }, rpUnits: { dataset: { bu: '+4.76' } },
  rpNavRecW: { textContent: '21' }, rpNavRecL: { textContent: '11' }, rpNavU: { textContent: '+4.76u' },
  rpNavPct: { textContent: '65.62%' },   // what build_gh_page_v2.py bakes ('%.2f' % 65.625)
};
const ctx = vm.createContext({ Math, Number, String, parseInt, parseFloat, $: id => els[id] || null });
vm.runInContext(extract('rpFixed') + '\n' + extract('navRec'), ctx);
try { ctx.navRec(); } catch (e) { failures++; console.log('FAIL navRec runs: ' + e.message); }
check('21-11 nav W/L keeps the baked 65.62% after load', els.rpNavPct.textContent, '65.62%');
check('nav W/L-record mirror unchanged', [els.rpNavRecW.textContent, els.rpNavRecL.textContent], ['21', '11']);

// full parity with the builder's Python formatting, same arithmetic (100.0*w/(w+l))
const N = 120;
const py = JSON.parse(execFileSync('python3', ['-c',
  `import json\nN=${N}\nprint(json.dumps({'%d-%d'%(w,l):['%.1f'%(100.0*w/(w+l)),'%.2f'%(100.0*w/(w+l))] for w in range(N+1) for l in range(N+1) if w+l}))`],
  { encoding: 'utf8', maxBuffer: 64 << 20 }));
let bad1 = [], bad2 = [], ties = 0;
for (const k of Object.keys(py)) {
  const [w, l] = k.split('-').map(Number), x = 100 * w / (w + l);
  if (x.toFixed(2) !== py[k][1] || x.toFixed(1) !== py[k][0]) ties++;
  let g1, g2;
  try { g1 = ctx.rpFixed(x, 1); g2 = ctx.rpFixed(x, 2); } catch (e) { g1 = g2 = 'THROW'; }
  if (g1 !== py[k][0]) bad1.push(k + ' ' + g1 + '!=' + py[k][0]);
  if (g2 !== py[k][1]) bad2.push(k + ' ' + g2 + '!=' + py[k][1]);
}
check('grid holds exact-tie records where toFixed and Python differ', ties > 0, true);
check(`rpFixed(x,2) == Python '%.2f' for every record to ${N}-${N}`, bad2.slice(0, 5), []);
check(`rpFixed(x,1) == Python '%.1f' for every record to ${N}-${N}`, bad1.slice(0, 5), []);
// doubles off the tie: toFixed already agrees with Python (0.025 is stored just above the tie)
for (const [x, dp, want] of [[0.025, 2, '0.03'], [2.675, 2, '2.67'], [1.005, 2, '1.00'], [0.125, 2, '0.12'],
  [0.375, 2, '0.38'], [2.5, 0, '2'], [3.5, 0, '4'], [12.25, 1, '12.2'], [12.75, 1, '12.8'], [100, 2, '100.00'], [0, 2, '0.00']]) {
  let g; try { g = ctx.rpFixed(x, dp); } catch (e) { g = 'THROW'; }
  check(`rpFixed(${x},${dp}) == Python '%.${dp}f'`, g, want);
}
check('rpFixed exported for the record popover script', /window\.rpFixed=rpFixed;/.test(src), true);

if (failures) { console.error(failures + ' FAILURES'); process.exit(1); }
console.log('W/L pct rounding parity fixture: ALL PASS');
