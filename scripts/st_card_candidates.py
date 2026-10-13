#!/usr/bin/env python3
"""s/t ADAPTER (pipeline step 3, wired 9/27): st_fair rows -> build_manifest candidate schema.
Mirrors st_hunt.candidate gates (P-EDGE-001 net >= 2c IN FORCE per governing 6:35 PM sequence).
Spread pick: side='home' (home-cover), line=consensus home spread (odds-api sign: <0 home favored).
  Kalshi position may be YES (home favored) or NO (away favored) - contract_side carried for ops;
  grading/ledger identity uses side='home' + line, which is contract-side-independent.
Total pick: side='over', line=consensus total (engine evaluates the over side only).
EID: resolved from the ESPN scoreboard (python-urllib UA; Mozilla 403s from this IP) matched on
  full team names; FAIL-CLOSED skip (loud) when no unique match. --eid-map JSON {match: eid}
  overrides resolution (tests + manual repair only).
IN : st_fair.py JSON list (path arg or stdin)
OUT: JSON list of build_manifest candidates (ml candidates merge in the build runbook)."""
import json, sys, re, urllib.request as _u
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ESPN_LEAGUE = {'nfl': 'football/nfl', 'mlb': 'baseball/mlb', 'nba': 'basketball/nba', 'wnba': 'basketball/wnba'}

LADDER = ((5, 60, 2), (6, 60, 3), (7, 70, 1), (8, 70, 2), (9, 70, 3), (10, 80, 3))

def tier_eval(ask_c, gross_c, net_c=None):
    # THE LADDER (owner 2026-10-13; scripts/build_manifest.py LADDER mirrors RixPicksSystem engine/ladder.py): band = the
    # Kalshi ask the pick is bought at, floor = the edge after fees (gross AND net); the highest rung cleared; 0 = not a
    # pick. 5u = 60c + 2c, 6u = 60c + 3c, 7u = 70c + 1c, 8u = 70c + 2c, 9u = 70c + 3c, 10u = 80c + 3c; no 15u, no 100u.
    # Replaces the J-096 rungs, the 2026-10-06 no-band and the 2026-10-07 1c floor.
    net_c = gross_c if net_c is None else net_c
    best = 0
    for u, b, f in LADDER:
        if ask_c >= b and gross_c >= f and net_c >= f: best = u
    return best

def short(name):
    return (name or '').split()[-1] if name else ''

def espn_events(league, ymd):
    url = (f'https://site.api.espn.com/apis/site/v2/sports/{league}/scoreboard'
           f'?dates={ymd.replace("-","")}&limit=200')
    req = _u.Request(url, headers={'User-Agent': 'python-urllib/3.10'})
    with _u.urlopen(req, timeout=20) as r:
        return json.load(r).get('events', [])

def resolve_eid(row, cache, eid_map):
    key = row['match']
    if key in eid_map: return eid_map[key], True
    lg = ESPN_LEAGUE.get((row.get('sport') or '').lower())
    if not lg: return None, False
    ymd = datetime.fromisoformat(row['commence'].replace('Z', '+00:00')).astimezone(ZoneInfo('America/Los_Angeles')).strftime('%Y-%m-%d')
    if (lg, ymd) not in cache:
        cache[(lg, ymd)] = espn_events(lg, ymd)
    a, h = row['away'].casefold(), row['home'].casefold()
    hits = []
    for ev in cache[(lg, ymd)]:
        comp = ev.get('competitions', [{}])[0]
        teams = {c.get('homeAway'): (c.get('team', {}).get('displayName') or '').casefold()
                 for c in comp.get('competitors', [])}
        if teams.get('away') == a and teams.get('home') == h:
            hits.append(ev.get('id'))
    uniq = list(dict.fromkeys(hits))
    return (uniq[0], False) if len(uniq) == 1 else (None, False)

def adapt(row, cache, eid_map, floor=True):
    # gates mirror st_hunt.candidate: needs anchored kalshi + net >= 2c (P-EDGE-001);
    # floor=False only for the governing-sequence floorless fallback pass.
    if row.get('net_c') is None: return None
    if row['net_c'] < (2 if floor else 0): return None  # floorless: zero-edge gate stands
    cls = row['cls']
    if cls not in ('spread', 'total'): return None
    cons = row['consensus_line']
    fair_c = row['fair_home_or_over_c']          # fair of the PICKED side (home-cover / over)
    units = tier_eval(round(row['kalshi']['ask'] * 100), row['gross_c'], row['net_c'])
    if units == 0: return None                    # no rung on the ladder (under the band or its floor)
    eid, overridden = resolve_eid(row, cache, eid_map)
    if not eid:
        print(f"SKIP (fail closed): no unique ESPN eid for {row['match']} {cls}", file=sys.stderr)
        return None
    a_s, h_s = short(row['away']), short(row['home'])
    k = row['kalshi']
    if cls == 'spread':
        name = f"{h_s} {cons:+g}"
        sub = f"vs {a_s} - home cover - cons {cons:+g}, {row['n_books']} books"
        team = h_s
    else:
        name = f"Over {cons:g}"
        sub = f"{a_s} @ {h_s} - over {cons:g}, {row['n_books']} books"
        team = f"{a_s} @ {h_s}"
    out = {'date': datetime.fromisoformat(row['commence'].replace('Z', '+00:00'))
                        .astimezone(ZoneInfo('America/Los_Angeles')).strftime('%Y-%m-%d'),
            'market_class': cls, 'name': name, 'side': 'home' if cls == 'spread' else 'over',
            'line': cons, 'away': row['away'], 'home': row['home'], 'commence': row['commence'],
            'eid': str(eid), 'espn_league': ESPN_LEAGUE[(row.get('sport') or '').lower()],
            'units': f'{units}u', 'model': fair_c, 'gross_c': row['gross_c'], 'net_c': row['net_c'],
            'sub_context': sub + (' [WIDE-BOOK]' if k.get('tag') == 'WIDE-BOOK' else ''),
            'kalshi': {'cents': round(k['ask'] * 100), 'team': team, 'ticker': k['ticker'],
                       'contract_side': k.get('side')}}
    return out

def adapt_alt(row, eid):
    # OPPOSITE SIDE (his 6:45:32 PM PT 9/27): away-cover / under candidates from row['alt'].
    # CONVENTION: 'line' is ALWAYS the home spread (odds-api sign) / game total - grading keys
    # on it with side='away'/'under'; the away-cover DISPLAY name carries the away line (-cons).
    cls = row['cls']; cons = row['consensus_line']; alt = row['alt']
    a_s, h_s = short(row['away']), short(row['home'])
    fair_c = alt['fair_c']; k = alt['kalshi']
    if cls == 'spread':
        name = f"{a_s} {-cons:+g}"
        sub = f"@ {h_s} - away cover - cons {-cons:+g}, {row['n_books']} books"
        side, team = 'away', a_s
    else:
        name = f"Under {cons:g}"
        sub = f"{a_s} @ {h_s} - under {cons:g}, {row['n_books']} books"
        side, team = 'under', f"{a_s} @ {h_s}"
    return {'date': datetime.fromisoformat(row['commence'].replace('Z', '+00:00'))
                        .astimezone(ZoneInfo('America/Los_Angeles')).strftime('%Y-%m-%d'),
            'market_class': cls, 'name': name, 'side': side,
            'line': cons, 'away': row['away'], 'home': row['home'], 'commence': row['commence'],
            'eid': str(eid), 'espn_league': ESPN_LEAGUE[(row.get('sport') or '').lower()],
            'units': None,  # filled by caller after tier_eval
            'model': fair_c, 'gross_c': alt['gross_c'], 'net_c': alt['net_c'],
            'sub_context': sub + (' [WIDE-BOOK]' if k.get('tag') == 'WIDE-BOOK' else ''),
            'kalshi': {'cents': round(k['ask'] * 100), 'team': team, 'ticker': k['ticker'],
                       'contract_side': k.get('side')}}

def main():
    rows = json.load(open(sys.argv[1])) if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else json.load(sys.stdin)
    eid_map = {}
    if '--eid-map' in sys.argv:
        eid_map = json.load(open(sys.argv[sys.argv.index('--eid-map') + 1]))
    cache = {}
    out = []
    floor = '--no-floor' not in sys.argv
    for r in rows:
        c = adapt(r, cache, eid_map, floor=floor)
        if c: out.append(c)
        alt = r.get('alt')
        if alt and alt.get('net_c') is not None and alt['net_c'] >= (2 if floor else 0):
            aunits = tier_eval(round(alt['kalshi']['ask'] * 100), alt['gross_c'], alt['net_c'])
            if aunits == 0: continue  # no rung on the ladder (under the band or its floor), floor or not
            eid, _ = resolve_eid(r, cache, eid_map)
            if not eid:
                print(f"SKIP (fail closed): no unique ESPN eid for {r['match']} {r['cls']} alt-side", file=sys.stderr)
                continue
            ca = adapt_alt(r, eid)
            ca['units'] = f'{aunits}u'
            out.append(ca)
    print(json.dumps(out, indent=1))

if __name__ == '__main__': main()
