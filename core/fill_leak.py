"""FILL-LEAK GUARD (money-math guard error class, 9/26 MSST 66c-vs-card fork):
the public record's locked price comes ONLY from the card entry (picks ledger /
manifest), never from a positions-ledger cash fill. Two checks:
1. manifest-vs-picks-ledger price equality for the same pick -> mismatch REFUSES
   (a forked card price means nobody knows what was published).
2. positions fill price for the same game != card price -> WARN only (fills at
   other venues are legitimate positions; the leak is USING one as the card basis).
"""
import json, os
PICKS_LEDGER = '/home/sandbox/rps_tmp/kb/ledger/picks.jsonl'
POSITIONS_LEDGER = '/home/sandbox/rps_tmp/kb/ledger/positions.jsonl'

def _rows(path):
    try:
        return [json.loads(l) for l in open(path) if l.strip()]
    except FileNotFoundError:
        return []

def _words(s):
    return {w for w in (s or '').lower().replace('-', ' ').split() if len(w) >= 4}

def _match(text_words, team):
    """A team matches when any distinctive (>=4 char) word of its name appears."""
    return bool(_words(team) & text_words)

def card_price(pick, picks_path=PICKS_LEDGER):
    """Locked card price (cents) for a manifest pick, matched by BOTH team names
    (word-overlap). Returns (cents, row) or (None, None) when no card entry exists."""
    home, away = pick['game']['home'], pick['game']['away']
    for r in _rows(picks_path):
        tw = _words(str(r.get('pick', '')) + ' ' + str(r.get('market', '')))
        if _match(tw, home) and _match(tw, away):
            return r.get('entry_c'), r
    return None, None

def fill_divergence(pick, positions_path=POSITIONS_LEDGER):
    """Positions fills for the same game whose entry price differs from the card
    price. WARN material, never a block."""
    home, away = pick['game']['home'], pick['game']['away']
    out = []
    seen = set()
    for r in _rows(positions_path):
        if r.get('kind') not in ('position', 'settlement'):
            continue
        tw = _words(str(r.get('market', '')) + ' ' + str(r.get('game', '')))
        if _match(tw, home) and _match(tw, away):
            key = (r.get('id'), r.get('entry_c') or r.get('fill_c'))
            if key in seen:
                continue
            seen.add(key)
            out.append({'id': r.get('id'), 'fill_c': r.get('entry_c') or r.get('fill_c'),
                        'venue': r.get('venue')})
    return out
