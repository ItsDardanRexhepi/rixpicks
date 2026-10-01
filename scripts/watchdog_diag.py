"""Pure helpers for scripts/watchdog.py: which job failed, and what to quote from its log."""

def pick_failed_jobs(jobs):
    """Jobs that actually failed, in order. Falls back to cancelled/timed_out, then to
    the last job, so a diagnosis never quotes a job that succeeded (Sep 30 runs
    36813762832 + 36813810976 quoted the passing hold-check job because jobs[0] was used)."""
    jobs = jobs or []
    for want in (('failure',), ('timed_out', 'cancelled')):
        hit = [j for j in jobs if j.get('conclusion') in want]
        if hit:
            return hit
    return jobs[-1:] if jobs else []


def failing_steps(failed_jobs):
    out = []
    for j in failed_jobs:
        for s in j.get('steps', []):
            if s.get('conclusion') == 'failure':
                out.append('%s / %s' % (j.get('name', '?'), s.get('name', '?')))
    return out


def error_tail(lines, limit=1200):
    """Quote the lines leading up to the first ##[error] (the failing step's own output);
    otherwise the keyword hits, otherwise the last lines."""
    idx = next((i for i, l in enumerate(lines) if '##[error]' in l), None)
    if idx is not None:
        return '\n'.join(lines[max(0, idx - 14):idx + 1])[-limit:]
    hits = [l for l in lines if any(k in l.lower() for k in ('error', 'fail', 'conflict', 'fatal', 'traceback', 'refus'))]
    return '\n'.join(hits[-6:] or lines[-6:])[:limit]
