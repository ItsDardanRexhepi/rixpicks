"""Canonical spread-line formatter (his verbatim 10:45 PM PT, phonemsg-01M3GPAMSD4J5TBA9CKDJ854VX,
relayed via main): spread wagers ALWAYS render as team +/- number + side - "CLE -1.5 NO",
NEVER "CLE by >1.5: NO". No '>' or '<' on any card, preview, ladder display, pipeline output,
or social copy. CORE-LEVEL single source of truth - every surface consumes this module.

The number shown is the actual spread for that wager: negative = team gives points,
positive = team gets points, 0 = pick'em."""
def fmt_spread(team, line, side=None):
    team = (team or '').strip()
    if not team: raise ValueError('fmt_spread: empty team')
    line = float(line)
    if line > 0: body = f"{team} +{abs(line):g}"
    elif line < 0: body = f"{team} -{abs(line):g}"
    else: body = f"{team} PK"
    out = f"{body} {side}" if side else body
    assert '>' not in out and '<' not in out  # contract guard: the banned symbols can never emit
    return out

def check_no_angle(s):
    """Surface-side assertion: any rendered spread string containing > or < fails loud."""
    if '>' in s or '<' in s: raise ValueError(f'banned spread notation in {s!r} - use core.linefmt.fmt_spread')
    return s
