#!/bin/bash
# Local fallback for .github/workflows/record_final.yml. GitHub Actions has failed to start
# (startup_failure) since 2026-10-06 03:55Z, so graded finals queued in record_request.json were not
# applied. This runs the workflow's steps, in its order, with its gates, from a Mac:
#   1. hold-check   node scripts/health_gate.js --hold. Exit 1 (a proven structural FAIL) or any exit
#                   other than 0/1 (a gate error, fail closed) HOLDS: nothing else runs, nothing is
#                   written. There is NO bypass here - the workflow's repair dispatch (hold_bypass=repair)
#                   is deliberately not mirrored, and no variable or flag skips the gate.
#   2. apply        python3 scripts/record_final.py (independent ESPN verify, fail-closed). A refusal
#                   (exit 3) stops the run with that exit code; record_final writes nothing then.
#   3. changed-gate rebuild + commit only when manifest.json, history.json, record_request.json or
#                   record_done.json moved (FORCE_REBUILD=true mirrors the force_rebuild input).
#   4. rebuild      python3 scripts/build_history.py history.json, then
#                   RP_REFRESH=1 python3 scripts/_build_nocanon_v2.py manifest.json index.html
#   5. sweep        node --check on every emitted <script> block (> 50 chars) of index.html.
#   6. commit       the workflow's exact allowlist, as the OWNER (Dardan Rexhepi); any other tracked
#                   change fails loud with its names (never add -A).
#   7. push         scripts/push_with_guard.sh: push, fetch/rebase retry loop (5 attempts), lane-file
#                   race guard, readback that origin/main contains the commit.
# Where it runs: a fresh scratch git worktree of origin/main (fetched first) on a temporary branch that
# tracks origin/main - the same clean checkout a runner gets. Your own checkout, its branch and any
# uncommitted work are never touched; the worktree and temporary branch are removed on exit.
# Afterwards run `git pull` in your checkout to see the record write.
#
#   bash scripts/record_final_local.sh                       real run (commits + pushes origin main)
#   DRY=1 bash scripts/record_final_local.sh                 steps 1-5 + what step 6 would commit; no commit, no push
#   FORCE_REBUILD=true bash scripts/record_final_local.sh    the workflow's force_rebuild=true dispatch
#
# Exit: 0 written / nothing pending / dry run done; 2 setup (no repo, fetch or worktree failed);
# 3 record_final.py refused; 4 HELD by the health gate; 1 any other failure (build, sweep, tripwire, push).
# Fixture: scripts/test_record_final_local.py (DRY and real paths against a local bare origin, offline).
set -u
OWNER_NAME='Dardan Rexhepi'
OWNER_EMAIL='242350397+ItsDardanRexhepi@users.noreply.github.com'
COMMIT_MSG='Record write: graded finals applied from record_request.json (ESPN-verified, ledger-exact) [record-final]'
# the workflow's changed-gate inputs and commit allowlist, verbatim (test_record_final_local.py holds them equal)
GATE_FILES='manifest.json history.json record_request.json record_done.json'
ALLOWLIST='manifest.json history.json record.html yesterday.html index.html futures.html game-*.html team-*.html record_request.json record_done.json slates/api_record.json slates/wooder_combos.json'
DRY="${DRY:-}"
FORCE_REBUILD="${FORCE_REBUILD:-false}"

say() { printf '%s\n' "$*"; }
die() { rc=$1; shift; printf 'record_final_local: %s\n' "$*" >&2; exit "$rc"; }

REPO=$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null) || die 2 'not inside a git checkout'
git -C "$REPO" remote get-url origin >/dev/null 2>&1 || die 2 "no origin remote in $REPO"
git -C "$REPO" fetch -q origin main || die 2 'git fetch origin main failed - nothing ran'
BASE=$(git -C "$REPO" rev-parse --verify -q origin/main) || die 2 'origin/main not found after fetch'

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BRANCH="record-final-local-$STAMP-$$"
WT=$(mktemp -d "${TMPDIR:-/tmp}/record-final-local.XXXXXX") || die 2 'mktemp failed'
SCRATCH=$(mktemp -d "${TMPDIR:-/tmp}/record-final-local-logs.XXXXXX") || die 2 'mktemp failed'
cleanup() {
  cd "$REPO" || cd /
  git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1
  git -C "$REPO" worktree prune >/dev/null 2>&1
  git -C "$REPO" branch -D "$BRANCH" >/dev/null 2>&1
  rm -f "$SCRATCH/hold.log" "$SCRATCH/build.log" "$SCRATCH/blk.js"
  rmdir "$SCRATCH" "$WT" >/dev/null 2>&1
  return 0
}
trap cleanup EXIT
git -C "$REPO" worktree add -q -b "$BRANCH" "$WT" "$BASE" >/dev/null 2>&1 || die 2 "could not create the scratch worktree at $WT"
git -C "$WT" branch -q --set-upstream-to=origin/main "$BRANCH" || die 2 'could not track origin/main'
cd "$WT" || die 2 "cannot enter $WT"
say "record_final_local: scratch checkout of origin/main $(git rev-parse --short HEAD) at $WT${DRY:+ (DRY RUN)}"

# 1. hold-check (structural health gate; fail closed; no bypass)
node scripts/health_gate.js --hold > "$SCRATCH/hold.log" 2>&1; hrc=$?
cat "$SCRATCH/hold.log"
if [ "$hrc" != "0" ]; then
  if [ "$hrc" = "1" ]; then kind='structural FAIL'; else kind="GATE ERROR (exit $hrc), failing closed"; fi
  say "HELD: posting job did not run ($kind)"
  say 'What broke / what users cannot see (from the gate):'
  grep -E '^(FAIL|GATE ERROR)' "$SCRATCH/hold.log" | sed 's/^/- /'
  say 'Nothing was applied, built, committed or pushed. The hold lifts on the next run after the gate passes; there is no bypass.'
  exit 4
fi

# 2. apply graded finals (independent ESPN verify, fail-closed)
python3 scripts/record_final.py; arc=$?
[ "$arc" = "0" ] || die "$arc" "record_final.py exited $arc - chain stopped, nothing committed or pushed"

# 3. nothing-pending gate: any apply-step write counts (an eod_day_close brief fill touches history.json only)
if [ "$FORCE_REBUILD" = "true" ]; then changed=true
elif git diff --quiet -- $GATE_FILES 2>/dev/null; then changed=false
else changed=true; fi
if [ "$changed" != "true" ]; then
  say 'nothing pending: no grade applied, no rebuild, no commit'
  exit 0
fi

# 4. rebuild record pages, then the site (record pages first: the site builder reads yesterday.html)
set -o pipefail
python3 scripts/build_history.py history.json || die 1 'build_history.py failed - nothing committed or pushed'
RP_REFRESH=1 python3 scripts/_build_nocanon_v2.py manifest.json index.html 2>&1 | tee "$SCRATCH/build.log" || die 1 'site build failed - nothing committed or pushed'
set +o pipefail

# 5. syntax-sweep emitted script blocks
BLK="$SCRATCH/blk.js" python3 - <<'PY' || die 1 'syntax sweep found a broken script block - nothing committed or pushed'
import os, re, subprocess, sys
s=open('index.html').read()
blocks=[b for b in re.findall(r'<script>(.*?)</script>', s, re.S) if len(b)>50]
bad=0
for i,b in enumerate(blocks):
    open(os.environ['BLK'],'w').write(b)
    r=subprocess.run(['node','--check',os.environ['BLK']],capture_output=True,text=True)
    if r.returncode!=0:
        bad+=1; print('BLOCK',i,'FAIL',r.stderr[:300])
print('blocks',len(blocks),'bad',bad)
sys.exit(1 if bad else 0)
PY

# 6. commit the allowlist as the owner; tripwire on any tracked change outside it
git add $ALLOWLIST || die 1 'git add of the allowlist failed'
if ! git diff --quiet; then
  echo 'UNSTAGED TRACKED OUTPUTS outside the add list - extend the allowlist:' >&2
  git diff --name-only >&2
  exit 1
fi
if git diff --cached --quiet; then
  say 'nothing to commit: the rebuild reproduced the committed pages'
  exit 0
fi
if [ -n "$DRY" ]; then
  say "DRY RUN: would commit as $OWNER_NAME <$OWNER_EMAIL>:"
  say "  $COMMIT_MSG"
  git diff --cached --stat | sed 's/^/  /'
  say 'DRY RUN: nothing committed, nothing pushed; the scratch checkout is removed on exit.'
  exit 0
fi
# the owner identity, for the commit and for a rebase of it in the push loop (author and committer)
export GIT_AUTHOR_NAME="$OWNER_NAME" GIT_AUTHOR_EMAIL="$OWNER_EMAIL" GIT_COMMITTER_NAME="$OWNER_NAME" GIT_COMMITTER_EMAIL="$OWNER_EMAIL"
git -c user.name="$OWNER_NAME" -c user.email="$OWNER_EMAIL" commit -q -m "$COMMIT_MSG" \
  -m 'Run locally by scripts/record_final_local.sh (GitHub Actions record-final fallback).' || die 1 'commit failed'

# 7. push: fetch/rebase retry loop with the lane-file race guard and readback. The temporary branch
# pushes to its upstream (origin main) - push.default=upstream for this process only.
GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=push.default GIT_CONFIG_VALUE_0=upstream bash scripts/push_with_guard.sh; prc=$?
[ "$prc" = "0" ] || die 1 "push failed (exit $prc) - nothing landed; the next run regenerates from the new origin/main"
say "RECORD WRITE LANDED: $(git rev-parse --short HEAD) is on origin/main. Run git pull in your checkout to see it."
exit 0
