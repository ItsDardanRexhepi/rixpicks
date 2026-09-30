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
BASE=$(git rev-parse HEAD)
for i in 1 2 3 4 5; do
  if git push; then exit 0; fi
  git pull --rebase -X theirs || { git rebase --abort; continue; }
  MOVED=""
  for f in $LANE_FILES; do
    UP=$(git rev-parse -q --verify "origin/main:$f" 2>/dev/null || true)
    WAS=$(git rev-parse -q --verify "$BASE:$f" 2>/dev/null || true)
    [ "$UP" != "$WAS" ] && MOVED="$MOVED $f"
  done
  OF=$(git show --pretty='' --name-only ORIG_HEAD)
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
