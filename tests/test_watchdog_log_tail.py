#!/usr/bin/env python3
"""The watchdog's diagnosis carries the failing job's error tail.

Thirteen of the 34 files under incidents/ end in
`log fetch failed: gh repos/.../actions/jobs/<id>/logs: the response contains
terminal escape sequences; pass --allow-escape-sequences to output it anyway`:
`gh api` refuses to print a body that holds escape sequences, and a job log
holds them whenever a step colours its output, so every such diagnosis recorded
no cause. The watchdog now fetches the log itself, follows the endpoint's
signed-URL redirect without the token, and strips the sequences.

Run: python3 tests/test_watchdog_log_tail.py   (exit 1 on any failure)
"""
import ast, io, os, sys, types, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'scripts', 'watchdog.py')

# The script runs its diagnosis at import time, so only its helpers are loaded here:
# the module-level imports, REPO, and the three log-fetch definitions.
tree = ast.parse(open(SRC).read())
keep = []
for node in tree.body:
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        keep.append(node)
    elif isinstance(node, ast.Assign) and any(getattr(t, 'id', '') in ('REPO', '_ESCAPES') for t in node.targets):
        keep.append(node)
    elif isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in ('strip_escapes', '_NoRedirect', 'job_log'):
        keep.append(node)
ns = {'__name__': 'watchdog_helpers'}
exec(compile(ast.Module(body=keep, type_ignores=[]), SRC, 'exec'), ns)

failures = []

if 'job_log' not in ns:
    print("FAIL scripts/watchdog.py fetches the job log through `gh api`, which refuses a body "
          "with terminal escape sequences; no job_log() to drive (see incidents/*-diag.md, "
          "'log fetch failed: ... pass --allow-escape-sequences')")
    sys.exit(1)


def check(label, got, want):
    ok = got == want
    if not ok:
        failures.append(f'{label}: want {want!r} got {got!r}')
    print(f"{'OK  ' if ok else 'FAIL'} {label}" + ('' if ok else f'  [want {want!r} got {got!r}]'))


RAW = (b'2026-09-30T00:35:10.1Z \x1b[36;1mrefresh odds and rebuild\x1b[0m\n'
       b'2026-09-30T00:35:11.2Z \x1b[91mTraceback (most recent call last):\x1b[0m\n'
       b'2026-09-30T00:35:11.3Z   File "scripts/odds_prefill.py", line 88, in <module>\n'
       b'2026-09-30T00:35:11.4Z \x1b[91mKeyError: \'bookmakers\'\x1b[0m\r\n'
       b'2026-09-30T00:35:11.5Z ##[error]Process completed with exit code 1.\n')


class Opener:
    """Answers the logs endpoint with a 302 to a signed URL, then serves the log there.
    Records every request so the test can see where the token went."""

    def __init__(self):
        self.requests = []

    def open(self, req):
        self.requests.append((req.full_url, dict(req.header_items())))
        if req.full_url.startswith('https://api.github.com/'):
            headers = {'Location': 'https://productionresultssa.blob.core.windows.net/logs/108694807086?sig=abc'}
            raise urllib.error.HTTPError(req.full_url, 302, 'Found', headers, io.BytesIO(b''))
        return io.BytesIO(RAW)


os.environ['GH_TOKEN'] = 'test-token-value'
opener = Opener()
text = ns['job_log'](108694807086, opener=opener)

check('escape sequences stripped', '\x1b' in text, False)
check('cause kept', 'KeyError' in text and 'Traceback' in text, True)
check('step name kept', 'refresh odds and rebuild' in text, True)
check('two requests: endpoint then signed url', len(opener.requests), 2)
check('token sent to the api host', 'Bearer test-token-value' in opener.requests[0][1].get('Authorization', ''), True)
check('token not sent to the signed url', any('Authorization' in k for k in opener.requests[1][1]), False)

# The same filter the diagnosis applies, on the stripped text: the tail names the cause.
lines = text.splitlines()
hits = [l for l in lines if any(k in l.lower() for k in ('error', 'fail', 'conflict', 'fatal', 'traceback', 'refus'))]
tail = '\n'.join(hits[-6:] or lines[-6:])
check('error tail names the failing line', "KeyError: 'bookmakers'" in tail, True)
check('error tail has no carriage returns', '\r' in tail, False)

# A log that needs no redirect (a direct 200) is read as it is.
class Direct:
    def open(self, req):
        return io.BytesIO(b'plain \x1b[1mbold\x1b[0m done\n')

check('direct body read', ns['job_log'](1, opener=Direct()), 'plain bold done\n')

# A refusal other than a redirect still surfaces as an error, so the diagnosis says so.
class Refuse:
    def open(self, req):
        raise urllib.error.HTTPError(req.full_url, 403, 'Forbidden', {}, io.BytesIO(b''))

try:
    ns['job_log'](1, opener=Refuse())
    check('403 raises', False, True)
except urllib.error.HTTPError as e:
    check('403 raises', e.code, 403)

if failures:
    print('\n%d failure(s):\n  ' % len(failures) + '\n  '.join(failures))
    sys.exit(1)
print('\nALL WATCHDOG LOG TAIL TESTS PASS (%d)' % 10)
