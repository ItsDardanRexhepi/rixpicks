// rixpicks-feeds - lane 3 Cloudflare migration: the feed pipeline's reliable time base.
// CF cron replaces GitHub hosted cron (the starvation class) at the root.
// Shadow phase: producers write R2 only; nothing user-visible changes.
import { runNews } from './lanes/news.js';
import { runKalshiQuotes } from './lanes/kalshiQuotes.js';
import { runFutures } from './lanes/futures.js';
import { runParity } from './lib/parity.js';
import { dispatchXFeed } from './lib/github.js';

const SERVE = {
  'feeds/news.json': 'slates/news.json',
  'feeds/nfl_kalshi_quotes.json': 'slates/nfl_kalshi_quotes.json',
  'feeds/news_images.json': 'slates/news_images.json',
  'feeds/img_check.json': 'slates/img_check.json',
  'feeds/futures/current.json': 'futures/current.json',
  'parity/latest.json': 'parity/latest.json',
};

export default {
  async scheduled(event, env, ctx) {
    const fiveMin = event.cron.startsWith('*/5');
    ctx.waitUntil((async () => {
      const ran = { news: false, kalshi: false, futures: true };
      try {
        const f = await runFutures(env);
        console.log('futures:', JSON.stringify(f));
      } catch (e) { console.error('futures lane error:', String(e).slice(0, 120)); }
      if (fiveMin) {
        ran.news = ran.kalshi = true;
        let newsRes = null;
        try {
          const before = await env.FEEDS.get('slates/news.json');
          const beforeTxt = before ? await before.text() : '';
          newsRes = await runNews(env);
          console.log('news:', JSON.stringify(newsRes));
          const after = await env.FEEDS.get('slates/news.json');
          const rotated = after && (await after.text()) !== beforeTxt;
          if (rotated) { try { console.log('xfeed dispatch:', JSON.stringify(await dispatchXFeed(env))); } catch (e) { console.error('dispatch err', String(e).slice(0, 80)); } }
        } catch (e) { console.error('news lane error:', String(e).slice(0, 120)); }
        try { console.log('kalshi:', JSON.stringify(await runKalshiQuotes(env))); } catch (e) { console.error('kalshi lane error:', String(e).slice(0, 120)); }
      }
      try { console.log('parity:', JSON.stringify(await runParity(env, ran))); } catch (e) { console.error('parity error:', String(e).slice(0, 120)); }
    })());
  },
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/^\//, '');
    if (path === 'health') return Response.json({ ok: true, ts: new Date().toISOString(), worker: 'rixpicks-feeds', phase: env.XFEED_DISPATCH === 'on' ? 'cutover' : 'shadow' });
    const key = SERVE[path];
    if (!key) return new Response('not found', { status: 404 });
    const obj = await env.FEEDS.get(key);
    if (!obj) return new Response('not ready', { status: 503, headers: { 'Retry-After': '60' } });
    return new Response(obj.body, { headers: { 'content-type': 'application/json', 'cache-control': 'no-store', 'access-control-allow-origin': '*' } });
  },
};
