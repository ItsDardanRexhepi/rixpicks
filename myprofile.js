/* RixPicks local profile: My Books + My Bets (on-device, no accounts) */
(function(){
var RP_BOOKS=[{k:'DK',n:'DraftKings'},{k:'FD',n:'FanDuel'},{k:'ESPN',n:'theScore Bet'} /* U-GEO-003: ESPN BET sportsbook dead (became theScore Bet Dec 1 2025); key kept so saved platform picks survive the rename */,{k:'MGM',n:'BetMGM'},{k:'HR',n:'Hard Rock'},{k:'BR',n:'BetRivers'},{k:'KAL',n:'Kalshi'},{k:'POLY',n:'Polymarket'},{k:'B365',n:'bet365'},{k:'FAN',n:'Fanatics'}];
var RP_LGS=['baseball/mlb','football/nfl','football/college-football','basketball/nba','basketball/wnba','hockey/nhl','soccer/usa.1','tennis/wta'];
function ls(k,d){try{var v=localStorage.getItem(k);return v===null?d:JSON.parse(v);}catch(e){return d;}}
function sv(k,v){try{localStorage.setItem(k,JSON.stringify(v));}catch(e){}}
function myBooks(){return ls('rp_books',[]);}
function getBets(){return ls('rp_bets',[]);}
function saveBets(b){sv('rp_bets',b);}
function each(nl,fn){for(var i=0;i<nl.length;i++)fn(nl[i],i);}
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function bookName(k){for(var i=0;i<RP_BOOKS.length;i++){if(RP_BOOKS[i].k===k)return RP_BOOKS[i].n;}return k;}
var css=document.createElement('style');
css.textContent=
'.rp-fab{background:transparent;border:1px solid rgba(255,255,255,.18);color:#3BEBF5;font-weight:600;border-radius:999px;padding:5px 12px;font-size:11px;cursor:pointer;white-space:nowrap;margin-left:10px;flex-shrink:0;letter-spacing:.2px}'+
'.rp-modal{position:fixed;top:0;left:0;right:0;bottom:0;z-index:70;background:rgba(0,0,0,.66);display:flex;align-items:flex-end;justify-content:center}'+
'.rp-sheet{background:#000;border-top:1px solid rgba(255,255,255,.09);border-radius:20px 20px 0 0;width:100%;max-width:520px;max-height:84vh;overflow-y:auto;padding:10px 20px 22px;color:#ECECF1;font-family:inherit}'+
'.rp-grab{width:36px;height:4px;border-radius:2px;background:rgba(255,255,255,.18);margin:2px auto 14px}'+
'.rp-sheet h3{margin:0 0 2px;font-size:17px;font-weight:700;color:#F2F2F5;letter-spacing:-.2px}.rp-sub{color:#8A8F98;font-size:12.5px;margin-bottom:14px;line-height:1.45}'+
'.rp-label{display:block;font-size:10.5px;font-weight:600;letter-spacing:.8px;text-transform:uppercase;color:#6E737C;margin:14px 0 8px}'+
'.rp-pill{display:inline-block;margin:0 8px 8px 0;padding:8px 14px;border-radius:999px;border:1px solid rgba(255,255,255,.14);background:transparent;color:#D5D5DA;font-size:13px;cursor:pointer;transition:border-color .15s,color .15s}'+
'.rp-pill.on{border-color:#10D5E1;color:#3BEBF5;background:rgba(16,213,225,.08)}'+
'.rp-btn{display:block;width:100%;padding:13px;border:none;border-radius:12px;background:#00CCBF;color:#03232B;font-weight:700;font-size:15px;cursor:pointer;margin-top:14px;letter-spacing:.1px}'+
'.rp-btn.ghost{background:transparent;color:#9A9AA3;border:1px solid rgba(255,255,255,.14)}'+
'.rp-tabs{display:flex;background:#111111;border-radius:12px;padding:3px;margin:12px 0 16px}'+
'.rp-tab{flex:1;text-align:center;padding:8px;border-radius:9px;color:#8A8F98;font-size:13.5px;font-weight:600;cursor:pointer;transition:background .15s,color .15s}'+
'.rp-tab.on{background:rgba(16,213,225,.12);color:#3BEBF5}'+
'.rp-stats{display:flex;background:#111111;border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:12px 0;margin-bottom:14px}'+
'.rp-stat{flex:1;text-align:center}'+
'.rp-stat+.rp-stat{border-left:1px solid rgba(255,255,255,.07)}'+
'.rp-stat b{display:block;font-size:16px;font-weight:700;color:#F2F2F5;margin-bottom:2px}'+
'.rp-stat span{font-size:10px;font-weight:600;letter-spacing:.8px;text-transform:uppercase;color:#6E737C}'+
'.rp-bet{border:1px solid rgba(255,255,255,.07);background:#111111;border-radius:14px;padding:12px 14px;margin-bottom:10px;font-size:13.5px;line-height:1.4}'+
'.rp-bet .rp-live{color:#8A8F98;font-size:12px;margin-top:4px}'+
'.rp-pos{color:#00CCBF}.rp-neg{color:#FF6B5E}'+
'.rp-input{width:100%;box-sizing:border-box;background:#111111;border:1px solid rgba(255,255,255,.12);border-radius:10px;color:#ECECF1;padding:11px 12px;font-size:14px;margin-bottom:10px;outline:none}'+
'.rp-input:focus{border-color:#10D5E1}'+
'.rp-input::placeholder{color:#5C6068}'+
'.rp-row{display:flex;gap:10px}.rp-row>*{flex:1}'+
'.chip.rpmine{border-color:#10D5E1 !important;box-shadow:0 0 0 1px rgba(16,213,225,.5) inset}'+
'.chip.rpdim{opacity:.45}'+
'.rp-trackbtn{display:inline-block;margin:4px 0 0;font-size:11px;color:#00CCBF;border:1px solid rgba(0,204,191,.4);border-radius:999px;padding:4px 11px;cursor:pointer;background:transparent}'+
'.rp-stats .rp-neg{color:#FF6B5E}'
+'@media (prefers-color-scheme: light){'
'.rp-sheet{background:#FFFFFF;border-top-color:rgba(0,0,0,.08);color:#1B1B1F}'
'.rp-sheet h3{color:#1B1B1F}.rp-sub{color:#6E737C}'
'.rp-grab{background:rgba(0,0,0,.18)}'
'.rp-tabs{background:#F0EFEB}'
'.rp-tab{color:#6E737C}.rp-tab.on{background:#FFFFFF;color:#0B8A80;box-shadow:0 1px 3px rgba(0,0,0,.08)}'
'.rp-stats{background:#F7F6F4;border-color:rgba(0,0,0,.06)}'
'.rp-stat b{color:#1B1B1F}.rp-stat+.rp-stat{border-left-color:rgba(0,0,0,.07)}'
'.rp-bet{background:#F7F6F4;border-color:rgba(0,0,0,.07);color:#1B1B1F}'
'.rp-bet .rp-live{color:#6E737C}'
'.rp-pill{border-color:rgba(0,0,0,.16);color:#3A3A40}'
'.rp-pill.on{border-color:#00A99E;color:#0B8A80;background:rgba(0,204,191,.08)}'
'.rp-input{background:#FFFFFF;border-color:rgba(0,0,0,.14);color:#1B1B1F}'
'.rp-input::placeholder{color:#9AA0A8}'
'.rp-btn.ghost{color:#6E737C;border-color:rgba(0,0,0,.14)}'
'.rp-fab{border-color:rgba(0,153,143,.45);color:#0B8A80}'
'.rp-label{color:#9AA0A8}';
document.head.appendChild(css);
var modalEl=null;
function closeModal(){if(modalEl){if(window.__rpBooksOpen){sv('rp_books_asked',1);window.__rpBooksOpen=null;}modalEl.remove();modalEl=null;}}
function openSheet(html){closeModal();modalEl=document.createElement('div');modalEl.className='rp-modal';modalEl.innerHTML='<div class="rp-sheet"><div class="rp-grab"></div>'+html+'</div>';modalEl.addEventListener('click',function(e){if(e.target===modalEl)closeModal();});document.body.appendChild(modalEl);return modalEl.firstChild;}
function toast(msg){var t=document.createElement('div');t.textContent=msg;t.style.cssText='position:fixed;left:50%;bottom:70px;transform:translateX(-50%);background:#000000;border:1px solid #3BEBF5;color:#3BEBF5;padding:8px 16px;border-radius:18px;font-size:13px;z-index:80';document.body.appendChild(t);setTimeout(function(){t.remove();},2200);}
/* --- My Books --- */
function personalize(){var mine=myBooks();each(document.querySelectorAll('.chips'),function(c){var kids=Array.prototype.slice.call(c.querySelectorAll('.chip'));if(!kids.length)return;if(!mine.length){kids.forEach(function(ch){ch.classList.remove('rpmine');ch.classList.remove('rpdim');});return;}kids.sort(function(a,b){var am=mine.indexOf(a.getAttribute('data-book')||'')>=0?0:1;var bm=mine.indexOf(b.getAttribute('data-book')||'')>=0?0:1;return am-bm;});kids.forEach(function(ch){var m=mine.indexOf(ch.getAttribute('data-book')||'')>=0;ch.classList.toggle('rpmine',m);ch.classList.toggle('rpdim',!m);c.appendChild(ch);});});}
function booksSheet(){window.__rpBooksOpen=1;var sel=myBooks().slice();var sh=openSheet('<h3>My Platforms</h3><div class="rp-sub">Tap the platforms you use. Picks highlight yours first - linked account sync lands here.</div><div id="rpPills"></div><button class="rp-btn" id="rpSaveBooks">Save</button>'+(sel.length?'<button class="rp-btn ghost" id="rpClearBooks">Clear my platforms</button>':''));
var pills=sh.querySelector('#rpPills');
RP_BOOKS.forEach(function(b){var p=document.createElement('span');p.className='rp-pill'+(sel.indexOf(b.k)>=0?' on':'');p.textContent=b.n;p.onclick=function(){var i=sel.indexOf(b.k);if(i>=0)sel.splice(i,1);else sel.push(b.k);p.classList.toggle('on');};pills.appendChild(p);});
sh.querySelector('#rpSaveBooks').onclick=function(){sv('rp_books',sel);sv('rp_books_asked',1);personalize();closeModal();toast(sel.length?'Platforms saved':'Saved');};
var clr=sh.querySelector('#rpClearBooks');if(clr)clr.onclick=function(){sv('rp_books',[]);personalize();closeModal();};}
/* --- Track bet --- */
function parseOdds(lbl){var m=/([+-]\d+)\s*$/.exec(lbl||'');return m?parseInt(m[1],10):null;}
function trackSheet(pick){var away=pick.getAttribute('data-away')||'',home=pick.getAttribute('data-home')||'',side=pick.getAttribute('data-side')||'away',mkt=pick.getAttribute('data-market')||'ml',lg=pick.getAttribute('data-espn')||'';
var selTeam=side==='away'?away:home;
var chipsA=[];each(pick.querySelectorAll('.chip[data-book]'),function(ch){chipsA.push({book:ch.getAttribute('data-book'),lbl:ch.textContent.trim()});});
var mine=myBooks();chipsA.sort(function(a,b){var am=mine.indexOf(a.book)>=0?0:1;var bm=mine.indexOf(b.book)>=0?0:1;return am-bm;});
var h='<h3>Track this bet</h3><div class="rp-sub">'+esc(selTeam)+' '+(mkt==='spread'?'spread':'moneyline')+' &middot; '+esc(away)+' @ '+esc(home)+'</div>';
if(chipsA.length){h+='<div class="rp-label">Book (yours first)</div>';chipsA.forEach(function(c,i){h+='<span class="rp-pill'+(i===0?' on':'')+'" data-rpbook="'+esc(c.book)+'" data-rpodds="'+(parseOdds(c.lbl)||'')+'">'+esc(c.lbl)+'</span>';});}
h+='<div class="rp-row" style="margin-top:6px"><input class="rp-input" id="rpOdds" type="number" placeholder="Odds (e.g. -150)"><input class="rp-input" id="rpStake" type="number" step="0.1" min="0" placeholder="Stake (units)"></div>';
if(mkt==='spread')h+='<input class="rp-input" id="rpLine" type="number" step="0.5" placeholder="Spread line (e.g. -3.5)">';
h+='<button class="rp-btn" id="rpSaveBet">Track bet</button>';
var sh=openSheet(h);
each(sh.querySelectorAll('.rp-pill'),function(p){p.onclick=function(){each(sh.querySelectorAll('.rp-pill'),function(x){x.classList.remove('on');});p.classList.add('on');var o=p.getAttribute('data-rpodds');if(o)sh.querySelector('#rpOdds').value=o;};});
var firstOdds=chipsA.length?parseOdds(chipsA[0].lbl):null;if(firstOdds)sh.querySelector('#rpOdds').value=firstOdds;
sh.querySelector('#rpSaveBet').onclick=function(){
var odds=rpInt(sh.querySelector('#rpOdds').value);var stake=rpNum(sh.querySelector('#rpStake').value);
var lineEl=sh.querySelector('#rpLine');var line=lineEl&&lineEl.value!==''?rpNum(lineEl.value):null;
var bookEl=sh.querySelector('.rp-pill.on');
if(isNaN(odds)||odds===0||isNaN(stake)||stake<=0){toast('Enter nonzero odds and stake');return;}
if(mkt==='spread'&&!(typeof line==='number'&&isFinite(line))){toast('Enter the spread line');return;}  /* same spread-line requirement on the card path */
var _day=pick.getAttribute('data-date')||rpEventDay(pick.getAttribute('data-commence'));
var _mlt=((lg||'').indexOf('soccer/')===0&&mkt==='ml')?'3way':null;  /* card soccer ML prices come from the books' three-way market - DNB is a separate market the card never quotes */
var bs=getBets();bs.unshift({id:Date.now(),ts:new Date().toISOString(),lg:lg,eid:pick.getAttribute('data-eid')||null,day:_day,away:away,home:home,side:side,sel:selTeam,market:mkt,line:line,mlType:_mlt,book:bookEl?bookEl.getAttribute('data-rpbook'):'',odds:odds,stake:stake,status:'open',result:null,units:null,src:'card'});
saveBets(bs);closeModal();toast('Bet tracked');renderBetsInto();};}
function manualSheet(){var h='<h3>Add a bet</h3><div class="rp-sub">Any platform, any game. Matched to live scores when possible.</div>';
h+='<div class="rp-row"><input class="rp-input" id="mAway" placeholder="Away team"><input class="rp-input" id="mHome" placeholder="Home team"></div>';
h+='<div class="rp-row"><span class="rp-pill on" id="mSideA">Away</span><span class="rp-pill" id="mSideH">Home</span></div>';
h+='<div class="rp-row"><span class="rp-pill on" id="mMktML">Moneyline</span><span class="rp-pill" id="mMktSp">Spread</span></div>';
h+='<div class="rp-row" id="mMlTypeRow" style="display:none"><span class="rp-pill on" id="mMl3">ML 3-way</span><span class="rp-pill" id="mDnb">Draw no bet</span></div>';
h+='<input class="rp-input" id="mLine" type="number" step="0.5" placeholder="Spread line (if spread)" style="display:none">';
h+='<div class="rp-row"><select class="rp-input" id="mLg">';RP_LGS.forEach(function(l){h+='<option value="'+l+'">'+l.split('/')[1].toUpperCase()+'</option>';});h+='</select><select class="rp-input" id="mBook">';RP_BOOKS.forEach(function(b){h+='<option value="'+b.k+'">'+b.n+'</option>';});h+='<option value="OTHER">Other</option></select></div>';
h+='<div class="rp-row"><input class="rp-input" id="mOdds" type="number" placeholder="Odds (e.g. -150)"><input class="rp-input" id="mStake" type="number" step="0.1" min="0" placeholder="Stake (units)"></div>';
h+='<div class="rp-sub" style="margin-top:6px">Game date (leave blank for today)</div><input class="rp-input" id="mDay" type="date">';

h+='<div class="rp-row"><input class="rp-input" id="mStakeUsd" type="number" step="0.01" min="0" placeholder="Slip stake ($)"><input class="rp-input" id="mUnitSize" type="number" step="0.01" min="0" placeholder="$ per unit (optional)"></div>';
h+='<button class="rp-btn ghost" id="mImport">Import from bet-slip screenshot</button><div id="mOcrStat" class="rp-sub" style="margin-top:6px"></div>';h+='<button class="rp-btn" id="mSave">Add bet</button>';
var sh=openSheet(h);var side='away';
sh.querySelector('#mSideA').onclick=function(){side='away';sh.querySelector('#mSideA').classList.add('on');sh.querySelector('#mSideH').classList.remove('on');};
sh.querySelector('#mSideH').onclick=function(){side='home';sh.querySelector('#mSideH').classList.add('on');sh.querySelector('#mSideA').classList.remove('on');};
var _mlTypeSync=function(){var soc=(sh.querySelector('#mLg').value||'').indexOf('soccer/')===0;var isML=sh.querySelector('#mMktML').classList.contains('on');sh.querySelector('#mMlTypeRow').style.display=(soc&&isML)?'':'none';};
sh.querySelector('#mMktML').onclick=function(){sh.querySelector('#mMktML').classList.add('on');sh.querySelector('#mMktSp').classList.remove('on');sh.querySelector('#mLine').style.display='none';_mlTypeSync();};
sh.querySelector('#mMktSp').onclick=function(){sh.querySelector('#mMktSp').classList.add('on');sh.querySelector('#mMktML').classList.remove('on');sh.querySelector('#mLine').style.display='block';_mlTypeSync();};
sh.querySelector('#mMl3').onclick=function(){sh.querySelector('#mMl3').classList.add('on');sh.querySelector('#mDnb').classList.remove('on');};
sh.querySelector('#mDnb').onclick=function(){sh.querySelector('#mDnb').classList.add('on');sh.querySelector('#mMl3').classList.remove('on');};
sh.querySelector('#mLg').onchange=_mlTypeSync;_mlTypeSync();
sh.querySelector('#mSave').onclick=function(){
var away=sh.querySelector('#mAway').value.trim(),home=sh.querySelector('#mHome').value.trim();
var mkt=sh.querySelector('#mMktSp').classList.contains('on')?'spread':'ml';
var odds=rpInt(sh.querySelector('#mOdds').value),stake=rpNum(sh.querySelector('#mStake').value);
if(isNaN(stake)||stake<=0){var _usd=rpNum((sh.querySelector('#mStakeUsd')||{value:''}).value),_ups=rpNum((sh.querySelector('#mUnitSize')||{value:''}).value);if(!isNaN(_usd)&&_usd>0&&!isNaN(_ups)&&_ups>0)stake=Math.round(_usd/_ups*100)/100;}
var line=sh.querySelector('#mLine').value!==''?rpNum(sh.querySelector('#mLine').value):null;
if(!away||!home||isNaN(odds)||odds===0||isNaN(stake)||stake<=0){toast('Fill teams, odds (nonzero), stake');return;}
if(mkt==='spread'&&!(typeof line==='number'&&isFinite(line))){toast('Enter the spread line');return;}
var _dv=(sh.querySelector('#mDay')||{value:''}).value,_day=_dv?_dv.replace(/-/g,''):null;
var _lgv=sh.querySelector('#mLg').value;
var _mlt=((_lgv||'').indexOf('soccer/')===0&&mkt==='ml')?(sh.querySelector('#mMl3').classList.contains('on')?'3way':'dnb'):null;
var bs=getBets();bs.unshift({id:Date.now(),ts:new Date().toISOString(),lg:_lgv,eid:null,day:_day,away:away,home:home,side:side,sel:side==='away'?away:home,market:mkt,line:line,mlType:_mlt,book:sh.querySelector('#mBook').value,odds:odds,stake:stake,status:'open',result:null,units:null,src:'manual'});
saveBets(bs);closeModal();toast('Bet added');renderBetsInto();}
sh.querySelector('#mImport').onclick=function(){
var fi=document.createElement('input');fi.type='file';fi.accept='image/*';
fi.onchange=function(){
if(!fi.files||!fi.files[0])return;
var stat=sh.querySelector('#mOcrStat');stat.textContent='Loading OCR engine (one-time download)...';
var s=document.createElement('script');s.src='https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js';
s.onload=function(){
stat.textContent='Reading slip...';
var url=URL.createObjectURL(fi.files[0]);
Tesseract.recognize(url,'eng').then(function(res){
var txt=(res&&res.data&&res.data.text)||'';
var oddsM=txt.match(/[+-]\d{3,4}/);
var amtM=txt.match(/\$\s?(\d+(?:\.\d{1,2})?)/);
var toWinM=txt.match(/(?:to win|payout)[^\d]*(\d+(?:\.\d{1,2})?)/i);
if(oddsM)sh.querySelector('#mOdds').value=parseInt(oddsM[0],10);
if(amtM)sh.querySelector('#mStakeUsd').value=amtM[1];
stat.textContent='Read the slip - confirm or fix the fields below. Slip $ went to the $ field: enter units, or $ per unit and I convert. (Found: '+(oddsM?oddsM[0]:'no odds')+(amtM?', $'+amtM[1]:'')+(toWinM?', to win '+toWinM[1]:'')+')';
}).catch(function(){stat.textContent='Could not read that image - enter the bet manually.';});};
s.onerror=function(){stat.textContent='OCR engine failed to load - enter the bet manually.';};
document.head.appendChild(s);};
fi.click();};
}
/* --- Settling --- */
function winUnits(odds,stake){return odds>0?stake*odds/100:stake*100/Math.abs(odds);}
function settleBet(b,ev){if(!(typeof b.odds==='number'&&isFinite(b.odds)&&b.odds!==0))return false;if(!(typeof b.stake==='number'&&isFinite(b.stake)&&b.stake>0))return false;
var cs=ev.competitions[0].competitors;var aw=null,hm=null;cs.forEach(function(c){if(c.homeAway==='away')aw=c;else hm=c;});if(!aw||!hm)return false;
var as=parseInt(aw.score,10),hs=parseInt(hm.score,10);if(isNaN(as)||isNaN(hs))return false;
var selScore=b.side==='away'?as:hs,oppScore=b.side==='away'?hs:as,res;
if(b.market==='spread'){if(!(typeof b.line==='number'&&isFinite(b.line)))return false;var adj=selScore+b.line;res=adj>oppScore?'W':(adj===oppScore?'P':'L');}
else{res=selScore>oppScore?'W':(selScore===oppScore?'P':'L');
/* swamp Sep 27: three-way soccer ML settles a draw as a LOSS - only draw-no-bet pushes.
   mlType is stamped at recording time. A LEGACY row (no mlType) that ends in a draw has unknown
   market semantics - never auto-settle it: hold it open and flag for manual review instead. */
if(res==='P'&&(b.lg||'').indexOf('soccer/')===0){
if(b.mlType==='3way')res='L';
else if(!b.mlType){b.needsReview='draw';return false;}}}
b.status='settled';b.result=res;b.units=res==='W'?winUnits(b.odds,b.stake):(res==='L'?-b.stake:0);return true;}
function rpEventDay(iso){if(!iso)return null;try{var p=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Los_Angeles',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(iso));return p.replace(/-/g,'');}catch(e){return null;}}
function rpInt(v){v=String(v==null?'':v).trim();if(!/^[+-]?\d+$/.test(v))return NaN;return parseInt(v,10);}
function rpNum(v){v=String(v==null?'':v).trim();if(!/^[+-]?(\d+(\.\d+)?|\.\d+)$/.test(v))return NaN;return parseFloat(v);}
function teamIdem(a,b){a=(a||'').toLowerCase().trim();b=(b||'').toLowerCase().trim();if(!a||!b)return false;return a===b||a.indexOf(b+' ')===0||b.indexOf(a+' ')===0;}
function betDay(b){if(b.day)return b.day;var d=new Date(b.ts);return ''+d.getFullYear()+('0'+(d.getMonth()+1)).slice(-2)+('0'+d.getDate()).slice(-2);}
function tickSettle(render){var all=getBets();var open=all.filter(function(b){return b.status==='open';});if(!open.length){if(render)render();return;}
var byKey={};open.forEach(function(b){var k=b.lg+'|'+betDay(b);(byKey[k]=byKey[k]||[]).push(b);});
var keys=Object.keys(byKey);var pending=keys.length;var changed=false;
keys.forEach(function(k){var parts=k.split('|');var url='https://site.api.espn.com/apis/site/v2/sports/'+parts[0]+'/scoreboard?limit=100&dates='+parts[1];
fetch(url).then(function(r){return r.json();}).then(function(d){
var evs=d.events||[];byKey[k].forEach(function(b){
var ev=null,i;
if(b.eid){for(i=0;i<evs.length;i++){if(String(evs[i].id)===String(b.eid)){ev=evs[i];break;}}
}else{var hits=[];for(i=0;i<evs.length;i++){var cs0=evs[i].competitions[0].competitors;var an0='',hn0='';cs0.forEach(function(c){if(c.homeAway==='away')an0=c.team.displayName;else hn0=c.team.displayName;});if(teamIdem(b.away,an0)&&teamIdem(b.home,hn0))hits.push(evs[i]);}
 if(hits.length===1)ev=hits[0];  }
if(ev){var cs=ev.competitions[0].competitors;var an='',hn='',as='',hs='';cs.forEach(function(c){if(c.homeAway==='away'){an=c.team.abbreviation;as=c.score;}else{hn=c.team.abbreviation;hs=c.score;}});b._live={an:an,as:as,hn:hn,hs:hs,det:(ev.status&&ev.status.type&&ev.status.type.shortDetail)||''};changed=true;
if(ev.status&&ev.status.type&&ev.status.type.completed){var _hadRev=!!b.needsReview;if(settleBet(b,ev))changed=true;else if(b.needsReview&&!_hadRev)changed=true;  /* swamp Sep 27 final pass: entering the review state must persist, same as a settle - else the flag dies on reload and the loop retries forever */}}});
}).catch(function(){}).finally(function(){pending--;if(pending===0){if(changed){var _latest=getBets(),_byId={};all.forEach(function(b){_byId[String(b.id)]=b;});var _merged=_latest.map(function(x){var m=_byId[String(x.id)];return (m&&x.status==='open')?m:x;});saveBets(_merged);}if(render)render();}});});}
/* --- My Bets panel --- */
function statsLine(bs){var w=0,l=0,p=0,u=0,risk=0;bs.forEach(function(b){if(b.status!=='settled')return;if(b.result==='W')w++;else if(b.result==='L')l++;else p++;u+=b.units||0;risk+=b.stake||0;});var roi=risk>0?(u/risk*100):0;return{w:w,l:l,p:p,u:u,roi:roi};}
function fmtU(u){return (u>0?'+':'')+u.toFixed(2)+'u';}
function betsSheet(){var h='<h3>My Account</h3><div class="rp-tabs"><div class="rp-tab on" id="tabBets">My Bets</div><div class="rp-tab" id="tabBooks">My Platforms</div></div><div id="rpBody"></div>';
var sh=openSheet(h);
sh.querySelector('#tabBets').onclick=function(){sh.querySelector('#tabBets').classList.add('on');sh.querySelector('#tabBooks').classList.remove('on');renderBetsInto();};
sh.querySelector('#tabBooks').onclick=function(){sh.querySelector('#tabBooks').classList.add('on');sh.querySelector('#tabBets').classList.remove('on');renderBooksInto();};
renderBetsInto();}
function renderBooksInto(){var body=document.querySelector('#rpBody');if(!body)return;var mine=myBooks();
var h='<div class="rp-sub">Your platforms: '+(mine.length?mine.map(bookName).join(', '):'none yet')+'</div><button class="rp-btn" id="rpEditBooks">Edit my platforms</button>';
body.innerHTML=h;body.querySelector('#rpEditBooks').onclick=function(){booksSheet();};}
function renderBetsInto(){var body=document.querySelector('#rpBody');if(!body)return;var bs=getBets();var st=statsLine(bs);
var h='<div class="rp-stats"><div class="rp-stat"><b>'+st.w+'-'+st.l+(st.p?'-'+st.p:'')+'</b><span>Record</span></div><div class="rp-stat"><b class="'+(st.u>=0?'rp-pos':'rp-neg')+'">'+fmtU(st.u)+'</b><span>Units</span></div><div class="rp-stat"><b>'+(st.roi>=0?'+':'')+st.roi.toFixed(1)+'%</b><span>ROI</span></div></div>';
var open=bs.filter(function(b){return b.status==='open';}),done=bs.filter(function(b){return b.status==='settled';});
if(open.length){h+='<div class="rp-sub" style="margin-bottom:6px">Open</div>';open.forEach(function(b){h+=betRow(b,true);});}
if(done.length){h+='<div class="rp-sub" style="margin:10px 0 6px">Settled</div>';done.slice(0,20).forEach(function(b){h+=betRow(b,false);});}
if(!bs.length)h+='<div class="rp-sub">No bets yet. Track one from a pick, or add one manually.</div>';
h+='<button class="rp-btn ghost" id="rpAddManual">Add a bet manually</button>';
body.innerHTML=h;
each(body.querySelectorAll('[data-grade]'),function(el){el.onclick=function(){var id=parseInt(el.getAttribute('data-grade'),10);var bs2=getBets();for(var i=0;i<bs2.length;i++){if(bs2[i].id===id){var r=el.getAttribute('data-r');bs2[i].status='settled';bs2[i].result=r;bs2[i].units=r==='W'?winUnits(bs2[i].odds,bs2[i].stake):(r==='L'?-bs2[i].stake:0);break;}}saveBets(bs2);renderBetsInto();};});
var am=body.querySelector('#rpAddManual');if(am)am.onclick=function(){manualSheet();};}
function betRow(b,isOpen){var desc=esc(b.sel)+' '+(b.market==='spread'?(b.line!==null&&b.line!==undefined?(b.line>0?'+'+b.line:b.line):'spread'):(b.mlType==='dnb'?'DNB':(b.mlType==='3way'?'ML 3-way':'ML')));
var live='';
if(isOpen&&b._live){var L=b._live;live='<div class="rp-live">'+esc(L.an)+' '+esc(L.as)+' @ '+esc(L.hn)+' '+esc(L.hs)+' &middot; '+esc(L.det)+'</div>';}
var rev=(isOpen&&b.needsReview==='draw')?'<div class="rp-live">Ended in a draw - review result (3-way ML loses, draw-no-bet pushes)</div>':'';
var right;
if(isOpen)right='<span style="white-space:nowrap"><span class="rp-pill" style="padding:3px 9px;margin:0 0 0 4px;font-size:11px" data-grade="'+b.id+'" data-r="W">W</span><span class="rp-pill" style="padding:3px 9px;margin:0 0 0 4px;font-size:11px" data-grade="'+b.id+'" data-r="L">L</span><span class="rp-pill" style="padding:3px 9px;margin:0 0 0 4px;font-size:11px" data-grade="'+b.id+'" data-r="P">P</span></span>';
else right='<b class="'+(b.units>0?'rp-pos':(b.units<0?'rp-neg':''))+'">'+fmtU(b.units||0)+'</b>';
return '<div class="rp-bet" style="display:flex;justify-content:space-between;align-items:center"><div><b>'+desc+'</b> <span style="color:#8a8f98">'+esc(bookName(b.book))+' '+(b.odds>0?'+':'')+b.odds+' &middot; '+b.stake+'u</span><div class="rp-live">'+esc(b.away)+' @ '+esc(b.home)+'</div>'+live+rev+'</div>'+right+'</div>';}
/* --- boot --- */
function boot(){
each(document.querySelectorAll('.pick[data-away][data-home]'),function(pick){
if(pick.closest('#rpFutTail'))return;  /* futures watch rows are not bet markets (no line/market data) - track-bet never attaches here (Dardan 12:31) */
if(pick.querySelector('.rp-trackbtn'))return;
var btn=document.createElement('button');btn.className='rp-trackbtn';btn.textContent='+ track bet';
btn.onclick=function(e){e.preventDefault();e.stopPropagation();trackSheet(pick);};
pick.appendChild(btn);});
personalize();
var fab=document.createElement('button');fab.className='rp-fab';fab.textContent='My Account';
fab.onclick=function(){betsSheet();tickSettle(renderBetsInto);};
var h1=document.querySelector('h1');if(h1){h1.style.position='relative';fab.style.position='absolute';fab.style.right='0';fab.style.top='50%';fab.style.transform='translateY(-50%)';h1.appendChild(fab);}else{fab.style.position='fixed';fab.style.right='12px';fab.style.top='10px';fab.style.zIndex='60';document.body.appendChild(fab);}

tickSettle(null);(function rpSettleLoop(){if(getBets().some(function(b){return b.status==='open';}))tickSettle(null);setTimeout(rpSettleLoop,modalEl?5000:60000);})();}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();

/* Wooder layout and date guard: load the existing guard when a generated index omits it. */
(function(){if(!document.querySelector('script[src^="active-day.js"]')){var s=document.createElement("script");s.src="active-day.js?v=20261010-2";document.head.appendChild(s);}function labels(){var n=document.getElementById("rpWNote");if(n)n.innerHTML=n.innerHTML.replace("and combined odds are estimates.","and combined quotes are moving-price reference snapshots.");var b=document.getElementById("rpBatchIdeas");if(b&&b.previousElementSibling)b.previousElementSibling.innerHTML=b.previousElementSibling.innerHTML.replace("No combined price is quoted.","Combined prices appear only when supplied as actual venue reference quotes.");}if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",labels);else labels();})();

/* Label stale season progress clearly, without inventing yard counts. */
(function(){function staleYards(){var b=document.getElementById("rpCmbFut");if(!b)return;b.querySelectorAll("span").forEach(function(e){if(e.textContent.trim()==="Unavailable"){e.textContent="Current yards unavailable. ESPN feed last updated Oct 5.";e.style.cssText="font-size:10px;color:#8a8f98;white-space:normal;width:175px;flex-shrink:0;text-align:right";}});}if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",staleYards);else staleYards();var o=new MutationObserver(staleYards);o.observe(document.documentElement,{childList:true,subtree:true});})();

/* No empty Wooder heading or border on NCAAF when there are no pure NCAAF tickets. */
(function(){var s=document.createElement("style");s.textContent='body.tab-ncaaf #st-wooder:not(:has(#rpTix>[data-rplg="ncaaf"])){display:none!important}';document.head.appendChild(s);})();
