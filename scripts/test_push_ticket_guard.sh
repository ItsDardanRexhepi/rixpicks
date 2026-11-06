#!/bin/bash
# Fixture: scripts/push_with_guard.sh refuses to push invalid ticket data (Nov 2 class) and still pushes
# valid ticket data and non-ticket commits. Real script, real git remote in a scratch repo, real
# validator (copied from this tree). Negative: truncated slates/wooder_tickets.json -> exit 1, nothing
# pushed, HEAD reset to origin/main. Positive: a valid ticket edit and an unrelated commit push fine.
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
S=$(mktemp -d); trap 'rm -rf "$S"' EXIT
cd "$S" || exit 2
git init -q --bare -b main origin.git 2>/dev/null || git init -q --bare origin.git
git clone -q origin.git w 2>/dev/null
cd w || exit 2
git config user.email t@t; git config user.name t; git checkout -q -B main
mkdir -p scripts slates
cp "$ROOT/scripts/validate_ticket_data.py" "$ROOT/scripts/push_with_guard.sh" scripts/
for f in past_tickets wooder_tickets wooder_combos wooder_dingers wooder_first_td ultrix_record; do cp "$ROOT/slates/$f.json" slates/; done
echo a > other.txt
git add -A && git commit -qm base && git push -q -u origin main
FAIL=0
head -c 1000 slates/wooder_tickets.json > slates/wooder_tickets.json.t && mv slates/wooder_tickets.json.t slates/wooder_tickets.json
git add -A && git commit -qm 'bad ticket edit'
BAD=$(git rev-parse HEAD)
bash scripts/push_with_guard.sh >"$S/out" 2>&1; RC=$?
[ $RC -eq 1 ] || { echo "FAIL: invalid ticket data should exit 1, got $RC"; FAIL=1; }
[ "$(git -C ../origin.git rev-parse main)" != "$BAD" ] || { echo 'FAIL: invalid ticket data reached origin'; FAIL=1; }
[ "$(git rev-parse HEAD)" = "$(git -C ../origin.git rev-parse main)" ] || { echo 'FAIL: HEAD not reset to origin/main'; FAIL=1; }
grep -q 'TICKET DATA GUARD' "$S/out" || { echo 'FAIL: no loud guard message'; FAIL=1; }
python3 - <<'PY'
import json
p='slates/wooder_tickets.json'; d=json.load(open(p)); d['generated_at']='2026-11-06T10:00:00-08:00'; json.dump(d,open(p,'w'),indent=1)
PY
git add -A && git commit -qm 'valid ticket edit'
bash scripts/push_with_guard.sh >"$S/out" 2>&1 || { echo "FAIL: valid ticket edit should push: $(tail -3 "$S/out")"; FAIL=1; }
[ "$(git rev-parse HEAD)" = "$(git -C ../origin.git rev-parse main)" ] || { echo 'FAIL: valid ticket edit not on origin'; FAIL=1; }
echo b > other.txt; git add -A && git commit -qm 'unrelated'
bash scripts/push_with_guard.sh >"$S/out" 2>&1 || { echo 'FAIL: unrelated commit should push'; FAIL=1; }
[ $FAIL -eq 0 ] && echo 'ALL OK' || { echo "$FAIL FAIL"; exit 1; }
