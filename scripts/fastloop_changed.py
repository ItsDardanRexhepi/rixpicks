"""Normalize a JSON feed for change detection in the fast loop: writes HEAD and
worktree copies with the volatile timestamp key stripped (per-row for list feeds).
Usage: fastloop_changed.py <path> <volatile_key> <old_out> <new_out>"""
import json, subprocess, sys

path, key, old_out, new_out = sys.argv[1:5]

def norm(text):
    try: d = json.loads(text)
    except Exception: return ''
    if isinstance(d, dict):
        d.pop(key, None)
        rows = [d]
    else:
        rows = d
    for r in rows:
        if isinstance(r, dict):
            r.pop(key, None)
            for v in r.values():
                if isinstance(v, dict): v.pop(key, None)
    return json.dumps(d, sort_keys=True)

old = subprocess.run(['git', 'show', 'HEAD:' + path], capture_output=True, text=True)
open(old_out, 'w').write(norm(old.stdout) if old.returncode == 0 else '')
open(new_out, 'w').write(norm(open(path).read()))
