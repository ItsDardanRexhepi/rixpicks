#!/usr/bin/env python3
"""Spread line convention and the optional pick_line field at the page builder's standing-rules card hold.
LINE CONVENTION (unchanged, graded as is): a spread pick's manifest 'line' is the HOME spread whichever side is
picked - record_final.score_result grades diff = home + line - away (home covers when diff > 0) - so the away pick
'Flyers +1.5' is stored line -1.5; a total's line is the total itself. pick_line (optional) is the same line read
from the PICKED side: spread away -> -line, spread home -> line, total -> line. The builder holds the current card
(exit 3, nothing written) when:
 - pick_line is present and is not that derived value, is not a number, sits on a moneyline, or has no numeric line
   (or no home/away side) to check against;
 - a spread pick's name ends in a number ('Flyers +1.5') that is not its picked side's line (e.g. 'Flyers -1.5'
   stored away line -1.5, or a picked-side value stored as the home line).
The name's line is read by the builder's _name_line, which is also the page's own fallback for a pick with no line:
a typographic minus (U+2212) reads as '-', one trailing American price is not the line ('Flyers +1.5 -110' says
+1.5), and a digit glued to a letter is no number ('Lightning -0.5 F5', '-2.5 Q1', '+1.5 P1' end in no line, so they
build, and a legacy pick so named with no line shows no line rather than 5 or 1).
These holds are never waived by the owner suspension. Cards with the convention right build - with or without
pick_line, and the legacy hand-manifest spread with no line - and pick_line puts nothing new on the page.
Builds run in a throwaway tree with the network sent to a dead proxy.
Run: python3 scripts/test_pick_line_hold.py [builder.py ...]   (default: both twins)"""
import copy, json, os, re, shutil, subprocess, sys, tempfile

from fixtures.card_contract import stamped, market, published_snapshot

SD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SD)
BUILDERS = [os.path.abspath(a) for a in sys.argv[1:]] or [os.path.join(SD, 'build_gh_page_v2.py'), os.path.join(SD, '_build_nocanon_v2.py')]
DEAD = 'http://127.0.0.1:9'
failures = 0

def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or detail == '' else '  [' + str(detail)[-400:] + ']'))
    if not ok:
        failures += 1

def build(builder, manifest, log=None):
    d = tempfile.mkdtemp(prefix='rp-pickline-')
    try:
        os.makedirs(os.path.join(d, 'scripts')); os.makedirs(os.path.join(d, 'slates'))
        bsrc = os.path.dirname(builder)
        shutil.copy(builder, os.path.join(d, 'scripts', 'build_gh_page_v2.py'))
        for f in ('index_v2.js', 'index_v2.css', 'game_page_template.html', 'team_page_template.html', 'poly_us.py'):
            shutil.copy(os.path.join(bsrc if os.path.exists(os.path.join(bsrc, f)) else SD, f), os.path.join(d, 'scripts', f))
        for f in ('feed_arbiter.js', 'feed_registry.json', 'config_leagues.json'):
            shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
        manifest=stamped(builder,manifest)
        json.dump(manifest, open(os.path.join(d, 'manifest.json'), 'w'), indent=1)
        published_snapshot(d,builder,manifest)
        json.dump([], open(os.path.join(d, 'slates', 'odds_prefill.json'), 'w'))
        if log is not None:
            open(os.path.join(d, 'slates', 'owner_rule_suspensions.jsonl'), 'w', encoding='utf-8').write(log)
        before = {os.path.relpath(os.path.join(p, f), d): os.path.getmtime(os.path.join(p, f)) for p, _, fs in os.walk(d) for f in fs}
        env = dict(os.environ, RP_REFRESH='1', http_proxy=DEAD, https_proxy=DEAD, HTTP_PROXY=DEAD, HTTPS_PROXY=DEAD, NO_PROXY='', no_proxy='')
        r = subprocess.run([sys.executable, os.path.join(d, 'scripts', 'build_gh_page_v2.py'), 'manifest.json', 'index.html'],
                           cwd=d, env=env, capture_output=True, text=True, timeout=600)
        after = {os.path.relpath(os.path.join(p, f), d): os.path.getmtime(os.path.join(p, f)) for p, _, fs in os.walk(d) for f in fs}
        written = sorted(f for f, t in after.items() if before.get(f) != t and '__pycache__' not in f)
        index = open(os.path.join(d, 'index.html'), encoding='utf-8').read() if 'index.html' in written else ''
        return r.returncode, r.stdout + r.stderr, written, index
    finally:
        shutil.rmtree(d, ignore_errors=True)

DATE = '2099-10-04'
BASE = {'date': DATE, 'date_label': 'Sunday, Oct 4', 'updated': 'Oct 4, 8:42 AM PT', 'record': '21-11',
        'units_pl': '+4.76u', 'units_ledger': None, 'yesterday': '', 'status_note': '', 'preview': False, 'parlay': None}
def pick(num, name, mclass='spread', side='away', line=None, model=66.0, **extra):
    # numerically clean (fair 66c, card ask 60c: gross 6c, net 4.32c, the 5u rung) so only the line can hold it
    p = {'num': num, 'name': name, 'market_class': mclass, 'sub': f'fixture - model {model:.1f}', 'odds': '-150',
         'card_american': -150, 'units': '5u', 'side': side,
         'game': {'away': 'Philadelphia Flyers', 'home': 'Tampa Bay Lightning', 'commence': '2099-10-04T23:00Z', 'eid': f'FIX-{num}'},
         'espn_league': 'hockey/nhl', 'league': 'NHL', 'best_book': 'Kalshi', 'card_source': 'Kalshi ask at lock'}
    if line is not None:
        p['line'] = line
    p=market(p)
    p.update(extra)
    return p
def card(picks, **kw):
    m = copy.deepcopy(BASE); m['picks'] = copy.deepcopy(picks); m.update(kw); return m
def held(rc, out, written):
    return rc == 3 and 'BUILD FAILED' in out and 'standing-rules card hold' in out and written == []
def data_lines(index):
    return re.findall(r'<div class="pick" [^>]*?data-market="(\w+)"(?: data-line="([^"]*)")?', index)

BUILDS = [
    ('away spread "Flyers +1.5", line -1.5 (home convention), no pick_line', [pick(1, 'Flyers +1.5', line=-1.5)]),
    ('away spread "Flyers +1.5", line -1.5, pick_line +1.5', [pick(1, 'Flyers +1.5', line=-1.5, pick_line=1.5)]),
    ('home spread "Lightning -1.5", line -1.5, pick_line -1.5', [pick(1, 'Lightning -1.5', side='home', line=-1.5, pick_line=-1.5)]),
    ('away spread "Flyers +1.5", numeric-string line "-1.5", pick_line 1.5 (int-valued float)', [pick(1, 'Flyers +1.5', line='-1.5', pick_line=1.5)]),
    ('away spread at a pick\'em "Flyers +0", line 0, pick_line 0', [pick(1, 'Flyers +0', line=0, pick_line=0)]),
    ('total "Over 5.5", line 5.5, pick_line 5.5', [pick(1, 'Over 5.5', mclass='total', side='over', line=5.5, pick_line=5.5)]),
    ('pick_line null (absent)', [pick(1, 'Flyers +1.5', line=-1.5, pick_line=None)]),
    ('legacy hand spread "Penn State -10" with no line (market:spread, no market_class)',
     [pick(1, 'Penn State -10', mclass=None, side='home', market='spread')]),
    ('away spread with no number in its name', [pick(1, 'Flyers puck line', line=-1.5)]),
    # the name's line is read by _name_line: no number glued to a letter, a typographic minus, a trailing price
    ('home run line "Lightning -0.5 F5" (F5 is no number), line -0.5', [pick(1, 'Lightning -0.5 F5', side='home', line=-0.5)]),
    ('home spread "Lightning -2.5 Q1" (Q1 is no number), line -2.5', [pick(1, 'Lightning -2.5 Q1', side='home', line=-2.5)]),
    ('away spread "Flyers +1.5 P1" (P1 is no number), line -1.5', [pick(1, 'Flyers +1.5 P1', line=-1.5)]),
    ('home spread "Lightning \u22121.5" (typographic minus), line -1.5', [pick(1, 'Lightning \u22121.5', side='home', line=-1.5)]),
    ('away spread "Flyers +1.5 -110" (a trailing price), line -1.5', [pick(1, 'Flyers +1.5 -110', line=-1.5)]),
    ('away spread "Flyers +1.5 (-110)" (a bracketed price), line -1.5, pick_line +1.5', [pick(1, 'Flyers +1.5 (-110)', line=-1.5, pick_line=1.5)]),
]
HOLDS = [
    ('pick_line -1.5 copied from the home-convention line on the away pick', [pick(1, 'Flyers +1.5', line=-1.5, pick_line=-1.5)],
     "pick_line -1.5 is not the away side's line +1.5"),
    ('away spread named "Flyers -1.5" with line -1.5 (the name is the home number)', [pick(1, 'Flyers -1.5', line=-1.5)],
     "name says -1.5 but the away side's line is +1.5"),
    ('away spread "Flyers +1.5" stored with the picked-side line +1.5', [pick(1, 'Flyers +1.5', line=1.5)],
     "name says +1.5 but the away side's line is -1.5"),
    ('home spread "Lightning +1.5" with line -1.5', [pick(1, 'Lightning +1.5', side='home', line=-1.5)],
     "name says +1.5 but the home side's line is -1.5"),
    ('total pick_line 6.5 against line 5.5', [pick(1, 'Over 5.5', mclass='total', side='over', line=5.5, pick_line=6.5)],
     'pick_line +6.5 is not its total line 5.5'),
    ('pick_line on a moneyline', [pick(1, 'Flyers ML', mclass='ml', pick_line=1.5)], 'on a moneyline pick'),
    ('pick_line as a string', [pick(1, 'Flyers +1.5', line=-1.5, pick_line='1.5')], "pick_line '1.5' is not a number"),
    ('pick_line true', [pick(1, 'Flyers +1.5', line=-1.5, pick_line=True)], 'pick_line True is not a number'),
    ('pick_line on a spread with no line', [pick(1, 'Flyers +1.5', pick_line=1.5)], 'has no spread line to check against'),
    ('pick_line on a spread whose side is not home or away', [pick(1, 'Flyers +1.5', side='over', line=-1.5, pick_line=1.5)],
     'has no spread line to check against'),
    ('away spread "Flyers \u22121.5" (typographic minus) with line -1.5', [pick(1, 'Flyers \u22121.5', line=-1.5)],
     "name says -1.5 but the away side's line is +1.5"),
    ('away spread "Flyers -1.5 -110" (the home number before a trailing price)', [pick(1, 'Flyers -1.5 -110', line=-1.5)],
     "name says -1.5 but the away side's line is +1.5"),
    ('home spread "Lightning +1.5 (-110)" with line -1.5', [pick(1, 'Lightning +1.5 (-110)', side='home', line=-1.5)],
     "name says +1.5 but the home side's line is -1.5"),
]

for B in BUILDERS:
    tag = os.path.basename(B)
    for label, picks in BUILDS:
        rc, out, written, _ = build(B, card(picks))
        check(f'{tag}: {label}: builds', rc == 0 and 'index.html' in written, (rc, out[-400:]))
    for label, picks, token in HOLDS:
        rc, out, written, _ = build(B, card(picks))
        check(f'{tag}: {label}: the card is held (exit 3, nothing written), the line named', held(rc, out, written) and token in out,
              (rc, out[-400:], written))

    # pick_line puts nothing new on the page: the pick row reads the same picked-side line with or without it
    _, _, _, plain = build(B, card([pick(1, 'Flyers +1.5', line=-1.5)]))
    _, _, _, withpl = build(B, card([pick(1, 'Flyers +1.5', line=-1.5, pick_line=1.5)]))
    check(f'{tag}: pick_line renders nothing new (same pick-row market and line, the word pick_line nowhere on the page)',
          data_lines(plain) == data_lines(withpl) == [('spread', '1.5')] and 'pick_line' not in withpl, (data_lines(plain), data_lines(withpl)))

    # a pick with no line reads its name through the same _name_line: never a glued period or quarter number, the
    # typographic minus as a minus, a trailing price dropped
    for name, want in (('Lightning -0.5 F5', []), ('Lightning \u22121.5', [('spread', '-1.5')]), ('Lightning -1.5 -110', [('spread', '-1.5')])):
        rc, out, written, index = build(B, card([pick(1, name, mclass=None, side='home', market='spread')]))
        check(f'{tag}: legacy spread {name!r} with no line: builds, the page reads the line {want[0][1] if want else "as absent"}',
              rc == 0 and [(m, l) for m, l in data_lines(index) if l] == want, (rc, data_lines(index), out[-300:]))

    # a line hold is never waived by the owner suspension, even with the pick logged and the disclosure in place
    thin = pick(2, 'Thin ML', mclass='ml', model=61.0)
    thin['game'] = dict(thin['game'], away='C2', home='D2')
    bad = pick(1, 'Flyers -1.5', line=-1.5)
    log = json.dumps({'date': DATE, 'rule': '2026-10-02 (4)', 'scope': 'numeric', 'approved': 'owner, fixture approval',
                      'logged_at': '2099-10-04T14:00:00Z',
                      'picks': [{'name': p['name'], 'eid': p['game']['eid'], 'units': p['units']} for p in (bad, thin)]}) + '\n'
    cnote = 'Owner-directed picks: fixture; sub-bar disclosure.'
    rc, out, written, _ = build(B, card([thin], card_note=cnote), log=log)
    check(f'{tag}: control - the logged sub-bar pick alone is waived and builds', rc == 0 and 'OWNER SUSPENSION:' in out, (rc, out[-400:]))
    rc, out, written, _ = build(B, card([bad, thin], card_note=cnote), log=log)
    check(f'{tag}: a logged spread whose name disagrees with its line: held, nothing waived',
          held(rc, out, written) and 'name says -1.5' in out and 'OWNER SUSPENSION:' not in out, (rc, out[-400:], written))

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
