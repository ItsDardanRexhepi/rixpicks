#!/usr/bin/env node
/* Nav record figure wrap fixture (Oct 1 sweep, LS-20).
   At 320px the header record broke at the hyphen ('Record 21-' / '11'): the figures in the nav
   record chip (<b> around W-L, W/L % and units) had white-space normal. Every rule in
   scripts/index_v2.css (the CSS the builder inlines) that styles 'nav.rpnav .rec b' must leave
   it nowrap, and no later rule may turn wrapping back on.
   Run: node scripts/test_nav_record_nowrap.js */
'use strict';
const fs = require('fs'), path = require('path');
const css = fs.readFileSync(process.argv[2] || path.join(__dirname, 'index_v2.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');

let failures = 0;
function check(label, cond, extra) {
  if (!cond) failures++;
  console.log((cond ? 'OK   ' : 'FAIL ') + label + (cond || extra === undefined ? '' : '  [' + extra + ']'));
}
// flatten @media blocks: collect every selector{decls} pair in source order
const rules = [];
const re = /([^{}@]+)\{([^{}]*)\}/g; let m;
while ((m = re.exec(css))) rules.push({ sel: m[1].trim(), decl: m[2] });
const hits = rules.filter(r => r.sel.split(',').some(s => /(^|\s)(nav\.rpnav|\.rpnav|#rpNavRec|button\.rec)[^,]*\s(\.rec\s+)?b$/.test(s.trim()) && /\.rec|#rpNavRec/.test(s)));
check('a rule styles the nav record figures', hits.length > 0, hits.length);
let ws = null;
for (const r of hits) { const w = /white-space\s*:\s*([a-z-]+)/i.exec(r.decl); if (w) ws = w[1]; }
check('nav record figures are white-space:nowrap', ws === 'nowrap', ws);
const later = rules.filter(r => /#rpNavRec\s+b|\.rec\s+b/.test(r.sel) && /white-space\s*:\s*(normal|pre-wrap|break-spaces)/i.test(r.decl));
check('no rule turns wrapping back on for them', later.length === 0, later.map(r => r.sel).join(' | '));

if (failures) { console.error(failures + ' FAILURES'); process.exit(1); }
console.log('nav record nowrap fixture: ALL PASS');
