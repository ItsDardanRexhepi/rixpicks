"""FILL-LEAK GUARD (money-math guard error class, 9/26 MSST 66c-vs-card fork):
the public record's locked price comes ONLY from the card entry (picks ledger),
never from a positions-ledger cash fill. Binding is CANONICAL (swamp 9:39):
event_id + market_class + side, exactly one picks-ledger 'pick' row - missing or
ambiguous FAILS CLOSED in the grade path. One explicitly approved locked entry
is replicated in accepted_entry.py; an installed duplicate/conflict still refuses.
Word/name matching alone is banned here.
Positions fills bind on event_id and WARN only (fills at other venues are
legitimate; the leak is USING one as the card basis).
"""
import json
from core.accepted_entry import accepted_entry
PICKS_LEDGER = '/home/sandbox/rps_tmp/kb/ledger/picks.jsonl'
POSITIONS_LEDGER = '/home/sandbox/rps_tmp/kb/ledger/positions.jsonl'

def _rows(path):
    try:
        return [json.loads(l) for l in open(path) if l.strip()]
    except FileNotFoundError:
        return []

def card_price(pick, picks_path=PICKS_LEDGER):
    """(cents, row, n_matches) for the canonical card entry: kind=='pick' rows whose
    event_id + market_class + side ALL equal the manifest pick's. n != 1 means the
    card record is missing (0) or ambiguous (>1) - the caller REFUSES to grade.
    The one accepted_entry.py approval may supply an absent local copy; it never
    overrides conflicting or duplicate ledger rows."""
    eid = pick['game']['eid']
    side = pick['side']
    mc = pick.get('market_class', 'ml')
    hits = [r for r in _rows(picks_path)
            if r.get('kind') == 'pick'
            and str(r.get('event_id')) == str(eid)
            and r.get('market_class', 'ml') == mc
            and r.get('side') == side]
    if mc == 'prop':
        # prop identity includes player + market + line (multiple props per game);
        # normalized-name compare, line as float.
        import re as _re
        want_p = _re.sub(r'[^a-z0-9]', '', (pick.get('player') or '').lower())
        hits = [r for r in hits
                if _re.sub(r'[^a-z0-9]', '', (r.get('player') or '').lower()) == want_p
                and r.get('market') == pick.get('market')
                and float(r.get('line') or -1) == float(pick.get('line') or -2)]
    elif mc in ('spread', 'total') and pick.get('line') is not None:
        # alt lines of the same game+side are distinct picks
        hits = [r for r in hits if float(r.get('line') or -1) == float(pick['line'])]
    accepted = accepted_entry(pick)
    if accepted is not None:
        # This one owner-approved entry is replicated from the private picks ledger.
        # Reconcile an installed copy exactly; never mask conflicts or duplicates.
        if hits:
            if len(hits) != 1 or any(hits[0].get(k) != v for k, v in accepted.items()):
                raise ValueError('accepted-entry conflict or duplicate in picks ledger - REFUSING to grade')
        return accepted['entry_c'], accepted, 1
    if len(hits) == 1:
        return hits[0].get('entry_c'), hits[0], 1
    return None, None, len(hits)

def fill_divergence(pick, positions_path=POSITIONS_LEDGER):
    """Positions fills on the same event_id. WARN material, never a block."""
    eid = str(pick['game']['eid'])
    out, seen = [], set()
    for r in _rows(positions_path):
        if r.get('kind') not in ('position', 'settlement'):
            continue
        if str(r.get('event_id')) != eid:
            continue
        key = (r.get('id'), r.get('entry_c') or r.get('fill_c'))
        if key in seen:
            continue
        seen.add(key)
        out.append({'id': r.get('id'), 'fill_c': r.get('entry_c') or r.get('fill_c'),
                    'venue': r.get('venue')})
    return out
