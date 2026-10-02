#!/usr/bin/env python3
"""Pre-push workflow sanity: every .github/workflows/*.yml must parse as YAML and carry
jobs. Catches the 9/27 dd0e7a2 break (unindented lines ending a run: | block scalar early)
before push. Also flags any env map (workflow, job, step, container, service) whose keys
collide case-insensitively, exact duplicates included: GitHub reads env names
case-insensitively and rejects the whole file (Oct 2: http_proxy next to HTTP_PROXY in
tests.yml parsed as YAML, so the run silently never started). Exit 1 on any violation."""
import glob, sys
try:
    import yaml
except ImportError:
    sys.exit('pyyaml required')

def env_collisions(node, where=''):
    """(map path, line, [keys]) for every env mapping in the composed node tree whose keys
    collide case-insensitively. Walks nodes, not the loaded dict, so a duplicate key the
    loader would silently collapse is still seen."""
    out = []
    if isinstance(node, yaml.MappingNode):
        for k, v in node.value:
            key = k.value if isinstance(k, yaml.ScalarNode) else '?'
            sub = (where + '.' if where else '') + str(key)
            if key == 'env' and isinstance(v, yaml.MappingNode):
                seen = {}
                for ek, _ in v.value:
                    if isinstance(ek, yaml.ScalarNode):
                        seen.setdefault(ek.value.lower(), []).append(ek)
                for group in seen.values():
                    if len(group) > 1:
                        out.append((sub, group[-1].start_mark.line + 1, [g.value for g in group]))
            out.extend(env_collisions(v, sub))
    elif isinstance(node, yaml.SequenceNode):
        for i, item in enumerate(node.value):
            out.extend(env_collisions(item, '%s[%d]' % (where, i)))
    return out

bad = []
for path in sorted(glob.glob('.github/workflows/*.yml')):
    try:
        d = yaml.safe_load(open(path))
        if not isinstance(d, dict) or 'jobs' not in d:
            bad.append(path + ': parses but no jobs key')
            continue
        for where, line, keys in env_collisions(yaml.compose(open(path))):
            bad.append('%s:%d: %s has keys that collide case-insensitively (GitHub rejects the file): %s'
                       % (path, line, where, ', '.join(keys)))
    except Exception as e:
        bad.append(path + ': ' + str(e).split('\n')[0])
if bad:
    print('\n'.join(bad)); sys.exit(1)
print('workflow YAML OK: ' + ', '.join(sorted(glob.glob('.github/workflows/*.yml'))))
