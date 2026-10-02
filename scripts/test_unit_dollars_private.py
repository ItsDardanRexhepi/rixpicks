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

tracked = subprocess.run(['git', '-C', ROOT, 'ls-files'], capture_output=True, text=True).stdout.split('\n')
pyc = [p for p in tracked if '__pycache__/' in p]
check('no tracked __pycache__ files (compiled copies of the old constant)', not pyc, pyc[:3])

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
