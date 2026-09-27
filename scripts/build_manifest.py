#!/usr/bin/env python3
"""Durable card manifest builder. CARD PRICE BASIS (his call 9/26 10:14 PM PT,
phonemsg-01M3GMJBQVQX5099CH3AN4TB3E): card_american converts from the KALSHI ASK the gate
consumed (units.cents_to_american), card_source = 'Kalshi ask at lock', and the card shows the
gate's own numbers (model vs Kalshi ask, gross/net edge) - never book-consensus display.
Forward-only: previously published cards keep their published prices.
Usage: build_manifest.py candidates.json out_manifest.json [--preview]
candidate row: {num,name,side,away,home,commence,eid,espn_league,units,kalshi:{cents,team,url,ticker},model,gross_c,net_c}"""
import json, sys, datetime, os
from zoneinfo import ZoneInfo
sys.path.insert(0, '/home/sandbox/rix_tmp')
from core.units import cents_to_american
from core.fill_leak import PICKS_LEDGER

def main():
    cands = json.load(open(sys.argv[1]))
    preview = '--preview' in sys.argv
    out = sys.argv[2] if not sys.argv[2].startswith('--') else sys.argv[3]
    now = datetime.datetime.now(ZoneInfo('America/Los_Angeles')).isoformat(timespec='seconds')
    picks = []
    for c in cands:
        cents = c['kalshi']['cents']
        if type(cents) is not int or not (1 <= cents <= 99):  # strict: bool is not int here
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
    # ATOMIC CARD LEDGER WIRING (swamp 10:16 PM block): the canonical kind='pick' ledger row
    # carrying entry_c + card_american + card_source + card_ts is written WITH the manifest,
    # not by a separate path - finals_watch.grade fails closed without exactly one matching row.
    ledger_rows = []
    existing = [json.loads(l) for l in open(PICKS_LEDGER)] if os.path.exists(PICKS_LEDGER) else []
    for c, p in zip(cands, picks):
        key = (str(c['eid']), c.get('market_class','ml'), c['side'])
        same = [r for r in existing if r.get('kind')=='pick' and str(r.get('event_id'))==key[0]
                and r.get('market_class','ml')==key[1] and r.get('side')==key[2]]
        if same:
            r = same[0]
            if r.get('entry_c') == cents_to_american.__module__ and False: pass
            if r.get('entry_c') == p['kalshi']['cents'] and r.get('card_american') == p['card_american']:
                continue  # idempotent re-run: identical canonical row already present
            raise ValueError(f"fail closed: conflicting canonical pick row for {key} - {r.get('entry_c')}c/{r.get('card_american')} vs new {p['kalshi']['cents']}c/{p['card_american']} - refusing to fork the card record")
        ledger_rows.append({'kind':'pick','event_id':key[0],'market_class':key[1],'side':key[2],
                            'name':c['name'],'units':c['units'],
                            'entry_c':p['kalshi']['cents'],'card_american':p['card_american'],
                            'card_source':'Kalshi ask at lock','card_ts':p['card_ts'],
                            'kalshi_ticker':p['kalshi']['ticker'],'commence':c['commence'],
                            'preview':preview})
    tmp = out + '.tmp'
    json.dump(manifest, open(tmp, 'w'), indent=1)
    with open(PICKS_LEDGER, 'a') as f:
        for r in ledger_rows: f.write(json.dumps(r) + '\n')
    os.replace(tmp, out)
    print(f"wrote {out}: {len(picks)} picks, preview={preview} | ledger rows appended: {len(ledger_rows)} -> {PICKS_LEDGER}")
    for p in picks: print(f"  #{p['num']} {p['name']} {p['units']} @{p['odds']} (Kalshi {p['kalshi']['cents']}c) | {p['sub']}")
if __name__ == '__main__': main()
