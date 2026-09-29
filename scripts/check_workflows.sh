#!/bin/sh
# guard 4 YAML-gate class kill: no workflow file reaches origin unparseable.
# House rule: quote every step name (unquoted colons broke x_feed.yml twice on 9/28).
set -e
cd "$(git rev-parse --show-toplevel)"
python3 - <<'PY'
import glob, sys, yaml
bad = False
for f in sorted(glob.glob('.github/workflows/*.yml')):
    try:
        yaml.safe_load(open(f))
    except Exception as e:
        print('INVALID WORKFLOW %s: %s' % (f, e)); bad = True
if bad:
    sys.exit(1)
print('workflow YAML gate: all files parse')
PY
if command -v actionlint >/dev/null 2>&1; then actionlint -oneline; fi
