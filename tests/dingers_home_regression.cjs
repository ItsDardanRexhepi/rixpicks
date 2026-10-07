// Run from the repository root: node tests/dingers_home_regression.cjs
// No network or packages. Exercises the actual generated renderer and date-roll source.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('index.html','utf8');
const css=fs.readFileSync('scripts/index_v2.css','utf8');
const tabs=fs.readFileSync('scripts/index_v2_tabs.js','utf8');
const builder=fs.readFileSync('scripts/build_site.py','utf8');
assert.equal(builder,fs.readFileSync('build_site.py','utf8'),'builder twins must match');
assert.equal((html.match(/id="rpDing"/g)||[]).length,1,'one shared Dingers node');
assert.equal((html.match(/id="st-ding"/g)||[]).length,1,'one shared Dingers state');
assert.match(html,/<div class="state" id="st-ding" data-home-league="1">/);
assert.match(builder,/<div class="state" id="st-ding" data-home-league="1">/);
assert.match(css,/body\.tab-home #st-ding\s*\{display:block\}/);
assert.match(css,/body\.tab-wooder #st-ding\s*\{display:block\}/);
assert.doesNotMatch(html+css,/body\.tab-home #st-ding\s*\{display:none/);
const start=html.indexOf('id="rpDing"'),a=html.indexOf('<script>',start)+8,b=html.indexOf('</script>',a);
const renderer=html.slice(a,b);
const today=new Date().toLocaleDateString('en-CA',{timeZone:'America/Los_Angeles'});
const pick={player:'Regression Player',team:'CWS',matchup:'CLE at CWS',time:'1PM PT',market:'1+ HR',links:[]};
async function render(record){
 const wrapper={style:{}},box={innerHTML:'',parentNode:{parentNode:wrapper}};
 const context={document:{getElementById:id=>id==='rpDing'?box:null,querySelectorAll:()=>[]},Date,Intl,setInterval:()=>{},fetch:async url=>({ok:true,json:async()=>url.startsWith('slates/')?record:{events:[]}})};
 vm.runInNewContext(renderer,context);
 for(let i=0;i<10;i++)await Promise.resolve();
 return {box,wrapper};
}
(async()=>{
 // Empty official card is deliberately absent from the renderer context.
 const current=await render({date:today,picks:[pick]});
 assert.match(current.box.innerHTML,/Regression Player/);
 assert.notEqual(current.wrapper.style.display,'none','current Dingers independent of empty official card');
 for(const record of [{date:'2000-01-01',picks:[pick]},{date:today,picks:[]}]){
  const result=await render(record);assert.equal(result.wrapper.style.display,'none');assert.equal(result.box.innerHTML,'');
 }
 const ding={querySelector:()=>null,removeAttribute:()=>{throw Error('Dingers removed by official date roll');}};
 let removed=false;const oldLeague={querySelector:s=>s==='.pick'?{}:null,removeAttribute:()=>{removed=true;},insertBefore:()=>{},firstChild:null};
 const official={innerHTML:'stale'},header={getAttribute:()=> '2000-01-01',textContent:'Old card'};
 const document={querySelector:()=>header,getElementById:id=>id==='st-home'?official:null,querySelectorAll:()=>[ding,oldLeague],createElement:()=>({}),body:{classList:{contains:()=>true}}};
 const roll=tabs.slice(tabs.indexOf('function rpDateRoll(){'),tabs.indexOf('rpDateRoll();'));
 const context={document,window:{},Date,Intl};vm.runInNewContext(roll+'rpDateRoll();',context);
 assert.equal(context.window.RP_CARD_STALE,true);assert.equal(removed,true);assert.match(official.innerHTML,/has not published yet/);
 assert.match(current.box.innerHTML,/Regression Player/,'date roll does not remove current Dingers');
 console.log('PASS: shared Home/Wooder node, current-day empty official card, stale official roll, wrong-date and empty Dingers, builder parity.');
})().catch(e=>{console.error(e);process.exitCode=1;});
