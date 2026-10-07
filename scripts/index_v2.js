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
  cw.style.display=((key==='home'&&!window.RP_CARD_STALE)||ok)?'':'none';
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
 try{sessionStorage.setItem('rp_tab',t.key);}catch(e){}
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
 navRecBtn.addEventListener('click',function(e){e.preventDefault();e.stopPropagation();location.href='record.html';}); /* owner 9:58 (screenshot): the record chip taps THROUGH to the full day-by-day synopsis page - the popover replaced that in the header move and killed the click-through */
 document.addEventListener('click',function(e){if(!recPop.hidden&&!recPop.contains(e.target)&&!navRecBtn.contains(e.target))setPop(false);});
 document.addEventListener('keydown',function(e){if(e.key==='Escape'&&!recPop.hidden)setPop(false);});
}
var burger=$('burger');
if(burger)burger.addEventListener('click',function(){document.body.classList.toggle('menu-open');});
/* one rounding rule for W/L % (Oct 1, 21-11 read 65.62% baked, 65.63% after load): the builder
   bakes the percent with _pct_half_up (exact integer arithmetic, an exact tie rounds up, so
   21-11 = 65.625 -> 65.63%); rpPct is the same arithmetic, so the baked figure holds after load
   for every record. */
function rpPct(w,l,dp){
 var n=w+l;if(!(n>0))return '';
 var sc=Math.pow(10,dp),p=200*sc*w+n,d=2*n,q=(p-p%d)/d;
 var f=String(q%sc);while(f.length<dp)f='0'+f;
 return String((q-q%sc)/sc)+(dp?'.'+f:'');
}
window.rpPct=rpPct; /* the record popover script (rpRecLive) formats W/L with the same rule */
/* ---- nav record mirror (canonical values live on #rpRec/#rpUnits datasets) ---- */
function navRec(){
 var r=$('rpRec'),u=$('rpUnits'),w=$('rpNavRecW'),l=$('rpNavRecL'),uu=$('rpNavU'),pc=$('rpNavPct');
 if(r&&w&&l){w.textContent=r.dataset.bw||'';l.textContent=r.dataset.bl||'';}
 if(r&&pc){var bw=parseInt(r.dataset.bw||'0',10),bl=parseInt(r.dataset.bl||'0',10);if(bw+bl>0)pc.textContent=rpPct(bw,bl,2)+'%';}
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
/* carded events open their built-out game page from every tappable surface (owner 11:13 regression:
   score/upcoming taps were landing on the bare tracker instead of the designed game view);
   live.html stays the destination for non-carded events only. Map ships per build. */
var RP_GAME_ROUTES={};
fetch('slates/game_routes.json?cb='+Date.now(),{cache:'no-store'}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){RP_GAME_ROUTES=j||{};if(cur&&SB[cur.key])renderGames(cur,SB[cur.key]);}).catch(function(){});
function lgpath(t){return t.espn||'';}
function ordinal(p){p=parseInt(p,10);if(!p)return '';if(p<=4)return p+(['th','st','nd','rd'][p]||'th');return p===5?'OT':(p-4)+'OT';}
/* future-dated feed times (Oct 1: ESPN RSS stamps its refresh time labelled EST, putting stories
   30-60 min in the future, so they read '1m ago' + NEW and sorted first). A time more than 5 min
   ahead of this clock is unknown, not new: no age label, no NEW marker, sorted as undated. */
var RP_FUTURE_SKEW=300000;
function pubT(iso){var t=Date.parse(iso||'');return (t&&t<=Date.now()+RP_FUTURE_SKEW)?t:0;}
function newsBlurb(a){var b=a&&a.blurb;return (typeof b==='string'&&!/^\s*(null|undefined|none)\s*$/i.test(b))?b:'';} /* a feed's literal 'null' is no blurb, never content */
function ago(iso){
 var t=pubT(iso);if(!t)return '';
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
 /* owner 9:33 screenshot bug: minutes must roll over - round TOTAL minutes first, then derive
    h/m (17h 59.6m reads 'in 18h 0m', never 'in 17h 60m'; same class at the sub-hour edge). */
 var tm=Math.round(s/60);
 if(tm<60)return 'in '+Math.max(1,tm)+'m';
 if(s<86400)return 'in '+Math.floor(tm/60)+'h '+(tm%60)+'m';
 return Math.round(s/86400)+'d';
}
function dayTime(iso){
 try{return new Date(iso).toLocaleString('en-US',{timeZone:'America/Los_Angeles',weekday:'short',hour:'numeric',minute:'2-digit'})+' PT';}catch(e){return '';}  /* all-times-PT rule (owner 9/27): sidebar game times render PT with explicit label, same convention as ptLabel elsewhere */
}
/* Predictions by UltRix (owner 9/27-28 spec, todo-01M3NDYDQG70VK9V6VYN2QD4JP): genuine
   forward predictions as plain outcome forecasts. The gate and confidence NEVER render -
   the artifact carries none. Fail-closed and isolated: any fetch/parse trouble hides the
   section and never touches the feeds. Home rail only. */
function renderPred(){
 var w=$('rpPredWrap'),box=$('rpPred');if(!w||!box)return;
 rpFeedJson('slates/predictions.json').then(function(j){
  var items=rpPredItems(j);
  if(!items.length){box.innerHTML='';w.style.display='none';return;}
  var h='';
  items.slice(0,6).forEach(function(p){
   h+='<div class="predrow"><span class="predtxt">'+esc(p.prediction||'')+'</span><span class="predmeta">'+esc(p.league||'')+(p.kickoff_utc?' \u00b7 '+esc(dayTime(p.kickoff_utc)):'')+'</span></div>';
  });
  box.innerHTML=h;w.style.display='';
 }).catch(function(){w.style.display='none';});
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
   when='<span class="when" data-until="'+esc(ev.date||'')+'">'+esc(until(ev.date))+'</span>';
  }
  var _row='<div class="grow"><div><div class="gname">'+txt+'</div><div class="gsub">'+sub+'</div></div>'+when+'</div>';
  rows.push((ev.id&&RP_GAME_ROUTES[ev.id])?('<a class="growtap" href="'+RP_GAME_ROUTES[ev.id]+'" style="display:block;text-decoration:none;color:inherit">'+_row+'</a>'):((ev.id&&RP_LIVE_OK[lgpath(t)])?('<a class="growtap" href="live.html?espn='+encodeURIComponent(lgpath(t))+'&eid='+encodeURIComponent(ev.id)+'" style="display:block;text-decoration:none;color:inherit">'+_row+'</a>'):_row));
 }
 box.innerHTML=rows.join('')||'<div class="empty">No games listed right now.</div>';
}
function srcDom(s){return s==='X'?'via X':(s==='CBS'?'cbssports.com':(s==='YAHOO'?'sports.yahoo.com':'espn.com'));}
function unesc(s){var t=document.createElement('textarea');t.innerHTML=String(s==null?'':s);return t.value;}  /* swamp 1:09: feeds ship HTML-encoded headlines (Jets&#39;) - decode before esc() or they double-escape */
function normH(h){return String(h||'').toLowerCase().replace(/[^a-z0-9]+/g,' ').replace(/^\s+|\s+$/g,'');}
function newsBucket(t){
 /* instant lane (owner: no lag on news dropping): the visible league's bucket merges
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
 out.sort(function(a,b){return pubT(b.published)-pubT(a.published);});
 var seen={},seenP={},ded=[];
 out.forEach(function(a){var n=normH(a.headline);if(!n)return;var pk=n.slice(0,40);if(seen[n]||seenP[pk])return;seen[n]=1;seenP[pk]=1;ded.push(a);});
 return ded.filter(isPublishableNews);
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
 var mb=$('rpSocMore');if(mb){var _mm=socMatchMore();mb.style.display=(_mm&&_mm.length)?'':'none';} /* audit 7: never offer an empty expansion */
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
 if(FEED_FALLBACK)return false; /* independent feeds: no positional correspondence, ever */

 /* aligned mode (user 4:27): social index IS the news index - the feeds can never disagree
    on position or count. Slide content already carries verified/latest/scan honesty tiers. */
 if(SOC_N>0&&CAR_LAST.length>0&&SOC_N===CAR_N){
  SOC_IDX=CAR_IDX;if(SOC_IDX>=SOC_N)SOC_IDX=SOC_N-1;if(SOC_IDX<0)SOC_IDX=0;
  socApply();SYNC_LAST=true;return true;
 }
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
 if(FEED_FALLBACK)return; /* independent feeds: social rotates on its own clock below - shared-tick rotation would imply pairing */
 if(!SYNC_LAST&&SOC_N>1)socAdv(1);
}
function socStep(){
 if(document.hidden||CAR_PAUSED||CAR_RM)return;
 if(SOC_N<2)return;
 var sb=$('rpSocial');
 if(sb&&(sb.matches(':hover')||sb.matches(':focus-within')))return;
 socAdv(1);
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
  if(!h){pop.hidden=true;return;}
  pop.innerHTML=h;
  pop.hidden=false;
 }else pop.hidden=true;
}
/* news carousel (owner 10:51 spec via main 11:53 + 12:06 critique: main-column width, one article at a
   time, image + headline + first lines + source, vertical rotation, all sports sources, Prev/Next +
   counter + Pause/Play, hover/focus pause, reduced-motion, dedupe, last-valid fallback, View all) -
   replaces the old sidebar news list; renderNews keeps its name so every existing call site feeds it. */
/* image optimizer, client layer (user 6:34 class): defense for stale cached payloads - the
   producer already rewrites, but a cached news.json in an open tab can still hold raw 2-3MB
   originals. Same rule: yimg + weserv stay direct, everything else routes through weserv. */
function imgOpt(u){
 if(typeof u!=='string'||!/^https:\/\//.test(u))return '';
 if(u.indexOf('images.weserv.nl/')>=0||u.indexOf('s.yimg.com/')>=0)return u;
 return 'https://images.weserv.nl/?url='+encodeURIComponent(u.slice(8))+'&w=1200&h=675&fit=cover&q=78&output=webp';
}
function RPimgErr(im){
 var u=im.getAttribute('data-rsrc')||im.src,n=+(im.getAttribute('data-rtry')||0);
 /* owner 7:13 kill-at-source: one transient load error never downgrades a card - retry twice
    (1.5s, 4s) with a fresh probe; on recovery the parent background is force-repainted. Only a
    confirmed-dead image reaches the league fallback, and every swap is logged. */
 if(n<2){im.setAttribute('data-rtry',n+1);setTimeout(function(){var t=new Image();t.onload=function(){var p=im.parentNode;if(p){p.style.backgroundImage='none';void p.offsetHeight;p.style.backgroundImage='url("'+u+'")';}im.remove();};t.onerror=function(){RPimgErr(im);};t.src=u;},n?4000:1500);return;}
 var p=im.parentNode;if(p){p.style.backgroundImage='none';p.className='carimg carimg-fb';p.setAttribute('data-lg',im.getAttribute('data-lg')||'SPORTS');}
 try{var L=JSON.parse(localStorage.getItem('rp_imgfb_v1')||'[]');L.push({u:u,ts:Date.now()});if(L.length>50)L=L.slice(-50);localStorage.setItem('rp_imgfb_v1',JSON.stringify(L));}catch(e){}
 (window.RP_IMGFB=window.RP_IMGFB||[]).push({u:u,ts:Date.now()});
 if(window.console&&console.warn)console.warn('[RP] image fallback after retries:',u);
 im.remove();
}
/* ONE shared pairing resolution (guard 1 source kill of the CAR_N>SOC_N divergence): each story's
   publishable distinct post is resolved ONCE here - verified pin -> probe-confirmed nearest ->
   on-story latest - and BOTH carousels render from PAIRS. A story with no resolvable post is
   excluded from both; neither renderer may filter further. Unmatched stories still live in
   View all News. Counters, sync and advancement consume this one array and one index. */
var PAIRS=[];
var CAR_UNIT=null; /* guard 1 atomic fallback (owner 7:11 "the same ones too"): the last fully
   rendered {story,post} unit. Fallback paths restore it AS ONE UNIT or blank BOTH carousels -
   unpaired news NEVER renders in the paired carousel (the 2-of-12 + empty-social class). */
/* ROLLED-DATES CLASS (phonemsg-01M3M8JV437ST9S8NV18WYAH66 "site must show current day,
   rolled dates"): the baked .rpdate header is the CARD's date; the site shows the current
   PT day. At PT midnight the header rolls forward and the stale card area is replaced by
   the honest not-published state (mirrors record_today.js) - yesterday's card never wears
   today's date. The roll compares ISO dates (the header's data-date with today's PT date) and
   fires only for a card dated BEFORE today: a card posted before PT midnight for the next day
   is not stale (Oct 2 review: the label-text compare hid its picks). A header with no ISO date
   keeps the card's own date. */
function rpDateRoll(){
 var el=document.querySelector('.rpdate');if(!el||window.RP_CARD_STALE)return;
 var card=(el.getAttribute&&el.getAttribute('data-date'))||'';
 var pt={};new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date()).forEach(function(x){pt[x.type]=x.value;});
 var todayIso=pt.year+'-'+pt.month+'-'+pt.day;
 if(!/^\d{4}-\d{2}-\d{2}$/.test(card)||card>=todayIso)return;
 var today=new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',weekday:'long',month:'short',day:'numeric'}).format(new Date());
 var cardDay=el.textContent.trim();
 el.textContent=today;
 window.RP_CARD_STALE=true;
 var st=document.getElementById('st-home');
 if(st)st.innerHTML='<div class="pick rp-empty"><div class="pick-head"><span class="name">Today\u2019s card has not published yet.</span></div></div>';
 /* the stale card's league panels stop projecting onto Home (they kept showing under the new date)
    and say which card they belong to; their "Today's picks" heading becomes "Picks"; its combo
    leaves Home too */
 document.querySelectorAll('.state[data-home-league]').forEach(function(p){
  if(!p.querySelector('.pick'))return;
  p.removeAttribute('data-home-league');
  var h=p.querySelector('.sect');if(h&&/^Today/.test(h.textContent))h.textContent='Picks';
  var n=document.createElement('div');n.className='cardnote';n.textContent='From the '+cardDay+' card';p.insertBefore(n,p.firstChild);
 });
 var cx=document.getElementById('rpComboTail');if(cx&&document.body.classList.contains('tab-home'))cx.style.display='none';
}
rpDateRoll();
/* A card's date by the builder's rule (_card_date_of; record_final.card_date_of): the most common PT
   date across its picks' commence (a game after PT midnight stays on its card), its own ISO date only
   when no pick has a readable, zoned start. No picks, or a preview, is no official card: ''. */
function rpCardDate(m){
 if(!m||m.preview===true||!Array.isArray(m.picks)||!m.picks.length)return '';
 var F=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Los_Angeles',year:'numeric',month:'2-digit',day:'2-digit'});
 var c={},o=[],b='',n=0;
 m.picks.forEach(function(p){
  var s=String((p&&p.game&&p.game.commence)||''),x=/(Z|[+-][0-9]{2}:?[0-9]{2})$/i.test(s)?Date.parse(s):NaN;
  if(isNaN(x))return;
  var d=F.format(new Date(x));if(!(d in c)){c[d]=0;o.push(d);}c[d]++;
 });
 o.forEach(function(d){if(c[d]>n){n=c[d];b=d;}});
 return b||(/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(String(m.date||''))?String(m.date):'');
}
/* The Home Yesterday line at VIEW time (r3 review). The builder bakes it for the build's PT yesterday
   (data-ydate) with the card dates that carried official picks and have no graded row (data-pending:
   manifests/ snapshots and the live card). A viewer on a later PT day gets it recomputed for their own
   PT yesterday from same-origin history.json: the graded row (linking yesterday.html while that page
   carries the day - its last two graded days), else 'results pending' when that date is a pending card
   date or the live manifest.json is that date's card, else '0-0 - no official picks'. history.json
   unreadable: the line is hidden, never left standing for another day. Same words as the builder's
   _hist_yesterday (scripts/test_home_yesterday_view.js). */
function rpYesterdayLine(){
 var a=document.querySelector('.home-yes');if(!a)return;
 var yd=a.getAttribute('data-ydate')||'';if(!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(yd))return;
 var t=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Los_Angeles',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
 var y=new Date(t+'T12:00:00Z');y.setUTCDate(y.getUTCDate()-1);y=y.toISOString().slice(0,10);
 if(y===yd)return;
 var pend=(a.getAttribute('data-pending')||'').split(' ');
 var g=function(u){return fetch(u+'?cb='+Date.now(),{cache:'no-store'}).then(function(r){return r.ok?r.json():null;}).catch(function(){return null;});};
 Promise.all([g('history.json'),g('manifest.json')]).then(function(r){
  var days=r[0]&&Array.isArray(r[0].days)?r[0].days:null;
  if(!days){a.style.display='none';return;}
  var ix=-1;days.forEach(function(d,i){if(d&&d.date===y)ix=i;});
  var row=ix>=0?days[ix]:null,txt,href='record.html';
  if(row&&Array.isArray(row.picks)&&row.picks.length){
   txt=String(row.record||'0-0')+' · '+row.picks.filter(function(p){return p&&p.name&&p.result;}).map(function(p){return String(p.name).trim()+' '+String(p.result).trim();}).join(' · ');
   if(ix>=days.length-2&&row.label)href='yesterday.html';
  }else if(pend.indexOf(y)>=0||rpCardDate(r[1])===y)txt='results pending';
  else txt='0-0 - no official picks';
  a.textContent='Yesterday: '+txt;a.setAttribute('href',href);a.setAttribute('data-ydate',y);
 });
}
rpYesterdayLine();
/* What the system is learning (Home). The builder bakes the first paint (_learnings_html); here the
   same-origin history.json is re-read on load and every 120 s while the page is visible, and the box is
   repainted by the same rules only when its content changed: day groups newest day first, at most 3;
   under each day label that day's own brief, then its graded picks' lessons newest-graded first
   (reverse ledger order), at most 6 picks in all. A day counts only when it has a graded pick; once 6
   picks are shown no further day is opened. A pick's lesson is its note, or its learning (the grading
   chain's field) when the note is missing or left out. Every value goes through esc(); a text naming
   money ($, U+FF04, U+FE69, the words dollar(s)/USD) or holding a lone surrogate (the builder cannot
   write it as UTF-8) is left out whole and renders as if absent. A failed read, or a file of the wrong
   shape, keeps what is on the page; a readable ledger with nothing to show hides the section.
   scripts/test_learnings_panel.py checks both renderers agree; test_learnings_panel.js the repaint. */
function rpLearnHtml(j){
 var days=j&&Array.isArray(j.days)?j.days:null;if(!days)return null;
 days=days.filter(function(d){return !!d&&typeof d==='object'&&Array.isArray(d.picks);});
 days.sort(function(a,b){var x=String(a.date||''),y=String(b.date||'');return x<y?1:(x>y?-1:0);});
 var money=/[$\uff04\ufe69]|(?:^|[^A-Za-z])(?:dollars?|usd)(?![A-Za-z])/i,lone=/[\ud800-\udbff](?![\udc00-\udfff])|(?:^|[^\ud800-\udbff])[\udc00-\udfff]/;
 var ws=/^[\s\x1c-\x1f\x85]+|[\s\x1c-\x1f\x85]+$/g;/* the builder's strip set: JS whitespace plus U+001C-U+001F, U+0085 */
 var t=function(v){var s=typeof v==='string'?v.replace(ws,''):'';return (lone.test(s)||money.test(s))?'':s;};
 var graded=function(p){return !!p&&typeof p==='object'&&(p.result==='W'||p.result==='L'||p.result==='P');};
 var out='',n=0,g=0;
 for(var k=0;k<days.length&&n<6&&g<3;k++){
  var d=days[k];if(!d.picks.some(graded))continue;
  var body=t(d.brief)?'<div class="lnbrief">'+esc(t(d.brief))+'</div>':'';
  for(var q=d.picks.length-1;q>=0&&n<6;q--){
   var p=d.picks[q];if(!graded(p))continue;
   var nm=t(p.name),tx=t(p.note)||t(p.learning);if(!(nm&&tx))continue;
   body+='<div class="lnitem"><div class="lnhead"><span class="lnres '+p.result+'">'+p.result+'</span>'
    +'<span class="lnname">'+esc(nm)+'</span>'
    +(t(p.units)?'<span class="lnunits">'+esc(t(p.units))+'</span>':'')
    +(p.added_after_kickoff===true?'<span class="lntag">added after kickoff</span>':'')
    +'</div><div class="lnnote">'+esc(tx)+'</div></div>';
   n++;
  }
  if(body){out+='<div class="lnday">'+esc(t(d.label)||t(d.date))+'</div>'+body;g++;}
 }
 return out;
}
function rpLearnPanel(){
 var box=$('rpLearn');if(!box)return;var hd=$('rpLearnHead');
 fetch('history.json?cb='+Date.now(),{cache:'no-store'}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){
  var h=rpLearnHtml(j);if(h==null)return;
  box.style.display=h?'':'none';if(hd)hd.style.display=h?'':'none';if(!h)return;
  var tp=document.createElement('template');tp.innerHTML=h;if(tp.innerHTML===box.innerHTML)return;
  box.innerHTML=h;
 }).catch(function(){});
}
rpLearnPanel();setInterval(function(){if(!document.hidden)rpLearnPanel();},120000);
function buildPairs(base){
 PAIRS=[];
 if(!rpMapFresh(SOC_MATCH))return;
 var usedA={};
 /* guard 3 (1:08 9/29) class kill - match BEFORE slicing: slicing the newest 12 unfiltered
    stories first blanked BOTH feeds whenever none of those 12 held an admitted post (the
    11-key/1-verified map). Scan EVERY publishable story for an admitted verified/nearest/
    latest pair, THEN cap at 12 paired stories. base is newest-first (newsBucket sort), so
    the post-match cap keeps the freshest 12 pairs. View-all pool CAR_ALL stays separate. */
 base.forEach(function(a){
  var k=carKey(a);
  var m=SOC_MATCH;
  var pr=(m.pairs||{})[k];
  function take(pid){
   var p=(pid&&SOC_XIDX[pid]!==undefined)?XNEWS[SOC_XIDX[pid]]:null;
   if(p&&!usedA[p.id]&&isPublishablePost(p)){usedA[p.id]=1;return p;}
   return null;
  }
  var post=null,kind=null;
  if(pr&&pr.verified===true){post=take(pr.post_id);if(post)kind='verified';}
  if(!post){var ne=(m.nearest||{})[k];if(ne){post=take(ne.post_id);if(post)kind='latest';}}
  if(!post){var lt=(m.latest||{})[k];if(lt){post=take(lt.post_id);if(post)kind='latest';}}
  if(post)PAIRS.push({a:a,post:post,kind:kind,k:k});
 });
 if(PAIRS.length>12)PAIRS=PAIRS.slice(0,12); /* the 12-cap lives AFTER pairing, never before */
}

/* zero-pair mode: a settled fresh map can legitimately admit ZERO pairs. The feeds never go
   blank and never imply a match: news shows the latest stories and social shows the latest
   posts as INDEPENDENT feeds (own counts, own indices, no shared PAIRS unit, no positional
   correspondence). Social slides carry the muted "Latest from the feed" tier; the verified
   badge stays exclusive to an algorithmic match. */
function zeroPairSocial(n){
 var fp=[],seen={};
 for(var i=0;i<XNEWS.length&&fp.length<n;i++){var p=XNEWS[i];if(p&&isPublishablePost(p)&&isSportsPost(p)&&!seen[p.id]){seen[p.id]=1;fp.push(p);}}
 return fp.map(function(p){return {post:p,kind:'latest',nkey:''};});
}
/* combo freshness (fail closed): a same-game combo renders only when its game date is today
   or later (PT). Date from an explicit date/game_date field, else the -yyyymmdd id suffix;
   no parseable current date -> hidden. A stale combo beside an unpublished card is worse
   than no combo. */
function rpComboFresh(c){
 if(c&&c.status==='expired')return false;
 if(c&&c.futures===true)return true; /* season-long futures items (9/30 NFL rec-yds idea): no day-roll expiry */ /* writer-marked at day close: can never serve */
 var t=new Date(new Date().toLocaleString('en-US',{timeZone:'America/Los_Angeles'}));
 var today=t.getFullYear()*10000+(t.getMonth()+1)*100+t.getDate();
 var d=c&&(c.date||c.game_date||''),n=0,m;
 if(d&&(m=String(d).match(/(\d{4})-?(\d{2})-?(\d{2})/)))n=+(m[1]+m[2]+m[3]);
 if(!n&&(m=String((c&&c.id)||'').match(/(\d{4})(\d{2})(\d{2})\s*$/)))n=+(m[1]+m[2]+m[3]);
 return n>0&&n>=today;
}
/* the Same Game Parlays module (separate script, async fetch callback) reads this as a
   global; without the export the IIFE scope hides it and the module fail-closes hidden. */
window.rpComboFresh=rpComboFresh;
/* EMPTY-STATE CLASS KILL (owner 6:58 9/28): the page NEVER renders empty-feed or
   loading/syncing strings. Last good content (this build only, so a stale badge from
   pre-fix code can never resurrect) is held through every transient: fetch failure,
   bad payload, mid-publish gap, unsettled verdicts. Fresh data replaces it on settle;
   the 30s poll self-heals. */
function feedCacheSave(){try{var s=JSON.stringify({v:RP_BUILD,t:Date.now(),items:CAR_LAST,all:CAR_ALL,pairs:PAIRS});localStorage.setItem('rp_feed_v2',s);localStorage.setItem('rp_feed_stable',s);}catch(e){}}
function feedCacheLoad(){try{var j=JSON.parse(localStorage.getItem('rp_feed_v2')||'null');
 if(!j||j.v!==RP_BUILD){j=JSON.parse(localStorage.getItem('rp_feed_stable')||'null');} /* cross-build hold (7:30 class): a deploy must never cold-boot to blank - the last coherent unit paints with badges suppressed regardless of which build saved it */
 if(!j)return null;
 /* no TTL (owner never-again mandate 10:40): the last coherent unit paints marked stale -
    badges suppressed above, 30s poll re-verifies - through ANY feed gap. Blank only when no
    coherent cache has ever existed. Revocation protection is badge suppression + the poll,
    not blanking (the 15-min TTL re-created the blank-sections incident it predated). */
 /* guard 1 (7:20) source kill of the independent-filter incoherence: pairs are validated
    FIRST, items are DERIVED from the survivors - a cached snapshot can never boot News N
    beside Social N-1. Distinct post IDs only, and the story key must match its pair key. */
 var seen={},pairs=[];
 (j.pairs||[]).forEach(function(p){
  if(!p||!p.a||!p.post)return;
  if(!isPublishableNews(p.a)||!isPublishablePost(p.post))return;
  var k=p.k||carKey(p.a);
  if(carKey(p.a)!==k)return;
  var pid=String(p.post.id||'');
  if(!pid||seen[pid])return;
  seen[pid]=1;
  pairs.push({a:p.a,post:p.post,kind:'latest',k:k}); /* badge suppressed until the live map re-verifies (revocation can never warm-paint) */
 });
 if(!pairs.length){
  if((j.pairs||[]).length)return null; /* broken pair snapshots never degrade to independent news */
  var news=(j.items||[]).filter(isPublishableNews);
  if(!news.length)return null;
  j.items=news;j.pairs=[];j.all=(j.all||news).filter(isPublishableNews);return j;
 }
 j.pairs=pairs;
 j.items=pairs.map(function(p){return p.a;});
 return j;}catch(e){return null;}}
function renderNews(t,arts){
 var box=$('rpNewsCar');if(!box)return;
 if(t&&t.key!=='home'){box.innerHTML='';return;}  /* owner 12:54: News renders on Home only - no leaks, no per-tab feeds */

 var base=(arts||[]).filter(isPublishableNews);
 /* matched-only (owner 1:09/1:11 + 2:59 "factually synced at all times" + QA audit 6): with a
    fresh sync map the news carousel shows ONLY stories holding a URF-verified social pair;
    unmatched stories live in View all News. Counts are a CONSEQUENCE, never forced. No fresh
    map -> fail closed to the plain list (12:29 news-never-blank is about fetch failures, not
    about rendering unverified pairs). */
 /* BIDIRECTIONAL standing rule (user 6:29, supersedes 3:54's paired-or-not floor): the news
    carousel shows ONLY articles carrying an algo match (verified pin, probe-confirmed nearest,
    or on-story latest), and every social slide carries its story's matching post. With no fresh
    map this fails closed to the plain list (12:29: news-never-blank is about fetch failures,
    not about rendering unpaired stories); with a fresh map, unmatched articles are excluded -
    coverage is owned server-side by the widened search and reported before shipping. */
 var curKey=(CAR_LAST[CAR_IDX]&&carKey(CAR_LAST[CAR_IDX]))||''; /* capture the active story key BEFORE replacing the list (guard 1 reorder-jump class) */
 var freshMap=rpMapFresh(SOC_MATCH);
 var items=[];
 if(freshMap&&base.length){
  buildPairs(base);
  items=PAIRS.map(function(p){return p.a;});
 }
 FEED_FALLBACK=false;
 if(!items.length){
  items=base.slice(0,12); /* settled zero-pair map OR aged-out map (guard 1 10/6 cold-load class: the
     rpMapFresh 2h window blanked News for every cold visitor while the feed jobs were down - a stale
     map is an unverified map, not an empty feed): independent latest-content feeds either way, no
     PAIRS unit, nothing implied. The muted caption and the Latest-from-the-feed tier carry the honesty. */
  FEED_FALLBACK=items.length>0;PAIRS=[];
 }
 if(!items.length&&CAR_UNIT){items=CAR_UNIT.items;PAIRS=CAR_UNIT.pairs.map(function(p){return {a:p.a,post:p.post,kind:freshMap?p.kind:'latest',k:p.k};});} /* atomic: prior unit as ONE unit, no stale verification badge */
 if(!items.length){CAR_LAST=[];PAIRS=[];} /* both pools empty and no good unit ever: blank atomically, self-heals on poll */
 if(items.length&&!FEED_FALLBACK){CAR_LAST=items;CAR_UNIT={items:items,pairs:PAIRS.slice()};}
 else if(items.length){CAR_LAST=items;}
 NEWS_READY=true;
 try{document.body.classList.toggle('rp-nosync',!!FEED_FALLBACK);}catch(e){} /* load-race guard (user 3:52 screenshot + QA 3:51): social must know news has rendered before it judges pinned==0 */
 try{var _zn=$('rpZeroNote');if(!_zn){var _sb=$('rpSocial');if(_sb&&_sb.parentNode){_zn=document.createElement('div');_zn.id='rpZeroNote';_zn.className='rp-zeronote';_zn.textContent='No verified matches yet - latest from the feeds';_sb.parentNode.insertBefore(_zn,_sb);}}if(_zn)_zn.style.display=FEED_FALLBACK?'':'none';}catch(e){}
 /* Sep 29 owner "Fix it" via main: the zero-pair state reads INTENTIONAL - one honest caption beside
    the independent feeds, never a manufactured badge. Hidden the moment a pair verifies. */
 CAR_ALL=base.slice(0,40);
 /* class kill (user 4:27 + QA 4:33 verdict 1): BOTH feeds hold the loading state until news,
    x_feed AND the sync-map verdict have all settled - one feed's numbers never render beside
    the other's placeholder. Failure paths set their done flags too, so this always releases. */
 if(!XFEED_DONE||!SOC_MAP_DONE){
  if(CAR_LAST.length&&!$('rpCarTrack')){items=CAR_LAST; /* cold boot, warm cache: paint last good now */}
  else if(CAR_LAST.length){items=CAR_LAST; /* a valid unit is RETAINED through every unsettled window - the 7:30 blank-site regression was clearing here mid-poll (kill-at-source: an unsettled poll must never destroy visible content) */}
  else{box.innerHTML='';CAR_SIG='';CAR_N=0; /* no valid unit ever: blank atomically, old track destroyed with the decision (guard 1 7:20) */ try{renderSocial();}catch(e){}return;}
 }
 var sig=items.map(function(a){return normH(a.headline);}).join('|');
 if(sig===CAR_SIG&&$('rpCarTrack')){carApply();try{renderSocial();}catch(e){}return;}
 CAR_SIG=sig;CAR_N=items.length;
 CAR_IDX=0;
 if(curKey){for(var _ci=0;_ci<items.length;_ci++){if(carKey(items[_ci])===curKey){CAR_IDX=_ci;break;}}}
 if(CAR_IDX>=CAR_N)CAR_IDX=0;
 if(!items.length){
  box.innerHTML='';CAR_SIG='';CAR_N=0; /* last resort: blank box atomically, old track destroyed, never a string (6:58 + guard 1 7:20); 30s poll self-heals */
  return;
 }
 var h='<div class="carvp"><div class="cartrack" id="rpCarTrack">';
 items.forEach(function(a){
  var u=a.link||'',src=a.source||'';
  var img=imgOpt(a.image);
  var lg=String(a.league||'').split('/').pop().toUpperCase()||'SPORTS';
  var blurb=newsBlurb(a),_age=ago(a.published);
  /* owner 6:59 graphics class kill: a card ALWAYS carries art - the real image, or the
     designed league fallback when the source has none or the URL dies at load time. */
  var inner=(img?'<span class="carimg" style="background-image:url(\''+esc(img)+'\')"><img src="'+esc(img)+'" data-rsrc="'+esc(img)+'" data-lg="'+esc(lg)+'" alt="" style="display:none" onerror="RPimgErr(this)"></span>':'<span class="carimg carimg-fb" data-lg="'+esc(lg)+'"></span>')
   +'<span class="carbody"><span class="carhead">'+esc(unesc(a.headline||''))+'</span>'
   +(blurb?'<span class="carblurb">'+esc(unesc(blurb))+'</span>':'')
   +'<span class="carmeta"><span class="src '+esc(src.toLowerCase())+'">'+esc(src)+'</span>'+(_age?' \u00b7 '+esc(_age):'')+(isNewIt(a)?' <span class="carnew">new</span>':'')+'</span></span>';
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
 try{renderSocial();}catch(e){} /* news rendered last: social rebuilds on the shared list now */
 feedCacheSave();
}
/* X social section (owner 10:32: X posts out of news, own Home section; built 11:53 scope):
   renders the x_feed items XNEWS already normalizes; Home-only visibility via body.tab-home CSS. */
var SOC_SIG='',SOC_IDX=0,SOC_N=0,SOC_LAST=[];
var FEED_FALLBACK=false;
var SOC_TIMER=null;
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
function socGo(d){
 /* one shared index (QA 4:33 verdict 2): social Prev/Next drives the SAME index as news -
    carAdv moves CAR_IDX and carMove's sync call pulls social along via socSync.
    feed guard 1 (9/30 12:04 AM pixel repro): in fallback the feeds are independent - equal
    counts are coincidence, carAdv would advance NEWS and leave SOCIAL stuck. Fallback always socAdv. */
 if(!FEED_FALLBACK&&SOC_N>0&&SOC_N===CAR_N){carAdv(d);return;}
 socAdv(d);
}
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
   var p=XNEWS[xi];if(!isPublishablePost(p))return;var txt=String(p.headline||'');
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
var SOC_MATCH=null,SOC_MATCH_OK=false,SOC_XIDX={},SOC_RIDX={},SOC_MATCH_PENDING=null;
/* guard 1 (1:28 9/29) coherent first-load settle: the initial map fetch can land BEFORE the
   news/X generations it must match, and discarding it forced a ~45s blank wait on rtPoll.
   Hold the fetched map and revalidate the moment BOTH generations exist - one coherent
   PAIRS unit paints as soon as the inputs are ready, no transient blank beyond network. */
function socMapRetry(){
 if(SOC_MATCH_OK||!SOC_MATCH_PENDING)return;
 if(!rpMapFresh(SOC_MATCH_PENDING))return;
 SOC_MATCH=SOC_MATCH_PENDING;SOC_MATCH_PENDING=null;SOC_MATCH_OK=true;
 try{if(typeof cur!=='undefined'&&cur&&cur.key==='home')renderNews(cur,newsBucket(cur));renderSocial();socSync();}catch(e){}
}
var XFEED_GEN=null; /* generation of the X payload actually ingested, not the wall-clock fetch time */
/* owner 1:26: social feed renders sports-relevant, topic-matching posts only - never a raw
   firehose. Fresh map: server relevance layer (URF evidence gate) decides per post. No fresh
   map: this keyword floor is the fallback so raw off-topic chatter never renders. */
/* owner 1:39: NO tout/selling-access posts, ever - client layer mirrors the server filter so
   legacy pool items and no-map fallbacks are covered too. */
var RP_AD_KW=/happy hour|dine[ -]?in|grab a (table|seat|cold one)|tall domestics|half rack|drink specials?|food specials?|come watch|watch party|patio|\$\d+(\.\d+)? (tall|pint|wing|slice|pitcher)|book a table|now open|grand opening|tickets? (to see|for|available)|[0-9]x tickets|seats? (available|for sale)|get rid of|price.{0,12}negotiable|send me a dm|dm if you|selling (my|[0-9])|face value|stubhub|vivid ?seats|seatgeek|tickpick|ticketmaster|gametime|freebie|free picks? on|model.{0,20}(is )?(live|cashed)|cashed some|brought to you by|listen in now|tune in (now|tonight)|[0-9]{2,3}\.[0-9] ?fm|[0-9]{3,4} ?am\b|get-in (price|as)|best free|top [0-9]+ (player )?props|deposit (bonus|match|offer)|bonus bets?|#\s*(ad|ads|sponsored|sponsorship)\b|#\w*sale\b|#giveaway\b|follow\s+(us|me|@\w+)\b.{0,40}(to win|to enter|for a chance|giveaway)|(secure|reserve|book)\s+(a\s+|your\s+)table|(arrive|get (there|here)|come)\s+early\b[^.!?]{0,50}(secure|reserve|grab|book)\s+(a\s+|your\s+)?(table|spot|seat)|free picks?\s*(up|here|today|tonight|now|below|thread|incoming|alert|inside|drop)/i;
var RP_TOUT_KW=/discord|telegram|dubclub|patreon|link in bio|dm (me|us) for|vip (picks|plays|access)|picks package|premium picks|paywall|subscribe for|promo code|join my|tap in with|free (play|pick)s? (today|daily)|lock of the day|guaranteed (winner|play)|freebie|free picks? on|model.{0,20}(is )?(live|cashed)|free signals?|vip[- ]?[0-9]* ?trades?|take[- ]?profits?|\btp[1-4]\b|stop[- ]?loss|(?:crypto|forex|trading) signals?|bitcoin|\b(?:btc|eth|xrp|doge|pepe|shib)\b|solana|memecoins?|altcoins?|binance|bybit|bitget|kucoin|\bokx\b|\bmexc\b|airdrops?|pump[ -]?fun|long setup|short setup|\b(?:50|100)x\b|\$(?:BTC|ETH|XRP|SOL|DOGE|ADA|PEPE|SHIB)\b/i;
/* guard 3+5 class kill: ONE publishability predicate on the COMPLETE post payload (text + link +
   author branding) - applied at XNEWS ingestion AND re-asserted at every display boundary
   (pin, nearest, bridge, more modal). Account branding counts (the Brownstone Bets class). */
/* sportsbook/operator brands are banned at author AND handle (guard 3 Betfair class) - a
   sportsbook-authored post is operator content by construction, whatever its text says. */
var RP_OPERATOR='bets|capper|cappers|handicapp|betfair|bet99|draftkings|fanduel|kalshi|betmgm|caesars|bet365|pointsbet|betrivers|unibet|betway|polymarket|sportsbook|cry|crypto|forex|btc|eth|xrp|solana|memecoin|altcoins?|defi|web3|signals';
/* zero-pair fallback sports gate (feed guard 1, Sep 29): fallback Social renders UNPAIRED
   posts, so candidates must be genuine sports posts - publishability kills touts/ads/operators
   but not off-topic content (the finance-solicitation / politics / fashion / sexual-solicitation /
   lost-luggage class observed in the first-12 X records). Positive sports context required
   (strong sport term OR team name OR 2+ weak game terms); a non-sports kill list denies even
   keyword-stuffed spam. Pair rendering (buildPairs take) is untouched: server-verified pairs
   never re-gate on heuristics, and the no-forced-match rule stands. */
var RP_NONSPORT_KILL=/only ?fans|lingerie|\bnudes?\b|nsfw|18\+|spicy content|hookup|escort|sext(ing)?\b|election|ballot|\bpresident\b|congress|senate|democrat|republican|midterms?|campaign rally|polling|immigration|ceasefire|stock tips|nasdaq|s&p 500|passive income|\bfashion\b|runway|\bootd\b|makeup|skincare|weight loss|diet pills|essay (help|service)|homework help/i;
var RP_SPORT_ACRO=/\b(nfl|nba|mlb|nhl|wnba|mls|nwsl|ncaa|cfb|ufc|mma|pga|atp|wta|nascar)\b/gi;
var RP_SPORT_STRONG=/\b(formula 1|football|basketball|baseball|hoops|hockey|soccer|tennis|golf|boxing|quarterback|touchdown|pitcher|pitching|home run|homer|goalie|playoffs?|super bowl|stanley cup|world series|march madness|heisman|grand slam|wimbledon|daytona|heavyweight|knockout|innings?|dugout|bullpen|buzzer beater|free throw|field goal|batting|\bpuck\b|rbi|strikeout|power play|penalty kick|slam dunk|fastball|curveball|faceoff|hat trick|slugger|halfcourt)\b/i;
var RP_SPORT_TEAMS=/\b(yankees|red sox|dodgers|cubs|cardinals|braves|astros|mets|phillies|padres|rangers|orioles|blue jays|guardians|tigers|royals|twins|white sox|athletics|angels|mariners|marlins|nationals|pirates|\breds\b|brewers|diamondbacks|d-backs|rockies|lakers|celtics|warriors|knicks|\bnets\b|sixers|76ers|\bbulls\b|bucks|cavaliers|\bcavs\b|mavericks|\bmavs\b|nuggets|\bsuns\b|clippers|grizzlies|\bhawks\b|hornets|pacers|pistons|raptors|wizards|\bspurs\b|\bthunder\b|timberwolves|trail blazers|\bjazz\b|pelicans|rockets|chiefs|eagles|cowboys|packers|\bbears\b|lions|vikings|falcons|saints|buccaneers|\bbucs\b|\brams\b|seahawks|49ers|raiders|chargers|broncos|ravens|bengals|browns|steelers|\bcolts\b|jaguars|texans|titans|dolphins|patriots|commanders|bruins|maple leafs|canadiens|oilers|avalanche|golden knights|\bkraken\b|canucks|flames|predators|blackhawks|red wings|penguins|capitals|flyers|islanders|hurricanes|lightning|senators|sabres|blue jackets|\bgiants\b|\bjets\b|panthers|\bheat\b|timberwolves|\bwolves\b|\bkings\b|\bleafs\b|\bhabs\b|anaheim ducks|winnipeg|buffalo bills|seattle seahawks)\b/i;
var RP_SPORT_WEAK=/\bgames?\b|\bwins?\b|\bloss(es)?\b|\bscored?\b|\btraded?\b|\binjur(y|ed|ies)\b|\bcoach(ed)?\b|\broster\b|\bdraft(ed)?\b|\bseason\b|\bopener\b|\bovertime\b|\bot\b|\bhalftime\b|\bstadium\b|\barena\b|\bcontract\b|\bextension\b|\bsuspension\b|\bejected\b|\brankings?\b|\bmvp\b|\bdebut\b|\bstreak\b|\bcomeback\b|\bupset\b|\brivalry\b|\bchampionship\b|\btournament\b|\bspread\b|\bparlay\b|\bprops\b|\bodds\b|\blineups?\b|\b\d{1,3}\s*[-–]\s*\d{1,3}\b/gi;
function isSportsPost(p){
 if(!p)return false;
 var t=(String(p.headline||'')+' '+String(p.author||'')).normalize('NFKC');
 if(RP_NONSPORT_KILL.test(t))return false; /* deny-side keeps the full payload (author included) */
 /* residual-leak fix (9/29, Emmagrace51 hashtag-stuffing + "tech giants" classes): sports
    evidence must come from the substantive BODY - author, URL and hashtag tokens never
    establish relevance, and a bare team word needs a second game signal (a matchup counts).
    Mirrors x_feed._sports_post / news_social._sports_post byte-for-byte in logic. */
 var body=String(p.headline||'').replace(/https?:\/\/\S+/g,' ').replace(/#\w+/g,' ').normalize('NFKC');
 if(RP_SPORT_STRONG.test(body))return true;
 /* RP_SPORT_TEAMS is /i (boolean-tested elsewhere): a plain .match counts full+capture, so a
    single team word reads as 2. Count real occurrences with a /gi copy. */
 var teams=(body.match(new RegExp(RP_SPORT_TEAMS.source,'gi'))||[]).length;
 var acro=(body.match(RP_SPORT_ACRO)||[]).length, weak=(body.match(RP_SPORT_WEAK)||[]).length;
 if(acro>=2&&weak===0)return false; /* bare-acronym stuffing: "NFL NBA MLB" with no game context is spam, not fandom */
 return teams>=2||(teams>=1&&acro+weak>=1)||acro>=1||weak>=2;
}
var RP_COMM_CTA=/\bjoin up\b|link in\b[^.!?\n]{0,12}\bbio\b|\bfree ?(?:play|pick)s?\b|\bpotd\b|\bplay of the day\b|boosted (?:odds|parlays?)|@playbook\b/i;
var RP_COMM_TAG=/#\s*(?:gamblingtwitter|gamblingx|prizepicks|freepicks?|sportsbetting|draftkings|fanduel|betmgm|bettingtips?|gambling)\b/i;
var RP_COMM_FREE=/\b(?:mlb|nfl|nba|nhl|wnba|cfb|ncaa|ufc|mls)\b[^.!?\n]{0,16}\bfree(?![- ](?:agent|agency|throws?|kicks?|transfer))\b|\bfree(?![- ](?:agent|agency|throws?|kicks?|transfer))\b[^.!?\n]{0,16}\b(?:mlb|nfl|nba|nhl|wnba|cfb|ncaa|ufc|mls)\b/i;
var RP_COMM_ODDS=/[-+]\d{3}\b/g;
function isPublishablePost(p){
 if(!p)return false;
 var t=(String(p.headline||'')+' '+String(p.link||'')+' '+String(p.author||'')+' '+String(p.handle||'')).normalize('NFKC').replace(/#\s+/g,'#');
 if(RP_TOUT_KW.test(t)||RP_AD_KW.test(t)||/\bFREE (PICKS?|SIGNALS?)\b/.test(t))return false;
 /* promo-sentinel 9/29 7:07 class: tout/acquisition CTA + destination rules, mirror of
    x_feed._commercial / news_social._commercial - byte-identical pattern text. */
 if(RP_COMM_CTA.test(t))return false;
 if(RP_COMM_TAG.test(t)&&/https?:\/\//.test(String(p.headline||'')))return false;
 /* free betting-sheet class (sentinel 9/29 7:38), mirror of _commercial: sport-near-free +
    >=2 concrete prices + outbound link; free-agent/free-throw etc whitelisted via lookahead. */
 if(RP_COMM_FREE.test(t)&&((String(p.headline||'').match(RP_COMM_ODDS)||[]).length>=2)&&/https?:\/\//.test(String(p.headline||'')))return false;
 if(new RegExp('\\b('+RP_OPERATOR+')\\b','i').test((String(p.author||'')+' '+String(p.handle||'')).normalize('NFKC').replace(/[^A-Za-z0-9]+/g,' ')))return false;
 return true;
}
/* guard 3 news-side default-deny (his 5:27/5:28 rule, one layer up): promo-code / bonus-bet /
   free-bet inducement / sponsored-affiliate articles never render in ANY news surface -
   carousel, ticker, View all News, league tabs, ESPN fallback. */
var RP_PROMO_NEWS=/promo code|bonus bets?|free bets?|bet \$?[0-9]+.{0,25}(get|claim)|claim \$?[0-9]+|deposit (bonus|match|offer)|sign ?up (offer|bonus|promo)|new (user|customer)s? (offer|bonus|promo)|sponsored content/i;
function isPublishableNews(a){
 if(!a||!String(a.headline||'').trim())return false;
 var stamp=Date.parse(a.published||'');
 if(isFinite(stamp)&&stamp>Date.now()+RP_FUTURE_SKEW)return false;
 var t=(String(a.headline||'')+' '+String(a.blurb||'')+' '+String(a.link||'')+' '+String(a.source||'')).normalize('NFKC');
 return !RP_PROMO_NEWS.test(t);
}
var RP_SPORT_KW=/nfl|nba|mlb|nhl|wnba|ncaa|cfb|mls|nwsl|pga|nascar|ufc|mma|boxing|tennis|football|basketball|baseball|hockey|soccer|golf|sports|touchdown|quarterback|playoff|super bowl|world series|stanley cup|fantasy|draft pick|trade rumor|injury report|starting lineup|home run|slam dunk|shutout|knockout|title fight|grand slam|eagles|bears|chiefs|cowboys|packers|vikings|giants|jets|patriots|steelers|ravens|bengals|browns|texans|colts|jaguars|titans|broncos|raiders|chargers|rams|seahawks|49ers|cardinals|falcons|panthers|saints|buccaneers|commanders|lions|dolphins|bills|yankees|dodgers|red sox|cubs|braves|astros|phillies|mets|padres|mariners|lakers|celtics|warriors|knicks|nets|sixers|bulls|heat|bucks|nuggets|suns|mavericks|thunder|timberwolves|spurs|rockets|clippers|grizzlies|pelicans|kings|trail blazers|jazz|hawks|hornets|hornets|pacers|cavaliers|pistons|magic|wizards|raptors|maple leafs|bruins|canadiens|oilers|avalanche|lightning|panthers|rangers|penguins|capitals|flyers|red wings|blackhawks|wild|stars|predators|blues|jets|kraken|golden knights|sharks|ducks|kings|coyotes|hurricanes|blue jackets|devils|islanders|sabres|senators|flames|canucks/i;
fetch('slates/soc_match.json?cb='+Date.now(),{cache:'no-store'}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(m){
 if(rpMapFresh(m)){SOC_MATCH=m;SOC_MATCH_OK=true;} /* stamped maps wait for matching served feed generations */
 else{SOC_MATCH_PENDING=m;} /* guard 1: hold for generation arrival - socMapRetry promotes it */
 SOC_MAP_DONE=true; /* settled = verdict reached (fresh map OR rejected); the feeds may now build */
 try{if(cur&&cur.key==='home')renderNews(cur,newsBucket(cur));renderSocial();socSync();}catch(e){}
}).catch(function(){SOC_MATCH_OK=false;SOC_MAP_DONE=true;
 try{if(cur&&cur.key==='home')renderNews(cur,newsBucket(cur));renderSocial();}catch(e){}});
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
 /* class kill (user 4:27 "feeds must never disagree" + QA 4:33): ONE shared displayed list.
    Social slides are built 1:1 from the news slides - same N, same index, same counter, always.
    Until news, x_feed and the sync-map verdict have ALL settled, show the loading state -
    never a number that can disagree with the news counter. */
 if(!NEWS_READY||!XFEED_DONE||!SOC_MAP_DONE||!CAR_LAST.length){
  if(PAIRS.length&&!$('rpSocTrack')){SOC_SIG=''; /* cold boot, warm cache: paint cached pairs below */}
  else if(NEWS_READY&&XFEED_DONE&&SOC_MAP_DONE){
   /* guard 1 10/6: all feeds SETTLED with zero inventory is an unavailable state, never a blank one -
      the status shows independently of news-carousel inventory; self-heals on the 30s poll */
   box.innerHTML='<div id="rpSocUnavail" class="rp-socunavail" role="status" style="padding:14px 12px;color:var(--muted,#9aa4ad);font-size:13px;line-height:1.4">Social feed temporarily unavailable. Check back soon.</div>';
   SOC_SIG='';SOC_N=0;SOC_LAST=[];SOC_RIDX={};
   if(SOC_TIMER){clearInterval(SOC_TIMER);SOC_TIMER=null;}
   try{var _zu2=$('rpZeroNote');if(_zu2)_zu2.style.display='none';}catch(e){}
   return;
  }
  else{if(!$('rpSocTrack'))box.innerHTML='';SOC_SIG='';SOC_N=0;return;}
 }
 /* owner 5:09 (his words: "It shouldn't say it's scanning, it should always have the latest post
    about the story"): every slide shows a REAL post - never a placeholder. Per story: probe-verified
    pair (green badge) -> the map's nearest-on-story post (muted label, probe-rejects honored) ->
    league-relevant pool -> most recent sports post. Non-verified NEVER claims sync (1:00 stands:
    no link claims the URF verdict without the full loop; the muted label makes that honest). */
 /* guard 1 shared array: social renders EXACTLY the resolved PAIRS - same order, same N,
    same index as the news carousel. No independent filtering here, no cascade, no fallback. */
 var items=FEED_FALLBACK?zeroPairSocial(12):PAIRS.map(function(p){return {post:p.post,kind:p.kind,nkey:p.k};});
 /* zero AVAILABLE posts (feed down) is NOT zero MATCHING pairs: say the feed is unavailable, render no controls and no caption implying posts exist (owner/guard 1, 10/1 12:13 AM visuals). Self-heals when posts return. */
 if(!items.length){
  box.innerHTML='<div id="rpSocUnavail" class="rp-socunavail" role="status" style="padding:14px 12px;color:var(--muted,#9aa4ad);font-size:13px;line-height:1.4">Social feed temporarily unavailable. Check back soon.</div>';
  SOC_SIG='';SOC_N=0;SOC_LAST=[];SOC_RIDX={};
  if(SOC_TIMER){clearInterval(SOC_TIMER);SOC_TIMER=null;}
  try{var _zu=$('rpZeroNote');if(_zu)_zu.style.display='none';}catch(e){}
  return;
 }
 var sig=items.map(function(it){return ((it.post&&it.post.id)||'-')+it.kind;}).join('|');
 if(sig===SOC_SIG&&$('rpSocTrack')){socApply();return;}
 SOC_SIG=sig;SOC_N=items.length;SOC_LAST=items;
 SOC_RIDX={};items.forEach(function(it,i){if(it.post&&it.post.id)SOC_RIDX[it.post.id]=i;});
 var _ck=(CAR_LAST[CAR_IDX]&&carKey(CAR_LAST[CAR_IDX]))||'';SOC_IDX=0;
 for(var _si=0;_si<items.length;_si++){if(items[_si].nkey===_ck){SOC_IDX=_si;break;}}
 if(SOC_IDX>=SOC_N)SOC_IDX=SOC_N-1;if(SOC_IDX<0)SOC_IDX=0;
 var h='<div class="carvp socvp"><div class="cartrack" id="rpSocTrack">';
 items.forEach(function(it){
  var p=it.post;
  if(!p)return; /* defensive: no slide ever renders the abstain line (owner 6:08) */
  var txt=String(p.headline||'');
  if(txt.length>280)txt=txt.slice(0,277)+'\u2026';
  var badge=it.kind==='verified'?'<span class="syncbadge">Verified by UltRix</span>':'<span class="synclatest">Latest from the feed</span>';
  var inner='<span class="carbody">'+badge+'<span class="stxt">'+esc(unesc(txt))+'</span>'
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
 if(FEED_FALLBACK){if(SOC_N>1&&!SOC_TIMER)SOC_TIMER=setInterval(socStep,7000);} /* own clock, off the news tick */
 else if(SOC_TIMER){clearInterval(SOC_TIMER);SOC_TIMER=null;}
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
var NEWSF=null,NEWSF_TS=0,XNEWS=[],XNEWS_TS=0,HOME_GAMES_TS=0,HOME_GAMES_PAINT=null,NEWS_READY=false,SOC_MAP_DONE=false,XFEED_DONE=false;
/* ESPN scoreboard days for day-scoped leagues (Oct 1: MLB/NHL rows never appeared - the bare
   scoreboard is ESPN's current day, which still reads yesterday's finals after midnight ET, and a
   dates=A-B range answers 400). ESPN files games under US Eastern calendar days. */
function rpEspnDays(n){
 var t=new Date(),y=0,m=0,d=0,out=[],i,u;
 try{var p={};new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',year:'numeric',month:'numeric',day:'numeric'}).formatToParts(t).forEach(function(x){p[x.type]=x.value;});y=+p.year;m=+p.month;d=+p.day;}catch(e){}
 if(!y){y=t.getUTCFullYear();m=t.getUTCMonth()+1;d=t.getUTCDate();}
 for(i=0;i<n;i++){u=new Date(Date.UTC(y,m-1,d+i));out.push(String(u.getUTCFullYear())+('0'+(u.getUTCMonth()+1)).slice(-2)+('0'+u.getUTCDate()).slice(-2));}
 return out;
}
/* guard 5 open-session class: the client knows its own build (stamped in this document by the
   builder) and self-updates when rtPoll sees a newer slates/build.json - a behind client never
   keeps old gates. Scroll position survives the controlled same-tab refresh. */
var RP_BUILD=(function(){var h=document.documentElement.innerHTML;var m=h.match(/build (\d{10})/)||h.match(/[?&]v=(\d{10})/);return m?+m[1]:0;})();
try{var _up=sessionStorage.getItem('rpUpd');if(_up){sessionStorage.removeItem('rpUpd');var _u=JSON.parse(_up);if(_u&&typeof _u.y==='number')setTimeout(function(){window.scrollTo(0,_u.y);},400);}}catch(e){}
/* REAL-TIME feeds (owner 12:44): poll feed JSONs + cached UltRix match map on a short interval,
   merge newest-first, keep the user's current slide stable, live counter, subtle 'new' marker.
   The match map stays build-time cached (12:37) - clients never touch the NIM endpoint. */
var RP_LOAD=Date.now();
function carKey(a){return (a&&a.link)||String((a&&a.headline)||'');}
function isNewIt(a){var t=pubT(a&&a.published);return t&&t>RP_LOAD;}
function rpMapFresh(m,newsGen,xGen){
 if(!(m&&m.built_at&&(Date.now()-Date.parse(m.built_at))<2*3600*1000&&m.pairs))return false;
 /* Old maps have no generation stamps and retain their prior built_at-only behavior.
    On stamped maps, an unavailable or different fetched generation is a mid-publish
    boundary, not permission to pair a newer story/post against an older map. */
 if(newsGen===undefined)newsGen=NEWSF&&NEWSF.generated_at;
 if(xGen===undefined)xGen=XFEED_GEN;
 function same(a,b){var x=Date.parse(a),y=Date.parse(b);return !!(a&&b&&isFinite(x)&&isFinite(y)&&x===y);}
 if(m.news_generated_at&&!same(m.news_generated_at,newsGen))return false;
 if(m.x_generated_at&&!same(m.x_generated_at,xGen))return false;
 return true;
}
function rpNewsPayload(j){
 return !!(j&&typeof j.generated_at==='string'&&isFinite(Date.parse(j.generated_at))
  &&Array.isArray(j.latest)&&j.leagues&&typeof j.leagues==='object'&&!Array.isArray(j.leagues));
}
function rpFeedJson(u){
 var ctl=new AbortController(),timer=setTimeout(function(){ctl.abort();},7000);
 return fetch(u+(u.indexOf('?')<0?'?':'&')+'cb='+Date.now(),{cache:'no-store',signal:ctl.signal})
  .then(function(r){if(!r.ok)throw new Error('feed unavailable');return r.json();})
  .finally(function(){clearTimeout(timer);});
}
function rpFetchNews(){
 /* The live worker is the existing news producer. Static Pages is a last-good fallback,
    not the freshness authority when the GitHub bridge is stopped. */
 return rpFeedJson('https://rixpicks-feeds.itsdardanr.workers.dev/feeds/news.json')
  .then(function(j){if(!rpNewsPayload(j))throw new Error('invalid news feed');return j;})
  .catch(function(){return rpFeedJson('slates/news.json').then(function(j){
   if(!rpNewsPayload(j))throw new Error('invalid news fallback');return j;
  });}).then(function(j){
   return rpNewsPayload(NEWSF)&&Date.parse(NEWSF.generated_at)>Date.parse(j.generated_at)?NEWSF:j;
  });
}
function rpPredItems(j){
 var now=Date.now();
 return ((j&&Array.isArray(j.items))?j.items:[]).filter(function(p){
  var start=Date.parse(p&&p.kickoff_utc||'');
  return !!(p&&typeof p.prediction==='string'&&p.prediction.trim()&&isFinite(start)&&start>now
    &&!p.result&&p.status!=='expired'&&p.status!=='settled');
 }).slice(0,6);
}
function rtPoll(){
 /* guard 5 live-loop class: news, x_feed and the map were three independent requests each
    committing as it landed - fresh news beside stale social, fresh X against an old map. Now one
    coordinated settle: successes stage together and render once; a failed source holds its last
    good state; map expiry revokes sync verdicts EVERY tick (open tabs never run expired verdicts). */
 var g=rpFeedJson;
 Promise.allSettled([rpFetchNews(),g('slates/x_feed.json'),g('slates/soc_match.json'),g('slates/build.json')]).then(function(rs){
  var v=rs[3].status==='fulfilled'?rs[3].value:null;
  if(v&&v.build&&RP_BUILD&&+v.build>+RP_BUILD){
   try{sessionStorage.setItem('rpUpd',JSON.stringify({y:window.scrollY||0}));}catch(e){}
   (window.rpReload||location.reload.bind(location))();return; /* controlled same-tab code refresh: behind clients never keep old gates */
  }
  var mv=rs[2].status==='fulfilled'?rs[2].value:null;
  if(mv&&mv.client_build&&RP_BUILD&&+mv.client_build>+RP_BUILD){
   try{sessionStorage.setItem('rpUpd',JSON.stringify({y:window.scrollY||0}));}catch(e){}
   (window.rpReload||location.reload.bind(location))();return; /* guard 5 bootstrap kill: version signal rides the map payload every tick */
  }
  var nj=rs[0].status==='fulfilled'?rs[0].value:null;
  var xj=rs[1].status==='fulfilled'?rs[1].value:null;
  var mj=rs[2].status==='fulfilled'?rs[2].value:null;
  /* Stage the fetched generations before accepting the map; do not briefly render
     a new news/X artifact against the previous map while the matcher is still publishing. */
  var nextNews=(nj&&nj.generated_at)||NEWSF&&NEWSF.generated_at;
  var nextX=(xj&&Array.isArray(xj.items)&&xj.generated_at)||XFEED_GEN;
  if(rpMapFresh(mj,nextNews,nextX)){SOC_MATCH=mj;SOC_MATCH_OK=true;}
  else{SOC_MATCH=null;SOC_MATCH_OK=false;} /* stale, mismatched, or unreadable map: hold prior coherent unit */
  if(xj&&Array.isArray(xj.items)){ingestX(xj);XFEED_DONE=true;}
  if(nj&&nj.generated_at&&(!NEWSF||nj.generated_at!==NEWSF.generated_at)){NEWSF=nj;NEWSF_TS=Date.now();}
  if(typeof cur!=='undefined'&&cur&&cur.key==='home'){renderNews(cur,newsBucket(cur));renderSocial();socSync();tickRender();renderPred();}
 });
}
setInterval(rtPoll,45000);
window.__rpRT={poll:rtPoll,state:function(){return {gen:NEWSF&&NEWSF.generated_at,carIdx:CAR_IDX,carN:CAR_N,socN:SOC_N,curKey:typeof cur!=='undefined'&&cur&&cur.key};}};
function ingestX(j){ /* single publishability-gated ingest path (guard 3): XNEWS holds vetted posts only; author NAME + HANDLE both retained (sentinel 9/29 7:24: a name-only copy hides tout handles like *Lockz from the predicate) */
 XFEED_GEN=j.generated_at||null;
 if(SOC_MATCH_OK&&!rpMapFresh(SOC_MATCH)){SOC_MATCH_OK=false;} /* independent first-load X fetch may outrun map */
 XNEWS=j.items.filter(function(p){return p&&/^[0-9]+$/.test(String(p.id||''))&&p.created_at&&p.text;}).map(function(p){var u=(typeof p.url==='string'&&/^https:\/\/(?:www\.)?(?:x\.com|twitter\.com)\/[A-Za-z0-9_]+\/status\/[0-9]+(?:\?.*)?$/.test(p.url)&&p.url.split('/status/')[1].split('?')[0]===String(p.id))?p.url:'';return {id:String(p.id),headline:String(p.text).slice(0,900),link:u,published:p.created_at,source:'X',author:typeof p.author_name==='string'?p.author_name.slice(0,80):'',handle:typeof p.author_username==='string'?p.author_username.slice(0,80):''};}).filter(isPublishablePost);
 SOC_XIDX={};XNEWS.forEach(function(p,i){if(p.id)SOC_XIDX[p.id]=i;});
 socMapRetry(); /* X generation + post index settled - promote a held map the moment it coheres */
}
function refreshX(){
 if(Date.now()-XNEWS_TS<60000)return;
 XNEWS_TS=Date.now();
 fetch('slates/x_feed.json?cb='+Date.now(),{cache:'no-store'}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){
  if(!j||!Array.isArray(j.items))throw 0;
  ingestX(j);
  XFEED_DONE=true;
  renderSocial();
 if(cur&&cur.key==='home')renderNews(cur,newsBucket(cur));
 }).catch(function(){XFEED_DONE=true;try{renderSocial();if(cur&&cur.key==='home')renderNews(cur,newsBucket(cur));}catch(e){}});
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
/* ticker core (stutter hunt 9/28): crawl driven by rAF at CONSTANT px/s in JS, never
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
 var arts=newsBucket({key:'home'});
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
   tr.style.animation=TICK_V>0?('rpTickX '+(nh>0?(nh/TICK_V).toFixed(2):1)+'s linear infinite'):'none';
  }
 });
}
function loadSide(t){
 var lg=lgpath(t),now=Date.now();
 /* polish (main 1:43): never show another tab's stale rows while the target tab's sidebar
    loads - cached tabs render instantly via the SB path, uncached get an honest Loading. */
 var _gb0=$('rpGames');
 if(_gb0&&t.key!=='home'){_gb0.classList.remove('homeall');if(!SB[t.key])_gb0.innerHTML='<div class="empty">Loading upcoming events&hellip;</div>';}
 if(t.key==='home'){refreshX();renderSocial();}
 if(!lg){
  if(t.key==='wooder'){
   /* wooder sidebar (1:17 regression kill: empty box on direct #wooder load - the tab has no
      espn path so neither sidebar branch filled it). Wooder Ice is NFL content: NFL scoreboard. */
   if(SB[t.key]&&now-(SB_TS[t.key]||0)<60000){renderGames(t,SB[t.key]);}
   else{fetch('https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?limit=50',{cache:'no-store'}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){SB[t.key]=j.events||[];SB_TS[t.key]=Date.now();if(cur===t)renderGames(t,SB[t.key]);}).catch(function(){if(cur===t)renderGames(t,SB[t.key]||null);});}
  }
  /* Trinity and Past Tickets have no league of their own, so neither sidebar branch filled them and they sat on
     'Loading upcoming events' for good. They show the same every-league list as Home. */
  if(t.key==='home'||t.key==='trinity'||t.key==='past'){
   var gb=$('rpGames'),games=[{label:'NFL',espn:'football/nfl'},{label:'CFB',espn:'football/college-football'},{label:'NBA',espn:'basketball/nba'},{label:'WNBA',espn:'basketball/wnba'},{label:'MLB',espn:'baseball/mlb'},{label:'NHL',espn:'hockey/nhl'},{label:'NCAAB',espn:'basketball/mens-college-basketball'},{label:'MLS',espn:'soccer/usa.1'},{label:'NWSL',espn:'soccer/usa.nwsl'},{label:'PGA',espn:'golf/pga'},{label:'NASCAR',espn:'racing/nascar-premier'},{label:'UFC',espn:'mma/ufc'},{label:'ATP',espn:'tennis/atp'},{label:'WTA',espn:'tennis/wta'}];
   /* day-scoped leagues read one ESPN day per request, today through +3 (the 72h window); week
      (NFL/CFB) and event (golf/racing/UFC/tennis) boards already span it. racing/nascar 400s
      on every load; racing/nascar-premier is the live route (same alias live.html uses). */
   var RP_DAY_LG={'basketball/nba':1,'basketball/wnba':1,'baseball/mlb':1,'hockey/nhl':1,'basketball/mens-college-basketball':1,'soccer/usa.1':1,'soccer/usa.nwsl':1};
   if(gb&&Date.now()-HOME_GAMES_TS<=300000&&HOME_GAMES_PAINT&&!gb.classList.contains('homeall')){
    /* back on Home inside the 5-min refetch guard: another tab left its rows (or its Loading
       line) in the shared panel - repaint the rows already fetched instead of waiting it out. */
    gb.classList.add('homeall');HOME_GAMES_PAINT();
   }
   if(gb&&Date.now()-HOME_GAMES_TS>300000){
   HOME_GAMES_TS=Date.now();
   /* owner 2:12: 72h window, EVERY covered league, no count cap (was 48h + slice(0,9)).
      owner 2:13 intermittent-load kill: the old Promise.all gated the whole section on the
      SLOWEST league fetch with NO timeout - one hung ESPN call stalled every row. Now each
      league gets a 7s abort and paints progressively as it lands. */
   gb.classList.add('homeall');
   var _days=rpEspnDays(4),_reqs=[];
   games.forEach(function(x){var b='https://site.api.espn.com/apis/site/v2/sports/'+x.espn+'/scoreboard?limit=50';if(RP_DAY_LG[x.espn])_days.forEach(function(d){_reqs.push({x:x,u:b+'&dates='+d});});else _reqs.push({x:x,u:b});});
   var _acc=[],_seenG={},_pend=_reqs.length;
   var _rowH=function(g){var c=(g.event.competitions||[])[0]||{},a=(c.competitors||[]).filter(function(x){return x.homeAway==='away';})[0]||{},h=(c.competitors||[]).filter(function(x){return x.homeAway==='home';})[0]||{};var _an=(a.team||{}).abbreviation||(a.team||{}).shortDisplayName||(a.team||{}).displayName||(a.athlete||{}).shortName||(a.athlete||{}).displayName||'',_hn=(h.team||{}).abbreviation||(h.team||{}).shortDisplayName||(h.team||{}).displayName||(h.athlete||{}).shortName||(h.athlete||{}).displayName||'';var title=(_an&&_hn)?(esc(_an)+(c.neutralSite?' vs ':' @ ')+esc(_hn)):esc(g.event.shortName||g.event.name||'');var _row='<div class="grow"><div><div class="gname">'+esc(g.league)+' &middot; '+title+'</div><div class="gsub">'+esc(dayTime(g.event.date))+'</div></div><span class="when" data-until="'+esc(g.event.date||'')+'">'+esc(until(g.event.date))+'</span></div>';var _gr=RP_GAME_ROUTES[g.event.id];return _gr?('<a class="growtap" href="'+_gr+'" style="display:block;text-decoration:none;color:inherit">'+_row+'</a>'):_row;};
   var _paint=function(){if(!gb||!cur||(cur!==t&&cur.key!=='home'&&cur.key!=='trinity'&&cur.key!=='past'))return;var all=_acc.slice().sort(function(p,q){return Date.parse(p.event.date||0)-Date.parse(q.event.date||0);});gb.innerHTML=all.map(_rowH).join('')||(_pend?'<div class="empty">Loading upcoming events&hellip;</div>':'<div class="empty">No upcoming events listed right now.</div>');};
   HOME_GAMES_PAINT=_paint;
   _paint();
   _reqs.forEach(function(q){
    var x=q.x,_ctl=new AbortController();var _to=setTimeout(function(){_ctl.abort();},7000);
    fetch(q.u,{cache:'no-store',signal:_ctl.signal}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){(j.events||[]).forEach(function(e){if(_seenG[e.id])return;var st=(((e.competitions||[])[0]||{}).status||{}).type||{};if(st.state==='pre'&&Date.parse(e.date||0)>=Date.now()-3600000&&Date.parse(e.date||0)<Date.now()+259200000){_seenG[e.id]=1;_acc.push({league:x.label,event:e});}});}).catch(function(){}).finally(function(){_pend--;clearTimeout(_to);_paint();});
   });
   }
  }
 }else{
  if(SB[t.key]&&now-(SB_TS[t.key]||0)<60000){renderGames(t,SB[t.key]);}
  else{fetch('https://site.api.espn.com/apis/site/v2/sports/'+lg+'/scoreboard?limit=50',{cache:'no-store'}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){SB[t.key]=j.events||[];SB_TS[t.key]=Date.now();if(cur===t)renderGames(t,SB[t.key]);}).catch(function(){if(cur===t)renderGames(t,SB[t.key]||null);});}
 }

 if(NEWSF&&now-NEWSF_TS<30000){renderNews(t,newsBucket(t));tickRender();}
 else{
  rpFetchNews()
   .then(function(j){NEWSF=j;NEWSF_TS=Date.now();if(SOC_MATCH_OK&&!rpMapFresh(SOC_MATCH))SOC_MATCH_OK=false;socMapRetry();if(cur===t){renderNews(t,newsBucket(t));tickRender();}})
   .catch(function(){if(cur===t){renderNews(t,newsBucket(t));tickRender();}});
 }
 if(lg&&(!DNEWS_TS[t.key]||now-DNEWS_TS[t.key]>25000)){
  fetch('https://site.api.espn.com/apis/site/v2/sports/'+lg+'/news?limit=8',{cache:'no-store'})
   .then(function(r){if(!r.ok)throw 0;return r.json();})
   .then(function(j){DNEWS[t.key]=(j.articles||[]).map(function(a){return {headline:a.headline||'',link:((a.links||{}).web||{}).href||'',published:a.published||'',source:'ESPN'};}).filter(function(a){return rpNewsOk(t,a.headline)&&isPublishableNews(a);});DNEWS_TS[t.key]=Date.now();if(cur===t){renderNews(t,newsBucket(t));tickRender();}})
   .catch(function(){DNEWS_TS[t.key]=Date.now()-10000;});  /* soft backoff, keeps last good */
 }
}
setInterval(function(){if(cur&&!document.hidden)loadSide(cur);},30000);
/* owner 9:33 addendum: countdowns are ALWAYS live against current time - repaint every
   countdown span from its own timestamp between the 30s/5min data refetches. */
setInterval(function(){if(document.hidden)return;var n=document.querySelectorAll('[data-until]');for(var i=0;i<n.length;i++){n[i].textContent=until(n[i].getAttribute('data-until'));}},15000);
setInterval(function(){if(cur&&!document.hidden&&NEWSF){renderNews(cur,newsBucket(cur));tickRender();}},30000);
/* wordmark -> home (9/27 4:31 PT via main): tap logo from any tab lands home. Clear rp_tab + hash so boot's default-tab pick (home) wins and a later refresh stays home. */
var _wmlogo=document.querySelector('nav.rpnav .logo');
if(_wmlogo){_wmlogo.addEventListener('click',function(e){e.preventDefault();try{sessionStorage.removeItem('rp_tab');}catch(x){}try{history.replaceState(null,'',location.pathname);}catch(x){}location.href='index.html';});}
/* ---- boot ---- */
var _fc=feedCacheLoad();
if(_fc){CAR_LAST=_fc.items;CAR_ALL=_fc.all||[];PAIRS=_fc.pairs||[];if(PAIRS.length)CAR_UNIT={items:_fc.items,pairs:PAIRS.slice()};}
/* A new visit opens on Home. The tab is remembered only for this browser tab (sessionStorage), so the site's own reloads keep a visitor where they were, and a new visit - even from a link or a restored address ending in #trinity - never opens on Trinity's tab. The old every-visit memory is cleared. */
try{localStorage.removeItem('rp_tab');}catch(e){}
var _sesTab=(function(){try{return sessionStorage.getItem('rp_tab');}catch(e){return null;}})();
var start=fromHash();
if(start==='trinity'&&_sesTab!=='trinity')start=null;
if(!start)start=_sesTab;
if(!start&&TABS.some(function(t){return t.key==='home';}))start='home';
if(!start){
 for(var i=0;i<TABS.length;i++){var p=$('st-'+TABS[i].key);if(p&&p.querySelector('.pick:not(.rp-empty)')){start=TABS[i].key;break;}}
 if(!start&&TABS.length)start=TABS[0].key;
}
if(start)activate(start,true);
else document.body.classList.add('rp-ready');
if(!document.body.classList.contains('intro-on'))document.body.classList.add('rp-ready');
renderPred();setInterval(renderPred,900000);
/* Strict event-bound score navigation. Do not guess event IDs from a team name.
   The pick title and market links keep their original destinations. */
(function(){
 function linkFor(el){var row=el.closest('[data-espn][data-eid]');if(!row)return null;
  var lg=row.dataset.espn||'',id=row.dataset.eid||'';
  var g=row.querySelector('a[href^="game-"]');if(g)return g.getAttribute('href');
  var cid=row.dataset.comp||'';if(cid&&RP_GAME_ROUTES[cid])return RP_GAME_ROUTES[cid];  /* multi-fight cards: the fight's competition id owns the route */
  if(RP_GAME_ROUTES[id])return RP_GAME_ROUTES[id];
  if(!RP_LIVE_OK[lg]||!/^[0-9]+$/.test(id))return null;
  return 'live.html?espn='+encodeURIComponent(lg)+'&eid='+encodeURIComponent(id);
 }
 document.addEventListener('click',function(e){var score=e.target.closest('[data-ls]');if(!score)return;
  var dest=linkFor(score);if(!dest)return;
  e.preventDefault();e.stopPropagation();location.assign(dest);
 },true);
 document.addEventListener('keydown',function(e){if(e.key!=='Enter'&&e.key!==' ')return;
  var score=e.target.closest('[data-ls]');if(!score)return;var dest=linkFor(score);if(!dest)return;
  e.preventDefault();e.stopPropagation();location.assign(dest);
 },true);
 function tag(){document.querySelectorAll('[data-ls]').forEach(function(el){var dest=linkFor(el);if(!dest)return;
  el.setAttribute('role','link');el.setAttribute('tabindex','0');el.setAttribute('aria-label','Open this game live view');el.classList.add('rplivescore');
 });}
 tag();new MutationObserver(function(m){if(m.some(function(x){return x.addedNodes.length;}))tag();}).observe(document.body,{childList:true,subtree:true});
})();

})();

/* Wooder WNBA shared ticket: one record, two destinations; explicit ESPN event binding. */
(function(){
'use strict';
function boot(){
if(document.getElementById('rpWnbaShared'))return;
var nav=document.querySelector('nav.rpnav .tab');if(!nav)return;
var anchor=nav.cloneNode(false);anchor.href='#wnba';anchor.dataset.tab='wnba';anchor.textContent='WNBA';anchor.classList.remove('active');nav.parentNode.appendChild(anchor);
var tabs=window.RP_TABS||[];if(!tabs.some(function(t){return t.key==='wnba';}))tabs.push({key:'wnba',label:'WNBA',espn:'basketball/wnba'});
var host=document.getElementById('st-wooder');if(!host)return;
var state=document.createElement('div');state.id='st-wnba';state.className='state';host.after(state);
var module=document.createElement('div');module.id='rpWnbaShared';module.className='state';state.after(module);
var style=document.createElement('style');style.textContent='body.tab-wnba aside{display:none!important}body.tab-wooder #rpWnbaShared,body.tab-wnba #rpWnbaShared{display:block}#rpWnbaShared .rpwleg{margin:12px 0;font-size:13px}#rpWnbaShared .rpwprice,#rpWnbaShared .rpwnote{font-size:11px;color:#8a8f98;margin-top:3px}';document.head.appendChild(style);
function tab(){if(location.hash!=='#wnba')return;document.body.className=document.body.className.replace(/\btab-[a-z0-9]+\b/g,'').trim();document.body.classList.add('tab-wnba');document.querySelectorAll('nav.rpnav .tab').forEach(function(a){a.classList.toggle('active',a.dataset.tab==='wnba');});document.querySelectorAll('.state').forEach(function(s){s.classList.remove('on');});document.body.classList.remove('menu-open');}
anchor.addEventListener('click',function(e){e.preventDefault();location.hash='wnba';tab();});window.addEventListener('hashchange',tab);tab();
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function draw(j){var arr=(j.tickets||[]).filter(function(t){return t.sport==='wnba';});if(!arr.length){module.innerHTML='<div class="sub">No Wooder Ice WNBA tickets.</div>';return;}
module.innerHTML=arr.map(function(t){return '<div style="margin-top:18px;border:1px solid rgba(216,162,58,.45);border-radius:12px;padding:12px"><div class="sect">Wooder Ice WNBA</div><h3>Ticket '+esc(t.id)+' - '+esc(t.title)+'</h3><div class="rpwnote">'+esc(t.status)+'; receipt, stake and fill not independently verified. Wilson points are intended only, not a placed points claim.</div>'+t.legs.map(function(l,i){return '<div class="rpwleg">'+(i+1)+'. <b>'+esc(l.player)+'</b> '+esc(l.market)+'<div class="rpwnote">'+esc(l.matchup)+' - '+esc(l.time)+'</div><div class="rpwprice">'+esc(l.note||'Unpriced')+'</div><div class="rpwstat" data-eid="'+esc(l.event_id)+'" data-player="'+esc(l.player)+'" data-stat="'+esc(l.stat_key)+'" data-target="'+esc(l.target)+'" data-intended="'+(l.intended_only?'1':'0')+'">Scheduled</div></div>';}).join('')+'<div class="rpwnote">CASHED = stat threshold met, not a payout. No combined quote. Prices are single-leg reference snapshots, fees excluded.</div></div>';}).join('');tick();}
function norm(s){return String(s).toLowerCase().replace(/[^a-z0-9]/g,'');}
function stat(j,name,key){var result=null;((j.boxscore||{}).players||[]).forEach(function(team){(team.statistics||[]).forEach(function(group){var idx=(group.keys||[]).indexOf(key);if(idx<0)return;(group.athletes||[]).forEach(function(a){if(norm((a.athlete||{}).displayName)!==norm(name))return;var v=Number((a.stats||[])[idx]);if(Number.isFinite(v))result=v;});});});return result;}
function tick(){var rows=Array.from(module.querySelectorAll('.rpwstat')),ids=[...new Set(rows.map(function(r){return r.dataset.eid;}))];ids.forEach(function(id){if(!/^\d+$/.test(id))return;fetch('https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary?event='+id,{cache:'no-store'}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){var head=j.header||{};if(String(head.id)!==id)throw 0;var type=(((head.competitions||[])[0]||{}).status||{}).type||{};rows.filter(function(r){return r.dataset.eid===id;}).forEach(function(r){if(type.state==='pre'){r.textContent='Scheduled';return;}var v=stat(j,r.dataset.player,r.dataset.stat);if(v==null){r.textContent='Stats unavailable';return;}var label=r.dataset.stat==='points'?'pts':'reb';var intent=r.dataset.intended==='1'?'Intended selection only: ':'';r.textContent=intent+v+'/'+r.dataset.target+' '+label+(v>=Number(r.dataset.target)?' - CASHED (stat threshold)':'')+(type.state==='post'?' - Final':' - Live');});}).catch(function(){rows.filter(function(r){return r.dataset.eid===id;}).forEach(function(r){r.textContent='Stats unavailable';});});});}
fetch('slates/wooder_tickets.json?cb='+Date.now(),{cache:'no-store'}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(draw).catch(function(){module.textContent='WNBA tickets unavailable';});setInterval(function(){if(!document.hidden)tick();},60000);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
