const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const window={RPSlip:{},dispatchEvent(){}},document={readyState:'loading',createElement:()=>({}),head:{appendChild(){}},addEventListener(){}};
vm.runInNewContext(fs.readFileSync('rp-slip-adapter.js','utf8'),{window,document,Date,Intl,Event:function(){},setInterval(){},setTimeout,clearTimeout});
const app=window.RPApp,x={event:'42',league:'nba',away:'NY',home:'IND',athlete:'7',team:'NY',requireBasketballParticipation:true,keys:['points','rebounds','assists','steals','blocks'],doubleDouble:true};
function game(stats=['10','10','1','0','0','12']){return {header:{id:'42',competitions:[{status:{type:{state:'in'},period:1,displayClock:'3:00'},competitors:[{homeAway:'away',team:{abbreviation:'NY'},score:'50'},{homeAway:'home',team:{abbreviation:'IND'},score:'45'}]}]},boxscore:{players:[{team:{abbreviation:'NY'},statistics:[{keys:['points','rebounds','assists','steals','blocks','minutes'],athletes:[{athlete:{id:'7'},stats}]}]}]}};}
let n=0;function test(name,f){f();console.log('PASS '+name);n++;}
test('double-double needs two complete categories at ten',()=>{assert.equal(app._gameFromEspn(game(),x).stat(x),1);assert.equal(app._gameFromEspn(game(['10','9','1','0','0','12']),x).stat(x),0);});
test('PRA uses total rebounds and sums three categories',()=>assert.equal(app._gameFromEspn(game(),x).stat({...x,doubleDouble:false,keys:['points','rebounds','assists']}),21));
for(const m of ['0','0:00','--',undefined])test('unverified participation '+m,()=>assert.equal(app._gameFromEspn(game(['10','10','1','0','0',m]),x).stat(x),null));
test('DNP overrides conflicting stats',()=>{const j=game();j.boxscore.players[0].statistics[0].athletes[0].didNotPlay=true;assert.equal(app._gameFromEspn(j,x).stat(x),null);});
test('wrong team and wrong athlete remain unknown',()=>{assert.equal(app._gameFromEspn(game(),x).stat({...x,team:'IND'}),null);assert.equal(app._gameFromEspn(game(),x).stat({...x,athlete:'8'}),null);});
test('missing category cannot become zero',()=>assert.equal(app._gameFromEspn(game(['10','--','1','0','0','12']),x).stat(x),null));
test('game total sums exact scores',()=>assert.equal(app._gameFromEspn(game(),x).stat({totalPoints:true}),95));
test('missing game score remains unknown',()=>{const j=game();j.header.competitions[0].competitors[0].score=null;assert.equal(app._gameFromEspn(j,x).stat({totalPoints:true}),null);});
test('half-point spread wins and loses correctly',()=>{const j=game();j.header.competitions[0].status.type={state:'post',completed:true};assert.equal(app._gameFromEspn(j,x).stat({spreadTeam:'IND',spreadLine:8.5}),1);assert.equal(app._gameFromEspn(j,x).stat({spreadTeam:'NY',spreadLine:-15.5}),0);});
const s=JSON.parse(fs.readFileSync('nba-nov13.js','utf8').match(/var DATA=(.*);\nfunction start/)[1]);
test('derived total labelled without hidden dollar inputs',()=>{assert.equal(s.wooder.totalLabel,'Derived return');assert.equal(s.wooder.total,'+325');assert.equal(s.wooder.legs[3].odds,undefined);assert.equal(s.wooder.legs[4].odds,undefined);assert(!JSON.stringify(s).includes('$'));});
test('NBA6 substitution explicit and no synthetic combined price',()=>{assert(s.nba.legs[1].market.includes('Original U235.5 → substitute U236.5'));assert.equal(s.nba.legs[1].dir,'under');assert.equal(s.nba.total,undefined);assert.equal(s.nba.legs[2].odds,'+104');});
console.log(n+' NBA checks passed');
