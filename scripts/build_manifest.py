#!/usr/bin/env python3
"""Durable card manifest builder. CARD PRICE BASIS (his call 9/26 10:14 PM PT,
phonemsg-01M3GMJBQVQX5099CH3AN4TB3E): card_american converts from the KALSHI ASK the gate
consumed (units.cents_to_american), card_source = 'Kalshi ask at lock', and the card shows the
gate's own numbers (model vs Kalshi ask, gross/net edge) - never book-consensus display.
Forward-only: previously published cards keep their published prices.
Usage: build_manifest.py candidates.json out_manifest.json [--preview]
candidate row: {num,name,side,away,home,commence,eid,espn_league,units,kalshi:{cents,team,url,ticker},model,gross_c,net_c}"""
import json, sys, datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, '/home/sandbox/rix_tmp')
from core.units import cents_to_american

def main():
    cands = json.load(open(sys.argv[1]))
    preview = '--preview' in sys.argv
    out = sys.argv[2] if not sys.argv[2].startswith('--') else sys.argv[3]
    now = datetime.datetime.now(ZoneInfo('America/Los_Angeles')).isoformat(timespec='seconds')
    picks = []
    for c in cands:
        cents = c['kalshi']['cents']
        if not isinstance(cents, int) or not (1 <= cents <= 99):
            raise ValueError(f"fail closed: bad kalshi cents {cents!r} on {c.get('name')}")
        am = cents_to_american(cents)
        picks.append({
            'num': c['num'], 'name': c['name'],
            'sub': f"{c.get('sub_context','')} - model {c['model']:.1f}, exchange {cents}c ask, gross {c['gross_c']:+.1f}c net {c['net_c']:+.1f}c".strip(' -'),
            'odds': f"{am:+d}", 'units': c['units'], 'side': c['side'],
            'game': {'away': c['away'], 'home': c['home'], 'commence': c['commence'], 'eid': c['eid']},
            'espn_league': c['espn_league'], 'best_book': 'Kalshi',
            'kalshi': {'url': c['kalshi'].get('url','https://kalshi.com/markets/'+c['kalshi']['ticker'].split('-')[0].lower()),
                       'cents': cents, 'team': c['kalshi']['team'], 'gate_cents': cents,
                       'ticker': c['kalshi']['ticker']},
            'card_american': am, 'card_source': 'Kalshi ask at lock', 'card_ts': now,
            'polymarket': c.get('polymarket'), 'dkp': c.get('dkp')})
    manifest = {'date': cands[0].get('date') if cands else None, 'preview': preview, 'picks': picks}
    json.dump(manifest, open(out, 'w'), indent=1)
    print(f"wrote {out}: {len(picks)} picks, preview={preview}")
    for p in picks: print(f"  #{p['num']} {p['name']} {p['units']} @{p['odds']} (Kalshi {p['kalshi']['cents']}c) | {p['sub']}")
if __name__ == '__main__': main()
