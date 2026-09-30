// GitHub couplings, both phase-gated OFF in shadow:
//  - dispatchXFeed: news rotation -> repository_dispatch 'x-feed-chain' (cutover: GHA news-refresh
//    is disabled and the X/NIM chain runs off THIS worker's rotations instead).
//  - futuresRepoBatch: hourly compacted ticks commit to keep analysis-side readers unchanged
//    during transition (replaces the GHA listener's every-75s pushes).
export async function dispatchXFeed(env) {
  // Lane 3 Option A: dispatch goes through the gh-dispatcher worker (service binding) - the PAT
  // never leaves that worker. Gated by XFEED_DISPATCH and the binding being present.
  if (env.XFEED_DISPATCH !== 'on' || !env.DISPATCHER) return { skipped: true };
  const r = await env.DISPATCHER.fetch('https://gh-dispatcher.internal/dispatch', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ event_type: 'x-feed-chain' }),
  });
  if (!r.ok) throw new Error('dispatch failed: ' + r.status);
  return { dispatched: true };
}
