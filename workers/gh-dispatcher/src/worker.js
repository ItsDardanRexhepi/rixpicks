// guard 4 scheduler class kill: GitHub hosted cron starves this repo (x-feed: 0 schedule fires
// in 40 runs). This worker is the external time base - repository_dispatch 'external-tick' every
// 15 min, staggered off the quarter-hour. GitHub cron stays as backstop signal only.
export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil((async () => {
      const res = await fetch('https://api.github.com/repos/ItsDardanRexhepi/rixpicks/dispatches', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer ' + env.GH_DISPATCH_TOKEN,
          'Accept': 'application/vnd.github+json',
          'X-GitHub-Api-Version': '2022-11-28',
          'User-Agent': 'rixpicks-cf-dispatcher'
        },
        body: JSON.stringify({ event_type: 'external-tick', client_payload: { source: 'cf-cron', ts: new Date().toISOString() } })
      });
      if (!res.ok) throw new Error('dispatch failed: ' + res.status + ' ' + (await res.text()));
    })());
  },
  // Lane 3 Option A (main 9/30 4:04 PM PT): service-binding entry point for rixpicks-feeds, so the
  // PAT stays in this worker only. Whitelisted event type; workers.dev is disabled in
  // wrangler.toml so this is reachable only through the binding.
  async fetch(request, env) {
    const u = new URL(request.url);
    if (request.method !== 'POST' || u.pathname !== '/dispatch') return new Response('not found', { status: 404 });
    let body = {};
    try { body = await request.json(); } catch (e) {}
    if (body.event_type !== 'x-feed-chain') return new Response('event_type not allowed', { status: 400 });
    const res = await fetch('https://api.github.com/repos/ItsDardanRexhepi/rixpicks/dispatches', {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + env.GH_DISPATCH_TOKEN,
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'rixpicks-cf-dispatcher'
      },
      body: JSON.stringify({ event_type: 'x-feed-chain', client_payload: { source: 'cf-feeds', ts: new Date().toISOString() } })
    });
    return new Response(JSON.stringify({ ok: res.ok, status: res.status }), { status: res.ok ? 200 : 502, headers: { 'content-type': 'application/json' } });
  }
};
