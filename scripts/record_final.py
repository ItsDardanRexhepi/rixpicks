#!/usr/bin/env python3
"""record_final.py - GHA-side record write on graded finals (main 9/27: record write moves into
a workflow, secrets never move; GITHUB_TOKEN commits). Self-contained: no private infra.

Input: record_request.json at repo root (analysis drops graded, ledger-verified requests;
each carries result, exact unit delta, record_after, units_after_exact, two-source attestation).
For each request, in order:
  1. INDEPENDENT verify against ESPN core (completed + scores match). Mismatch/stale -> stop,
     exit 3, no write. In-order processing: later finals wait for the next fire.
  2. Running record from manifest must chain into request.record_after exactly.
Apply: manifest record/units_pl, history.json day row (+day record/units), record_done.json.
Writes NOTHING to any private ledger - that stays analysis-side.
"""
import json, re, os, re, sys, urllib.request
from datetime import datetime, timezone
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
REQ = os.path.join(ROOT, 'record_request.json')
MAN = os.path.join(ROOT, 'manifest.json')
HIST = os.path.join(ROOT, 'history.json')
DONE = os.path.join(ROOT, 'record_done.json')

def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def _deref(node):
    return _get(node['$ref']) if isinstance(node, dict) and '$ref' in node else node

def espn_verify(league, eid, away_score, home_score):
    """Independent check: event completed AND scores match. Returns competitor map or None."""
    lg = league.replace('/', '/leagues/')
    base = f'https://sports.core.api.espn.com/v2/sports/{lg}/events/{eid}/competitions/{eid}'
    try:
        c = _get(base)
        st = _deref(c.get('status', {})).get('type', {})
        if not st.get('completed'):
            print(f'  verify {eid}: not completed ({st.get("name")})', file=sys.stderr)
            return None
        out = {}
        for comp in c.get('competitors', []):
            comp = _deref(comp)
            team = _deref(comp.get('team', {}))
            sc = _deref(comp.get('score', {}))
            val = sc.get('value') if isinstance(sc, dict) else None
            try: val = int(float(val))
            except (TypeError, ValueError): val = None
            out[comp.get('homeAway')] = {'name': team.get('displayName', ''), 'score': val}
        if out.get('home', {}).get('score') != home_score or out.get('away', {}).get('score') != away_score:
            print(f'  verify {eid}: score mismatch espn {out} vs req {away_score}-{home_score}', file=sys.stderr)
            return None
        return out
    except Exception as e:
        print(f'  verify {eid}: espn error {type(e).__name__}: {e}', file=sys.stderr)
        return None

SCORE_RE = re.compile(r'^([A-Z]{2,4})\s+(\d+)\s*@\s*([A-Z]{2,4})\s+(\d+)$')

def fmt_units(d):
    d = Decimal(d).quantize(Decimal('0.01'))
    return ('+' if d >= 0 else '') + f'{d}u'

def nick(display):
    # "New York Jets" -> "Jets"; "New York Liberty" -> "Liberty"
    parts = display.split()
    return parts[-1] if parts else display

def main():
    if not os.path.exists(REQ):
        print('no record_request.json - nothing to do')
        return 0
    reqs = (json.load(open(REQ)).get('requests')) or []
    if not reqs:
        print('record_request.json empty - nothing to do')
        return 0
    man = json.load(open(MAN))
    hist = json.load(open(HIST))
    done = {'processed': [], 'at': None}
    if os.path.exists(DONE):
        done = json.load(open(DONE))

    rw, rl = [int(x) for x in man['record'].split('-')[:2]]
    processed = []
    for q in reqs:
        gid = q['grade_id']
        if gid in done.get('processed', []):
            print(f'  skip {gid}: already processed')
            continue
        m = SCORE_RE.match(q['score'].strip())
        if not m:
            print(f'  REFUSE {gid}: unparseable score {q["score"]!r}', file=sys.stderr)
            return 3
        away_ab, away_sc, home_ab, home_sc = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
        comp = espn_verify(q['league'], q['event_id'], away_sc, home_sc)
        if comp is None:
            print(f'  REFUSE {gid}: independent verification failed - chain stops, no write', file=sys.stderr)
            return 3
        res = q['result']
        if res == 'WON': rw += 1
        elif res == 'LOST': rl += 1
        elif res != 'PUSH':
            print(f'  REFUSE {gid}: unknown result {res!r}', file=sys.stderr)
            return 3
        expected = q['record_after']
        if f'{rw}-{rl}' != expected:
            print(f'  REFUSE {gid}: chain mismatch - running {rw}-{rl} != record_after {expected}', file=sys.stderr)
            return 3
        # history day row
        opp = comp['away' if q['side'] == 'home' else 'home']['name']
        game = ('vs ' if q['side'] == 'home' else 'at ') + nick(opp)
        score_txt = f'{away_ab} {away_sc}, {home_ab} {home_sc}'
        day_date = man.get('date') or datetime.now(timezone.utc).strftime('%Y-%m-%d')
        days = hist['days']
        day = days[-1] if days and days[-1]['date'] == day_date else None
        if day is None:
            d0 = datetime.strptime(day_date, '%Y-%m-%d')
            day = {'date': day_date, 'label': d0.strftime('%A, %b %-d'), 'record': '0-0', 'units': '+0.00u',
                   'brief': '', 'picks': []}
            days.append(day)
        if not any(p.get('name') == q['pick'] and p.get('score') == score_txt for p in day['picks']):
            day['picks'].append({'name': q['pick'], 'game': game, 'odds': q['locked_american'],
                                 'units': q['stake_units'], 'result': {'WON': 'W', 'LOST': 'L', 'PUSH': 'P'}[res],
                                 'score': score_txt, '_delta': str(Decimal(str(q['delta_units_exact'])))})
        dw = sum(1 for p in day['picks'] if p['result'] == 'W')
        dl = sum(1 for p in day['picks'] if p['result'] == 'L')
        day['record'] = f'{dw}-{dl}'
        processed.append((q, Decimal(str(q['delta_units_exact']))))
        print(f'  graded {gid}: {q["pick"]} {res} {score_txt} -> record {rw}-{rl}')

    if not processed:
        print('nothing new processed')
        return 0
    # ROUND-ONCE CORE RULE (main 9/27 3:19): deltas and units_after_exact travel at FULL
    # ledger precision; every displayed total is computed from exact canonical values and
    # quantized ONCE at display time. Never sum pre-rounded deltas - one-cent drift results.
    # day units = exact sum of per-pick deltas graded into this day
    day = hist['days'][-1]
    du = sum((Decimal(p['_delta']) for p in day['picks'] if '_delta' in p), Decimal('0'))
    if any('_delta' in p for p in day['picks']):
        day['units'] = fmt_units(du)

    last = processed[-1][0]
    man['record'] = last['record_after']
    man['units_pl'] = fmt_units(Decimal(str(last['units_after_exact'])))
    # freshness truth (main Sep 27): the write moves manifest state, so its freshness label
    # must move with it - stamp `updated` at write time, PT, same display format ingest uses.
    from zoneinfo import ZoneInfo as _ZI
    import datetime as _dtc
    _now=_dtc.datetime.now(_ZI('America/Los_Angeles'))
    man['updated']=re.sub(r'(\d), 0', r'\1, ', _now.strftime('%b %d, %I:%M %p PT').replace(' 0',' '))
    done.setdefault('processed', []).extend(q['grade_id'] for q, _ in processed)
    done['at'] = datetime.now(timezone.utc).isoformat()
    remaining = [q for q in reqs if q['grade_id'] not in done['processed']]

    json.dump(man, open(MAN, 'w'), indent=2)
    json.dump(hist, open(HIST, 'w'), indent=2)
    json.dump(done, open(DONE, 'w'), indent=2)
    json.dump({'requests': remaining}, open(REQ, 'w'), indent=2)
    # API MIRROR (main 9/27 6:20, option B): slates/api_record.json in the
    # api.rix-picks.com/record worker's exact GET shape, emitted on every apply.
    # graded_pick/source ride in analysis's request payload; omitted when absent -
    # no invented state.
    mirror = {
        'w': rw, 'l': rl,
        'pct': float((Decimal(rw * 100) / (rw + rl)).quantize(Decimal('0.1'))) if (rw + rl) else 0.0,
        'units': float(Decimal(str(last['units_after_exact'])).quantize(Decimal('0.01'))),
        'updated': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
    }
    if last.get('graded_pick'):
        mirror['graded_pick'] = last['graded_pick']
    if last.get('source'):
        mirror['source'] = last['source']
    json.dump(mirror, open(os.path.join(ROOT, 'slates', 'api_record.json'), 'w'), indent=1)
    print(f'RECORD WRITE: record {man["record"]} units {man["units_pl"]}; {len(processed)} graded, {len(remaining)} remain')
    return 0

if __name__ == '__main__':
    sys.exit(main())
