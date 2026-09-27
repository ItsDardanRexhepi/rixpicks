"""Stage 0 executable integration (J-121/J-122/J-123): st_screen flags -> per-flag canonical
Kalshi binding -> J-122 gate. fetch_binding(row, market_class, side) receives the FULL row
(with event_id/abbrs) and must bind on canonical identifiers. Rows without event identity
are screen-only by construction."""
import sys
from datetime import datetime, timezone
sys.path.insert(0, '/home/sandbox/rix_tmp')
from core.card_gate import card_eligible
def run_stage0(screen_rows, fetch_binding, now=None, log_lines=None):
    log_lines = log_lines if log_lines is not None else []
    out = {'screen_only': [], 'gate_passed': []}
    # gate_passed means ONLY: J-122 Kalshi-carried gate passed. NOT carded - every gate_passed
    # row still needs model fair + standards + the J-119/J-120 2-check bar via core.gems.card_gem.
    for r in screen_rows:
        if not r.get('flags'): continue
        for cls in ('spread', 'total'):
            side = 'home' if cls == 'spread' else 'over'
            rec = {'match': f"{r['away']} @ {r['home']}", 'class': cls, 'flags': r['flags'],
                   'event_id': r.get('event_id')}
            if not r.get('event_id'):
                rec['gate'] = {'eligible': False, 'why': 'screen-only: no event identity on row (J-112/J-122)'}
                out['screen_only'].append(rec)
                log_lines.append(f"{datetime.now(timezone.utc).isoformat()} {rec['match']} {cls}: gate=False ({rec['gate']['why']})")
                continue
            b = fetch_binding(r, cls, side)
            gate = card_eligible(b, cls, r['event_id'], side, now)
            rec['gate'] = {'eligible': gate[0], 'why': gate[1]}
            if gate[0]:
                rec['next'] = 'standards + model fair + 2-check bar (core.gems.card_gem) before ANY card - gate pass alone never cards'
                out['gate_passed'].append(rec)
            else:
                out['screen_only'].append(rec)
            log_lines.append(f"{datetime.now(timezone.utc).isoformat()} {rec['match']} {cls}: gate={gate[0]} ({gate[1]})")
    return out
