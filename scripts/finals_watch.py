#!/usr/bin/env python3
"""J-118 TRIGGER (production): detect FINALs on today's card and fire the instant record
chain (core.record_pipe.on_final -> record ledger + live site POST + GET value-verify).
Invoked on the 5-min wire cadence and the 11:30 PM reconciliation. Each final writes
exactly one record row: record_pipe idempotency (grade_id) is the backstop.
Usage: finals_watch.py [--dry-run]"""
import json, os, sys, urllib.request
sys.path.insert(0, '/home/sandbox/rix_tmp')
from decimal import Decimal
from core import record_pipe, units
HERE = os.path.dirname(__file__)
MANIFEST = os.path.join(HERE, '..', 'manifest.json')
STATE = '/home/sandbox/rps_tmp/kb/ledger/finals_seen.json'
LEDGER = '/home/sandbox/rps_tmp/kb/ledger/record_rows.jsonl'
TOKEN_PATH = '/tmp/.push_token'
def _get(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)
def _deref(node):
    return _get(node['$ref']) if isinstance(node, dict) and '$ref' in node else node
def espn_final(league, eid):
    lg = league.replace('/', '/leagues/')
    base = f'https://sports.core.api.espn.com/v2/sports/{lg}/events/{eid}/competitions/{eid}'
    c = _get(base)
    st = _deref(c.get('status', {})).get('type', {})
    if not st.get('completed'): return None
    sc = {}
    for x in c.get('competitors', []):
        s2 = _deref(x.get('score', {}))
        v = s2.get('value') if isinstance(s2, dict) else None
        sc[x.get('homeAway')] = int(float(v)) if v is not None else None
    if sc.get('home') is None or sc.get('away') is None: return None
    return sc
def main():
    dry = '--dry-run' in sys.argv
    m = json.load(open(MANIFEST))
    try: seen = json.load(open(STATE))
    except Exception: seen = {}
    fired = []
    for p in m.get('picks', []):
        g = p.get('game', {}); eid = g.get('eid')
        if not eid or eid in seen: continue
        try: sc = espn_final(p.get('espn_league', 'football/college-football'), eid)
        except Exception as e:
            print(f'WARN: status fetch failed for {eid}: {e}'); continue
        if not sc: continue
        home_won = sc.get('home', 0) > sc.get('away', 0)
        won = (p['side'] == 'home') == home_won
        cents = (p.get('kalshi') or {}).get('cents')
        u = float(p.get('units', '0u').rstrip('u'))
        if not cents or not u:
            print(f'WARN: {eid} missing price/units in manifest - grade manually'); continue
        stake = Decimal(str(u * 15))
        pnl = units.stake_pnl(stake, cents) if won else -stake
        grade_id = f"G-{eid}-{p['side']}"
        # cumulative record from the ledger (this row inclusive)
        rec = m.get('record', '0-0'); w, l = (int(x) for x in rec.split('-')[:2])
        w2, l2 = w + (1 if won else 0), l + (0 if won else 1)
        # exact cumulative units: ledger + this pnl
        cum = Decimal('0')
        try:
            for line in open(LEDGER):
                d = json.loads(line)
                if 'units_exact' in d: cum = Decimal(d['units_exact'])
        except FileNotFoundError: pass
        cum = cum + units.pnl_to_units(pnl)
        token = open(TOKEN_PATH).read().strip() if os.path.exists(TOKEN_PATH) else ''
        res = record_pipe.on_final(eid, sc.get('home', 0), sc.get('away', 0), grade_id,
                                   m.get('date_label', ''), f'{w2}-{l2}',
                                   f'{100*w2/(w2+l2):.2f}%', cum,
                                   'card stake at locked price, $15/u', LEDGER, token, dry_run=dry)
        seen[eid] = {'fired': res['chain'], 'won': won}
        fired.append((eid, p['name'], won, res['chain']))
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(seen, open(STATE, 'w'))
    for f in fired: print('FINAL-CHAIN:', f)
    print(f'finals_watch: {len(fired)} new final(s) processed' + (' [DRY RUN]' if dry else ''))
if __name__ == '__main__': main()
