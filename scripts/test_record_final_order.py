"""Standing guard: record_final.yml must apply graded finals (record_final.py writes
history.json/manifest.json) BEFORE rebuilding record.html/yesterday.html (build_history.py),
and the commit allowlist must stage both the ledger inputs and the regenerated record pages.
Incident class: record.html built before the history row lands serves a stale record.
Bite-proven: reordering the steps or dropping an allowlist entry fails this test."""
import re, sys

yml = open('.github/workflows/record_final.yml').read()
fails = []

def step_pos(marker):
    i = yml.find(marker)
    return i if i >= 0 else None

apply_i = step_pos('scripts/record_final.py')
hist_i = step_pos('scripts/build_history.py')
build_i = step_pos('_build_nocanon_v2.py')

if apply_i is None: fails.append('record_final.py apply step missing')
if hist_i is None: fails.append('build_history.py step missing')
if build_i is None: fails.append('_build_nocanon_v2.py rebuild step missing')
if None not in (apply_i, hist_i, build_i):
    if not (apply_i < build_i and apply_i < hist_i):
        fails.append('ORDER: record_final.py must run before the page rebuilds (stale record.html class)')
# record.html/yesterday.html must be produced AFTER the row write, i.e. by the post-apply
# rebuild step, and staged in the same commit as history.json.
add_m = re.search(r'git add ([^\n]+)', yml)
if not add_m: fails.append('git add allowlist line missing')
else:
    add = add_m.group(1)
    for need in ('history.json', 'record.html', 'yesterday.html', 'manifest.json'):
        if need not in add: fails.append(f'allowlist missing {need} - regenerated record page could ship unstaged')
# the rebuild step must not run before the apply step's history write: guard the exact
# step-name sequence as a second tripwire (name anchors survive refactors of run bodies)
names = re.findall(r'- name: (.+)', yml)
def npos(frag):
    for i, n in enumerate(names):
        if frag in n: return i
    return None
if npos('apply graded finals') is None or npos('rebuild site') is None:
    fails.append('step names changed - re-anchor this guard')
elif npos('apply graded finals') > npos('rebuild site'):
    fails.append('ORDER(names): apply step moved after rebuild step')

print('FAILS:', fails if fails else 'none')
sys.exit(1 if fails else 0)
