// news lane - faithful Worker port of scripts/news_feed.py (multi-source aggregator).
// Same lanes, same guards, same output shape: news.json / news_images.json / img_check.json.
// Fail-closed everywhere: a dead lane never blocks the file; blank beats wrong.
import { parseFeed, isoDate } from '../lib/xml.js';

const UA = { 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) RixPicks/1.0' };
const ESPN_RSS = { NFL:'nfl', NBA:'nba', MLB:'mlb', NHL:'nhl', CFB:'ncf', NCAAB:'ncb', WNBA:'wnba', PGA:'golf', NASCAR:'racing', UFC:'mma', Boxing:'boxing' };
const CBS_RSS  = { NFL:'nfl', NBA:'nba', MLB:'mlb', NHL:'nhl', CFB:'college-football', NCAAB:'college-basketball', WNBA:'wnba', PGA:'golf', UFC:'mma', Boxing:'boxing' };
const YAHOO_RSS= { NFL:'nfl', NBA:'nba', MLB:'mlb', NHL:'nhl', CFB:'college-football', NCAAB:'college-basketball', WNBA:'wnba', PGA:'golf', NASCAR:'nascar', UFC:'mma', Boxing:'boxing' };

const LEAGUE_KEYWORDS = {
 NFL:['nfl','football','super bowl','quarterback','touchdown'], NBA:['nba','basketball'],
 MLB:['mlb','baseball','world series','pitcher','home run'], NHL:['nhl','hockey','stanley cup'],
 CFB:['college football','ncaa football','cfb','quarterback','touchdown','heisman'],
 NCAAB:['college basketball','ncaa','march madness','basketball'], WNBA:['wnba','basketball'],
 MLS:['mls','soccer','major league soccer'], NWSL:['nwsl','soccer'],
 PGA:['golf','pga','masters','ryder','open championship','tour championship','birdie','eagle'],
 ATP:['tennis','atp','grand slam','wimbledon','us open','australian open','french open'],
 WTA:['tennis','wta','grand slam','wimbledon','us open','australian open','french open'],
 NASCAR:['nascar','racing','daytona','cup series'], UFC:['ufc'], Boxing:['boxing','heavyweight','title bout'] };
const STRONG_MARKERS = {
 NFL:['nfl','super bowl','quarterback','touchdown'], NBA:['nba'], MLB:['mlb','world series','home run'],
 NHL:['nhl','stanley cup'], WNBA:['wnba'] };
const SPORT_OF = { NFL:'NFL', CFB:'NFL', NBA:'NBA', NCAAB:'NBA', WNBA:'WNBA', MLB:'MLB', NHL:'NHL' };
const NICHE = ['MLS','NWSL','PGA','ATP','WTA','NASCAR','UFC','Boxing'];
const PROMO_NEWS = /promo code|bonus bets?|free bets?|bet \$?[0-9]+.{0,25}(get|claim)|claim \$?[0-9]+|deposit (bonus|match|offer)|sign ?up (offer|bonus|promo)|new (user|customer)s? (offer|bonus|promo)|sponsored content/i;

const norm = h => (h || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
const tsOf = a => { const t = Date.parse(a.published || ''); return isNaN(t) ? 0 : t / 1000; };

async function getText(url, timeoutMs = 12000, headers = UA) {
  const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), timeoutMs);
  try { const r = await fetch(url, { headers, signal: ctl.signal, redirect: 'follow' }); if (!r.ok) throw new Error('http ' + r.status); return await r.text(); }
  finally { clearTimeout(t); }
}

async function espnApi(path) {
  try {
    const j = JSON.parse(await getText(`https://site.api.espn.com/apis/site/v2/sports/${path}/news?limit=10`));
    return (j.articles || []).map(a => ({ headline: a.headline || '', link: ((a.links || {}).web || {}).href || '',
      published: a.published || '', source: 'ESPN', image: (a.images && a.images[0] && a.images[0].url) || '', blurb: a.description || '' }));
  } catch (e) { console.error('lane espn-api', path, String(e).slice(0, 80)); return []; }
}
async function rss(url, source) {
  try {
    const xml = await getText(url);
    return parseFeed(xml).map(it => ({ ...it, published: isoDate(it.published), source }));
  } catch (e) { console.error('lane rss', url, String(e).slice(0, 80)); return []; }
}

function relevant(key, headline) {
  const h = ' ' + (headline || '').toLowerCase() + ' ';
  const mySport = SPORT_OF[key];
  for (const [sport, marks] of Object.entries(STRONG_MARKERS)) {
    if (sport === mySport) continue;
    if (marks.some(m => h.includes(m))) return false;
  }
  if (NICHE.includes(key)) {
    const kws = LEAGUE_KEYWORDS[key] || [];
    const cut = Math.max(20, Math.floor(h.length * 0.6));
    return kws.some(k => h.slice(0, cut).includes(k));
  }
  return true;
}
const publishable = a => !PROMO_NEWS.test([a.headline, a.summary, a.blurb, a.link, a.source].map(x => x || '').join(' ').normalize('NFKC'));

function optImage(u) {
  if (!u || typeof u !== 'string' || !u.startsWith('https://')) return '';
  if (u.includes('images.weserv.nl/') || u.includes('s.yimg.com/')) return u;
  return 'https://images.weserv.nl/?url=' + encodeURIComponent(u.slice(8)) + '&w=1200&h=675&fit=cover&q=78&output=webp';
}

const OG_RE = [
  /<meta[^>]+(?:property|name)=["'](?:og:image|twitter:image)["'][^>]+content=["']([^"']+)["']/i,
  /<meta[^>]+content=["']([^"']+)["'][^>]+(?:property|name)=["'](?:og:image|twitter:image)["']/i ];

async function enrichImages(latest, cache) {
  let fresh = 0;
  for (const a of latest) {
    if (a.image) continue;
    const link = a.link || '';
    if (!link) continue;
    if (link in cache) { a.image = cache[link]; continue; }
    if (fresh >= 12) continue;
    fresh++;
    let img = '';
    try {
      const html = (await getText(link, 6000)).slice(0, 200000);
      const m = OG_RE[0].exec(html) || OG_RE[1].exec(html);
      if (m && m[1].startsWith('http')) img = m[1];
    } catch (e) { console.error('og:image', link.slice(0, 60), String(e).slice(0, 60)); }
    cache[link] = img; a.image = img;
  }
  const keys = Object.keys(cache);
  if (keys.length > 300) for (const k of keys.slice(0, keys.length - 300)) delete cache[k];
}

const IMG_UA = { 'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1',
  'Accept': 'image/webp,image/avif,image/*,*/*;q=0.8' };

async function validateImages(arts) {
  const cand = arts.filter(a => a.image);
  const dead = [];
  async function check(a) {
    const u = a.image;
    for (let i = 0; i < 2; i++) {
      try {
        const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 6000);
        let r = await fetch(u, { method: 'HEAD', headers: IMG_UA, signal: ctl.signal });
        clearTimeout(t);
        if (r.status === 200 && (r.headers.get('content-type') || '').includes('image')) return;
      } catch (e) {}
      try {
        const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 6000);
        let r = await fetch(u, { headers: { ...IMG_UA, Range: 'bytes=0-1023' }, signal: ctl.signal });
        clearTimeout(t);
        if (r.status === 200 || r.status === 206) return;
      } catch (e) {}
    }
    dead.push({ headline: (a.headline || '').slice(0, 80), url: u.slice(0, 200) });
    a.image = '';
  }
  // 8-way concurrency, mirroring the python ThreadPoolExecutor
  for (let i = 0; i < cand.length; i += 8) await Promise.all(cand.slice(i, i + 8).map(check));
  return { ts: new Date().toISOString(), checked: cand.length, dead_stripped: dead.length, dead };
}

async function loadConfig(env) {
  try {
    const obj = await env.FEEDS.get('config/leagues.json');
    if (obj) return JSON.parse(await obj.text());
  } catch (e) {}
  const j = JSON.parse(await getText(env.PROD_BASE + '/config_leagues.json?cb=' + Date.now()));
  return j;
}

export async function runNews(env) {
  const cfg = await loadConfig(env);
  const leagues = {}; let latest = [];
  for (const [key, v] of Object.entries(cfg.leagues)) {
    const path = v.espn; const jkey = path || key.toLowerCase();
    let items = [];
    if (path) items = items.concat(await espnApi(path));
    if (ESPN_RSS[key]) items = items.concat(await rss(`https://www.espn.com/espn/rss/${ESPN_RSS[key]}/news`, 'ESPN'));
    if (CBS_RSS[key]) items = items.concat(await rss(`https://www.cbssports.com/rss/headlines/${CBS_RSS[key]}/`, 'CBS'));
    if (YAHOO_RSS[key]) items = items.concat(await rss(`https://sports.yahoo.com/${YAHOO_RSS[key]}/rss.xml`, 'YAHOO'));
    const seen = new Set(); const ded = [];
    for (const a of items.sort((x, y) => tsOf(y) - tsOf(x))) {
      const n = norm(a.headline);
      if (!n || seen.has(n)) continue;
      if (!relevant(key, a.headline)) continue;
      if (!publishable(a)) continue;
      seen.add(n); a.league = key; ded.push(a);
    }
    const bySrc = {};
    for (const a of ded) (bySrc[a.source] = bySrc[a.source] || []).push(a);
    const mixed = []; let i = 0;
    while (mixed.length < 10 && Object.keys(bySrc).length) {
      for (const src of Object.keys(bySrc)) {
        const lst = bySrc[src];
        if (i < lst.length) mixed.push(lst[i]); else delete bySrc[src];
      }
      i++;
    }
    leagues[jkey] = mixed.slice(0, 10);
    latest = latest.concat(mixed.slice(0, 6));
  }
  latest.sort((a, b) => tsOf(b) - tsOf(a));
  latest = latest.slice(0, 40);

  let cache = {};
  try { const o = await env.FEEDS.get('slates/news_images.json'); if (o) cache = JSON.parse(await o.text()); } catch (e) {}
  await enrichImages(latest, cache);

  const seenArt = new Set(); const arts = [];
  for (const lst of [...Object.values(leagues), latest]) for (const a of lst) {
    if (seenArt.has(a)) continue; seenArt.add(a);
    a.image = optImage(a.image || ''); arts.push(a);
  }
  const imgCheck = await validateImages(arts);

  const out = { generated_at: new Date().toISOString(), leagues, latest };
  const put = (k, v) => env.FEEDS.put(k, JSON.stringify(v, null, 1), { httpMetadata: { contentType: 'application/json' } });
  await Promise.all([put('slates/news.json', out), put('slates/news_images.json', cache), put('slates/img_check.json', imgCheck)]);
  return { generated_at: out.generated_at, buckets: Object.keys(leagues).length, latest: latest.length };
}
