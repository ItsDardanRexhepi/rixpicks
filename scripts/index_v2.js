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
  var _row='<div class="grow"><div><div class="gname">'+txt+'</div><div class="gsub">'+sub+'</div></div>'+when+'</div>';
  rows.push((ev.id&&RP_LIVE_OK[lgpath(t)])?('<a class="growtap" href="live.html?espn='+encodeURIComponent(lgpath(t))+'&eid='+encodeURIComponent(ev.id)+'" style="display:block;text-decoration:none;color:inherit">'+_row+'</a>'):_row);
 }
 box.innerHTML=rows.join('')||'<div class="empty">No games listed right now.</div>';
}
function srcDom(s){return s==='CBS'?'cbssports.com':(s==='YAHOO'?'sports.yahoo.com':'espn.com');}
function unesc(s){var t=document.createElement('textarea');t.innerHTML=String(s==null?'':s);return t.value;}  /* swamp 1:09: feeds ship HTML-encoded headlines (Jets&#39;) - decode before esc() or they double-escape */
function normH(h){return String(h||'').toLowerCase().replace(/[^a-z0-9]+/g,' ').replace(/^\s+|\s+$/g,'');}
function newsBucket(t){
 /* instant lane (Dardan 1:13: no lag on news dropping): the visible league's bucket merges
    the 5-min server file with a direct 25s ESPN poll from the page - new ESPN stories render
    within ~30s of publish; CBS/Yahoo lanes arrive on the server cadence. */
 var out=[];
 if(NEWSF&&NEWSF.leagues){
  var L=NEWSF.leagues;
  if(t.key==='tennis'){out=(L['tennis/atp']||[]).concat(L['tennis/wta']||[]);}
  else if(t.key==='ufcboxing'){out=(L['mma/ufc']||[]).concat(L['boxing']||[]);}
  else out=L[t.espn]||[];
  out=out.slice();
 }
 out=out.concat(DNEWS[t.key]||[]);
 out.sort(function(a,b){return Date.parse(b.published||0)-Date.parse(a.published||0);});
 var seen={},ded=[];
 out.forEach(function(a){var n=normH(a.headline);if(!n||seen[n])return;seen[n]=1;ded.push(a);});
 return ded;
}
function renderNews(t,arts){
 var box=$('rpNews');if(!box)return;
 if(!arts||!arts.length){box.innerHTML='<div class="empty">News unavailable right now.</div>';return;}
 var h='';
 arts.slice(0,8).forEach(function(a){
  var u=a.link||'';
  var s=a.source||'ESPN';
  var inner='<span class="src '+s.toLowerCase()+'">'+esc(s)+'</span><span class="ntxt">'+esc(unesc(a.headline||''))+'</span><div class="nts">'+esc(ago(a.published))+' \u00b7 '+srcDom(s)+'</div>';
  h+='<div class="nitem">'+(u?'<a href="'+esc(u)+'" target="_blank" rel="noreferrer">'+inner+'</a>':inner)+'</div>';
 });
 box.innerHTML=h;
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
var NEWSF=null,NEWSF_TS=0;
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
function tickRender(){
 var tr=$('rpTickTrack'),bar=$('rpTickBar');if(!tr||!bar)return;
 var arts=(NEWSF&&NEWSF.latest)||[];
 kalItemsFor(cur,function(kal){
  if(!arts.length&&!kal.length){bar.style.display='none';return;}
  bar.style.display='';
  var h='';
  arts.slice(0,8).forEach(function(a){
   var u=a.link||'';
   var s=a.source||'ESPN';
   h+='<'+(u?'a class="titem" href="'+esc(u)+'" target="_blank" rel="noreferrer"':'span class="titem"')+'><span class="tsrc '+s.toLowerCase()+'">'+esc(s)+'</span><span class="tsrc">'+esc(a.league||'')+'</span>'+esc(unesc(a.headline||''))+'</'+(u?'a':'span')+'><span class="tsep">\u00b7</span>';
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
 if(NEWSF&&now-NEWSF_TS<30000){renderNews(t,newsBucket(t));tickRender();}
 else{
  fetch('slates/news.json', {cache:'no-store'})
   .then(function(r){if(!r.ok)throw 0;return r.json();})
   .then(function(j){NEWSF=j;NEWSF_TS=Date.now();if(cur===t){renderNews(t,newsBucket(t));tickRender();}})
   .catch(function(){if(cur===t){renderNews(t,newsBucket(t));tickRender();}});
 }
 if(!DNEWS_TS[t.key]||now-DNEWS_TS[t.key]>25000){
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
if(!start){
 for(var i=0;i<TABS.length;i++){var p=$('st-'+TABS[i].key);if(p&&p.querySelector('.pick:not(.rp-empty)')){start=TABS[i].key;break;}}
 if(!start&&TABS.length)start=TABS[0].key;
}
if(start)activate(start,true);
else document.body.classList.add('rp-ready');
if(!document.body.classList.contains('intro-on'))document.body.classList.add('rp-ready');
})();
