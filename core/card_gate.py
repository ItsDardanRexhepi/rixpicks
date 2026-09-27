"""J-122 (AMENDED 9/26 9:10 PM, verbatim "it must at least be on Kalshi"):
a market class is CARD-ELIGIBLE only when Kalshi carries that market for that game,
proven by a validated binding (same event/class/side, open, live ask, fresh quote).
Polymarket not required. Book-only screens inform, never card."""
from core.binding import KalshiBinding
ELIGIBLE_CLASSES = {'ml', 'spread', 'total', 'parlay', 'futures', 'live'}  # J-121 ext; props gated J-123a
def card_eligible(binding, market_class, event_id, side, now=None):
    if market_class not in ELIGIBLE_CLASSES:
        return False, f'class {market_class} not card-eligible under current scope (props gated J-123a)'
    if not isinstance(binding, KalshiBinding):
        return False, 'screen-only: no Kalshi binding for this game+class (J-122)'
    ok, why = binding.validate(event_id, market_class, side, now)
    if not ok: return False, f'screen-only: binding failed - {why}'
    return True, f'Kalshi {binding.ticker} bound ({why}) - card-eligible'
