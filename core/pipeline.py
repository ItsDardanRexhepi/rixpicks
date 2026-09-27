"""Stage 0 executable integration (J-121/J-122/J-123): odds_prefill_st -> st_screen
divergence flags -> per-flag Kalshi binding attempt -> J-122 gate -> output.
Everything stays screen-only unless a validated binding exists. Emits artifacts + run log."""
import json, sys
from datetime import datetime, timezone
sys.path.insert(0, '/home/sandbox/rps_tmp/kb')
from core.binding import KalshiBinding
from core.card_gate import card_eligible
def run_stage0(screen_rows, fetch_binding, now=None, log_lines=None):
    """screen_rows: st_screen output. fetch_binding(away, home, market_class) -> KalshiBinding|None.
    Returns {'screen_only': [...], 'cardable': [...]}. NOTHING cards here - carding still
    needs standards + 2 evidence checks through gems.card_gem."""
    log_lines = log_lines if log_lines is not None else []
    out = {'screen_only': [], 'cardable': []}
    for r in screen_rows:
        if not r.get('flags'): continue
        for cls in ('spread', 'total'):
            side = 'home' if cls == 'spread' else 'over'
            b = fetch_binding(r['away'], r['home'], cls)
            gate = card_eligible(b, cls, r.get('event_id', ''), side, now)
            rec = {'match': f"{r['away']} @ {r['home']}", 'class': cls, 'flags': r['flags'],
                   'gate': {'eligible': gate[0], 'why': gate[1]}}
            (out['cardable'] if gate[0] else out['screen_only']).append(rec)
            log_lines.append(f"{datetime.now(timezone.utc).isoformat()} {rec['match']} {cls}: gate={gate[0]} ({gate[1]})")
    return out
