#!/usr/bin/env python3
"""Local record-final fallback fixture (scripts/record_final_local.sh; GitHub Actions has failed to
start since 2026-10-06 03:55Z). Runs the REAL script and the REAL scripts/push_with_guard.sh in a
scratch clone whose origin is a local bare repo, with the heavy steps (health gate, record_final.py,
build_history.py, the site builder) replaced by stubs that log what they were asked to do.
  DRY=1: hold-check, apply, changed-gate, rebuild (RP_REFRESH=1, record pages first) and sweep run in
    order; it says what it would commit and commits/pushes NOTHING; origin and the caller's checkout
    are untouched and the scratch worktree/branch are gone afterwards.
  holds: a structural FAIL (exit 1) or a gate error (exit 2) holds - record_final never runs - and no
    variable (hold_bypass=repair, HC_BYPASS, HOLD_BYPASS) gets past it.
  stops: a record_final refusal passes its exit 3 through; nothing pending -> no rebuild (unless
    FORCE_REBUILD=true); a broken script block or a tracked change outside the allowlist fails loud.
  real run: one commit by the OWNER (no co-author line), only allowlisted files, pushed to origin
    main; a concurrent unrelated push is rebased over (retry loop) and the write still lands; a
    concurrent manifest.json push fails loud and nothing lands.
  mirror: the script's changed-gate files and commit allowlist equal the workflow's, and it runs the
    workflow's commands.
Offline. Bite-proof: red without scripts/record_final_local.sh. Run: python3 scripts/test_record_final_local.py"""
import json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(HERE, 'record_final_local.sh')
OWNER = 'Dardan Rexhepi|242350397+ItsDardanRexhepi@users.noreply.github.com'
failures = 0

def check(name, actual, expected):
    global failures
    ok = actual == expected
    print(('OK  ' if ok else 'FAIL'), name, '' if ok else f'(got {actual!r}, want {expected!r})')
    if not ok:
        failures += 1

if not os.path.exists(SCRIPT):
    check('scripts/record_final_local.sh exists', False, True)
    sys.exit(1)

STUB_GATE = r"""const fs=require('fs');fs.appendFileSync(process.env.STUB_LOG,'gate '+process.argv.slice(2).join(' ')+'\n');
const rc=Number(process.env.STUB_GATE_RC||0);console.log(rc===1?'FAIL stub structural check  [user impact: stub page broken]':'OK   stub check');process.exit(rc);
"""
STUB_RF = r"""import json,os,subprocess,sys
open(os.environ['STUB_LOG'],'a').write('record_final\n')
rc=int(os.environ.get('STUB_RF_RC','0'))
if rc: sys.exit(rc)
if os.environ.get('STUB_RF_NOOP'): print('nothing new processed'); sys.exit(0)
h=json.load(open('history.json')); h['days'].append({'date':'2026-10-05','picks':[{'name':'Penguins ML','result':'L'}]}); json.dump(h,open('history.json','w'))
m=json.load(open('manifest.json')); m['record']='33-16'; json.dump(m,open('manifest.json','w'))
json.dump({'requests':[]},open('record_request.json','w'))
d=json.load(open('record_done.json')); d['processed'].append('401892447|ml|home'); json.dump(d,open('record_done.json','w'))
if os.environ.get('STUB_RACE_CMD'): subprocess.run(['bash','-c',os.environ['STUB_RACE_CMD']],check=True,capture_output=True)
print('RECORD WRITE: record 33-16')
"""
STUB_HIST = r"""import json,os,sys
open(os.environ['STUB_LOG'],'a').write('build_history '+' '.join(sys.argv[1:])+'\n')
h=json.load(open(sys.argv[1]))
open('record.html','w').write('<p>%d days</p>' % len(h['days'])); open('yesterday.html','w').write('<p>y %d</p>' % len(h['days']))
"""
STUB_SITE = r"""import json,os,sys
open(os.environ['STUB_LOG'],'a').write('site RP_REFRESH=%s %s\n' % (os.environ.get('RP_REFRESH',''),' '.join(sys.argv[1:])))
m=json.load(open(sys.argv[1]))
js='var rec=%s;function f(){return rec+" ok";}' % json.dumps(m['record'])
if os.environ.get('STUB_BAD_JS'): js='function broken( { return 1; }'
open(sys.argv[2],'w').write('<html><script>'+js.ljust(64)+'</script></html>\n')
if os.environ.get('STUB_TOUCH_OUTSIDE'): open('odds_moves.jsonl','a').write('tick\n')
"""
BASE_FILES = {
    'manifest.json': {'date': '2026-10-05', 'record': '33-15', 'picks': []}, 'history.json': {'days': []},
    'record_request.json': {'requests': [{'grade_id': '401892447|ml|home'}]}, 'record_done.json': {'processed': []},
    'record.html': '<p>0 days</p>', 'yesterday.html': '<p>y 0</p>', 'index.html': '<html></html>\n', 'futures.html': 'f',
    'game-1.html': 'g', 'team-a.html': 't', 'slates/api_record.json': {}, 'slates/wooder_combos.json': {}, 'odds_moves.jsonl': '',
    'scripts/health_gate.js': STUB_GATE, 'scripts/record_final.py': STUB_RF, 'scripts/build_history.py': STUB_HIST,
    'scripts/_build_nocanon_v2.py': STUB_SITE}

class Scene:
    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix='rf_local_')
        self.tmp = os.path.join(self.dir, 'tmp'); os.makedirs(self.tmp)
        self.log = os.path.join(self.dir, 'stub.log')
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', TMPDIR=self.tmp, STUB_LOG=self.log)
        for k in ('DRY', 'FORCE_REBUILD', 'STUB_GATE_RC', 'STUB_RF_RC', 'STUB_RF_NOOP', 'STUB_BAD_JS', 'STUB_TOUCH_OUTSIDE', 'STUB_RACE_CMD'):
            self.env.pop(k, None)
        self.origin, self.work, self.other = (os.path.join(self.dir, n) for n in ('origin.git', 'work', 'other'))
        self.git(self.dir, 'init', '-q', '--bare', '-b', 'main', self.origin)
        self.git(self.dir, 'init', '-q', '-b', 'main', self.work)
        for rel, obj in BASE_FILES.items():
            p = os.path.join(self.work, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, 'w').write(obj if isinstance(obj, str) else json.dumps(obj))
        for real in ('record_final_local.sh', 'push_with_guard.sh'):
            shutil.copy(os.path.join(HERE, real), os.path.join(self.work, 'scripts', real))
        self.git(self.work, 'add', '-A')
        self.git(self.work, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'base')
        self.git(self.work, 'remote', 'add', 'origin', self.origin)
        self.git(self.work, 'push', '-q', '-u', 'origin', 'main')
        self.git(self.dir, 'clone', '-q', self.origin, self.other)

    def git(self, cwd, *a):
        return subprocess.run(['git', *a], cwd=cwd, env=self.env, check=True, capture_output=True, text=True).stdout.strip()

    def run(self, **env):
        e = dict(self.env, **env)
        r = subprocess.run(['bash', os.path.join(self.work, 'scripts', 'record_final_local.sh')], cwd=self.work, env=e,
                           capture_output=True, text=True, timeout=180)
        steps = open(self.log).read().splitlines() if os.path.exists(self.log) else []
        return r.returncode, r.stdout + r.stderr, steps

    def tip(self):
        return self.git(self.origin, 'rev-parse', 'main')

    def tidy(self):
        """the caller's checkout untouched and nothing left behind"""
        return {'branch': self.git(self.work, 'rev-parse', '--abbrev-ref', 'HEAD'),
                'status': self.git(self.work, 'status', '--porcelain'),
                'worktrees': len(self.git(self.work, 'worktree', 'list').splitlines()),
                'temp_branches': self.git(self.work, 'branch', '--list', 'record-final-local-*'),
                'temp_dirs': sorted(os.listdir(self.tmp))}

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)

TIDY = {'branch': 'main', 'status': '', 'worktrees': 1, 'temp_branches': '', 'temp_dirs': []}
FULL = ['gate --hold', 'record_final', 'build_history history.json', 'site RP_REFRESH=1 manifest.json index.html']

def scene_run(label, **env):
    s = Scene()
    try:
        tip0, head0 = s.tip(), s.git(s.work, 'rev-parse', 'HEAD')
        code, out, steps = s.run(**env)
        return s, code, out, steps, tip0, head0
    except Exception:
        s.close()
        raise

# ---- DRY path ----
s, code, out, steps, tip0, head0 = scene_run('dry', DRY='1')
try:
    check('DRY: exit 0', code, 0)
    check('DRY: every workflow step ran, in order (hold-check, apply, record pages, site with RP_REFRESH=1)', steps, FULL)
    check('DRY: says what it would commit', 'DRY RUN: would commit as Dardan Rexhepi <242350397+ItsDardanRexhepi@users.noreply.github.com>' in out, True)
    check('DRY: the would-be commit lists the record files', all(f in out for f in ('history.json', 'manifest.json', 'record.html', 'index.html')), True)
    check('DRY: syntax sweep ran', 'blocks 1 bad 0' in out, True)
    check('DRY: nothing pushed (origin main unchanged)', s.tip(), tip0)
    check('DRY: caller checkout untouched (same HEAD)', s.git(s.work, 'rev-parse', 'HEAD'), head0)
    check('DRY: clean up (no worktree, temp branch or temp dir left)', s.tidy(), TIDY)
    check('DRY: the queue in the caller checkout is still there', json.load(open(os.path.join(s.work, 'record_request.json')))['requests'] != [], True)
finally:
    s.close()

# ---- holds: no bypass ----
for label, env in (('structural FAIL', {'STUB_GATE_RC': '1'}), ('gate error', {'STUB_GATE_RC': '2'}),
                   ('structural FAIL + hold_bypass=repair', {'STUB_GATE_RC': '1', 'hold_bypass': 'repair', 'HC_BYPASS': 'repair',
                                                            'HOLD_BYPASS': 'repair', 'BYPASS': 'repair'})):
    for dry in ('1', ''):
        s, code, out, steps, tip0, head0 = scene_run(label, DRY=dry, **env)
        try:
            tag = f'{label} ({"DRY" if dry else "real"})'
            check(f'HOLD {tag}: exit 4', code, 4)
            check(f'HOLD {tag}: record_final never ran', steps, ['gate --hold'])
            check(f'HOLD {tag}: says HELD and names the failure', ('HELD' in out, 'no bypass' in out), (True, True))
            check(f'HOLD {tag}: nothing pushed, nothing left', (s.tip() == tip0, s.tidy()), (True, TIDY))
        finally:
            s.close()

# ---- stops ----
s, code, out, steps, tip0, _ = scene_run('refusal', DRY='1', STUB_RF_RC='3')
try:
    check('record_final refusal: its exit 3 passes through', code, 3)
    check('record_final refusal: no rebuild', steps, ['gate --hold', 'record_final'])
finally:
    s.close()
s, code, out, steps, tip0, _ = scene_run('noop', STUB_RF_NOOP='1')
try:
    check('nothing pending: exit 0, no rebuild, nothing pushed', (code, steps, s.tip() == tip0, 'nothing pending' in out),
          (0, ['gate --hold', 'record_final'], True, True))
finally:
    s.close()
s, code, out, steps, tip0, _ = scene_run('force', DRY='1', STUB_RF_NOOP='1', FORCE_REBUILD='true')
try:
    check('FORCE_REBUILD=true with nothing pending: rebuilds (the workflow\'s force_rebuild)', (code, steps), (0, FULL))
finally:
    s.close()
s, code, out, steps, tip0, _ = scene_run('badjs', STUB_BAD_JS='1')
try:
    check('broken script block: the sweep fails loud, nothing pushed', (code, 'BLOCK 0 FAIL' in out, s.tip() == tip0, s.tidy()), (1, True, True, TIDY))
finally:
    s.close()
s, code, out, steps, tip0, _ = scene_run('tripwire', STUB_TOUCH_OUTSIDE='1')
try:
    check('tracked change outside the allowlist: fails loud with its name, nothing pushed',
          (code, 'UNSTAGED TRACKED OUTPUTS' in out and 'odds_moves.jsonl' in out, s.tip() == tip0), (1, True, True))
finally:
    s.close()

# ---- real run ----
s, code, out, steps, tip0, head0 = scene_run('real')
try:
    check('real: exit 0', code, 0)
    check('real: every workflow step ran, in order', steps, FULL)
    check('real: origin main moved by exactly one commit on the old tip',
          (s.git(s.origin, 'rev-parse', 'main~1'), s.git(s.origin, 'rev-list', '--count', f'{tip0}..main')), (tip0, '1'))
    check('real: authored AND committed by the owner', s.git(s.origin, 'log', '-1', '--format=%an|%ae', 'main') + '/' +
          s.git(s.origin, 'log', '-1', '--format=%cn|%ce', 'main'), OWNER + '/' + OWNER)
    msg = s.git(s.origin, 'log', '-1', '--format=%B', 'main')
    check('real: the workflow\'s commit subject', msg.splitlines()[0],
          'Record write: graded finals applied from record_request.json (ESPN-verified, ledger-exact) [record-final]')
    # the whole message, exactly: the subject and the one run-locally line, so no trailer or extra line can ride along
    check('real: the commit message is exactly the two expected paragraphs', msg,
          'Record write: graded finals applied from record_request.json (ESPN-verified, ledger-exact) [record-final]\n\n'
          'Run locally by scripts/record_final_local.sh (GitHub Actions record-final fallback).')
    files = sorted(s.git(s.origin, 'diff', '--name-only', f'{tip0}..main').splitlines())
    check('real: only allowlisted record files committed', files,
          ['history.json', 'index.html', 'manifest.json', 'record.html', 'record_done.json', 'record_request.json', 'yesterday.html'])
    check('real: says it landed', 'RECORD WRITE LANDED' in out, True)
    check('real: caller checkout untouched, nothing left behind', (s.git(s.work, 'rev-parse', 'HEAD') == head0, s.tidy()), (True, TIDY))
finally:
    s.close()

# ---- real run racing another writer (the fetch/rebase retry loop) ----
s = Scene()
try:
    tip0 = s.tip()
    race = (f'cd {s.other} && git pull -q origin main && echo tick >> futures_ticks.txt && git add futures_ticks.txt && '
            f'git -c user.name=bot -c user.email=b@b commit -qm "futures ws ticks" && git push -q origin main')
    code, out, steps = s.run(STUB_RACE_CMD=race)
    check('race (unrelated push mid-run): rebased over it and landed (exit 0)', code, 0)
    check('race: origin main = record write on top of the concurrent tick',
          (s.git(s.origin, 'log', '-1', '--format=%s', 'main~1'), s.git(s.origin, 'log', '-1', '--format=%s', 'main')[:13]),
          ('futures ws ticks', 'Record write:'))
    check('race: the rebased commit is still authored AND committed by the owner',
          s.git(s.origin, 'log', '-1', '--format=%an|%ae', 'main') + '/' + s.git(s.origin, 'log', '-1', '--format=%cn|%ce', 'main'),
          OWNER + '/' + OWNER)
    check('race: tidy', s.tidy(), TIDY)
finally:
    s.close()
s = Scene()
try:
    race = (f'cd {s.other} && git pull -q origin main && python3 -c "import json;m=json.load(open(\'manifest.json\'));'
            f'm[\'picks\']=[1];json.dump(m,open(\'manifest.json\',\'w\'))" && git add manifest.json && '
            f'git -c user.name=bot -c user.email=b@b commit -qm "card" && git push -q origin main')
    code, out, steps = s.run(STUB_RACE_CMD=race)
    check('race (manifest.json pushed mid-run): fails loud, the record write does not land',
          (code, s.git(s.origin, 'log', '-1', '--format=%s', 'main')), (1, 'card'))
    check('race (manifest.json): tidy', s.tidy(), TIDY)
finally:
    s.close()

# ---- mirror: the workflow's own gate files, allowlist and commands ----
wf = open(os.path.join(ROOT, '.github', 'workflows', 'record_final.yml')).read()
sh = open(SCRIPT).read()
wf_add = re.search(r'^\s*git add (.+)$', wf, re.M).group(1).strip()
sh_add = re.search(r"^ALLOWLIST='(.+)'$", sh, re.M).group(1)
check('mirror: commit allowlist == the workflow\'s git add line', sh_add, wf_add)
wf_gate = re.search(r'git diff --quiet -- (.+?) 2>/dev/null', wf).group(1).strip()
sh_gate = re.search(r"^GATE_FILES='(.+)'$", sh, re.M).group(1)
check('mirror: changed-gate files == the workflow\'s', sh_gate, wf_gate)
act = open(os.path.join(ROOT, '.github', 'actions', 'hold-check', 'action.yml')).read()
check('mirror: the workflow\'s hold-check runs the gate with --hold', ('ARGS="--hold"' in act, 'node scripts/health_gate.js $ARGS' in act), (True, True))
check('mirror: the script runs the gate with --hold', 'node scripts/health_gate.js --hold' in sh, True)
for cmd in ('python3 scripts/record_final.py', 'python3 scripts/build_history.py history.json',
            'RP_REFRESH=1 python3 scripts/_build_nocanon_v2.py manifest.json index.html', 'bash scripts/push_with_guard.sh',
            "blocks=[b for b in re.findall(r'<script>(.*?)</script>', s, re.S) if len(b)>50]"):
    check(f'mirror: {cmd!r} in the workflow and the script', (cmd in wf, cmd in sh), (True, True))

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
