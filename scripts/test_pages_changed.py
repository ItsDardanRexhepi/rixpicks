#!/usr/bin/env python3
"""Fixture for scripts/pages_changed.py. --legacy swaps in an always-deploy decide() to prove
the fixture bites (an unchanged tip must NOT redeploy)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pages_changed as pc
decide = (lambda tip, last, force=False: ('true', 'legacy')) if '--legacy' in sys.argv else pc.decide
T, O = 'a' * 40, 'b' * 40
f = []
if decide(T, T)[0] != 'false': f.append('unchanged tip must not deploy')
if decide(T, O)[0] != 'true': f.append('moved tip must deploy')
if decide(T, None)[0] != 'true': f.append('no prior deployment must deploy')
if decide(T, T, True)[0] != 'true': f.append('force must deploy')
deps = [{'sha': O, 'state': 'failure'}, {'sha': T, 'state': 'success'}, {'sha': O, 'state': 'success'}]
if pc.last_success_sha(deps) != T: f.append('last_success_sha must skip failed deployments')
if pc.last_success_sha([{'sha': T, 'state': 'failure'}]) is not None: f.append('only-failed must yield None')
# a failed deployment of the current tip must NOT count as deployed
if decide(T, pc.last_success_sha([{'sha': T, 'state': 'failure'}]))[0] != 'true': f.append('failed tip deploy must retry')
if f: print('FAIL: ' + '; '.join(f)); sys.exit(1)
print('PASS pages_changed (skip unchanged, deploy moved/none/forced/failed)')
