#!/usr/bin/env python3
"""TENNIS ADAPTER (pipeline step 3 tennis, wired 9/27 evening): tennis_kalshi_discovery catches
-> build_manifest candidate schema. Mirrors st_card_candidates gates + conventions:
  P-EDGE-001 net >= 2c (floored pass; --no-floor only for the governing-sequence floorless pass)
  J-096 ladder via the same tier_eval as hunt_v2/st: fair 60-69c=5u, 70-79=10u (gross>=3c else 5u),
    80-89=15u, 90+=100u; fair < 60c = below card band, NOT carded (J-124a: never manufacture).
  Book-divergence kill (>=4.5c): needs TWO fair anchors. Tennis tonight is single-anchor
    (Polymarket fallback while odds-API tennis keys are inactive), so the kill is N/A and the
    candidate records anchors=1. When discovery carries fair_pct_alt (dual-anchor future), a
    |fair - fair_alt| >= 4.5c kill applies here.
  Match-winner rungs ONLY (series endswith MATCH, no ':' qualifier in title) - spread/total rung
    fairs land in a later stage.
  EID: fail-closed on missing slate binding (catch['slate_bound'] from --slate run); loud skip.
  LEAGUE: KXATP*->tennis/atp (ATP), KXWTA*->tennis/wta (WTA); ITF/challenger/doubles have no
    ESPN scoreboard -> loud skip (ungradeable today; finals_watch tennis grading not yet wired).
  SIDE convention: title 'A vs B' -> A='away', B='home' (team-sport convention; ledger identity).
IN : tennis catch JSON (path arg or stdin)
OUT: JSON list of build_manifest candidates."""
import json, sys

def tier_eval(fair_c, gross_c):
    # J-096 ladder (verbatim copy of hunt_v2/st_card_candidates).
    if fair_c >= 90: return 100
    if 80 <= fair_c < 90: return 15
    if 70 <= fair_c < 80: return 10 if gross_c >= 3 else 5
    if 60 <= fair_c < 70: return 5
    return 0

def espn_league(series):
    if series.startswith('KXATP'): return 'tennis/atp'
    if series.startswith('KXWTA'): return 'tennis/wta'
    return None

def adapt(catch, side_rec, floor=True):
    if not catch['series'].endswith('MATCH') or ':' in catch['title']: return None
    fair_c = side_rec.get('fair_pct'); ask = side_rec.get('yes_ask_c')
    if fair_c is None or ask is None: return None
    gross = fair_c - ask
    net = side_rec.get('net_edge_c')
    if net is None: return None
    if floor and net < 2: return None            # P-EDGE-001
    # divergence kill: dual-anchor only; single-anchor tonight = N/A (recorded)
    alt = side_rec.get('fair_pct_alt')
    anchors = 2 if alt is not None else 1
    if alt is not None and abs(fair_c - alt) >= 4.5:
        print(f"KILL (divergence {abs(fair_c-alt):.1f}c >= 4.5c): {side_rec.get('player')} {catch['title']}", file=sys.stderr)
        return None
    units = tier_eval(fair_c, gross)
    if units == 0:
        print(f"SKIP (below J-096 card band, fair {fair_c}c): {side_rec.get('player')} - {catch['title']}", file=sys.stderr)
        return None
    lg = espn_league(catch['series'])
    if not lg:
        print(f"SKIP (fail closed: no ESPN league for {catch['series']} - ITF/challenger ungradeable today): {catch['title']}", file=sys.stderr)
        return None
    eid = catch.get('slate_bound')
    if not eid:
        print(f"SKIP (fail closed: no ESPN slate binding): {side_rec.get('player')} - {catch['title']}", file=sys.stderr)
        return None
    players = catch['title'].split(' vs ')
    picked = side_rec.get('player') or ''
    side = 'away' if picked and players and picked.lower().endswith(players[0].split()[-1].lower()) else 'home'
    opp = players[0] if side == 'home' else (players[1] if len(players) > 1 else '?')
    surname = picked.split()[-1] if picked else '?'
    return {'date': (catch.get('pt_date') or catch['exp_pt'][:10]),
            'market_class': 'ml', 'name': surname, 'side': side,
            'away': players[0] if len(players) > 1 else picked, 'home': players[-1],
            'commence': catch['exp_pt'], 'eid': str(eid), 'espn_league': lg,
            'units': f'{units}u', 'model': fair_c, 'gross_c': round(gross, 1), 'net_c': net,
            'sub_context': f"vs {opp.split()[-1]} - tennis ML - {anchors} fair anchor(s)",
            'kalshi': {'cents': int(round(ask)), 'team': picked, 'ticker': side_rec['ticker']}}

def main():
    d = json.load(open(sys.argv[1])) if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else json.load(sys.stdin)
    floor = '--no-floor' not in sys.argv
    out = []
    for catch in d.get('catches', []):
        for s in catch.get('sides', []):
            c = adapt(catch, s, floor=floor)
            if c: out.append(c)
    print(json.dumps(out, indent=1))

if __name__ == '__main__': main()
