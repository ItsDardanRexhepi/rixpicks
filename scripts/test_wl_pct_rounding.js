#!/usr/bin/env node
/* W/L % rounding parity fixture (Oct 1 sweep, LS-17 / DI-13 / OS-12).
   The builder baked the nav W/L % with Python '%.2f' (21-11 = 65.625 -> '65.62%'); the page's
   navRec() then rewrote it with toFixed(2) -> '65.63%', so the figure changed on load. One rule
   everywhere: the builder now bakes with _pct_half_up (exact integer arithmetic, an exact tie
   rounds up), and the page must print the digits the builder bakes for every record.
   Extracts the real rpPct/navRec from scripts/index_v2.js (vm sandbox) and the real _pct_half_up
   from scripts/build_gh_page_v2.py, and compares them over every W-L record up to 120-120.
   Run: node scripts/test_wl_pct_rounding.js [index_v2.js] [build_gh_page_v2.py] */
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm'), { execFileSync } = require('child_process');
const src = fs.readFileSync(process.argv[2] || path.join(__dirname, 'index_v2.js'), 'utf8');
const builder = process.argv[3] || path.join(__dirname, 'build_gh_page_v2.py');

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

// the builder's own formatter, every record up to 120-120 at 1 and 2 dp
const N = 120;
const py = JSON.parse(execFileSync('python3', ['-c', [
  'import ast, json, sys, warnings',
  'warnings.simplefilter("ignore")',
  'src = open(sys.argv[1]).read()',
  'ns = {}',
  'for node in ast.parse(src).body:',
  '    if isinstance(node, ast.FunctionDef) and node.name == "_pct_half_up":',
  '        exec(compile(ast.Module(body=[node], type_ignores=[]), sys.argv[1], "exec"), ns)',
  'fn = ns["_pct_half_up"]',
  `print(json.dumps({"%d-%d" % (w, l): [fn(w, l, 1), fn(w, l, 2), "%.1f" % (100.0*w/(w+l)), "%.2f" % (100.0*w/(w+l))] for w in range(${N}+1) for l in range(${N}+1) if w + l}))`,
].join('\n'), builder], { encoding: 'utf8', maxBuffer: 64 << 20 }));

// navRec as the page runs it: #rpRec carries the canonical counts, #rpNavPct shows the baked percent
const els = {
  rpRec: { dataset: { bw: '21', bl: '11' } }, rpUnits: { dataset: { bu: '+4.76' } },
  rpNavRecW: { textContent: '21' }, rpNavRecL: { textContent: '11' }, rpNavU: { textContent: '+4.76u' },
  rpNavPct: { textContent: py['21-11'][1] + '%' },   // what build_gh_page_v2.py bakes
};
const ctx = vm.createContext({ Math, Number, String, parseInt, parseFloat, $: id => els[id] || null });
vm.runInContext(extract('rpPct') + '\n' + extract('navRec'), ctx);
check('the builder bakes 21-11 as 65.63%', py['21-11'][1], '65.63');
try { ctx.navRec(); } catch (e) { failures++; console.log('FAIL navRec runs: ' + e.message); }
check('21-11 nav W/L keeps the baked 65.63% after load', els.rpNavPct.textContent, '65.63%');
check('nav W/L-record mirror unchanged', [els.rpNavRecW.textContent, els.rpNavRecL.textContent], ['21', '11']);

let bad1 = [], bad2 = [], ties = 0;
for (const k of Object.keys(py)) {
  const [w, l] = k.split('-').map(Number);
  if (py[k][0] !== py[k][2] || py[k][1] !== py[k][3]) ties++;
  let g1, g2;
  try { g1 = ctx.rpPct(w, l, 1); g2 = ctx.rpPct(w, l, 2); } catch (e) { g1 = g2 = 'THROW'; }
  if (g1 !== py[k][0]) bad1.push(k + ' ' + g1 + '!=' + py[k][0]);
  if (g2 !== py[k][1]) bad2.push(k + ' ' + g2 + '!=' + py[k][1]);
}
check("grid holds exact-tie records where Python '%.Nf' rounds to even", ties > 0, true);
check(`rpPct(w,l,2) == builder _pct_half_up for every record to ${N}-${N}`, bad2.slice(0, 5), []);
check(`rpPct(w,l,1) == builder _pct_half_up for every record to ${N}-${N}`, bad1.slice(0, 5), []);
for (const [w, l, dp, want] of [[1, 15, 1, '6.3'], [21, 11, 1, '65.6'], [1, 0, 2, '100.00'], [0, 1, 2, '0.00'], [0, 0, 2, '']]) {
  let g; try { g = ctx.rpPct(w, l, dp); } catch (e) { g = 'THROW'; }
  check(`rpPct(${w},${l},${dp})`, g, want);
}
check('rpPct exported for the record popover script', /window\.rpPct=rpPct;/.test(src), true);

if (failures) { console.error(failures + ' FAILURES'); process.exit(1); }
console.log('W/L pct rounding parity fixture: ALL PASS');
