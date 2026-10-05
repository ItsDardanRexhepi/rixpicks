#!/usr/bin/env python3
"""Offline regression for the one accepted Polymarket entry (no real result/fill).
All finals are hypothetical fixtures. Production HTTP and ledger writes are absent.
"""
import contextlib
import copy
from decimal import Decimal
import functools
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ['RIX_UNIT_DOLLARS'] = '1'
from core import fill_leak
from core.accepted_entry import accepted_entry, entry_delta, _SCOPE


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fw, rf = load('finals_watch'), load('record_final')
pick = copy.deepcopy(_SCOPE)
entry = accepted_entry(pick)
assert entry is not None and entry['card_venue'] == 'polymarket'
assert entry['entry_c'] == 58 and entry['card_american'] == -138
assert entry['card_ts'] == '2026-10-05T09:30:11-07:00'
assert 'kalshi' not in pick
checks = 0


def check(label, got, expected):
    global checks
    assert got == expected, (label, got, expected)
    checks += 1
    print('OK', label)


def refuses(label, call, contains):
    try:
        call()
    except ValueError as exc:
        check(label, contains in str(exc), True)
    else:
        raise AssertionError(label + ': unexpectedly accepted')


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    ledger = root / 'picks.jsonl'
    ledger.write_text('')
    real_card_price = fill_leak.card_price
    fill_leak.card_price = functools.partial(real_card_price, picks_path=str(ledger))
    fill_leak.fill_divergence = lambda p: []
    check('approved entry resolves without external ledger copy', fill_leak.card_price(pick), (58, entry, 1))
    delta = Decimal(5) * Decimal(42) / Decimal(58)
    for a, h, want in ((3, 2, 'W'), (2, 3, 'W'), (1, 3, 'L'), (0, 0, 'W')):
        result, pnl = fw.grade(pick, {'away_score': a, 'home_score': h})
        check(f'Flyers hypothetical {a}-{h} result', result, want)
        check(f'Flyers hypothetical {a}-{h} exact 58c delta', pnl, delta if want == 'W' else Decimal(-5))
    check('58c is exact, distinct from rounded -138 settlement', delta != Decimal(500) / Decimal(138), True)
    for a in range(8):
        for h in range(8):
            assert fw.grade(pick, {'away_score': a, 'home_score': h})[0] != 'PUSH'
    check('half-goal spread never pushes across integer score grid', True, True)
    mutated = copy.deepcopy(entry)
    mutated['entry_c'] = 1
    check('returned accepted records cannot mutate authority', accepted_entry(pick)['entry_c'], 58)
    refuses('unknown entry cannot settle', lambda: entry_delta('W', Decimal(5), mutated), 'unrecognized')
    ledger.write_text(json.dumps(dict(entry, provenance={'private': 'fixture'})) + '\n')
    check('matching installed private ledger copy reconciles once', fill_leak.card_price(pick), (58, entry, 1))
    for key, value in (('entry_c', 59), ('card_american', -139), ('units', '10u'), ('card_venue', 'kalshi'),
                       ('accepted_entry_id', 'different'), ('card_ts', '2026-10-05T09:31:11-07:00')):
        bad = dict(entry, **{key: value})
        ledger.write_text(json.dumps(bad) + '\n')
        refuses('ledger conflict ' + key, lambda: fw.grade(pick, {'away_score': 2, 'home_score': 3}), 'accepted-entry conflict')
    ledger.write_text((json.dumps(entry) + '\n') * 2)
    refuses('duplicate ledger rows refuse', lambda: fill_leak.card_price(pick), 'duplicate')
    ledger.write_text('')
    for key, value in (('name', 'Flyers -1.5'), ('side', 'home'), ('line', 1.5), ('odds', '-139'),
                       ('card_american', -139), ('units', '10u'), ('card_source', 'unapproved'),
                       ('card_ts', '2026-10-05T09:31:11-07:00'), ('espn_league', 'other/league')):
        bad = dict(pick, **{key: value})
        check('changed scope has no approval: ' + key, accepted_entry(bad), None)
        refuses('changed scope still requires ledger: ' + key,
                lambda: fw.grade(bad, {'away_score': 2, 'home_score': 3}), 'missing or ambiguous')
    for key in ('eid', 'commence', 'away', 'home'):
        bad = copy.deepcopy(pick)
        bad['game'][key] = 'changed'
        check('changed event scope has no approval: ' + key, accepted_entry(bad), None)
    for key in ('kalshi', 'best_ask', 'polymarket', 'polymarket_us'):
        check('structured price is never silently overridden: ' + key, accepted_entry(dict(pick, **{key: {}})), None)
    other = copy.deepcopy(pick)
    other['game']['eid'] = 'other-event'
    other['kalshi'] = {'cents': 58}
    row = {'kind': 'pick', 'event_id': 'other-event', 'market_class': 'spread', 'side': 'away',
           'line': -1.5, 'entry_c': 58, 'card_american': -138}
    ledger.write_text(json.dumps(row) + '\n')
    check('unrelated Kalshi pick keeps original rounded-American math',
          fw.grade(other, {'away_score': 2, 'home_score': 3}), ('W', Decimal(500) / Decimal(138)))
    no_price = copy.deepcopy(other)
    del no_price['kalshi']
    refuses('unrelated missing manifest price still refuses', lambda: fw.grade(no_price, {'away_score': 2, 'home_score': 3}), 'manifest price missing')
    other['kalshi']['cents'] = 59
    refuses('unrelated price fork still refuses', lambda: fw.grade(other, {'away_score': 2, 'home_score': 3}), 'card-price fork')
    ledger.write_text('')
    refuses('unrelated missing ledger still refuses', lambda: fw.grade(other, {'away_score': 2, 'home_score': 3}), 'missing or ambiguous')

    # Real watcher queue -> real record verifier. Network is replaced only at its
    # source read; verification, arithmetic, archival binding and writes run in tmp.
    (root / 'scripts').mkdir()
    (root / 'manifests').mkdir()
    (root / 'slates').mkdir()
    fw.HERE = str(root / 'scripts')
    rf.ROOT = str(root)
    rf.REQ, rf.MAN, rf.HIST, rf.DONE = (str(root / f) for f in
        ('record_request.json', 'manifest.json', 'history.json', 'record_done.json'))
    rf.MANIFESTS = str(root / 'manifests')
    card = {'date': '2026-10-05', 'record': '33-15', 'units_pl': '+24.81u', 'picks': [pick]}
    primary = {'away_score': 2, 'home_score': 3, 'away_abbr': 'PHI', 'home_abbr': 'TB'}
    game_key = '401892445|spread|away|-1.5'
    state = {'completed': True}

    def get(url, *args, **kwargs):
        assert url == 'https://sports.core.api.espn.com/v2/sports/hockey/leagues/nhl/events/401892445/competitions/401892445', url
        return {'status': {'type': {'completed': state['completed']}}, 'competitors': [
            {'homeAway': 'away', 'team': {'displayName': 'Philadelphia Flyers'}, 'score': {'value': 2}},
            {'homeAway': 'home', 'team': {'displayName': 'Tampa Bay Lightning'}, 'score': {'value': 3}}]}
    rf._get = get

    def initialize():
        for f, obj in (('manifest.json', card), ('history.json', {'days': []}),
                       ('record_done.json', {'processed': [], 'record_after': '33-15', 'units_after_exact': '24.81'}),
                       ('record_request.json', {'requests': []})):
            (root / f).write_text(json.dumps(obj))
        json.dump(card, (root / 'manifests' / 'manifest-fixture.json').open('w'))
        fw._queue_record_request(pick, '401892445', game_key, 'W', primary, '34-15', Decimal('24.81') + delta,
                                 delta, {'source': 'independent offline fixture'}, 'fixture', card_date='2026-10-05')

    def run():
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            rc = rf.main()
        return rc, out.getvalue()

    initialize()
    queued = json.load(open(rf.REQ))
    check('queue preserves opaque approved-entry price basis', queued['requests'][0]['accepted_entry']['entry_c'], 58)
    before = {p: p.read_bytes() for p in root.glob('*.json')}
    state['completed'] = False
    rc, out = run()
    check('unfinished event refuses without settling', rc, 3)
    check('unfinished event writes nothing', {p: p.read_bytes() for p in root.glob('*.json')}, before)
    state['completed'] = True
    for key in ('delta_units_exact', 'accepted_entry'):
        initialize()
        q = json.load(open(rf.REQ))
        q['requests'][0][key] = float(Decimal(500) / Decimal(138)) if key == 'delta_units_exact' else {'entry_c': 58}
        (root / 'record_request.json').write_text(json.dumps(q))
        before = {p: p.read_bytes() for p in root.glob('*.json')}
        check('record verifier rejects wrong ' + key, run()[0], 3)
        check('refused record writes nothing: ' + key, {p: p.read_bytes() for p in root.glob('*.json')}, before)
    initialize()
    rc, out = run()
    check('hypothetical verified final reconciles queue successfully', (rc, 'REFUSE' in out), (0, False))
    check('same original grade identity preserved', json.load(open(rf.DONE))['processed'], [game_key])
    history = json.load(open(rf.HIST))
    hrow = history['days'][0]['picks'][0]
    check('history preserves accepted entry rather than claiming venue fill', hrow['accepted_entry']['entry_basis'], 'approved_card_entry_assumption')
    check('history exact delta equals queued cents delta', Decimal(hrow['_delta']), Decimal(str(float(delta))))
    check('queue retry does not double-grade', run()[0], 0)
    check('only one hypothetical history result exists', len(json.load(open(rf.HIST))['days'][0]['picks']), 1)

print(f'ALL {checks} CHECKS PASS (offline hypothetical fixtures only)')
