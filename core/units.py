"""UNIT BASIS (final, 9/26 8:33 PM via main): canonical = card stake at locked price, $15/u.
Store exact, display half-up 2dp. Actual-cash fills live in positions ledger only, never public record."""
from decimal import Decimal, ROUND_HALF_UP
UNIT_DOLLARS = Decimal('15')
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
    return Decimal(str(pnl_dollars)) / UNIT_DOLLARS
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
