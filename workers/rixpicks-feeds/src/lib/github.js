// GitHub couplings, both phase-gated OFF in shadow:
//  - dispatchXFeed: news rotation -> repository_dispatch 'x-feed-chain' (cutover: GHA news-refresh
//    is disabled and the X/NIM chain runs off THIS worker's rotations instead).
//  - futuresRepoBatch: hourly compacted ticks commit to keep analysis-side readers unchanged
//    during transition (replaces the GHA listener's every-75s pushes).
export async function dispatchXFeed(env) {
  if (env.XFEED_DISPATCH !== 'on' || !env.GH_DISPATCH_TOKEN) return { skipped: true };
  const r = await fetch('https://api.github.com/repos/ItsDardanRexhepi/rixpicks/dispatches', {
    method: 'POST',
    headers: { Authorization: 'Bearer ' + env.GH_DISPATCH_TOKEN, Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'rixpicks-feeds' },
    body: JSON.stringify({ event_type: 'x-feed-chain', client_payload: { source: 'cf-feeds', ts: new Date().toISOString() } }),
  });
  if (!r.ok) throw new Error('dispatch failed: ' + r.status);
  return { dispatched: true };
}
