/* Provider-parser fixtures: these do not prove live feed availability. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const window={RPSlip:{},dispatchEvent(){}};
const document={readyState:'loading',createElement:()=>({}),head:{appendChild(){}},addEventListener(){}};
vm.runInNewContext(fs.readFileSync('rp-slip-adapter.js','utf8'),{window,document,Date,Intl,Event:function(){},setInterval(){},setTimeout,clearTimeout});
const app=window.RPApp;
const leg={nhlGame:10,nhlPlayer:7,athlete:'77',event:'100',league:'nhl',away:'NYR',home:'VAN',team:'NYR',goals:true,requireParticipation:true};
const nhl=(toi,goals=0)=>({id:10,gameState:'LIVE',awayTeam:{abbrev:'NYR',score:0},homeTeam:{abbrev:'VAN',score:0},periodDescriptor:{number:1},clock:{timeRemaining:'19:00'},playerByGameStats:{awayTeam:{forwards:[{playerId:7,toi,goals}]},homeTeam:{forwards:[]}}});
const espn=(toi,goals='0')=>({header:{id:'100',competitions:[{status:{type:{state:'in'},period:1,displayClock:'19:00'},competitors:[{homeAway:'away',team:{abbreviation:'NYR'}},{homeAway:'home',team:{abbreviation:'VAN'}}]}]},boxscore:{players:[{team:{abbreviation:'NYR'},statistics:[{keys:['goals','timeOnIce'],athletes:[{athlete:{id:'77'},stats:[goals,toi]}]}]}]}});
let passed=0;function test(name,fn){fn();passed++;console.log('PASS '+name);}
for(const toi of [undefined,null,'','0:00','00:00','1:99','-1:20'])test('NHL does not assume participation from '+String(toi),()=>assert.equal(app._gameFromNhl(nhl(toi),leg).stat(leg),null));
test('NHL verified positive ice time permits a recorded zero',()=>assert.equal(app._gameFromNhl(nhl('0:01'),leg).stat(leg),0));
test('NHL positive ice time and one goal preserve the exact stat',()=>assert.equal(app._gameFromNhl(nhl('12:31',1),leg).stat(leg),1));
test('NHL refuses wrong team even when player ID is present',()=>assert.equal(app._gameFromNhl(nhl('12:31'),leg).stat({...leg,team:'VAN'}),null));
test('NHL refuses duplicate player records',()=>{const g=nhl('2:00');g.playerByGameStats.awayTeam.forwards.push({...g.playerByGameStats.awayTeam.forwards[0]});assert.equal(app._gameFromNhl(g,leg).stat(leg),null);});
test('NHL rejects wrong matchup',()=>{const g=nhl('2:00');g.homeTeam.abbrev='TOR';assert.throws(()=>app._gameFromNhl(g,leg),/Wrong matchup/);});
test('NHL refuses negative goal totals',()=>assert.equal(app._gameFromNhl(nhl('2:00',-1),leg).stat(leg),null));
for(const toi of [undefined,'','0:00','1:99'])test('ESPN does not assume participation from '+String(toi),()=>assert.equal(app._gameFromEspn(espn(toi),leg).stat(leg),null));
test('ESPN verified positive ice time permits recorded zero',()=>assert.equal(app._gameFromEspn(espn('0:01'),leg).stat(leg),0));
test('ESPN explicit DNP remains unknown despite contradictory time',()=>{const g=espn('2:00');g.boxscore.players[0].statistics[0].athletes[0].didNotPlay=true;assert.equal(app._gameFromEspn(g,leg).stat(leg),null);});
test('ESPN wrong team remains unknown',()=>{const g=espn('2:00');g.boxscore.players[0].team.abbreviation='VAN';assert.equal(app._gameFromEspn(g,leg).stat(leg),null);});
test('other NHL card parsing stays unchanged without opt-in',()=>assert.equal(app._gameFromNhl(nhl('0:00'),{...leg,requireParticipation:false}).stat({...leg,requireParticipation:false}),0));
test('final unplayed row cannot become a failed selection',()=>{const g=nhl('0:00');g.gameState='FINAL';app._games['nhl:10']=app._gameFromNhl(g,leg);const result=app._derive({sport:'NHL',resolveFinal:true,selectionOnly:true,legs:[{player:'Fixture',market:'goals',line:1,x:leg}]},Date.now());assert.equal(result.status,'open');assert.equal(result.legs[0].final,undefined);});
console.log(passed+' NHL participation checks passed');
