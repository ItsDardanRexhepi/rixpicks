#!/bin/bash
# Runs every standing fixture from the repo root and fails if any fails (F12, Oct 2: 20 of 32
# test files ran in no workflow and no gate, which is how four of them went stale unnoticed).
# New scripts/test_*.py|js and tests/test_*.py files are picked up automatically; a file is left
# out only with a reason in SKIP below. Used by .github/workflows/tests.yml; runs locally too:
#   bash scripts/run_fixtures.sh
set -u
cd "$(dirname "$0")/.." || exit 2
# finals_watch reads its private paths and secrets from these (grading host only); fixtures never use them
unset RPS_KB RIX_REPO RIX_FINALS_CONFIG RIX_RECORD_TOKEN THE_ODDS_API_KEY
# file -> reason it is not run here (keep each reason true; remove the entry once it is fixed)
SKIP="
scripts/test_manifest_chips_class.py|content check of a built page: needs manifest.json + index.html args
scripts/test_feed_fallback_dom.js|needs jsdom; runs in x-feed with the pinned install
scripts/test_state_gate_pm_path.js|needs jsdom; not yet verified green anywhere
"
skip_reason() { printf '%s\n' "$SKIP" | awk -F'|' -v f="$1" '$1==f {print $2}'; }
PASS=0; FAILED=""; SKIPPED=0
for f in scripts/test_*.py scripts/test_*.js scripts/test_*.sh tests/test_*.py tests/run_tests.py; do
  [ -f "$f" ] || continue
  why=$(skip_reason "$f")
  if [ -n "$why" ]; then echo "SKIP $f ($why)"; SKIPPED=$((SKIPPED+1)); continue; fi
  case "$f" in
    *.py) cmd=(python3 "$f") ;;
    *.js) cmd=(node "$f") ;;
    *.sh) cmd=(bash "$f") ;;
  esac
  out=$("${cmd[@]}" 2>&1); rc=$?
  if [ $rc -eq 0 ]; then
    echo "PASS $f"; PASS=$((PASS+1))
  else
    echo "FAIL $f (exit $rc)"; printf '%s\n' "$out" | tail -15 | sed 's/^/    /'
    FAILED="$FAILED $f"
  fi
done
echo "fixtures: $PASS passed, $SKIPPED skipped, $(echo $FAILED | wc -w | tr -d ' ') failed"
[ -z "$FAILED" ] || { echo "FAILED:$FAILED"; exit 1; }
