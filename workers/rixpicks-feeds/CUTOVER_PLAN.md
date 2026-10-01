# Lane 3 - Cloudflare Migration Cutover Plan (feed pipeline -> Workers, repo retirement)

Status: PROPOSED, pre-cutover. Nothing in this document has executed against production.
Gate: main relays owner sign-off before any step marked [CUTOVER] or [USER-VISIBLE].

## 0. Current state (verified 2026-09-28 20:10 PT)

- rix-picks.com apex -> GitHub Pages IPs (185.199.108-111.x), `server: GitHub.com`. DNS zone on Cloudflare, apex records grey-cloud.
- api.rix-picks.com -> Cloudflare (172.67.x/104.21.x), `rixpicks-api` worker live (users/logins/wagers).
- rix-picks.pages.dev mirror live, deployed in parallel by cf-pages-deploy on every push.
- Feed producers run as GitHub Actions on hosted cron + `external-tick` repository_dispatch
  from the `rixpicks-gh-dispatcher` CF worker (15-min). Hosted cron starves (x-feed: 0/40
  schedule fires; odds-refresh slipped 56 min on 9/28). external-tick is the builder's
  mitigation; this lane is the root kill.
- futures-ws-listener: 340-min self-respawning GHA runner, git-pushes every 75s
  (~1150 commits/day of `futures ws ticks`) — the repo's dominant churn class.
- Existing CF infra: KV rixpicks-kb + rixpicks-loop-state, queue rixpicks-wake-fanout,
  R2 ultrix-archive + rixpicks-spine-archive, workers ultrix-core / ultrix-intake /
  rixpicks-api / rixpicks-gh-dispatcher. Repo secrets CLOUDFLARE_API_TOKEN +
  CLOUDFLARE_ACCOUNT_ID already power cf-* workflows.

## 1. What ships in the worker (built, smoke-tested live 2026-09-29 03:11 UTC)

`workers/rixpicks-feeds/` — one Worker, three lanes + parity harness:

| lane | port of | cadence (CF cron) | artifact (R2 `rixpicks-feeds`) | live smoke result |
|---|---|---|---|---|
| news | scripts/news_feed.py (all ESPN API/RSS, CBS, Yahoo lanes; cross-sport guard; promo deny; interleave; og-enrich; weserv rewrite; image HEAD validation) | */5 min | slates/news.json, slates/news_images.json, slates/img_check.json | 15 buckets, 40 latest, 22.8s end-to-end |
| kalshi-quotes | scripts/kalshi_quotes.py (reads prod nfl_chips.json, fail-closed) | */5 min | slates/nfl_kalshi_quotes.json | correctly dormant (no active slate) |
| futures | futures_ws_listener.py discovery+tick shape, poll-based (Poly gamma + Kalshi public REST, no secrets) | */2 min | futures/current.json, futures/ticks/YYYY-MM-DD/HHMM.jsonl, futures/heartbeat.json | 14 leagues, 407 board keys, 1.4s |

Parity harness runs every cycle and keeps a rolling 24h window in R2 parity/history.json +
parity/latest.json. Serving: workers.dev `/feeds/*`, `/health`, `/parity/latest.json`
(CORS *, no-store). Zero new secrets required for shadow (all lanes read public APIs).

Deliberately NOT in worker v1 (phasing, section 4): x_feed chain, odds-refresh, settles.

## 2. Phases

### Phase A - SHADOW (starts on merge+deploy of this patch; nothing user-visible)
- Worker deployed by cf-feeds-deploy CI (wrangler; repo secrets already present).
- GHA producers untouched; they remain the production writers. Worker writes R2 only.
- Parity accumulates per cycle. Gates for cutover (24h window):
  - news: top-15 link-set overlap >= 80% vs prod in >= 95% of cycles
  - kalshi-quotes: ticker coverage >= 95%, |yes_bid diff| <= 2c in >= 95% of compared cycles
  - futures: board-key coverage >= 95% of prod union, |price diff| <= 2c in >= 95%
- Rollback of phase A: disable the worker cron (one wrangler call). Nothing to restore.

### Phase B - ROLLBACK DRILL (pre-cutover proof, still nothing user-visible)
1. Build a preview site artifact with feed base URL pointed at the worker (pages.dev preview).
2. Verify the client renders from worker feeds (news carousel, chips, futures board).
3. Revert the pointer; verify the client renders from the GH pipeline again.
4. Document timings + evidence in the retirement checklist. This is the proven rollback path:
   cutover is one revertible pointer flip; the GH pipeline stays intact and re-armable
   (one commit) throughout the soak.

### Phase C - CUTOVER [CUTOVER] [USER-VISIBLE] — per-lane, only after 24h parity + drill + relay
Per lane, in order kalshi-quotes -> news -> futures (least to most coupled):
1. Site feed base pointer flips from `/slates/<file>` to the worker endpoint for that lane
   (builder lands the one-line site change; Pages deploys it).
2. Corresponding GHA producer disabled by removing its schedule/dispatch triggers
   (workflow file stays in-repo, inert, one revert commit to re-arm).
3. news cutover also flips XFEED_DISPATCH=on: the worker fires `x-feed-chain`
   repository_dispatch on rotation so the X/NIM chain keeps its news-driven trigger.
   Requires worker secret GH_DISPATCH_TOKEN (the dispatcher PAT) set on rixpicks-feeds.
4. futures cutover requires the analysis-side reader (futures_247.py) repointed from
   repo `data/futures_ws_ticks.jsonl` to the worker (R2/API). Interim: hourly compacted
   repo batch from the worker (contents API) keeps the file shape unchanged.
5. Soak 24h per lane before the next flips.

### Phase D - REPO RETIREMENT [USER-VISIBLE] (owner already approved deleting ONLY this repo
once hosting is verified on Cloudflare; final go still via main relay)
Preconditions (the retirement checklist, section 5) all green, then:
1. Archive: full git mirror + issues/PR export to R2 rixpicks-spine-archive and a private repo.
2. Apex flip: rix-picks.com A/AAAA records -> CF Pages (orange-cloud), GH Pages stays
   reachable as fallback origin for 48h; itsdardanrexhepi.github.io/rixpicks redirect
   re-homed (Pages redirect rule) before deletion.
3. Delete the public repo. RixPicksSystem, ultrix, and all other repos untouched.

## 3. Blast radius

| surface | what changes | who/what can break | mitigation |
|---|---|---|---|
| Workers account | +1 worker, +1 R2 bucket | nothing existing; new names, no shared bindings | shadow phase proves isolation |
| rix-picks.com visitors | phase C: feed JSON served from worker instead of Pages | stale/empty carousels, chips, futures board if worker or R2 fails | per-lane flip, 24h parity gate, drill-proven one-commit revert; GHA producers re-armable |
| x_feed chain (X API burn ~$3/day + NIM) | trigger moves from workflow_run(news-refresh) to worker dispatch | double-burn if both triggers live; missed pulls if dispatch secret absent | XFEED_DISPATCH gate; GHA news-refresh disabled in the same commit the dispatch turns on |
| futures analysis-side (futures_247.py, private) | ticks source moves repo -> worker | analysis reads stale/missing ticks | interim hourly repo batch keeps shape; builder confirms the read path before the flip |
| odds-refresh / site build | unchanged in v1 | none | stays GHA on external-tick; port is phase 4 work |
| api.rix-picks.com, OneSignal, bets@ email, GoatCounter, login/wager backend | untouched | none | no shared code paths; not in lane |
| CF costs | worker crons: */2 + */5 = ~1.2k invocations/day; R2 storage GBs | plan limits | Workers cron+subrequest budget needs the paid plan (news lane ~190 subrequests/cycle vs 50 free) - verify plan tier before deploy; shard news per league-group as fallback |
| The Odds API 20K credits/mo | unchanged | none | odds-refresh not in worker v1 |
| GitHub repo | +workers/ dir, +1 workflow; at phase D the repo is deleted | external readers of raw files (config_leagues.json, slates/*, data/*) | retirement checklist inventories every reader and repoints first; archive before deletion |

## 4. Not in worker v1 - phasing for the remaining GH-cron classes

- x_feed chain (x_feed.py 293 + news_social.py 419 + soc_match.py + NIM verdicts): X burn
  discipline + NIM matching. NIM already fronts through ultrix-core. Port = phase 2 worker
  lane after shadow proves the pattern; until then it runs off worker dispatch (phase C3).
- odds-refresh (refresh.sh -> odds_prefill*, futures_quotes, wooder_td_feed, live_games,
  build_gh_page_v2 full site rebuild): feed pull is coupled to the site build. Splitting
  feed-from-build is lanes 1/2 site-build territory; until then it stays GHA on
  external-tick (starvation already mitigated by the dispatcher).
- settles / record-final: analysis-side graded writes; stays GHA workflow_dispatch/push
  triggered (not a cron class). Retires with the repo only after its chain moves to
  RixPicksSystem — retirement checklist item, builder owns the move.
- Every other workflow (nfl-scores, wooder-td, official-video, extras-sweep, predictions,
  publish-card, card-chain, watchdog, incident-hook): enumerated in the checklist with an
  owner and a destination (worker lane / RixPicksSystem GHA / retire-with-repo) before
  phase D.

## 5. Repo retirement checklist (all must be green before deletion)

1. [ ] 24h parity gates green per lane (parity/latest.json summary)
2. [ ] Rollback drill documented (phase B evidence)
3. [ ] All three feed lanes cut over and soaked 24h each
4. [ ] x_feed chain running off worker dispatch (or ported), X burn nominal
5. [ ] futures analysis-side reader confirmed repointed (builder sign-off)
6. [ ] Site hosting: CF Pages serving rix-picks.com apex for 48h, GH Pages fallback verified
7. [ ] github.io/rixpicks redirect re-homed and verified
8. [ ] Every remaining workflow has an owner + destination; none still required from this repo
9. [ ] External raw-file readers inventoried and repointed (builder + analysis-side sweep)
10. [ ] Full archive (git mirror + issues/PRs) in R2 + private repo, restore-tested
11. [ ] Owner's final go relayed by main (his approval covers deleting THIS repo only)
12. [ ] Delete repo; verify site + feeds + api unaffected for 24h post-deletion

### Futures gate: prod-staleness exemption (main decision 9/30 15:22 PT)
Prod's futures_ws_ticks.jsonl is changed-keys-only. A Poly key whose last prod tick is older
than 60 min is excluded from the price comparison (coverage still counts) and recorded in the
futures report as `exempt_stale: [{key, last_prod_tick, age_min}]`. Tolerance stays +/-2c;
NWSL-style wide-spread (>25c) exclusion unchanged. Acceptance summary must list every exempted
key with last prod tick and excluded minutes. Evidence: Bell (NASCAR) prod 12.7c last tick
20:34:11Z vs worker 9.9c vs Gamma mid ~10.2c. Applies from deploy forward; earlier history
entries carry no per-key detail and are scored as recorded.

### Futures gate: off-market-reference exemption v12 (main decision 9/30 4:37 PM PT)
Not a tolerance change (still +/-2c). A Poly key is excluded from the PRICE comparison (coverage
still counts) only when ALL hold: (1) prod value is outside the live [bid, ask] book of the same
market from the worker's latest poll; (2) the key's last prod tick is older than 15 min; (3) the
worker value is inside the live book (or within 0.1c of live mid). Worker also outside the book
= real divergence, counts against parity. Exempted keys are recorded per cycle in the futures
report as `exempt_offbook: [{key, prod, worker, bid, ask, last_prod_tick, age_min}]` and must all
be listed in the acceptance summary with this rule stated. Stacks with the v11 >60-min stale rule
(`exempt_stale`). Evidence: NASCAR Hamlin prod 36.0 vs ask 35, Elliott prod 5.7 vs ask 4.6.
Futures 24h clock keeps its 22:25:09Z 9/30 anchor unless main re-anchors at the v12 deploy.

### Futures gate audit store v13 (main decision 9/30 ~11:25 PM PT)
The report's `exempt_stale` / `exempt_offbook` lists are capped at 30 for history size; each cycle
also records `exempt_stale_n`, `exempt_offbook_n` and `exempt_stale_keys_hash` (FNV-1a of the sorted
full key set). The FULL per-cycle lists are written to R2 `parity/exempt/<ts>.json` (served at
`/parity/exempt/<ts>.json`) whenever any key is exempted, and `parity/exempt_summary.json`
(served at `/parity/exempt_summary.json`) keeps a running per-key table (stale_cycles,
offbook_cycles, last prod tick, last off-book prod/worker/bid/ask) plus per-cycle counts for the
last 800 cycles. History before the v13 deploy carries only the capped lists. The acceptance
summary must state the v11 and v12 rules, count exempted keys per cycle, and note that sparse
overnight prod ticks make the gate noisy (a data-sparsity artifact, not a parity regression).

### v14 diagnostic (main decision 10/1 1:27 PM PT, no rule or threshold change)
Each futures cycle also records `mismatch_n` and a capped-30 `mismatch` list: non-exempt compared Poly keys outside the 2c band (key, prod, worker, gap, live bid/ask, prod tick age). The full list is stored in `parity/exempt/<ts>.json` (field `mismatch`), and `parity/exempt_summary.json` gains per-key `mismatch_cycles`, `max_gap`, `last_mismatch`, plus `cycles_with_mismatch` and a 5th element in `cycle_counts`. Cycles before the v14 deploy carry no mismatch data.

### v15 retention (main decision 10/1 3:29 PM PT)
`parity/exempt/<ts>.json` files older than 7 days are pruned (hourly, max 100 deletes per run, oldest first). `parity/exempt_summary.json` and the `parity/` prefix are never touched. Nothing is deleted in the first 7 days after v13 deploy (9:28Z 10/1), so the acceptance evidence stays until at least 10/8.

### v16 futures in-book rule (Julian approval relayed via main 10/1 3:32 PM PT; NOT cutover acceptance)
A compared Poly key is exempt from the 2c band when ALL hold: the worker price is inside a verified live bid/ask for that key (book_c present, two finite numbers, bid <= ask), the prod tick is older than 15 min, and the gap is over 2c. No book quote or an unusable one means no exemption; a worker outside the book is still a miss. v11 stale, v12 off-book and the 0.95 gate are unchanged. Every exemption is listed: `exempt_v16_n` / capped-30 `exempt_v16` per cycle, the full list in `parity/exempt/<ts>.json` (`v16`), and `cycle_counts` gains a 6th element (v16 count) and a 7th (price_close under the pre-v16 rule). `exempt_summary.json` adds `cycles_with_v16`, per-key `v16_cycles` / `last_v16`, and `rules.v16`. Each cycle also records `price_close_old` and `ok_old`; the lane summary reports `in_parity_old_rule` / `pct_old_rule` beside `in_parity` / `pct`.
Prospective only: the 9/30 22:25Z to 10/1 22:25Z window (1006 cycles, 92.5% ok, 13 dips) stays on record untouched. The fresh 24h window starts at the v16 deploy and reports both numbers side by side.
