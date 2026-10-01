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
  'parity/exempt_summary.json': 'parity/exempt_summary.json',
  'parity/history.json': 'parity/history.json',
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
    if (path === 'diag') {
      const targets = {
        kalshi_series: 'https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker=KXMLB&limit=2&status=open',
        kalshi_tickers: 'https://api.elections.kalshi.com/trade-api/v2/markets?tickers=KXMLB-26-TB&limit=1',
        poly_gamma: 'https://gamma-api.polymarket.com/events?slug=mlb-world-series-champion-2026',
        espn_api: 'https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/news?limit=1',
        yahoo_rss: 'https://sports.yahoo.com/mlb/rss.xml',
        cbs_rss: 'https://www.cbssports.com/rss/headlines/mlb/',
        espn_rss: 'https://www.espn.com/espn/rss/mlb/news',
      };
      // probes use the lane UAs: espn_api 403s bot-looking UAs (UA+IP keyed, builder 4825975)
      const LANE_UA = { espn_api: 'Python-urllib/3.12 RixPicks/1.0' };
      const DEFAULT_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) RixPicks/1.0';
      const out = { ts: new Date().toISOString(), targets: {} };
      for (const [name, u] of Object.entries(targets)) {
        try {
          const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 10000);
          const r = await fetch(u, { headers: { 'User-Agent': LANE_UA[name] || DEFAULT_UA }, signal: ctl.signal });
          clearTimeout(t);
          const body = await r.text();
          out.targets[name] = { status: r.status, bytes: body.length, head: body.slice(0, 120) };
        } catch (e) { out.targets[name] = { error: String(e).slice(0, 120) }; }
      }
      return Response.json(out);
    }
    if (/^parity\/exempt\/[0-9TZ:.\-]+\.json$/.test(path)) {
      const eo = await env.FEEDS.get(path);
      if (!eo) return new Response('not found', { status: 404 });
      return new Response(eo.body, { headers: { 'content-type': 'application/json', 'cache-control': 'no-store', 'access-control-allow-origin': '*' } });
    }
    const key = SERVE[path];
    if (!key) return new Response('not found', { status: 404 });
    const obj = await env.FEEDS.get(key);
    if (!obj) return new Response('not ready', { status: 503, headers: { 'Retry-After': '60' } });
    return new Response(obj.body, { headers: { 'content-type': 'application/json', 'cache-control': 'no-store', 'access-control-allow-origin': '*' } });
  },
};
