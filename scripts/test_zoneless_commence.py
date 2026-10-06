#!/usr/bin/env python3
"""A zoneless game.commence ('2099-10-04T20:25:00', no 'Z' or +hh:mm) is read as UTC by the page builder's _pt_date,
the builder's one convention for a naive commence (the ledger carryover check and _eid_resolve's time match read it
so too), never in the machine's own zone, and never as no date at all. Every caller depends on that date:
 - _eid_resolve checks a manifest eid against the ESPN scoreboard of that date; an eid the feed cannot verify (here
   the network is a dead proxy) is suppressed ('EID SUPPRESSED', data-eid="") - it is never shipped on faith;
 - the pick's live room (data-room="g<num>-<date>") and game page carry the date;
 - _card_date_of dates the card from its picks' commence dates, and only a gameless card falls back to today: a
   past hand-landed card is never dated today, so the date header shows its own date and a publish build of it
   never re-pins the shipped ledger's __card__ (the Sep 27 swamp-kill failure _card_date_of was written to stop).
The same card gives the same output under a UTC, a Pacific and a Tokyo machine zone. The owner-suspension date
binding is stricter on purpose (a zoneless commence binds to no date there): see test_owner_rule_suspension.py (l).
Builds run in a throwaway tree with the network sent to a dead proxy.
Run: python3 scripts/test_zoneless_commence.py [builder.py ...]   (default: both twins)"""
import copy, json, os, re, shutil, subprocess, sys, tempfile

from fixtures.card_contract import stamped, market, published_snapshot

SD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SD)
BUILDERS = [os.path.abspath(a) for a in sys.argv[1:]] or [os.path.join(SD, 'build_gh_page_v2.py'), os.path.join(SD, '_build_nocanon_v2.py')]
DEAD = 'http://127.0.0.1:9'
ZONES = ('UTC', 'America/Los_Angeles', 'Asia/Tokyo')
failures = 0

def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or detail == '' else '  [' + str(detail)[-400:] + ']'))
    if not ok:
        failures += 1

def build(builder, manifest, tz, seed=None, publish=False):
    """Build manifest.json in a throwaway tree under machine zone tz, with any `seed` files. Returns (rc, output,
    index.html text, shipped_books.json after the build or None)."""
    d = tempfile.mkdtemp(prefix='rp-zoneless-')
    try:
        os.makedirs(os.path.join(d, 'scripts')); os.makedirs(os.path.join(d, 'slates'))
        bsrc = os.path.dirname(builder)
        shutil.copy(builder, os.path.join(d, 'scripts', 'build_gh_page_v2.py'))
        for f in ('index_v2.js', 'index_v2.css', 'game_page_template.html', 'team_page_template.html', 'poly_us.py'):
            shutil.copy(os.path.join(bsrc if os.path.exists(os.path.join(bsrc, f)) else SD, f), os.path.join(d, 'scripts', f))
        for f in ('feed_arbiter.js', 'feed_registry.json', 'config_leagues.json'):
            shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
        for rel, text in (seed or {}).items():
            open(os.path.join(d, rel), 'w', encoding='utf-8').write(text)
        manifest=dict(manifest,picks=[market(p) for p in manifest.get('picks',[])])
        manifest=stamped(builder,manifest)
        json.dump(manifest, open(os.path.join(d, 'manifest.json'), 'w'), indent=1)
        published_snapshot(d,builder,manifest)
        json.dump([], open(os.path.join(d, 'slates', 'odds_prefill.json'), 'w'))
        env = dict(os.environ, RP_REFRESH='1', http_proxy=DEAD, https_proxy=DEAD, HTTP_PROXY=DEAD, HTTPS_PROXY=DEAD,
                   NO_PROXY='', no_proxy='', TZ=tz)
        env.pop('RP_PUBLISH', None)
        if publish:
            env['RP_PUBLISH'] = '1'
        r = subprocess.run([sys.executable, os.path.join(d, 'scripts', 'build_gh_page_v2.py'), 'manifest.json', 'index.html'],
                           cwd=d, env=env, capture_output=True, text=True, timeout=600)
        ix = os.path.join(d, 'index.html')
        index = open(ix, encoding='utf-8').read() if os.path.exists(ix) else ''
        sb = os.path.join(d, 'shipped_books.json')
        shipped = json.load(open(sb)) if os.path.exists(sb) else None
        return r.returncode, r.stdout + r.stderr, index, shipped
    finally:
        shutil.rmtree(d, ignore_errors=True)

BASE = {'date': '2099-10-04', 'date_label': 'Sunday, Oct 4', 'updated': 'Oct 4, 8:42 AM PT', 'record': '21-11',
        'units_pl': '+4.76u', 'units_ledger': None, 'yesterday': '', 'status_note': '', 'preview': False, 'parlay': None}
def pick(commence, eid='WRONG-EID-123'):
    return {'num': 1, 'name': 'Bills ML', 'market_class': 'ml', 'sub': 'fixture - model 66.0', 'odds': '-150', 'card_american': -150,
            'units': '5u', 'side': 'home',
            'game': {'away': 'New England Patriots', 'home': 'Buffalo Bills', 'commence': commence, 'eid': eid},
            'espn_league': 'football/nfl', 'league': 'NFL', 'best_book': 'Kalshi', 'card_source': 'Kalshi ask at lock'}
def card(picks, drop=(), **kw):
    m = copy.deepcopy(BASE); m['picks'] = copy.deepcopy(picks); m.update(kw)
    for k in drop:
        m.pop(k, None)
    return m
def row(index):
    """(data-eid, data-room) of the first pick row."""
    mo = re.search(r'<div class="pick" [^>]*?data-eid="([^"]*)"[^>]*?data-room="([^"]*)"', index)
    return mo.groups() if mo else None
def rpdate(index):
    mo = re.search(r'class="rpdate" data-date="([^"]*)"', index)
    return mo.group(1) if mo else None

for B in BUILDERS:
    tag = os.path.basename(B)
    for tz in ZONES:
        # (1) the eid check runs for a zoneless commence: an unverifiable eid is suppressed, the room carries the date
        for when, room in (('2099-10-04T20:25Z', 'g1-2099-10-04'), ('2099-10-04T20:25:00', 'g1-2099-10-04'),
                           ('2099-10-05T02:00:00', 'g1-2099-10-04')):
            rc, out, index, _ = build(B, card([pick(when)]), tz)
            check(f'{tag} [{tz}]: commence {when!r}: the unverifiable eid is suppressed, data-eid empty, room {room}',
                  rc == 0 and 'EID SUPPRESSED: Bills ML manifest eid WRONG-EID-123' in out and row(index) == ('', room),
                  (rc, row(index), out[-300:]))

        # (2) a past hand-landed card with a zoneless commence is dated by its game, never today
        past = card([pick('2026-09-20T20:25:00')], drop=('date',), date_label='Sunday, Sep 20', posted_at='2026-09-20T15:00:00Z')
        rc, out, index, _ = build(B, past, tz)
        check(f'{tag} [{tz}]: a past card with a zoneless commence and no manifest date: the date header reads its game date',
              rc == 0 and rpdate(index) == '2026-09-20', (rc, rpdate(index), out[-300:]))
        pin = {'__card__': {'date': '2026-10-01', 'locked': 'Oct 1, 9:00 AM PT', 'picks_sha': 'fixture-current-card'}}
        rc, out, index, shipped = build(B, past, tz, seed={'shipped_books.json': json.dumps(pin)}, publish=True)
        check(f'{tag} [{tz}]: a publish build of that past card leaves the shipped ledger\'s __card__ pin as it was',
              rc == 0 and (shipped or pin).get('__card__') == pin['__card__'], (rc, (shipped or {}).get('__card__'), out[-300:]))

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
