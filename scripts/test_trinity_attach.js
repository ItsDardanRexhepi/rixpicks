// A photo picked in Trinity's chat waits until it is sent, so a message can be written with it (owner, 2026-10-13:
// "make it so text can be written before the photo is sent 'cause right now it sends as soon as its attached").
// Run: node scripts/test_trinity_attach.js
const fs = require('fs'); const path = require('path');
const js = fs.readFileSync(path.join(__dirname, '..', 'trinity', 'trinity.js'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, '..', 'trinity', 'panel.html'), 'utf8');
const css = fs.readFileSync(path.join(__dirname, '..', 'trinity', 'trinity.css'), 'utf8');
let fails = 0; const check = (c, l) => { console.log((c ? 'OK   ' : 'FAIL ') + l); if (!c) fails++; };
const onChange = js.slice(js.indexOf("pfile.addEventListener('change'"), js.indexOf("pfile.addEventListener('change'") + 200);
check(/attach\(f\)/.test(onChange) && !/sendPhoto\(f\)/.test(onChange), 'picking a photo attaches it and does not send it');
check(/form\.addEventListener\('submit', function \(e\) \{ e\.preventDefault\(\); go\(\); \}\)/.test(js), 'Ask sends through go()');
check(/e\.keyCode !== 229\) \{ e\.preventDefault\(\); go\(\); \}/.test(js), 'Enter sends through go()');
const goFn = js.slice(js.indexOf('function go()'), js.indexOf('function go()') + 300);
check(/attached && signedIn\(\)/.test(goFn) && /sendPhoto\(f\)/.test(goFn) && /ask\(/.test(goFn), 'go() sends the held photo with the box as its caption, else asks');
check(/caption = \(input && input\.value/.test(js), 'the caption is what was typed');
check(/id="trAttach"[^>]*hidden/.test(html) && /id="trAttachX"/.test(html), 'the waiting photo has its own tray and a remove button, hidden until a photo is picked');
check(/\.tr-attach img\{[^}]*max-width:\s*84px/.test(css), 'the preview is small enough for a 390 px phone');
check(/function resetToIntro\(\) \{\n\s*if \(typeof attach === 'function'\) attach\(null\);/.test(js), 'signing out drops a waiting photo');
console.log(fails ? `${fails} FAILED` : 'ALL ATTACH CHECKS PASS'); process.exit(fails ? 1 : 0);
