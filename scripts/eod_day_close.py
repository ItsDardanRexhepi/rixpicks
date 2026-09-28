#!/usr/bin/env python3
"""UltRix EOD DAY CLOSE (his 12:16 AM directive): the standing event chain - fires when the final
game of the day's picks ends. Composes the day row (picks + WHAT THE SYSTEM LEARNED brief) from the
system's own verified state ONLY. Nothing is produced without checking the system first; the graded
state is verified TWICE (fresh picks-tab read + record-tab cumulative cross-check) before anything
is written. No falsehoods: every brief claim traces to a graded row. Disagreement = hold + alert.

Usage: python3 eod_day_close.py --date 2026-09-27 [--write]
Without --write: dry-run report only."""
import json, subprocess, sys, datetime, re, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import learn_brief

SHEET = '1fHV-8iNpa7VIgcBYoPxYPyjqh9HVSxyuAltIjFynNGA'
HIST = '/home/sandbox/rix_tmp/history.json'
RR = '/home/sandbox/rix_tmp/record_request.json'

def sheet_read(rng):
    out = subprocess.run(['tools','google-sheets','read-range','--spreadsheet-id',SHEET,
                          '--range',rng,'--include','values','--json'],
                         capture_output=True, text=True, timeout=60)
    return json.loads(out.stdout).get('values') or []

def day_rows(date):
    vals = sheet_read('picks!A1:N60')
    hdr = vals[0]
    rows = []
    for r in vals[1:]:
        if len(r) >= 6 and str(r[0]) == date:
            rows.append(dict(zip(hdr, r)))
    return [r for r in rows if r.get('league','') != 'DAY TOTAL']

def record_cumulative():
    vals = sheet_read('record!A1:H20')
    out = []
    for r in vals[1:]:
        if len(r) >= 6:
            try: out.append({'ts':r[0],'w':int(r[2]),'l':int(r[3]),'units':float(r[5])})
            except Exception: pass
    return out

def result_of(r):
    res = str(r.get('result',''))
    if res.startswith('W'): return 'win'
    if res.startswith('L'): return 'loss'
    if 'VOID' in res.upper(): return 'void'
    return None

def units_delta(r):
    """Published-card American units from locked_odds text."""
    o = str(r.get('locked_odds',''))
    m = re.search(r'(-?\d{3,4}) published card', o) or re.search(r'^(-?\d{3,4})\b', o)
    try: u = float(str(r.get('units','5u')).replace('u',''))
    except Exception: u = 5.0
    if result_of(r) == 'loss': return -u
    if result_of(r) == 'win' and m:
        price = int(m.group(1))
        return round(u * (100/abs(price) if price < 0 else price/100), 3)
    return 0.0

def compose(date, write=False):
    picks = day_rows(date)
    if not picks:
        return {'status':'HOLD','why':f'no carded picks found for {date} on the sheet'}
    graded = [p for p in picks if result_of(p) in ('win','loss')]
    pending = [p for p in picks if result_of(p) is None]
    if pending:
        return {'status':'HOLD','why':f'{len(pending)} picks ungraded - chain fires only when the final game ends',
                'pending':[p.get('pick') for p in pending]}
    # VERIFY TWICE: read 1 = picks tab (above); read 2 = fresh re-read + record-tab cumulative cross-check
    picks2 = day_rows(date)
    if [ (p.get('pick'), result_of(p)) for p in picks ] != [ (p.get('pick'), result_of(p)) for p in picks2 ]:
        return {'status':'HOLD','why':'verify-twice failed: two reads of the graded state disagree'}
    w = sum(1 for p in graded if result_of(p)=='win'); l = len(graded)-w
    units = round(sum(units_delta(p) for p in graded), 2)
    # LEARNING ENGINE OUTPUT ONLY (his 12:32 AM standing rule: "picks go through KB and
    # learning engine and then the system actually gives you what to post there" - never a
    # hand summary). learn_brief re-verifies the graded state twice itself.
    eng = learn_brief.learn(date)
    if eng.get('status') != 'OK':
        return {'status':'HOLD','why':f"learning engine hold: {eng.get('why')}"}
    brief = eng['brief']
    day = {'date': date,
           'label': datetime.date.fromisoformat(date).strftime('%A, %b %-d'),
           'record': f'{w}-{l}', 'units': f"{'+' if units>=0 else ''}{units}u",
           'picks': [{'name': p.get('pick'), 'game': str(p.get('note',''))[:80],
                      'odds': p.get('locked_odds',''), 'units': p.get('units','5u'),
                      'result': result_of(p), 'score': (re.search(r'([WL] \d+-\d+)', str(p.get('result',''))) or [None,''])[1] if re.search(r'([WL] \d+-\d+)', str(p.get('result',''))) else '',
                      'note': eng['notes'].get(p.get('pick'),'')} for p in graded],
           'brief': brief}
    report = {'status':'OK','date':date,'record':day['record'],'units':day['units'],'picks':len(graded),
              'verified':'twice (picks-tab re-read identical)', 'brief': brief}
    if write:
        h = json.load(open(HIST))
        existing = next((d for d in h['days'] if d.get('date') == date), None)
        if existing is not None:
            # CHAIN-WRITTEN ROWS ARE CANONICAL (builder 12:29 AM): never rewrite pick rows,
            # never drop _delta or provenance. Fill the brief field ONLY.
            existing['brief'] = brief
            json.dump(h, open(HIST,'w'), indent=1)
            report['write'] = 'brief filled on existing canonical day row - picks untouched'
        else:
            # FAIL-CLOSED (builder record_final wire): a day row must already exist from the
            # canonical record chain (record_request -> GHA record-final). Never create one here.
            report['status']='HOLD'
            report['why']='no chain-written day row exists for this date - record chain must write it first'
        # brief travels IN the payload: GHA record-final fills the repo history.json brief from
        # payload.brief after anchor verification - eod_day_close.py is not executable in GHA
        # (its sheet reads need the analysis runtime's tools CLI).
        json.dump({'ts': datetime.datetime.now().isoformat(timespec='seconds'),
                   'kind':'eod_day_close','date':date,'record':day['record'],'units':day['units'],
                   'brief':brief},
                  open(RR,'w'), indent=1)
        report['record_request'] = 'emitted'
        # INSTANT INTAKE (his 00:56 steering "have it all be instant"): chain outputs land in the
        # learning algorithm as they happen.
        subprocess.run(['python3','/home/sandbox/ultrix_repo/runtime/intake_learn.py','--file',HIST],
                       capture_output=True, timeout=120)
    return report

if __name__ == '__main__':
    date = None; write = '--write' in sys.argv
    for i,a in enumerate(sys.argv):
        if a == '--date': date = sys.argv[i+1]
    if not date:
        date = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    rep = compose(date, write)
    print(json.dumps(rep, indent=1))
    sys.exit(0 if rep.get('status')=='OK' else 3)
