#!/bin/bash
# Bite-proof fixture for K22 (Sep 30 live race, run 36730127672): the refresh push loop
# raced a lane card push; the rebase guard fired but the on-failure incident hook pushed
# the Frankenstein HEAD (today's header + yesterday's settled picks) to origin.
# This fixture runs the REAL scripts/push_with_guard.sh against a REAL git race in a
# scratch repo and asserts: (1) loud failure, (2) HEAD reset to the upstream card commit,
# (3) the card manifest in the worktree is byte-identical to the lane's push - no merge.
# Pass a script path as $1 to test a legacy loop (bite-proof).
set -u
SCRIPT_UNDER_TEST=$(readlink -f "${1:-scripts/push_with_guard.sh}")
SCRATCH=$(mktemp -d)
trap 'rm -rf "$SCRATCH"' EXIT
cd "$SCRATCH" || exit 2
git init -q --bare origin.git
git init -q runner && git init -q lane
for d in runner lane; do (cd $d && git config user.email t@t && git config user.name t && git config init.defaultBranch main 2>/dev/null; git checkout -q -b main 2>/dev/null || true); done
# base commit: yesterday's 5-pick manifest
printf 'picks: [Leafs, Bruins, Abushaar, Braves, Yordan]\nprice: 100\n' > runner/manifest.json
(cd runner && git add -A && git commit -qm 'base: yesterday card' && git remote add origin ../origin.git && git push -q -u origin main)
(cd lane && git remote add origin ../origin.git && git pull -q origin main)
# runner does slow generated work (price update) WITHOUT the lane's card push
printf 'picks: [Leafs, Bruins, Abushaar, Braves, Yordan]\nprice: 108\n' > runner/manifest.json
(cd runner && git add -A && git commit -qm 'refresh: regenerated prices')
# lane lands the card push mid-run (today's 1-pick manifest)
printf 'picks: [WhiteSox]\n' > lane/manifest.json
(cd lane && git add -A && git commit -qm 'lane: Sep 30 card' && git push -q origin main)
# runner hits the race
cd runner || exit 2
bash "$SCRIPT_UNDER_TEST" >/dev/null 2>&1
RC=$?
FAIL=0
[ $RC -eq 1 ] || { echo "FAIL: expected loud exit 1, got $RC"; FAIL=1; }
TIP=$(git -C ../origin.git rev-parse main)
[ "$(git rev-parse HEAD)" = "$TIP" ] || { echo 'FAIL: HEAD not reset to origin/main tip'; FAIL=1; }
[ "$(cat manifest.json)" = "picks: [WhiteSox]" ] || { echo 'FAIL: worktree manifest is not the lane card (Frankenstein risk):'" $(cat manifest.json)"; FAIL=1; }
# control: a push with NO race must succeed
printf 'picks: [WhiteSox]\nprice: 110\n' > manifest.json
git add -A && git commit -qm 'refresh: clean regen'
OUT=$(bash "$SCRIPT_UNDER_TEST" 2>&1) || { echo "FAIL: clean push should succeed: $OUT"; FAIL=1; }
[ "$(git -C ../origin.git show main:manifest.json)" = "picks: [WhiteSox]"$'\n'"price: 110" ] || { echo 'FAIL: clean push content mismatch'; FAIL=1; }
# case (Sep 30 runs 36747004985/36747211413): the run's OWN commit changes manifest.json
# (odds moved) while upstream lands a non-lane tick - the guard must NOT misfire.
printf 'picks: [WhiteSox]\nprice: 112\n' > manifest.json
git add -A && git commit -qm 'refresh: regenerated prices (own manifest change)'
(cd ../lane && git pull -q origin main && printf 'tick %s\n' "$(date +%s)" > futures_tick.txt && git add -A && git commit -qm 'tick: futures only' && git push -q origin main)
OUT=$(bash "$SCRIPT_UNDER_TEST" 2>&1) || { echo "FAIL: own-manifest-change + non-lane tick misfired loud: $OUT"; FAIL=1; }
[ "$(git -C ../origin.git show main:manifest.json)" = "picks: [WhiteSox]"$'\n'"price: 112" ] || { echo 'FAIL: origin manifest lost the regenerated prices'; FAIL=1; }
[ -f ../lane/futures_tick.txt ] || { echo 'FAIL: lane tick vanished'; FAIL=1; }
if [ $FAIL -eq 0 ]; then echo 'PASS push race guard (loud fail + reset + clean-push control + own-manifest misfire case)'; exit 0; else exit 1; fi
