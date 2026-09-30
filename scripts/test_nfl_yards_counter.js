#!/usr/bin/env node
/* Fixture: NFL futures yards counter. Extracts the real ydTxt from the builder source and
   checks fail-closed behaviour: fresh number renders N/T yards; stale/missing/null/negative/
   non-numeric -> "Unavailable"; a real 0 renders 0/T (only when source says 0). */
const fs=require('fs');
const src=fs.readFileSync(__dirname+'/build_gh_page_v2.py','utf8');
const m=src.match(/function ydTxt\(n,t\)\{.*?\}'/);
if(!m){console.log('FAIL ydTxt not found in builder');process.exit(1);}
const body=m[0].replace(/\}'$/,'}');
let bad=0;const t=(n,c)=>{console.log((c?'ok   ':'FAIL ')+n);if(!c)bad++;};
function mk(YD){return new Function('YD','Date',body+';return ydTxt;')(YD,Date);}
const now=new Date().toISOString();
const old=new Date(Date.now()-3*86400000).toISOString();
t('fresh 375',mk({fetched_at:now,players:{A:{yards:375}}})('A',1000)==='375/1000 yards');
t('fresh zero from source',mk({fetched_at:now,players:{A:{yards:0}}})('A',1000)==='0/1000 yards');
t('missing player',mk({fetched_at:now,players:{}})('A',1000)==='Unavailable');
t('null yards',mk({fetched_at:now,players:{A:{yards:null}}})('A',1000)==='Unavailable');
t('string yards',mk({fetched_at:now,players:{A:{yards:'375'}}})('A',1000)==='Unavailable');
t('negative',mk({fetched_at:now,players:{A:{yards:-5}}})('A',1000)==='Unavailable');
t('stale >48h',mk({fetched_at:old,players:{A:{yards:375}}})('A',1000)==='Unavailable');
t('no sidecar',mk(null)('A',1000)==='Unavailable');
t('no fetched_at',mk({players:{A:{yards:375}}})('A',1000)==='Unavailable');
console.log(bad?bad+' FAIL':'ALL OK');process.exit(bad?1:0);
