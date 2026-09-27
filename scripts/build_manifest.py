#!/usr/bin/env python3
"""Durable card manifest builder. CARD PRICE BASIS (his call 9/26 10:14 PM PT,
phonemsg-01M3GMJBQVQX5099CH3AN4TB3E): card_american converts from the KALSHI ASK the gate
consumed (units.cents_to_american), card_source = 'Kalshi ask at lock', and the card shows the
gate's own numbers (model vs Kalshi ask, gross/net edge) - never book-consensus display.
Forward-only: previously published cards keep their published prices.
Usage: build_manifest.py candidates.json out_manifest.json [--preview]
candidate row: {num,name,side,away,home,commence,eid,espn_league,units,kalshi:{cents,team,url,ticker},model,gross_c,net_c}

PUBLICATION SHAPE (swamp rounds 4): a preview NEVER touches the production ledger - it writes
to picks.preview.jsonl. Production publication holds a single-writer flock, reads the ledger
INSIDE the lock, appends canonical rows, publishes the manifest via os.replace, then reads
back and verifies every appended row. Crash recovery: re-running with the same candidates is
idempotent (identical rows skip, manifest publishes); re-running with different candidates on
the same key refuses closed rather than forking the card record."""
import json, sys, datetime, os, fcntl
from zoneinfo import ZoneInfo
sys.path.insert(0, '/home/sandbox/rix_tmp')
from core.units import cents_to_american
from core.fill_leak import PICKS_LEDGER as _DEFAULT_PICKS_LEDGER
PICKS_LEDGER = os.environ.get('RIX_PICKS_LEDGER', _DEFAULT_PICKS_LEDGER)  # test-isolation hook

PREVIEW_LEDGER = PICKS_LEDGER.replace('picks.jsonl', 'picks.preview.jsonl')
LOCK_PATH = PICKS_LEDGER + '.lock'

def main():
    cands = json.load(open(sys.argv[1]))
    preview = '--preview' in sys.argv
    out = sys.argv[2] if not sys.argv[2].startswith('--') else sys.argv[3]
    now = datetime.datetime.now(ZoneInfo('America/Los_Angeles')).isoformat(timespec='seconds')
    ledger = PREVIEW_LEDGER if preview else PICKS_LEDGER
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

    # Single-writer lock: held across read-decide-append-publish-verify so concurrent builds
    # can never both read the pre-append ledger and duplicate a canonical row.
    os.makedirs(os.path.dirname(ledger), exist_ok=True)
    lockf = open(LOCK_PATH, 'w')
    fcntl.flock(lockf, fcntl.LOCK_EX)
    try:
        existing = [json.loads(l) for l in open(ledger)] if os.path.exists(ledger) else []
        ledger_rows = []
        for c, p in zip(cands, picks):
            key = (str(c['eid']), c.get('market_class','ml'), c['side'])
            same = [r for r in existing if r.get('kind')=='pick' and str(r.get('event_id'))==key[0]
                    and r.get('market_class','ml')==key[1] and r.get('side')==key[2]]
            if same:
                r = same[0]
                identical = r.get('entry_c') == p['kalshi']['cents'] and r.get('card_american') == p['card_american']
                if identical and not r.get('preview') and not preview:
                    continue  # idempotent re-run: identical canonical row already present
                if identical and preview:
                    continue  # preview ledger re-run: identical row already present
                if identical and r.get('preview') and not preview:
                    # STAGED PROMOTION (swamp replay): a legacy preview marker on this key must
                    # never satisfy a production publish. Rewrite the ledger without the marker,
                    # append the canonical production row, verify. Explicit, logged, one write.
                    staged = [x for x in existing if x is not r]
                    ltmp = ledger + '.stage'
                    with open(ltmp, 'w') as sf:
                        for x in staged: sf.write(json.dumps(x) + '\n')
                    os.replace(ltmp, ledger)
                    existing = staged
                    print(f"STAGED PROMOTION: retired preview marker on {key}, publishing canonical row")
                else:
                    raise ValueError(f"fail closed: conflicting canonical pick row for {key} - {r.get('entry_c')}c/{r.get('card_american')} vs new {p['kalshi']['cents']}c/{p['card_american']} - refusing to fork the card record")
            ledger_rows.append({'kind':'pick','event_id':key[0],'market_class':key[1],'side':key[2],
                                'name':c['name'],'units':c['units'],
                                'entry_c':p['kalshi']['cents'],'card_american':p['card_american'],
                                'card_source':'Kalshi ask at lock','card_ts':p['card_ts'],
                                'kalshi_ticker':p['kalshi']['ticker'],'commence':c['commence'],
                                'preview':preview})
        tmp = out + '.tmp'
        json.dump(manifest, open(tmp, 'w'), indent=1)
        appended_at = None
        with open(ledger, 'a') as f:
            for r in ledger_rows: f.write(json.dumps(r) + '\n')
        os.replace(tmp, out)
        # READBACK VERIFICATION: every row we meant to append must parse and match exactly.
        if ledger_rows:
            tail = [json.loads(l) for l in open(ledger)][-len(ledger_rows):]
            for want, got in zip(ledger_rows, tail):
                if want != got:
                    raise ValueError(f"fail closed: ledger readback mismatch for {want.get('event_id')} - appended row does not verify")
        print(f"wrote {out}: {len(picks)} picks, preview={preview} | ledger rows appended: {len(ledger_rows)} -> {ledger} (readback verified)")
    finally:
        fcntl.flock(lockf, fcntl.LOCK_UN); lockf.close()
    for p in picks: print(f"  #{p['num']} {p['name']} {p['units']} @{p['odds']} (Kalshi {p['kalshi']['cents']}c) | {p['sub']}")
if __name__ == '__main__': main()
