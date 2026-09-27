/* RixPicks index v2 shell: intro (once/session, natural scroll, no trapping), league tabs, games+news sidebar, ticker */
(function(){
"use strict";
var TABS=window.RP_TABS||[];
function $(id){return document.getElementById(id);}
function esc(s){var M={"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"};return String(s==null?"":s).replace(/[&<>"]/g,function(c){return M[c];});}
/* ---- intro ---- */
(function(){
var intro=$('rpIntro');if(!intro){document.body.classList.add('rp-ready');return;}
var SK='rp_intro_seen',seen=false;
try{seen=!!sessionStorage.getItem(SK);}catch(e){}
if(seen){intro.remove();document.body.classList.add('rp-ready');return;}
document.body.classList.add('intro-on');
var wm=intro.querySelector('.wm');
var reduced=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
var done=false;
function consume(){
 if(done)return;done=true;
 try{sessionStorage.setItem(SK,'1');}catch(e){}
 var h=intro.offsetHeight;
 intro.remove();
 document.body.classList.remove('intro-on');
 document.body.classList.add('rp-ready');
 window.scrollBy(0,-h);
}
if(!reduced&&wm){
 var tick=false;
 window.addEventListener('scroll',function(){
  if(tick)return;tick=true;
  requestAnimationFrame(function(){
   tick=false;
   if(done)return;
   var y=window.scrollY||0;
   wm.style.transform='translateY('+(-y*0.55)+'px)';
   wm.style.opacity=String(Math.max(0,1-y/(window.innerHeight*0.75)));
  });
 },{passive:true});
}
if('IntersectionObserver' in window){
 new IntersectionObserver(function(es){es.forEach(function(en){if(en.intersectionRatio<0.35)consume();});},{threshold:[0.35]}).observe(intro);
}else{
 window.addEventListener('scroll',function(){if(window.scrollY>window.innerHeight*0.6)consume();},{passive:true});
}
})();
/* ---- tabs ---- */
var cur=null;
var TABOF={};TABS.forEach(function(t){if(t.espn)TABOF[t.espn]=t.key;});
function tailFilter(key){
 var cw=document.getElementById('rpComboTail');
 if(cw){
  var lgs=(cw.getAttribute('data-cx-espn')||'').split(',').filter(function(x){return x;});
  var ok=false;
  for(var i=0;i<lgs.length;i++)if(TABOF[lgs[i]]===key){ok=true;break;}
  cw.style.display=ok?'':'none';
 }
 var ft=document.getElementById('rpFutTail');
 if(ft){
  var kids=ft.children,sect=null,i,k,row,tk,show;
  for(i=0;i<kids.length;i++){
   k=kids[i];
   if(k.classList.contains('sect')){sect=k;k._fv=0;continue;}
   row=k.querySelector?k.querySelector('[data-espn]'):null;
   if(!row)continue;
   tk=TABOF[row.getAttribute('data-espn')];
   show=(tk===key);
   k.style.display=show?'':'none';
   if(show&&sect)sect._fv++;
  }
  for(i=0;i<kids.length;i++)if(kids[i].classList.contains('sect'))kids[i].style.display=kids[i]._fv>0?'':'none';
 }
}
function tabKey(t){return t.key;}
function activate(key,skipHash){
 var t=null,i;
 for(i=0;i<TABS.length;i++)if(TABS[i].key===key)t=TABS[i];
 if(!t)return;
 cur=t;
 document.body.className=document.body.className.replace(/\btab-[a-z0-9]+\b/g,'').trim();
 document.body.classList.add('tab-'+t.key);
 var states=document.querySelectorAll('.state');
 for(i=0;i<states.length;i++)states[i].classList.toggle('on',states[i].id==='st-'+t.key);
 var links=document.querySelectorAll('nav.rpnav .tab');
 for(i=0;i<links.length;i++)links[i].classList.toggle('active',links[i].getAttribute('data-tab')===t.key);
 document.body.classList.remove('menu-open');
 var sub=$('rpAsideSub');if(sub)sub.textContent=t.label+' \u00b7 ET';
 tailFilter(t.key);
 loadSide(t);
 if(!skipHash){try{history.replaceState(null,'','#'+t.key);}catch(e){}}
}
function fromHash(){
 var h=(location.hash||'').replace('#','').toLowerCase(),i;
 for(i=0;i<TABS.length;i++)if(TABS[i].key===h)return TABS[i].key;
 return null;
}
window.addEventListener('hashchange',function(){var k=fromHash();if(k)activate(k,true);});
document.querySelectorAll('nav.rpnav .tab').forEach(function(a){
 a.addEventListener('click',function(e){e.preventDefault();activate(a.getAttribute('data-tab'));});
});
var burger=$('burger');
if(burger)burger.addEventListener('click',function(){document.body.classList.toggle('menu-open');});
/* ---- nav record mirror (canonical values live on #rpRec/#rpUnits datasets) ---- */
function navRec(){
 var r=$('rpRec'),u=$('rpUnits'),w=$('rpNavRecW'),l=$('rpNavRecL'),uu=$('rpNavU');
 if(r&&w&&l){w.textContent=r.dataset.bw||'';l.textContent=r.dataset.bl||'';}
 if(u&&uu)uu.textContent=(u.dataset.bu||'')+'u';
}
navRec();
if('MutationObserver' in window){
 var mo=new MutationObserver(navRec);
 ['rpRec','rpUnits'].forEach(function(id){var n=$(id);if(n)mo.observe(n,{attributes:true,attributeFilter:['data-bw','data-bl','data-bu']});});
}
/* ---- sidebar: games + news (ESPN free endpoints; failure states honest, never fabricated) ---- */
var SB={},NEWS={},SB_TS={},NEWS_TS={};
function lgpath(t){return t.espn||'';}
function ordinal(p){p=parseInt(p,10);if(!p)return '';if(p<=4)return p+(['th','st','nd','rd'][p]||'th');return p===5?'OT':(p-4)+'OT';}
function ago(iso){
 var t=Date.parse(iso);if(!t)return '';
 var s=Math.max(0,(Date.now()-t)/1000);
 if(s<90)return '1m ago';
 if(s<3600)return Math.round(s/60)+'m ago';
 if(s<86400)return Math.round(s/3600)+'h ago';
 return Math.round(s/86400)+'d ago';
}
function until(iso){
 var t=Date.parse(iso);if(!t)return '';
 var s=(t-Date.now())/1000;
 if(s<=0)return 'soon';
 if(s<3600)return 'in '+Math.max(1,Math.round(s/60))+'m';
 if(s<86400)return 'in '+Math.floor(s/3600)+'h '+Math.round((s%3600)/60)+'m';
 return Math.round(s/86400)+'d';
}
function dayTime(iso){
 try{return new Date(iso).toLocaleString('en-US',{timeZone:'America/New_York',weekday:'short',hour:'numeric',minute:'2-digit'});}catch(e){return '';}
}
function renderGames(t,events){
 var box=$('rpGames');if(!box)return;
 if(!events||!events.length){box.innerHTML='<div class="empty">No games listed right now.</div>';return;}
 var rows=[],i,ev,c,st,comps,away,home,txt,sub,when,cls;
 events=events.slice();
 events.sort(function(a,b){
  var sa=(((a.competitions||[])[0]||{}).status||{}).type||{},sb=(((b.competitions||[])[0]||{}).status||{}).type||{};
  var ra=sa.state==='in'?0:(sa.state==='pre'?1:2),rb=sb.state==='in'?0:(sb.state==='pre'?1:2);
  if(ra!==rb)return ra-rb;
  return Date.parse(a.date||0)-Date.parse(b.date||0);
 });
 for(i=0;i<events.length&&rows.length<9;i++){
  ev=events[i];c=(ev.competitions||[])[0]||{};st=c.status||{};comps=c.competitors||[];
  away=comps.filter(function(x){return x.homeAway==='away';})[0]||{};
  home=comps.filter(function(x){return x.homeAway==='home';})[0]||{};
  var an=(away.team||{}).abbreviation||'',hn=(home.team||{}).abbreviation||'';
  if(st.type&&st.type.state==='in'){
   txt=esc(an)+' '+(away.score!=null?esc(away.score):'\u2014')+' - '+(home.score!=null?esc(home.score):'\u2014')+' '+esc(hn);
   sub=esc(st.type.shortDetail||st.type.detail||'');
   when='<span class="when live"><span class="dot"></span>LIVE</span>';
  }else if(st.type&&st.type.state==='post'){
   txt=esc(an)+' '+(away.score!=null?esc(away.score):'\u2014')+' - '+(home.score!=null?esc(home.score):'\u2014')+' '+esc(hn);
   sub='Final';
   when='<span class="when fin">FINAL</span>';
  }else{
   txt=esc(an)+' @ '+esc(hn);
   sub=esc(dayTime(ev.date));
   when='<span class="when">'+esc(until(ev.date))+'</span>';
  }
  rows.push('<div class="grow"><div><div class="gname">'+txt+'</div><div class="gsub">'+sub+'</div></div>'+when+'</div>');
 }
 box.innerHTML=rows.join('')||'<div class="empty">No games listed right now.</div>';
}
function renderNews(t,arts){
 var box=$('rpNews');if(!box)return;
 if(!arts||!arts.length){box.innerHTML='<div class="empty">News unavailable right now.</div>';return;}
 var h='';
 arts.slice(0,3).forEach(function(a){
  var u=((a.links||{}).web||{}).href||'';
  var inner='<span class="src espn">ESPN</span><span class="ntxt">'+esc(a.headline||'')+'</span><div class="nts">'+esc(ago(a.published))+' \u00b7 espn.com</div>';
  h+='<div class="nitem">'+(u?'<a href="'+esc(u)+'" target="_blank" rel="noreferrer">'+inner+'</a>':inner)+'</div>';
 });
 box.innerHTML=h;
}
var KALW=window.RP_KAL_WATCH||[];
var KALD={},KALD_TS={},KALIN={};
function kalHasSfx(tick,sfx){return !!sfx&&tick.length>sfx.length&&tick.slice(-(sfx.length+1))===('-'+sfx);}
function kalItemsFor(t,cb){
 if(!KALW.length||!t||!t.espn)return cb([]);
 var out=[],pend=0,done=false;
 var fin=function(){if(!done){done=true;cb(out);}};
 KALW.forEach(function(w){
  if(w.lg!==t.espn)return;
  var ck=w.ev;
  var use=function(d){
   var ks=(d&&d.markets&&d.markets.kalshi&&d.markets.kalshi.markets)||[];
   var m=null,i;
   for(i=0;i<ks.length;i++)if(kalHasSfx(ks[i].ticker||'',w.sfx)){m=ks[i];break;}
   if(!m)return;
   var px=(m.yesAsk!=null&&m.yesAsk>0)?m.yesAsk:m.lastTrade;
   if(px==null||px<=0)return;
   var dd=px-w.entry;
   var verb=Math.abs(dd)<=1?'steady at':(dd>0?'up to':'down to');
   out.push('<span class="titem"><span class="tsrc kalshi">KALSHI</span>'+esc(w.awa+'-'+w.hom+' winner '+verb+' '+px+'c')+'</span><span class="tsep">\u00b7</span>');
  };
  if(KALD[ck]&&Date.now()-(KALD_TS[ck]||0)<600000){use(KALD[ck]);return;}
  if(KALIN[ck])return;
  KALIN[ck]=1;pend++;
  fetch('https://api.rix-picks.com/feed/game/'+w.eid+'?league='+encodeURIComponent(w.lg)+'&kalshi='+encodeURIComponent(w.ev),{cache:'no-store'})
   .then(function(r){if(!r.ok)throw 0;return r.json();})
   .then(function(j){KALD[ck]=j;var ok=!!(j&&j.markets&&j.markets.kalshi&&j.markets.kalshi.httpOk);KALD_TS[ck]=Date.now()-(ok?0:540000);use(j);})
   .catch(function(){})
   .finally(function(){delete KALIN[ck];pend--;if(pend<=0)fin();});
 });
 if(pend===0)fin();
}
function tickRender(){
 var tr=$('rpTickTrack'),bar=$('rpTickBar');if(!tr||!bar)return;
 var arts=NEWS[cur?cur.key:'']||[];
 kalItemsFor(cur,function(kal){
  if(!arts.length&&!kal.length){bar.style.display='none';return;}
  bar.style.display='';
  var h='';
  arts.slice(0,4).forEach(function(a){
   var u=((a.links||{}).web||{}).href||'';
   h+='<'+(u?'a class="titem" href="'+esc(u)+'" target="_blank" rel="noreferrer"':'span class="titem"')+'><span class="tsrc espn">ESPN</span>'+esc(a.headline||'')+'</'+(u?'a':'span')+'><span class="tsep">\u00b7</span>';
  });
  h+=kal.join('');
  tr.innerHTML=h+h;
 });
}
function loadSide(t){
 var lg=lgpath(t);if(!lg)return;
 var now=Date.now();
 if(SB[t.key]&&now-(SB_TS[t.key]||0)<60000){renderGames(t,SB[t.key]);}
 else{
  fetch('https://site.api.espn.com/apis/site/v2/sports/'+lg+'/scoreboard?limit=50',{cache:'no-store'})
   .then(function(r){if(!r.ok)throw 0;return r.json();})
   .then(function(j){SB[t.key]=j.events||[];SB_TS[t.key]=Date.now();if(cur===t)renderGames(t,SB[t.key]);})
   .catch(function(){if(cur===t)renderGames(t,SB[t.key]||null);});
 }
 if(NEWS[t.key]&&now-(NEWS_TS[t.key]||0)<600000){renderNews(t,NEWS[t.key]);tickRender();}
 else{
  fetch('https://site.api.espn.com/apis/site/v2/sports/'+lg+'/news?limit=4',{cache:'no-store'})
   .then(function(r){if(!r.ok)throw 0;return r.json();})
   .then(function(j){NEWS[t.key]=j.articles||[];NEWS_TS[t.key]=Date.now();if(cur===t){renderNews(t,NEWS[t.key]);tickRender();}})
   .catch(function(){if(cur===t){renderNews(t,NEWS[t.key]||null);tickRender();}});
 }
}
setInterval(function(){if(cur&&!document.hidden)loadSide(cur);},60000);
/* ---- boot ---- */
var start=fromHash();
if(!start){
 for(var i=0;i<TABS.length;i++){var p=$('st-'+TABS[i].key);if(p&&p.querySelector('.pick:not(.rp-empty)')){start=TABS[i].key;break;}}
 if(!start&&TABS.length)start=TABS[0].key;
}
if(start)activate(start,true);
else document.body.classList.add('rp-ready');
if(!document.body.classList.contains('intro-on'))document.body.classList.add('rp-ready');
})();
