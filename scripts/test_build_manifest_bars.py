#!/usr/bin/env python3
"""Standing-bars and best-ask fixture for scripts/build_manifest.py (owner rulings 2026-10-02, relayed
verbatim by muse on MeshTrix, 15:35Z).
 (1) "Card price is the ASK across ALL markets, not just Kalshi - compare everywhere, take the ask."
     A candidate may carry best_ask {venue, price, read_at, compared:[{venue, price, read_at}]}. The
     market must still be on Kalshi (the kalshi block: ticker + cents). The card price is the cheapest
     cost to buy across kalshi.cents and every venue compared (an exchange's cents, a book's American
     odds as its implied probability; equal cost: the lower fee). card_american is that venue's price,
     card_source '<venue> ask at <read_at>', best_book the venue. The edge is measured again from the
     fair against that cost, with that venue's own fee (the Kalshi taker fee only for Kalshi; Polymarket
     and the books pay 0), and ALWAYS from the card price - never the candidate's self-reported gross_c/net_c.
     Manifest pick and ledger row record the venue, its read time and every venue compared. A NON-preview pick
     with no best_ask block refuses closed (build_manifest never silently ships a non-compared Kalshi price);
     only a --preview build may skip it, priced from Kalshi exactly as before.
 (2) "Parlay breakeven room: use the system's own rules." A parlay clears 2c gross and 2c net: combined
     fair (product of the legs' fairs) against the product of the legs' card prices, or a venue's quoted
     parlay price (parlay.best_ask) when that is cheaper. 2-4 legs (J-098), every leg a pick on the card.
 (4) "NO - an owner-approved card cannot break a standing rule. Vegas rule, ladder sizes, all of it:
     hard gates, no exceptions." Every bar refuses the card closed, nothing written: card
     ask >= 85c, card ask under the 60c band, gross or net under the floor of the pick's band (THE LADDER,
     owner 2026-10-13: band = the card ask the pick is bought at, floor = the edge after fees; 5u = 60c + 2c,
     6u = 60c + 3c, 7u = 70c + 1c, 8u = 70c + 2c, 9u = 70c + 3c, 10u = 80c + 3c, the highest rung cleared; no
     15u, no 100u; fragility 2 one rung lower and tennis capped at 5u, each to a rung the pick also clears, else held;
     fragility 3 refuses; the Kalshi fee rounded up to the cent as charged), units other than that
     rung, and a candidate missing model, gross_c or net_c. A status_note cannot carry a sub-bar card: an owner-forced sub-bar pick is impossible.
Builds run in a throwaway tree with the network sent to a dead proxy.
Run: python3 scripts/test_build_manifest_bars.py"""
import copy, json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
failures = 0

def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or detail == '' else '  [' + str(detail)[-400:] + ']'))
    if not ok:
        failures += 1

META = {'record': '21-11', 'units_pl': '+4.76u', 'units_ledger': None, 'yesterday': '', 'status_note': '', 'parlay': None}
T0 = '2099-10-04T14:51:00Z'

def kfee(c):
    """The Kalshi taker fee in cents a candidate priced at Kalshi c cents pays (build_manifest.kalshi_fee_c): the
    exchange's own figure, rounded UP to the whole cent, as the engine charges it."""
    import math
    a = c / 100.0
    return float(math.ceil(0.07 * a * (1 - a) * 100))

def cand(num, name, model, gross, net, units, cents=61, mc='ml', league='hockey/nhl', **extra):
    # owner ruling 2026-10-02 (1): a non-preview card must carry a best_ask block, so by default a candidate gets
    # a Kalshi best_ask at its own cents (nothing cheaper compared) - the card price is then the Kalshi ask and the
    # edge is recomputed from the fair against it, exactly as a legacy Kalshi pick priced before. Pass best_ask=...
    # for a real cross-venue best ask, or best_ask=None to build a no-best_ask candidate (preview only).
    ba = extra.pop('best_ask', 'auto')
    c = {'num': num, 'date': '2099-10-04', 'market_class': mc, 'name': name, 'side': 'home',
         'away': f'Away{num} Club', 'home': f'Home{num} Club', 'commence': '2099-10-04T23:00Z',
         'eid': str(401995000 + num), 'espn_league': league, 'units': units,
         'model': model, 'gross_c': gross, 'net_c': net, 'sub_context': 'fixture',
         'kalshi': {'cents': cents, 'team': f'Home{num}', 'side': 'yes', 'ticker': 'KXFIX-99OCT04-%d' % num}}
    if mc in ('spread', 'total', 'prop'):
        c['line'] = -1.5 if mc == 'spread' else 5.5
        if mc == 'total': c['side'] = 'over'
    if mc == 'prop':
        c.update(player=f'Player {num}', market='points', side='over')
    c.update(extra)
    if ba == 'auto':
        if isinstance(cents, int) and not isinstance(cents, bool):
            c['best_ask'] = {'venue': 'kalshi', 'price': cents, 'read_at': T0,
                             'compared': [{'venue': 'kalshi', 'price': cents, 'read_at': T0}]}
    elif ba is not None:
        c['best_ask'] = ba
    return c

def run_seq(runs):
    """Runs build_manifest once per (cands, meta) in ONE throwaway tree (ledger, prod mirror and the
    published manifest carry over between runs, as on the box)."""
    d = tempfile.mkdtemp(prefix='rp-bm-bars-')
    try:
        os.makedirs(os.path.join(d, 'ledger')); os.makedirs(os.path.join(d, 'prod'))
        cf, mf, out = (os.path.join(d, x) for x in ('cands.json', 'meta.json', 'manifest.json'))
        ledger = os.path.join(d, 'ledger', 'picks.jsonl')
        env = dict(os.environ, PYTHONPATH=ROOT, RIX_PICKS_LEDGER=ledger,
                   RIX_PROD_MANIFEST=os.path.join(d, 'prod', 'manifest.json'),
                   http_proxy='http://127.0.0.1:9', https_proxy='http://127.0.0.1:9')
        res = []
        for cands, meta in runs:
            json.dump(cands, open(cf, 'w')); json.dump(meta, open(mf, 'w'))
            r = subprocess.run([sys.executable, os.path.join(HERE, 'build_manifest.py'), cf, out, '--meta', mf],
                               capture_output=True, text=True, env=env, timeout=120)
            raw = open(out).read() if os.path.exists(out) else ''
            res.append({'rc': r.returncode, 'log': r.stdout + r.stderr, 'man': json.loads(raw) if raw else None,
                        'ledger': [json.loads(l) for l in open(ledger)] if os.path.exists(ledger) else [],
                        'written': sorted(os.path.relpath(os.path.join(p, f), d) for p, _, fs in os.walk(d) for f in fs
                                          if f not in ('cands.json', 'meta.json', 'picks.jsonl.lock'))})
        return res
    finally:
        shutil.rmtree(d, ignore_errors=True)

def build(cands, **meta_kw):
    return run_seq([(cands, dict(META, **meta_kw))])[0]

def build_preview(cands, **meta_kw):
    """Build in --preview mode (legacy Kalshi-only pricing is allowed; nothing mirrors to production)."""
    d = tempfile.mkdtemp(prefix='rp-bm-bars-prev-')
    try:
        os.makedirs(os.path.join(d, 'ledger')); os.makedirs(os.path.join(d, 'prod'))
        cf, mf, out = (os.path.join(d, x) for x in ('cands.json', 'meta.json', 'prev.json'))
        ledger = os.path.join(d, 'ledger', 'picks.jsonl')
        env = dict(os.environ, PYTHONPATH=ROOT, RIX_PICKS_LEDGER=ledger,
                   RIX_PROD_MANIFEST=os.path.join(d, 'prod', 'manifest.json'),
                   http_proxy='http://127.0.0.1:9', https_proxy='http://127.0.0.1:9')
        json.dump(cands, open(cf, 'w')); json.dump(dict(META, **meta_kw), open(mf, 'w'))
        r = subprocess.run([sys.executable, os.path.join(HERE, 'build_manifest.py'), cf, out, '--preview', '--meta', mf],
                           capture_output=True, text=True, env=env, timeout=120)
        raw = open(out).read() if os.path.exists(out) else ''
        return {'rc': r.returncode, 'log': r.stdout + r.stderr, 'man': json.loads(raw) if raw else None}
    finally:
        shutil.rmtree(d, ignore_errors=True)

def refused(label, cands, whys, **meta_kw):
    r = build(cands, **meta_kw)
    check(f'{label}: refused (exit nonzero)', r['rc'] != 0, r['log'])
    for why in ([whys] if isinstance(whys, str) else whys):
        check(f'{label}: the refusal says {why!r}', why in r['log'], r['log'])
    check(f'{label}: nothing written (no manifest, ledger or prod mirror)', r['man'] is None and r['written'] == [], r['written'])
    return r

def built(label, cands, **meta_kw):
    r = build(cands, **meta_kw)
    check(f'{label}: builds', r['rc'] == 0 and r['man'] is not None, r['log'])
    return r

RULING4 = 'owner ruling 2026-10-02 (4)'

# ------------------------------------------------------------------ (4) the bars, each a hard gate
OK5 = cand(1, 'Home1 ML', 66.0, 5.0, 3.3, '6u')      # Kalshi 61c: 5c gross, 3.33c net -> the 60c band + 3c floor, 6u
built('a pick that clears every bar', [OK5])
check('the ladder is one table in build_manifest', 'LADDER = ((5, 60, 2), (6, 60, 3), (7, 70, 1), (8, 70, 2), (9, 70, 3), (10, 80, 3))'
      in open(os.path.join(HERE, 'build_manifest.py')).read())
# THE BAND IS ON THE ASK (owner, 2026-10-13: "bring back the 60c band and the 2c floor"): under 60c nothing is a
# pick, whatever its edge - and the fair's own level refuses nothing
refused('bought under the 60c band (fair 70c at Kalshi 56c, 14c of gross)', [cand(1, 'Home1 ML', 70.0, 14.0, 12.3, '5u', cents=56)], ['below the 60c band', RULING4])
refused('bought under the 60c band at 6u', [cand(1, 'Home1 ML', 70.0, 14.0, 12.3, '6u', cents=56)], ['below the 60c band'])
refused('card ask 85c (the 85c cut)', [cand(1, 'Home1 ML', 92.0, 7.0, 6.1, '10u', cents=85)], ['85c', RULING4])
# THE 60c BAND'S 2c FLOOR: gross >= 2c AND net >= 2c, each checked on its own and recomputed from the fair against
# the card price - never the candidate's gross_c/net_c. The Kalshi 61c ask pays a 2c fee (0.07 x 0.61 x 0.39 =
# 1.67c, rounded UP to the cent as the exchange charges it), so a fair of 65c nets exactly 2.00c and 64.99c 1.99c.
GROSS_HELD = re.compile(r'gross -?[0-9.]+c below the 2c floor')
refused('gross 1.99c (fair 62.99c at Kalshi 61c)', [cand(1, 'Home1 ML', 62.99, 1.99, 0.32, '5u')], ['gross 1.99c below the 2c floor of the 60c band', RULING4])
r = refused('gross 2.00c (fair 63c at Kalshi 61c): the net alone refuses', [cand(1, 'Home1 ML', 63.0, 2.0, 0.0, '5u')], ['net 0c below the 2c floor of the 60c band'])
check('gross 2.00c: the gross floor does not refuse it', not GROSS_HELD.search(r['log']), r['log'][-300:])
for mc in ('ml', 'spread', 'total', 'prop'):
    r = refused(f'{mc} net 1.99c (fair 64.99c)', [cand(1, f'Home1 {mc}', 64.99, 3.99, 1.99, '5u', mc=mc)], ['net 1.99c below the 2c floor of the 60c band', RULING4])
    check(f'{mc} net 1.99c: the gross (3.99c) is not refused', not GROSS_HELD.search(r['log']), r['log'][-300:])
    built(f'{mc} net 2.00c cards at 5u (fair 65c)', [cand(1, f'Home1 {mc}', 65.0, 4.0, 2.0, '5u', mc=mc)])
# THE 70c BAND'S 1c FLOOR, and its three rungs: Kalshi 71c pays a 2c fee (1.44c rounded up)
refused('70c band: net 0.99c (fair 73.99c at Kalshi 71c) is under the 1c floor', [cand(1, 'Home1 ML', 73.99, 2.99, 0.99, '7u', cents=71)], ['net 0.99c below the 1c floor of the 70c band'])
built('70c band: fair 74.5c at Kalshi 71c (net 1.5c) cards at 7u', [cand(1, 'Home1 ML', 74.5, 3.5, 1.5, '7u', cents=71)])
refused('70c band: fair 74.5c carded at 8u (rung 7u)', [cand(1, 'Home1 ML', 74.5, 3.5, 1.5, '8u', cents=71)], ['ladder rung 7u'])
built('70c band: fair 75.5c (net 2.5c) cards at 8u', [cand(1, 'Home1 ML', 75.5, 4.5, 2.5, '8u', cents=71)])
built('70c band: fair 76.5c (net 3.5c) cards at 9u', [cand(1, 'Home1 ML', 76.5, 5.5, 3.5, '9u', cents=71)])
refused('70c band: fair 76.5c carded at 10u (rung 9u)', [cand(1, 'Home1 ML', 76.5, 5.5, 3.5, '10u', cents=71)], ['ladder rung 9u'])
# THE 80c BAND: 10u needs 3c; with 2c the highest rung cleared is 8u. Kalshi 81c pays a 2c fee (1.08c rounded up)
built('80c band: fair 85.1c at Kalshi 81c (net 2.1c) cards at 8u', [cand(1, 'Home1 ML', 85.1, 4.1, 2.1, '8u', cents=81)])
refused('80c band: fair 85.1c carded at 10u (rung 8u)', [cand(1, 'Home1 ML', 85.1, 4.1, 2.1, '10u', cents=81)], ['ladder rung 8u'])
built('80c band: fair 86.1c (net 3.1c) cards at 10u', [cand(1, 'Home1 ML', 86.1, 5.1, 3.1, '10u', cents=81)])
refused('80c band: fair 86.1c carded at 9u (rung 10u)', [cand(1, 'Home1 ML', 86.1, 5.1, 3.1, '9u', cents=81)], ['ladder rung 10u'])
# THE FEE IS THE EXCHANGE'S ROUNDED-UP CENT, as the engine charges it: 72c ask, 75.5c fair = gross 3.5c, fee 2c,
# net 1.5c = 7u. The unrounded 1.41c fee said net 2.09c = 8u and refused the engine's own 7u card.
# the hunters that write candidates charge the same fee, so a candidate's own net never disagrees with the build's
import ast as _ast
for _f in ('hunt_v2.py', 'hunt_nofloor.py', 'props_fair.py', 'st_fair.py'):
    _tree = _ast.parse(open(os.path.join(HERE, _f)).read())
    _fn = next(n for n in _tree.body if isinstance(n, _ast.FunctionDef) and n.name == 'fee')
    _ns = {}
    exec(compile(_ast.Module(body=[_fn], type_ignores=[]), _f, 'exec'), _ns)
    check(f'{_f} charges the rounded-up Kalshi fee at every price', all(abs(_ns['fee'](c / 100) * 100 - kfee(c)) < 1e-9 for c in range(1, 100)),
          [(c, _ns['fee'](c / 100) * 100, kfee(c)) for c in (60, 61, 71, 81) if abs(_ns['fee'](c / 100) * 100 - kfee(c)) >= 1e-9])
built('72c ask, 75.5c fair cards at 7u, as the engine sizes it (fee 2c, net 1.5c)', [cand(1, 'Home1 ML', 75.5, 3.5, 1.5, '7u', cents=72)])
refused('72c ask, 75.5c fair carded at 8u (the unrounded fee\'s rung)', [cand(1, 'Home1 ML', 75.5, 3.5, 1.5, '8u', cents=72)], ['ladder rung 7u'])
refused('15u is not on the ladder', [cand(1, 'Home1 ML', 85.1, 4.1, 3.02, '15u', cents=81)], ['not on the ladder'])
refused('100u is not on the ladder', [cand(1, 'Home1 ML', 85.1, 4.1, 3.02, '100u', cents=81)], ['not on the ladder', RULING4])
refused('units written 5 (an integer) on a 5u rung', [cand(1, 'Home1 ML', 65.2, 4.2, 2.2, 5)], ["'5u'"])
refused("units written '5.0u' on a 5u rung", [cand(1, 'Home1 ML', 65.2, 4.2, 2.2, '5.0u')], ["'5u'"])
# every manifest pick carries the band and the floor it cleared, and the words the page prints beside its units
r = built('a 9u pick carries band_c 70, floor_c 3 and its ladder words', [cand(1, 'Home1 ML', 76.5, 5.5, 3.5, '9u', cents=71)])
p9 = (r['man'] or {'picks': [{}]})['picks'][0]
check('band_c / floor_c / rung / ladder on the manifest pick', (p9.get('band_c'), p9.get('floor_c'), p9.get('rung')) == (70, 3, '9u')
      and p9.get('ladder') == '9u \u00b7 70c band \u00b7 3c floor', p9)
# fragility (J-097): 2 lowers to the highest LOWER rung the pick also clears (5 stays 5), 3 refuses; 0 and 1 change
# nothing. A pick carries only a band and a floor it passed: a 7u pick at net 1-1.99c clears neither 6u (3c) nor
# 5u (2c), so fragility 2 on it is a hold - never "6u · 60c band · 3c floor" (RixPicksSystem engine/ladder.py)
built('fragility 2 on a 10u rung cards 9u', [cand(1, 'Home1 ML', 86.1, 5.1, 3.1, '9u', cents=81, fragility=2)])
refused('fragility 2 on a 10u rung carded at 10u', [cand(1, 'Home1 ML', 86.1, 5.1, 3.1, '10u', cents=81, fragility=2)], ['ladder rung', 'fragility'])
built('fragility 2 on a 5u rung stays 5u', [cand(1, 'Home1 ML', 65.2, 4.2, 2.2, '5u', fragility=2)])
built('fragility 2 on an 8u rung cards 7u (70c band, 1c floor: cleared)', [cand(1, 'Home1 ML', 75.5, 4.5, 2.5, '7u', cents=71, fragility=2)])
for u in ('6u', '5u', '7u'):
    refused(f'fragility 2 on a 7u pick at net 1.5c is held, carded {u} or not', [cand(1, 'Home1 ML', 74.5, 3.5, 1.5, u, cents=71, fragility=2)], ['fragility 2', 'clears no rung below it'])
built('fragility 1 changes nothing', [cand(1, 'Home1 ML', 86.1, 5.1, 3.1, '10u', cents=81, fragility=1)])
refused('fragility 3 refuses', [cand(1, 'Home1 ML', 86.1, 5.1, 3.1, '10u', cents=81, fragility=3)], ['fragility 3'])
refused('a fragility that is not a whole number refuses', [cand(1, 'Home1 ML', 86.1, 5.1, 3.1, '10u', cents=81, fragility='high')], ['fragility'])
# tennis is capped at 5u, by the same rule: the highest rung at or under 5u the pick also clears
built('tennis at a 10u rung cards 5u', [cand(1, 'Player One ML', 86.1, 5.1, 3.1, '5u', cents=81, league='tennis/atp')])
refused('tennis at a 10u rung carded at 10u', [cand(1, 'Player One ML', 86.1, 5.1, 3.1, '10u', cents=81, league='tennis/wta')], ['ladder rung', 'tennis'])
refused('tennis at a 7u rung with net 1.5c is held (5u needs 2c of the net)', [cand(1, 'Player One ML', 74.5, 3.5, 1.5, '5u', cents=71, league='tennis/atp')], ['tennis is capped at 5u', 'clears no rung'])
# the candidate must carry its fair and its edge
for k in ('model', 'gross_c', 'net_c'):
    c = copy.deepcopy(OK5); del c[k]
    refused(f'a candidate missing {k}', [c], [k])
refused('a model that is not a number', [dict(OK5, model='66')], ['model'])
refused('a bool gross_c', [dict(OK5, gross_c=True)], ['gross_c'])

# the probe that passed before (fresh clone of 7172df01): model 46.7, gross 1.0, net 0.1 with the
# Sep 29/30 status_note words, and every violation on a card in one refusal
PROBE_NOTE = 'Official pick by owner directive - sub-bar disclosure on file (fair 46.7c below the 60c card band)'
r = refused('the sub-bar probe with the owner-directive status_note',
            [cand(1, 'Home1 ML', 46.7, 1.0, 0.1, '5u', cents=46)], ['below the 60c band', 'gross', 'net', 'sub-bar', RULING4], status_note=PROBE_NOTE)
check('the refusal names an owner-forced sub-bar pick impossible', 'owner-forced sub-bar pick is impossible' in r['log'], r['log'][-300:])
refused('a sub-bar disclosure status_note on a clean card refuses (a status_note cannot carry a sub-bar card)', [OK5], ['status_note', RULING4],
        status_note='Official pick by owner directive - sub-bar disclosure on file')
r = refused('two sub-bar picks and a clean one: both named in one refusal',
            [OK5, cand(2, 'Home2 ML', 58.0, 1.0, 0.0, '5u', cents=57), cand(3, 'Home3 ML', 66.0, 5.0, 3.3, '15u')], ['Home2 ML', 'Home3 ML'])
check('...and the clean pick is not named', '#1 Home1 ML' not in r['log'], r['log'][-300:])

# ------------------------------------------------------------------ (1) the card price is the best ask
def ba(venue, price, compared, read_at=T0):
    return {'venue': venue, 'price': price, 'read_at': read_at, 'compared': compared}
K61 = {'venue': 'kalshi', 'price': 61, 'read_at': '2099-10-04T14:52:00Z'}
DK150 = {'venue': 'dk', 'price': -150, 'read_at': T0}
PM62 = {'venue': 'poly', 'price': 62, 'read_at': '2099-10-04T14:50:00Z'}

# a book wins: DK -150 costs 60.0c, below Kalshi 61c and Polymarket 62c
c = cand(1, 'Home1 ML', 66.0, 5.0, 3.3, '6u', best_ask=ba('dk', -150, [K61, DK150, PM62]))
r = built('DK -150 beats Kalshi 61c and Polymarket 62c', [c])
p = (r['man'] or {'picks': [{}]})['picks'][0]
check('card_american and odds are the DK price (-150), not the Kalshi -156', p.get('card_american') == -150 and p.get('odds') == '-150', p)
check("best_book is the venue (DraftKings) and card_source '<venue> ask at <read_at>'",
      p.get('best_book') == 'DraftKings' and p.get('card_source') == f'DraftKings ask at {T0}', p)
check('the kalshi block is still the Kalshi market (eligibility), its cents unchanged',
      (p.get('kalshi') or {}).get('cents') == 61 and (p.get('kalshi') or {}).get('ticker') == 'KXFIX-99OCT04-1', p.get('kalshi'))
pba = p.get('best_ask') or {}
check('the manifest pick records the venue, its read time and every venue compared, cheapest first',
      pba.get('venue') == 'dk' and pba.get('price') == -150 and pba.get('read_at') == T0
      and [q.get('venue') for q in pba.get('compared') or []] == ['dk', 'kalshi', 'poly']
      and (pba.get('compared') or [{}])[1].get('read_at') == '2099-10-04T14:52:00Z', pba)
check('the edge is measured again against the DK cost with no fee (gross = net = 6.0c)',
      pba.get('cost_c') == 60.0 and pba.get('fee_c') == 0.0 and pba.get('gross_c') == 6.0 and pba.get('net_c') == 6.0, pba)
row = (r['ledger'] or [{}])[0]
check('the ledger row records the card price, the venue, its read time and the compared list',
      row.get('card_american') == -150 and row.get('entry_c') == 61 and row.get('card_venue') == 'dk'
      and row.get('card_read_at') == T0 and row.get('card_source') == f'DraftKings ask at {T0}'
      and [q.get('venue') for q in row.get('card_compared') or []] == ['dk', 'kalshi', 'poly'], row)

# Kalshi wins: its read time comes from the best_ask block, the price from cents_to_american
c = cand(1, 'Home1 ML', 66.0, 5.0, 3.3, '6u', best_ask=ba('kalshi', 61, [{'venue': 'dk', 'price': -170, 'read_at': T0}], read_at='2099-10-04T14:53:00Z'))
r = built('Kalshi 61c beats DK -170', [c])
p = (r['man'] or {'picks': [{}]})['picks'][0]
check("Kalshi best: card_american -156, best_book Kalshi, card_source 'Kalshi ask at <read_at>'",
      p.get('card_american') == -156 and p.get('best_book') == 'Kalshi' and p.get('card_source') == 'Kalshi ask at 2099-10-04T14:53:00Z', p)
check('Kalshi best: the Kalshi taker fee is charged as the exchange charges it (7 x 0.61 x 0.39 = 1.67c, rounded up: 2c)', (p.get('best_ask') or {}).get('fee_c') == 2.0, p.get('best_ask'))

# Polymarket wins: no fee
c = cand(1, 'Home1 ML', 66.0, 5.0, 3.3, '6u', best_ask=ba('poly', 60, [K61, {'venue': 'poly', 'price': 60, 'read_at': T0}]))
r = built('Polymarket 60c beats Kalshi 61c', [c])
p = (r['man'] or {'picks': [{}]})['picks'][0]
check('Polymarket best: card_american -150 (60c), best_book Polymarket, no fee',
      p.get('card_american') == -150 and p.get('best_book') == 'Polymarket' and (p.get('best_ask') or {}).get('fee_c') == 0.0, p)
# float noise is not an edge: 65.1 - 63.1 is 1.99999...c in binary, a 2.00c gross and net at Polymarket (no fee)
built('a 2.00c edge at Polymarket 63.1c (fair 65.1c) cards', [cand(1, 'Home1 ML', 65.1, 2.0, 2.0, '5u', cents=65,
      best_ask=ba('poly', 63.1, [{'venue': 'kalshi', 'price': 65, 'read_at': T0}, {'venue': 'poly', 'price': 63.1, 'read_at': T0}]))])

# the edge is the best ask's: a pick short of the bar at Kalshi clears it at a cheaper book ...
SHORT_AT_KALSHI = cand(1, 'Home1 ML', 62.5, 1.5, -0.2, '5u')
refused('fair 62.5c against Kalshi 61c alone (gross 1.5c, net -0.5c after the 2c fee)', [SHORT_AT_KALSHI], ['net -0.5c below the 2c floor of the 60c band'])
built('the same pick against DK -150 (gross 2.5c, no fee)', [dict(SHORT_AT_KALSHI, best_ask=ba('dk', -150, [K61, DK150]))])
# ... and the Kalshi fee counts when Kalshi is the best venue, whatever net_c the candidate carried
built('spread fair 64.1c, Kalshi 60c beats DK -155: net 4.1 - 2 = 2.1c cards (over the 60c band\'s 2c floor)',
        [cand(1, 'Home1 -1.5', 64.1, 4.1, 2.1, '5u', cents=60, mc='spread',
              # a book quote on a spread names its line (one line, one market): the home pick's own -1.5
              best_ask=ba('kalshi', 60, [{'venue': 'dk', 'price': -155, 'read_at': T0, 'line': -1.5}]))])

# fail closed on a best_ask block the builder cannot trust
refused('best_ask names DK but Kalshi is cheaper', [cand(1, 'Home1 ML', 66.0, 5.0, 3.3, '6u', best_ask=ba('dk', -170, [K61]))], ['cheaper'])
refused('the best ask has no read time', [cand(1, 'Home1 ML', 66.0, 5.0, 3.3, '6u', best_ask=ba('dk', -150, [K61], read_at=None))], ['read_at'])
refused('a read time with no zone', [cand(1, 'Home1 ML', 66.0, 5.0, 3.3, '6u', best_ask=ba('dk', -150, [K61], read_at='2099-10-04T14:51'))], ['read_at'])
refused('an unknown venue', [cand(1, 'Home1 ML', 66.0, 5.0, 3.3, '6u', best_ask=ba('pinnacle', -150, [K61]))], ['unknown venue'])
refused('a venue compared twice', [cand(1, 'Home1 ML', 66.0, 5.0, 3.3, '6u', best_ask=ba('dk', -150, [DK150, dict(DK150, price=-160)]))], ['twice'])
refused("a compared Kalshi ask that is not the kalshi block's", [cand(1, 'Home1 ML', 66.0, 5.0, 3.3, '6u', best_ask=ba('dk', -150, [dict(K61, price=59)]))], ['kalshi'])
refused('a Polymarket price in dollars (0.61, not cents)', [cand(1, 'Home1 ML', 66.0, 5.0, 3.3, '6u', best_ask=ba('poly', 0.61, [K61]))], ['cents'])
refused('a book price that is not American odds (-100)', [cand(1, 'Home1 ML', 66.0, 5.0, 3.3, '6u', best_ask=ba('dk', -100, [K61]))], ['American'])
refused('compared is not a list', [cand(1, 'Home1 ML', 66.0, 5.0, 3.3, '6u', best_ask={'venue': 'dk', 'price': -150, 'read_at': T0})], ['compared'])
nok = cand(1, 'Home1 ML', 66.0, 5.0, 3.3, '6u', best_ask=ba('dk', -150, [DK150])); del nok['kalshi']
refused('a book-only market (no kalshi block) never cards', [nok], ['Kalshi'])
nok = cand(1, 'Home1 ML', 66.0, 5.0, 3.3, '6u', best_ask=ba('dk', -150, [DK150])); nok['kalshi'] = {'cents': 61, 'team': 'x'}
refused('a kalshi block with no ticker', [nok], ['ticker'])

# B1 (owner ruling 2026-10-02 (1)): a non-preview pick with no best_ask block refuses closed - build_manifest
# never silently ships a non-compared Kalshi price. The candidate clears every other bar, so the missing
# best_ask is the only reason to refuse.
NOBA = cand(1, 'Home1 ML', 66.0, 5.0, 3.3, '6u', best_ask=None)
check('no best_ask on OK5 would refuse non-preview (B1 is wired)', 'best_ask' not in NOBA, NOBA)
refused('a non-preview pick with no best_ask block', [NOBA], ['best_ask', '2026-10-02 (1)'])
# a --preview build may still skip best_ask: the card is then priced from Kalshi exactly as before
pr = build_preview([NOBA])
check('a preview build with no best_ask builds', pr['rc'] == 0 and pr['man'] is not None, pr['log'])
p = (pr['man'] or {'picks': [{}]})['picks'][0]
check("preview no best_ask: Kalshi price, 'Kalshi ask at lock', no best_ask on the pick",
      p.get('card_american') == -156 and p.get('best_book') == 'Kalshi' and p.get('card_source') == 'Kalshi ask at lock' and 'best_ask' not in p, p)
# B2 (owner ruling 2026-10-02 (1)/(4)): gross and net are always recomputed from the fair against the card price,
# never the candidate's self-reported gross_c/net_c. Candidate net_c 1.5 is what it is, but the recompute from
# Kalshi 61c (1.5 - fee 2 = -0.5c) is under the 60c band's 2c floor - preview refuses just as a production
# best-ask pick would.
_b2 = build_preview([cand(1, 'Home1 ML', 62.5, 1.5, 1.5, '5u', best_ask=None)])
check('a preview legacy pick whose candidate net clears the floor but recomputes below it is refused',
      _b2['rc'] != 0 and _b2['man'] is None and 'net -0.5c below the 2c floor of the 60c band' in _b2['log'], _b2['log'])
built_preview_clears = build_preview([cand(1, 'Home1 ML', 65.2, 2.0, 0.0, '5u', best_ask=None)])  # 65.2-61-2=2.2 >= 2
check('a preview legacy pick whose recomputed net clears builds (candidate net_c 0.0 ignored)',
      built_preview_clears['rc'] == 0 and built_preview_clears['man'] is not None, built_preview_clears['log'])

# the ledger: an identical re-run adds nothing; a new best venue on a published key is a fork
c = cand(1, 'Home1 ML', 66.0, 5.0, 3.3, '6u', best_ask=ba('dk', -150, [K61, DK150]))
c2 = cand(1, 'Home1 ML', 66.0, 5.0, 3.3, '6u', best_ask=ba('poly', 60, [K61, {'venue': 'poly', 'price': 60, 'read_at': T0}]))
a, b, f = run_seq([([c], META), ([c], META), ([c2], META)])
check('an identical best-ask re-run adds no ledger row', a['rc'] == 0 and b['rc'] == 0 and len(b['ledger']) == 1, b['log'][-300:])
check('a different best venue on a published key refuses to fork the card record',
      f['rc'] != 0 and 'refusing to fork' in f['log'] and len(f['ledger']) == 1 and f['ledger'][0].get('card_venue') == 'dk', f['log'][-300:])

# ------------------------------------------------------------------ (2) the parlay bar
L1 = cand(1, 'Home1 ML', 66.0, 5.0, 3.3, '6u')                  # Kalshi 61c: 6u
L2 = cand(2, 'Home2 ML', 72.0, 5.0, 3.0, '6u', cents=67)        # Kalshi 67c: 5c gross, 3c net (2c fee), 6u
built('a parlay at the product of the legs clears 2c gross and net (fair 47.52c, price 40.87c, fee 2.6c, net 4.05c)',
      [L1, L2], parlay={'legs': ['Home1 ML', 'Home2 ML'], 'note': ''})
T1 = cand(1, 'Home1 ML', 74.0, 3.0, 1.0, '7u', cents=71)       # 74 x 74 = 54.76c, legs 71c x 71c = 50.41c, all-in 73c x 73c = 53.29c (price 50.43c from American), net 1.45c
T2 = cand(2, 'Home2 ML', 74.0, 3.0, 1.0, '7u', cents=71)       # 3c gross, 1c net: each leg clears the 70c band's 1c floor at 7u
refused('a parlay whose net is 1.45c (each Kalshi leg pays its fee)', [T1, T2], ['parlay', 'net 1.45c below the 2c parlay bar', RULING4],
        parlay={'legs': ['Home1 ML', 'Home2 ML'], 'note': ''})
built('the same parlay at a cheaper venue quote (DK +260)', [T1, T2],
      parlay={'legs': ['Home1 ML', 'Home2 ML'], 'note': '', 'best_ask': {'venue': 'dk', 'price': 260, 'read_at': T0}})
refused('a parlay venue quote with no read time', [T1, T2], ['parlay', 'read_at'],
        parlay={'legs': ['Home1 ML', 'Home2 ML'], 'note': '', 'best_ask': {'venue': 'dk', 'price': 260}})
FIVE = [cand(i, f'Home{i} ML', 92.0, 8.0, 7.3, '10u', cents=84) for i in range(1, 6)]
refused('a five-leg parlay (J-098: 2-4 legs)', FIVE, ['parlay', 'J-098'], parlay={'legs': [x['name'] for x in FIVE], 'note': ''})
refused('a parlay leg that is not a pick on the card', [L1, L2], ['parlay', 'Rangers ML'], parlay={'legs': ['Home1 ML', 'Rangers ML'], 'note': ''})
refused('a one-leg parlay', [L1, L2], ['parlay'], parlay={'legs': ['Home1 ML'], 'note': ''})

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
