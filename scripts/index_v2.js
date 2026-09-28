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
  cw.style.display=(key==='home'||ok)?'':'none';
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
   show=(key==='home'||tk===key);
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
 var sub=$('rpAsideSub');if(sub)sub.textContent=t.label+' · PT';
 tailFilter(t.key);
 loadSide(t);
 if(!skipHash){try{history.replaceState(null,'','#'+t.key);}catch(e){}}
 try{localStorage.setItem('rp_tab',t.key);}catch(e){}
 /* tester Sep 27 (Phillies/Brewers repro): rpBestStar/rpLineShop skip chips on hidden panels
    (offsetParent gate), so a freshly activated panel carried no star/range until the next 30s
    tick. Recompute both on every tab activation; guarded - these exist only on the card page. */
 if(typeof rpAllBest==='function')rpAllBest();
 if(typeof rpAllLineShops==='function')rpAllLineShops();
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
/* record strip -> record panel (owner 10:55): tap opens the record view with the units
   math under the units P/L; tap again / outside / Escape closes. Works from every tab. */
var navRecBtn=$('rpNavRec'),recPop=$('rpRecPop');
if(navRecBtn&&recPop){
 var setPop=function(open){recPop.hidden=!open;navRecBtn.setAttribute('aria-expanded',open?'true':'false');};
 navRecBtn.addEventListener('click',function(e){e.preventDefault();e.stopPropagation();setPop(recPop.hidden);});
 document.addEventListener('click',function(e){if(!recPop.hidden&&!recPop.contains(e.target)&&!navRecBtn.contains(e.target))setPop(false);});
 document.addEventListener('keydown',function(e){if(e.key==='Escape'&&!recPop.hidden)setPop(false);});
}
var burger=$('burger');
if(burger)burger.addEventListener('click',function(){document.body.classList.toggle('menu-open');});
/* ---- nav record mirror (canonical values live on #rpRec/#rpUnits datasets) ---- */
function navRec(){
 var r=$('rpRec'),u=$('rpUnits'),w=$('rpNavRecW'),l=$('rpNavRecL'),uu=$('rpNavU'),pc=$('rpNavPct');
 if(r&&w&&l){w.textContent=r.dataset.bw||'';l.textContent=r.dataset.bl||'';}
 if(r&&pc){var bw=parseInt(r.dataset.bw||'0',10),bl=parseInt(r.dataset.bl||'0',10);if(bw+bl>0)pc.textContent=(100*bw/(bw+bl)).toFixed(2)+'%';}
 if(u&&uu){var uv=parseFloat(u.dataset.bu||'0');uu.textContent=(uv>=0?'+':'')+uv.toFixed(2)+'u';}
}
navRec();
if('MutationObserver' in window){
 var mo=new MutationObserver(navRec);
 ['rpRec','rpUnits'].forEach(function(id){var n=$(id);if(n)mo.observe(n,{attributes:true,attributeFilter:['data-bw','data-bl','data-bu']});});
}
/* ---- sidebar: games + news (ESPN free endpoints; failure states honest, never fabricated) ---- */
var SB={},NEWS={},SB_TS={},NEWS_TS={};
/* leagues with a verified live-tracking route (live.html) - rows for anything else stay untappable (fail closed; boxing has no working ESPN route 12:30) */
var RP_LIVE_OK={'football/nfl':1,'football/college-football':1,'basketball/nba':1,'basketball/wnba':1,'basketball/college-basketball':1,'basketball/mens-college-basketball':1,'basketball/womens-college-basketball':1,'baseball/mlb':1,'hockey/nhl':1,'tennis/atp':1,'tennis/wta':1,'soccer/usa.1':1,'soccer/usa.nwsl':1,'golf/pga':1,'racing/nascar':1,'racing/nascar-premier':1,'mma/ufc':1};
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
 try{return new Date(iso).toLocaleString('en-US',{timeZone:'America/Los_Angeles',weekday:'short',hour:'numeric',minute:'2-digit'})+' PT';}catch(e){return '';}  /* all-times-PT rule (owner 9/27): sidebar game times render PT with explicit label, same convention as ptLabel elsewhere */
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
  var an=(away.team||{}).abbreviation||(away.team||{}).shortDisplayName||(away.team||{}).displayName||(away.athlete||{}).shortName||(away.athlete||{}).displayName||'',hn=(home.team||{}).abbreviation||(home.team||{}).shortDisplayName||(home.team||{}).displayName||(home.athlete||{}).shortName||(home.athlete||{}).displayName||'';
  if(st.type&&st.type.state==='in'){
   txt=esc(an)+' '+(away.score!=null?esc(away.score):'\u2014')+' - '+(home.score!=null?esc(home.score):'\u2014')+' '+esc(hn);
   sub=esc(st.type.shortDetail||st.type.detail||'');
   when='<span class="when live"><span class="dot"></span>LIVE</span>';
  }else if(st.type&&st.type.state==='post'){
   txt=esc(an)+' '+(away.score!=null?esc(away.score):'\u2014')+' - '+(home.score!=null?esc(home.score):'\u2014')+' '+esc(hn);
   sub='Final';
   when='<span class="when fin">FINAL</span>';
  }else{
   txt=(an&&hn)?(esc(an)+' @ '+esc(hn)):esc(ev.shortName||ev.name||'');
   sub=esc(dayTime(ev.date));
   when='<span class="when">'+esc(until(ev.date))+'</span>';
  }
  var _row='<div class="grow"><div><div class="gname">'+txt+'</div><div class="gsub">'+sub+'</div></div>'+when+'</div>';
  rows.push((ev.id&&RP_LIVE_OK[lgpath(t)])?('<a class="growtap" href="live.html?espn='+encodeURIComponent(lgpath(t))+'&eid='+encodeURIComponent(ev.id)+'" style="display:block;text-decoration:none;color:inherit">'+_row+'</a>'):_row);
 }
 box.innerHTML=rows.join('')||'<div class="empty">No games listed right now.</div>';
}
function srcDom(s){return s==='X'?'via X':(s==='CBS'?'cbssports.com':(s==='YAHOO'?'sports.yahoo.com':'espn.com'));}
function unesc(s){var t=document.createElement('textarea');t.innerHTML=String(s==null?'':s);return t.value;}  /* swamp 1:09: feeds ship HTML-encoded headlines (Jets&#39;) - decode before esc() or they double-escape */
function normH(h){return String(h||'').toLowerCase().replace(/[^a-z0-9]+/g,' ').replace(/^\s+|\s+$/g,'');}
function newsBucket(t){
 /* instant lane (Dardan 1:13: no lag on news dropping): the visible league's bucket merges
    the 5-min server file with a direct 25s ESPN poll from the page - new ESPN stories render
    within ~30s of publish; CBS/Yahoo lanes arrive on the server cadence. */
 var out=[];
 if(NEWSF&&NEWSF.leagues){
  var L=NEWSF.leagues;
  if(t.key==='home'||t.key==='wooder'||t.key==='past'){out=[];Object.keys(L).forEach(function(k){out=out.concat(L[k]||[]);});if(!out.length)out=(NEWSF.latest||[]).slice();}
  else if(t.key==='tennis'){out=(L['tennis/atp']||[]).concat(L['tennis/wta']||[]);}
  else if(t.key==='ufcboxing'){out=(L['mma/ufc']||[]).concat(L['boxing']||[]);}
  else out=L[t.espn]||[];
  if(!out.length)out=(NEWSF.latest||[]).slice(); /* owner 12:29: empty news on a live tab is a bug - fall back to all-sources latest */
  out=out.slice();
 }
 out=out.concat(DNEWS[t.key]||[]);
 /* XNEWS intentionally NOT merged: X posts get their own Home social section (owner 10:32); news is articles only. XNEWS stays populated for that consumer. */
 out.sort(function(a,b){return Date.parse(b.published||0)-Date.parse(a.published||0);});
 var seen={},seenP={},ded=[];
 out.forEach(function(a){var n=normH(a.headline);if(!n)return;var pk=n.slice(0,40);if(seen[n]||seenP[pk])return;seen[n]=1;seenP[pk]=1;ded.push(a);});
 return ded;
}
var CAR_SIG='',CAR_IDX=0,CAR_N=0,CAR_TIMER=null,CAR_PAUSED=false,CAR_LAST=[],CAR_ALL=[];
var CAR_RM=false;try{CAR_RM=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;}catch(e){}
/* owner 2:47 seamless loop: the wrap used to transition from the last slide back to the first,
   visibly rushing backwards through every slide ("restringing"). Each track now carries a clone of
   the last slide up front and of the first slide at the end; a wrap animates onto the clone (motion
   stays continuous, same direction), then silent-jumps to the identical real slide. CAR_IDX/SOC_IDX
   stay logical (0..N-1); track space adds +1 while clones are present. */
var CAR_JUMP=0,SOC_JUMP=0;
function carClonify(tr,N){
 if(!tr||N<2)return;
 var f=tr.children[0],l=tr.children[N-1];if(!f||!l)return;
 var cl=l.cloneNode(true);cl.classList.add('carclone');cl.setAttribute('aria-hidden','true');
 var cf=f.cloneNode(true);cf.classList.add('carclone');cf.setAttribute('aria-hidden','true');
 tr.insertBefore(cl,f);tr.appendChild(cf);
}
function carCloned(tr,N){return !!(tr&&N>1&&tr.children.length===N+2);}
function carNoTrans(tr,fn){
 var vp=tr.parentElement;
 tr.style.transition='none';if(vp)vp.style.transition='none';
 fn();
 void tr.offsetHeight;
 tr.style.transition='';if(vp)vp.style.transition='';
}
function carMove(ci,sync){
 var tr=$('rpCarTrack');if(!tr||!CAR_N)return;
 var s=tr.children[ci];if(!s)return;
 /* owner 12:21 bug: fixed slide heights clipped content at mobile widths (prev slide bled in,
    current headline cut). Natural slide heights + pixel-offset translate: the viewport hugs the
    active slide's real height, so nothing clips and nothing bleeds, any width, any content. */
 var vp=tr.parentElement;
 vp.style.height=s.offsetHeight+'px';
 tr.style.transform='translateY(-'+s.offsetTop+'px)';
 var c=$('rpCarCount');if(c)c.textContent=(CAR_N?(CAR_IDX+1):0)+' of '+CAR_N;
 if(sync)socSync();
}
function carApply(){carMove(CAR_IDX+(carCloned($('rpCarTrack'),CAR_N)?1:0),true);}
function carAdv(d){
 if(CAR_N<2)return;
 var tr=$('rpCarTrack');
 if(!carCloned(tr,CAR_N)){CAR_IDX=(CAR_IDX+d+CAR_N)%CAR_N;carApply();return;}
 var v=CAR_IDX+1+d;
 if(v>=1&&v<=CAR_N){CAR_IDX=v-1;carApply();return;}
 if(CAR_JUMP)clearTimeout(CAR_JUMP);
 CAR_IDX=(d>0)?0:CAR_N-1;
 carMove((d>0)?CAR_N+1:0,true); /* glide onto the clone - identical content, motion stays continuous */
 CAR_JUMP=setTimeout(function(){CAR_JUMP=0;var t2=$('rpCarTrack');if(t2)carNoTrans(t2,function(){carApply();});},580);
}
var CAR_RZ=null;
window.addEventListener('resize',function(){if(CAR_RZ)clearTimeout(CAR_RZ);CAR_RZ=setTimeout(function(){carApply();socApply();},180);});
/* owner 12:25 add-on: news + social rotate IN SYNC on one shared clock; pausing one pauses both;
   hover/focus on either freezes both. Manual Prev/Next stays per-carousel. */
var SYNC_STOP=['with','from','that','this','after','before','into','your','their','will','would','could','should','about','over','just','have','been','what','when','where','they','them','then','than','against','season','trade','week','year','game','games','team','teams','picks','pick','news','says','report','first','last','next','back','down','more','most','some','make','makes','made','take','takes','gets','going','goes','here','there','still','even','much','many','only','also','very','head','heads','look','looks','best','worst','every','each','both','while','which','whose','rank','ranks','ranked','ranking','start','starts','started'];
var SYNC_LAST=false;
function socSync(){
 SYNC_LAST=false;
 var mp=socMatchPair();
 if(mp>=0){SOC_IDX=mp;socApply();SYNC_LAST=true;return true;}
 /* abstain or no map entry: NEVER guess a pairing (owner 1:00 hard rule - a wrong match is a failure,
    an abstain is not). Social simply advances chronologically. */
 return false;
}
 /* owner 12:30 contextual sync: social slide follows the news slide's entities (team/player/story
    keywords). A match jumps the social index; no match -> caller keeps chronological advance. */

function carStep(){
 if(document.hidden||CAR_PAUSED||CAR_RM)return;
 if(CAR_N<2&&SOC_N<2)return;
 var nb=$('rpNewsCar'),sb=$('rpSocial');
 if((nb&&(nb.matches(':hover')||nb.matches(':focus-within')))||(sb&&(sb.matches(':hover')||sb.matches(':focus-within'))))return;
 if(CAR_N>1)carAdv(1);
 if(!SYNC_LAST&&SOC_N>1)socAdv(1);
}
function carGo(d){carAdv(d);}
function carPP(){CAR_PAUSED=!CAR_PAUSED;var ids=['rpCarPP','rpSocPP'];for(var i=0;i<ids.length;i++){var b=$(ids[i]);if(b)b.textContent=CAR_PAUSED?'Play':'Pause';}}
function carAll(){
 var pop=$('rpCarAllPop');if(!pop)return;
 if(pop.hidden){
  var h='';
  CAR_ALL.forEach(function(a){
   var u=a.link||'',src=a.source||'';
   var inner='<span class="napill src '+esc(src.toLowerCase())+'">'+esc(src)+'</span>'
    +'<span class="nabody"><span class="nahead">'+esc(unesc(a.headline||''))+'</span><span class="nameta">'+esc(ago(a.published))+'</span></span>';
   h+='<div class="narow">'+(u?'<a href="'+esc(u)+'" target="_blank" rel="noreferrer">'+inner+'</a>':inner)+'</div>';
  });
  pop.innerHTML=h||'<div class="empty">News unavailable right now.</div>';
  pop.hidden=false;
 }else pop.hidden=true;
}
/* news carousel (owner 10:51 spec via main 11:53 + 12:06 critique: main-column width, one article at a
   time, image + headline + first lines + source, vertical rotation, all sports sources, Prev/Next +
   counter + Pause/Play, hover/focus pause, reduced-motion, dedupe, last-valid fallback, View all) -
   replaces the old sidebar news list; renderNews keeps its name so every existing call site feeds it. */
function renderNews(t,arts){
 var box=$('rpNewsCar');if(!box)return;
 if(t&&t.key!=='home'){box.innerHTML='';return;}  /* owner 12:54: News renders on Home only - no leaks, no per-tab feeds */

 var items=(arts||[]).slice(0,12);
 if(!items.length&&CAR_LAST.length)items=CAR_LAST; /* latest-valid fallback: never blank a good card on a bad fetch */
 if(items.length)CAR_LAST=items;
 CAR_ALL=(arts||[]).slice(0,40);
 var sig=items.map(function(a){return normH(a.headline);}).join('|');
 if(sig===CAR_SIG&&$('rpCarTrack')){carApply();return;}
 var curKey=(CAR_LAST[CAR_IDX]&&carKey(CAR_LAST[CAR_IDX]))||'';
 CAR_SIG=sig;CAR_N=items.length;
 CAR_IDX=0;
 if(curKey){for(var _ci=0;_ci<items.length;_ci++){if(carKey(items[_ci])===curKey){CAR_IDX=_ci;break;}}}
 if(CAR_IDX>=CAR_N)CAR_IDX=0;
 if(!items.length){box.innerHTML='<div class="empty">News unavailable right now.</div>';return;}
 var h='<div class="carvp"><div class="cartrack" id="rpCarTrack">';
 items.forEach(function(a){
  var u=a.link||'',src=a.source||'';
  var img=(typeof a.image==='string'&&/^https:\/\//.test(a.image))?a.image:'';
  var blurb=(typeof a.blurb==='string')?a.blurb:'';
  var inner=(img?'<span class="carimg" style="background-image:url(\''+esc(img)+'\')"></span>':'')
   +'<span class="carbody"><span class="carhead">'+esc(unesc(a.headline||''))+'</span>'
   +(blurb?'<span class="carblurb">'+esc(unesc(blurb))+'</span>':'')
   +'<span class="carmeta"><span class="src '+esc(src.toLowerCase())+'">'+esc(src)+'</span> \u00b7 '+esc(ago(a.published))+(isNewIt(a)?' <span class="carnew">new</span>':'')+'</span></span>';
  h+='<div class="carslide" data-nkey="'+esc(u||String(a.headline||''))+'">'+(u?'<a href="'+esc(u)+'" target="_blank" rel="noreferrer" aria-label="'+esc(unesc(a.headline||''))+'">'+inner+'</a>':inner)+'</div>';
 });
 h+='</div></div><div class="carctl"><button type="button" id="rpCarPrev" aria-label="previous article">\u2039 Prev</button>'
  +'<span id="rpCarCount" class="carcount"></span>'
  +'<button type="button" id="rpCarNext" aria-label="next article">Next \u203a</button>'
  +'<button type="button" id="rpCarPP" aria-label="pause rotation">'+(CAR_PAUSED?'Play':'Pause')+'</button>'
  +'<button type="button" id="rpCarAllBtn" class="carall">View all News</button></div>';
 box.innerHTML=h;
 carClonify($('rpCarTrack'),CAR_N);
 if(CAR_JUMP){clearTimeout(CAR_JUMP);CAR_JUMP=0;}
 $('rpCarPrev').addEventListener('click',function(e){e.preventDefault();carGo(-1);});
 $('rpCarNext').addEventListener('click',function(e){e.preventDefault();carGo(1);});
 $('rpCarPP').addEventListener('click',function(e){e.preventDefault();carPP();});
 $('rpCarAllBtn').addEventListener('click',function(e){e.preventDefault();carAll();});
 carApply();
 carObserve();
 if((CAR_N>1||SOC_N>1)&&!CAR_TIMER)CAR_TIMER=setInterval(carStep,5500);
}
/* X social section (owner 10:32: X posts out of news, own Home section; built 11:53 scope):
   renders the x_feed items XNEWS already normalizes; Home-only visibility via body.tab-home CSS. */
var SOC_SIG='',SOC_IDX=0,SOC_N=0,SOC_LAST=[];
function socMove(ci){
 var tr=$('rpSocTrack');if(!tr||!SOC_N)return;
 var sl=tr.children[ci];if(!sl)return;
 var vp=tr.parentElement;
 vp.style.height=sl.offsetHeight+'px';
 tr.style.transform='translateY(-'+sl.offsetTop+'px)';
 var c=$('rpSocCount');if(c)c.textContent=(SOC_N?(SOC_IDX+1):0)+' of '+SOC_N;
}
function socApply(){socMove(SOC_IDX+(carCloned($('rpSocTrack'),SOC_N)?1:0));}
function socAdv(d){
 if(SOC_N<2)return;
 var tr=$('rpSocTrack');
 if(!carCloned(tr,SOC_N)){SOC_IDX=(SOC_IDX+d+SOC_N)%SOC_N;socApply();return;}
 var v=SOC_IDX+1+d;
 if(v>=1&&v<=SOC_N){SOC_IDX=v-1;socApply();return;}
 if(SOC_JUMP)clearTimeout(SOC_JUMP);
 SOC_IDX=(d>0)?0:SOC_N-1;
 socMove((d>0)?SOC_N+1:0);
 SOC_JUMP=setTimeout(function(){SOC_JUMP=0;var t2=$('rpSocTrack');if(t2)carNoTrans(t2,function(){socApply();});},580);
}
function socGo(d){socAdv(d);}
/* owner 2:55 clip kill (permanent): slide offsets measured before late reflows (font swap, image
   layout, async CSS) left translateY pointing BETWEEN slides - the previous slide's tail bled into
   the viewport top, headline cut mid-line. Any geometry change on either track, plus full load,
   re-applies the CURRENT slide position so offsets are never stale. */
var CAR_RO=null;
try{CAR_RO=new ResizeObserver(function(){carApply();socApply();});}catch(e){CAR_RO=null;}
window.addEventListener('load',function(){carApply();socApply();});
function carObserve(){
 if(!CAR_RO)return;
 CAR_RO.disconnect();
 var a=$('rpCarTrack'),b=$('rpSocTrack');
 if(a)CAR_RO.observe(a);if(b)CAR_RO.observe(b);
}
/* View more posts (owner 12:33): pop listing the fuller set of posts related to the current
   news+social pair's topic - same topic matching as the contextual sync; row grid mobile pass. */
function socMore(){
 var pop=$('rpSocMorePop');if(!pop)return;
 if(!pop.hidden){pop.hidden=true;return;}
 var mm=socMatchMore();
 var h2='';
 if(mm&&mm.length){
  mm.forEach(function(e){
   var xi=SOC_XIDX[e.post_id];if(xi===undefined)return;
   var p=XNEWS[xi],txt=String(p.headline||'');
   if(txt.length>280)txt=txt.slice(0,277)+'\u2026';
   var inner='<span class="napill src x">X</span>'
    +'<span class="nabody"><span class="nahead stxt">'+esc(unesc(txt))+'</span><span class="nameta">'+(p.author?esc(p.author)+' \u00b7 ':'')+esc(ago(p.published))+'</span></span>';
   h2+='<div class="narow">'+(p.link?'<a href="'+esc(p.link)+'" target="_blank" rel="noreferrer">'+inner+'</a>':inner)+'</div>';
  });
 }
 if(!h2)h2='<div class="empty">No posts about this topic right now.</div>';
 pop.innerHTML=h2;pop.hidden=false;
}
/* social carousel (owner 12:25): one post at a time, same mechanics as the news carousel,
   natural slide heights (12:21 clip fix), shared tick + shared pause via carStep/carPP. */
/* ULTRIX semantic match map (owner 12:37): built+cached by scripts/soc_match.py at feed-refresh time.
   Never per-pageview. Stale (>2h) or missing map => NO sync jump (abstain beats a wrong match, 1:00 rule). */
var SOC_MATCH=null,SOC_MATCH_OK=false,SOC_XIDX={},SOC_RIDX={};
/* owner 1:26: social feed renders sports-relevant, topic-matching posts only - never a raw
   firehose. Fresh map: server relevance layer (URF evidence gate) decides per post. No fresh
   map: this keyword floor is the fallback so raw off-topic chatter never renders. */
/* owner 1:39: NO tout/selling-access posts, ever - client layer mirrors the server filter so
   legacy pool items and no-map fallbacks are covered too. */
var RP_TOUT_KW=/discord|telegram|dubclub|patreon|link in bio|dm (me|us) for|vip (picks|plays|access)|picks package|premium picks|paywall|subscribe for|promo code|join my|tap in with|free (play|pick)s? (today|daily)|lock of the day|guaranteed (winner|play)/i;
var RP_SPORT_KW=/nfl|nba|mlb|nhl|wnba|ncaa|cfb|mls|nwsl|pga|nascar|ufc|mma|boxing|tennis|football|basketball|baseball|hockey|soccer|golf|sports|touchdown|quarterback|playoff|super bowl|world series|stanley cup|fantasy|draft pick|trade rumor|injury report|starting lineup|home run|slam dunk|shutout|knockout|title fight|grand slam|eagles|bears|chiefs|cowboys|packers|vikings|giants|jets|patriots|steelers|ravens|bengals|browns|texans|colts|jaguars|titans|broncos|raiders|chargers|rams|seahawks|49ers|cardinals|falcons|panthers|saints|buccaneers|commanders|lions|dolphins|bills|yankees|dodgers|red sox|cubs|braves|astros|phillies|mets|padres|mariners|lakers|celtics|warriors|knicks|nets|sixers|bulls|heat|bucks|nuggets|suns|mavericks|thunder|timberwolves|spurs|rockets|clippers|grizzlies|pelicans|kings|trail blazers|jazz|hawks|hornets|hornets|pacers|cavaliers|pistons|magic|wizards|raptors|maple leafs|bruins|canadiens|oilers|avalanche|lightning|panthers|rangers|penguins|capitals|flyers|red wings|blackhawks|wild|stars|predators|blues|jets|kraken|golden knights|sharks|ducks|kings|coyotes|hurricanes|blue jackets|devils|islanders|sabres|senators|flames|canucks/i;
fetch('slates/soc_match.json',{cache:'no-store'}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(m){
 if(m&&m.built_at&&(Date.now()-Date.parse(m.built_at))<2*3600*1000&&m.pairs){SOC_MATCH=m;SOC_MATCH_OK=true;try{renderSocial();socSync();}catch(e){}}
}).catch(function(){SOC_MATCH_OK=false;});
function socMatchPair(){ /* XNEWS index of the current news slide's verified pair; -2 abstained; -1 no map entry */
 if(!SOC_MATCH_OK)return -1;
 var ntr=$('rpCarTrack');if(!ntr)return -1;
 var slide=ntr.children[CAR_IDX+(carCloned(ntr,CAR_N)?1:0)];if(!slide)return -1;
 var k=slide.getAttribute('data-nkey')||'';
 if(!k||!(k in SOC_MATCH.pairs))return -1;
 var pr=SOC_MATCH.pairs[k];
 if(!pr||!pr.post_id)return -2;
 return (pr.post_id in SOC_RIDX)?SOC_RIDX[pr.post_id]:-2;
}
function socMatchMore(){ /* ranked related posts for the current news key; null when the map has no entry */
 if(!SOC_MATCH_OK)return null;
 var ntr=$('rpCarTrack');if(!ntr)return null;
 var slide=ntr.children[CAR_IDX+(carCloned(ntr,CAR_N)?1:0)];if(!slide)return null;
 var k=slide.getAttribute('data-nkey')||'';
 if(!k||!(k in SOC_MATCH.more))return null;
 return SOC_MATCH.more[k];
}
function renderSocial(){
 var box=$('rpSocial');if(!box)return;
 if(!XNEWS.length){box.innerHTML='<div class="empty">No posts right now.</div>';SOC_SIG='';SOC_N=0;return;}
 var REL=(SOC_MATCH_OK&&SOC_MATCH&&SOC_MATCH.relevance)?SOC_MATCH.relevance:null;
 var ADMIT=(SOC_MATCH_OK&&SOC_MATCH&&SOC_MATCH.admit&&SOC_MATCH.admit.length)?SOC_MATCH.admit:null;
 var onTopic=function(p){
  /* owner 1:39 narrow rule: social shows ONLY posts related to news-feed articles.
     tout check always first; fresh map: admit-set membership is the admission test
     (a post earned membership by scoring the relatedness floor against a current story);
     no fresh map: sports-keyword floor so the raw firehose never renders. */
  if(RP_TOUT_KW.test(String(p.headline||'')))return false;
  if(ADMIT){if(ADMIT.indexOf(String(p.id))<0)return false;
   var rr=REL&&REL[String(p.id)];return rr?rr.on_topic!==false:true;} /* combined gate: related AND sports-relevant (QA 1:49) */
  if(REL){var r=REL[String(p.id)];if(r)return r.on_topic!==false;return true;}
  return RP_SPORT_KW.test(String(p.headline||''));
 };
 var chrono=XNEWS.slice().sort(function(a,b){return Date.parse(b.published||0)-Date.parse(a.published||0);});
 /* matched pinning (owner 1:09/1:11): posts with a URF-verified pair to a carousel story are
    pinned into the rendered slice (news-carousel order), then chronological fills to 6.
    Without pinning a verified post older than the top-6 silently abstained (drift bug, 1:12 test). */
 var pinned=[],seenP={};
 if(SOC_MATCH_OK&&SOC_MATCH&&SOC_MATCH.pairs){
  (CAR_LAST||[]).forEach(function(a){
   var k=(a.link||'')||String(a.headline||'');
   var pr=SOC_MATCH.pairs[k];
   if(!pr||!pr.post_id||seenP[pr.post_id])return;
   var xi=SOC_XIDX[pr.post_id];
   if(xi===undefined)return;
   seenP[pr.post_id]=1;pinned.push(XNEWS[xi]);
  });
 }
 var pool=chrono.filter(function(p){return seenP[p.id]||onTopic(p);}); /* verified pins bypass the topic floor - the probe already judged them */
 var items=pinned.concat(pool.filter(function(p){return pinned.indexOf(p)<0;})).slice(0,6);
 var sig=items.map(function(p){return p.id||String(p.headline||'').slice(0,40);}).join('|');
 if(sig===SOC_SIG&&$('rpSocTrack')){socApply();return;}
 var curId=(SOC_LAST[SOC_IDX]&&SOC_LAST[SOC_IDX].id)||'';
 SOC_SIG=sig;SOC_N=items.length;SOC_LAST=items;
 SOC_RIDX={};items.forEach(function(p,i){if(p.id)SOC_RIDX[p.id]=i;});
 SOC_IDX=0;
 if(curId){for(var _si=0;_si<items.length;_si++){if(items[_si].id===curId){SOC_IDX=_si;break;}}}
 if(SOC_IDX>=SOC_N)SOC_IDX=0;
 var h='<div class="carvp socvp"><div class="cartrack" id="rpSocTrack">';
 items.forEach(function(p){
  var txt=String(p.headline||'');
  if(txt.length>280)txt=txt.slice(0,277)+'\u2026';
  var inner='<span class="carbody"><span class="stxt">'+esc(unesc(txt))+'</span>'
   +'<span class="carmeta">'+(p.author?esc(p.author)+' \u00b7 ':'')+esc(ago(p.published))+(isNewIt(p)?' <span class="carnew">new</span>':'')+'</span></span>';
  h+='<div class="carslide socslide">'+(p.link?'<a href="'+esc(p.link)+'" target="_blank" rel="noreferrer">'+inner+'</a>':inner)+'</div>';
 });
 h+='</div></div><div class="carctl"><button type="button" id="rpSocPrev" aria-label="previous post">\u2039 Prev</button>'
  +'<span id="rpSocCount" class="carcount"></span>'
  +'<button type="button" id="rpSocNext" aria-label="next post">Next \u203a</button>'
  +'<button type="button" id="rpSocPP" aria-label="pause rotation">'+(CAR_PAUSED?'Play':'Pause')+'</button>'
  +'<button type="button" id="rpSocMore" class="carall">View more posts</button></div>';
 box.innerHTML=h;
 carClonify($('rpSocTrack'),SOC_N);
 if(SOC_JUMP){clearTimeout(SOC_JUMP);SOC_JUMP=0;}
 $('rpSocPrev').addEventListener('click',function(e){e.preventDefault();socGo(-1);});
 $('rpSocNext').addEventListener('click',function(e){e.preventDefault();socGo(1);});
 $('rpSocPP').addEventListener('click',function(e){e.preventDefault();carPP();});
 $('rpSocMore').addEventListener('click',function(e){e.preventDefault();socMore();});
 socApply();
 carObserve();
 if((CAR_N>1||SOC_N>1)&&!CAR_TIMER)CAR_TIMER=setInterval(carStep,5500);
}
/* client replica of news_feed.py relevant() - the 25s instant lane merges straight into the
   visible bucket, so it must pass the same promotion/league filter the server applies
   (swamp 1:19: unfiltered ESPN mma stories bypassed the UFC-promotion rule). Keep in sync. */
var RP_NEWS_LEAGUE_KW={
 'NFL':['nfl','football','super bowl','quarterback','touchdown'],
 'NBA':['nba','basketball'],
 'MLB':['mlb','baseball','world series','pitcher','home run'],
 'NHL':['nhl','hockey','stanley cup'],
 'CFB':['college football','ncaa football','cfb','quarterback','touchdown','heisman'],
 'NCAAB':['college basketball','ncaa','march madness','basketball'],
 'WNBA':['wnba','basketball'],
 'MLS':['mls','soccer','major league soccer'],
 'NWSL':['nwsl','soccer'],
 'PGA':['golf','pga','masters','ryder','open championship','tour championship','birdie','eagle'],
 'ATP':['tennis','atp','grand slam','wimbledon','us open','australian open','french open'],
 'WTA':['tennis','wta','grand slam','wimbledon','us open','australian open','french open'],
 'NASCAR':['nascar','racing','daytona','cup series'],
 'UFC':['ufc'],
 'Boxing':['boxing','heavyweight','title bout']
};
var RP_NEWS_STRONG={'NFL':['nfl','super bowl','quarterback','touchdown'],'NBA':['nba'],'MLB':['mlb','world series','home run'],'NHL':['nhl','stanley cup'],'WNBA':['wnba']};
var RP_NEWS_SPORT_OF={'NFL':'NFL','CFB':'NFL','NBA':'NBA','NCAAB':'NBA','WNBA':'WNBA','MLB':'MLB','NHL':'NHL'};
var RP_NEWS_NICHE={'MLS':1,'NWSL':1,'PGA':1,'ATP':1,'WTA':1,'NASCAR':1,'UFC':1,'Boxing':1};
var RP_NEWS_ESPN2KEY={'football/nfl':'NFL','football/college-football':'CFB','basketball/nba':'NBA','basketball/mens-college-basketball':'NCAAB','basketball/wnba':'WNBA','baseball/mlb':'MLB','hockey/nhl':'NHL','soccer/usa.1':'MLS','soccer/usa.nwsl':'NWSL','golf/pga':'PGA','tennis/atp':'ATP','tennis/wta':'WTA','racing/nascar-premier':'NASCAR','mma/ufc':'UFC'};
function rpNewsKeys(t){
 if(!t)return[];
 if(t.key==='tennis')return['ATP','WTA'];
 if(t.key==='ufcboxing')return['UFC','Boxing'];
 var k=RP_NEWS_ESPN2KEY[t.espn||''];
 return k?[k]:[];
}
function rpNewsOkKey(key,headline){
 var h=' '+(headline||'').toLowerCase()+' ';
 var my=RP_NEWS_SPORT_OF[key];
 for(var sport in RP_NEWS_STRONG){
  if(sport===my)continue;
  var marks=RP_NEWS_STRONG[sport];
  for(var i=0;i<marks.length;i++)if(h.indexOf(marks[i])!==-1)return false;
 }
 if(RP_NEWS_NICHE[key]){
  var kws=RP_NEWS_LEAGUE_KW[key];
  if(!kws)return false;
  var cut=Math.max(20,Math.floor(h.length*0.6));
  var lead=h.slice(0,cut);
  for(var j=0;j<kws.length;j++)if(lead.indexOf(kws[j])!==-1)return true;
  return false;
 }
 return true;
}
function rpNewsOk(t,headline){
 var ks=rpNewsKeys(t);
 if(!ks.length)return true;  /* unknown tab: server file already filtered; don't double-gate */
 for(var i=0;i<ks.length;i++)if(rpNewsOkKey(ks[i],headline))return true;
 return false;
}
var NEWSF=null,NEWSF_TS=0,XNEWS=[],XNEWS_TS=0,HOME_GAMES_TS=0;
/* REAL-TIME feeds (owner 12:44): poll feed JSONs + cached UltRix match map on a short interval,
   merge newest-first, keep the user's current slide stable, live counter, subtle 'new' marker.
   The match map stays build-time cached (12:37) - clients never touch the NIM endpoint. */
var RP_LOAD=Date.now();
function carKey(a){return (a&&a.link)||String((a&&a.headline)||'');}
function isNewIt(a){var t=Date.parse((a&&a.published)||0);return t&&t>RP_LOAD;}
function rtPoll(){
 fetch('slates/news.json',{cache:'no-store'}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){
  if(j&&j.generated_at&&(!NEWSF||j.generated_at!==NEWSF.generated_at)){
   NEWSF=j;NEWSF_TS=Date.now();
   if(typeof cur!=='undefined'&&cur){renderNews(cur,newsBucket(cur));}
  }
 }).catch(function(){});
 if(typeof cur!=='undefined'&&cur&&cur.key==='home'){XNEWS_TS=0;refreshX();}
 fetch('slates/soc_match.json',{cache:'no-store'}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(m){
  if(m&&m.built_at&&(Date.now()-Date.parse(m.built_at))<2*3600*1000&&m.pairs){SOC_MATCH=m;SOC_MATCH_OK=true;}
 }).catch(function(){});
}
setInterval(rtPoll,45000);
window.__rpRT={poll:rtPoll,state:function(){return {gen:NEWSF&&NEWSF.generated_at,carIdx:CAR_IDX,carN:CAR_N,socN:SOC_N,curKey:typeof cur!=='undefined'&&cur&&cur.key};}};
function refreshX(){
 if(Date.now()-XNEWS_TS<60000)return;
 XNEWS_TS=Date.now();
 fetch('slates/x_feed.json',{cache:'no-store'}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){
  if(!j||!Array.isArray(j.items))throw 0;
  XNEWS=j.items.filter(function(p){return p&&/^[0-9]+$/.test(String(p.id||''))&&p.created_at&&p.text;}).map(function(p){var u=(typeof p.url==='string'&&/^https:\/\/(?:www\.)?(?:x\.com|twitter\.com)\/[A-Za-z0-9_]+\/status\/[0-9]+(?:\?.*)?$/.test(p.url)&&p.url.split('/status/')[1].split('?')[0]===String(p.id))?p.url:'';return {id:String(p.id),headline:String(p.text).slice(0,900),link:u,published:p.created_at,source:'X',author:typeof p.author_name==='string'?p.author_name.slice(0,80):''};});
  SOC_XIDX={};XNEWS.forEach(function(p,i){if(p.id)SOC_XIDX[p.id]=i;});
  renderSocial();
 if(cur&&cur.key==='home')renderNews(cur,newsBucket(cur));
 }).catch(function(){});
}

var DNEWS={},DNEWS_TS={};
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
/* ticker core (Julian stutter hunt 9/28): crawl driven by rAF at CONSTANT px/s in JS, never
   CSS animation. Root causes killed: (1) innerHTML swap on every tickRender (tab switch, 30s
   refresh, async KALSHI callback) restarted/jerked the loop - swap now only on real content
   change; (2) translateX(-50%) remapped pixel position on width change mid-loop - position
   preserved modulo new half-width; (3) %-duration made px/s vary with content volume - speed
   is constant; (4) background/visibility desync - rAF stops/resumes without state loss. */
var TICK_V=46,tickX=0,tickHalf=0,tickPaused=false,tickLast=0;
try{if(window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches)TICK_V=0;}catch(e){}
/* ticker motion is CSS-composited (rpTickX keyframes) since 1:50 - no rAF drive, no 1Hz
   throttling artifacts, hover pause via CSS animation-play-state. tickX/tickHalf kept for
   content-rebuild bookkeeping. */
function tickRender(){
 var tr=$('rpTickTrack'),bar=$('rpTickBar');if(!tr||!bar)return;
 var arts=(NEWSF&&NEWSF.latest)||[];
 kalItemsFor(cur,function(kal){
  if(!arts.length&&!kal.length){bar.style.display='none';tr.__h='';tr.innerHTML='';tickHalf=0;tickX=0;return;}
  bar.style.display='';
  var h='';
  arts.slice(0,8).forEach(function(a){
   var u=a.link||'';
   var s=a.source||'ESPN';
   h+='<'+(u?'a class="titem" href="'+esc(u)+'" target="_blank" rel="noreferrer"':'span class="titem"')+'><span class="tsrc '+s.toLowerCase()+'">'+esc(s)+'</span><span class="tsrc">'+esc(a.league||'')+'</span>'+esc(unesc(a.headline||''))+'</'+(u?'a':'span')+'><span class="tsep">\u00b7</span>';
  });
  h+=kal.join('');
  if(h!==tr.__h){
   tr.__h=h;tr.innerHTML=h+h;
   var nh=tr.scrollWidth/2;
   tickHalf=nh;
   /* QA 1:50 stutter kill: compositor-driven CSS animation (true constant px/s, smooth even
      when rAF is throttled to 1Hz in occluded tabs - the stepwise 47px jumps QA measured
      were rAF starvation, not the drive math). Speed stays TICK_V px/s via duration. */
   tr.style.animation='none';
   void tr.offsetWidth;
   tr.style.animation='rpTickX '+(nh>0?(nh/TICK_V).toFixed(2):1)+'s linear infinite';
  }
 });
}
function loadSide(t){
 var lg=lgpath(t),now=Date.now();
 /* polish (main 1:43): never show another tab's stale rows while the target tab's sidebar
    loads - cached tabs render instantly via the SB path, uncached get an honest Loading. */
 var _gb0=$('rpGames');
 if(_gb0&&t.key!=='home'){_gb0.classList.remove('homeall');if(!SB[t.key])_gb0.innerHTML='<div class="empty">Loading upcoming games&hellip;</div>';}
 if(t.key==='home'){refreshX();renderSocial();}
 if(!lg){
  if(t.key==='wooder'){
   /* wooder sidebar (1:17 regression kill: empty box on direct #wooder load - the tab has no
      espn path so neither sidebar branch filled it). Wooder Ice is NFL content: NFL scoreboard. */
   if(SB[t.key]&&now-(SB_TS[t.key]||0)<60000){renderGames(t,SB[t.key]);}
   else{fetch('https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?limit=50',{cache:'no-store'}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){SB[t.key]=j.events||[];SB_TS[t.key]=Date.now();if(cur===t)renderGames(t,SB[t.key]);}).catch(function(){if(cur===t)renderGames(t,SB[t.key]||null);});}
  }
  if(t.key==='home'){
   var gb=$('rpGames'),games=[{label:'NFL',espn:'football/nfl'},{label:'CFB',espn:'football/college-football'},{label:'NBA',espn:'basketball/nba'},{label:'WNBA',espn:'basketball/wnba'},{label:'MLB',espn:'baseball/mlb'},{label:'NHL',espn:'hockey/nhl'},{label:'NCAAB',espn:'basketball/mens-college-basketball'},{label:'MLS',espn:'soccer/usa.1'},{label:'NWSL',espn:'soccer/usa.nwsl'},{label:'PGA',espn:'golf/pga'},{label:'NASCAR',espn:'racing/nascar'},{label:'UFC',espn:'mma/ufc'},{label:'ATP',espn:'tennis/atp'},{label:'WTA',espn:'tennis/wta'}];
   if(gb&&Date.now()-HOME_GAMES_TS>300000){
   HOME_GAMES_TS=Date.now();
   /* owner 2:12: 72h window, EVERY covered league, no count cap (was 48h + slice(0,9)).
      owner 2:13 intermittent-load kill: the old Promise.all gated the whole section on the
      SLOWEST league fetch with NO timeout - one hung ESPN call stalled every row. Now each
      league gets a 7s abort and paints progressively as it lands. */
   gb.classList.add('homeall');
   var _acc=[],_seenG={},_pend=games.length;
   var _rowH=function(g){var c=(g.event.competitions||[])[0]||{},a=(c.competitors||[]).filter(function(x){return x.homeAway==='away';})[0]||{},h=(c.competitors||[]).filter(function(x){return x.homeAway==='home';})[0]||{};var _an=(a.team||{}).abbreviation||(a.team||{}).shortDisplayName||(a.team||{}).displayName||(a.athlete||{}).shortName||(a.athlete||{}).displayName||'',_hn=(h.team||{}).abbreviation||(h.team||{}).shortDisplayName||(h.team||{}).displayName||(h.athlete||{}).shortName||(h.athlete||{}).displayName||'';var title=(_an&&_hn)?(esc(_an)+' @ '+esc(_hn)):esc(g.event.shortName||g.event.name||'');return '<div class="grow"><div><div class="gname">'+esc(g.league)+' &middot; '+title+'</div><div class="gsub">'+esc(dayTime(g.event.date))+'</div></div><span class="when">'+esc(until(g.event.date))+'</span></div>';};
   var _paint=function(){if(cur!==t||!gb)return;var all=_acc.slice().sort(function(p,q){return Date.parse(p.event.date||0)-Date.parse(q.event.date||0);});gb.innerHTML=all.map(_rowH).join('')||(_pend?'<div class="empty">Loading upcoming games&hellip;</div>':'<div class="empty">No upcoming games listed right now.</div>');};
   _paint();
   games.forEach(function(x){
    var _ctl=new AbortController();var _to=setTimeout(function(){_ctl.abort();},7000);
    fetch('https://site.api.espn.com/apis/site/v2/sports/'+x.espn+'/scoreboard?limit=50',{cache:'no-store',signal:_ctl.signal}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){(j.events||[]).forEach(function(e){if(_seenG[e.id])return;var st=(((e.competitions||[])[0]||{}).status||{}).type||{};if(st.state==='pre'&&Date.parse(e.date||0)>=Date.now()-3600000&&Date.parse(e.date||0)<Date.now()+259200000){_seenG[e.id]=1;_acc.push({league:x.label,event:e});}});}).catch(function(){}).finally(function(){_pend--;clearTimeout(_to);_paint();});
   });
   }
  }
 }else{
  if(SB[t.key]&&now-(SB_TS[t.key]||0)<60000){renderGames(t,SB[t.key]);}
  else{fetch('https://site.api.espn.com/apis/site/v2/sports/'+lg+'/scoreboard?limit=50',{cache:'no-store'}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){SB[t.key]=j.events||[];SB_TS[t.key]=Date.now();if(cur===t)renderGames(t,SB[t.key]);}).catch(function(){if(cur===t)renderGames(t,SB[t.key]||null);});}
 }

 if(NEWSF&&now-NEWSF_TS<30000){renderNews(t,newsBucket(t));tickRender();}
 else{
  fetch('slates/news.json', {cache:'no-store'})
   .then(function(r){if(!r.ok)throw 0;return r.json();})
   .then(function(j){NEWSF=j;NEWSF_TS=Date.now();if(cur===t){renderNews(t,newsBucket(t));tickRender();}})
   .catch(function(){if(cur===t){renderNews(t,newsBucket(t));tickRender();}});
 }
 if(lg&&(!DNEWS_TS[t.key]||now-DNEWS_TS[t.key]>25000)){
  fetch('https://site.api.espn.com/apis/site/v2/sports/'+lg+'/news?limit=8',{cache:'no-store'})
   .then(function(r){if(!r.ok)throw 0;return r.json();})
   .then(function(j){DNEWS[t.key]=(j.articles||[]).map(function(a){return {headline:a.headline||'',link:((a.links||{}).web||{}).href||'',published:a.published||'',source:'ESPN'};}).filter(function(a){return rpNewsOk(t,a.headline);});DNEWS_TS[t.key]=Date.now();if(cur===t){renderNews(t,newsBucket(t));tickRender();}})
   .catch(function(){DNEWS_TS[t.key]=Date.now()-10000;});  /* soft backoff, keeps last good */
 }
}
setInterval(function(){if(cur&&!document.hidden)loadSide(cur);},30000);
setInterval(function(){if(cur&&!document.hidden&&NEWSF){renderNews(cur,newsBucket(cur));tickRender();}},30000);
/* wordmark -> home (Julian 9/27 4:31 PT via main): tap logo from any tab lands home. Clear rp_tab + hash so boot's default-tab pick (home) wins and a later refresh stays home. */
var _wmlogo=document.querySelector('nav.rpnav .logo');
if(_wmlogo){_wmlogo.addEventListener('click',function(e){e.preventDefault();try{localStorage.removeItem('rp_tab');}catch(x){}try{history.replaceState(null,'',location.pathname);}catch(x){}location.href='index.html';});}
/* ---- boot ---- */
var start=fromHash()||(function(){try{return localStorage.getItem('rp_tab');}catch(e){return null;}})();
if(!start&&TABS.some(function(t){return t.key==='home';}))start='home';
if(!start){
 for(var i=0;i<TABS.length;i++){var p=$('st-'+TABS[i].key);if(p&&p.querySelector('.pick:not(.rp-empty)')){start=TABS[i].key;break;}}
 if(!start&&TABS.length)start=TABS[0].key;
}
if(start)activate(start,true);
else document.body.classList.add('rp-ready');
if(!document.body.classList.contains('intro-on'))document.body.classList.add('rp-ready');
})();
