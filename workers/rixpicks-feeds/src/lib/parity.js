// Parity harness (lane 3 acceptance gate): after each shadow cycle, compare the R2 artifact
// against the live GH-pipeline artifact and record a verdict. 24h of >=95% in-parity cycles
// per lane is the cutover gate (see CUTOVER_PLAN.md).
async function getJson(url) { const r = await fetch(url); if (!r.ok) throw new Error('http ' + r.status); return r.json(); }

function newsParity(mine, prod) {
  const key = a => (a.link || '') || a.headline || '';
  const m = new Set((prod.latest || []).slice(0, 15).map(key));
  const w = (mine.latest || []).slice(0, 15).map(key);
  if (!m.size || !w.length) return { ok: false, reason: 'empty side', overlap: 0 };
  const hit = w.filter(k => m.has(k)).length;
  const overlap = hit / Math.max(m.size, w.length);
  return { ok: overlap >= 0.8, overlap: +overlap.toFixed(3), prod_latest: m.size, worker_latest: w.length };
}
function quotesParity(mine, prod) {
  const mq = mine.quotes || {}, pq = prod.quotes || {};
  const tickers = Object.keys(pq);
  if (!tickers.length) return { ok: true, reason: 'prod empty' };
  let covered = 0, close = 0, compared = 0;
  for (const t of tickers) {
    const a = mq[t], b = pq[t];
    if (!a) continue;
    covered++;
    if (a.yes_bid != null && b.yes_bid != null) { compared++; if (Math.abs(a.yes_bid - b.yes_bid) <= 2) close++; }
  }
  const cov = covered / tickers.length;
  const priceOk = compared === 0 || close / compared >= 0.95;
  return { ok: cov >= 0.95 && priceOk, coverage: +cov.toFixed(3), price_close: compared ? +(close / compared).toFixed(3) : null };
}
function futuresParity(mine, prodRows) {
  // prodRows: latest row per league from the repo ticks file (parsed by caller)
  let keysP = new Set(), keysM = new Set(); let close = 0, compared = 0;
  const mineByLeague = mine.leagues || {};
  for (const [lg, prow] of Object.entries(prodRows)) {
    const pb = prow.board || {}, mb = (mineByLeague[lg] || {}).board || {};
    for (const k of Object.keys(pb)) {
      keysP.add(lg + k);
      if (k in mb) {
        keysM.add(lg + k);
        if (Math.abs((mb[k] || 0) - pb[k]) <= 2) close++;
        compared++;
      }
    }
    for (const k of Object.keys(mb)) keysM.add(lg + k);
  }
  if (!keysP.size) return { ok: true, reason: 'prod empty' };
  const cov = [...keysP].filter(k => keysM.has(k)).length / keysP.size;
  const priceOk = compared === 0 || close / compared >= 0.95;
  return { ok: cov >= 0.95 && priceOk, coverage: +cov.toFixed(3), price_close: compared ? +(close / compared).toFixed(3) : null };
}

export async function runParity(env, justRan) {
  const report = { ts: new Date().toISOString(), lanes: {} };
  try {
    if (justRan.news) {
      const o = await env.FEEDS.get('slates/news.json'); const mine = o ? JSON.parse(await o.text()) : null;
      const prod = await getJson(env.PROD_BASE + '/slates/news.json?cb=' + Date.now());
      report.lanes.news = mine ? newsParity(mine, prod) : { ok: false, reason: 'no worker artifact' };
    }
    if (justRan.kalshi) {
      const o = await env.FEEDS.get('slates/nfl_kalshi_quotes.json'); const mine = o ? JSON.parse(await o.text()) : null;
      const prod = await getJson(env.PROD_BASE + '/slates/nfl_kalshi_quotes.json?cb=' + Date.now());
      report.lanes.kalshi_quotes = mine ? quotesParity(mine, prod) : { ok: false, reason: 'no worker artifact' };
    }
    if (justRan.futures) {
      const o = await env.FEEDS.get('futures/current.json'); const mine = o ? JSON.parse(await o.text()) : null;
      let prodRows = {};
      try {
        const txt = await (await fetch(env.PROD_BASE + '/data/futures_ws_ticks.jsonl?cb=' + Date.now())).text();
        const lines = txt.trim().split('\n').filter(Boolean);
        for (const ln of lines.slice(-400)) { const r = JSON.parse(ln); prodRows[r.league] = r; }
      } catch (e) { report.lanes.futures = { ok: false, reason: 'prod ticks unreadable' }; }
      if (!report.lanes.futures) report.lanes.futures = mine ? futuresParity(mine, prodRows) : { ok: false, reason: 'no worker artifact' };
    }
  } catch (e) { report.error = String(e).slice(0, 120); }
  // rolling 24h window
  let hist = [];
  try { const o = await env.FEEDS.get('parity/history.json'); if (o) hist = JSON.parse(await o.text()); } catch (e) {}
  hist.push(report);
  const cutoff = Date.now() - 24 * 3600 * 1000;
  hist = hist.filter(r => Date.parse(r.ts) >= cutoff).slice(-2000);
  const summary = { ts: report.ts, window_cycles: hist.length, lanes: {} };
  for (const lane of ['news', 'kalshi_quotes', 'futures']) {
    const runs = hist.map(h => h.lanes && h.lanes[lane]).filter(Boolean);
    if (!runs.length) { summary.lanes[lane] = null; continue; }
    const okN = runs.filter(r => r.ok).length;
    summary.lanes[lane] = { cycles: runs.length, in_parity: okN, pct: +(100 * okN / runs.length).toFixed(1), gate_95: okN / runs.length >= 0.95 };
  }
  await Promise.all([
    env.FEEDS.put('parity/history.json', JSON.stringify(hist)),
    env.FEEDS.put('parity/latest.json', JSON.stringify({ report, summary }, null, 1), { httpMetadata: { contentType: 'application/json' } }),
  ]);
  return summary;
}
