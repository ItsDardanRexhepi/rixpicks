/* The chat's instant site changes, as the page reads them (trinity/trinity.js, ovPlan and shotUrl).
   The overrides document comes from the Mac; this proves the page keeps only typed keys and checked values from it,
   so the document can never put markup, a script, a selector or a URL on the page, and that a picture is shown only
   when its own bytes are a PNG or a JPEG. Run: node scripts/test_trinity_overrides.js */
'use strict';
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync('trinity/trinity.js', 'utf8');
let bad = 0;
const check = (l, ok, d) => { if (!ok) bad++; console.log((ok ? 'OK   ' : 'FAIL ') + l + (ok ? '' : '  [' + d + ']')); };
const cut = (a, b) => { const i = src.indexOf(a), j = src.indexOf(b, i); if (i < 0 || j < 0) throw new Error('missing ' + a); return src.slice(i, j); };
const code = cut('var SHOTS =', 'function shotsKept') + cut('var OV_VARS =', 'var ovDone');
const ctx = { atob: s => Buffer.from(s, 'base64').toString('latin1') };
vm.createContext(ctx);
vm.runInContext(code + '\nthis.ovPlan = ovPlan; this.shotUrl = shotUrl;', ctx);
const id = n => ('a'.repeat(11) + n).slice(-12);
const good = { v: 1, rev: 3, items: [
  { id: id(1), k: 'var', var: '--acc', value: '#2f6fdb' },
  { id: id(2), k: 'style', target: 'tabs', prop: 'font-size', value: '16px' },
  { id: id(3), k: 'hide', section: 'news' },
  { id: id(4), k: 'text', find: 'Bet responsibly.', replace: 'Bet smart.' },
  { id: id(5), k: 'note', slot: 'wooder-top', text: 'Tickets go up by noon PT.', tone: 'banner' },
  { id: id(6), k: 'img', slot: 'home-top', alt: 'The team' },
  { id: id(7), k: 'ticket', date: '2026-10-07', card: { id: 't3a1', title: 'Kwan Hit single', matchup: 'CLE at CWS',
    legs: [{ player: 'Steven Kwan', market: 'Hit (1+)', links: [{ venue: 'KAL', cents: 55 }, { venue: 'FD', cents: 50 }] }] } },
  { id: id(8), k: 'untix', date: '2026-10-07', ticket_id: 't3', card: { id: 't3', title: 'x', legs: [] } },
], gone: [{ id: id(9), k: 'text', find: 'Old words', replace: 'New words' }] };
let p = ctx.ovPlan(good);
check('every typed change is kept', p.ops.length === 8, JSON.stringify(p.ops.map(o => o.k)));
check('a style target becomes the page\'s own selector', p.ops[1].sel === 'nav.rpnav .tab', p.ops[1].sel);
check('a sportsbook price is dropped from a ticket leg', p.ops[6].legs[0].links.length === 1, JSON.stringify(p.ops[6].legs));
check('a taken-back change is kept by its id alone, never by its words', p.gone.length === 1 && p.gone[0].id === id(9) &&
      !('find' in p.gone[0]) && !('replace' in p.gone[0]), JSON.stringify(p.gone));
const evil = { v: 1, rev: 4, items: [
  { id: id(1), k: 'var', var: '--acc', value: 'red;}body{background:url(javascript:alert(1))' },
  { id: id(2), k: 'var', var: 'background', value: '#000000' },
  { id: id(3), k: 'style', target: 'body script', prop: 'color', value: '#ffffff' },
  { id: id(4), k: 'style', target: 'tabs', prop: 'behavior', value: 'url(x.htc)' },
  { id: id(5), k: 'style', target: 'tabs', prop: 'font-size', value: '400px' },
  { id: id(6), k: 'hide', section: 'trinity' },
  { id: id(7), k: 'hide', section: '#rpNavRec' },
  { id: id(8), k: 'text', find: 'Record', replace: '<script>alert(1)</script>' },
  { id: id(9), k: 'text', find: '33-17', replace: '50-0' },
  { id: id(10), k: 'text', find: 'Picks', replace: 'More Picks' },
  { id: id(11), k: 'note', slot: 'trinity-top', text: 'hi' },
  { id: id(12), k: 'note', slot: 'footer', text: '<img src=x onerror=alert(1)>' },
  { id: id(13), k: 'img', slot: 'nowhere' },
  { id: id(14), k: 'ticket', date: '2026-10-07', card: { id: 'x"><script>', title: 'T', legs: [{ player: 'A', market: 'm' }] } },
  { id: id(15), k: 'ticket', date: '2026-10-07', card: { id: 't9', title: '<b>T</b>', legs: [{ player: 'A', market: 'm' }] } },
  { id: id(16), k: 'script', src: 'https://evil.example/x.js' },
  { id: 'not-an-id', k: 'var', var: '--acc', value: '#000000' },
  { id: id(17), k: 'ticket', date: '2026-10-07', card: { id: 't8', title: 'T', legs: [{ player: 'A', market: 'm',
    links: [{ venue: 'KAL', cents: 'javascript:1' }, { venue: 'KAL', cents: 150 }] }] } },
] };
p = ctx.ovPlan(evil);
check('nothing from a hostile document survives but the one clean ticket', p.ops.length === 1 && p.ops[0].tid === 't8' &&
      p.ops[0].legs[0].links.length === 0, JSON.stringify(p.ops));
check('a document of the wrong version is ignored', ctx.ovPlan({ v: 2, items: good.items }).ops.length === 0, 'v');
check('no document, no change', ctx.ovPlan(null).ops.length === 0 && ctx.ovPlan('x').ops.length === 0, 'null');
/* the applier writes only through textContent and setProperty: nothing that parses markup or runs code */
const ap = cut('var ovDone', 'function ovStart');
/* no wording change reaches the official card, the yesterday line, the record or the past tickets */
const keep = (src.match(/var OV_KEEP_OUT = '([^']*)'/) || [])[1] || '';
check('the card, the yesterday line, the record and the past tickets are out of reach of a wording change',
      ['#rpNavRec', '#rpRecPop', '.rphead', '.yesrec', '.pick', '#st-past', '.recpop'].every(function (x) {
        return keep.split(',').indexOf(x) !== -1; }), keep);
/* a wording change taken back is put back only on the text this page changed itself, never by searching the page
   for the new words (an undone "Flyers" -> "Picks" would otherwise turn every "Picks" on the page into "Flyers") */
check('an undone wording change never rewrites the page by its new words',
      !/ovReplaceText\(\s*(?:g|op)\.replace/.test(ap) && /ovUnreplace\(/.test(ap), 'gone');
check('the applier never parses markup or runs code', !/innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(|new Function|setAttribute\(['"]on|\.src\s*=(?!\s*url;)/.test(ap), 'markup');
check('a picture is set only from shotUrl', /var url = shotUrl\(im\);[\s\S]*img\.src = url/.test(ap), 'img');
/* pictures, by their own bytes */
const png = Buffer.from('89504e470d0a1a0a0000000d49484452', 'hex').toString('base64');
const jpg = Buffer.from('ffd8ffe000104a4649460001', 'hex').toString('base64');
check('a PNG is shown', ctx.shotUrl({ mime: 'image/png', b64: png }).startsWith('data:image/png;base64,'), 'png');
check('a JPEG is shown', ctx.shotUrl({ mime: 'image/jpeg', b64: jpg }).startsWith('data:image/jpeg;base64,'), 'jpg');
check('a PNG labelled JPEG is refused', ctx.shotUrl({ mime: 'image/jpeg', b64: png }) === '', 'mislabel');
check('an SVG is refused', ctx.shotUrl({ mime: 'image/svg+xml', b64: Buffer.from('<svg onload=alert(1)>').toString('base64') }) === '', 'svg');
check('markup in base64 is refused', ctx.shotUrl({ mime: 'image/png', b64: Buffer.from('<html><script>x</script></html>').toString('base64') }) === '', 'html');
check('a payload that is not base64 is refused', ctx.shotUrl({ mime: 'image/png', b64: png + '"><script>' }) === '', 'b64');
if (bad) { console.log('FAILED ' + bad); process.exit(1); }
console.log('all checks passed');
