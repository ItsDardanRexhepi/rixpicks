// Trinity's tab is the last tab in the nav, always, and no league ever has two tabs (owner, 2026-10-07): the page builds it last, and when a script
// adds a tab of its own afterwards (the Wooder WNBA module once appended one after hers), hers goes back to the end.
// Runs trinity/trinity.js as shipped against a small DOM with a MutationObserver.
const fs = require('fs');
const code = fs.readFileSync(__dirname + '/../trinity/trinity.js', 'utf8');
const observers = [], queue = [];
function Tab(key) { return { key, parentNode: null, tagName: 'A', getAttribute: (k) => (k === 'data-tab' ? key : null) }; }
const bar = {
  children: [],
  removeChild(c) { this.children = this.children.filter((x) => x !== c); c.parentNode = null; observers.forEach((f) => queue.push(f)); return c; },
  get lastElementChild() { return this.children[this.children.length - 1] || null; },
  appendChild(c) { this.children = this.children.filter((x) => x !== c); this.children.push(c); c.parentNode = this; observers.forEach((f) => queue.push(f)); return c; },
  insertBefore(c, ref) { this.children = this.children.filter((x) => x !== c); const i = ref ? this.children.indexOf(ref) : -1; if (i < 0) this.children.push(c); else this.children.splice(i, 0, c); c.parentNode = this; observers.forEach((f) => queue.push(f)); return c; },
  querySelector(sel) { const m = /data-tab="([a-z]+)"/.exec(sel); return m ? this.children.find((t) => t.key === m[1]) || null : null; },
};
['home', 'mlb', 'wnba', 'wooder', 'past', 'trinity'].forEach((k) => bar.appendChild(Tab(k)));
function MutationObserver(cb) { this.observe = () => observers.push(cb); }
const document = { readyState: 'complete', querySelector: (s) => (s === 'nav.rpnav .tabs' ? bar : null), getElementById: () => null,
  querySelectorAll: () => [], addEventListener() {}, body: { classList: { toggle() {}, add() {}, remove() {}, contains: () => false } } };
const window = { addEventListener() {} };
new Function('window', 'document', 'sessionStorage', 'fetch', 'location', 'setInterval', 'MutationObserver', code)(
  window, document, { getItem: () => null, setItem() {}, removeItem() {} }, () => Promise.reject(), { reload() {} }, () => 1, MutationObserver);
const order = () => bar.children.map((t) => t.key).join(',');
const flush = () => { while (queue.length) queue.shift()(); };
let fails = 0; const check = (c, l) => { console.log((c ? 'OK   ' : 'FAIL ') + l + ' [' + order() + ']'); if (!c) fails++; };
check(bar.lastElementChild.key === 'trinity', 'her tab is last as built');
bar.appendChild(Tab('crypto')); flush();
check(bar.lastElementChild.key === 'trinity' && bar.children.some((t) => t.key === 'crypto'), 'a tab appended after hers goes before hers');
bar.insertBefore(bar.children.find((t) => t.key === 'trinity'), bar.children[0]); flush();
check(bar.lastElementChild.key === 'trinity', 'moved to the front, she goes back to the end');
bar.appendChild(Tab('wnba')); flush();
check(bar.children.filter((t) => t.key === 'wnba').length === 1 && bar.lastElementChild.key === 'trinity', 'a second WNBA tab is removed, never shown');
console.log(fails ? `trinity last tab: ${fails} FAILED` : 'trinity last tab: ALL PASS');
process.exit(fails ? 1 : 0);
