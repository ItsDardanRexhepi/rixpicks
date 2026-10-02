// Crypto-spam class (Sep 29, lane 3): client isPublishablePost must mirror the server
// gates - free-signals / VIP-trade / take-profit X spam and crypto-handle authors denied,
// legit sports posts pass. Extracts the real RP_* vars + isPublishablePost from index_v2.js.
// Run: node scripts/test_client_spam.js
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync(__dirname + '/index_v2.js', 'utf8');
// isPublishablePost also reads the commercial CTA/tag/free-sheet patterns (promo-sentinel 9/29)
const varLines = src.split('\n').filter(l => /^var (RP_AD_KW|RP_TOUT_KW|RP_OPERATOR|RP_COMM_CTA|RP_COMM_TAG|RP_COMM_FREE|RP_COMM_ODDS)=/.test(l) && /;\s*$/.test(l));
if (varLines.length !== 7) { console.log('FAIL expected 7 RP_ vars (incl. RP_COMM_*), got ' + varLines.length); process.exit(1); }
function extractFn(name){
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) throw new Error(name + ' not found');
  let depth = 0, i = src.indexOf('{', start);
  for (; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (!depth) return src.slice(start, i + 1); }
  }
  throw new Error(name + ' unterminated');
}
const ctx = {};
vm.createContext(ctx);
vm.runInContext(varLines.join('\n') + '\n' + extractFn('isPublishablePost'), ctx);

let fails = 0;
function check(label, cond){ console.log((cond ? 'OK   ' : 'FAIL ') + label); if (!cond) fails++; }

const SPAM = [
  ['free-signals VIP-trade', {id:'1', headline:'FREE SIGNALS!! VIP-1 TRADE: LONG $BTC entry 64500, TP1 66000, TP2 67500. Thursday Silver Squarely NFL NBA MLB', link:'https://x.com/Cry_Fortress/status/1', author:'Cry Fortress'}],
  ['clean text, crypto handle in author', {id:'2', headline:'Big night of baseball ahead, who you got?', link:'https://x.com/Cry_Fortress/status/2', author:'Cry Fortress @Cry_Fortress'}],
  ['take-profit phrasing', {id:'3', headline:'TP1 smashed. TP2 loading. Take-profit secured, stop-loss moved to entry. VIP-2 TRADE drops soon', link:'https://x.com/joe_sports/status/3', author:'Joe Sports'}],
  ['exchange/airdrop/100x', {id:'4', headline:'Airdrop live on Binance and Bybit, 100x gem, do not miss this one', link:'https://x.com/sportsfan99/status/4', author:'Sports Fan'}],
  ['caps FREE SIGNALS', {id:'5', headline:'FREE SIGNALS for tonight\'s slate, tail at your own risk', link:'https://x.com/pickpro/status/5', author:'Pick Pro'}],
];
const LEGIT = [
  ['Alvarez HR post', {id:'6', headline:'Yordan Alvarez goes deep AGAIN. Third homer in two games for the Astros slugger.', link:'https://x.com/astrostalk/status/6', author:'Astros Talk'}],
  ['Contreras lineup post', {id:'7', headline:'Willson Contreras batting third and playing first for the Red Sox tonight in the Bronx', link:'https://x.com/soxbeat/status/7', author:'Sox Beat'}],
  ['Silver Slugger post', {id:'8', headline:'Silver Slugger watch: Alvarez has to be in the conversation after this stretch', link:'https://x.com/espnmlb/status/8', author:'ESPN MLB'}],
  ['mixed signals post', {id:'9', headline:'Lakers showing mixed signals in the halfcourt, but the defense travels', link:'https://x.com/lakeshow/status/9', author:'Lake Show'}],
  ['Thursday Night Football post', {id:'10', headline:'Thursday Night Football should be a good one between two desperate teams', link:'https://x.com/nflupdate/status/10', author:'NFL Update'}],
];

for (const [name, p] of SPAM) check('client rejects ' + name, ctx.isPublishablePost(p) === false);
for (const [name, p] of LEGIT) check('client passes ' + name, ctx.isPublishablePost(p) === true);

console.log(fails === 0 ? 'PASS' : fails + ' FAILURES');
process.exit(fails ? 1 : 0);
