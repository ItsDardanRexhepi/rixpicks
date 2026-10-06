#!/usr/bin/env node
'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync(__dirname+'/index_v2.js','utf8');
function fn(name){const a=src.indexOf('function '+name+'(');assert(a>=0,name);let d=0;for(let i=src.indexOf('{',a);i<src.length;i++){if(src[i]==='{')d++;else if(src[i]==='}'&&!--d)return src.slice(a,i+1);}throw Error(name);}
const NOW=Date.now(),iso=n=>new Date(NOW+n).toISOString();
const payload=g=>({generated_at:g,latest:[{headline:'NHL news',published:iso(-60000)}],leagues:{NHL:[]}});
(async()=>{
 let seen=[],live=payload(iso(-5000)),staticNews=payload(iso(-3600000)),failLive=false,badLive=false;
 const ctx=vm.createContext({Date,Number,String,Array,Object,Promise,isFinite,AbortController,setTimeout,clearTimeout,
 RP_BUILD:1,localStorage:{getItem:()=>JSON.stringify({v:1,items:[{headline:'News',published:iso(-5000)}],all:[{headline:'News',published:iso(-5000)}],pairs:[]})},isPublishablePost:()=>true,carKey:a=>a.link||a.headline,NEWSF:null,RP_FUTURE_SKEW:300000,RP_PROMO_NEWS:/promo code/i,
 fetch:async u=>{seen.push(u);if(u.includes('workers.dev')){if(failLive)throw Error('down');return {ok:true,json:async()=>badLive?{latest:[]}:live};}return {ok:true,json:async()=>staticNews};}});
 vm.runInContext(['rpNewsPayload','rpFeedJson','rpFetchNews','rpPredItems','isPublishableNews','feedCacheLoad'].map(fn).join('\n'),ctx);
 assert.equal((await ctx.rpFetchNews()).generated_at,live.generated_at);assert.equal(seen.length,1);
 console.log('PASS live worker wins without waiting for stale bridge');
 failLive=true;seen=[];assert.equal((await ctx.rpFetchNews()).generated_at,staticNews.generated_at);assert.equal(seen.length,2);
 console.log('PASS failed worker uses validated static fallback');
 failLive=false;badLive=true;assert.equal((await ctx.rpFetchNews()).generated_at,staticNews.generated_at);
 console.log('PASS malformed live payload uses fallback');
 ctx.NEWSF=live;failLive=true;assert.equal((await ctx.rpFetchNews()).generated_at,live.generated_at);
 console.log('PASS fallback never replaces newer last-good news');
 const cache=ctx.feedCacheLoad();assert(cache&&cache.items.length===1&&cache.pairs.length===0);
 console.log('PASS independent last-good news survives a zero-social reload without badges');
 assert(!ctx.rpNewsPayload({generated_at:'bad',latest:[],leagues:{}}));assert(!ctx.rpNewsPayload({generated_at:iso(0),latest:{},leagues:{}}));
 assert(!ctx.isPublishableNews({headline:'Future NHL',published:iso(3600000)}));assert(ctx.isPublishableNews({headline:'NHL',published:iso(-5000)}));assert(!ctx.isPublishableNews({headline:'promo code'}));
 console.log('PASS malformed and future-clock stories cannot claim latest');
 const forecasts=[{prediction:'future',kickoff_utc:iso(3600000)},{prediction:'past',kickoff_utc:iso(-1)},{prediction:'missing'},{prediction:'expired',kickoff_utc:iso(60000),status:'expired'}];
 assert.deepEqual(JSON.parse(JSON.stringify(ctx.rpPredItems({items:forecasts}))).map(p=>p.prediction),['future']);
 console.log('PASS prediction feed hides past, expired and unknown-start forecasts');
 assert(src.includes('socSync();tickRender();renderPred();}'));assert(src.includes("var arts=newsBucket({key:'home'});"));assert(src.includes("tr.style.animation=TICK_V>0?"));
 console.log('PASS coordinated updates repaint ticker and reduced motion stays stopped');
})().catch(e=>{console.error(e);process.exit(1);});
