// Parity harness (lane 3 acceptance gate): after each shadow cycle, compare the R2 artifact
// against the live GH-pipeline artifact and record a verdict. 24h of >=95% in-parity cycles
// per lane is the cutover gate (see CUTOVER_PLAN.md).
async function getJson(url) { const r = await fetch(url); if (!r.ok) throw new Error('http ' + r.status); return r.json(); }

// ---------------------------------------------------------------------------
// News gate v9 (builder decision 9/29 10:18 PT, amendments A/B/C over the
// distributional+staleness proposal): story-identity parity is structurally
// capped (~0.87 mean) because two pollers sample rolling limit-10 windows 5-6
// min apart; the gate therefore measures what cutover must preserve.
//   (1) per-source coverage: presence + tolerance bands vs the worker's own
//       rolling baseline (cross-poller mix variance observed at +/-30%, so
//       bands anchor to the worker baseline ESPN 54 / YAHOO 66 / CBS 37)
//   (2) bucket coverage: every league bucket prod serves is non-empty here
//   (3) freshness: comparative while prod exists (median latest age <= prod
//       median + 5 min); absolute at cutover (median <= 20 min, p90 <= 60)
//   (4) staleness: no >24h story in latest or in the evidence-safe major
//       buckets; niche + nhl/wnba/soccer exempt (evidence 9/29 below)
//   (5) outage guard (sustained): 1h median recall < 0.6, or a prod-present
//       source absent here (v4 UA bug sat at ~0.2; churn cycles sit >= 0.71)
//   (6) schema integrity: every story has headline, link, source, parseable ts
//   (7) volume floor: total occurrences >= 60% of rolling 7d median
// Amendment A evidence (9/29 artifact audit, both pollers): >24h items sat in
// hockey/nhl (26d), basketball/wnba (11d), soccer/usa.1+usa.nwsl (26-32h) on
// BOTH pollers, and niche buckets routinely carry slow-feed backlog (CBS
// boxing feed top item 3d old; prod's boxing/golf buckets reach Aug items
// when prod's niche ESPN lanes fail). Ban set is therefore the five buckets
// verified all-fresh on both pollers:
const STALENESS_BAN_BUCKETS = ['football/nfl', 'basketball/nba', 'baseball/mlb',
  'football/college-football', 'basketball/mens-college-basketball'];
// two-form staleness (9/29 14:15 PT evidence: CBS nba feed held the same 3 items at 24-25h
// on BOTH pollers - legit feed backlog in a major bucket, not worker lag): while prod exists
// a >24h ban-bucket item is excused when prod's same location carries it; post-cutover the
// hard backstop is STALE_ABS_H. Mirrors amendment B's two-form freshness.
const STALE_H = 24, STALE_ABS_H = 48;
// Freshness mode: 'comparative' while the GH poller exists; flip to 'absolute'
// at news cutover (one-line change, Phase C of CUTOVER_PLAN.md).
const FRESHNESS_MODE = 'comparative';
const FRESH_COMPARE_SLACK_MIN = 5, FRESH_ABS_MEDIAN_MIN = 20, FRESH_ABS_P90_MIN = 60;
const BAND_LO = 0.4, BAND_HI = 2.0; // vs rolling per-source median baseline
const BASELINE_MIX = { ESPN: 54, YAHOO: 66, CBS: 37 }; // builder-stated 9/29 baseline (pre-rolling fallback)
const BASELINE_TOTAL = 157, VOLUME_FLOOR_FRAC = 0.6;
const OUTAGE_MEDIAN_RECALL = 0.6; // 1h median recall below this = sustained outage
const MISS_AGE_MIN = 15; // age-aware recall window (9/29 09:15 PT decision) - observational

function mixOf(d) {
  const m = {};
  const add = a => { if (a && a.source) m[a.source] = (m[a.source] || 0) + 1; };
  (d.latest || []).forEach(add);
  for (const lst of Object.values(d.leagues || {})) lst.forEach(add);
  return m;
}
function agesMin(arts, now) {
  const out = [];
  for (const a of arts) {
    const t = Date.parse(a.published || '');
    if (!isNaN(t)) out.push(Math.max(0, (now - t) / 60000)); // future-dated clamps to 0
  }
  return out.sort((x, y) => x - y);
}
const median = a => a.length ? (a.length % 2 ? a[(a.length - 1) / 2] : (a[a.length / 2 - 1] + a[a.length / 2]) / 2) : null;
const p90 = a => a.length ? a[Math.min(a.length - 1, Math.floor(0.9 * a.length))] : null;

function newsGate(mine, prod, ctx, now) {
  const checks = {};
  // (6) schema integrity
  let schemaBad = [];
  const allArts = [...(mine.latest || [])];
  for (const [lg, lst] of Object.entries(mine.leagues || {})) for (const a of lst) allArts.push({ ...a, _lg: lg });
  for (const a of allArts) {
    if (!a.headline || !a.link || !a.source || isNaN(Date.parse(a.published || '')))
      schemaBad.push((a.headline || '?').slice(0, 50));
    if (schemaBad.length > 4) break;
  }
  checks.schema = { ok: schemaBad.length === 0, violations: schemaBad.slice(0, 5) };
  // (1) per-source coverage
  const myMix = mixOf(mine), prodMix = mixOf(prod);
  const srcDetail = {};
  let srcOk = true;
  for (const src of ['ESPN', 'YAHOO', 'CBS']) {
    const base = (ctx.mixBaseline && ctx.mixBaseline[src]) || BASELINE_MIX[src];
    const n = myMix[src] || 0;
    const missing = (prodMix[src] || 0) > 0 && n === 0;
    const inBand = n >= BAND_LO * base && n <= BAND_HI * base;
    if (missing || !inBand) srcOk = false;
    srcDetail[src] = { n, baseline: +base.toFixed(1), missing, in_band: inBand };
  }
  checks.sources = { ok: srcOk, ...srcDetail };
  // (2) bucket coverage
  const bucketGaps = Object.entries(prod.leagues || {}).filter(([, l]) => l.length > 0)
    .map(([k]) => k).filter(k => !((mine.leagues || {})[k] || []).length);
  // news bucket rule (relayed by main 10/1 3:33 PM PT; prospective only): a bucket gap is skipped ONLY when the worker's own
  // reads for that bucket this cycle all succeeded (ok > 0, fail = 0) and found zero relevant items, taken from
  // slates/news_reads.json stamped with the same generated_at as the artifact judged. Missing, mismatched, failed
  // or unverifiable reads fail closed. Source items with an empty worker bucket still fail. No headline-age exemption.
  const rd = ctx.reads && ctx.reads.generated_at === mine.generated_at ? ctx.reads.reads || {} : null;
  const skipped = [], remaining = [];
  for (const k of bucketGaps) {
    const r = rd && rd[k];
    if (r && r.fail === 0 && r.ok > 0 && r.n_relevant === 0) skipped.push({ bucket: k, ...r }); else remaining.push(k);
  }
  checks.buckets = { ok: remaining.length === 0, gaps: remaining, rule: "verified-zero", ok_v9: bucketGaps.length === 0, gaps_v9: bucketGaps, skipped_verified_zero: skipped, reads_stamp_match: !!rd };
  // (3) freshness
  const wAges = agesMin(mine.latest || [], now), pAges = agesMin(prod.latest || [], now);
  const wMed = median(wAges), pMed = median(pAges), wP90 = p90(wAges);
  let freshOk, freshMode = FRESHNESS_MODE;
  if (FRESHNESS_MODE === 'absolute') freshOk = (wMed != null && wMed <= FRESH_ABS_MEDIAN_MIN) && (wP90 != null && wP90 <= FRESH_ABS_P90_MIN);
  else freshOk = wMed == null || pMed == null || wMed <= pMed + FRESH_COMPARE_SLACK_MIN;
  // v8 generated_at ordering guard retained: worker artifact must not predate prod's
  const freshOrder = !prod.generated_at || (mine.generated_at || '') >= (prod.generated_at || '');
  checks.freshness = { ok: freshOk && freshOrder, mode: freshMode, worker_median_age: wMed && +wMed.toFixed(1),
    prod_median_age: pMed && +pMed.toFixed(1), worker_p90_age: wP90 && +wP90.toFixed(1), generated_order_ok: freshOrder };
  // (4) staleness (scoped ban set; niche + nhl/wnba/soccer exempt per evidence above)
  const storyKey = a => (a.link || '') || (a.headline || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  const prodAt = where => new Set((where === 'latest' ? prod.latest || [] : (prod.leagues || {})[where] || []).map(storyKey));
  const prodLatestKeys = prodAt('latest');
  const stale = [], excused = [];
  const staleCheck = (a, where) => {
    const t = Date.parse(a.published || '');
    if (isNaN(t)) return;
    const ageH = (now - t) / 3600000;
    const rec = { where, age_h: Math.round(ageH), headline: (a.headline || '').slice(0, 50) };
    if (FRESHNESS_MODE === 'absolute') { if (ageH > STALE_ABS_H) stale.push(rec); return; }
    if (ageH <= STALE_H) return;
    // comparative: excused when prod carries the same story in the same location (or latest)
    if (prodAt(where).has(storyKey(a)) || prodLatestKeys.has(storyKey(a))) excused.push(rec);
    else stale.push(rec);
  };
  for (const a of mine.latest || []) staleCheck(a, 'latest');
  for (const k of STALENESS_BAN_BUCKETS) for (const a of (mine.leagues || {})[k] || []) staleCheck(a, k);
  checks.staleness = { ok: stale.length === 0, mode: FRESHNESS_MODE === 'absolute' ? 'absolute_' + STALE_ABS_H + 'h' : 'comparative_' + STALE_H + 'h',
    ban_buckets: STALENESS_BAN_BUCKETS, violations: stale.slice(0, 5), excused_shared_with_prod: excused.slice(0, 5) };
  // (7) volume floor
  const total = Object.values(myMix).reduce((s, n) => s + n, 0);
  const volBase = ctx.totalBaseline || BASELINE_TOTAL;
  checks.volume = { ok: total >= VOLUME_FLOOR_FRAC * volBase, total, baseline: +volBase.toFixed(1), floor: +(VOLUME_FLOOR_FRAC * volBase).toFixed(1) };
  // (5) sustained-outage guard: 1h median recall (incl. this cycle) < 0.6
  // age-aware recall (observational + feeds the guard)
  const key = a => (a.link || '') || a.headline || '';
  const p15arts = (prod.latest || []).slice(0, 15);
  const wall = new Set();
  for (const a of mine.latest || []) wall.add(key(a));
  for (const lst of Object.values(mine.leagues || {})) for (const a of lst) wall.add(key(a));
  let scored = 0, hit = 0; const misses = [];
  for (const a of p15arts) {
    const k = key(a); if (!k) continue;
    const pub = Date.parse(a.published || '');
    const ageMin = isNaN(pub) ? Infinity : (now - pub) / 60000;
    if (wall.has(k)) { scored++; hit++; continue; }
    if (ageMin <= MISS_AGE_MIN) continue;
    scored++;
    misses.push({ src: a.source, league: a.league, age_min: Math.round(ageMin), headline: (a.headline || '').slice(0, 60) });
  }
  const recall = scored ? hit / scored : (wall.size ? 1 : 0);
  const recalls1h = [...(ctx.recentRecalls || []), recall];
  const recMed = median(recalls1h.slice().sort((x, y) => x - y));
  checks.outage_guard = { ok: recMed == null || recMed >= OUTAGE_MEDIAN_RECALL, recall_1h_median: recMed && +recMed.toFixed(3), samples: recalls1h.length };
  const ok = Object.values(checks).every(c => c.ok);
  return { ok, checks, recall: +recall.toFixed(3), scored, misses: misses.slice(0, 5),
    worker_mix: myMix, worker_total: total, prod_mix: prodMix,
    med_age_w: wMed && +wMed.toFixed(1), med_age_p: pMed && +pMed.toFixed(1),
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
// Prod-staleness exemption (main 9/30 15:22 PT): prod's tick file is changed-keys-only, so a Poly
// key whose last prod tick is older than STALE_PROD_MIN is prod lag, not a worker defect. Such
// keys are excluded from the PRICE comparison only (coverage still counts) and are listed in
// report `exempt_stale` (key, last_prod_tick, age_min) - never silently dropped. No tolerance
// change; the NWSL wide-spread (>25c) exclusion is unchanged. Acceptance math: a cycle's
// price_close = close/compared with exempt and wide keys removed from `compared`.
// v12 off-market-reference exemption (main 9/30 4:37 PM PT). ALL THREE required, per Poly key:
//  (1) prod value sits OUTSIDE the live [bid, ask] book of the same market (worker's latest poll);
//  (2) last prod tick for that key is more than OFFBOOK_MIN_AGE_MIN old;
//  (3) worker value sits INSIDE the live book (or within 0.1c of the live mid).
// If the worker is also outside the book it is a real divergence: not exempt, counts against
// parity. Price comparison only (coverage still counts). Every exempted key is reported in
// `exempt_offbook` with prod value, worker value, live bid/ask and last prod tick time, and
// must be listed in the final acceptance summary. Tolerance unchanged (+/-2c).
function fnv(str) { let h = 2166136261; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; } return h.toString(16).padStart(8, '0'); }
const OFFBOOK_MIN_AGE_MIN = 15;
const EXEMPT_RETAIN_DAYS = 7; // v15: retention for parity/exempt/<ts>.json audit files
const STALE_PROD_MIN = 60;
function futuresParity(mine, prodRows, quality, lastTick, nowMs) {
  const exempt = []; const exemptBook = []; const mism = []; const exemptIn = []; let closeOld = 0, comparedOld = 0;
  const bookC = (quality || {}).book_c || {};
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
          if (prefix === 'P:' && lastTick) {
            const lt = lastTick[lg + k], ageMin = lt ? (nowMs - lt) / 60000 : Infinity;
            if (ageMin > STALE_PROD_MIN) { exempt.push({ key: lg + k, last_prod_tick: lt ? new Date(lt).toISOString() : null, age_min: isFinite(ageMin) ? Math.round(ageMin) : null }); continue; }
          }
          if (prefix === 'P:' && lastTick && bookC[k]) {
            const [bid, ask] = bookC[k], pv = pb[k], wv = mb[k];
            const lt = lastTick[lg + k], ageMin = lt ? (nowMs - lt) / 60000 : Infinity;
            const prodOut = pv < bid || pv > ask;
            const workerIn = (wv >= bid && wv <= ask) || Math.abs(wv - (bid + ask) / 2) <= 0.1;
            if (prodOut && ageMin > OFFBOOK_MIN_AGE_MIN && workerIn && Math.abs(wv - pv) > 2) {
              exemptBook.push({ key: lg + k, prod: pv, worker: wv, bid, ask, last_prod_tick: lt ? new Date(lt).toISOString() : null, age_min: isFinite(ageMin) ? Math.round(ageMin) : null });
              continue;
            }
          }
          if (prefix === 'P:' && lastTick && bookC[k]) {
            // v16 in-book stale-prod exemption (relayed by main 10/1 3:32 PM PT): worker inside the
            // live [bid, ask], last prod tick >15 min old, |worker-prod| > 2c. No book = no exemption; a worker
            // outside the book is a miss. Logged per key in exempt_inbook. Old-rule ratio kept alongside.
            const [bid, ask] = bookC[k], pv = pb[k], wv = mb[k];
            const lt = lastTick[lg + k], ageMin = lt ? (nowMs - lt) / 60000 : Infinity;
            if (wv >= bid && wv <= ask && ageMin > OFFBOOK_MIN_AGE_MIN && Math.abs(wv - pv) > 2) {
              exemptIn.push({ key: lg + k, prod: pv, worker: wv, bid, ask, last_prod_tick: lt ? new Date(lt).toISOString() : null, age_min: isFinite(ageMin) ? Math.round(ageMin) : null });
              comparedOld++; // old rule: counted as a miss
              continue;
            }
          }
          if (prefix === 'P:') { comparedOld++; if (Math.abs((mb[k] || 0) - pb[k]) <= 2) closeOld++; }
          if (Math.abs((mb[k] || 0) - pb[k]) <= 2) close++;
          else if (prefix === 'P:') {
            // v14 diagnostic (main 10/1 1:27 PM PT): non-exempt compared keys that miss the 2c band
            const lt = lastTick && lastTick[lg + k], ageMin = lt ? (nowMs - lt) / 60000 : null, bk = bookC[k];
            mism.push({ key: lg + k, prod: pb[k], worker: mb[k], gap: +Math.abs((mb[k] || 0) - pb[k]).toFixed(2), bid: bk ? bk[0] : null, ask: bk ? bk[1] : null, prod_tick_age_min: ageMin != null && isFinite(ageMin) ? Math.round(ageMin) : null });
          }
          compared++;
        }
      }
      for (const k of Object.keys(mb).filter(k => k.startsWith(prefix))) keysM.add(lg + k);
    }
    if (!keysP.size) return { ok: true, reason: 'prod empty' };
    const cov = [...keysP].filter(k => keysM.has(k)).length / keysP.size;
    const priceOk = compared === 0 || close / compared >= 0.95;
    const r = { ok: cov >= 0.95 && priceOk, coverage: +cov.toFixed(3), price_close: compared ? +(close / compared).toFixed(3) : null };
    if (prefix === 'P:') r.price_close_v15rule = comparedOld ? +(closeOld / comparedOld).toFixed(3) : null;
    return r;
  }
  const poly = evalLeg('P:');
  const kalshi = evalLeg('K:');
  poly.kalshi_leg = { delegated: 'gha', ...kalshi };
  // v13 audit (main 9/30 ~11:25 PM PT): history lists stay capped at 30 but the counts and a hash of
  // the FULL key set are always recorded; the full per-cycle lists ride on a transient field that
  // runParity moves to R2 (parity/exempt/<ts>.json) and into parity/exempt_summary.json.
  poly.exempt_stale_n = exempt.length;
  poly.exempt_offbook_n = exemptBook.length;
  if (exempt.length) { poly.exempt_stale = exempt.slice(0, 30); poly.exempt_stale_keys_hash = fnv(exempt.map(e => e.key).sort().join('|')); }
  if (exemptBook.length) poly.exempt_offbook = exemptBook.slice(0, 30);
  poly.exempt_inbook_n = exemptIn.length;
  if (exemptIn.length) poly.exempt_inbook = exemptIn.slice(0, 30);
  poly.mismatch_n = mism.length;
  if (mism.length) poly.mismatch = mism.slice(0, 30);
  poly._exempt_full = { stale: exempt, offbook: exemptBook, inbook: exemptIn, mismatch: mism };
  return poly;
}

// ---------------------------------------------------------------------------
// Ported-lane gates (2026-10-14, repo-retirement steps 1-3): one comparator per new shadow
// lane, structural + value agreement, sized to the timing noise of two independent pollers.
// Same acceptance shape as the original three lanes: 24h of >=95% in-parity cycles per lane.
function freshMin(ts, now) { const t = Date.parse(ts || ''); return isNaN(t) ? null : (now - t) / 60000; }

function liveGamesParity(mine, prod, now) {
  const ids = d => { const s = new Set(); for (const l of (d && d.leagues) || []) for (const g of l.games || []) s.add(g.espn_event_id); return s; };
  const p = ids(prod), m = ids(mine);
  const age = freshMin(mine.generated_at, now);
  const freshOk = age != null && age <= 20;
  if (!p.size) return { ok: freshOk, reason: 'prod empty', worker_games: m.size, worker_age_min: age != null ? +age.toFixed(1) : null };
  const cov = [...p].filter(k => m.has(k)).length / p.size;
  return { ok: cov >= 0.9 && freshOk, coverage: +cov.toFixed(3), prod_games: p.size, worker_games: m.size, worker_age_min: age != null ? +age.toFixed(1) : null };
}

function wooderTdParity(mine, prod) {
  const pl = prod.legs || [];
  const ml = new Map((mine.legs || []).map(l => [l.player + '|' + l.matchup, l]));
  if (!pl.length) return { ok: true, reason: 'prod empty' };
  let covered = 0, agree = 0;
  for (const l of pl) {
    const w = ml.get(l.player + '|' + l.matchup);
    if (!w) continue;
    covered++;
    if (!!w.td_scored === !!l.td_scored) agree++;
  }
  const cov = covered / pl.length;
  return { ok: cov >= 0.95 && (covered === 0 || agree / covered >= 0.95),
    coverage: +cov.toFixed(3), td_agree: covered ? +(agree / covered).toFixed(3) : null, legs: pl.length };
}

// prod futures.json carries quotes inline and only moves when its GHA lanes commit, so a prod
// quote older than 30 min is prod lag, not a worker defect: excluded from the price comparison
// (coverage still counts), same exemption philosophy as the futures v11 stale rule.
function futuresQuotesParity(mine, prod, now) {
  const prows = (Array.isArray(prod) ? prod : []).filter(r => r.kalshi_quote && r.kalshi_quote.ticker);
  const mrows = new Map(((mine || {}).rows || []).map(r => [r.id, r]));
  if (!prows.length) return { ok: true, reason: 'prod empty' };
  let covered = 0, compared = 0, close = 0, exemptStale = 0;
  for (const p of prows) {
    const w = mrows.get(p.id);
    if (!w || !w.kalshi_quote || w.kalshi_quote.ask_c == null) continue;
    covered++;
    const page = freshMin(p.kalshi_quote.quoted_at, now);
    if (page == null || page > 30) { exemptStale++; continue; }
    if (p.kalshi_quote.ask_c == null) continue;
    compared++;
    if (Math.abs(w.kalshi_quote.ask_c - p.kalshi_quote.ask_c) <= 2) close++;
  }
  const cov = covered / prows.length;
  const priceOk = compared === 0 || close / compared >= 0.9;
  return { ok: cov >= 0.9 && priceOk, coverage: +cov.toFixed(3),
    price_close: compared ? +(close / compared).toFixed(3) : null, exempt_stale_n: exemptStale, rows: prows.length };
}

function officialVideoParity(mine, prod) {
  const pids = new Set((prod.items || []).map(i => i.video_id + '|' + i.event_id));
  const mids = new Set((mine.items || []).map(i => i.video_id + '|' + i.event_id));
  if (!pids.size) return { ok: true, reason: mids.size ? 'prod empty' : 'both empty', worker_items: mids.size };
  const cov = [...pids].filter(k => mids.has(k)).length / pids.size;
  return { ok: cov >= 0.8, coverage: +cov.toFixed(3), prod_items: pids.size, worker_items: mids.size };
}

function recYardsParity(mine, prod, now) {
  const pp = prod.players || {}, mp = (mine || {}).players || {};
  const names = Object.keys(pp);
  const age = freshMin(mine.fetched_at, now);
  const freshOk = age != null && age <= 7 * 60;
  if (!names.length) return { ok: freshOk, reason: 'prod empty', worker_age_min: age != null ? Math.round(age) : null };
  let covered = 0, close = 0;
  for (const n of names) {
    if (!(n in mp)) continue;
    covered++;
    if (Math.abs((mp[n].yards || 0) - (pp[n].yards || 0)) <= 10) close++;
  }
  const cov = covered / names.length;
  return { ok: cov >= 0.9 && (covered === 0 || close / covered >= 0.9) && freshOk,
    coverage: +cov.toFixed(3), yards_close: covered ? +(close / covered).toFixed(3) : null,
    worker_age_min: age != null ? Math.round(age) : null };
}

function nflScoresParity(mine, prod) {
  const pg = prod.games || [];
  const mg = new Map(((mine || {}).games || []).map(g => [g.id, g]));
  if (!pg.length) return { ok: true, reason: 'prod empty' };
  let covered = 0, agree = 0;
  for (const g of pg) {
    const w = mg.get(g.id);
    if (!w) continue;
    covered++;
    if (!!w.completed === !!g.completed) agree++;
  }
  const cov = covered / pg.length;
  return { ok: cov >= 0.9 && (covered === 0 || agree / covered >= 0.9),
    coverage: +cov.toFixed(3), completed_agree: covered ? +(agree / covered).toFixed(3) : null, games: pg.length };
}

function extrasParity(mine, prod) {
  const ps = prod.sports || {}, ms = (mine || {}).sports || {};
  const sports = Object.keys(ps).filter(s => Array.isArray(ps[s]));
  if (!sports.length) return { ok: true, reason: 'prod empty/errored' };
  let okN = 0; const detail = {};
  for (const s of sports) {
    const pn = ps[s].length, mn = Array.isArray(ms[s]) ? ms[s].length : -1;
    const inBand = mn >= 0 && (pn === 0 || (mn >= 0.5 * pn - 3 && mn <= 2 * pn + 3));
    if (inBand) okN++;
    detail[s] = { prod: pn, worker: mn, in_band: inBand };
  }
  return { ok: okN === sports.length, sports: detail };
}

function oddsParity(mine, prod) {
  // st rows are the identity-bearing artifact (provider_event_id); h2h/props ride the same pulls
  const prows = Array.isArray(prod) ? prod : [];
  const mrows = new Map((Array.isArray(mine) ? mine : []).map(r => [r.provider_event_id, r]));
  if (!prows.length) return { ok: true, reason: 'prod empty' };
  let covered = 0, compared = 0, close = 0;
  for (const p of prows) {
    const w = mrows.get(p.provider_event_id);
    if (!w) continue;
    covered++;
    for (const bk of ['fanduel', 'draftkings']) {
      const pb = (p.books || {})[bk], wb = (w.books || {})[bk];
      if (!pb || !wb || pb.total_pts == null || wb.total_pts == null) continue;
      compared++;
      if (Math.abs(pb.total_pts - wb.total_pts) <= 1) close++;
    }
  }
  const cov = covered / prows.length;
  return { ok: cov >= 0.9 && (compared === 0 || close / compared >= 0.8),
    coverage: +cov.toFixed(3), total_close: compared ? +(close / compared).toFixed(3) : null, events: prows.length };
}

const SUMMARY_LANES = ['news', 'kalshi_quotes', 'futures', 'futures_kalshi', 'live_games',
  'wooder_td', 'futures_quotes', 'official_video', 'rec_yards', 'nfl_scores', 'extras', 'odds'];

// generic wiring for one ported lane: skip silently while the lane is dormant/skipped AND has
// never written (soak clock starts at the first real artifact); red once it claims to run.
async function portedLane(env, report, lane, r2key, prodPath, laneRes, cmp) {
  try {
    let mine = null;
    try { const o = await env.FEEDS.get(r2key); if (o) mine = JSON.parse(await o.text()); } catch (e) {}
    if (!mine) {
      if (laneRes && (laneRes.dormant || laneRes.skipped || laneRes.refused)) return; // not soaking yet
      report.lanes[lane] = { ok: false, reason: 'no worker artifact' };
      return;
    }
    let prod;
    try { prod = await getJson(env.PROD_BASE + prodPath + '?cb=' + Date.now()); }
    catch (e) { report.lanes[lane] = { ok: false, reason: 'prod unreadable' }; return; }
    report.lanes[lane] = cmp(mine, prod);
  } catch (e) { report.lanes[lane] = { ok: false, reason: String(e).slice(0, 80) }; }
}

export async function runParity(env, justRan, laneResults) {
  const report = { ts: new Date().toISOString(), lanes: {} };
  const now = Date.now();
  const lr = laneResults || {};
  // rolling state loaded up front: the news gate ctx derives from it
  let hist = [];
  try { const o = await env.FEEDS.get('parity/history.json'); if (o) hist = JSON.parse(await o.text()); } catch (e) {}
  let volSeries = [];
  try { const o = await env.FEEDS.get('parity/volume_series.json'); if (o) volSeries = JSON.parse(await o.text()); } catch (e) {}
  try {
    if (justRan.news) {
      const o = await env.FEEDS.get('slates/news.json'); const mine = o ? JSON.parse(await o.text()) : null;
      let newsReads = null; try { const ro = await env.FEEDS.get('slates/news_reads.json'); if (ro) newsReads = JSON.parse(await ro.text()); } catch (e) {}
      const prod = await getJson(env.PROD_BASE + '/slates/news.json?cb=' + now);
      if (mine) {
        // gate ctx: 1h of recalls (outage guard), rolling per-source + total baselines (7d series)
        const h1 = now - 3600000;
        const recentRecalls = hist.filter(r => Date.parse(r.ts) >= h1 && r.lanes && r.lanes.news && r.lanes.news.recall != null)
          .map(r => r.lanes.news.recall);
        const d7 = now - 7 * 24 * 3600000;
        const vs = volSeries.filter(r => Date.parse(r.ts) >= d7);
        const mixBaseline = {}, med = arr => median(arr.sort((x, y) => x - y));
        if (vs.length >= 12) {
          for (const src of ['ESPN', 'YAHOO', 'CBS']) {
            const vals = vs.map(r => (r.mix || {})[src]).filter(n => n != null);
            if (vals.length >= 12) mixBaseline[src] = med(vals);
          }
          const tots = vs.map(r => r.total).filter(n => n != null);
          if (tots.length >= 12) var totalBaseline = med(tots);
        }
        report.lanes.news = newsGate(mine, prod, { reads: newsReads, recentRecalls, mixBaseline, totalBaseline: typeof totalBaseline !== 'undefined' ? totalBaseline : null }, now);
        volSeries.push({ ts: report.ts, total: report.lanes.news.worker_total, mix: report.lanes.news.worker_mix });
        volSeries = volSeries.filter(r => Date.parse(r.ts) >= d7).slice(-2200);
      } else report.lanes.news = { ok: false, reason: 'no worker artifact' };
    }
    if (justRan.kalshi) {
      const o = await env.FEEDS.get('slates/nfl_kalshi_quotes.json'); const mine = o ? JSON.parse(await o.text()) : null;
      const prod = await getJson(env.PROD_BASE + '/slates/nfl_kalshi_quotes.json?cb=' + now);
      if (!mine && !Object.keys(prod.quotes || {}).length) report.lanes.kalshi_quotes = { ok: true, reason: 'both dormant' };
      else report.lanes.kalshi_quotes = mine ? quotesParity(mine, prod) : { ok: false, reason: 'no worker artifact' };
    }
    if (justRan.futures) {
      const o = await env.FEEDS.get('futures/current.json'); const mine = o ? JSON.parse(await o.text()) : null;
      let prodRows = {}; const lastTick = {};
      try {
        const txt = await (await fetch(env.PROD_BASE + '/data/futures_ws_ticks.jsonl?cb=' + now)).text();
        const lines = txt.trim().split('\n').filter(Boolean);
        // prod rows are incremental (changed keys only) - replay to reconstruct current state
        for (const ln of lines.slice(-3000)) {
          const r = JSON.parse(ln);
          const rt = Date.parse(r.ts);
          if (!isNaN(rt)) for (const k of Object.keys(r.board || {})) lastTick[r.league + k] = rt;
          if (!prodRows[r.league]) prodRows[r.league] = { board: {} };
          Object.assign(prodRows[r.league].board, r.board || {});
        }
      } catch (e) { report.lanes.futures = { ok: false, reason: 'prod ticks unreadable' }; }
      if (!report.lanes.futures) {
        let quality = null;
        try { const qo = await env.FEEDS.get('futures/quality.json'); if (qo) quality = JSON.parse(await qo.text()); } catch (e) {}
        report.lanes.futures = mine ? futuresParity(mine, prodRows, quality, lastTick, now) : { ok: false, reason: 'no worker artifact' };
      }
      // v13 audit store: full exempt lists per cycle (R2) + running per-key summary
      try {
        const fl = report.lanes.futures; const full = fl && fl._exempt_full; if (fl) delete fl._exempt_full;
        if (fl && 'exempt_stale_n' in fl) {
          let sum = { since: report.ts, rules: { stale_min: STALE_PROD_MIN, offbook_min_age_min: OFFBOOK_MIN_AGE_MIN, note: 'v11 stale>60min; v12 off-book (prod outside live bid/ask, tick>15min, worker inside book)' }, cycles: 0, cycles_with_exempt: 0, keys: {}, cycle_counts: [] };
          try { const so = await env.FEEDS.get('parity/exempt_summary.json'); if (so) sum = JSON.parse(await so.text()); } catch (e) {}
          sum.cycles++; sum.updated = report.ts;
          const nS = fl.exempt_stale_n, nB = fl.exempt_offbook_n;
          if (nS || nB) sum.cycles_with_exempt++;
          const nI = fl.exempt_inbook_n || 0; if (nI) sum.cycles_with_inbook = (sum.cycles_with_inbook || 0) + 1; sum.rules.v16 = sum.rules.v16 || 'v16 in-book stale-prod exemption: worker in [bid,ask], prod tick >15min, gap >2c; no book = no exemption'; sum.rules.v16_since = sum.rules.v16_since || report.ts;
          const nM = fl.mismatch_n || 0; if (nM) sum.cycles_with_mismatch = (sum.cycles_with_mismatch || 0) + 1;
          sum.cycle_counts.push([report.ts, nS, nB, fl.price_close, nM, nI, fl.price_close_v15rule]);
          if (sum.cycle_counts.length > 800) sum.cycle_counts = sum.cycle_counts.slice(-800);
          for (const e of (full && full.stale) || []) { const k = sum.keys[e.key] = sum.keys[e.key] || { stale_cycles: 0, offbook_cycles: 0 }; k.stale_cycles++; k.last_prod_tick = e.last_prod_tick; k.max_stale_age_min = Math.max(k.max_stale_age_min || 0, e.age_min || 0); k.last_seen = report.ts; }
          for (const e of (full && full.offbook) || []) { const k = sum.keys[e.key] = sum.keys[e.key] || { stale_cycles: 0, offbook_cycles: 0 }; k.offbook_cycles++; k.last_offbook = { prod: e.prod, worker: e.worker, bid: e.bid, ask: e.ask, last_prod_tick: e.last_prod_tick, ts: report.ts }; k.last_seen = report.ts; }
          for (const e of (full && full.inbook) || []) { const k = sum.keys[e.key] = sum.keys[e.key] || { stale_cycles: 0, offbook_cycles: 0 }; k.inbook_cycles = (k.inbook_cycles || 0) + 1; k.last_inbook = { prod: e.prod, worker: e.worker, bid: e.bid, ask: e.ask, last_prod_tick: e.last_prod_tick, ts: report.ts }; k.last_seen = report.ts; }
          for (const e of (full && full.mismatch) || []) { const k = sum.keys[e.key] = sum.keys[e.key] || { stale_cycles: 0, offbook_cycles: 0 }; k.mismatch_cycles = (k.mismatch_cycles || 0) + 1; k.max_gap = Math.max(k.max_gap || 0, e.gap); k.last_mismatch = { prod: e.prod, worker: e.worker, bid: e.bid, ask: e.ask, prod_tick_age_min: e.prod_tick_age_min, ts: report.ts }; k.last_seen = report.ts; }
          const puts = [env.FEEDS.put('parity/exempt_summary.json', JSON.stringify(sum))];
          if (nS || nB || nM || nI) puts.push(env.FEEDS.put('parity/exempt/' + report.ts + '.json', JSON.stringify({ ts: report.ts, price_close: fl.price_close, stale: full.stale, offbook: full.offbook, inbook: full.inbook, mismatch: full.mismatch })));
          await Promise.all(puts);
        }
      } catch (e) { console.error('exempt audit store error:', String(e).slice(0, 100)); }
      // v15 retention (main 10/1 3:29 PM PT): prune per-cycle audit files older than 7 days. Keys are
      // ISO-timestamped so list order is chronological; stop at the first file inside the window.
      // Once an hour, at most 100 deletes. exempt_summary.json and the parity/ prefix are never touched.
      try {
        if (new Date(report.ts).getUTCMinutes() < 2) {
          const cutoff = new Date(Date.parse(report.ts) - EXEMPT_RETAIN_DAYS * 86400000).toISOString();
          const lst = await env.FEEDS.list({ prefix: 'parity/exempt/', limit: 100 });
          const old = [];
          for (const o of lst.objects || []) { const t = o.key.slice('parity/exempt/'.length, -'.json'.length); if (t < cutoff) old.push(o.key); else break; }
          if (old.length) await env.FEEDS.delete(old);
        }
      } catch (e) { console.error('exempt prune error:', String(e).slice(0, 100)); }
    }
    // futures-switch gate visibility: the Kalshi leg gets its own tracked lane so its 24h
    // window is measurable (the futures SWITCH requires it ok, prompt 2026-10-14 step 6)
    if (report.lanes.futures && report.lanes.futures.kalshi_leg) {
      const k = report.lanes.futures.kalshi_leg;
      report.lanes.futures_kalshi = { ok: !!k.ok, coverage: k.coverage, price_close: k.price_close, reason: k.reason };
    }
    // ported shadow lanes (2026-10-14)
    if (justRan.live_games) await portedLane(env, report, 'live_games', 'slates/live_games.json', '/slates/live_games.json', lr.live_games, (m, p) => liveGamesParity(m, p, now));
    if (justRan.wooder_td) await portedLane(env, report, 'wooder_td', 'slates/nfl_live.json', '/slates/nfl_live.json', lr.wooder_td, (m, p) => wooderTdParity(m, p));
    if (justRan.futures_quotes) await portedLane(env, report, 'futures_quotes', 'futures/futures_quotes.json', '/futures.json', lr.futures_quotes, (m, p) => futuresQuotesParity(m, p, now));
    if (justRan.official_video) await portedLane(env, report, 'official_video', 'slates/official_video.json', '/slates/official_video.json', lr.official_video, (m, p) => officialVideoParity(m, p));
    if (justRan.rec_yards) await portedLane(env, report, 'rec_yards', 'slates/nfl_rec_yards.json', '/slates/nfl_rec_yards.json', lr.rec_yards, (m, p) => recYardsParity(m, p, now));
    if (justRan.nfl_scores) await portedLane(env, report, 'nfl_scores', 'nfl_scores.json', '/nfl_scores.json', lr.nfl_scores, (m, p) => nflScoresParity(m, p));
    if (justRan.extras) await portedLane(env, report, 'extras', 'extras_books.json', '/extras_books.json', lr.extras, (m, p) => extrasParity(m, p));
    if (justRan.odds) await portedLane(env, report, 'odds', 'slates/odds_prefill_st.json', '/slates/odds_prefill_st.json', lr.odds, (m, p) => oddsParity(m, p));
  } catch (e) { report.error = String(e).slice(0, 120); }
  // per-lane soak clocks: first cycle a lane ever reported = the exact timestamp its 24h soak started
  let since = {};
  try { const o = await env.FEEDS.get('parity/lanes_since.json'); if (o) since = JSON.parse(await o.text()); } catch (e) {}
  let sinceChanged = false;
  for (const lane of Object.keys(report.lanes)) if (!since[lane]) { since[lane] = report.ts; sinceChanged = true; }
  // rolling 24h window
  hist.push(report);
  const cutoff = now - 24 * 3600 * 1000;
  hist = hist.filter(r => Date.parse(r.ts) >= cutoff).slice(-2000);
  const summary = { ts: report.ts, window_cycles: hist.length, lanes: {}, soak_started: since };
  for (const lane of SUMMARY_LANES) {
    const runs = hist.map(h => h.lanes && h.lanes[lane]).filter(Boolean);
    if (!runs.length) { summary.lanes[lane] = null; continue; }
    const okN = runs.filter(r => r.ok).length;
    summary.lanes[lane] = { cycles: runs.length, in_parity: okN, pct: +(100 * okN / runs.length).toFixed(1), gate_95: okN / runs.length >= 0.95 };
  }
  const puts = [
    env.FEEDS.put('parity/history.json', JSON.stringify(hist)),
    env.FEEDS.put('parity/volume_series.json', JSON.stringify(volSeries)),
    env.FEEDS.put('parity/latest.json', JSON.stringify({ report, summary }, null, 1), { httpMetadata: { contentType: 'application/json' } }),
  ];
  if (sinceChanged) puts.push(env.FEEDS.put('parity/lanes_since.json', JSON.stringify(since, null, 1), { httpMetadata: { contentType: 'application/json' } }));
  await Promise.all(puts);
  return summary;
}
