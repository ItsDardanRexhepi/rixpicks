/* rpFeedArb v3 - browser arbiter per selector v5.1 contract + registry v1.8 sport_clock.
   v3 (Sep 26, Matrix outcome_truth doctrine): three-way verdict per source per tick.
   ok      = named fields parsed AND a usable progress marker - stamps, eligible.
   failed  = the source ANSWERED with a negative verdict (event completed/postponed,
             market closed) - recorded, not eligible; feeds failover health.
   unknown = transport error, unparseable body, or missing named fields - NOT eligible
             and NOT a failure: never poisons source health, never learned as success.
   Schema drift (expected key path absent) flags lastDrift loudly instead of silently
   serving nothing. Freeze/failover semantics unchanged from v2 (4-min field freeze,
   stale_serve + served_is_live:false + failover_gap => RECONNECTING, never silent). */
(function(W){
"use strict";
var REGISTRY_VERSION='1.8';
function parseClock(s){var m=/^(\d+):(\d{2})$/.exec(String(s||''));return m?(+m[1])*60+(+m[2]):null;}
function progressOf(clockSec,period,clockCfg){
 if(clockSec==null||!period||period<1)return null;
 var ps=clockCfg.period_seconds;
 if(clockCfg.counts_down)return (period-1)*ps+(ps-clockSec);
 return (period-1)*ps+clockSec; /* count-up: clock value is elapsed within the period */
}
/* ESPN site summary marker. status lives at header.competitions[0].status with type.shortDetail/state. */
function markerFromEspnSummary(j,clockCfg){
 if(!j)return null; /* unknown: no body to read */
 if(!j.header||!Array.isArray(j.header.competitions)){
  W.rpFeedArb.lastDrift={at:Date.now(),what:'espn_summary_schema',hint:'header.competitions missing'};
  return null; /* unknown + loud drift flag: shape changed under us */
 }
 var comp=j.header.competitions[0]||{};
 var st=comp.status||{};
 var ty=st.type||{};
 if(ty.state==='post'||ty.completed===true)return {negative:true,reason:'completed'}; /* failed verdict: game over, not a live source */
 if(ty.state==='pre')return {negative:true,reason:'not_started'};
 var sc=(comp.competitors||[]).map(function(c){return c.score||'0';});
 var per=st.period||0;
 var clk=parseClock(st.displayClock),adv=null;
 var dr=j.drives&&j.drives.current;
 if(dr&&dr.plays&&dr.plays.length){
  var last=dr.plays[dr.plays.length-1];
  adv=parseClock(last.clock&&last.clock.displayValue);
 }
 var best=(adv!=null)?adv:clk; /* frozen-field rule: plays clock outranks status.displayClock */
 if(best==null&&ty.state!=='in')return null; /* unknown: no clock fields to trust */
 var pk='';
 if(dr&&dr.plays){var lp=dr.plays[dr.plays.length-1];pk=dr.plays.length+'|'+(((j.drives||{}).previous)||[]).length+'|'+(lp?(lp.id||lp.text||''):'');}
 return {progress:progressOf(best,per,clockCfg),clock:best,period:per,scores:sc,state:ty.state||'',
         sClock:clk,pClock:adv,playKey:pk, /* raw fields for the page-side clock arbiter (single parser, no drift) */
         periodText:(ty.shortDetail||'').replace(/^\d+:\d+\s*-\s*/,''),
         text:(best!=null?(Math.floor(best/60)+':'+('0'+best%60).slice(-2)+' - '):'')+((ty.shortDetail||'').replace(/^\d+:\d+\s*-\s*/,'')||'')};
}
function Arb(league,clockCfg){
 this.league=league;this.clockCfg=clockCfg;
 this.cands=[];this.hist={};this.lastAdvance=0;this.lastProg=-1;this.held=null;this.serving=null;
 this.verdicts={};this.health={}; /* health[id]: consecutive FAILED verdicts only - unknown never increments */
}
Arb.prototype.addCand=function(id,rank,fetcher,parser){this.cands.push({id:id,rank:rank,fetcher:fetcher,parser:parser,lat:null});};
Arb.prototype.tick=function(done){
 var self=this;var results=[];var pending=self.cands.length;
 if(!pending){done(self.decide([]));return;}
 self.cands.forEach(function(c){
  var t0=Date.now();
  c.fetcher(function(err,j){
   var v='unknown';
   if(!err&&j){
    var mk=c.parser(j,self.clockCfg);
    if(mk&&mk.progress!=null){c.lat=Date.now()-t0;results.push({c:c,mk:mk});v='ok';}
    else if(mk&&mk.negative){v='failed';}
   }
   self.verdicts[c.id]=v;
   if(v==='failed')self.health[c.id]=(self.health[c.id]||0)+1;else if(v==='ok')self.health[c.id]=0;
   /* unknown: health untouched - an unlabelled sample costs one data point, a mislabelled one corrupts the rate */
   if(--pending===0)done(self.decide(results));
  });
 });
};
Arb.prototype.decide=function(results){
 var now=Date.now();
 var elig=results.filter(function(r){ /* own-history advance gate: no rewinds */
  var h=this.hist[r.c.id];
  return !h||r.mk.progress>=h.progress-0.0001;
 },this);
 elig.sort(function(a,b){
  if(b.mk.progress!==a.mk.progress)return b.mk.progress-a.mk.progress;
  if(a.c.lat!==b.c.lat)return a.c.lat-b.c.lat;
  if(a.c.rank-b.c.rank!==0)return a.c.rank-b.c.rank;
  return (this.health[a.c.id]||0)-(this.health[b.c.id]||0); /* tie-break: fewer consecutive failed verdicts */
 },this);
 var win=elig[0]||null;
 if(win){
  this.hist[win.c.id]=win.mk;
  if(win.mk.progress>this.lastProg){this.lastProg=win.mk.progress;this.lastAdvance=now;}
 }
 var frozen=(now-this.lastAdvance)>240000; /* 4-min field-freeze rule */
 var gap=!win||frozen;
 if(win&&!frozen){
  this.held={mk:win.mk,src:win.c.id,at:now};
  this.serving={mk:win.mk,src:win.c.id,stale_serve:false,served_is_live:true,failover_gap:false};
 }else if(this.held){
  this.serving={mk:this.held.mk,src:this.held.src,stale_serve:true,served_is_live:false,failover_gap:true};
 }else{
  this.serving={mk:null,src:null,stale_serve:false,served_is_live:false,failover_gap:true};
 }
 this.serving.verdicts=JSON.parse(JSON.stringify(this.verdicts));
 return this.serving;
};
W.rpFeedArb={Arb:Arb,markerFromEspnSummary:markerFromEspnSummary,parseClock:parseClock,progressOf:progressOf,registryVersion:REGISTRY_VERSION,lastDrift:null};
})(typeof window!=='undefined'?window:globalThis);
