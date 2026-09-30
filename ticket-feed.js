/* rpTicketFeed - live per-leg tracking feed for user-reported tickets.
   Source: statsapi.mlb.com liveFeed (CORS-open, official MLB feed).
   House rule: fail-closed. Counts are null unless the game is Live or Final.
   Pregame boxscore reports zeros - those are NOT in-game data and must never
   render as progress. No leg is graded before its game goes Final, except a
   threshold already reached (which stays hit even mid-game). */
(function(root){
'use strict';
var FEED_FIELDS='metaData,timeStamp,gameData,status,abstractGameState,detailedState,teams,team,abbreviation,gameDate,liveData,boxscore,players,person,fullName,stats,batting,pitching,homeRuns,strikeOuts,hits';

// Leg definitions from the ticket owner's reports relayed by Main (Sep 30, verified peer).
//   Placement status per the owner's 11:03 AM clarification (11:16 AM relay): the
//   strikeouts parlay and the HITS ticket are placed; the Dingers HR picks are an
//   idea - NOT bought. Labels only; no threshold, leg, or value changes. No odds, stakes, or prices were supplied,
//   so none exist here. Note: a double or HR counts as ONE hit.
var TICKETS=[
 {id:'hr-picks-2026-09-30',label:'Dingers HR picks (idea - not bought)',legs:[
  {legId:'hr-schwarber',kind:'batter_home_run',player:{id:656941,name:'Kyle Schwarber',team:'PHI'},gamePk:849841},
  {legId:'hr-alvarez',kind:'batter_home_run',player:{id:670541,name:'Yordan Alvarez',team:'HOU'},gamePk:849846},
  {legId:'hr-rice',kind:'batter_home_run',player:{id:700250,name:'Ben Rice',team:'NYY'},gamePk:849848},
  {legId:'hr-tatis',kind:'batter_home_run',player:{id:665487,name:'Fernando Tatis Jr.',team:'SD'},gamePk:849842}
 ]},
 {id:'hits-tracker-2026-09-30',label:'Hits ticket (placed - reported by Wooder Ice)',legs:[
  {legId:'h-turner',kind:'batter_hits',threshold:1,player:{id:607208,name:'Trea Turner',team:'PHI'},gamePk:849841},
  {legId:'h-alvarez',kind:'batter_hits',threshold:2,player:{id:670541,name:'Yordan Alvarez',team:'HOU'},gamePk:849846},
  {legId:'h-rice',kind:'batter_hits',threshold:1,player:{id:700250,name:'Ben Rice',team:'NYY'},gamePk:849848},
  {legId:'h-tatis',kind:'batter_hits',threshold:2,player:{id:665487,name:'Fernando Tatis Jr.',team:'SD'},gamePk:849842}
 ]},
 {id:'k-parlay-2026-09-30',label:'Strikeouts parlay',legs:[
  {legId:'k-sanchez',kind:'pitcher_strikeouts',threshold:7,player:{id:650911,name:'Cristopher Sánchez',team:'PHI'},gamePk:849841},
  {legId:'k-brown',kind:'pitcher_strikeouts',threshold:7,player:{id:686613,name:'Hunter Brown',team:'HOU'},gamePk:849846},
  {legId:'k-fried',kind:'pitcher_strikeouts',threshold:6,player:{id:608331,name:'Max Fried',team:'NYY'},gamePk:849848},
  {legId:'k-gausman',kind:'pitcher_strikeouts',threshold:5,player:{id:592332,name:'Kevin Gausman',team:'CHC'},gamePk:849842}
 ]}
];

function fetchGame(gamePk){
 var url='https://statsapi.mlb.com/api/v1.1/game/'+gamePk+'/feed/live?fields='+FEED_FIELDS;
 return fetch(url,{cache:'no-store'}).then(function(r){if(!r.ok)throw new Error('http '+r.status);return r.json();});
}

function legFromGame(leg,j){
 var gd=j.gameData||{},st=gd.status||{};
 var state=st.abstractGameState||null; // Preview | Live | Final
 var out={
  legId:leg.legId,kind:leg.kind,player:leg.player,
  threshold:leg.threshold!=null?leg.threshold:null,
  gamePk:leg.gamePk,
  game:{state:state,detailedState:st.detailedState||null,
        away:((gd.teams||{}).away||{}).abbreviation||null,
        home:((gd.teams||{}).home||{}).abbreviation||null,
        startTime:gd.datetime?gd.datetime.dateTime:(gd.gameDate||null)},
  current:null,status:'unavailable',
  freshness:{sourceTs:(j.metaData||{}).timeStamp||null,fetchedAt:new Date().toISOString()},
  source:'statsapi.mlb.com liveFeed'
 };
 if(state!=='Live'&&state!=='Final'){
  out.status=state==='Preview'?'pre':'unavailable'; // pre = game not started; counts intentionally null
  return out;
 }
 var pl=(((j.liveData||{}).boxscore||{}).teams)||{};
 var rec=null;
 ['away','home'].forEach(function(s){
  var ps=(pl[s]||{}).players||{};
  var r=ps['ID'+leg.player.id];
  if(r)rec=r;
 });
 if(!rec||!rec.stats)return out; // player not in boxscore yet (e.g. not in lineup) -> unavailable, never zero
 var stt=leg.kind==='pitcher_strikeouts'?rec.stats.pitching:rec.stats.batting;
 if(!stt)return out;
 var v=leg.kind==='pitcher_strikeouts'?stt.strikeOuts:(leg.kind==='batter_hits'?stt.hits:stt.homeRuns);
 if(typeof v!=='number')return out;
 out.current=v;
 if(leg.kind==='pitcher_strikeouts'||leg.kind==='batter_hits'){
  if(v>=leg.threshold)out.status='hit';                     // reached, even mid-game
  else out.status=state==='Final'?'final_miss':'pending';
 }else{
  if(v>=1)out.status='hit';
  else out.status=state==='Final'?'final_miss':'pending';
 }
 return out;
}

function rpTicketFeed(){
 var pks={},i;
 for(i=0;i<TICKETS.length;i++)TICKETS[i].legs.forEach(function(l){pks[l.gamePk]=1;});
 var games={};
 return Promise.all(Object.keys(pks).map(function(pk){
  return fetchGame(pk).then(function(j){games[pk]=j;}).catch(function(e){games[pk]={__error:String(e)};});
 })).then(function(){
  return {
   generatedAt:new Date().toISOString(),
   tickets:TICKETS.map(function(t){
    return {id:t.id,label:t.label,legs:t.legs.map(function(l){
     var g=games[l.gamePk];
     if(!g||g.__error)return {legId:l.legId,kind:l.kind,player:l.player,
       threshold:l.threshold!=null?l.threshold:null,gamePk:l.gamePk,
       game:null,current:null,status:'unavailable',
       freshness:{sourceTs:null,fetchedAt:new Date().toISOString()},
       source:'statsapi.mlb.com liveFeed',error:g?g.__error:'no data'};
     return legFromGame(l,g);
    })};
   })
  };
 });
}

root.rpTicketFeed=rpTicketFeed;
root.rpTicketFeedTickets=TICKETS;
if(typeof module!=='undefined')module.exports={rpTicketFeed:rpTicketFeed,TICKETS:TICKETS};
})(typeof window!=='undefined'?window:this);
