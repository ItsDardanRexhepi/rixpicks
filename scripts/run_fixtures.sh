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
# RP_FIXTURES_JOBS=N runs N files at a time and reports them in the same order as a serial run (the site-change
# worker uses it so a chat change is checked in about a minute rather than three and a half). Unset or 1 is the
# serial run CI has always used. A file in SERIAL always runs alone, after the parallel ones.
JOBS="${RP_FIXTURES_JOBS:-1}"
SERIAL="
"
run_one() {  # file outdir -> outdir/<name>.out and outdir/<name>.rc
  local f="$1" d="$2" n
  n=$(printf '%s' "$f" | tr '/' '_')
  case "$f" in
    *.py) python3 "$f" > "$d/$n.out" 2>&1 ;;
    *.js) node "$f" > "$d/$n.out" 2>&1 ;;
    *.sh) bash "$f" > "$d/$n.out" 2>&1 ;;
  esac
  echo $? > "$d/$n.rc"
}
report() {  # file rc out
  if [ "$2" -eq 0 ]; then
    echo "PASS $1"; PASS=$((PASS+1))
  else
    echo "FAIL $1 (exit $2)"; printf '%s\n' "$3" | tail -15 | sed 's/^/    /'
    FAILED="$FAILED $1"
  fi
}
RUN=""
for f in scripts/test_*.py scripts/test_*.js scripts/test_*.sh tests/test_*.py tests/run_tests.py; do
  [ -f "$f" ] || continue
  why=$(skip_reason "$f")
  if [ -n "$why" ]; then echo "SKIP $f ($why)"; SKIPPED=$((SKIPPED+1)); continue; fi
  RUN="$RUN $f"
done
if [ "$JOBS" -gt 1 ] 2>/dev/null; then
  OUT=$(mktemp -d "${TMPDIR:-/tmp}/rp-fixtures.XXXXXX") || exit 2
  export -f run_one
  PAR=""; SER=""
  for f in $RUN; do
    if printf '%s\n' "$SERIAL" | grep -qx "$f"; then SER="$SER $f"; else PAR="$PAR $f"; fi
  done
  printf '%s\n' $PAR | xargs -P "$JOBS" -I{} bash -c 'run_one "$1" "$2"' _ {} "$OUT"
  for f in $SER; do run_one "$f" "$OUT"; done
  for f in $RUN; do
    n=$(printf '%s' "$f" | tr '/' '_')
    report "$f" "$(cat "$OUT/$n.rc" 2>/dev/null || echo 99)" "$(cat "$OUT/$n.out" 2>/dev/null)"
  done
  rm -r "$OUT"
else
  for f in $RUN; do
    case "$f" in
      *.py) cmd=(python3 "$f") ;;
      *.js) cmd=(node "$f") ;;
      *.sh) cmd=(bash "$f") ;;
    esac
    out=$("${cmd[@]}" 2>&1); rc=$?
    report "$f" "$rc" "$out"
  done
fi
echo "fixtures: $PASS passed, $SKIPPED skipped, $(echo $FAILED | wc -w | tr -d ' ') failed"
[ -z "$FAILED" ] || { echo "FAILED:$FAILED"; exit 1; }
