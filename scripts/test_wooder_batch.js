/* Wooder Ice batch tickets panel (Oct 5): hydrates slates/wooder_batch.json under the Wooder Ice tab.
   Per-leg KAL/DKP chips cents->American, unlisted notes, hides on missing/empty/wrong-date file, no combined price.
   Run: node scripts/test_wooder_batch.js [index.html] */
'use strict';
const fs=require('fs'),vm=require('vm');const html=fs.readFileSync(process.argv[2]||'index.html','utf8');
let bad=0;const check=(l,ok,d)=>{if(!ok)bad++;console.log((ok?'OK   ':'FAIL ')+l+(ok?'':'  ['+d+']'));};
const i=html.indexOf('id="rpBatchIdeas"');check('batch container present once',i>0&&html.split('id="rpBatchIdeas"').length===2,i);
const j=html.indexOf('<script>',i),k=html.indexOf('</script>',j),src=html.slice(j+8,k);
function run(data,now){const box={innerHTML:''};const doc={getElementById:id=>id==='rpBatchIdeas'?box:null};
 const D=class extends Date{toLocaleDateString(){return now;}};
 const ctx={document:doc,Date:D,Math,String,Array,fetch:()=>Promise.resolve({ok:!!data,json:()=>Promise.resolve(data)})};
 vm.createContext(ctx);vm.runInContext(src,ctx);return new Promise(r=>setTimeout(()=>r(box),30));}
const good={date:'2026-10-05',cards:[{id:'t3',title:'T',legs:[{player:'A',market:'m',links:[{venue:'KAL',cents:12},{venue:'DKP',cents:13},{venue:'FD',cents:50}]},{player:'B',market:'m',links:[],unlisted:['Kalshi','DraftKings Predictions']}]}]};
(async()=>{let b=await run(good,'2026-10-05');
 check('KAL 12c +733, DKP 13c +669',/KAL \+733/.test(b.innerHTML)&&/DKP \+669/.test(b.innerHTML),b.innerHTML.slice(0,300));
 check('card id anchor tk-t3',/id="tk-t3"/.test(b.innerHTML),'id');
 check('sportsbook chip dropped',!/FD /.test(b.innerHTML),'fd');
 check('unlisted on both renders',/Not listed on Kalshi, DraftKings Predictions/.test(b.innerHTML),'unl');
 check('no combined price / placed text',!/parlay|combined odds|payout|stake|NOT PLACED/i.test(b.innerHTML),'txt');
 b=await run(good,'2026-10-06');check('wrong date hides',b.innerHTML==='',b.innerHTML);
 b=await run({date:'2026-10-05',cards:[]},'2026-10-05');check('empty hides',b.innerHTML==='',b.innerHTML);
 b=await run(null,'2026-10-05');check('missing hides',b.innerHTML==='',b.innerHTML);
 if(bad){console.log('FAILED '+bad);process.exit(1);}console.log('all checks passed');})();
