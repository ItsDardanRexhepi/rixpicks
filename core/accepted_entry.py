"""One explicitly accepted card entry, not evidence of a venue fill or settlement.

The approval reference is opaque; full attributed provenance is in the private
RixPicksSystem picks ledger. Match the locked public card exactly. No general
fallback from missing prices, current quotes, names, or arbitrary approval text.
"""
from copy import deepcopy
from decimal import Decimal

APPROVAL_REF = "accepted-entry-20261005-185743-401892445"
_SCOPE = {'name': 'Flyers +1.5',
 'market_class': 'spread',
 'line': -1.5,
 'odds': '-138',
 'units': '5u',
 'side': 'away',
 'game': {'away': 'Philadelphia Flyers',
          'home': 'Tampa Bay Lightning',
          'commence': '2026-10-05T23:00Z',
          'eid': '401892445'},
 'espn_league': 'hockey/nhl',
 'card_american': -138,
 'card_source': 'best ask at lock: Polymarket 58c',
 'card_ts': '2026-10-05T09:30:11-07:00'}
_ENTRY = {
    "kind": "pick", "accepted_entry_id": APPROVAL_REF,
    "event_id": "401892445", "market_class": "spread", "side": "away",
    "line": -1.5, "line_basis": "home", "entry_c": 58,
    "card_venue": "polymarket", "card_american": -138, "units": "5u",
    "card_ts": "2026-10-05T09:30:11-07:00",
    "entry_basis": "approved_card_entry_assumption",
}


def accepted_entry(pick):
    """Return this exact approved entry or None; mutable copies never change authority."""
    if any(pick.get(key) != value for key, value in _SCOPE.items()):
        return None
    # Do not silently override a later conflicting structured venue/price field.
    if any(key in pick for key in ("kalshi", "best_ask", "polymarket", "polymarket_us")):
        return None
    return deepcopy(_ENTRY)


def entry_delta(result, stake, entry):
    """Exact accepted cents; American odds on the card are rounded display only."""
    if entry != _ENTRY:
        raise ValueError("unrecognized accepted entry")
    if result in ("W", "WON"):
        cents = Decimal(entry["entry_c"])
        return stake * (Decimal(100) - cents) / cents
    if result in ("L", "LOST"):
        return -stake
    if result == "PUSH":
        return Decimal(0)
    raise ValueError("unknown result for accepted entry")
