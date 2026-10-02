#!/usr/bin/env python3
"""Fixture: the public Past Tickets archive shows no dollar amounts and no bankroll wording when the
builder's PAST_HIDE_MONEY option is on (the prepared default). Rendering only: the stored entries in
slates/past_tickets.json are untouched, every entry still renders, venue and odds stay, BOUGHT stays
distinct from SUGGESTED. Runs the emitted Past Tickets client script under node against a fixture
and the live archive file, for both twin builders. Option off must still show the stored text."""
import json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
failures = 0
def check(name, cond, detail=''):
    global failures
    print(('OK  ' if cond else 'FAIL'), name, '' if cond else detail)
    if not cond: failures += 1

MONEY = re.compile(r'\$\s?\d')
FIXTURE = {'entries': [
    {'id': 'f1', 'kind': 'ticket', 'origin': 'bought', 'title': '7 Pick Combo', 'result': 'lost',
     'detail': 'Kalshi app - bought $0.04, to pay $3.00', 'legs': [{'player': 'A', 'market': 'Anytime TD Scorer'}],
     'reason': 'Combo lost', 'removed_label': 'Sep 27'},
    {'id': 'f2', 'kind': 'ticket', 'origin': 'bought', 'title': '5-leg SGP', 'result': 'lost',
     'detail': 'Fanatics +1500 - FanCash $0.23', 'reason': 'Combo lost', 'removed_label': 'Sep 27'},
    {'id': 'f3', 'kind': 'ticket', 'origin': 'bought', 'title': '5-leg SGP · +1050 · Fanatics', 'result': 'lost',
     'detail': 'Fanatics - bought $0.21 FanCash', 'reason': 'Ticket lost', 'removed_label': 'Sep 27'},
    {'id': 'f4', 'kind': 'combo', 'origin': 'suggested', 'title': 'Bankroll Builder - BAL @ DAL', 'result': 'lost',
     'detail': 'Sum of individual asks 163c', 'reason': 'Combo lost - Mark Andrews leg lost, game final',
     'removed_label': 'Sep 27'},
    {'id': 'f5', 'kind': 'pick', 'origin': 'suggested', 'title': 'Plain pick', 'result': 'won',
     'detail': 'DK +120', 'reason': 'Pick won - game final', 'removed_label': 'Sep 28'},
]}
HARNESS = r'''
var data = JSON.parse(require('fs').readFileSync(process.argv[3], 'utf8'));
var els = {rpPastBox: {innerHTML: ''}, rpPastBar: {innerHTML: '', querySelectorAll: function () { return []; }}};
global.document = {getElementById: function (id) { return els[id] || null; }};
global.fetch = function () { return Promise.resolve({ok: true, json: function () { return data; }}); };
require('vm').runInThisContext(require('fs').readFileSync(process.argv[2], 'utf8'));
setTimeout(function () { process.stdout.write(els.rpPastBox.innerHTML); }, 50);
'''
tmp = tempfile.mkdtemp(prefix='past_money_')
open(os.path.join(tmp, 'h.js'), 'w').write(HARNESS)
json.dump(FIXTURE, open(os.path.join(tmp, 'fx.json'), 'w'))
LIVE = os.path.join(ROOT, 'slates', 'past_tickets.json')

def render(src, hide, data_path):
    a = src.index('    past_entry=(')
    b = src.index("r'})();</script>')", a) + len("r'})();</script>')")
    block = '\n'.join(l[4:] for l in src[a:b].split('\n'))
    ns = {'PAST_HIDE_MONEY': hide}
    exec(block, ns)
    js = ns['past_entry'].split('<script>', 1)[1].rsplit('</script>', 1)[0]
    p = os.path.join(tmp, 'past.js'); open(p, 'w').write(js)
    r = subprocess.run(['node', os.path.join(tmp, 'h.js'), p, data_path], capture_output=True, text=True)
    if r.returncode: print(r.stderr[:400])
    return r.stdout

for B in ('build_gh_page_v2.py', '_build_nocanon_v2.py'):
    src = open(os.path.join(ROOT, 'scripts', B)).read()
    check(f'{B}: PAST_HIDE_MONEY option present and on', bool(re.search(r'^\s*PAST_HIDE_MONEY\s*=\s*True\b', src, re.M)))
    on = render(src, True, os.path.join(tmp, 'fx.json'))
    check(f'{B}: option on renders every fixture entry', on.count('Removed ') == len(FIXTURE['entries']), on[:200])
    check(f'{B}: option on shows no dollar amount', not MONEY.search(on), MONEY.findall(on))
    check(f'{B}: option on shows no bankroll wording', 'bankroll' not in on.lower())
    check(f'{B}: venue and odds kept', all(s in on for s in ('Kalshi app', 'Fanatics +1500', '>Fanatics<', 'DK +120', 'Sum of individual asks 163c')))
    check(f'{B}: combo title keeps matchup', 'Combo - BAL @ DAL' in on)
    check(f'{B}: BOUGHT stays distinct from SUGGESTED', on.count('BOUGHT TICKET') == 3 and on.count('SUGGESTED') == 2)
    check(f'{B}: other text untouched', 'Combo lost - Mark Andrews leg lost, game final' in on and 'Pick won - game final' in on)
    off = render(src, False, os.path.join(tmp, 'fx.json'))
    check(f'{B}: option off still shows the stored text', all(s in off for s in ('$0.04, to pay $3.00', 'FanCash $0.23', 'Bankroll Builder - BAL @ DAL')))
    if os.path.exists(LIVE):
        ents = json.load(open(LIVE)).get('entries') or []
        n = len(ents)
        stamped = sum(1 for e in ents if e.get('removed_label') or e.get('archived_at'))  # LS-15: no stamp without a removal time
        live = render(src, True, LIVE)
        check(f'{B}: live archive ({n} entries) renders with no dollar amount or bankroll wording',
              live.count('border-radius:12px;padding:11px 12px') == n and live.count('Removed ') == stamped
              and not MONEY.search(live) and 'bankroll' not in live.lower(), (MONEY.findall(live)[:4], live.count('Removed '), stamped))

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
