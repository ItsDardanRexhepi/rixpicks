#!/usr/bin/env python3
"""Fixture: the private card-dollar size of 1u never lives in the public tree.
core/units.py and both finals_watch copies read it from the RIX_UNIT_DOLLARS environment
variable at call time (fail closed when unset), every importer still imports with it unset,
and the unit numbers come out the same whatever size is set (dollars cancel). Tracked
__pycache__ files (compiled copies of the old constant) are gone. The test value below is a
placeholder, not the private size. No side effects."""
import importlib.util, os, re, subprocess, sys
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
ENV = 'RIX_UNIT_DOLLARS'
TEST_SIZE = '40'  # placeholder size for the fixture only
failures = 0
def check(name, cond, detail=''):
    global failures
    print(('OK  ' if cond else 'FAIL'), name, '' if cond else detail)
    if not cond: failures += 1

def raises(fn):
    try: fn()
    except ValueError: return True
    except Exception as e: return 'wrong exception %s: %s' % (type(e).__name__, e)
    return False

os.environ.pop(ENV, None)
from core import units
import core.record_pipe  # importer: display_units
check('core.units and core.record_pipe import with the size unset', True)
check('cents_to_american works with the size unset', units.cents_to_american(57) == -133)
check('display_units works with the size unset', units.display_units(Decimal('1.005')) == '1.01')
check('pnl_to_units fails closed (ValueError) with the size unset', raises(lambda: units.pnl_to_units(Decimal('-30'))) is True)
src = open(os.path.join(ROOT, 'core', 'units.py')).read()
check('core/units.py assigns no literal dollar size', not re.search(r"UNIT_DOLLARS\s*=\s*Decimal\(\s*['\"]?\d", src))
check('core/units.py reads the size from %s' % ENV, ENV in src and hasattr(units, 'unit_dollars'))

for bad in ('', 'abc', '0', '-5', 'NaN', 'Infinity'):
    os.environ[ENV] = bad
    check('size %r refused (fail closed)' % bad, raises(lambda: units.unit_dollars()) is True if hasattr(units, 'unit_dollars') else False)
os.environ[ENV] = TEST_SIZE + '.00'
check('integral size canonicalizes to an exponent-0 Decimal', hasattr(units, 'unit_dollars') and str(units.unit_dollars()) == TEST_SIZE)
os.environ[ENV] = TEST_SIZE
check('legacy attribute units.UNIT_DOLLARS still resolves (from env)', getattr(units, 'UNIT_DOLLARS', None) == Decimal(TEST_SIZE))
check('pnl_to_units divides by the env size', units.pnl_to_units(Decimal('-80')) == Decimal('-2'))
# dollars cancel: the unit result of a win does not depend on the size
for u, am in ((Decimal('2'), -205), (Decimal('1.5'), 150), (Decimal('0.75'), -110), (Decimal('3'), 1050)):
    direct = u * am / 100 if am > 0 else u * 100 / abs(am)
    got = units.pnl_to_units(units.stake_pnl_american(u * units.unit_dollars(), am)) if hasattr(units, 'unit_dollars') else None
    check('win %su @%+d -> %s u, size-independent' % (u, am, float(direct)), got is not None and float(got) == float(direct), got)

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m
for rel in ('scripts/finals_watch.py', 'previews/overlay/scripts/finals_watch.py'):
    path = os.path.join(ROOT, rel)
    fsrc = open(path).read()
    check('%s: no hard-coded dollar stake' % rel, not re.search(r'stake\s*=\s*u\s*\*\s*Decimal\(\s*\d', fsrc))
    os.environ.pop(ENV, None)
    fw = load(path, 'fw_' + rel.replace('/', '_').replace('.', '_'))
    fw.fill_leak.card_price = lambda pick: (67, {'card_american': -205}, 1)
    fw.fill_leak.fill_divergence = lambda pick: []
    pick = {'game': {'eid': '1'}, 'side': 'home', 'kalshi': {'cents': 67}, 'odds': -205, 'units': '2u'}
    check('%s: grade fails closed with the size unset' % rel, raises(lambda: fw.grade(pick, {'home_score': 3, 'away_score': 1})) is True)
    os.environ[ENV] = TEST_SIZE
    r, pnl = fw.grade(pick, {'home_score': 1, 'away_score': 3})
    check('%s: loss stake comes from the env size' % rel, (r, pnl) == ('L', Decimal('-80')), r)  # never echo a dollar figure
    check('%s: loss is exactly -2u' % rel, fw.units.pnl_to_units(pnl) == Decimal('-2'))
    r, pnl = fw.grade(pick, {'home_score': 3, 'away_score': 1})
    check('%s: win at -205 is 2*100/205 u' % rel, r == 'W' and float(fw.units.pnl_to_units(pnl)) == float(Decimal(200) / 205))

# a push (spread/total/prop/ML tie) grades to 0 dollars before any dollar size is read; turning it
# into units still needs the size, so with the size unset the chain must stop with the same clear
# fail-closed WARN as a W/L grade - never an uncaught traceback (privacy review of the env move)
import contextlib, io, json, tempfile
from datetime import datetime
from zoneinfo import ZoneInfo
for rel in ('scripts/finals_watch.py', 'previews/overlay/scripts/finals_watch.py'):
    os.environ.pop(ENV, None)
    fw = load(os.path.join(ROOT, rel), 'fwpush_' + rel.replace('/', '_').replace('.', '_'))
    tmp = tempfile.mkdtemp(prefix='fw_push_')
    man = {'date': datetime.now(ZoneInfo('America/Los_Angeles')).strftime('%Y-%m-%d'), 'date_label': 'fixture', 'picks': [
        {'name': 'Aces -11', 'market_class': 'spread', 'line': -11, 'side': 'home', 'odds': '-110', 'units': '5u',
         'espn_league': 'basketball/wnba', 'kalshi': {'cents': 52},
         'game': {'away': 'Indiana Fever', 'home': 'Las Vegas Aces', 'commence': '2026-10-02T02:00Z', 'eid': '401918022'}}]}
    json.dump(man, open(os.path.join(tmp, 'manifest.json'), 'w'))
    fw.MANIFEST = os.path.join(tmp, 'manifest.json'); fw.STATE = os.path.join(tmp, 'seen.json'); fw.LEDGER = os.path.join(tmp, 'rows.jsonl')
    fw.TOKEN_PATH = os.path.join(tmp, 'no_token')
    fw.load_seen = lambda: {}
    fw.record_pipe.verified_grade_ids = lambda ledger: []
    fw.record_pipe.current_state = lambda ledger: (21, 11, Decimal('4.761952343474163'))
    # ESPN core gives each side's abbreviation with the score; finals_watch refuses a final without them
    # (the queued score must parse in record_final), so the stub carries them as the real final does
    fw.espn_final = lambda lg, eid: {'home_score': 94, 'away_score': 83, 'completed': True, 'home_abbr': 'LV', 'away_abbr': 'IND'}
    fw.second_source = lambda pick, primary, commence: {'source': 'fixture second source'}
    fw.two_source_ok = lambda primary, secondary: True
    argv0 = sys.argv; sys.argv = ['finals_watch.py', '--dry-run']
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            fw.main()
        crashed = None
    except Exception as e:
        crashed = '%s: %s' % (type(e).__name__, e)
    finally:
        sys.argv = argv0
    log = out.getvalue()
    check('%s: a spread push with the size unset stops the chain cleanly (no traceback)' % rel, crashed is None, crashed)
    check('%s: the push stop says why (%s, fail closed)' % (rel, ENV), 'chain STOPS' in log and ENV in log and 'FINAL-CHAIN' not in log, log[-300:])
    os.environ[ENV] = TEST_SIZE
    out = io.StringIO(); sys.argv = ['finals_watch.py', '--dry-run']
    try:
        with contextlib.redirect_stdout(out):
            fw.main()
    finally:
        sys.argv = argv0
    check('%s: with the size set the push grades (P, record unchanged, 0 units)' % rel,
          'FINAL-CHAIN(dry) 401918022|spread|home|-11' in out.getvalue() and '-> PUSH 21-11' in out.getvalue(), out.getvalue()[-300:])
    os.environ.pop(ENV, None)
    import shutil; shutil.rmtree(tmp, ignore_errors=True)

# Nothing that runs in GitHub Actions needs the private size, so it lives only on the grading host:
# record_final.py (the Actions record write) never reads the private size, no workflow names the env,
# and no script a workflow runs - followed through the shell scripts it calls and every repo module
# it imports - reads the size. (Importing core.units for cents_to_american/display_units is fine:
# that needs no size.) The fixtures tests.yml runs set their own placeholder.
import ast, glob
SIZE_READ = re.compile(r'\bunit_dollars\s*\(|\bpnl_to_units\s*\(|\bUNIT_DOLLARS\b')
def _mod_files(name, here):
    parts = name.split('.')
    cands = (os.path.join(ROOT, *parts) + '.py', os.path.join(ROOT, *parts, '__init__.py'),
             os.path.join(here, *parts) + '.py', os.path.join(ROOT, 'scripts', *parts) + '.py')
    return [c for c in cands if os.path.exists(c)]
def _closure(start):
    seen, todo = set(), [start]
    while todo:
        f = todo.pop()
        if f in seen: continue
        seen.add(f)
        src = open(f, encoding='utf-8', errors='ignore').read()
        if f.endswith('.sh'):
            todo += [os.path.join(ROOT, m) for m in re.findall(r'((?:scripts|core)/[\w/.-]+\.(?:py|sh))', src)
                     if os.path.exists(os.path.join(ROOT, m))]
            continue
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                tree = ast.parse(src)
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names: todo += _mod_files(a.name, os.path.dirname(f))
            elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
                todo += _mod_files(n.module, os.path.dirname(f))
                for a in n.names: todo += _mod_files(n.module + '.' + a.name, os.path.dirname(f))
    return seen
UNITS_PY = os.path.join(ROOT, 'core', 'units.py')
# CLV may import pure conversion/display helpers; no path in this closure may read the private size.
_record_closure = _closure(os.path.join(ROOT, 'scripts', 'record_final.py'))
_record_size_reads = [os.path.relpath(f, ROOT) for f in _record_closure if f != UNITS_PY and SIZE_READ.search(open(f, encoding='utf-8', errors='ignore').read())]
check('record_final.py never reads the private dollar size (directly or through its imports)', not _record_size_reads, _record_size_reads)
_env_no_size = dict(os.environ); _env_no_size.pop(ENV, None)
_import_check = subprocess.run([sys.executable, '-c', "import sys;sys.path.insert(0,'scripts');import record_final"], cwd=ROOT, env=_env_no_size, capture_output=True, text=True)
check('record_final.py imports with the size unset', _import_check.returncode == 0, _import_check.stderr[-300:])
wf_named, wf_reads = [], []
for wf in sorted(glob.glob(os.path.join(ROOT, '.github', 'workflows', '*.yml'))):
    txt = open(wf).read()
    if ENV in txt: wf_named.append(os.path.basename(wf))
    for m in set(re.findall(r'((?:scripts|core|previews)/[\w/.-]+\.(?:py|sh))', txt)):
        if not os.path.exists(os.path.join(ROOT, m)): continue
        for f in _closure(os.path.join(ROOT, m)):
            if f != UNITS_PY and SIZE_READ.search(open(f, encoding='utf-8', errors='ignore').read()):
                wf_reads.append('%s -> %s -> %s' % (os.path.basename(wf), m, os.path.relpath(f, ROOT)))
check('no workflow names %s' % ENV, not wf_named, wf_named)
check('no script any workflow runs reads the size (so Actions never needs the env)', not wf_reads, sorted(set(wf_reads))[:4])

tracked = subprocess.run(['git', '-C', ROOT, 'ls-files'], capture_output=True, text=True).stdout.split('\n')
pyc = [p for p in tracked if '__pycache__/' in p]
check('no tracked __pycache__ files (compiled copies of the old constant)', not pyc, pyc[:3])

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
