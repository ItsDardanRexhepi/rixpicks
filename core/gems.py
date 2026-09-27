"""J-119 gem screen -> carding. gem_check (in hunt_v2.py) is the SCREEN. This is the BAR:
a gem cards only with a validated J-122 binding + two evidence-backed checks, executed
through the J-120 chain."""
from core.card_gate import card_eligible
from core.intraday import add_pick
def card_gem(entry, binding, check1, check2, card_append, push, record_chain, ledger_path, now=None):
    pick = {'event_id': entry['instance_id'], 'match': entry['match'],
            'market_class': entry.get('market_class', 'ml'), 'side': entry['side'],
            'entry_c': round(entry['ask'] * 100, 1)}
    gate = card_eligible(binding, pick['market_class'], pick['event_id'], pick['side'], now)
    return add_pick(pick, gate, check1, check2, card_append, push, record_chain, ledger_path)
