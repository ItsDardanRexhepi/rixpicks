#!/usr/bin/env python3
"""Change-detect for the gated Pages deploy: deploy only when the gated tip differs from the
sha of the last SUCCESSFUL github-pages deployment. Any lookup problem -> deploy (the gate
still applies; a redundant deploy is harmless, a skipped one would freeze the site).
Env: GH_TOKEN, GITHUB_REPOSITORY, TIP, FORCE ('true' forces). Writes changed=/reason= to GITHUB_OUTPUT."""
import json, os, subprocess


def last_success_sha(deps):
    """deps: newest-first list of {'sha':..., 'state':...}; the first deployment whose latest
    status is success, else None."""
    for d in deps:
        if d.get('state') == 'success':
            return d.get('sha')
    return None


def decide(tip, last, force=False):
    if force:
        return 'true', 'forced'
    if not last:
        return 'true', 'no successful deployment found'
    if last == tip:
        return 'false', 'tip %s already deployed' % tip[:8]
    return 'true', 'tip %s differs from last deployed %s' % (tip[:8], last[:8])


def _gh(path):
    r = subprocess.run(['gh', 'api', path], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[:200])
    return json.loads(r.stdout)


def main():
    repo, tip = os.environ['GITHUB_REPOSITORY'], os.environ['TIP']
    force = os.environ.get('FORCE', '') == 'true'
    try:
        deps = []
        for d in _gh('repos/%s/deployments?environment=github-pages&per_page=10' % repo):
            st = _gh('repos/%s/deployments/%s/statuses?per_page=1' % (repo, d['id']))
            deps.append({'sha': d['sha'], 'state': st[0]['state'] if st else None})
        changed, reason = decide(tip, last_success_sha(deps), force)
    except Exception as e:
        changed, reason = 'true', 'lookup failed (%s), deploying' % str(e)[:120]
    print('changed=%s reason=%s' % (changed, reason))
    out = os.environ.get('GITHUB_OUTPUT')
    if out:
        with open(out, 'a') as f:
            f.write('changed=%s\nreason=%s\n' % (changed, reason))


if __name__ == '__main__':
    main()
