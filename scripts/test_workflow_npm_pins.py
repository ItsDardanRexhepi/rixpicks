#!/usr/bin/env python3
"""Supply-chain guard for test-only npm installs in workflows. x_feed.yml ran
`npm install --no-save --silent jsdom` (latest, install scripts on) inside the step whose env
carried NIM_CLIENT_TOKEN, in a job with contents:write and actions:write, on every x-feed run.
Every workflow `npm install` of a package the fixtures require (scripts/test_*.js) must name it
at an exact version, skip lifecycle scripts, and run in a step with no secrets in its environment.
(Deploy tooling such as the Cloudflare workflows' wrangler is outside this guard.)
Run: python3 scripts/test_workflow_npm_pins.py   (exit 1 on any failure)
"""
import glob, os, re, shlex, sys
try:
    import yaml
except ImportError:
    sys.exit('pyyaml required')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXACT = re.compile(r'^(@[a-z0-9][\w.-]*/)?[a-z0-9][\w.-]*@\d+\.\d+\.\d+$')
BUILTIN = {'fs', 'path', 'vm', 'assert', 'child_process', 'os', 'util', 'url', 'crypto', 'http', 'https', 'zlib', 'events', 'stream'}
# third-party packages the fixtures load: require('x') of a bare, non-builtin name
TEST_DEPS = set()
for f in glob.glob(os.path.join(ROOT, 'scripts', 'test_*.js')):
    for m in re.finditer(r"require\(\s*['\"]([^'\"./][^'\"]*)['\"]\s*\)", open(f).read()):
        name = m.group(1).split('/')[0] if not m.group(1).startswith('@') else '/'.join(m.group(1).split('/')[:2])
        if name.replace('node:', '') not in BUILTIN and not name.startswith('node:'):
            TEST_DEPS.add(name)

def pkg_name(spec):
    return spec.rsplit('@', 1)[0] if spec.count('@') > (1 if spec.startswith('@') else 0) else spec

failures = []
def check(label, ok, detail=''):
    if not ok:
        failures.append(label + (': ' + detail if detail else ''))
    print(f"{'OK  ' if ok else 'FAIL'} {label}" + ('' if ok else f'  [{detail}]'))

installs = 0
for path in sorted(glob.glob(os.path.join(ROOT, '.github', 'workflows', '*.yml'))):
    wf = os.path.basename(path)
    d = yaml.safe_load(open(path)) or {}
    for jname, job in (d.get('jobs') or {}).items():
        job_secret = 'secrets.' in str(job.get('env') or '')
        for step in job.get('steps') or []:
            run = step.get('run') or ''
            for line in run.splitlines():
                for cmd in re.split(r'&&|\|\||;', line.split('#', 1)[0]):
                    try:
                        toks = shlex.split(cmd)
                    except ValueError:
                        toks = cmd.split()
                    if len(toks) < 2 or toks[0] != 'npm' or toks[1] not in ('install', 'i', 'add'):
                        continue
                    pkgs = [t for t in toks[2:] if not t.startswith('-')]
                    if not pkgs or not any(pkg_name(p) in TEST_DEPS for p in pkgs):
                        continue
                    installs += 1
                    where = f"{wf} {jname} '{step.get('name', '?')}'"
                    for p in pkgs:
                        check(f'{where}: {p} pinned to an exact version', bool(EXACT.match(p)), 'use name@X.Y.Z')
                    check(f'{where}: lifecycle scripts skipped', '--ignore-scripts' in toks, ' '.join(toks))
                    check(f'{where}: no secret in the install step env',
                          'secrets.' not in str(step.get('env') or '') and not job_secret,
                          'env: ' + ', '.join(sorted((step.get('env') or {}).keys())))

check('fixture dependencies found (jsdom)', 'jsdom' in TEST_DEPS, ', '.join(sorted(TEST_DEPS)))
check('at least one fixture-dependency install is checked (x_feed DOM fixture)', installs >= 1, f'{installs} found')
if failures:
    print(f'WORKFLOW NPM PINS: {len(failures)} FAILURES')
    sys.exit(1)
print(f'WORKFLOW NPM PINS: ALL PASS ({installs} install(s))')
