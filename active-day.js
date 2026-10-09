/* PT active-view expiry. No settlement, archive, or source-data writes. */
(function(){
 'use strict';
 function day(ms){var p={};new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(ms==null?Date.now():ms)).forEach(function(x){p[x.type]=x.value;});return p.year+'-'+p.month+'-'+p.day;}
 function iso(v){var s=String(v||'');if(/^\d{4}-\d{2}-\d{2}$/.test(s))return s;if(/(Z|[+-]\d{2}:?\d{2})$/i.test(s)&&isFinite(Date.parse(s)))return day(Date.parse(s));return '';}
 function itemDay(t,j){var d=iso(t.date||t.game_date||t.slate_date||t.commence||t.kickoff);if(d)return d;var m=String(t.id||'').match(/(20\d{2})-?(\d{2})-?(\d{2})(?:\D|$)/);if(m)return m[1]+'-'+m[2]+'-'+m[3];d=iso(j.date||j.game_date||j.kickoff);if(d)return d;var ds=(t.legs||[]).map(function(l){return iso(l.date||l.game_date||l.commence);}).filter(Boolean).sort();if(ds.length)return ds[ds.length-1];return iso(j.generated_at);}
 function fresh(t,j){if(!t||t.status==='expired')return false;if(t.futures===true||t.season_long===true)return true;var d=itemDay(t,j);return !!d&&d>=day();}
 var specs={'wooder_tickets.json':'tickets','wooder_combos.json':'combos','wooder_batch.json':'cards','nfl_ideas.json':'cards','wooder_first_td.json':'picks','wooder_dingers.json':'picks','nfl_night_sgp.json':'legs'};
 function filter(name,j){if(!j||typeof j!=='object')return j;var key=specs[name];if(key&&Array.isArray(j[key]))j[key]=j[key].filter(function(t){return fresh(t,j);});if(name==='nfl_night.json'||name==='nfl_latest.json'){if(!fresh(j,j)){j.dk={};j.kalshi={};j.sgp_idea=null;}}return j;}
 var nativeFetch=window.fetch.bind(window);
 window.fetch=function(input,opts){var u=String(typeof input==='string'?input:input.url||''),m=u.match(/(?:^|\/)slates\/([^/?]+)(?:\?|$)/);if(!m||!(specs[m[1]]||/^(nfl_night|nfl_latest)\.json$/.test(m[1])))return nativeFetch(input,opts);var name=m[1];return nativeFetch(input,opts).then(function(r){if(!r.ok)return r;var copy=r.clone();return copy.json().then(function(j){return new Response(JSON.stringify(filter(name,j)),{status:r.status,statusText:r.statusText,headers:r.headers});}).catch(function(){return r;});});};
 var opened=day();
 function boundary(now){var lo=now,hi=now+27*3600000,today=day(now);while(hi-lo>1){var mid=Math.floor((lo+hi)/2);if(day(mid)===today)lo=mid;else hi=mid;}return hi;}
 function check(){if(day()===opened)return;/* Hide old active views before navigation, including offline resumes. */document.querySelectorAll('#st-home,#st-wooder,#st-ding,[data-home-league]').forEach(function(el){el.style.display='none';});var u=new URL(location.href);u.searchParams.set('dayroll',day());location.replace(u.href);}
 setTimeout(check,Math.max(1,boundary(Date.now())-Date.now()));document.addEventListener('visibilitychange',function(){if(!document.hidden)check();});window.addEventListener('focus',check);window.addEventListener('pageshow',check);
 /* Only the official date-bound schedule can establish an offday. Failure hides stale picks silently. */
 function offday(){var d=day();nativeFetch('https://statsapi.mlb.com/api/v1/schedule?sportId=1&date='+d,{cache:'no-store'}).then(function(r){if(!r.ok)throw 0;return r.json();}).then(function(j){if(day()!==d||j.totalGames!==0||!Array.isArray(j.dates)||j.dates.length!==0)return;var box=document.getElementById('rpDing');if(!box)return;box.innerHTML='<div style="font-size:13px;color:#8a8f98;padding:6px 0">No MLB games today</div>';box.parentNode.parentNode.style.display='';}).catch(function(){});}
 if(document.readyState==='complete')offday();else window.addEventListener('load',offday);
 window.rpActiveDay={day:day,itemDay:itemDay,fresh:fresh,filter:filter,boundary:boundary,check:check};
})();
