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
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
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
# case (Sep 30 runs 36813762832/36813810976): run made NO commit, upstream moved while it
# ran (a file the runner's last checkout commit also touched) - must exit 0, not fail loud.
(cd ../lane && git pull -q origin main && printf 'tick1 %s\n' "$(date +%s)" > futures_tick.txt && git add -A && git commit -qm 'tick: futures only 1' && git push -q origin main)
cd .. && git clone -q -b main origin.git runner2 && (cd runner2 && git config user.email t@t && git config user.name t) && cd runner2 || exit 2
(cd ../lane && git pull -q origin main && printf 'tick2 %s\n' "$(date +%s)" > futures_tick.txt && git add -A && git commit -qm 'tick: futures only 2' && git push -q origin main)
OUT=$(bash "$SCRIPT_UNDER_TEST" 2>&1); RC2=$?
[ $RC2 -eq 0 ] || { echo "FAIL: no-commit run misfired loud (rc=$RC2): $OUT"; FAIL=1; }
# case (Sep 30 odds-refresh 36821687100): two non-lane ticks land between three push attempts
# (a pre-push hook injects a real lane push before the first two attempts). The run's own commit
# must still land and both ticks must survive; no loud fail.
cd .. && git clone -q -b main origin.git runner3 && cd runner3 || exit 2
git config user.email t@t && git config user.name t
printf 'odds 1\n' > odds_file.txt && git add -A && git commit -qm 'refresh: own odds commit'
printf '0' > "$SCRATCH/hookcount"
cat > .git/hooks/pre-push <<HOOK
#!/bin/bash
n=\$(cat "$SCRATCH/hookcount"); n=\$((n+1)); printf '%s' "\$n" > "$SCRATCH/hookcount"
if [ "\$n" -le 2 ]; then
  (cd "$SCRATCH/lane" && git pull -q origin main && printf 'race tick %s\n' "\$n" >> futures_tick.txt && git add -A && git commit -qm "tick: race \$n" && git push -q origin main)
fi
exit 0
HOOK
chmod +x .git/hooks/pre-push
OUT=$(bash "$SCRIPT_UNDER_TEST" 2>&1); RC3=$?
[ $RC3 -eq 0 ] || { echo "FAIL: two-tick race failed loud (rc=$RC3): $(echo "$OUT" | tail -3)"; FAIL=1; }
[ "$(git -C ../origin.git show main:odds_file.txt 2>/dev/null)" = "odds 1" ] || { echo 'FAIL: own odds commit did not land'; FAIL=1; }
[ "$(git -C ../origin.git show main:futures_tick.txt | grep -c 'race tick')" = "2" ] || { echo 'FAIL: race ticks lost'; FAIL=1; }
# Call-site readback cases (Oct 2 nfl-scores-confirm runs 36962855292 + 36962967323): every
# workflow/script that runs the guard is executed the way it ships - the guard, then whatever
# readback line the call site runs right after it - against three real races:
#   A  no-commit run while main moved past the checkout      -> must pass
#   B  own push lands, a bot commits right after the push    -> must pass
#   C  own push "succeeds" but origin does not keep it       -> must fail loud, HEAD reset
# B and C are injected by a post-receive hook on the scratch origin (one shot per arm).
# PENDING: call sites owned outside the CI scripts that still carry the tip-equality readback;
# their A/B results are reported, not failed, until that line is dropped there too.
PENDING_SITES=""
cd "$SCRATCH" || exit 2
: > "$SCRATCH/pr_mode"
cat > origin.git/hooks/post-receive <<HOOK
#!/bin/bash
mode=\$(cat "$SCRATCH/pr_mode" 2>/dev/null); : > "$SCRATCH/pr_mode"
export GIT_AUTHOR_NAME=bot GIT_AUTHOR_EMAIL=bot@t GIT_COMMITTER_NAME=bot GIT_COMMITTER_EMAIL=bot@t
while read -r old new ref; do
  [ "\$ref" = refs/heads/main ] || continue
  case "\$mode" in
    tick) c=\$(echo 'bot tick right after the push' | git commit-tree "\$new^{tree}" -p "\$new") && git update-ref "\$ref" "\$c" "\$new" ;;
    drop) git update-ref "\$ref" "\$old" "\$new" ;;
  esac
done
exit 0
HOOK
chmod +x origin.git/hooks/post-receive
fresh_runner() {
  rm -rf "$SCRATCH/site_runner"
  git clone -q -b main "$SCRATCH/origin.git" "$SCRATCH/site_runner" && git -C "$SCRATCH/site_runner" config user.email t@t && git -C "$SCRATCH/site_runner" config user.name t
}
lane_tick() { (cd "$SCRATCH/lane" && git pull -q origin main && printf 'site tick %s\n' "$1" >> futures_tick.txt && git add -A && git commit -qm "tick: $1" && git push -q origin main); }
# runs the call site's shipped sequence in site_runner: the guard, then its post-guard readback line
run_site() {
  (cd "$SCRATCH/site_runner" && bash "$SCRIPT_UNDER_TEST" >/dev/null 2>&1 && { [ -z "$1" ] || bash -c "$1" >/dev/null 2>&1; })
}
SITES=$(cd "$REPO_ROOT" && grep -l 'bash scripts/push_with_guard.sh' .github/workflows/*.yml scripts/*.sh 2>/dev/null | grep -v '/test_')
[ -n "$SITES" ] || { echo 'FAIL: no push_with_guard.sh call sites found'; FAIL=1; }
NSITES=0
for site in $SITES; do
  NSITES=$((NSITES+1))
  LINE=$(awk '/bash scripts\/push_with_guard.sh/{if ((getline n) > 0 && n ~ /ls-remote|READBACK/) print n}' "$REPO_ROOT/$site" | head -1)
  pending=0; case " $PENDING_SITES " in *" $site "*) pending=1 ;; esac
  # A: no own commit, main moved after checkout
  fresh_runner; lane_tick "A $site"
  if ! run_site "$LINE"; then
    if [ $pending -eq 1 ]; then echo "PENDING $site: no-commit run fails its tip-equality readback"; else echo "FAIL: $site no-commit run went red after main moved (readback compares a stale checkout)"; FAIL=1; fi
  fi
  # B: own commit lands, a bot commits right after the push
  fresh_runner; (cd "$SCRATCH/site_runner" && printf 'own B %s\n' "$site" > own_file.txt && git add -A && git commit -qm 'own commit B')
  printf 'tick' > "$SCRATCH/pr_mode"
  if ! run_site "$LINE"; then
    if [ $pending -eq 1 ]; then echo "PENDING $site: landed push fails its tip-equality readback when a bot commits right after"; else echo "FAIL: $site landed push went red because a bot committed right after it"; FAIL=1; fi
  fi
  git -C origin.git cat-file -e "$(git -C site_runner rev-parse HEAD)^{commit}" 2>/dev/null && git -C origin.git merge-base --is-ancestor "$(git -C site_runner rev-parse HEAD)" main || { echo "FAIL: $site own commit not on origin/main after B"; FAIL=1; }
  # C: push reports success but origin drops it - must fail loud with HEAD reset to origin/main
  fresh_runner; (cd "$SCRATCH/site_runner" && printf 'own C %s\n' "$site" > own_file.txt && git add -A && git commit -qm 'own commit C')
  printf 'drop' > "$SCRATCH/pr_mode"
  if run_site "$LINE"; then echo "FAIL: $site push that origin did not keep passed silently"; FAIL=1; fi
  [ "$(git -C site_runner rev-parse HEAD)" = "$(git -C origin.git rev-parse main)" ] || { echo "FAIL: $site HEAD not reset to origin/main after a dropped push (on-failure hook would publish it)"; FAIL=1; }
  : > "$SCRATCH/pr_mode"
done
[ $NSITES -ge 6 ] || { echo "FAIL: expected at least 6 guard call sites, found $NSITES"; FAIL=1; }
if [ $FAIL -eq 0 ]; then echo "PASS push race guard (loud fail + reset + clean-push control + own-manifest misfire case + no-commit case + two-tick race + readback at $NSITES call sites: no-commit moved main, bot commit after push, dropped push)"; exit 0; else exit 1; fi
