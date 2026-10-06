#!/usr/bin/env node
/* CP-03 fixture (Oct 1 card): the page's final verdict graded every pick as a straight-up winner
   keyed on away/home. The losing Under 38.5 (PIT 24 @ CLE 27 = 51) painted W, a 2-point Aces win
   on -4.5 painted W, and the Under/Aces/Devils parlay announced "Combo cashed" although it lost.
   Totals grade the combined score against the line, spreads the pick-side margin plus the line,
   an exact landing is a push, a market the page cannot grade shows the final with no verdict,
   and a pushed leg never counts as home in the combo status.
   Away spreads (Oct 2 review): the pipeline stores a spread pick's line as the HOME spread
   (record_final.score_result, finals_watch, st_card_candidates.adapt_alt). The builder's own
   _pick_line turns a manifest pick into the data-line the page grades with, and the page's verdict
   must equal record_final.score_result on the same final - 'Lynx +4' (line -4) on 85-84 is W, not L,
   and an away favourite 'Lynx -3' (line +3) winning by 2 is L, not W.
   Oct 5 Flyers +1.5 regression: manifest line -1.5 is Tampa Bay's HOME spread, not
   the Flyers' selected-side spread. A sign-only manifest edit would change the pick.
   The actual page conversion and all four graders must agree: a one-goal Flyers loss
   still covers; a two-goal loss does not. Hypothetical finals below are fixtures, not scores.
   Functions are extracted from the real builder template (both twins).
   Run: node scripts/test_final_verdict.js [builder.py ...] */
'use strict';
const fs = require('fs'), path = require('path'), vm = require('vm'), { execFileSync } = require('child_process');
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

  // away spreads: the builder's emitted data-line (from build_manifest-shape picks) vs the record's grade
  const PIPE = [
    ['Lynx +4 (away cover, home line -4)', { name: 'Lynx +4', market_class: 'spread', side: 'away', line: -4 }],
    ['Lynx -3 (away favourite, home line +3)', { name: 'Lynx -3', market_class: 'spread', side: 'away', line: 3 }],
    ['Liberty -4 (home, home line -4)', { name: 'Liberty -4', market_class: 'spread', side: 'home', line: -4 }],
    ['Fever +4.5 legacy name-only away spread', { name: 'Fever +4.5', market: 'spread', side: 'away' }],
    ['Lynx PK (away pick\'em, home line 0)', { name: 'Lynx PK', market_class: 'spread', side: 'away', line: 0 }],
    ['Flyers +1.5 (away cover, home line -1.5)', { name: 'Flyers +1.5', market_class: 'spread', side: 'away', line: -1.5 }]];
  const FINALS = [[85, 84], [82, 84], [80, 84], [70, 84], [86, 84], [87, 84], [81, 84], [3, 2], [2, 3], [1, 3], [0, 0]];
  const py = [
    'import ast, importlib.util, json, os, re, sys, warnings',
    'warnings.simplefilter("ignore")  # the builder source carries pre-existing invalid escapes inside JS templates',
    'B, SD, picks, finals = sys.argv[1], sys.argv[2], json.loads(sys.argv[3]), json.loads(sys.argv[4])',
    'ns = {"re": re}',
    'for node in ast.parse(open(B).read()).body:',
    '    if isinstance(node, ast.FunctionDef) and node.name in ("_pick_mclass", "_pick_line"):',
    '        exec(compile(ast.Module(body=[node], type_ignores=[]), B, "exec"), ns)',
    'spec = importlib.util.spec_from_file_location("rf", SD + "/record_final.py"); rf = importlib.util.module_from_spec(spec); spec.loader.exec_module(rf)',
    'sys.path.insert(0, os.path.dirname(SD)); os.environ["RIX_UNIT_DOLLARS"] = "1"',
    'spec = importlib.util.spec_from_file_location("fw", SD + "/finals_watch.py"); fw = importlib.util.module_from_spec(spec); spec.loader.exec_module(fw)',
    '# Only external price-ledger reads are stubbed; real grade(), including sign math, runs.',
    'fw.fill_leak.card_price = lambda p: (58, {"card_american": -138}, 1)',
    'fw.fill_leak.fill_divergence = lambda p: []',
    'out = []',
    'for p in picks:',
    '    ln = ns["_pick_line"](p)',
    '    hl = p.get("line") if p.get("line") is not None else (-ln if p["side"] == "away" else ln)',
    '    fixture = dict(p, market_class="spread", line=hl, odds="-138", units="5u", kalshi={"cents": 58})',
    '    watch = [fw.grade(fixture, {"away_score": a, "home_score": h})[0] for a, h in finals]',
    '    out.append({"line": ("%g" % ln) if ln is not None else None, "watch": [{"PUSH": "P"}.get(v, v) for v in watch],',
    '                "record": [{"WON": "W", "LOST": "L", "PUSH": "P"}.get(rf.score_result("spread", p["side"], hl, a, h)) for a, h in finals]})',
    'print(json.dumps(out))'].join('\n');
  let emitted = null;
  try { emitted = JSON.parse(execFileSync('python3', ['-c', py, B, __dirname, JSON.stringify(PIPE.map(x => x[1])), JSON.stringify(FINALS)], { encoding: 'utf8' })); }
  catch (e) { check(`${tag}: builder _pick_line + record_final.score_result load`, String(e.message).slice(0, 200), ''); }
  const tpl = fs.readFileSync(path.join(path.dirname(B), 'game_page_template.html'), 'utf8');
  const gctx = vm.createContext({});
  vm.runInContext(fn(tpl, 'rpGameGrade'), gctx);
  if (emitted) {
    check(`${tag}: Lynx +4 from the manifest emits data-line 4 (its own side's spread)`, emitted[0].line, '4');
    check(`${tag}: Lynx -3 from the manifest emits data-line -3`, emitted[1].line, '-3');
    check(`${tag}: an away pick'em emits data-line 0, never -0`, emitted[4].line, '0');
    check(`${tag}: Flyers +1.5 emits selected-side data-line 1.5`, emitted[5].line, '1.5');
    check(`${tag}: Flyers +1.5: win, one-goal loss, two-goal loss, tied score`, emitted[5].record.slice(-4).join(''), 'WWLW');
    check(`${tag}: Flyers half-goal spread cannot push on integer-score fixtures`, emitted[5].record.includes('P'), false);
    check(`${tag}: record grades Lynx +4 W, W, P, L on 85-84, 82-84, 80-84, 70-84`, emitted[0].record.slice(0, 4).join(''), 'WWPL');
    PIPE.forEach(([label, p], i) => {
      const ds = { side: p.side, market: 'spread', line: emitted[i].line };
      const home = FINALS.map(([a, h]) => { const c = verdict(ds, { a: 'MIN', h: 'NY', as: a, hs: h, w: a > h ? 'a' : 'h' }).className; return { 'ls on won': 'W', 'ls on lost': 'L', 'ls on push': 'P' }[c] || c; });
      const game = FINALS.map(([a, h]) => gctx.rpGameGrade({ dataset: ds }, a, h));
      check(`${tag}: ${label}: finals watcher equals the record on every final`, emitted[i].watch.join(','), emitted[i].record.join(','));
      check(`${tag}: ${label}: Home row verdict equals the record on every final`, home.join(','), emitted[i].record.join(','));
      check(`${tag}: ${label}: game page verdict equals the record on every final`, game.join(','), emitted[i].record.join(','));
    });
    // the 2-leg combo: Lynx +4 on 85-84 is a leg home (the record grades it WON), never "Combo dead"
    const LYNX = { side: 'away', market: 'spread', line: emitted[0].line };
    const lynxCombo = combo([[LYNX, { a: 'MIN', h: 'NY', as: 85, hs: 84, w: 'a' }], [ACES, INDLV]]);
    check(`${tag}: Lynx +4 (85-84) + Aces -4.5 combo reads cashed, not dead`, /Combo cashed/.test(lynxCombo) && !/Combo dead/.test(lynxCombo), true);
  }
}
console.log(failures ? 'FAILURES: ' + failures : 'ALL CHECKS PASS');
process.exit(failures ? 1 : 0);
