"""UNIT BASIS: canonical = card stake at locked price; the record is unit-denominated.
The legacy card-dollar P&L conversion size (unit_dollars) is private: it is read from the RIX_UNIT_DOLLARS
environment variable at grade time and never committed, so no served file carries it.
Store exact, display half-up 2dp. Actual-cash fills live in positions ledger only, never public record."""
import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
UNIT_DOLLARS_ENV = 'RIX_UNIT_DOLLARS'
def unit_dollars():
    """Private card-dollar size of 1u, read from the environment at call time. Unset or invalid
    raises ValueError (fail closed: the grader stops the chain instead of writing a guessed number).
    An integral size comes back as an exponent-0 Decimal, so trailing zeros in the setting never change
    the exact math.
    The value is never echoed in errors or logs."""
    raw = os.environ.get(UNIT_DOLLARS_ENV, '').strip()
    try:
        v = Decimal(raw)
    except InvalidOperation:
        raise ValueError(f'{UNIT_DOLLARS_ENV} unset or not a number - REFUSING to convert dollars to units (fail closed)') from None
    if not v.is_finite() or v <= 0:
        raise ValueError(f'{UNIT_DOLLARS_ENV} must be a positive finite number - REFUSING to convert dollars to units (fail closed)')
    return Decimal(int(v)) if v == v.to_integral_value() else v
def __getattr__(name):
    # legacy readers of units.UNIT_DOLLARS keep working, now sourced from the environment
    if name == 'UNIT_DOLLARS':
        return unit_dollars()
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
def _price(p):
    p = Decimal(str(p))
    if not p.is_finite() or not (Decimal(0) < p <= Decimal(100)):
        raise ValueError(f'invalid price_c {p}: must be finite, 0 < p <= 100')
    return p
def _stake(s):
    s = Decimal(str(s))
    if not s.is_finite() or s < 0:
        raise ValueError(f'invalid stake {s}: must be finite and nonnegative')
    return s
def pnl_to_units(pnl_dollars):
    """Exact units from a card-stake dollar P&L. No rounding - store this value."""
    return Decimal(str(pnl_dollars)) / unit_dollars()
def stake_pnl(stake_dollars, price_c):
    """P&L of a WIN at locked price (cents of a 100c contract). Validates inputs."""
    s, p = _stake(stake_dollars), _price(price_c)
    return s * (Decimal(100) - p) / p
def _american(price):
    if isinstance(price, bool) or not isinstance(price, int):
        raise ValueError(f'american odds must be an int, got {price!r}')
    if -100 <= price < 100:
        raise ValueError(f'american odds invalid: {price} (need >= +100 or <= -101)')
    return price
def stake_pnl_american(stake_dollars, american):
    """P&L of a WIN at the published card price (American odds). Validates inputs.
    -205 -> stake*100/205; +150 -> stake*150/100. Exact Decimal from the first op."""
    s, a = _stake(stake_dollars), _american(american)
    return s * a / Decimal(100) if a > 0 else s * Decimal(100) / abs(a)
def display_units(u):
    """Half-up 2dp display of an exact unit value. NEVER store the displayed form."""
    return str(Decimal(u).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
def cents_to_american(price_c):
    """Kalshi ask cents -> int American for the PUBLISHED card price (his call 9/26 10:14 PM PT,
    phonemsg-01M3GMJBQVQX5099CH3AN4TB3E reply 'Show the Kalshi +/-': card price = the Kalshi
    executable he actually pays, forward-only; Toledo/NEB/MSST stay as published).
    57c -> -133, 40c -> +150, 50c -> +100 (even money is +100 by convention)."""
    p = _price(price_c)
    if p == Decimal(100):
        raise ValueError('100c has no American equivalent')
    if p > 50:
        a = -(Decimal(100) * p / (Decimal(100) - p)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    elif p < 50:
        a = ((Decimal(100) * (Decimal(100) - p)) / p).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    else:
        return 100
    a = int(a)
    return 100 if a == -100 else a
