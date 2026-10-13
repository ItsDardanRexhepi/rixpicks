#!/usr/bin/env node
/* Record on every tab + the notice under the nav (owner, Oct 13).
   - The overall record in the nav (#rpNavRec and its popover #rpRecPop) used to vanish on the
     Picks from Wooder Ice tab: scripts/index_v2.css carried body.tab-wooder .rpnav .rec{display:none}
     and body.tab-wooder .rpRecPop{display:none}. No body.tab-* rule in any stylesheet the page
     inlines (index_v2.css, trinity/trinity.css, the builder's own blocks in the built index.html)
     may hide the nav, the record button or its popover on any tab.
   - A notice sits right under the nav tab bar on every tab: one element, outside every tab panel
     and every .home-only block, its words the builder constant RP_SYSTEM_NOTICE (the same in both
     builder twins), with no digit in it and no description of the system; styled in normal flow
     (never sticky or fixed, so it cannot cover the nav or the record button) and never hidden by
     a body.tab-* rule.
   Run: node scripts/test_record_every_tab.js [index.html]   (default: the built ../index.html) */
'use strict';
const fs = require('fs'), path = require('path');
const ROOT = path.join(__dirname, '..');
const read = p => fs.readFileSync(p, 'utf8');
const strip = css => css.replace(/\/\*[\s\S]*?\*\//g, '');
let failures = 0;
function check(label, cond, extra) {
  if (!cond) failures++;
  console.log((cond ? 'OK   ' : 'FAIL ') + label + (cond || extra === undefined ? '' : '  [' + extra + ']'));
}
function rules(css) {  // flatten @media blocks: every selector{decls} in source order
  const out = []; const re = /([^{}@]+)\{([^{}]*)\}/g; let m;
  while ((m = re.exec(strip(css)))) out.push({ sel: m[1].trim(), decl: m[2] });
  return out;
}
const page = read(process.argv[2] ? path.resolve(process.argv[2]) : path.join(ROOT, 'index.html'));
const sheets = {
  'scripts/index_v2.css': read(path.join(ROOT, 'scripts/index_v2.css')),
  'trinity/trinity.css': fs.existsSync(path.join(ROOT, 'trinity/trinity.css')) ? read(path.join(ROOT, 'trinity/trinity.css')) : '',
  'index.html <style>': (page.match(/<style[^>]*>([\s\S]*?)<\/style>/g) || []).map(s => s.replace(/<\/?style[^>]*>/g, '')).join('\n'),
};
const REC = /(^|[\s>+~])(nav\.rpnav|\.rpnav|#rpNavRec|button\.rec|\.rec|#rpRecPop|\.rpRecPop|\.recpop)(?![\w-])/;
const HIDE = /display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?![.\d])/i;
for (const [name, css] of Object.entries(sheets)) {
  if (!css) continue;
  const bad = rules(css).filter(r => HIDE.test(r.decl) && r.sel.split(',').some(s => /(^|\s)body\.tab-[a-z0-9]+/.test(s.trim()) && REC.test(s.trim()) && !/\.rpnotice/.test(s)));
  check(name + ': no body.tab-* rule hides the nav record button or its popover', bad.length === 0, bad.map(r => r.sel).join(' | '));
  const badNotice = rules(css).filter(r => HIDE.test(r.decl) && /\.rpnotice|#rpSystemNotice/.test(r.sel));
  check(name + ': no rule hides the notice', badNotice.length === 0, badNotice.map(r => r.sel).join(' | '));
}
check('the page is built with a nav record button', /<button[^>]*id="rpNavRec"/.test(page));
check('the page is built with the record popover', /id="rpRecPop"/.test(page));

// the notice: builder constant, same words in both twins, no digits, once on the page right under the nav
const twins = ['scripts/build_gh_page_v2.py', 'scripts/_build_nocanon_v2.py'].map(f => read(path.join(ROOT, f)));
const words = twins.map(src => (src.match(/^RP_SYSTEM_NOTICE\s*=\s*'([^'\n]*)'/m) || [])[1]);
check('RP_SYSTEM_NOTICE is a constant in the builder', !!words[0] && words[0].length > 20, words[0]);
check('both builder twins carry the same words', words[0] === words[1], words[1]);
const NOTICE = words[0] || '';
check('the words carry no number', !/\d/.test(NOTICE), NOTICE);
check('the words describe no system internals', !/model|edge|threshold|probab|algorithm|%|score|sharp|close|line value|clv/i.test(NOTICE), NOTICE);
const esc = NOTICE.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const noticeRe = /<div class="rpnotice" id="rpSystemNotice" role="note">([^<]*)<\/div>/g;
const found = [...page.matchAll(noticeRe)];
check('the notice renders exactly once on the page', found.length === 1, found.length);
check('the notice renders the builder words', found.length === 1 && found[0][1] === esc, found.length === 1 ? found[0][1] : '');
const navEnd = page.indexOf('</nav>'), noticeAt = found.length === 1 ? found[0].index : -1, layoutAt = page.indexOf('<div class="layout">');
check('it sits right under the nav tab bar, before the page body', navEnd > 0 && noticeAt > navEnd && layoutAt > noticeAt && page.slice(navEnd + 6, noticeAt).trim() === '',
      JSON.stringify(page.slice(navEnd, navEnd + 60)));
check('it belongs to no tab panel and no Home-only block', !/<section id="st-|class="[^"]*\bhome-only\b/.test(page.slice(navEnd, noticeAt + 1)));
const noticeRules = rules(sheets['scripts/index_v2.css']).filter(r => r.sel.split(',').some(s => s.trim() === '.rpnotice'));
check('.rpnotice is styled in index_v2.css', noticeRules.length > 0);
check('.rpnotice is in normal flow (never sticky or fixed, so it cannot cover the nav or the record)',
      noticeRules.every(r => !/position\s*:\s*(sticky|fixed|absolute)/.test(r.decl)));
check('.rpnotice uses the theme tokens (dark/light follow the site)', noticeRules.some(r => /var\(--mut\)/.test(r.decl) && /var\(--line\)/.test(r.decl)));

if (failures) { console.error(failures + ' FAILURES'); process.exit(1); }
console.log('record-every-tab + notice fixture: ALL PASS');
