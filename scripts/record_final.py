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
import json, re, re, os, re, sys, urllib.request
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


def espn_verify_mma(league, eid, comp_id, q):
    """MMA independent check (9/29 Abushaar DWCS class): ESPN core MMA carries NO point scores
    and NO home/away assignment, so the generic score-compare cannot run. Verification is:
    competition completed + exactly 2 fighters with exactly one winner flag + the row's picked
    fighter identified uniquely by displayName inside the pick text + result consistent with
    the winner flag + opponent identity bound to the attested graded_pick text. competition_id
    is REQUIRED: MMA event ids and competition ids differ (event 600060739, comp 401891663)."""
    if not comp_id:
        print('  verify mma: competition_id required - MMA event ids and competition ids differ', file=sys.stderr)
        return None
    lg = league.replace('/', '/leagues/')
    base = f'https://sports.core.api.espn.com/v2/sports/{lg}/events/{eid}/competitions/{comp_id}'
    try:
        c = _get(base)
        st = _deref(c.get('status', {})).get('type', {})
        if not st.get('completed'):
            print(f'  verify mma {eid}/{comp_id}: not completed ({st.get("name")})', file=sys.stderr)
            return None
        fighters = []
        for comp in c.get('competitors', []):
            comp = _deref(comp)
            ath = _deref(comp.get('athlete', comp.get('team', {})))
            fighters.append({'name': ath.get('displayName', ''), 'winner': bool(comp.get('winner'))})
        if len(fighters) != 2 or sum(1 for f in fighters if f['winner']) != 1:
            print(f'  verify mma {eid}/{comp_id}: need 2 fighters and exactly one winner, got {fighters}', file=sys.stderr)
            return None
        def _name_hit(fname, text, other):
            # attestation texts may carry last names only ("Staines def. Abushaar"): word-bounded
            # full-name hit, else word-bounded last-name hit when the two fighters' last names
            # differ (fail-closed; bare substring would false-hit "Schmabushaar").
            t = (text or '').lower()
            full = (fname or '').lower()
            if full and re.search(r'\b' + re.escape(full) + r'\b', t):
                return True
            last, olast = full.split()[-1], (other or '').lower().split()[-1]
            return bool(last) and last != olast and bool(re.search(r'\b' + re.escape(last) + r'\b', t))
        pick_txt = q.get('pick') or ''
        picked = [f for f in fighters if f['name'] and _name_hit(f['name'], pick_txt, next(g['name'] for g in fighters if g is not f))]
        if len(picked) != 1:
            print(f'  verify mma {eid}/{comp_id}: picked fighter not uniquely identified in {q.get("pick")!r}', file=sys.stderr)
            return None
        picked = picked[0]
        opp = next(f for f in fighters if f is not picked)
        res = q.get('result')
        if (res == 'WON' and not picked['winner']) or (res == 'LOST' and picked['winner']):
            print(f'  verify mma {eid}/{comp_id}: result {res} contradicts winner flags {fighters}', file=sys.stderr)
            return None
        gp = q.get('graded_pick') or ''
        if not _name_hit(opp['name'], gp, picked['name']):
            print(f'  verify mma {eid}/{comp_id}: opponent {opp["name"]!r} absent from attested graded_pick', file=sys.stderr)
            return None
        return {'picked': picked['name'], 'opp': opp['name'],
                'winner': next(f['name'] for f in fighters if f['winner'])}
    except Exception as e:
        print(f'  verify mma {eid}/{comp_id}: espn error {type(e).__name__}: {e}', file=sys.stderr)
        return None

SCORE_RE = re.compile(r'^([A-Z]{2,4})\s+(\d+)\s*@\s*([A-Z]{2,4})\s+(\d+)$')

def fmt_units(d):
    d = Decimal(d).quantize(Decimal('0.01'))
    return ('+' if d >= 0 else '') + f'{d}u'

def nick(display):
    # "New York Jets" -> "Jets"; "New York Liberty" -> "Liberty"
    parts = display.split()
    return parts[-1] if parts else display


def eod_day_close(p):
    """EOD DAY CLOSE wire (analysis, Sep 28): the brief travels IN the payload.
    eod_day_close.py itself can NEVER run here - its sheet reads shell out to the
    analysis runtime. Verify anchors fail-closed, then fill the day-row brief ONLY.
    Canonical pick rows and _delta fields are never touched; no row creation."""
    date = p.get('date')
    brief = p.get('brief')
    if not date or not isinstance(brief, str) or not brief.strip():
        print('  REFUSE eod_day_close: missing date or empty brief', file=sys.stderr)
        return 3
    hist = json.load(open(HIST))
    day = next((d for d in hist['days'] if d.get('date') == date), None)
    if day is None:
        print(f'  REFUSE eod_day_close: no chain-written day row for {date} - no row creation', file=sys.stderr)
        return 3
    if not day['picks'] or any(pk.get('result') not in ('W', 'L', 'P') for pk in day['picks']):
        print(f'  REFUSE eod_day_close: ungraded picks remain in {date} row', file=sys.stderr)
        return 3
    if p.get('record') != day.get('record'):
        print(f'  REFUSE eod_day_close: record anchor {p.get("record")} != day row {day.get("record")}', file=sys.stderr)
        return 3
    if not any('_delta' in pk for pk in day['picks']):
        print(f'  REFUSE eod_day_close: no _delta ledger fields in {date} row - not chain-written', file=sys.stderr)
        return 3
    du = sum((Decimal(pk['_delta']) for pk in day['picks'] if '_delta' in pk), Decimal('0'))
    try:
        pu = Decimal(str(p.get('units', '')).strip().rstrip('u'))
    except Exception:
        print(f'  REFUSE eod_day_close: unparsable units anchor {p.get("units")!r}', file=sys.stderr)
        return 3
    if pu != du and pu != du.quantize(Decimal('0.01')):
        print(f'  REFUSE eod_day_close: units anchor {pu} != exact day sum {du}', file=sys.stderr)
        return 3
    gid = 'eod_day_close:' + date
    done = {'processed': [], 'at': None}
    if os.path.exists(DONE):
        done = json.load(open(DONE))
    if gid in done.get('processed', []):
        print(f'  skip {gid}: already processed')
        json.dump({'requests': []}, open(REQ, 'w'), indent=2)
        return 0
    day['brief'] = brief
    json.dump(hist, open(HIST, 'w'), indent=2)
    done.setdefault('processed', []).append(gid)
    done['at'] = datetime.now(timezone.utc).isoformat()
    json.dump(done, open(DONE, 'w'), indent=2)
    json.dump({'requests': []}, open(REQ, 'w'), indent=2)
    print(f'EOD DAY CLOSE: brief filled for {date} (record {day["record"]}, units {fmt_units(du)})')
    # combo expiry wire: day close marks every combo dated on/before the cutoff as expired.
    # MARK, never delete - the audit trail stays; the display layer filters on status too.
    ce = p.get('combo_expiry')
    if isinstance(ce, dict) and ce.get('action') == 'mark_expired':
        target = ce.get('target'); cutoff = str(ce.get('expire_on_or_before') or '')
        if not target or not re.match(r'^\d{4}-\d{2}-\d{2}$', cutoff):
            print('  REFUSE combo_expiry: bad target or cutoff', file=sys.stderr)
        else:
            tp = os.path.join(ROOT, target)
            try:
                cj = json.load(open(tp))
                n = 0
                for c in cj.get('combos') or []:
                    d = str(c.get('date') or c.get('game_date') or '')
                    if not d:
                        m = re.search(r'(\d{4})(\d{2})(\d{2})\s*$', str(c.get('id') or ''))
                        d = '%s-%s-%s' % m.groups() if m else ''
                    if d and d <= cutoff and c.get('status') != 'expired':
                        c['status'] = 'expired'
                        c['expired_at'] = datetime.now(timezone.utc).isoformat()
                        n += 1
                if n:
                    json.dump(cj, open(tp, 'w'), indent=2)
                print(f'  combo_expiry: {n} marked expired in {target} (cutoff {cutoff})')
            except FileNotFoundError:
                print(f'  combo_expiry: {target} absent - nothing to mark')
    return 0

def main():
    if not os.path.exists(REQ):
        print('no record_request.json - nothing to do')
        return 0
    payload = json.load(open(REQ))
    if payload.get('kind') == 'eod_day_close':
        return eod_day_close(payload)
    reqs = payload.get('requests') or []
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
        # per-pick learnings (his 6:41 directive): optional, display-only, fail-closed on malformed.
        if 'learning' in q and (not isinstance(q['learning'], str) or not q['learning'].strip() or len(q['learning']) > 400):
            print(f'  REFUSE {gid}: learning must be a non-empty string <= 400 chars', file=sys.stderr)
            return 3
        if str(q.get('league') or '').startswith('mma/'):
            # MMA rows: winner-flag verification, no score compare (ESPN carries no MMA scores).
            info = espn_verify_mma(q['league'], q['event_id'], q.get('competition_id'), q)
            if info is None:
                print(f'  REFUSE {gid}: independent verification failed - chain stops, no write', file=sys.stderr)
                return 3
            if sorted((away_sc, home_sc)) != [0, 1]:
                print(f'  REFUSE {gid}: mma score convention is winner 1 / loser 0, got {q["score"]!r}', file=sys.stderr)
                return 3
            game = 'vs ' + nick(info['opp'])
            # display truth (main 6:46): the 1-0 encoding is a machine convention, never a shown
            # score - the stored/served row carries "Winner def. Loser" (build_history renders
            # the score field verbatim, so the display string lives in the data).
            _loser = info['picked'] if info['winner'] != info['picked'] else info['opp']
            score_txt = f'{nick(info["winner"])} def. {nick(_loser)}'
        else:
            comp = espn_verify(q['league'], q['event_id'], away_sc, home_sc)
            if comp is None:
                print(f'  REFUSE {gid}: independent verification failed - chain stops, no write', file=sys.stderr)
                return 3
            game = None  # computed after res, from comp, below
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
        if game is None:
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
            _row = {'name': q['pick'], 'game': game, 'odds': q['locked_american'],
                    'units': q['stake_units'], 'result': {'WON': 'W', 'LOST': 'L', 'PUSH': 'P'}[res],
                    'score': score_txt, '_delta': str(Decimal(str(q['delta_units_exact'])))}
            if isinstance(q.get('learning'), str) and q['learning'].strip():
                _row['learning'] = q['learning'].strip()
            day['picks'].append(_row)
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
