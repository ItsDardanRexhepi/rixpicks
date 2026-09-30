// Feed guard 1 (Sep 29): isSportsPost classification unit test - the zero-pair fallback
// Social gate. Genuine sports posts pass (strong term / team name / acronym+context / 2+
// weak game terms); off-topic content (finance, politics, fashion, sexual solicitation,
// luggage, essay/diet spam, bare-acronym stuffing) is dropped. Run: node scripts/test_social_sports_gate.js
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync(__dirname + '/index_v2.js', 'utf8');
const varLines = src.split('\n').filter(l => /^var (RP_AD_KW|RP_TOUT_KW|RP_OPERATOR|RP_NONSPORT_KILL|RP_SPORT_ACRO|RP_SPORT_STRONG|RP_SPORT_TEAMS|RP_SPORT_WEAK)=/.test(l) && /;\s*$/.test(l));
if (varLines.length !== 8) { console.log('FAIL expected 8 RP_ vars, got ' + varLines.length); process.exit(1); }
function extractFn(name){
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) throw new Error(name + ' not found');
  let depth = 0, i = src.indexOf('{', start);
  for (; i < src.length; i++) { if (src[i] === '{') depth++; else if (src[i] === '}') { depth--; if (!depth) return src.slice(start, i + 1); } }
  throw new Error(name + ' unterminated');
}
const ctx = {};
vm.createContext(ctx);
vm.runInContext(varLines.join('\n') + '\n' + extractFn('isPublishablePost') + '\n' + extractFn('isSportsPost') + '\n' + extractFn('zeroPairSocial'), ctx);

let fails = 0;
function check(label, cond){ console.log((cond ? 'OK   ' : 'FAIL ') + label); if (!cond) fails++; }
const S = (id, text, author) => ({ id, headline: text, link: 'https://x.com/x/status/' + id, author: author || 'Fan', published: '2026-09-29T23:00:00Z' });

const SPORTS = [
  ['strong term (homer)', S('1', 'Yordan Alvarez goes deep AGAIN. Third homer in two games for the Astros slugger.')],
  ['team name (Red Sox)', S('2', 'Willson Contreras batting third and playing first for the Red Sox tonight in the Bronx')],
  ['strong (football)', S('3', 'Thursday Night Football should be a good one between two desperate teams')],
  ['weak x2 (OT comeback)', S('4', 'UCLA survives in OT, what a comeback win')],
  ['team (Yankees)', S('5', 'Judge sends one into the second deck, 3-0 Yankees')],
  ['teams (Leafs Habs)', S('6', 'Leafs and Habs renew the rivalry Saturday night')],
  ['acronym+weak (NFL game)', S('7', 'NFL game of the week just flexed to Sunday night')],
  ['single acronym (NBA)', S('8', 'NBA is so back, opening night was a movie')],
];
const NONSPORT = [
  ['finance solicitation', S('11', 'NASDAQ ripping today, passive income stock tips inside')],
  ['politics', S('12', 'The president addressed congress on the election results tonight')],
  ['fashion promo', S('13', 'New fashion drop just hit the runway, shop the look now')],
  ['sexual solicitation', S('14', '18+ spicy content on my only fans page tonight')],
  ['lost luggage', S('15', 'Airline lost my luggage again, worst travel day ever')],
  ['essay spam', S('16', 'Essay help and homework help, DM for rates')],
  ['diet spam', S('17', 'Weight loss diet pills that actually work fast')],
  ['bare-acronym stuffing', S('18', 'Thursday Silver Squarely NFL NBA MLB, big day')],
  ['random life post', S('19', 'Just got my coffee and the line was so long')],
];
for (const [n, p] of SPORTS) check('isSportsPost passes ' + n, ctx.isSportsPost(p) === true);
for (const [n, p] of NONSPORT) check('isSportsPost drops ' + n, ctx.isSportsPost(p) === false);

ctx.XNEWS = SPORTS.concat(NONSPORT).map(x => x[1]);
const fp = ctx.zeroPairSocial(12);
check('zeroPairSocial returns only sports posts', fp.every(it => SPORTS.some(s => s[1].id === it.post.id)), true);
check('zeroPairSocial returns all 8 sports posts', fp.length, 8);
check('zeroPairSocial kind latest-only', fp.every(it => it.kind === 'latest'), true);
check('zeroPairSocial order preserved', fp.map(it => it.post.id).join(','), '1,2,3,4,5,6,7,8');

console.log(fails === 0 ? 'PASS' : fails + ' FAILURES');
process.exit(fails ? 1 : 0);
