#!/usr/bin/env python3
"""H-16: the site repository is public and GitHub Pages serves every tracked file, so a file that must not be
read publicly cannot stay in the tree (robots.txt only asks crawlers; it is not access control).
 - docs/feed_bug_ledger.md, the internal feed bug and release ledger, is not tracked and not on disk here (it
   lives in the private system repository now);
 - no tracked source file under scripts/ or docs/ names an internal coordination seat or channel: rulings are
   cited by their date and id, never by who relayed them.
Out of scope here and left as they are: slates/owner_rule_suspensions.jsonl (the page builder reads it; its
place is the owner's decision) and the record files' approval pointers (the record).
Run: python3 scripts/test_h16_private_files.py"""
import os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SELF = os.path.relpath(os.path.abspath(__file__), ROOT)
failures = 0

def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or detail == '' else '  [' + str(detail)[:400] + ']'))
    if not ok:
        failures += 1

tracked = [f for f in subprocess.run(['git', '-C', ROOT, 'ls-files'], capture_output=True, text=True).stdout.split('\n') if f]
check('H-16 docs/feed_bug_ledger.md is not tracked', 'docs/feed_bug_ledger.md' not in tracked)
check('H-16 docs/feed_bug_ledger.md is not on disk in the served tree', not os.path.exists(os.path.join(ROOT, 'docs', 'feed_bug_ledger.md')))

# names built from parts so this file never carries them itself
SEAT = re.compile(r'(?i)\b(?:' + 'mesh' + 'trix' + r'|' + 'mu' + 'se' + r')\b')
hits = []
for f in tracked:
    if f == SELF or not f.startswith(('scripts/', 'docs/')):
        continue
    p = os.path.join(ROOT, f)
    try:
        text = open(p, encoding='utf-8').read()
    except (UnicodeDecodeError, OSError):
        continue
    for n, line in enumerate(text.split('\n'), 1):
        if SEAT.search(line):
            hits.append('%s:%d' % (f, n))
check('H-16 no tracked scripts/ or docs/ file names an internal seat or channel', not hits, hits[:8])

print('FAILURES: %d' % failures if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
