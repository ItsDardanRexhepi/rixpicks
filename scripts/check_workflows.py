#!/usr/bin/env python3
"""Pre-push workflow sanity: every .github/workflows/*.yml must parse as YAML and carry
jobs. Catches the 9/27 dd0e7a2 break (unindented lines ending a run: | block scalar early)
before push. Exit 1 on any violation."""
import glob, sys
try:
    import yaml
except ImportError:
    sys.exit('pyyaml required')
bad = []
for path in sorted(glob.glob('.github/workflows/*.yml')):
    try:
        d = yaml.safe_load(open(path))
        if not isinstance(d, dict) or 'jobs' not in d:
            bad.append(path + ': parses but no jobs key')
    except Exception as e:
        bad.append(path + ': ' + str(e).split('\n')[0])
if bad:
    print('\n'.join(bad)); sys.exit(1)
print('workflow YAML OK: ' + ', '.join(sorted(glob.glob('.github/workflows/*.yml'))))
