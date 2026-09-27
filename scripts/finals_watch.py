#!/usr/bin/env python3
"""J-118 TRIGGER (production, DRY-RUN until swamp certification + parent's word):
detect FINALs on today's card, grade SEQUENTIALLY in commence order with a running
cumulative record/units from the canonical baseline, then fire the instant record chain.
Guards (swamp 9:23 PM):
- baseline REQUIRED: record_rows.jsonl must contain G-BASELINE-* with record+units_exact,
  else refuse (never zero-seed).
- cumulative across the batch: each final's row carries the running cumulative AFTER it.
- two-source final verification: ESPN core + a second independent score source must agree
  on the final before any grade (J-115).
- tie = PUSH: 0 pnl, no W/L, never an away win.
- seen[eid] written ONLY on a verified chain (dry-run marks separately and never blocks).
Usage: finals_watch.py [--dry-run]"""
import json, os, sys, urllib.request
sys.path.insert(0, '/home/sandbox/rix_tmp')
from datetime import datetime
from decimal import Decimal
from core import record_pipe, units
HERE = os.path.dirname(__file__)
MANIFEST = os.path.join(HERE, '..', 'manifest.json')
STATE = '/home/sandbox/rps_tmp/kb/ledger/finals_seen.json'
LEDGER = '/home/sandbox/rps_tmp/kb/ledger/record_rows.jsonl'
TOKEN_PATH = '/tmp/.push_token'
def _get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=20) as r: return json.load(r)
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
def yahoo_final(home_name, away_name):
    """Second independent source (J-115): Yahoo scoreboard page title carries the final."""
    import re, urllib.parse
    q = urllib.parse.quote(f'{away_name} {home_name} score')
    html = _get.__wrapped__ if False else None
    req = urllib.request.Request(f'https://sports.yahoo.com/search/?q={q}', headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            t = r.read().decode('utf-8', 'ignore')[:200000]
        m = re.search(r'<title>([^<]*?)(\d+)\s*[-\u2013]\s*(\d+)[^<]*</title>', t)
        return (int(m.group(2)), int(m.group(3))) if m else None
    except Exception:
        return None
def load_baseline():
    try:
        for line in open(LEDGER):
            d = json.loads(line)
            if str(d.get('grade_id', '')).startswith('G-BASELINE-'):
                w, l = (int(x) for x in d['record'].split('-')[:2])
                return w, l, Decimal(d['units_exact'])
    except FileNotFoundError: pass
    raise SystemExit('REFUSE: no G-BASELINE-* row in record ledger - canonical baseline required, never zero-seed')
def main():
    dry = '--dry-run' in sys.argv
    m = json.load(open(MANIFEST))
    try: seen = json.load(open(STATE))
    except Exception: seen = {}
    W, L, U = load_baseline()
    picks = sorted([p for p in m.get('picks', []) if p.get('game', {}).get('eid')],
                   key=lambda p: p['game'].get('commence', ''))
    fired = []
    for p in picks:
        g = p['game']; eid = g['eid']
        mclass = 'ml'  # manifest picks are moneyline; extend when spread/total picks card
        pkey = f"{eid}|{mclass}|{p['side']}"
        if pkey in seen: continue
        try: sc = espn_final(p.get('espn_league', 'football/college-football'), eid)
        except Exception as e:
            print(f'WARN: status fetch failed for {eid}: {e}'); continue
        if not sc: continue
        second = yahoo_final(g.get('home', ''), g.get('away', ''))
        if second is None:
            print(f'WARN: {eid} second source unavailable - NOT grading (J-115 two-source)'); continue
        if (second[0], second[1]) != (sc['home'], sc['away']) and (second[0], second[1]) != (sc['away'], sc['home']):
            print(f'WARN: {eid} sources disagree ESPN {sc} vs Yahoo {second} - NOT grading'); continue
        if sc['home'] == sc['away']:
            result, pnl = 'PUSH', Decimal('0')           # tie is a push, never an away win
        else:
            home_won = sc['home'] > sc['away']
            won = (p['side'] == 'home') == home_won
            cents = (p.get('kalshi') or {}).get('cents')
            u = Decimal(p.get('units', '0u').rstrip('u'))
            if not cents or not u:
                print(f'WARN: {pkey} missing price/units in manifest - grade manually'); continue
            stake = u * Decimal(15)  # exact from the first multiplication (store-exact standard)
            pnl = units.stake_pnl(stake, cents) if won else -stake
            result = 'W' if won else 'L'
        if result == 'W': W += 1
        elif result == 'L': L += 1
        U = U + units.pnl_to_units(pnl)                  # running cumulative across the batch
        grade_id = f"G-{pkey}"
        token = open(TOKEN_PATH).read().strip() if os.path.exists(TOKEN_PATH) else ''
        res = record_pipe.on_final(pkey, sc['home'], sc['away'], grade_id,
                                   m.get('date_label', ''), f'{W}-{L}',
                                   f'{100*W/(W+L):.2f}%', U,
                                   'card stake at locked price, $15/u', LEDGER, token, dry_run=dry)
        verified = res['chain'] == 'complete'
        if dry:
            pass  # dry-run never marks seen - a live retry is never blocked
        elif verified:
            seen[pkey] = {'fired': res['chain'], 'result': result}
        else:
            print(f'WARN: {pkey} chain {res["chain"]} - NOT marked seen, will retry next fire')
        fired.append((pkey, p['name'], result, res['chain']))
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(seen, open(STATE, 'w'))
    for f in fired: print('FINAL-CHAIN:', f)
    print(f'finals_watch: {len(fired)} new final(s) processed' + (' [DRY RUN]' if dry else ''))
if __name__ == '__main__': main()
