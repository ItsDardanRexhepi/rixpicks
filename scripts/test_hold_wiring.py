#!/usr/bin/env python3
"""Static wiring fixture for the posting-job auto-hold (Julian 9/30). No side effects.
Every posting workflow must: have a hold-check job using ./.github/actions/hold-check; gate its
main job with needs: hold-check and the exact fail-closed condition; expose the hold_bypass dispatch
input. The composite action must not exempt manual dispatch. --selfbite proves each check bites by
mutating copies in memory and requiring a failure."""
import copy, sys, yaml
POSTING = ['x_feed','odds_refresh','news_refresh','predictions','official_video','extras_sweep',
           'nfl_scores','wooder_td','publish','record_final']
COND = "${{ !cancelled() && needs.hold-check.result == 'success' && needs.hold-check.outputs.held == 'false' }}"
def load(n): return yaml.safe_load(open('.github/workflows/%s.yml' % n))
def problems(name, wf, action_text):
    p = []
    jobs = wf.get('jobs', {})
    hc = jobs.get('hold-check')
    if not hc: return ['%s: no hold-check job' % name]
    if not any(s.get('uses') == './.github/actions/hold-check' for s in hc.get('steps', [])):
        p.append('%s: hold-check job does not use the composite action' % name)
    if 'held' not in (hc.get('outputs') or {}): p.append('%s: hold-check job has no held output' % name)
    mains = [k for k in jobs if k != 'hold-check']
    if not mains: p.append('%s: no gated main job' % name)
    for k in mains:
        j = jobs[k]
        need = j.get('needs'); need = [need] if isinstance(need, str) else (need or [])
        if 'hold-check' not in need: p.append('%s: job %s missing needs: hold-check' % (name, k))
        if j.get('if') != COND: p.append('%s: job %s if-condition is not the exact fail-closed form' % (name, k))
    on = wf.get(True, wf.get('on', {}))
    wd = (on or {}).get('workflow_dispatch') or {}
    if 'hold_bypass' not in (wd.get('inputs') or {}): p.append('%s: workflow_dispatch lacks the hold_bypass input' % name)
    return p
def action_problems(t):
    p = []
    if 'exempt' in t.lower() and 'is exempt' in t.lower(): p.append('action: manual dispatch exemption present')
    if 'GATE ERROR' not in t or 'failing closed' not in t: p.append('action: gate error does not fail closed')
    if 'hold_bypass' not in t and 'HC_BYPASS' not in t: p.append('action: no explicit repair bypass')
    return p
def run():
    t = open('.github/actions/hold-check/action.yml').read()
    out = action_problems(t)
    for n in POSTING: out += problems(n, load(n), t)
    return out
def selfbite():
    t = open('.github/actions/hold-check/action.yml').read()
    bad = 0
    for n in POSTING:
        wf = load(n); main = [k for k in wf['jobs'] if k != 'hold-check'][0]
        muts = []
        m = copy.deepcopy(wf); del m['jobs']['hold-check']; muts.append(('drop hold-check job', m))
        m = copy.deepcopy(wf); m['jobs'][main].pop('needs', None); muts.append(('drop needs', m))
        m = copy.deepcopy(wf); m['jobs'][main]['if'] = "${{ !cancelled() && needs.hold-check.outputs.held != 'true' }}"; muts.append(('fail-open condition', m))
        m = copy.deepcopy(wf); m.get(True, m.get('on'))['workflow_dispatch'] = {}; muts.append(('drop hold_bypass input', m))
        for label, mm in muts:
            if not problems(n, mm, t):
                print('SELFBITE MISS %s: mutation "%s" not detected' % (n, label)); bad += 1
    if not action_problems(t.replace('failing closed', '')): print('SELFBITE MISS action: fail-open edit not detected'); bad += 1
    print('selfbite: %d misses' % bad); return bad
if __name__ == '__main__':
    pr = run()
    for x in pr: print('FAIL', x)
    print('wiring: %s' % ('OK (%d posting workflows)' % len(POSTING) if not pr else '%d FAIL' % len(pr)))
    sb = selfbite() if '--selfbite' in sys.argv else 0
    sys.exit(1 if pr or sb else 0)
