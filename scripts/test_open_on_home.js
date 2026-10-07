// A new visit opens on Home: the tab a visitor was on is kept only for that browser tab's own reloads, and a new visit
// never opens on Trinity's tab, even from an address ending #trinity. Runs the boot lines of index_v2.js as shipped.
const fs = require('fs');
const src = fs.readFileSync(__dirname + '/index_v2.js', 'utf8');
const a = src.indexOf("try{localStorage.removeItem('rp_tab');}catch(e){}");
const b = src.indexOf('if(!start)start=_sesTab;');
if (a < 0 || b < 0) { console.log('FAIL boot lines not found'); process.exit(1); }
const boot = src.slice(a, b + 'if(!start)start=_sesTab;'.length);
function store(init) { const m = Object.assign({}, init); return { getItem: k => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); }, removeItem: k => { delete m[k]; }, m }; }
function run(hash, local, session) {
  const localStorage = store(local), sessionStorage = store(session);
  const TABS = ['home', 'mlb', 'nhl', 'past', 'trinity'];
  const fromHash = () => (TABS.indexOf(hash) >= 0 ? hash : null);
  const start = new Function('localStorage', 'sessionStorage', 'fromHash', boot + '\nreturn start;')(localStorage, sessionStorage, fromHash);
  return { start: start || 'home', local: localStorage.m };
}
let fails = 0;
const check = (cond, label) => { console.log((cond ? 'OK   ' : 'FAIL ') + label); if (!cond) fails++; };
check(run('', {}, {}).start === 'home', 'a first visit opens on Home');
check(run('', { rp_tab: 'trinity' }, {}).start === 'home', 'a new visit after leaving on Trinity opens on Home');
check(!('rp_tab' in run('', { rp_tab: 'trinity' }, {}).local), 'and the old every-visit memory is cleared');
check(run('trinity', {}, {}).start === 'home', 'a new visit to an address ending #trinity opens on Home');
check(run('mlb', {}, {}).start === 'mlb', 'a link to another tab still opens that tab');
check(run('', {}, { rp_tab: 'trinity' }).start === 'trinity', "the site's own reload while on Trinity stays on Trinity");
check(run('trinity', {}, { rp_tab: 'trinity' }).start === 'trinity', 'a refresh on her tab stays on her tab');
check(run('', {}, { rp_tab: 'nhl' }).start === 'nhl', 'a reload on another tab stays on it');
console.log(fails ? `open-on-home: ${fails} FAILED` : 'open-on-home: ALL PASS');
process.exit(fails ? 1 : 0);
