// The photo row's rules on the page, as shipped: a photo the person sent is a bare picture row with no bubble, rounded,
// no padding or border, and sized so it can never widen a 390 px phone screen. The stylesheet is read as text (no
// layout engine here); the live check on a phone and a desktop is in the handoff notes. Run: node scripts/test_trinity_photo_row.js
const fs = require('fs');
const path = require('path');
const css = fs.readFileSync(path.join(__dirname, '..', 'trinity', 'trinity.css'), 'utf8');
const js = fs.readFileSync(path.join(__dirname, '..', 'trinity', 'trinity.js'), 'utf8');
let fails = 0;
const check = (c, l) => { console.log((c ? 'OK   ' : 'FAIL ') + l); if (!c) fails++; };
const rule = (sel) => { const m = css.match(new RegExp(sel.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\{([^}]*)\\}')); return m ? m[1] : ''; };
const pic = rule('.tr-row.tr-pic .tr-thumb');
check(pic !== '', 'the photo row has its own rule');
check(/max-width:\s*min\(\s*240px\s*,\s*72%\s*\)/.test(pic), 'the picture is at most 240 px and at most 72% of the row, so a 390 px phone never scrolls sideways');
check(/\bmargin:\s*0\b/.test(pic) && /\bpadding:\s*0\b/.test(pic) && /\bborder:\s*0\b/.test(pic), 'no margin, no padding, no border round it');
check(/background:\s*transparent/.test(pic) && /border-radius:\s*14px/.test(pic), 'nothing behind it, and it is rounded');
check(/\.tr-row\.tr-pic\{[^}]*justify-content:\s*flex-end/.test(css), 'on the right, as the person\'s own rows are');
check(/el\('div', 'tr-row me tr-pic'\)/.test(js) && /el\('img', 'tr-thumb'\)/.test(js), 'the row is built as a div holding one img');
check(!/tr-pic[^}]*tr-bub/.test(js.slice(js.indexOf('function photoRow'), js.indexOf('function photoRow') + 600)), 'and no bubble is ever put in it');
check(/row\('her', PENDING, null, 'tr-pending', true\)/.test(js.slice(js.indexOf('function sendPhoto'))), 'while the photo goes, the dots');
check(/THUMB_MAX\s*=\s*60000/.test(js) && /thumb\.length <= THUMB_MAX/.test(js), 'the kept copy is capped');
console.log(fails ? `${fails} FAILED` : 'ALL PHOTO ROW CHECKS PASS');
process.exit(fails ? 1 : 0);
