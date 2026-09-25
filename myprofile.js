/* RixPicks local profile: My Books + My Bets (on-device, no accounts) */
(function(){
var RP_BOOKS=[{k:'DK',n:'DraftKings'},{k:'FD',n:'FanDuel'},{k:'ESPN',n:'ESPN BET'},{k:'MGM',n:'BetMGM'},{k:'HR',n:'Hard Rock'},{k:'BR',n:'BetRivers'},{k:'KAL',n:'Kalshi'},{k:'POLY',n:'Polymarket'},{k:'B365',n:'bet365'},{k:'FAN',n:'Fanatics'}];
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
'.rp-fab{background:#16181d;border:1px solid rgba(127,127,127,.35);color:#e8b10a;font-weight:700;border-radius:14px;padding:4px 10px;font-size:11px;cursor:pointer;white-space:nowrap;margin-left:10px;flex-shrink:0}'+
'.rp-modal{position:fixed;top:0;left:0;right:0;bottom:0;z-index:70;background:rgba(0,0,0,.6);display:flex;align-items:flex-end;justify-content:center}'+
'.rp-sheet{background:#16181d;border:1px solid rgba(127,127,127,.3);border-bottom:none;border-radius:16px 16px 0 0;width:100%;max-width:520px;max-height:82vh;overflow-y:auto;padding:16px;color:#e6e8eb;font-family:inherit}'+
'.rp-sheet h3{margin:0 0 4px;font-size:16px}.rp-sub{color:#8a8f98;font-size:12px;margin-bottom:12px}'+
'.rp-pill{display:inline-block;margin:0 6px 8px 0;padding:8px 13px;border-radius:18px;border:1px solid rgba(127,127,127,.35);background:#101216;color:#c9cdd4;font-size:13px;cursor:pointer}'+
'.rp-pill.on{border-color:#e8b10a;color:#e8b10a;background:rgba(232,177,10,.08)}'+
'.rp-btn{display:block;width:100%;padding:12px;border:none;border-radius:10px;background:#e8b10a;color:#111;font-weight:700;font-size:14px;cursor:pointer;margin-top:10px}'+
'.rp-btn.ghost{background:transparent;color:#8a8f98;border:1px solid rgba(127,127,127,.3)}'+
'.rp-tabs{display:flex;gap:8px;margin-bottom:12px}.rp-tab{flex:1;text-align:center;padding:8px;border-radius:9px;border:1px solid rgba(127,127,127,.3);color:#8a8f98;font-size:13px;cursor:pointer}.rp-tab.on{color:#e8b10a;border-color:#e8b10a}'+
'.rp-bet{border:1px solid rgba(127,127,127,.22);border-radius:12px;padding:10px 12px;margin-bottom:8px;font-size:13px}'+
'.rp-bet .rp-live{color:#8a8f98;font-size:12px;margin-top:3px}'+
'.rp-pos{color:#3fb950}.rp-neg{color:#e5484d}'+
'.rp-input{width:100%;box-sizing:border-box;background:#101216;border:1px solid rgba(127,127,127,.35);border-radius:9px;color:#e6e8eb;padding:9px;font-size:14px;margin-bottom:8px}'+
'.rp-row{display:flex;gap:8px}.rp-row>*{flex:1}'+
'.chip.rpmine{border-color:#e8b10a !important;box-shadow:0 0 0 1px #e8b10a inset}'+
'.chip.rpdim{opacity:.45}'+
'.rp-trackbtn{display:inline-block;margin:4px 0 0;font-size:11px;color:#8a8f98;border:1px solid rgba(127,127,127,.3);border-radius:14px;padding:3px 10px;cursor:pointer;background:transparent}'+
'.rp-stats{display:flex;gap:14px;font-size:13px;color:#c9cdd4;margin-bottom:12px;flex-wrap:wrap}.rp-stats b{color:#e8b10a}';
document.head.appendChild(css);
var modalEl=null;
function closeModal(){if(modalEl){modalEl.remove();modalEl=null;}}
function openSheet(html){closeModal();modalEl=document.createElement('div');modalEl.className='rp-modal';modalEl.innerHTML='<div class="rp-sheet">'+html+'</div>';modalEl.addEventListener('click',function(e){if(e.target===modalEl)closeModal();});document.body.appendChild(modalEl);return modalEl.firstChild;}
function toast(msg){var t=document.createElement('div');t.textContent=msg;t.style.cssText='position:fixed;left:50%;bottom:70px;transform:translateX(-50%);background:#16181d;border:1px solid #e8b10a;color:#e8b10a;padding:8px 16px;border-radius:18px;font-size:13px;z-index:80';document.body.appendChild(t);setTimeout(function(){t.remove();},2200);}
/* --- My Books --- */
function personalize(){var mine=myBooks();each(document.querySelectorAll('.chips'),function(c){var kids=Array.prototype.slice.call(c.querySelectorAll('.chip'));if(!kids.length)return;if(!mine.length){kids.forEach(function(ch){ch.classList.remove('rpmine');ch.classList.remove('rpdim');});return;}kids.sort(function(a,b){var am=mine.indexOf(a.getAttribute('data-book')||'')>=0?0:1;var bm=mine.indexOf(b.getAttribute('data-book')||'')>=0?0:1;return am-bm;});kids.forEach(function(ch){var m=mine.indexOf(ch.getAttribute('data-book')||'')>=0;ch.classList.toggle('rpmine',m);ch.classList.toggle('rpdim',!m);c.appendChild(ch);});});}
function booksSheet(){var sel=myBooks().slice();var sh=openSheet('<h3>My Platforms</h3><div class="rp-sub">Tap the platforms you use. Picks highlight yours first - linked account sync lands here.</div><div id="rpPills"></div><button class="rp-btn" id="rpSaveBooks">Save</button>'+(sel.length?'<button class="rp-btn ghost" id="rpClearBooks">Clear my platforms</button>':''));
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
if(chipsA.length){h+='<div class="rp-sub" style="margin-bottom:6px">Book (yours first):</div>';chipsA.forEach(function(c,i){h+='<span class="rp-pill'+(i===0?' on':'')+'" data-rpbook="'+esc(c.book)+'" data-rpodds="'+(parseOdds(c.lbl)||'')+'">'+esc(c.lbl)+'</span>';});}
h+='<div class="rp-row" style="margin-top:6px"><input class="rp-input" id="rpOdds" type="number" placeholder="Odds (e.g. -150)"><input class="rp-input" id="rpStake" type="number" step="0.1" min="0" placeholder="Stake (units)"></div>';
if(mkt==='spread')h+='<input class="rp-input" id="rpLine" type="number" step="0.5" placeholder="Spread line (e.g. -3.5)">';
h+='<button class="rp-btn" id="rpSaveBet">Track bet</button>';
var sh=openSheet(h);
each(sh.querySelectorAll('.rp-pill'),function(p){p.onclick=function(){each(sh.querySelectorAll('.rp-pill'),function(x){x.classList.remove('on');});p.classList.add('on');var o=p.getAttribute('data-rpodds');if(o)sh.querySelector('#rpOdds').value=o;};});
var firstOdds=chipsA.length?parseOdds(chipsA[0].lbl):null;if(firstOdds)sh.querySelector('#rpOdds').value=firstOdds;
sh.querySelector('#rpSaveBet').onclick=function(){
var odds=parseInt(sh.querySelector('#rpOdds').value,10);var stake=parseFloat(sh.querySelector('#rpStake').value);
var lineEl=sh.querySelector('#rpLine');var line=lineEl&&lineEl.value!==''?parseFloat(lineEl.value):null;
var bookEl=sh.querySelector('.rp-pill.on');
if(isNaN(odds)||isNaN(stake)||stake<=0){toast('Enter odds and stake');return;}
var bs=getBets();bs.unshift({id:Date.now(),ts:new Date().toISOString(),lg:lg,away:away,home:home,side:side,sel:selTeam,market:mkt,line:line,book:bookEl?bookEl.getAttribute('data-rpbook'):'',odds:odds,stake:stake,status:'open',result:null,units:null,src:'card'});
saveBets(bs);closeModal();toast('Bet tracked');renderBetsInto();};}
function manualSheet(){var h='<h3>Add a bet</h3><div class="rp-sub">Any platform, any game. Matched to live scores when possible.</div>';
h+='<div class="rp-row"><input class="rp-input" id="mAway" placeholder="Away team"><input class="rp-input" id="mHome" placeholder="Home team"></div>';
h+='<div class="rp-row"><span class="rp-pill on" id="mSideA">Away</span><span class="rp-pill" id="mSideH">Home</span></div>';
h+='<div class="rp-row"><span class="rp-pill on" id="mMktML">Moneyline</span><span class="rp-pill" id="mMktSp">Spread</span></div>';
h+='<input class="rp-input" id="mLine" type="number" step="0.5" placeholder="Spread line (if spread)" style="display:none">';
h+='<div class="rp-row"><select class="rp-input" id="mLg">';RP_LGS.forEach(function(l){h+='<option value="'+l+'">'+l.split('/')[1].toUpperCase()+'</option>';});h+='</select><select class="rp-input" id="mBook">';RP_BOOKS.forEach(function(b){h+='<option value="'+b.k+'">'+b.n+'</option>';});h+='<option value="OTHER">Other</option></select></div>';
h+='<div class="rp-row"><input class="rp-input" id="mOdds" type="number" placeholder="Odds (e.g. -150)"><input class="rp-input" id="mStake" type="number" step="0.1" min="0" placeholder="Stake (units)"></div>';
h+='<button class="rp-btn ghost" id="mImport">Import from bet-slip screenshot</button><div id="mOcrStat" class="rp-sub" style="margin-top:6px"></div>';h+='<button class="rp-btn" id="mSave">Add bet</button>';
var sh=openSheet(h);var side='away';
sh.querySelector('#mSideA').onclick=function(){side='away';sh.querySelector('#mSideA').classList.add('on');sh.querySelector('#mSideH').classList.remove('on');};
sh.querySelector('#mSideH').onclick=function(){side='home';sh.querySelector('#mSideH').classList.add('on');sh.querySelector('#mSideA').classList.remove('on');};
sh.querySelector('#mMktML').onclick=function(){sh.querySelector('#mMktML').classList.add('on');sh.querySelector('#mMktSp').classList.remove('on');sh.querySelector('#mLine').style.display='none';};
sh.querySelector('#mMktSp').onclick=function(){sh.querySelector('#mMktSp').classList.add('on');sh.querySelector('#mMktML').classList.remove('on');sh.querySelector('#mLine').style.display='block';};
sh.querySelector('#mSave').onclick=function(){
var away=sh.querySelector('#mAway').value.trim(),home=sh.querySelector('#mHome').value.trim();
var mkt=sh.querySelector('#mMktSp').classList.contains('on')?'spread':'ml';
var odds=parseInt(sh.querySelector('#mOdds').value,10),stake=parseFloat(sh.querySelector('#mStake').value);
var line=sh.querySelector('#mLine').value!==''?parseFloat(sh.querySelector('#mLine').value):null;
if(!away||!home||isNaN(odds)||isNaN(stake)||stake<=0){toast('Fill teams, odds, stake');return;}
var bs=getBets();bs.unshift({id:Date.now(),ts:new Date().toISOString(),lg:sh.querySelector('#mLg').value,away:away,home:home,side:side,sel:side==='away'?away:home,market:mkt,line:line,book:sh.querySelector('#mBook').value,odds:odds,stake:stake,status:'open',result:null,units:null,src:'manual'});
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
if(amtM)sh.querySelector('#mStake').value=amtM[1];
stat.textContent='Read the slip - confirm or fix the fields below, then Add bet. (Found: '+(oddsM?oddsM[0]:'no odds')+(amtM?', $'+amtM[1]:'')+(toWinM?', to win '+toWinM[1]:'')+')';
}).catch(function(){stat.textContent='Could not read that image - enter the bet manually.';});};
s.onerror=function(){stat.textContent='OCR engine failed to load - enter the bet manually.';};
document.head.appendChild(s);};
fi.click();};
}
/* --- Settling --- */
function winUnits(odds,stake){return odds>0?stake*odds/100:stake*100/Math.abs(odds);}
function settleBet(b,ev){var cs=ev.competitions[0].competitors;var aw=null,hm=null;cs.forEach(function(c){if(c.homeAway==='away')aw=c;else hm=c;});if(!aw||!hm)return false;
var as=parseInt(aw.score,10),hs=parseInt(hm.score,10);if(isNaN(as)||isNaN(hs))return false;
var selScore=b.side==='away'?as:hs,oppScore=b.side==='away'?hs:as,res;
if(b.market==='spread'&&b.line!==null&&b.line!==undefined){var adj=selScore+b.line;res=adj>oppScore?'W':(adj===oppScore?'P':'L');}
else res=selScore>oppScore?'W':(selScore===oppScore?'P':'L');
b.status='settled';b.result=res;b.units=res==='W'?winUnits(b.odds,b.stake):(res==='L'?-b.stake:0);return true;}
function teamMatch(a,b){a=(a||'').toLowerCase();b=(b||'').toLowerCase();if(!a||!b)return false;return a===b||a.indexOf(b)>=0||b.indexOf(a.indexOf(' ')>-1?a.split(' ').pop():a)>=0;}
function tickSettle(render){var open=getBets().filter(function(b){return b.status==='open';});if(!open.length){if(render)render();return;}
var byLg={};open.forEach(function(b){(byLg[b.lg]=byLg[b.lg]||[]).push(b);});
var lgs=Object.keys(byLg);var pending=lgs.length;var changed=false;
lgs.forEach(function(lg){var url='https://site.api.espn.com/apis/site/v2/sports/'+lg+'/scoreboard?limit=100';
fetch(url).then(function(r){return r.json();}).then(function(d){
var evs=d.events||[];byLg[lg].forEach(function(b){
for(var i=0;i<evs.length;i++){var ev=evs[i];var cs=ev.competitions[0].competitors;var an='',hn='';cs.forEach(function(c){if(c.homeAway==='away')an=c.team.displayName;else hn=c.team.displayName;});
if(teamMatch(b.away,an)&&teamMatch(b.home,hn)){b._ev=ev;if(ev.status&&ev.status.type&&ev.status.type.completed){if(settleBet(b,ev))changed=true;}break;}}});
}).catch(function(){}).finally(function(){pending--;if(pending===0){if(changed)saveBets(getBets());if(render)render();}});});}
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
var h='<div class="rp-stats"><span>Record <b>'+st.w+'-'+st.l+(st.p?'-'+st.p:'')+'</b></span><span>Units <b class="'+(st.u>=0?'rp-pos':'rp-neg')+'">'+fmtU(st.u)+'</b></span><span>ROI <b>'+(st.roi>=0?'+':'')+st.roi.toFixed(1)+'%</b></span></div>';
var open=bs.filter(function(b){return b.status==='open';}),done=bs.filter(function(b){return b.status==='settled';});
if(open.length){h+='<div class="rp-sub" style="margin-bottom:6px">Open</div>';open.forEach(function(b){h+=betRow(b,true);});}
if(done.length){h+='<div class="rp-sub" style="margin:10px 0 6px">Settled</div>';done.slice(0,20).forEach(function(b){h+=betRow(b,false);});}
if(!bs.length)h+='<div class="rp-sub">No bets yet. Track one from a pick, or add one manually.</div>';
h+='<button class="rp-btn ghost" id="rpAddManual">Add a bet manually</button>';
body.innerHTML=h;
each(body.querySelectorAll('[data-grade]'),function(el){el.onclick=function(){var id=parseInt(el.getAttribute('data-grade'),10);var bs2=getBets();for(var i=0;i<bs2.length;i++){if(bs2[i].id===id){var r=el.getAttribute('data-r');bs2[i].status='settled';bs2[i].result=r;bs2[i].units=r==='W'?winUnits(bs2[i].odds,bs2[i].stake):(r==='L'?-bs2[i].stake:0);break;}}saveBets(bs2);renderBetsInto();};});
var am=body.querySelector('#rpAddManual');if(am)am.onclick=function(){manualSheet();};}
function betRow(b,isOpen){var desc=esc(b.sel)+' '+(b.market==='spread'?(b.line!==null&&b.line!==undefined?(b.line>0?'+'+b.line:b.line):'spread'):'ML');
var live='';
if(isOpen&&b._ev){try{var cs=b._ev.competitions[0].competitors;var an='',hn='',as='',hs='';cs.forEach(function(c){if(c.homeAway==='away'){an=c.team.abbreviation;as=c.score;}else{hn=c.team.abbreviation;hs=c.score;}});
live='<div class="rp-live">'+esc(an)+' '+esc(as)+' @ '+esc(hn)+' '+esc(hs)+' &middot; '+esc(b._ev.status.type.shortDetail||'')+'</div>';}catch(e){}}
var right;
if(isOpen)right='<span style="white-space:nowrap"><span class="rp-pill" style="padding:3px 9px;margin:0 0 0 4px;font-size:11px" data-grade="'+b.id+'" data-r="W">W</span><span class="rp-pill" style="padding:3px 9px;margin:0 0 0 4px;font-size:11px" data-grade="'+b.id+'" data-r="L">L</span><span class="rp-pill" style="padding:3px 9px;margin:0 0 0 4px;font-size:11px" data-grade="'+b.id+'" data-r="P">P</span></span>';
else right='<b class="'+(b.units>0?'rp-pos':(b.units<0?'rp-neg':''))+'">'+fmtU(b.units||0)+'</b>';
return '<div class="rp-bet" style="display:flex;justify-content:space-between;align-items:center"><div><b>'+desc+'</b> <span style="color:#8a8f98">'+esc(bookName(b.book))+' '+(b.odds>0?'+':'')+b.odds+' &middot; '+b.stake+'u</span><div class="rp-live">'+esc(b.away)+' @ '+esc(b.home)+'</div>'+live+'</div>'+right+'</div>';}
/* --- boot --- */
function boot(){
each(document.querySelectorAll('.pick[data-away][data-home]'),function(pick){
if(pick.querySelector('.rp-trackbtn'))return;
var btn=document.createElement('button');btn.className='rp-trackbtn';btn.textContent='+ track bet';
btn.onclick=function(e){e.preventDefault();e.stopPropagation();trackSheet(pick);};
pick.appendChild(btn);});
personalize();
var fab=document.createElement('button');fab.className='rp-fab';fab.textContent='My Account';
fab.onclick=function(){betsSheet();tickSettle(renderBetsInto);};
var h1=document.querySelector('h1');if(h1){h1.style.position='relative';fab.style.position='absolute';fab.style.right='0';fab.style.top='50%';fab.style.transform='translateY(-50%)';h1.appendChild(fab);}else{fab.style.position='fixed';fab.style.right='12px';fab.style.top='10px';fab.style.zIndex='60';document.body.appendChild(fab);}
if(!ls('rp_books_asked',null)&&!myBooks().length){setTimeout(function(){booksSheet();},900);}
tickSettle(null);setInterval(function(){tickSettle(null);},60000);}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
