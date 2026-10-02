#!/usr/bin/env python3
"""Standing fixture for the Sep 30 public-name sweep: the guest is "Wooder Ice" on every public
surface. No tracked source, workflow, doc or incident file (and no tracked file NAME) may carry
the retired private first name. The name is matched by SHA-256 of each lowercase word, so this
guard never republishes it. Generated pages and data feeds are out of scope here (they can carry
real athlete names); their producers are scanned instead. PENDING lists the files still owned
elsewhere, each waiting on its owner: they are reported, not failed. No side effects."""
import hashlib, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIGEST = 'ce0fee7e61f9c74f1110f0e5940a80b4f059f189217d0c3d26bb41960d4bf597'
TEXT = ('.py', '.js', '.yml', '.yaml', '.md', '.sh', '.txt', '.toml', '.css', '.trigger')
PENDING = set()
PENDING_BY_DIGEST = {
    # owner decision: the two superseded slates/ feed copies (wooder_* replaced them; served, read by
    # nothing). Listed by SHA-256 of the path because the file names carry the name.
    '05cd5c548e3871e699a905ec20433976cbdb084ebf964643c62b72c84efb34b9',
    '7601b7f37ae36be49fb7d337664fad145141105e88cd38bab2d78b398deec872',
}
def hit(text):
    return any(hashlib.sha256(w.lower().encode()).hexdigest() == DIGEST for w in set(re.findall(r'[A-Za-z]+', text)))

files = [f for f in subprocess.run(['git', '-C', ROOT, 'ls-files'], capture_output=True, text=True).stdout.split('\n') if f]
bad, pending = [], []
for f in files:
    named = hit(f)
    body = False
    if f.endswith(TEXT):
        try: body = hit(open(os.path.join(ROOT, f), encoding='utf-8').read())
        except (UnicodeDecodeError, FileNotFoundError): body = False
    if named or body:
        waiting = f in PENDING or hashlib.sha256(f.encode()).hexdigest() in PENDING_BY_DIGEST
        label = (os.path.dirname(f) + '/<superseded feed copy, name withheld>') if named and waiting else f + (' (file name)' if named else '')
        (pending if waiting else bad).append(label)
for f in pending: print('PENDING', f)
for f in bad: print('FAIL', f, 'carries the retired private first name - use "Wooder Ice" or drop the name')
print('scanned %d tracked files: %s' % (len(files), 'ALL CHECKS PASS' if not bad else '%d FAIL' % len(bad)))
sys.exit(1 if bad else 0)
