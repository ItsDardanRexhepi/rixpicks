// official-video lane - Worker port of scripts/official_video.py (official-video workflow,
// every 15 min). FREE sources: channel-page identity resolve -> RSS -> oEmbed embeddability
// (optional YT_API_KEY secret upgrades to the authoritative videos.list status check).
// Live games come from this worker's own live-games lane (R2), prod as fallback.
// Fail-closed: only validated entries tied to current/upcoming games.
// Shadow: writes R2 slates/official_video.json only.
import { getJson, prodJson, r2Json, putJson, sleep } from '../lib/util.js';

const GAME_WINDOW_H = 36;
const UA = { 'User-Agent': 'rixpicks-official-video/1.0' };

// stream-vs-clip gate (fail-closed): title must assert live/full-game AND carry no clip marker
const NEG = ['highlight', 'recap', 'best plays', 'top plays', 'condensed', "mic'd", 'micd',
  'every play', 'best of', 'week in review', 'preview', 'prediction', 'reaction'];
const POS = ['live', 'full game', 'full match', 'watch along', 'watchalong', 'game day live', 'gameday live'];
const isStreamTitle = title => {
  const t = String(title).toLowerCase();
  if (NEG.some(n => t.includes(n))) return false;
  return POS.some(p => t.includes(p));
};
const nrm = s => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '');

async function getText(url) {
  const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 20000);
  try {
    const r = await fetch(url, { headers: UA, signal: ctl.signal });
    return { status: r.status, body: await r.text() };
  } finally { clearTimeout(t); }
}

async function resolveChannelId(handle) {
  try {
    const { body } = await getText(`https://www.youtube.com/@${handle}`);
    const m = body.match(/"externalId":"(UC[^"]+)"/) || body.match(/channel_id=(UC[^"&]+)/);
    const title = body.match(/<title>([^<]+)<\/title>/);
    return [m ? m[1] : null, title ? title[1].trim() : ''];
  } catch (e) { console.error(`official_video resolve FAIL @${handle}: ${String(e).slice(0, 60)}`); return [null, '']; }
}

async function channelUploads(cid) {
  try {
    const { body } = await getText(`https://www.youtube.com/feeds/videos.xml?channel_id=${cid}`);
    const chTitle = (body.match(/<title>([^<]*)<\/title>/) || [])[1] || '';
    const out = [];
    for (const entry of body.split('<entry>').slice(1)) {
      const vid = (entry.match(/<yt:videoId>([^<]+)<\/yt:videoId>/) || [])[1];
      const title = (entry.match(/<title>([^<]*)<\/title>/) || [])[1];
      const published = (entry.match(/<published>([^<]+)<\/published>/) || [])[1];
      if (vid && title) out.push({ video_id: vid, title, published, channel_title: chTitle });
    }
    return out;
  } catch (e) { console.error(`official_video rss FAIL ${cid}: ${String(e).slice(0, 60)}`); return []; }
}

async function oembedOk(vid) {
  try {
    const u = 'https://www.youtube.com/oembed?url=' + encodeURIComponent(`https://www.youtube.com/watch?v=${vid}`) + '&format=json';
    const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 15000);
    try { const r = await fetch(u, { headers: UA, signal: ctl.signal }); return r.status === 200; }
    finally { clearTimeout(t); }
  } catch (e) { return false; }
}

async function apiEmbeddable(env, vids) {
  if (!env.YT_API_KEY || !vids.length) return null;
  try {
    const d = await getJson('https://www.googleapis.com/youtube/v3/videos?part=status&id=' + vids.slice(0, 50).join(',') + '&key=' + env.YT_API_KEY);
    const out = {};
    for (const it of d.items || []) out[it.id] = !!(it.status && it.status.embeddable);
    return out;
  } catch (e) { console.error(`official_video yt api FAIL: ${String(e).slice(0, 60)}`); return null; }
}

export async function runOfficialVideo(env) {
  const now = new Date();
  const games = [];
  try {
    const lg = (await r2Json(env, 'slates/live_games.json')) || (await prodJson(env, '/slates/live_games.json'));
    for (const league of lg.leagues || []) {
      for (const g of league.games || []) {
        const ct = Date.parse(String(g.commence || '').replace('Z', '+00:00'));
        if (isNaN(ct)) continue;
        if (Math.abs(ct - now.getTime()) > GAME_WINDOW_H * 3600000 || !['pre', 'in'].includes(g.status)) continue;
        const sides = String(g.matchup || '').split(' @ ').map(p => p.trim()).filter(Boolean);
        if (sides.length === 2) games.push({ event_id: g.espn_event_id, league: league.league,
          matchup: g.matchup, sides, commence: g.commence });
      }
    }
  } catch (e) { console.error(`official_video live_games unreadable: ${String(e).slice(0, 60)}`); }
  let chanCfg = [];
  try { chanCfg = (await prodJson(env, '/slates/official_video_channels.json')).channels || []; }
  catch (e) { console.error('official_video channels unreadable - fail closed, empty feed'); }
  const candidates = [];
  for (const ch of chanCfg) {
    const [cid, ctitle] = await resolveChannelId(ch.handle || '');
    if (!cid) continue;
    for (const v of (await channelUploads(cid)).slice(0, 10)) {
      candidates.push({ ...v, channel_id: cid, handle: ch.handle, leagues: ch.leagues || [],
        channel_title: v.channel_title || ctitle });
    }
    await sleep(150);
  }
  const flags = await apiEmbeddable(env, candidates.map(v => v.video_id));
  const items = [];
  for (const v of candidates) {
    const t = nrm(v.title);
    for (const g of games) {
      if (!v.leagues.includes(g.league)) continue;
      if (!isStreamTitle(v.title)) continue;
      if (!g.sides.every(s => t.includes(nrm(s)))) continue;
      const ok = flags ? flags[v.video_id] : await oembedOk(v.video_id);
      if (!ok) { console.log(`official_video not embeddable, excluded: ${v.video_id}`); continue; }
      items.push({ event_id: g.event_id, league: g.league, matchup: g.matchup,
        video_id: v.video_id, title: v.title, channel_handle: v.handle, channel_id: v.channel_id,
        channel_title: v.channel_title || '',
        embed_url: `https://www.youtube.com/embed/${v.video_id}`,
        watch_url: `https://www.youtube.com/watch?v=${v.video_id}`,
        published: v.published, status: 'embeddable-official',
        checked_at: now.toISOString().replace(/\.\d{3}Z$/, '+00:00') });
    }
  }
  const out = { version: 1, generated_at: now.toISOString().replace(/\.\d{3}Z$/, '+00:00'),
    source: 'youtube-official-channels', fail_closed: true, items };
  await putJson(env, 'slates/official_video.json', out);
  return { games: games.length, scanned: candidates.length, validated: items.length, yt_api: !!flags };
}
