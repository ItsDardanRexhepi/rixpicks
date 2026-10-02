/* Today on the record page: public, same-origin card and ledger only.
 * No browser-side result inference from scores. An optional pipeline-emitted
 * today_record.json may enrich verdict/CLV/note, but only for the same date and
 * locked card identity; history.json's chain-written row is the verdict fallback.
 * An absent today_record.json (404) is not asked for again for 10 minutes.
 * record.html lists every graded day statically; the block for the date painted here
 * is hidden while this section shows its picks and every graded row of that day, so no
 * day is shown twice or dropped. A pick with no event id (MMA) is keyed by league + name.
 */
(function(){'use strict';
var mount=document.getElementById('rpToday');if(!mount)return;
var lastDate='',active=false;
function pt(){return new Intl.DateTimeFormat('en-CA',{timeZone:'America/Los_Angeles',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());}
function text(v){return v==null?'':String(v);}
function child(parent,tag,cls,value){var e=document.createElement(tag);if(cls)e.className=cls;if(value!=null)e.textContent=text(value);parent.appendChild(e);return e;}
function odds(p){var n=Number(p.card_american);return Number.isFinite(n)&&n!==0?n:(/^[+-]\d+$/.test(text(p.odds))?Number(p.odds):null);}
function stake(p){var n=Number.parseFloat(text(p.units));return Number.isFinite(n)&&n>0?n:null;}
function fmt(n){return (n>=0?'+':'')+n.toFixed(2)+'u';}
/* A pick with no event id (MMA before K19) is keyed by league + name. */
function key(p){var g=p.game||{};if(!g.eid)return ['noeid',text(p.espn_league),p.name||''].join('|');return [g.eid||'',p.market||'ml',p.side||'',p.line||'',p.player||'',p.name||''].join('|');}
function result(x){var r=text(x&&x.result).toUpperCase();return ({W:'W',WON:'W',L:'L',LOST:'L',P:'P',PUSH:'P'})[r]||'';}
function safeJson(url){return fetch(url+'?cb='+Date.now(),{cache:'no-store'}).then(function(r){return r.ok?r.json():null;}).catch(function(){return null;});}
var liveRetryAt=0;
function liveJson(){if(Date.now()<liveRetryAt)return Promise.resolve(null);return fetch('today_record.json?cb='+Date.now(),{cache:'no-store'}).then(function(r){if(r.status===404){liveRetryAt=Date.now()+600000;return null;}return r.ok?r.json():null;}).catch(function(){return null;});}
function shadow(date){[].forEach.call(document.querySelectorAll('.rpday[data-date]'),function(b){b.hidden=!!date&&b.getAttribute('data-date')===date;});}
function paint(date,picks,graded,extra,complete){
 var frag=document.createDocumentFragment(),w=0,l=0,u=0,exact=true,settled=0,lastLeague='';
 var h=child(frag,'div','dayhead');child(h,'span','d','Today · '+new Intl.DateTimeFormat('en-US',{timeZone:'UTC',weekday:'long',month:'short',day:'numeric'}).format(new Date(date+'T12:00:00Z')));
 var rh=child(h,'span','r','0-0');var uh=child(h,'span','u','0.00u');
 if(!picks.length){child(frag,'div','nt','No carded picks today.');mount.replaceChildren(frag);shadow('');return;}
 picks.forEach(function(p){
   var lg=p.league||text(p.espn_league).split('/').pop().toUpperCase()||'Picks';if(lg!==lastLeague){var sect=child(frag,'div','dayhead');sect.style.marginTop='16px';child(sect,'span','d',lg);lastLeague=lg;}
   var k=key(p),x=graded[k]||extra[k]||null,r=result(x);var s=stake(p),a=odds(p);
   /* A chain-written history verdict wins if optional state disagrees. */
   if(graded[k]&&result(graded[k])){x=graded[k];r=result(x);}
   if(r==='W')w++;if(r==='L')l++;
   if(r){settled++;var d=Number(x.delta_units_exact!=null?x.delta_units_exact:x._delta);if(Number.isFinite(d)){u+=d;}else if(r==='P'){}else if(s!=null&&a!=null){u+=r==='L'?-s:s*(a>0?a/100:100/Math.abs(a));}else exact=false;}
   var box=child(frag,'div','pk'),top=child(box,'div','pk-top'),badge=child(top,'span','res '+(r||'pending'),r||'·');badge.setAttribute('aria-label',r||'Pending');
   child(top,'span','nm',p.name||'Pick');child(top,'span','un',p.units||'');child(top,'span','od',a!=null?(a>0?'+':'')+a:(p.odds||''));
   var g=p.game||{};child(box,'div','gm',(p.league||text(p.espn_league).split('/').pop().toUpperCase()||'Pick')+(g.home||g.away?' · '+(p.side==='away'?'at '+g.home:p.side==='home'?'vs '+g.away:[g.away,g.home].filter(Boolean).join(' vs ')):'') );
   if(x&&x.score)child(box,'div','sc',x.score);
   if(r){var note='';if(x&&x.note)note=text(x.note);else if(r==='P')note='Push · 0.00u at the published card price.';else if(s!=null&&a!=null)note=fmt(r==='L'?-s:s*(a>0?a/100:100/Math.abs(a)))+' on '+p.units+' at the '+(a>0?'+':'')+a+' published card price.';else note='Result posted; units pending verified card price.';
    child(box,'div','nt',note);if(x&&x.learning)child(box,'div','nt',text(x.learning));
    if(x&&x.close!=null&&x.clv!=null&&Number.isFinite(Number(x.clv))){var c=Number(x.clv),cl=child(box,'div','clv','close '+x.close+' · CLV '+(c>=0?'+':'')+c.toFixed(1)+'% · '+(c>.05?'beat the close':c<-.05?'gave back vs the close':'matched the close'));cl.style.cssText='font-size:12px;color:#8a8f98;margin-top:4px';}
   }else child(box,'div','nt','Pending · units settle at the published card price.');
 });
 rh.textContent=w+'-'+l+(settled<picks.length?' · '+(picks.length-settled)+' pending':'');uh.textContent=exact?fmt(u):'Units pending';
 /* The static block for this day is hidden only while Today paints every graded row of it. */
 mount.replaceChildren(frag);shadow(complete?date:'');
}
function hydrate(){if(active)return;active=true;var day=pt();Promise.all([safeJson('manifest.json'),safeJson('history.json'),liveJson()]).then(function(all){
 var m=all[0],hist=all[1],live=all[2];if(!m||!Array.isArray(m.picks)||m.date!==day){
   /* At midnight never show yesterday's picks as today's; retain the previous
      card only until local date flips. Unavailable sources never erase a good view. */
   if(day!==lastDate){mount.replaceChildren();child(mount,'div','dayhead').appendChild(Object.assign(document.createElement('span'),{className:'d',textContent:'Today'}));child(mount,'div','nt','Today’s card has not published yet.');shadow('');lastDate=day;}return;
 }
 var picks=m.picks.filter(function(p){return p&&typeof p==='object'&&p.name&&p.game&&(p.game.eid||p.espn_league);});
 /* Reject duplicate identities, rather than silently attaching one result twice. */
 var seen=new Set();picks=picks.filter(function(p){var k=key(p);if(seen.has(k))return false;seen.add(k);return true;});
 var historyRow=hist&&Array.isArray(hist.days)&&hist.days.find(function(d){return d.date===day;});
 var graded={},extra={},complete=true;
 if(historyRow&&Array.isArray(historyRow.picks)){
   /* Legacy history has no event ID. Only unique card names can safely match. */
   var counts={},histCounts={};picks.forEach(function(p){counts[p.name]=(counts[p.name]||0)+1;});historyRow.picks.forEach(function(x){histCounts[x.name]=(histCounts[x.name]||0)+1;});
   historyRow.picks.forEach(function(x){var p=picks.find(function(q){return q.name===x.name&&counts[q.name]===1&&histCounts[x.name]===1;});if(p&&result(x))graded[key(p)]=x;else if(result(x))complete=false;});
 }
 if(live&&live.date===day&&Array.isArray(live.picks))live.picks.forEach(function(x){if(x&&seen.has(x.pick_key))extra[x.pick_key]=x;});
 paint(day,picks,graded,extra,complete);lastDate=day;
 }).finally(function(){active=false;});}
hydrate();setInterval(hydrate,15000);document.addEventListener('visibilitychange',function(){if(!document.hidden)hydrate();});
})();
