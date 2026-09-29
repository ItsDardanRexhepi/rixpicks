// Parity harness (lane 3 acceptance gate): after each shadow cycle, compare the R2 artifact
// against the live GH-pipeline artifact and record a verdict. 24h of >=95% in-parity cycles
// per lane is the cutover gate (see CUTOVER_PLAN.md).
async function getJson(url) { const r = await fetch(url); if (!r.ok) throw new Error('http ' + r.status); return r.json(); }

// Age-aware recall (gate decision 9/29 09:15 PT, main+builder): a miss counts only if the
// prod story is older than MISS_AGE_MIN at comparison time - both pollers get a fair window
// on a fast lane before divergence counts against fidelity.
const MISS_AGE_MIN = 15;
function newsParity(mine, prod) {
  const key = a => (a.link || '') || a.headline || '';
  const p15arts = (prod.latest || []).slice(0, 15);
  const wall = new Set();
  for (const a of mine.latest || []) wall.add(key(a));
  for (const lst of Object.values(mine.leagues || {})) for (const a of lst) wall.add(key(a));
  if (!p15arts.length || !wall.size) return { ok: false, reason: 'empty side', recall: 0 };
  const now = Date.now();
  let scored = 0, hit = 0; const misses = [];
  for (const a of p15arts) {
    const k = key(a); if (!k) continue;
    const pub = Date.parse(a.published || '');
    const ageMin = isNaN(pub) ? Infinity : (now - pub) / 60000;
    if (wall.has(k)) { scored++; hit++; continue; }
    if (ageMin <= MISS_AGE_MIN) continue; // inside the fair window - not scored
    scored++;
    misses.push({ src: a.source, league: a.league, age_min: Math.round(ageMin), headline: (a.headline || '').slice(0, 60) });
  }
  const recall = scored ? hit / scored : 1;
  const src = arr => arr.reduce((m, a) => { m[a.source] = (m[a.source] || 0) + 1; return m; }, {});
  const fresh = !prod.generated_at || (mine.generated_at || '') >= (prod.generated_at || '');
  return { ok: recall >= 0.8 && fresh, recall: +recall.toFixed(3), scored, fresh, misses: misses.slice(0, 5),
    prod_sources: src(prod.latest || []), worker_sources: src(mine.latest || []),
    prod_degraded: prod.degraded_sources || null };
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
// Hybrid decision (main 9/28 22:16 relay): Poly legs migrate to the worker; Kalshi legs stay
// GHA-side until a non-CF relay exists. The futures GATE therefore evaluates the Poly leg;
// the Kalshi leg is reported informationally and never gates.
function futuresParity(mine, prodRows, quality) {
  // illiquid books (spread > 25c) have no knowable mid - exclude from price agreement
  const wide = new Set(Object.entries((quality || {}).spread_c || {}).filter(([, v]) => v > 25).map(([k]) => k));
  const mineByLeague = mine.leagues || {};
  function evalLeg(prefix) {
    let keysP = new Set(), keysM = new Set(); let close = 0, compared = 0;
    for (const [lg, prow] of Object.entries(prodRows)) {
      const pb = prow.board || {}, mb = (mineByLeague[lg] || {}).board || {};
      for (const k of Object.keys(pb).filter(k => k.startsWith(prefix))) {
        keysP.add(lg + k);
        if (k in mb) {
          keysM.add(lg + k);
          if (prefix === 'P:' && wide.has(k)) continue; // illiquid: coverage counts, price doesn't
          if (Math.abs((mb[k] || 0) - pb[k]) <= 2) close++;
          compared++;
        }
      }
      for (const k of Object.keys(mb).filter(k => k.startsWith(prefix))) keysM.add(lg + k);
    }
    if (!keysP.size) return { ok: true, reason: 'prod empty' };
    const cov = [...keysP].filter(k => keysM.has(k)).length / keysP.size;
    const priceOk = compared === 0 || close / compared >= 0.95;
    return { ok: cov >= 0.95 && priceOk, coverage: +cov.toFixed(3), price_close: compared ? +(close / compared).toFixed(3) : null };
  }
  const poly = evalLeg('P:');
  const kalshi = evalLeg('K:');
  poly.kalshi_leg = { delegated: 'gha', ...kalshi };
  return poly;
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
      if (!mine && !Object.keys(prod.quotes || {}).length) report.lanes.kalshi_quotes = { ok: true, reason: 'both dormant' };
      else report.lanes.kalshi_quotes = mine ? quotesParity(mine, prod) : { ok: false, reason: 'no worker artifact' };
    }
    if (justRan.futures) {
      const o = await env.FEEDS.get('futures/current.json'); const mine = o ? JSON.parse(await o.text()) : null;
      let prodRows = {};
      try {
        const txt = await (await fetch(env.PROD_BASE + '/data/futures_ws_ticks.jsonl?cb=' + Date.now())).text();
        const lines = txt.trim().split('\n').filter(Boolean);
        // prod rows are incremental (changed keys only) - replay to reconstruct current state
        for (const ln of lines.slice(-3000)) {
          const r = JSON.parse(ln);
          if (!prodRows[r.league]) prodRows[r.league] = { board: {} };
          Object.assign(prodRows[r.league].board, r.board || {});
        }
      } catch (e) { report.lanes.futures = { ok: false, reason: 'prod ticks unreadable' }; }
      if (!report.lanes.futures) {
        let quality = null;
        try { const qo = await env.FEEDS.get('futures/quality.json'); if (qo) quality = JSON.parse(await qo.text()); } catch (e) {}
        report.lanes.futures = mine ? futuresParity(mine, prodRows, quality) : { ok: false, reason: 'no worker artifact' };
      }
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
