#!/usr/bin/env python3
"""test_record_pnl_exact.py - the record's units ARE the P&L math (owner directive, Oct 2 2026):
every graded pick is settled at its card price and card stake (a loss loses the stake; a win pays
stake x 100/|odds| on a favourite, stake x odds/100 on an underdog or even money; a push is 0),
summed in exact fractions, and every displayed figure is that exact value rounded once, half-up
to the cent.

Checks against the live repo files:
  - each day's W-L equals its graded picks, and its units equal fmt_units(exact day P&L)
  - record_done.json units_after_exact equals the exact total (no seed or chain drift)
  - manifest.json units_pl and slates/api_record.json units equal the exact total rounded once
  - the overall W-L in manifest.json and the API mirror equals the sum of the days
A day's rounded figure is not summed into the total: rounded days may add up to a cent more or
less than the total, which is display rounding, not a P&L error."""
import json, os, re, sys
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from record_final import fmt_units  # noqa: E402  the display rule, not a copy

TOL = Fraction(1, 10 ** 12)  # transport of a 15-16 digit decimal string
failures = 0


def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok else f'  [{detail}]'))
    failures += 0 if ok else 1


def pick_pl(p):
    odds = int(str(p['odds']).replace('+', '').strip())
    stake = Fraction(re.sub(r'[^0-9.]', '', str(p['units'])))
    res = p.get('result')
    if res == 'W':
        return stake * 100 / abs(odds) if odds < 0 else stake * odds / 100
    if res == 'L':
        return -stake
    if res in ('P', 'Push'):
        return Fraction(0)
    return None


def dec(fr):
    return Decimal(fr.numerator) / Decimal(fr.denominator)


hist = json.load(open(os.path.join(ROOT, 'history.json')))
total, W, L = Fraction(0), 0, 0
for day in hist['days']:
    exact, w, l, ungraded = Fraction(0), 0, 0, []
    for p in day.get('picks') or []:
        pl = pick_pl(p)
        if pl is None:
            ungraded.append(p.get('name'))
            continue
        exact += pl
        w += p['result'] == 'W'
        l += p['result'] == 'L'
    check(f"{day['date']}: every pick graded", not ungraded, ungraded)
    check(f"{day['date']}: W-L {w}-{l} matches its picks", day.get('record') == f'{w}-{l}', day.get('record'))
    check(f"{day['date']}: units {fmt_units(dec(exact))} = exact P&L {float(exact):+.6f} rounded once",
          day.get('units') == fmt_units(dec(exact)), day.get('units'))
    total += exact
    W, L = W + w, L + l

done = json.load(open(os.path.join(ROOT, 'record_done.json')))
anchor = Fraction(str(done.get('units_after_exact')))
check(f"record_done.json units_after_exact = exact total {float(total):+.9f}", abs(anchor - total) <= TOL,
      f'stored {done.get("units_after_exact")}, drift {float(anchor - total):+.3e}')
check(f"record_done.json record_after = {W}-{L}", done.get('record_after') == f'{W}-{L}', done.get('record_after'))

man = json.load(open(os.path.join(ROOT, 'manifest.json')))
check(f"manifest.json units_pl = {fmt_units(dec(total))}", man.get('units_pl') == fmt_units(dec(total)), man.get('units_pl'))
check(f"manifest.json record = {W}-{L}", man.get('record') == f'{W}-{L}', man.get('record'))

api = json.load(open(os.path.join(ROOT, 'slates', 'api_record.json')))
cents = float(dec(total).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
check(f"api_record.json units = {cents}", api.get('units') == cents, api.get('units'))
check(f"api_record.json W-L = {W}-{L}", (api.get('w'), api.get('l')) == (W, L), (api.get('w'), api.get('l')))

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
