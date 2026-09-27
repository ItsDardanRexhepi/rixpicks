
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
 var sc=(comp.competitors||[]).map(function(c){return c.score!=null?c.score:'\u2014';});
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
W.rpFeedArb={markerFromEspnSummary:markerFromEspnSummary,parseClock:parseClock,progressOf:progressOf,registryVersion:REGISTRY_VERSION,lastDrift:null};
})(typeof window!=='undefined'?window:globalThis);
