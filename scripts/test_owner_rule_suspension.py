#!/usr/bin/env python3
"""Owner suspension of standing ruling 2026-10-02 (4), numeric bars only (owner, typed in the operator chat
2026-10-03 about 7:20 AM PT, option B: suspend rule (4) for that day so the named owner-directed picks with a
sub-bar disclosure can post; card corrected by the owner to six picks about 7:44 AM PT).
The page builder's standing-rules card hold stays a hard gate (exit 3, nothing written). The one exception is
narrow and logged: slates/owner_rule_suspensions.jsonl (append-only; every pick an object {name, eid, units})
waives a held item only when a line has date == the manifest's date (exact string), rule == "2026-10-02 (4)",
scope == "numeric", the item is a numeric bar (gross below the 2c bar, net below the
class bar, units over the J-096 rung of its fair) and its pick name is exactly a logged name. The whole waiver is
refused unless the card_note (the note the page renders) carries the disclosure stated positively ("owner-directed"
or "owner directive", and "sub-bar"; "not owner-directed", "no owner directive", "not sub-bar" disclose nothing), no
logged name is on more than one card pick, and every waived pick plays on the logged date (game.commence, with an
explicit UTC offset, read in America/Los_Angeles - never in the machine's own zone) with exactly its logged eid and
units. A Las Vegas team, units off the ladder, a card ask at or above the 85c cut, a card price that is not the best
recorded ask and every parlay item are never waived. One unwaived item holds the whole card exactly as before; an
unreadable or malformed log waives nothing.
 - (a) a sub-bar card with no log is held; (b) the matching log plus the disclosure builds it, with the loud
   OWNER SUSPENSION line, an EXECUTE decision and the card_note on the page; (c) a log for another date, (d) a
   pick not in the list, (e) a listed Vegas pick, (f) a listed ladder violation, (g) a missing or negated card_note
   disclosure and (h) a malformed log line (an impossible date or a zoneless logged_at included) each keep the
   hold; so do a wrong rule or scope, a near-miss pick name, a listed 85c-cut pick, a listed best-ask miss and a
   sub-bar parlay.
 - (i) the real Oct 3 owner card (scripts/fixtures/owner_card_2026-10-03: picks.json, status_note.txt and
   card_note.txt, copied byte-for-byte from the final six-pick card), dated 2026-10-03 with record 27-13 /
   +14.01u, is held with no log and builds with the repo's own slates/owner_rule_suspensions.jsonl, its
   card_note rendered on the page; re-dated to another day, or under a log whose entry differs, it is held.
 - (j) a card with no holds builds to identical output with and without the log present.
 - (k) a logged name on two card picks, or logged twice with different entries: held (nothing waived).
 - (l) a waived pick whose game is not on the logged date in Pacific time (the 2099 stale-date case): held; a
   commence with no UTC offset binds to no date, the same under a UTC and a Pacific machine clock: held.
 - (m) a waived pick whose eid or units differ from its logged entry: held.
Builds run in a throwaway tree with the network sent to a dead proxy.
Run: python3 scripts/test_owner_rule_suspension.py [builder.py ...]   (default: both twins)"""
import ast, copy, hashlib, html, json, os, re, shutil, subprocess, sys, tempfile, warnings

from fixtures.card_contract import stamped as contract_stamped, market, published_snapshot

SD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SD)
BUILDERS = [os.path.abspath(a) for a in sys.argv[1:]] or [os.path.join(SD, 'build_gh_page_v2.py'), os.path.join(SD, '_build_nocanon_v2.py')]
REAL_CARD = os.path.join(SD, 'fixtures', 'owner_card_2026-10-03')
REAL_LOG = os.path.join(ROOT, 'slates', 'owner_rule_suspensions.jsonl')
LOG_REL = os.path.join('slates', 'owner_rule_suspensions.jsonl')
DEAD = 'http://127.0.0.1:9'
failures = 0

def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or detail == '' else '  [' + str(detail)[-500:] + ']'))
    if not ok:
        failures += 1

def build(builder, manifest, log=None, seed=None, tz=None):
    """Build manifest.json in a throwaway tree, with slates/owner_rule_suspensions.jsonl holding `log` (absent
    when None) and any `seed` files. Returns (rc, output with the tree path as <tree>, files written by the
    build, {written file: bytes})."""
    d = tempfile.mkdtemp(prefix='rp-suspend-')
    try:
        os.makedirs(os.path.join(d, 'scripts')); os.makedirs(os.path.join(d, 'slates'))
        for rel, text in (seed or {}).items():
            open(os.path.join(d, rel), 'w', encoding='utf-8').write(text)
        bsrc = os.path.dirname(builder)
        shutil.copy(builder, os.path.join(d, 'scripts', 'build_gh_page_v2.py'))
        for f in ('index_v2.js', 'index_v2.css', 'game_page_template.html', 'team_page_template.html', 'poly_us.py'):
            shutil.copy(os.path.join(bsrc if os.path.exists(os.path.join(bsrc, f)) else SD, f), os.path.join(d, 'scripts', f))
        for f in ('feed_arbiter.js', 'feed_registry.json', 'config_leagues.json'):
            shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
        manifest=contract_stamped(builder,manifest)
        json.dump(manifest, open(os.path.join(d, 'manifest.json'), 'w'), indent=1)
        published_snapshot(d,builder,manifest)
        json.dump([], open(os.path.join(d, 'slates', 'odds_prefill.json'), 'w'))
        if log is not None:
            open(os.path.join(d, LOG_REL), 'w', encoding='utf-8').write(log)
        before = {os.path.relpath(os.path.join(p, f), d): os.path.getmtime(os.path.join(p, f)) for p, _, fs in os.walk(d) for f in fs}
        env = dict(os.environ, RP_REFRESH='1', http_proxy=DEAD, https_proxy=DEAD, HTTP_PROXY=DEAD, HTTPS_PROXY=DEAD, NO_PROXY='', no_proxy='')
        if tz:
            env['TZ'] = tz  # the machine's own zone, which a zoneless timestamp must never be read in
        r = subprocess.run([sys.executable, os.path.join(d, 'scripts', 'build_gh_page_v2.py'), 'manifest.json', 'index.html'],
                           cwd=d, env=env, capture_output=True, text=True, timeout=600)
        after = {os.path.relpath(os.path.join(p, f), d): os.path.getmtime(os.path.join(p, f)) for p, _, fs in os.walk(d) for f in fs}
        written = sorted(f for f, t in after.items() if before.get(f) != t and '__pycache__' not in f)
        body = {f: open(os.path.join(d, f), 'rb').read() for f in written}
        out = (r.stdout + r.stderr).replace(os.path.realpath(d), '<tree>').replace(d, '<tree>')
        return r.returncode, out, written, body
    finally:
        shutil.rmtree(d, ignore_errors=True)

DATE = '2099-10-04'
NOTE = 'Official picks by owner directive - sub-bar disclosure on file (fixture)'
CNOTE = "Owner-directed picks: none of today's fixture picks cleared every bar; sub-bar disclosure."
BASE = {'date': DATE, 'date_label': 'Sunday, Oct 4', 'updated': 'Oct 4, 8:42 AM PT', 'record': '21-11',
        'units_pl': '+4.76u', 'units_ledger': None, 'yesterday': '', 'status_note': NOTE, 'card_note': CNOTE, 'preview': False, 'parlay': None}
LEAGUE = {'football/nfl': 'NFL', 'hockey/nhl': 'NHL', 'baseball/mlb': 'MLB'}
REG = {}  # pick name -> its log entry {name, eid, units}, from the latest pick() of that name
def ent(p):
    u = p.get('units')
    return {'name': p['name'], 'eid': (p.get('game') or {}).get('eid') or 'FIX-0', 'units': u if isinstance(u, str) and u.strip() else '5u'}
def pick(num, name, league='hockey/nhl', away='A', home='B', units='5u', model=66.0, american=-150, mclass='ml', **extra):
    p = {'num': num, 'name': name, 'market_class': mclass, 'sub': f'fixture - model {model:.1f}', 'odds': f'{american:+d}',
         'card_american': american, 'units': units, 'side': 'home',
         'game': {'away': away, 'home': home, 'commence': '2099-10-04T20:25Z', 'eid': f'FIX-{num}'},
         'espn_league': league, 'league': LEAGUE[league], 'best_book': 'Kalshi', 'card_source': 'Kalshi ask at lock'}
    p=market(p)
    p.update(extra)
    REG[name] = ent(p)
    return p
def card(picks, **kw):
    m = copy.deepcopy(BASE); m['picks'] = copy.deepcopy(picks); m.update(kw); return m
def line(date=DATE, rule='2026-10-02 (4)', scope='numeric', picks=(), approved='owner, fixture approval', logged_at='2099-10-04T14:00:00Z', **extra):
    """One log line. A str in `picks` becomes the entry of the fixture pick of that name (an unknown name gets
    eid FIX-0, units 5u); a dict is written as given."""
    r = {'date': date, 'rule': rule, 'scope': scope,
         'picks': [x if not isinstance(x, str) else REG.get(x, {'name': x, 'eid': 'FIX-0', 'units': '5u'}) for x in picks],
         'approved': approved, 'logged_at': logged_at}
    r.update(extra)
    return json.dumps(r, separators=(',', ':'))
def log_of(*lines):
    return ''.join(l + '\n' for l in lines)
def pick_hash(builder, manifest):
    """The builder's own pick-content hash of `manifest` (its _pick_content_hash, lifted out by AST)."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', SyntaxWarning)  # the builder's own long-standing escape warnings
        tree = ast.parse(open(builder, encoding='utf-8').read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == '_pick_content_hash':
            ns = {'json': json, '_hl': hashlib}
            exec(compile(ast.Module(body=[node], type_ignores=[]), builder, 'exec'), ns)
            return ns['_pick_content_hash'](json.loads(json.dumps(manifest)))
    raise SystemExit(f'{builder}: no _pick_content_hash')
def stamped(r):
    """A build result with its time stamp (build_sha, epoch seconds) replaced, so two builds compare by content."""
    m = re.search(r'\| build (\d+) complete:', r[1])
    st = m.group(1).encode() if m else None
    return (r[0], r[1].replace(m.group(1), '<stamp>') if m else r[1], r[2],
            {f: (b.replace(st, b'<stamp>') if st else b) for f, b in r[3].items()})

# a sub-bar card: every hold on it is a numeric bar (gross, net, units over the rung, fair below the band)
CLEAN = pick(1, 'Clean ML', away='C1', home='D1')                                                    # no hold
THIN = pick(2, 'Thin ML', away='C2', home='D2', model=61.0)                                          # gross 1c, net -0.68c
TOTAL = pick(3, 'Total Over 4.5', away='C3', home='D3', model=82.0, american=-400, mclass='total', line=4.5, side='over')  # net 0.88c
OFFRUNG = pick(4, 'OffRung ML', away='C4', home='D4', units='10u')                                   # 10u on a 5u rung
SUBFAIR = pick(5, 'SubFair ML', away='C5', home='D5', model=55.0)                                   # fair below the 60c band
SUB = [CLEAN, THIN, TOTAL, OFFRUNG, SUBFAIR]
SUB_NAMES = [p['name'] for p in SUB[1:]]
SUB_HELD = 6  # Thin: gross + net; Total: net; OffRung: over the rung; SubFair: fair band + gross + net
NUMERIC_TOKENS = ('gross 1c below the 2c bar', 'net 0.88c below the 2c bar', "over the J-096 rung 5u")

def held(rc, out, written):
    return rc == 3 and 'BUILD FAILED' in out and 'owner ruling 2026-10-02 (4)' in out and written == [] and 'OWNER SUSPENSION:' not in out

for B in BUILDERS:
    tag = os.path.basename(B)

    # (a) the sub-bar card with no log: held, every numeric item named, no suspension line
    rc, out, written, _ = build(B, card(SUB))
    check(f'{tag}: (a) a sub-bar card with no suspension log is held (exit 3, nothing written)',
          held(rc, out, written) and all(t in out for t in NUMERIC_TOKENS) and 'owner suspension' not in out.lower(), (rc, out[-600:], written))
    rc, out, written, _ = build(B, card(SUB), log='')
    check(f'{tag}: (a) an empty suspension log waives nothing', held(rc, out, written), (rc, out[-400:], written))

    # (b) the matching log line plus the disclosure: the card builds, loudly
    rc, out, written, body = build(B, card(SUB), log=log_of(line(picks=SUB_NAMES)))
    sus = [l for l in out.splitlines() if l.startswith('OWNER SUSPENSION:')]
    check(f'{tag}: (b) matching log + disclosure: the card builds (index.html written)', rc == 0 and 'index.html' in written, (rc, out[-600:]))
    check(f'{tag}: (b) the card_note disclosure renders on the built page',
          html.escape(CNOTE).encode() in body.get('index.html', b'') and b'<div class="cardnote">' + html.escape(CNOTE).encode() in body.get('index.html', b''))
    check(f'{tag}: (b) one loud OWNER SUSPENSION line naming the rule, the date, the approval and every waived item',
          len(sus) == 1 and sus[0].startswith(f'OWNER SUSPENSION: rule 2026-10-02 (4) suspended for {DATE} (approved: owner, fixture approval) - waived: ')
          and all(t in sus[0] for t in NUMERIC_TOKENS) and 'Clean ML' not in sus[0], sus)
    check(f'{tag}: (b) an EXECUTE decision line is logged for the suspension, and no hold',
          re.search(r'URF Decision: EXECUTE - .* \| owner suspension of standing rule 2026-10-02 \(4\): ' + str(SUB_HELD) + r' numeric hold\(s\) waived for ' + DATE, out) is not None
          and 'BUILD FAILED' not in out, out[-600:])
    # the disclosure is read case-insensitively; extra unrelated lines in the log are fine
    rc, out, written, _ = build(B, card(SUB, card_note='OFFICIAL PICKS BY OWNER DIRECTIVE - SUB-BAR DISCLOSURE ON FILE', status_note=''),
                                log=log_of(line(date='2099-10-01', picks=['Other ML']), line(picks=SUB_NAMES)))
    check(f'{tag}: (b) "owner directive" disclosure in capitals and an earlier day\'s line alongside: still builds', rc == 0 and 'index.html' in written, (rc, out[-400:]))
    rc, out, written, _ = build(B, card(SUB, card_note='OWNER-DIRECTED PICKS, SUB-BAR'), log=log_of(line(picks=SUB_NAMES)))
    check(f'{tag}: (b) "owner-directed" disclosure in capitals: builds', rc == 0 and 'index.html' in written, (rc, out[-400:]))
    # the Oct 4 and Oct 5 cards' own card_note: its "neither" negates nothing in the disclosure's clauses
    oct45 = "Owner-directed picks: neither cleared this morning's full process (standing bars plus red team); sub-bar disclosure."
    rc, out, written, _ = build(B, card(SUB, card_note=oct45), log=log_of(line(picks=SUB_NAMES)))
    check(f'{tag}: (b) the Oct 4/5 card_note (a "neither" in another clause) is a positive disclosure: builds', rc == 0 and 'index.html' in written, (rc, out[-400:]))

    # (c) a log line for another date: held
    for other in ('2099-10-05', '2099-10-03', '2099-10-4', ' 2099-10-04'):
        rc, out, written, _ = build(B, card(SUB), log=log_of(line(date=other, picks=SUB_NAMES)))
        check(f'{tag}: (c) a log line dated {other!r} for a {DATE} card: held', held(rc, out, written), (rc, out[-400:], written))
    rc, out, written, _ = build(B, card(SUB, date=None), log=log_of(line(picks=SUB_NAMES)))
    check(f'{tag}: (c) a manifest with no date: held', held(rc, out, written), (rc, out[-400:], written))

    # (d) a held pick not in the list: the whole card is held (nothing partly waived)
    rc, out, written, _ = build(B, card(SUB), log=log_of(line(picks=SUB_NAMES[:-1])))
    check(f'{tag}: (d) a held pick missing from the list: held, the hold names every item',
          held(rc, out, written) and all(t in out for t in NUMERIC_TOKENS) and f'covers 4 of {SUB_HELD} held item(s)' in out, (rc, out[-600:], written))
    for near in ('thin ml', 'Thin ML ', 'Thin  ML', 'Thin'):
        rc, out, written, _ = build(B, card(SUB), log=log_of(line(picks=[near] + SUB_NAMES[1:])))
        check(f'{tag}: (d) pick name {near!r} is not exactly "Thin ML": held', held(rc, out, written), (rc, out[-400:], written))

    # (e) a Vegas pick listed in the log: held (the Vegas rule is never suspendable), numeric-clean or sub-bar
    for label, vp in (('numeric-clean', pick(6, 'Raiders ML', 'football/nfl', 'Denver Broncos', 'Las Vegas Raiders')),
                      ('also sub-bar', pick(6, 'Kings ML', 'hockey/nhl', 'Los Angeles Kings', 'Vegas Golden Knights', model=61.0))):
        rc, out, written, _ = build(B, card(SUB + [vp]), log=log_of(line(picks=SUB_NAMES + [vp['name']])))
        check(f'{tag}: (e) a listed Vegas pick ({label}): held, the Vegas rule named', held(rc, out, written) and 'Las Vegas team' in out, (rc, out[-400:], written))

    # (f) a ladder violation listed in the log: held
    for u in ('6u', '20u', '5', None):
        lp = pick(6, 'Bills ML', 'football/nfl', 'New England Patriots', 'Buffalo Bills', units=u)
        rc, out, written, _ = build(B, card(SUB + [lp]), log=log_of(line(picks=SUB_NAMES + ['Bills ML'])))
        check(f'{tag}: (f) a listed pick at units {u!r} (off the ladder): held', held(rc, out, written) and 'not on the J-096 ladder' in out, (rc, out[-400:], written))

    # the other non-suspendable items, listed in the log: held
    cut = pick(6, 'Fav ML', units='100u', model=96.0, american=-567)
    rc, out, written, _ = build(B, card(SUB + [cut]), log=log_of(line(picks=SUB_NAMES + ['Fav ML'])))
    check(f'{tag}: a listed pick with the card ask at the 85c cut: held', held(rc, out, written) and '85c cut' in out, (rc, out[-400:], written))
    ba = pick(6, 'BadAm ML', model=66.0, american=-130)
    ba['best_ask'] = {'venue': 'dk', 'price': -150, 'read_at': '2099-10-04T14:51:00Z', 'cost_c': 60.0, 'fee_c': 0.0, 'gross_c': 6.0, 'net_c': 6.0,
                      'compared': [{'venue': 'dk', 'price': -150, 'read_at': '2099-10-04T14:51:00Z'}, {'venue': 'kalshi', 'price': 61, 'read_at': '2099-10-04T14:51:00Z'}]}
    ba['kalshi'] = {'cents': 61, 'team': 'B', 'ticker': 'KXFIX-1'}
    rc, out, written, _ = build(B, card(SUB + [ba]), log=log_of(line(picks=SUB_NAMES + ['BadAm ML'])))
    check(f'{tag}: a listed pick whose card price is not the best recorded ask: held', held(rc, out, written) and 'best recorded ask' in out, (rc, out[-400:], written))
    l1, l2 = pick(6, 'Leg1 ML', away='E1', home='F1', model=63.0), pick(7, 'Leg2 ML', away='E2', home='F2', model=63.0)
    rc, out, written, _ = build(B, card(SUB + [l1, l2], parlay={'legs': ['Leg1 ML', 'Leg2 ML'], 'note': ''}),
                                log=log_of(line(picks=SUB_NAMES + ['Leg1 ML', 'Leg2 ML', 'parlay'])))
    check(f'{tag}: a sub-bar parlay with its legs listed: held (parlay items are never suspendable)',
          held(rc, out, written) and 'parlay: net' in out, (rc, out[-400:], written))
    for k, v in (('rule', '2026-10-02 (1)'), ('rule', '2026-10-02 (4) '), ('scope', 'all'), ('scope', 'Numeric')):
        rc, out, written, _ = build(B, card(SUB), log=log_of(line(picks=SUB_NAMES, **{k: v})))
        check(f'{tag}: a log line with {k} {v!r}: held', held(rc, out, written), (rc, out[-400:], written))

    # (g) the card_note disclosure is missing or half there: held. The status_note is never rendered by this
    # builder, so a disclosure there alone does not count.
    for note in ('', 'Official picks', 'Owner-directed picks', 'Official picks by owner directive', 'sub-bar disclosure on file',
                 'Owner directed picks; sub-bar', 'owner-direct sub-bar', None, 7):
        rc, out, written, _ = build(B, card(SUB, card_note=note), log=log_of(line(picks=SUB_NAMES)))
        check(f'{tag}: (g) card_note {note!r}: held, the missing disclosure named',
              held(rc, out, written) and 'needs the card_note disclosure' in out, (rc, out[-400:], written))
    # a negated disclosure is no disclosure: the old substring test let every one of these through
    for note in ('not owner-directed; sub-bar disclosure', 'No owner directive - sub-bar disclosure', 'Owner-directed picks; not sub-bar',
                 'Owner-directed picks: no sub-bar disclosure', 'Non-owner-directed picks; sub-bar disclosure', 'Owner-directed: no; sub-bar: no',
                 'Neither owner-directed nor sub-bar', 'These picks are not owner-directed and carry no sub-bar disclosure',
                 'Owner-directed picks; sub-bar disclosure; this card isn\u2019t owner-directed', 'Owner-directed picks without a sub-bar disclosure',
                 'OWNER DIRECTIVE: NONE. SUB-BAR: NONE.'):
        rc, out, written, _ = build(B, card(SUB, card_note=note), log=log_of(line(picks=SUB_NAMES)))
        check(f'{tag}: (g) a negated card_note disclosure {note!r}: held, the negation named',
              held(rc, out, written) and 'needs the card_note disclosure stated positively' in out and 'is negated' in out, (rc, out[-400:], written))
    m = card(SUB, status_note=NOTE); del m['card_note']
    rc, out, written, _ = build(B, m, log=log_of(line(picks=SUB_NAMES)))
    check(f'{tag}: (g) the disclosure only in the (unrendered) status_note, no card_note: held',
          held(rc, out, written) and 'needs the card_note disclosure' in out, (rc, out[-400:], written))

    # (h) a malformed log: nothing waived, even beside a well-formed matching line
    good = line(picks=SUB_NAMES)
    thin = REG['Thin ML']
    bad_lines = [('not JSON', '{"date":"2099-10-04",'), ('a JSON list', '[1,2]'), ('a blank line', ''),
                 ('picks as a string', line(picks=()).replace('"picks":[]', '"picks":"Thin ML"')),
                 ('an empty picks list', line(picks=())), ('a non-object pick', line(picks=[thin, 7])),
                 ('an old-style name-only pick', line(picks=()).replace('"picks":[]', '"picks":["Thin ML"]')),
                 ('an entry without eid', line(picks=[{'name': 'Thin ML', 'units': '5u'}])),
                 ('an entry with a numeric eid', line(picks=[dict(thin, eid=2)])),
                 ('an entry with blank units', line(picks=[dict(thin, units=' ')])),
                 ('an entry with no name', line(picks=[dict(thin, name='')])),
                 ('no approval', line(picks=SUB_NAMES, approved='')), ('no logged_at', json.dumps({k: v for k, v in json.loads(good).items() if k != 'logged_at'})),
                 ('a numeric date', good.replace('"date":"2099-10-04"', '"date":20991004')),
                 ('an impossible calendar date', line(date='2099-02-30', picks=['Other ML'])),
                 ('a date with a time', line(date='2099-10-04T00:00:00Z', picks=['Other ML'])),
                 ('a zoneless logged_at', line(picks=['Other ML'], logged_at='2099-10-04T14:00:00')),
                 ('an unreadable logged_at', line(picks=['Other ML'], logged_at='this morning'))]
    for label, bl in bad_lines:
        for order, text in (('after', log_of(good, bl)), ('before', log_of(bl, good))):
            rc, out, written, _ = build(B, card(SUB), log=text)
            check(f'{tag}: (h) a malformed line ({label}, {order} the matching line): held, the log named untrusted',
                  held(rc, out, written) and 'owner_rule_suspensions.jsonl line' in out and 'nothing waived' in out, (rc, out[-400:], written))
    rc, out, written, _ = build(B, card(SUB), log='\ufeff' + good + '\x00\n')
    check(f'{tag}: (h) a log with stray bytes: held', held(rc, out, written), (rc, out[-400:], written))

    # (i) the real Oct 3 owner card: held with no log, builds with the repo's own suspension log. Offline, its
    # Kalshi-priced pick can only build as a display-only rebuild (the card's pick-content hash already shipped,
    # as on every refresh after the publish): the live market cannot be re-read here. The standing-rules hold runs
    # before that gate on every build, display-only included, so the hold and the waiver are exercised as published.
    real_cnote = open(os.path.join(REAL_CARD, 'card_note.txt'), encoding='utf-8').read().strip()
    real = card(json.load(open(os.path.join(REAL_CARD, 'picks.json'), encoding='utf-8')), date='2026-10-03', date_label='Saturday, Oct 3',
                updated='Oct 3, 7:44 AM PT', record='27-13', units_pl='+14.01u',
                status_note=open(os.path.join(REAL_CARD, 'status_note.txt'), encoding='utf-8').read().strip(), card_note=real_cnote)
    real_log = open(REAL_LOG, encoding='utf-8').read()
    real_rec = json.loads(real_log.splitlines()[0])
    check(f'{tag}: (i) the repo log line names every pick on the final card with its eid and units',
          real_rec['picks'] == [{'name': p['name'], 'eid': p['game']['eid'], 'units': p['units']} for p in real['picks']]
          and len(real['picks']) == 6 and {'Rays ML', 'Lightning ML'} <= {p['name'] for p in real['picks']}, real_rec['picks'])
    shipped = {'shipped_pick_hash.txt': pick_hash(B, real) + '\n'}
    rc, out, written, _ = build(B, real, seed=shipped)
    check(f'{tag}: (i) the real 2026-10-03 owner card with no log: held (it breaks numeric bars)', held(rc, out, written), (rc, out[-600:], written))
    real_holds = sorted(set(re.findall(r"pick \d '([^']+)'", out.split('BUILD FAILED', 1)[-1])))
    rc, out, written, body = build(B, real, log=real_log, seed=shipped)
    sus = [l for l in out.splitlines() if l.startswith('OWNER SUSPENSION:')]
    check(f'{tag}: (i) historical owner card replayed as current content stays held: missing Kalshi is structural, never waived',
          held(rc,out,written) and 'no Kalshi market' in out and not body and not sus,(rc,out[-600:]))
    check(f'{tag}: (i) original historical fixture has not gained synthetic Kalshi fields',
          json.load(open(os.path.join(REAL_CARD,'picks.json'))) == real['picks'])
    rc,out,written,_=build(B,real,log=real_log)
    check(f'{tag}: (i) historical card as new current content is refused even with numeric log',
          held(rc,out,written) and 'no Kalshi market' in out,(rc,out[-400:]))
    for other in ('2026-10-04', '2026-10-02'):
        rc, out, written, _ = build(B, dict(real, date=other), log=real_log, seed=shipped)
        check(f'{tag}: (i) the same card dated {other} with the real log: held (the suspension is for 2026-10-03 only)', held(rc, out, written), (rc, out[-400:], written))
    rc, out, written, _ = build(B, dict(real, card_note='Official picks'), log=real_log, seed=shipped)
    check(f'{tag}: (i) the real card without its card_note sub-bar disclosure: held', held(rc, out, written), (rc, out[-400:], written))
    # the stale-date case: the real card re-dated 2099-10-04 under a 2099-10-04 line carrying its exact entries
    rc, out, written, _ = build(B, dict(real, date=DATE), log=log_of(line(picks=real_rec['picks'])), seed=shipped)
    check(f'{tag}: (i) the real card re-dated {DATE} under a {DATE} log line with its entries: held (its games play 2026-10-03)',
          held(rc, out, written) and 'plays on 2026-10-03 (Pacific), not the logged ' + DATE in out, (rc, out[-400:], written))
    for k, v in (('eid', '401907986'), ('units', '10u')):
        bad = json.loads(real_log.splitlines()[0])
        held_names = [e for e in bad['picks'] if e['name'] in real_holds]
        if held_names: held_names[0][k] = v
        rc, out, written, _ = build(B, real, log=json.dumps(bad, separators=(',', ':')) + '\n', seed=shipped)
        check(f'{tag}: (i) the real card under a log whose entry for a held pick has a different {k}: held',
              bool(held_names) and held(rc, out, written) and 'does not match its logged entry' in out, (rc, out[-400:], written))

    # (j) a card with no holds: identical output with and without the log (the log is never read for it)
    for label, m in (('a clean one-pick card', card([CLEAN])), ('an empty card', card([], status_note='No official picks today'))):
        r0 = stamped(build(B, m))
        for loglabel, text in (('the real log', real_log), ('a matching log', log_of(line(picks=['Clean ML']))), ('a malformed log', '{not json\n')):
            r1 = stamped(build(B, m, log=text))
            check(f'{tag}: (j) {label} builds identically without and with {loglabel} (exit, output, files written, bytes)',
                  r0[0] == 0 and 'index.html' in r0[2] and r1[:3] == r0[:3] and r1[3] == r0[3] and 'owner suspension' not in r1[1].lower(),
                  (r0[0], r1[0], r0[2], r1[2], [f for f in r0[2] if r0[3].get(f) != r1[3].get(f)],
                   [l for l in set(r0[1].splitlines()) ^ set(r1[1].splitlines())][:4]))

    # (k) unique names: a logged name on more than one card pick waives nothing, held or not
    dup = pick(6, 'Thin ML', away='C6', home='D6', model=61.0)
    rc, out, written, _ = build(B, card(SUB + [dup]), log=log_of(line(picks=SUB_NAMES)))
    check(f'{tag}: (k) a logged held name on two card picks: held, the duplicate named',
          held(rc, out, written) and "logged pick name(s) on more than one card pick: 'Thin ML'" in out, (rc, out[-400:], written))
    REG['Thin ML'] = ent(THIN)
    dupc = pick(6, 'Clean ML', away='C6', home='D6')
    rc, out, written, _ = build(B, card(SUB + [dupc]), log=log_of(line(picks=SUB_NAMES + ['Clean ML'])))
    check(f'{tag}: (k) a logged clean name on two card picks (every hold otherwise covered): held',
          held(rc, out, written) and "more than one card pick: 'Clean ML'" in out, (rc, out[-400:], written))
    REG['Clean ML'] = ent(CLEAN)
    rc, out, written, _ = build(B, card(SUB), log=log_of(line(picks=SUB_NAMES), line(picks=[dict(REG['Thin ML'], eid='FIX-99')])))
    check(f'{tag}: (k) a name logged twice for the date with different entries: held',
          held(rc, out, written) and "pick 'Thin ML' is logged twice with different entries" in out, (rc, out[-400:], written))
    rc, out, written, _ = build(B, card(SUB), log=log_of(line(picks=SUB_NAMES), line(picks=['Thin ML'])))
    check(f'{tag}: (k) a name logged twice with the same entry: builds', rc == 0 and 'index.html' in written, (rc, out[-400:]))

    # (l) real date: each waived pick's game must be on the logged date in Pacific time
    for when, ok in (('2099-10-03T20:25Z', False), ('2099-10-05T03:00Z', True), ('2099-10-05T08:00Z', False),
                     ('2026-10-03T20:25Z', False), ('', False), (None, False)):
        tp = copy.deepcopy(THIN); tp['game']['commence'] = when
        rc, out, written, _ = build(B, card([CLEAN, tp] + SUB[2:]), log=log_of(line(picks=SUB_NAMES)))
        if ok:
            check(f'{tag}: (l) a waived pick at {when} (still {DATE} in Pacific time): builds', rc == 0 and 'index.html' in written, (rc, out[-400:]))
        else:
            check(f'{tag}: (l) a waived pick at {when!r} (not {DATE} in Pacific time): held, the date named',
                  held(rc, out, written) and "pick 'Thin ML' plays on" in out and f'not the logged {DATE}' in out, (rc, out[-400:], written))

    # a commence with no UTC offset is never read in the machine's own zone: '2099-10-05T02:00' read as UTC is
    # 2099-10-04 in Pacific time (the old reading on a UTC runner waived it), read as Pacific it is 2099-10-05
    for zone in ('UTC', 'America/Los_Angeles', 'Asia/Tokyo'):
        tp = copy.deepcopy(THIN); tp['game']['commence'] = '2099-10-05T02:00'
        rc, out, written, _ = build(B, card([CLEAN, tp] + SUB[2:]), log=log_of(line(picks=SUB_NAMES)), tz=zone)
        check(f'{tag}: (l) a waived pick with a zoneless commence, machine zone {zone}: held, the missing offset named',
              held(rc, out, written) and "pick 'Thin ML' plays on no date" in out and 'explicit UTC offset' in out, (rc, out[-400:], written))
    tp = copy.deepcopy(THIN); tp['game']['commence'] = '2099-10-04T23:30-07:00'
    rc, out, written, _ = build(B, card([CLEAN, tp] + SUB[2:]), log=log_of(line(picks=SUB_NAMES)), tz='UTC')
    check(f'{tag}: (l) a waived pick at 2099-10-04T23:30-07:00 (an explicit offset, {DATE} in Pacific time) on a UTC machine: builds',
          rc == 0 and 'index.html' in written, (rc, out[-400:]))

    # (m) content binding: a waived pick must carry exactly its logged eid and units
    for label, entry in (('eid', dict(REG['Thin ML'], eid='FIX-99')), ('eid case', dict(REG['Thin ML'], eid='fix-2')),
                         ('units', dict(REG['OffRung ML'], units='5u'))):
        others = [n for n in SUB_NAMES if n != entry['name']]
        rc, out, written, _ = build(B, card(SUB), log=log_of(line(picks=others + [entry])))
        check(f'{tag}: (m) a logged entry whose {label} differs from the card pick: held, the mismatch named',
              held(rc, out, written) and f"pick {entry['name']!r} (eid" in out and 'does not match its logged entry' in out, (rc, out[-400:], written))
    tp = copy.deepcopy(THIN); tp['game']['eid'] = ''
    rc, out, written, _ = build(B, card([CLEAN, tp] + SUB[2:]), log=log_of(line(picks=SUB_NAMES)))
    check(f'{tag}: (m) a waived pick with no eid on the card: held', held(rc, out, written) and 'does not match its logged entry' in out, (rc, out[-400:], written))

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
