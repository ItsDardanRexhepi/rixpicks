#!/usr/bin/env python3
"""finals_watch runs on the grading Mac: no fixed checkout paths, dry run by default, NCAAB keyed by its
ESPN path, and offline replays of real finals.

finals_watch.py was pinned to a sandbox checkout that no longer exists (its core/ import, ledger, seen
state and token paths), so it could not run anywhere. Checked here:
  1. no sandbox path is left; RPS_KB / RIX_REPO come from the environment or the RIX_FINALS_CONFIG
     file (the environment wins); with no RPS_KB the run refuses before grading;
  2. secrets come from the environment or the macOS keychain (security find-generic-password), and a
     dry run never asks for the record token;
  3. a run is dry unless --live; a dry run writes no production state; --requests-out writes the
     record requests a live run would queue to a preview file only; --live refuses (nothing written)
     while core/record_pipe lacks the relay parameters the live chain calls;
  4. NCAAB is keyed 'basketball/mens-college-basketball' (the registry's ESPN path), so its CBS and
     the-odds-api second sources fire; 'basketball/ncaab' is gone;
  5. offline replays on recorded data (tests/fixtures/finals_replay, trimmed to the fields read,
     values untouched):
     - Oct 1 PIT@CLE (401872964): ESPN core 24-27 verified by CBS's week-4 scoreboard; Under 38.5 LOST;
     - MLB: ESPN core verified by statsapi for the Oct 3 Padres-Brewers night game (filed under its
       Eastern date, not the UTC date that holds the next day's rematch) and the Oct 4 day game;
     - Oct 5: main() over the published card, with CBS's Oct 5 NHL scoreboard as the second source,
       emits record requests whose grade fields equal the hand grade committed in 15d1b31af.
Run: python3 scripts/test_finals_watch_mac.py"""
import contextlib, copy, importlib.util, io, json, os, shutil, subprocess, sys, tempfile, types
from datetime import datetime as _real_dt, timezone
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIX = os.path.join(ROOT, 'tests', 'fixtures', 'finals_replay')
sys.path.insert(0, ROOT)
for k in ('RPS_KB', 'RIX_REPO', 'RIX_FINALS_CONFIG', 'RIX_RECORD_TOKEN', 'THE_ODDS_API_KEY', 'ODDS_CREDITS_LEDGER'):
    os.environ.pop(k, None)
os.environ.setdefault('RIX_UNIT_DOLLARS', '1')  # placeholder: unit results do not depend on the size
from core import budget, record_pipe
BUDGET_LEDGER0 = budget.LEDGER

failures = 0
def check(name, actual, expected):
    global failures
    ok = actual == expected
    print(('OK  ' if ok else 'FAIL'), name, '' if ok else f'(got {actual!r}, want {expected!r})')
    if not ok:
        failures += 1

_n = [0]
def load_fw(env=None):
    """A fresh finals_watch module, imported with exactly these settings in the environment."""
    saved = {k: os.environ.pop(k, None) for k in ('RPS_KB', 'RIX_REPO', 'RIX_FINALS_CONFIG')}
    os.environ.update(env or {})
    try:
        _n[0] += 1
        spec = importlib.util.spec_from_file_location(f'finals_watch_mac_{_n[0]}', os.path.join(HERE, 'finals_watch.py'))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        for k in ('RPS_KB', 'RIX_REPO', 'RIX_FINALS_CONFIG'):
            os.environ.pop(k, None)
            if saved[k] is not None:
                os.environ[k] = saved[k]
        budget.LEDGER = BUDGET_LEDGER0  # the module points the shared credit ledger under RPS_KB; undo for the next case

def run_main(fw, argv):
    """(exit code or None, stdout, stderr) of fw.main() with these arguments."""
    out, err = io.StringIO(), io.StringIO()
    saved, sys.argv = sys.argv, ['finals_watch.py'] + list(argv)
    code = None
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            fw.main()
    except SystemExit as e:
        code = e.code
    finally:
        sys.argv = saved
    return code, out.getvalue(), err.getvalue()

def fx(name):
    return json.load(open(os.path.join(FIX, name)))

CORE = fx('espn_core.json')
CBS = {'https://www.cbssports.com/nfl/scoreboard/all/2026/regular/4/': 'cbs_nfl_2026_regular_4.html',
       'https://www.cbssports.com/nhl/scoreboard/20261005/': 'cbs_nhl_20261005.html'}
STATSAPI = {f'https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={d}&hydrate=linescore': f'statsapi_{d}.json'
            for d in ('2026-10-03', '2026-10-04')}
asked = []
def fake_get(url, *a, **k):
    asked.append(url)
    if url in CORE:
        return copy.deepcopy(CORE[url])
    if url in STATSAPI:
        return fx(STATSAPI[url])
    raise OSError(f'offline fixture missing {url}')
def fake_get_text(url, *a, **k):
    asked.append(url)
    if url in CBS:
        return open(os.path.join(FIX, CBS[url]), encoding='utf-8').read()
    raise OSError(f'offline fixture missing {url}')
def offline(fw):
    fw._get, fw._get_text = fake_get, fake_get_text
    return fw

tmp = tempfile.mkdtemp(prefix='fw_mac_')
try:
    # ---------- 1. paths ----------
    src = open(os.path.join(HERE, 'finals_watch.py')).read()
    check('no sandbox path is left in finals_watch.py', [p for p in ('/home/sandbox', '/tmp/.push_token', '.odds_api_key') if p in src], [])
    kb, kb2, repo = (os.path.join(tmp, d) for d in ('kb', 'kb2', 'repo'))
    for d in (os.path.join(kb, 'ledger'), os.path.join(kb2, 'ledger'), os.path.join(repo, 'scripts')):
        os.makedirs(d)
    fw = load_fw({'RPS_KB': kb, 'RIX_REPO': repo})
    check('RPS_KB from the environment: record ledger, seen state, picks/positions ledgers under it',
          (fw.LEDGER, fw.STATE, fw.PICKS_LEDGER, fw.POSITIONS_LEDGER),
          tuple(os.path.join(kb, 'ledger', f) for f in ('record_rows.jsonl', 'finals_seen.json', 'picks.jsonl', 'positions.jsonl')))
    check('RIX_REPO from the environment: manifest and the request queue come from that checkout',
          (fw.MANIFEST, os.path.normpath(os.path.join(fw.HERE, '..', 'record_request.json'))),
          (os.path.join(repo, 'manifest.json'), os.path.join(repo, 'record_request.json')))
    cfg = os.path.join(tmp, 'finals.json')
    json.dump({'RPS_KB': kb2}, open(cfg, 'w'))
    fwc = load_fw({'RIX_FINALS_CONFIG': cfg})
    check('RPS_KB from the RIX_FINALS_CONFIG file', fwc.LEDGER, os.path.join(kb2, 'ledger', 'record_rows.jsonl'))
    check('RIX_REPO unset: the checkout this script is in', fwc.MANIFEST, os.path.join(ROOT, 'manifest.json'))
    fwe = load_fw({'RIX_FINALS_CONFIG': cfg, 'RPS_KB': kb})
    check('the environment wins over the config file', fwe.LEDGER, os.path.join(kb, 'ledger', 'record_rows.jsonl'))
    json.dump(['not', 'an', 'object'], open(cfg, 'w'))
    try:
        load_fw({'RIX_FINALS_CONFIG': cfg}); bad = None
    except SystemExit as e:
        bad = str(e)
    check('a config file that is not a JSON object refuses at import', bool(bad and 'FAIL-CLOSED' in bad), True)
    fw0 = load_fw()
    check('no RPS_KB anywhere: no ledger paths', (fw0.LEDGER, fw0.STATE, fw0.PICKS_LEDGER), (None, None, None))
    code, out, err = run_main(fw0, [])
    check('no RPS_KB: main() refuses before grading (exit 5) and names RPS_KB', (code, 'RPS_KB' in err), (5, True))

    # ---------- 2. secrets ----------
    calls = []
    def fake_run(args, **kw):
        calls.append(args)
        return types.SimpleNamespace(returncode=0 if args[3] == 'RIX_RECORD_TOKEN' else 44, stdout='fixture-value\n')
    fw.subprocess = types.SimpleNamespace(run=fake_run, SubprocessError=subprocess.SubprocessError)
    check('a secret comes from the macOS keychain item named for it', fw._secret('RIX_RECORD_TOKEN'), 'fixture-value')
    check('... asked as security find-generic-password -s <name> -w', calls[-1], ['security', 'find-generic-password', '-s', 'RIX_RECORD_TOKEN', '-w'])
    check('no keychain item: empty, never an error', fw._secret('THE_ODDS_API_KEY'), '')
    os.environ['RIX_RECORD_TOKEN'] = 'from-env'
    n0 = len(calls)
    check('the environment variable wins and the keychain is not asked', (fw._secret('RIX_RECORD_TOKEN'), len(calls)), ('from-env', n0))
    os.environ.pop('RIX_RECORD_TOKEN')
    def no_security(args, **kw):
        raise FileNotFoundError('security')
    fw.subprocess = types.SimpleNamespace(run=no_security, SubprocessError=subprocess.SubprocessError)
    check('no security tool (not a Mac): empty', fw._secret('RIX_RECORD_TOKEN'), '')

    # ---------- 4. NCAAB keyed by its ESPN path ----------
    check('CBS slug keyed basketball/mens-college-basketball', fw.CBS_SLUG.get('basketball/mens-college-basketball'), 'college-basketball')
    check('the-odds-api sport keyed basketball/mens-college-basketball', fw.ODDS_API_SPORT.get('basketball/mens-college-basketball'), 'basketball_ncaab')
    check("'basketball/ncaab' is no key anywhere", ('basketball/ncaab' in fw.CBS_SLUG, 'basketball/ncaab' in fw.ODDS_API_SPORT,
                                                   hasattr(fw, 'SITE_LEAGUE'), 'basketball/ncaab' in src), (False, False, False, False))
    ncaab = {'espn_league': 'basketball/mens-college-basketball', 'game': {'eid': '401999999'}}
    prim = {'home': 'Duke Blue Devils', 'away': 'Kansas Jayhawks', 'home_score': 80, 'away_score': 70}
    tip = _real_dt(2026, 11, 15, 0, 30, tzinfo=timezone.utc)  # 7:30 PM ET, Nov 14
    asked.clear(); offline(fw)
    fw.cbs_final(ncaab, prim, tip)
    check('NCAAB: the CBS college-basketball page of the game\'s Eastern date is read', asked, ['https://www.cbssports.com/college-basketball/scoreboard/20261114/'])
    fw._secret = lambda name: 'fixture-key' if name == 'THE_ODDS_API_KEY' else ''
    budget_calls = []
    real_check = budget.check_and_log
    budget.check_and_log = lambda *a: budget_calls.append(a)
    try:
        asked.clear(); fw._odds_cache.clear()
        fw.odds_api_final(ncaab, prim, tip)
        check('NCAAB: the-odds-api basketball_ncaab scores are pulled (budget-logged first)',
              (len(asked), '/sports/basketball_ncaab/scores/' in (asked or [''])[0], budget_calls), (1, True, [('basketball_ncaab', 'scores', 1)]))
        fw._secret = lambda name: ''
        asked.clear(); fw._odds_cache.clear(); budget_calls.clear()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = fw.odds_api_final(ncaab, prim, tip)
        check('no odds key: no pull and no credit logged', (r, asked, budget_calls, 'THE_ODDS_API_KEY' in out.getvalue()), (None, [], [], True))
    finally:
        budget.check_and_log = real_check
    asked.clear()
    fw.espn_site_final(ncaab, prim, tip)
    check('NCAAB: ESPN site scoreboard read under its own path', asked[0].startswith(
        'https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates='), True)

    # ---------- 5a. Oct 1 PIT@CLE Under 38.5, CBS as the second source ----------
    fwr = offline(load_fw())
    import importlib
    rf_spec = importlib.util.spec_from_file_location('record_final_mac', os.path.join(HERE, 'record_final.py'))
    rf = importlib.util.module_from_spec(rf_spec); rf_spec.loader.exec_module(rf)
    card1 = fx('manifest_2026-10-01.json')
    under = next(p for p in card1['picks'] if p['name'] == 'Under 38.5')
    asked.clear()
    primary = fwr.espn_final(under['espn_league'], under['game']['eid'])
    check('Oct 1: ESPN core final PIT 24 @ CLE 27', (primary['away_abbr'], primary['away_score'], primary['home_abbr'], primary['home_score']),
          ('PIT', 24, 'CLE', 27))
    asked.clear()
    sec = fwr.second_source(under, primary, fwr._parse_ts(under['game']['commence']))
    check('Oct 1: the second source is CBS (independent company), read from the week-4 page',
          ((sec or {}).get('source', '').startswith('cbs scoreboard'), [u for u in asked if 'cbssports' in u]),
          (True, ['https://www.cbssports.com/nfl/scoreboard/all/2026/regular/4/']))
    check('Oct 1: CBS agrees on the ordered score (two-source check passes)', fwr.two_source_ok(primary, sec), True)
    check('Oct 1 PIT@CLE Under 38.5 grades LOST (finals_watch)', fwr.result_of(under, primary), 'L')
    check('Oct 1 PIT@CLE Under 38.5 grades LOST (record_final on the same final)',
          rf.score_result('total', 'under', 38.5, 24, 27, league='football/nfl'), 'LOST')
    swapped = dict(primary, home_score=24, away_score=27)
    check('CBS does not attest a reversed score', fwr.two_source_ok(swapped, fwr.second_source(under, swapped, fwr._parse_ts(under['game']['commence']))), False)

    # ---------- 5b. MLB finals verified against statsapi ----------
    for label, eid, commence, want in (
            ('Oct 3 SD@MIL night game (00:30Z, Oct 3 Eastern)', '401908002', '2026-10-04T00:30Z', (2, 3)),
            ('Oct 4 SD@MIL day game', '401908003', '2026-10-04T20:00Z', (3, 4))):
        pick = {'espn_league': 'baseball/mlb', 'game': {'eid': eid, 'commence': commence}}
        primary = fwr.espn_final('baseball/mlb', eid)
        asked.clear()
        sec = fwr.mlb_statsapi_final(pick, primary, fwr._parse_ts(commence))
        check(f'{label}: statsapi Final {want[0]}-{want[1]} verifies ESPN core', (
            (sec or {}).get('source'), (sec or {}).get('away_score'), (sec or {}).get('home_score'), fwr.two_source_ok(primary, sec)),
            ('mlb-statsapi (official)', want[0], want[1], True))
        check(f'{label}: statsapi asked only for the game\'s own date', [u.split('date=')[1][:10] for u in asked],
              [fwr._parse_ts(commence).astimezone(fwr.ET).date().isoformat()])
    # the UTC date holds the next day's rematch (3-4): a start 19.5 hours away never stands in
    STATSAPI_SWAP = dict(STATSAPI)
    STATSAPI['https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=2026-10-03&hydrate=linescore'] = 'statsapi_2026-10-04.json'
    try:
        primary = fwr.espn_final('baseball/mlb', '401908002')
        check('a same-teams game hours away from the card start is no attestation',
              fwr.mlb_statsapi_final({'espn_league': 'baseball/mlb', 'game': {'eid': '401908002'}}, primary, fwr._parse_ts('2026-10-04T00:30Z')), None)
    finally:
        STATSAPI.clear(); STATSAPI.update(STATSAPI_SWAP)

    # ---------- 3 + 5c. Oct 5: dry run by default; emitted grade fields equal 15d1b31af ----------
    card5 = fx('manifest_2026-10-05.json')
    json.dump(card5, open(os.path.join(repo, 'manifest.json'), 'w'), indent=2)
    led = os.path.join(kb, 'ledger', 'record_rows.jsonl')
    rows = [record_pipe.build_record_row('G-BASELINE-0926', '2026-09-26', '13-6', '68.42%', Decimal('3.8937'), record_pipe.BASIS),
            # the running record before Oct 5's finals: record_done.json at 15d1b31af's parent
            record_pipe.build_record_row('fixture-anchor-oct4', '2026-10-04', '33-15', '68.75%', Decimal('24.80670486265687'), record_pipe.BASIS)]
    with open(led, 'w') as f:
        f.writelines(json.dumps(r) + '\n' for r in rows)
    json.dump({'fixture-anchor-oct4': {'appended': True, 'verified': True}}, open(led + '.state.json', 'w'))
    # the picks-ledger card entry of the Penguins pick, from the published card (Kalshi 63c, -163);
    # the Flyers entry is the one accepted entry in core/accepted_entry.py
    pen = next(p for p in card5['picks'] if p['name'] == 'Penguins ML')
    json.dump({'kind': 'pick', 'event_id': pen['game']['eid'], 'market_class': 'ml', 'side': 'home',
               'entry_c': pen['kalshi']['cents'], 'card_american': pen['card_american'], 'units': pen['units']},
              open(os.path.join(kb, 'ledger', 'picks.jsonl'), 'w'))
    open(os.path.join(kb, 'ledger', 'picks.jsonl'), 'a').write('\n')
    before = {p: open(p, 'rb').read() for p in (led, led + '.state.json', os.path.join(kb, 'ledger', 'picks.jsonl'))}

    class FixedNow(_real_dt):  # 3:00 AM PT Oct 6: the Oct 5 card is yesterday's, inside the stale-manifest guard
        @classmethod
        def now(cls, tz=None):
            t = _real_dt(2026, 10, 6, 10, 0, tzinfo=timezone.utc)
            return t.astimezone(tz) if tz else t.astimezone().replace(tzinfo=None)

    def oct5_fw():
        m = offline(load_fw({'RPS_KB': kb, 'RIX_REPO': repo}))
        m.datetime = FixedNow
        m.secrets_asked = []
        m._secret = lambda name: m.secrets_asked.append(name) or ''
        return m

    def production_untouched():
        return (not os.path.exists(os.path.join(repo, 'record_request.json')),
                not os.path.exists(os.path.join(kb, 'ledger', 'finals_seen.json')),
                all(open(p, 'rb').read() == b for p, b in before.items()))

    fw5 = oct5_fw()
    code, out, err = run_main(fw5, [])
    check('no flag: a dry run that grades both Oct 5 finals', (code, out.count('FINAL-CHAIN(dry)'), 'DRY RUN' in out), (None, 2, True))
    check('the dry run wrote no production state (queue, seen state, ledgers)', production_untouched(), (True, True, True))
    check('the dry run never asked for the record token', 'RIX_RECORD_TOKEN' in fw5.secrets_asked, False)

    preview = os.path.join(tmp, 'would_queue.json')
    fw5 = oct5_fw()
    code, out, err = run_main(fw5, ['--requests-out', preview])
    emitted = json.load(open(preview))['requests']
    hand = fx('record_request_15d1b31af.json')['requests']
    GRADE_FIELDS = ('grade_id', 'event_id', 'league', 'pick', 'side', 'market_class', 'line', 'card_date', 'result', 'score',
                    'stake_units', 'locked_american', 'delta_units_exact', 'graded_pick', 'accepted_entry')
    grade = lambda q: {k: q.get(k) for k in GRADE_FIELDS}  # an absent line and a null line are the same: none
    check('Oct 5: two requests emitted, nothing else written', (code, len(emitted), production_untouched()), (None, 2, (True, True, True)))
    check('Oct 5: every grade field equals the hand grade in 15d1b31af',
          sorted((grade(q) for q in emitted), key=lambda g: g['grade_id']), sorted((grade(q) for q in hand), key=lambda g: g['grade_id']))
    check('Oct 5: the chain ends where 15d1b31af ends (33-17, +14.80670486265687u)',
          (emitted[-1]['record_after'], emitted[-1]['units_after_exact']), (hand[-1]['record_after'], hand[-1]['units_after_exact']))
    # finals_watch grades in commence order (Flyers 7:00 PM ET, Penguins 7:30 PM ET); the hand grade went in
    # card order, so the running record after each row swaps between the two rows - the same chain either way
    check('Oct 5: running record follows commence order, Flyers then Penguins',
          [(q['grade_id'], q['record_after'], q['units_after_exact']) for q in emitted],
          [('401892445|spread|away|-1.5', '33-16', 19.80670486265687), ('401892447|ml|home', '33-17', 14.80670486265687)])
    check('Oct 5: each final attested by CBS (independent), not ESPN\'s own site API',
          [q['two_source'][1].startswith('cbs scoreboard') for q in emitted], [True, True])

    code, out, err = run_main(oct5_fw(), ['--live'])
    check('--live on this checkout: refused before anything is read or written (exit 7), says why',
          (code, 'record_pipe.resume_pending() takes no skip=' in err, production_untouched()), (7, True, (True, True, True)))
    for args, why in ((['--live', '--dry-run'], 'both modes'), (['--live', '--requests-out', preview], '--requests-out with --live'),
                      (['--requests-out', os.path.join(repo, 'record_request.json')], "--requests-out at the checkout's queue"),
                      (['--requests-out', os.path.join(repo, 'preview.json')], '--requests-out inside the checkout'),
                      (['--requests-out', led], '--requests-out over the record ledger'),
                      (['--requests-out', os.path.join(kb, 'ledger', 'finals_seen.json')], '--requests-out over the seen state'),
                      (['--requests-out', tmp], '--requests-out at a directory'),
                      (['--requests-out'], '--requests-out with no path')):
        code, out, err = run_main(oct5_fw(), args)
        check(f'refused: {why} (exit 2, nothing written)', (code, production_untouched(), os.path.exists(os.path.join(repo, 'preview.json'))),
              (2, (True, True, True), False))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
