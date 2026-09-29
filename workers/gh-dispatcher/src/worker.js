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
  fetch() { return new Response('not found', { status: 404 }); }
};
