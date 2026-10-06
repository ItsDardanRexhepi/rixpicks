"""Soccer results on the scope the contract settles on: regulation time.

Kalshi's soccer game, spread and total contracts (KXMLSGAME, KXNWSLGAME and their spread and total
series) settle after 90 minutes plus stoppage time. Extra time and a penalty shootout never count.
A level score after 90 minutes resolves the TIE contract yes and both team contracts no. So a pick
that a team wins is LOST on a draw for either side, never a push. A total is graded on regulation
goals only.

ESPN's final score includes extra-time goals (a 1-1 match at 90 minutes that ends 2-1 after extra
time reads 2-1), so no grader reads the regulation score off the final. regulation_score() takes it
from the summary's period line scores and checks it two ways before anyone grades on it:
  - the periods add up to ESPN's final, and the count of periods fits the final state
    (2 for full time, 4 after extra time, 5 with a shootout);
  - the regulation goals equal the goal events ESPN logs in periods 1-2 (own goals included,
    shootout kicks never).
Anything it cannot establish raises ValueError: the caller refuses to grade (fail closed).

outcome() turns the regulation score into WON / LOST / PUSH for one pick. scripts/record_final.py,
scripts/finals_watch.py and scripts/predictions.py all grade soccer through these two functions.
"""
from decimal import Decimal, InvalidOperation

SOCCER_PREFIX = 'soccer/'
# ESPN status names of a finished match -> number of line-score periods it must carry
FINAL_PERIODS = {
    'STATUS_FULL_TIME': 2,   # regular season: 90 minutes plus stoppage
    'STATUS_FINAL': 2,
    'STATUS_FINAL_AET': 4,   # after extra time: two 15-minute periods follow regulation
    'STATUS_FINAL_PEN': 5,   # after a shootout: the fifth line score is the shootout, never a goal
}
REGULATION_PERIODS = (1, 2)


def is_soccer(league):
    """True for an ESPN soccer league path ('soccer/usa.1' MLS, 'soccer/usa.nwsl' NWSL, ...)."""
    return str(league or '').startswith(SOCCER_PREFIX)


def _goals(v, what):
    """A non-negative whole goal count from an ESPN value ('1', 1, 1.0); anything else raises."""
    if isinstance(v, bool):
        raise ValueError(f'{what} is not a goal count ({v!r})')
    try:
        d = Decimal(str(v).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f'{what} is not a goal count ({v!r})') from None
    if not d.is_finite() or d < 0 or d != d.to_integral_value():
        raise ValueError(f'{what} is not a goal count ({v!r})')
    return int(d)


def regulation_score(summary):
    """The regulation score of a finished match, from ESPN's soccer summary
    (site.api .../summary?event=<id>).

    Returns {'home': n, 'away': n, 'final_home': n, 'final_away': n, 'status': <ESPN status name>,
    'extra_time': bool, 'shootout': bool}. 'home'/'away' are the goals after 90 minutes plus
    stoppage; 'final_*' is ESPN's final, which counts extra time but never the shootout.
    Raises ValueError when the match is not final or any check fails."""
    comps = ((summary or {}).get('header') or {}).get('competitions') or []
    if len(comps) != 1 or not isinstance(comps[0], dict):
        raise ValueError(f'summary carries {len(comps)} competitions, need exactly 1')
    comp = comps[0]
    st = (comp.get('status') or {}).get('type') or {}
    name = st.get('name')
    if st.get('completed') is not True or st.get('state') != 'post':
        raise ValueError(f'match is not final ({name!r})')
    if name not in FINAL_PERIODS:
        raise ValueError(f'final state {name!r} has no regulation rule here')
    periods = FINAL_PERIODS[name]
    played = min(periods, 4)  # periods whose goals count in ESPN's final (a shootout never does)
    sides = {}
    for c in comp.get('competitors') or []:
        ha = c.get('homeAway')
        if ha not in ('home', 'away') or ha in sides:
            raise ValueError(f'competitors are not one home and one away ({ha!r})')
        ls = c.get('linescores')
        if not isinstance(ls, list) or len(ls) != periods:
            n = len(ls) if isinstance(ls, list) else None
            raise ValueError(f'{ha} line score has {n} periods; {name} needs {periods}')
        per = [_goals((x or {}).get('displayValue', (x or {}).get('value')), f'{ha} period {i + 1}')
               for i, x in enumerate(ls)]
        final = _goals(c.get('score'), f'{ha} final score')
        if sum(per[:played]) != final:
            raise ValueError(f'{ha} periods {per[:played]} do not add up to the final {final}')
        sides[ha] = {'reg': per[0] + per[1], 'final': final, 'team_id': str((c.get('team') or {}).get('id') or '')}
    if set(sides) != {'home', 'away'}:
        raise ValueError('competitors are not one home and one away')
    # second check: the goal events ESPN logs in periods 1-2 (own goals count once, shootout kicks never)
    logged = 0
    for ev in summary.get('keyEvents') or []:
        if not isinstance(ev, dict) or ev.get('scoringPlay') is not True or ev.get('shootout') is True:
            continue
        if (ev.get('period') or {}).get('number') in REGULATION_PERIODS:
            logged += 1
    reg_total = sides['home']['reg'] + sides['away']['reg']
    if logged != reg_total:
        raise ValueError(f'line scores give {reg_total} regulation goals but {logged} goal events are logged in periods 1-2')
    return {'home': sides['home']['reg'], 'away': sides['away']['reg'],
            'final_home': sides['home']['final'], 'final_away': sides['away']['final'],
            'status': name, 'extra_time': periods >= 4, 'shootout': periods == 5}


def outcome(scope, side, market_class='ml', line=None):
    """WON / LOST / PUSH of one soccer pick on the score its contract settles on.

    scope: that score, {'home': n, 'away': n} (regulation_score's result).
    side: home|away for ml and spread, over|under for total.
    line: the HOME spread (negative when home is favored) or the game total.
    ml is the three-way team-win contract: a draw is LOST for either side.
    Returns None when the market, side or line cannot be graded from a score."""
    try:
        h, a = _goals(scope['home'], 'home goals'), _goals(scope['away'], 'away goals')
    except (KeyError, TypeError, ValueError):
        return None
    if market_class == 'ml':
        if side not in ('home', 'away'):
            return None
        if h == a:
            return 'LOST'
        return 'WON' if (side == 'home') == (h > a) else 'LOST'
    if market_class not in ('spread', 'total'):
        return None
    if isinstance(line, bool):
        return None
    try:
        ln = Decimal(str(line))
    except (InvalidOperation, ValueError):
        return None
    if not ln.is_finite():
        return None
    if market_class == 'spread':
        if side not in ('home', 'away'):
            return None
        diff = Decimal(h) + ln - Decimal(a)  # >0 home covers
        if diff == 0:
            return 'PUSH'
        return 'WON' if (side == 'home') == (diff > 0) else 'LOST'
    if side not in ('over', 'under'):
        return None
    tot = Decimal(h + a)
    if tot == ln:
        return 'PUSH'
    return 'WON' if (side == 'over') == (tot > ln) else 'LOST'
