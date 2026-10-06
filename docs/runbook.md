# RixPicks runbook

Operator procedures for the record pipeline. Each section names the script, when to use it, and
what it will and will not do. Internal document: no page links here.

## Local grading fallback: `scripts/record_final_local.sh`

**When.** Graded finals sit in `record_request.json` and the `record-final` workflow
(`.github/workflows/record_final.yml`) did not apply them. Since 2026-10-06 03:55Z GitHub Actions
runs end in `startup_failure` before any step runs, so nothing gets graded. This script runs the
same steps on a Mac.

**What it runs.** The workflow's steps, in the workflow's order:

1. **Hold check.** `node scripts/health_gate.js --hold`. Exit 1 is a structural FAIL and exit 2 is
   a gate error. Either one HOLDS the run, so nothing is applied, built, committed or pushed.
   The script has **no bypass**. The workflow's `hold_bypass=repair` dispatch is not carried over,
   and no variable or flag skips the gate. A hold lifts when the gate passes. While the live site
   is down (repo private, GitHub Pages 404), the gate's served-site checks fail and the fallback
   holds by design. Bring the site back first.
2. **Apply.** `python3 scripts/record_final.py` checks each final against ESPN on its own and
   fails closed. If it refuses (exit 3), the run stops with that exit code and nothing is written.
3. **Changed gate.** The run continues only if `manifest.json`, `history.json`,
   `record_request.json` or `record_done.json` changed. Setting `FORCE_REBUILD=true` does the same
   as the workflow's `force_rebuild` input.
4. **Rebuild.** First `python3 scripts/build_history.py history.json`, then
   `RP_REFRESH=1 python3 scripts/_build_nocanon_v2.py manifest.json index.html`.
5. **Syntax sweep.** Runs `node --check` on every emitted `<script>` block of `index.html`.
6. **Commit.** Commits the workflow's exact file allowlist as the owner, Dardan Rexhepi. Any other
   tracked change fails loudly and names the file.
7. **Push.** `scripts/push_with_guard.sh`:
   - pushes, then retries up to 5 times with fetch and rebase;
   - fails loudly if another writer moved `manifest.json` mid-run;
   - confirms by reading back that `origin/main` contains the commit.

**Where it runs.** It fetches `origin main` and works in a fresh scratch git worktree of
`origin/main`, on a temporary branch that tracks it. That is the same clean checkout a runner
gets. Your own checkout, its branch and any uncommitted work are never touched. The scratch
worktree and temporary branch are removed on exit.

**How.**

```
DRY=1 bash scripts/record_final_local.sh   # steps 1-5 and what step 6 would commit; no commit, no push
bash scripts/record_final_local.sh         # real run: commits and pushes origin main
git pull                                    # then see the record write in your checkout
```

Requirements: `git` with push access to `origin`, `python3`, and `node` (for the gate and the sweep).

**Exit codes.**

| Code | Meaning |
|---|---|
| 0 | Written, nothing pending, or dry run done |
| 2 | Setup failed: not a checkout, fetch failed or worktree failed |
| 3 | `record_final.py` refused |
| 4 | HELD by the health gate |
| 1 | Any other failure: build, sweep, allowlist tripwire or push |

Fixture: `scripts/test_record_final_local.py`. It runs the real script and push guard against a
local bare origin, offline. It covers:

- the dry run;
- every hold, including a bypass attempt;
- a refusal;
- nothing pending and force rebuild;
- a broken script block and the allowlist tripwire;
- a real run;
- both push races.

It also checks that the script's gate files and allowlist still match the workflow's.

## Late-post disclosure on the record

Some picks are carded after their game began, by owner override. On the published card such a pick
carries `added_after_kickoff: true`. It also carries `added_after_final: true` when the game had
already ended at posting.

**`scripts/record_final.py`** copies both flags onto the pick's `history.json` row. A disclosure
on any published copy of the card is kept. Grading fails closed (exit 3, nothing written) when:

- a flag is not `true`/`false`;
- copies contradict each other;
- `added_after_final` appears without `added_after_kickoff`;
- the request states a different disclosure.

**Where it shows.**

- `record.html` and `yesterday.html` show "Added after the final" or "Added after kickoff" on the
  row. A malformed flag stops `build_history.py` before either page is written.
- The record page's live Today section (`scripts/record_today.js`) shows the same.
- The Home learnings panel shows its "added after kickoff" tag.

Fixtures: `scripts/test_late_disclosure.py` and `scripts/test_late_disclosure_today.js`.

**Rows graded before the rule: `scripts/record_disclosure.py`.** `record_final.py` copies the flags
only when it grades a pick, and it never grades a row twice. A row graded before the rule keeps no
flag on its own. This script brings such a row in line with its card:

```
python3 scripts/record_disclosure.py --check   # what would change; writes nothing
python3 scripts/record_disclosure.py           # adds the card's flags to the graded rows
```

Nothing is typed in. The flags come only from the published card, through `record_final.py`'s own
`card_rows` and `disclosure_of`. A row gets them only when:

- its grade key is in `record_done.json`;
- it is the one pick on its card date's `history.json` day with the card pick's name at the card
  price.

A disclosed pick that is not graded yet is listed as pending and left to `record_final.py`.

The script refuses (exit 3, nothing written) when:

- the card's copies are malformed or contradict each other;
- a row says `false`, carries a malformed flag, or claims a flag its card does not;
- a graded pick's row is missing or doubled;
- an MMA pick, or a pick with no grade key, carries a flag;
- an audit line is on file but its row lost the flags.

It only adds `true` flags. W-L, units, results, prices, names and scores never move, and
`history.json` keeps its stored format. Each row it changes gets one line in
`slates/record_disclosures.jsonl`. A re-run is a no-op.

**Applied once, Oct 6.** It carried both flags onto the three Oct 2 owner-override rows: Under 3.5,
Over 43.5 and Under 54.5. All three were carded after their finals, and both Oct 2 card copies
carry the flags. `record.html` shows "Added after the final" on those rows from the next
`build_history.py` run, which every record write does.

Fixture: `scripts/test_record_disclosure.py`. It also checks the real tree: every graded row
carries its card's disclosure, and `record.html` built from `history.json` labels the three Oct 2
rows.

## Soccer results: regulation time (`core/soccer_result.py`)

Kalshi's MLS and NWSL game, spread and total contracts settle after 90 minutes plus stoppage time.
Extra time and a penalty shootout never count. A level score after 90 minutes resolves the TIE
contract yes and both team contracts no. So:

- a moneyline (a team to win) that draws is **LOST** for either side, never a push;
- totals and spreads count regulation goals only.

ESPN's final includes extra-time goals, so no grader reads the regulation score off the final.
`regulation_score()` takes it from the match summary's period line scores and checks it two ways
before anyone grades on it:

- the periods add up to ESPN's final, and their count fits the final state (2 at full time,
  4 after extra time, 5 with a shootout);
- the regulation goals equal the goal events ESPN logs in periods 1-2 (own goals included,
  shootout kicks never).

Anything it cannot establish refuses. On Oct 6 it was checked against 331 finished MLS and NWSL
matches with no refusal. They were played from October to December 2025 and from July to
October 2026. 27 of them had own goals, 8 went to a shootout and 2 were decided in extra time.

**Where it applies.**

- **`scripts/record_final.py`.** For a `soccer/...` league it reads the ESPN summary, checks that
  its final equals the verified final, and grades on the regulation score. With no regulation
  score it refuses (exit 3, nothing written). When extra time changed the score, the row shows both:
  `GFC 2, KC 1 (90 min: GFC 1, KC 1)`.
- **`scripts/finals_watch.py`** grades the same way; a missing or contradicting summary stops the
  chain.
- **`scripts/predictions.py`** settles a soccer prediction as a miss when the match ends level at
  full time. Before, the draw stayed pending until the 36-hour void.

Every other league is unchanged: a level moneyline (an NFL tie) is still a push. Soccer scorer
props already counted periods 1-2 only.

Fixtures: `scripts/test_soccer_regulation.py`, plus the grading suite in `tests/run_tests.py`.
Both run on recorded ESPN summaries in `tests/fixtures/soccer/`.

## Instant grader on a Mac: `scripts/finals_watch.py`

It watches today's card and grades each final in commence order. Every final needs a second
source from another company before it is graded.

**Dry run by default.**

```
python3 scripts/finals_watch.py                                   # dry run: prints each grade, writes nothing
python3 scripts/finals_watch.py --requests-out /tmp/would.json    # also writes the requests a live run would queue
python3 scripts/finals_watch.py --live                            # production writes (refused today, see below)
```

A dry run never reads the record token. The `--requests-out` path must be outside the checkout
and outside `RPS_KB`.

**Settings.** Each comes from the environment, or from a JSON file named by `RIX_FINALS_CONFIG`
(`{"RPS_KB": ..., "RIX_REPO": ...}`); the environment wins.

| Setting | What |
|---|---|
| `RIX_REPO` | The checkout to read: `manifest.json`, `core/`, `record_request.json`. Default: the checkout the script is in. |
| `RPS_KB` | The private knowledge-base folder. Its `ledger/` holds `record_rows.jsonl` (the record ledger), `finals_seen.json`, `picks.jsonl`, `positions.jsonl` and `odds_credits.jsonl`. No default. |

Secrets are read from the environment variable of that name, or else from the login keychain item
whose service is that name. They are never printed.

- `RIX_RECORD_TOKEN` is the record POST token. Only a live run reads it.
- `THE_ODDS_API_KEY` is the-odds-api key. Without it, that source is skipped and no credit is
  logged.

**Second sources, in order.**

1. The CBS scoreboard. The NFL is read from the game's week page; every other league from the
   page for the game's Eastern date. Teams are matched by CBS's full team name, the card must
   read final, and its rows must be the game's away and home teams in that order.
2. theScore (WNBA).
3. MLB statsapi. It reads the game's own date, and the game must be scheduled within 6 hours of
   the card's start. The UTC date can hold the next day's rematch.
4. The repo's `nfl_scores.json`.
5. the-odds-api.

ESPN's own site API never counts as a second source.

NCAAB is keyed `basketball/mens-college-basketball`, the registry's ESPN path.

**Exit codes.**

| Code | Meaning |
|---|---|
| 0 | Done, live or dry |
| 1 | Fail closed: the record ledger is missing or its baseline row is wrong, or the `RIX_FINALS_CONFIG` file is unreadable |
| 2 | Bad options |
| 5 | `RPS_KB` not set |
| 6 | Stale manifest: the card is not today's or yesterday's |
| 7 | `--live` refused: the live chain is not wired in this checkout |

**What it still needs before it can grade here.**

- The record ledger `ledger/record_rows.jsonl` must exist. It must begin with the canonical
  baseline row, and the running record must continue from it. Without it a dry run stops with
  exit 1.
- `ledger/picks.jsonl` needs a card-entry row for each card pick. The one accepted entry in
  `core/accepted_entry.py` is the exception. A pick without a row is refused. A card that carried
  no exchange price, like the Oct 1 late-filed card, cannot be graded here.
- `--live` stays refused until `core/record_pipe.py` takes the relay parameters the live chain
  calls: `resume_pending(skip=)` and `on_final(no_post=)`.
- Nothing schedules it.

Fixture: `scripts/test_finals_watch_mac.py`. It runs offline on recorded data in
`tests/fixtures/finals_replay/` and covers:

- the settings, the keychain lookup and the dry-run default;
- every refusal;
- Oct 1 PIT@CLE Under 38.5: LOST, verified by CBS's week-4 page;
- the Oct 3 and Oct 4 Padres-Brewers finals: verified by statsapi;
- the Oct 5 card through `main()`: every grade field of the emitted requests equals the hand grade
  committed in 15d1b31af.

The Oct 5 run grades in commence order, Flyers before Penguins. So the running record after each
row swaps between the two rows, and the chain ends at the same 33-17, +14.81u.

## CLV ledger (internal): `scripts/clv_report.py`

```
python3 scripts/clv_report.py                       # all graded picks, plus queued grades (marked)
python3 scripts/clv_report.py --date 2026-10-05     # one card date
python3 scripts/clv_report.py --no-queued --out /tmp/clv.json
```

**What it computes.** For each graded pick:

1. Take the last book snapshot in git history from before the card commence and before the
   snapshot's own commence for the game. Moneylines come from `slates/odds_prefill.json`; spreads
   and totals from `slates/odds_prefill_st.json`. The snapshot must be at most 180 minutes old.
2. De-vig each book multiplicatively. Spreads use the HOME-basis line and the picked side's price.
3. Take the median across at least 3 books. That is `close_novig`.
4. `clv_c = close_novig*100 - locked_c`.

Locked cents come from the first of these that applies:

- the accepted entry's cents;
- the Kalshi cents, when they are the card price;
- the whole cents behind the card's American price;
- the implied cents.

**Output.** Writes only `slates/clv_ledger.json`, or the path given with `--out`. It never touches
`history.json`, `manifest.json`, `record_done.json` or `record_request.json`. Grading never calls
it. No page renders it.

Snapshots exist only as far back as the clone's history goes. In a shallow clone, earlier picks
list "no close" with the reason.

Fixture: `scripts/test_clv_report.py`.
