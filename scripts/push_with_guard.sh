#!/bin/bash
# Atomic push-with-guard for generated-content lanes (K22, Sep 30 live race, run 36730127672).
# Two publish holes closed here:
#  1) the on-failure incident hook PUSHES HEAD - every loud-fail path must reset HEAD to
#     origin/main first, or the hook publishes whatever merged/generated state sits in the
#     worktree (Sep 30: guard fired, hook pushed the Frankenstein manifest live anyway);
#  2) `git pull --rebase -X theirs` can resolve to EXACTLY the runner's stale content,
#     silently discarding a lane's mid-run card push with the old guard passing clean.
# Rule: if upstream moved a lane-shipped file (manifest.json class) after checkout, this
# run's regenerated content is stale by construction - reset + fail loud; next cycle
# regenerates from the new card. Fixture: scripts/test_push_race_guard.sh (real git race).
set -u
LANE_FILES="manifest.json"
# Readback after a successful push: origin/main must CONTAIN the pushed HEAD (ancestry), not
# equal it. The call sites' old `ls-remote | grep -q HEAD` demanded tip equality, so it went red
# whenever any bot committed between the push and the check (main moves about once a minute),
# and on every no-commit run once main had moved past the trigger commit (Oct 2 runs
# 36962855292 + 36962967323 nfl-scores-confirm). A push that origin did not keep still fails
# loud, and HEAD is reset first so the on-failure hook never publishes it.
readback() {
  for r in 1 2 3; do
    if git fetch -q origin main; then
      if git merge-base --is-ancestor HEAD FETCH_HEAD; then
        echo "PUSH READBACK OK: origin/main contains $(git rev-parse --short HEAD)"
        return 0
      fi
      echo "PUSH READBACK FAILED: origin/main does not contain HEAD $(git rev-parse --short HEAD) - reset to origin/main, fail loud" >&2
      git reset --hard origin/main
      return 1
    fi
    sleep 3
  done
  echo 'PUSH READBACK FAILED: origin/main could not be fetched - reset to origin/main, fail loud' >&2
  git reset --hard origin/main
  return 1
}
# BASE must be the checkout-time upstream, NOT HEAD: refresh.sh commits its own regenerated
# manifest.json before calling this script, so BASE=HEAD makes the lane-move check below
# compare origin vs the run's OWN commit and misfire on every run whose odds actually
# moved (Sep 30 runs 36747004985 + 36747211413: "race touched ... manifest.json" with no
# lane push upstream at all). merge-base(HEAD, origin/main) is the true checkout base.
BASE=$(git merge-base HEAD origin/main)
# Nothing of our own to publish (run found no changes): there is no content to protect or
# race. Without this, a no-commit run whose push is rejected because main moved fast-forwards,
# then the guard below compared the PREVIOUS commit's files (ORIG_HEAD) against upstream and
# failed loud on a harmless tick (Sep 30 runs 36813762832 + 36813810976, nfl-scores-confirm).
if [ "$(git rev-parse HEAD)" = "$BASE" ]; then
  echo "PUSH GUARD: no local commits to publish - nothing to do"
  exit 0
fi
for i in 1 2 3 4 5; do
  if git push; then readback; exit $?; fi
  # Re-derive the base for THIS attempt. After a first rebase our commits sit on top of the
  # upstream we already pulled; a base frozen at checkout time would count that upstream
  # content as "our files" on attempt 2 and fail loud on the next tick (Sep 30 odds-refresh
  # 36821687100: two ticks landed between three push attempts).
  BASE=$(git merge-base HEAD origin/main)
  git pull --rebase -X theirs || { git rebase --abort; continue; }
  MOVED=""
  for f in $LANE_FILES; do
    UP=$(git rev-parse -q --verify "origin/main:$f" 2>/dev/null || true)
    WAS=$(git rev-parse -q --verify "$BASE:$f" 2>/dev/null || true)
    [ "$UP" != "$WAS" ] && MOVED="$MOVED $f"
  done
  # files changed by THIS run's own commits only (checkout base..pre-rebase tip)
  OF=$(git diff --name-only "$BASE" ORIG_HEAD)
  if [ -n "$MOVED" ] || ! git diff --quiet ORIG_HEAD HEAD -- $OF; then
    echo "REBASE GUARD: race touched lane-shipped/generated content ($MOVED) - reset to origin/main, fail loud; next cycle regenerates" >&2
    git reset --hard origin/main
    exit 1
  fi
done
# attempts exhausted - never let the failure hook publish a stale/generated HEAD either
git reset --hard origin/main
echo 'PUSH GUARD: 5 attempts exhausted - reset to origin/main, fail loud' >&2
exit 1
