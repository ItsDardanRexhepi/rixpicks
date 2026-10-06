#!/usr/bin/env python3
"""RIX core regression gate (stage 0 of the core merge, 9/27). Self-contained: adapters ->
build_manifest preview (isolated ledger) -> finals_watch grading suites. Exit 1 on any failure.
Run: python3 tests/run_tests.py (from any checkout; RIX_SCRIPTS overrides the scripts dir)"""
import importlib.util, json, os, subprocess, sys, tempfile

# Paths follow this checkout (was hardcoded to /home/sandbox/rix_tmp, so the gate could not run
# from a repo clone or in Actions). The repo root goes on the import path for core/, both here
# and for the adapter/builder subprocesses.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.environ.get('RIX_SCRIPTS', os.path.join(ROOT, 'scripts'))
sys.path.insert(0, ROOT)
os.environ['PYTHONPATH'] = ROOT + (os.pathsep + os.environ['PYTHONPATH'] if os.environ.get('PYTHONPATH') else '')
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')
failures = []

def check(label, got, want):
    ok = got == want
    if not ok: failures.append(f'{label}: want {want!r} got {got!r}')
    print(f"{'OK  ' if ok else 'FAIL'} {label}" + ('' if ok else f'  [want {want!r} got {got!r}]'))

def load(mod, path):
    spec = importlib.util.spec_from_file_location(mod, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m

def run_adapter(script, rows, eid_map, extra=()):
    r = subprocess.run(['python3', f'{SCRIPTS}/{script}', rows, '--eid-map', eid_map, *extra],
                       capture_output=True, text=True)
    return json.loads(r.stdout), r.stderr.strip()

tmp = tempfile.mkdtemp(prefix='rixtest_')
os.environ['RIX_PICKS_LEDGER'] = f'{tmp}/picks.jsonl'
os.environ['RIX_PROD_MANIFEST'] = f'{tmp}/prod_manifest.json'  # never read or mirror the grader's manifest
os.environ.setdefault('RIX_CONFIG_PROPS', os.path.join(ROOT, 'config_props.json'))  # props adapter config from this checkout
# grading suites compare result letters only: any positive 1u dollar size works, so a placeholder
# stands in when the private RIX_UNIT_DOLLARS is not set (the real size never lives in the repo)
os.environ.setdefault('RIX_UNIT_DOLLARS', '1')
LEDGER = f'{tmp}/picks.preview.jsonl'

# ---------- 1. adapter gates ----------
cs, err = run_adapter('st_card_candidates.py', f'{FIX}/st_rows.json', f'{FIX}/eid_map.json')
check('s/t adapter: 3 of 4 rows card (2c floor)', len(cs), 3)
cs_nf, _ = run_adapter('st_card_candidates.py', f'{FIX}/st_rows.json', f'{FIX}/eid_map.json', ('--no-floor',))
check('s/t adapter --no-floor: band still binds (3, not 4)', len(cs_nf), 3)
cs2, _ = run_adapter('st_card_candidates.py', f'{FIX}/st_rows2.json', f'{FIX}/eid_map2.json')
check('s/t alt adapter: away-cover + under emit', sorted(c['side'] for c in cs2), ['away', 'under'])
# --now = the 6:45 AM build moment; fixture commences are that evening except the started row
pc, perr = run_adapter('props_card_candidates.py', f'{FIX}/props_feed.json', f'{FIX}/eid_map.json',
                       ('--now=2026-09-28T06:45:00-07:00',))
check('props adapter: 4 of 10 rows card (NFL 2 + MLB 1 + MLS 1)', len(pc), 4)
check('props adapter: loud skip missing espn_id', 'no ESPN id' in perr, True)
check('props adapter: loud skip live/started prop (pre-game only)', 'pre-game only' in perr, True)
check('props adapter: loud skip missing commence (fail closed)', 'no/ambiguous commence' in perr, True)
check('props adapter: loud skip ungradeable market', 'ungradeable market' in perr, True)
check('props adapter: MLB/soccer rows carry new markets',
      sorted(c['market'] for c in pc if c['market_class'] == 'prop'),
      ['anytime_goal', 'bat_hits', 'receiving_yards', 'receptions'])

# ---------- 2. manifest builds ----------
def build(cands, name):
    for i, c in enumerate(cands, 1):
        c['num'] = i
        # Synthetic adapter fixture only: explicit YES identity, never infer side for real candidates.
        if isinstance(c.get('kalshi'),dict): c['kalshi'].setdefault('side','yes')
    cf = f'{tmp}/{name}.json'; json.dump(cands, open(cf, 'w'))
    if os.path.exists(LEDGER): os.remove(LEDGER)
    r = subprocess.run(['python3', f'{SCRIPTS}/build_manifest.py', cf, f'{tmp}/{name}.manifest.json',
                        '--preview', '--meta', f'{FIX}/meta.json'], capture_output=True, text=True,
                       env=dict(os.environ))
    assert r.returncode == 0, f'{name} build failed: {r.stderr}'
    return [json.loads(l) for l in open(LEDGER)]

ml = json.load(open(f'{FIX}/ml_cand.json'))
rows = build(ml + cs, 'primary')
check('primary manifest: 4 ledger rows', len(rows), 4)
check('primary ledger: spread row carries line', any(r.get('line') == -6.5 for r in rows), True)

# ---------- 3. grading suites ----------
for _k in ('RPS_KB', 'RIX_REPO', 'RIX_FINALS_CONFIG'):
    os.environ.pop(_k, None)  # finals_watch reads its private paths at import; this gate uses its own
fw = load('fw', f'{SCRIPTS}/finals_watch.py')
_real = fw.fill_leak.card_price
fw.fill_leak.card_price = lambda pick, **kw: _real(pick, picks_path=LEDGER)

def P(eid, cents, odds, units, **kw):
    d = {'game': {'eid': eid}, 'kalshi': {'cents': cents}, 'odds': odds, 'units': units}
    d.update(kw); return d

# variant ledger rows for line/side/push variants of the published picks
variants = [
 {'kind':'pick','event_id':'401000001','market_class':'spread','side':'home','line':-7,'entry_c':52,'card_american':-110,'name':'t','units':'5u','card_ts':'x','kalshi_ticker':'T','commence':'c','preview':True},
 {'kind':'pick','event_id':'401000003','market_class':'total','side':'over','line':44,'entry_c':52,'card_american':-110,'name':'t','units':'5u','card_ts':'x','kalshi_ticker':'T','commence':'c','preview':True},
 # soccer: recorded ESPN summaries (tests/fixtures/soccer) - MLS 761439 1-1; NWSL 760606 1-1 at 90, 2-1 AET
 {'kind':'pick','event_id':'761439','market_class':'ml','side':'home','entry_c':45,'card_american':122,'name':'t','units':'5u','card_ts':'x','kalshi_ticker':'T','commence':'c','preview':True},
 {'kind':'pick','event_id':'760606','market_class':'ml','side':'away','entry_c':45,'card_american':122,'name':'t','units':'5u','card_ts':'x','kalshi_ticker':'T','commence':'c','preview':True},
 {'kind':'pick','event_id':'760606','market_class':'total','side':'under','line':2.5,'entry_c':60,'card_american':-150,'name':'t','units':'5u','card_ts':'x','kalshi_ticker':'T','commence':'c','preview':True},
]
for _eid, _lg in (('761439', 'soccer/usa.1'), ('760606', 'soccer/usa.nwsl')):
    fw._PROP_BOX[(_lg, _eid)] = json.load(open(f'{FIX}/soccer/summary_{_eid}.json'))
with open(LEDGER, 'a') as f:
    for v in variants: f.write(json.dumps(v) + '\n')
for label, want, pick, primary in [
    ('ml home win','W', P('401000010',71,-245,'10u',market_class='ml',side='home'), {'home_score':30,'away_score':20}),
    # a level moneyline: a tie refunds in the NFL (PUSH); soccer settles on regulation time, where a draw
    # loses either side (Kalshi's three-way game contract) and extra time never counts
    ('nfl ml tie push','PUSH', P('401000010',71,-245,'10u',market_class='ml',side='home',espn_league='football/nfl'), {'home_score':20,'away_score':20}),
    ('mls ml 1-1 draw lost','L', P('761439',45,122,'5u',market_class='ml',side='home',espn_league='soccer/usa.1'), {'home_score':1,'away_score':1}),
    ('nwsl 760606 Gotham ml lost (1-1 at 90, 2-1 AET)','L', P('760606',45,122,'5u',market_class='ml',side='away',espn_league='soccer/usa.nwsl'), {'home_score':1,'away_score':2}),
    ('nwsl 760606 under 2.5 won (2 regulation goals)','W', P('760606',60,-150,'5u',market_class='total',side='under',line=2.5,espn_league='soccer/usa.nwsl'), {'home_score':1,'away_score':2}),
    ('spread -6.5 cover','W', P('401000001',55,-122,'5u',market_class='spread',side='home',line=-6.5), {'home_score':27,'away_score':20}),
    ('spread -7 push','PUSH', P('401000001',52,-110,'5u',market_class='spread',side='home',line=-7), {'home_score':27,'away_score':20}),
    ('spread +4.5 dog cover','W', P('401000002',44,127,'5u',market_class='spread',side='home',line=4.5), {'home_score':20,'away_score':24}),
    ('total 44.5 over','W', P('401000003',52,-108,'5u',market_class='total',side='over',line=44.5), {'home_score':24,'away_score':21}),
    ('total 44 push','PUSH', P('401000003',52,-110,'5u',market_class='total',side='over',line=44), {'home_score':23,'away_score':21}),
]:
    try: got = fw.grade(pick, primary)[0]
    except Exception as e: got = f'RAISED: {e}'
    check(f'grade primary: {label}', got, want)

# alt suite: rebuild alt ledger + variants
rows2 = build(cs2, 'alt')
check('alt manifest: 2 ledger rows', len(rows2), 2)
with open(LEDGER, 'a') as f:
    f.write(json.dumps({'kind':'pick','event_id':'401000001','market_class':'spread','side':'away','line':-6,'entry_c':52,'card_american':-110,'name':'t','units':'5u','card_ts':'x','kalshi_ticker':'T','commence':'c','preview':True}) + '\n')
    f.write(json.dumps({'kind':'pick','event_id':'401000003','market_class':'total','side':'under','line':44,'entry_c':52,'card_american':-110,'name':'t','units':'5u','card_ts':'x','kalshi_ticker':'T','commence':'c','preview':True}) + '\n')
for label, want, pick, primary in [
    ('away +6.5 cover','W', P('401000001',55,-122,'5u',market_class='spread',side='away',line=-6.5), {'home_score':24,'away_score':21}),
    ('away +6 push','PUSH', P('401000001',52,-110,'5u',market_class='spread',side='away',line=-6), {'home_score':27,'away_score':21}),
    ('under 44.5 holds','W', P('401000003',56,-127,'5u',market_class='total',side='under',line=44.5), {'home_score':23,'away_score':21}),
    ('under 44 push','PUSH', P('401000003',52,-110,'5u',market_class='total',side='under',line=44), {'home_score':23,'away_score':21}),
]:
    try: got = fw.grade(pick, primary)[0]
    except Exception as e: got = f'RAISED: {e}'
    check(f'grade alt: {label}', got, want)

# props suite: rebuild props ledger + variants + mocked boxscore
rows3 = build(pc, 'props')
check('props manifest: 4 ledger rows w/ player+market', len(rows3) == 4 and all(r.get('player') and r.get('market') for r in rows3), True)
pvars = [
 ('Kyren Williams','receptions',3.5,'over',66,-194), ('Kyren Williams','receptions',3,'over',66,-194),
 ('Kyren Williams','receptions',3.5,'under',66,-194), ('Kyren Williams','anytime_td',0.5,'over',42,138),
 ('CeeDee Lamb','anytime_td',0.5,'over',42,138), ('Williams','receptions',2.5,'over',66,-194),
 ('Ghost Player','receptions',2.5,'over',66,-194), ('Kyren Williams','double_double',0.5,'over',66,-194),
]
with open(LEDGER, 'a') as f:
    for player, market, line, side, c, am in pvars:
        f.write(json.dumps({'kind':'pick','event_id':'401000001','market_class':'prop','player':player,
                            'market':market,'line':line,'side':side,'entry_c':c,'card_american':am,
                            'name':'t','units':'5u','card_ts':'x','kalshi_ticker':'T','commence':'c','preview':True}) + '\n')
BOX = json.loads(open(f'{FIX}/boxscore.json').read())
fw._PROP_BOX[('football/nfl', '401000001')] = BOX
LE = 'football/nfl'
for label, want, pick in [
    ('receptions 3 over 2.5','W', P('401000001',66,-194,'5u',market_class='prop',espn_league=LE,player='Kyren Williams',market='receptions',line=2.5,side='over')),
    ('receptions 3 over 3.5','L', P('401000001',66,-194,'5u',market_class='prop',espn_league=LE,player='Kyren Williams',market='receptions',line=3.5,side='over')),
    ('receptions 3 push','PUSH', P('401000001',66,-194,'5u',market_class='prop',espn_league=LE,player='Kyren Williams',market='receptions',line=3,side='over')),
    ('receptions under','W', P('401000001',66,-194,'5u',market_class='prop',espn_league=LE,player='Kyren Williams',market='receptions',line=3.5,side='under')),
    ('recv yards 80 over 72.5','W', P('401000001',55,-122,'5u',market_class='prop',espn_league=LE,player='Puka Nacua',market='receiving_yards',line=72.5,side='over')),
    ('anytime_td yes','W', P('401000001',42,138,'5u',market_class='prop',espn_league=LE,player='Kyren Williams',market='anytime_td',line=0.5,side='over')),
    ('anytime_td no','L', P('401000001',42,138,'5u',market_class='prop',espn_league=LE,player='CeeDee Lamb',market='anytime_td',line=0.5,side='over')),
    ('ambiguous player','REFUSED', P('401000001',66,-194,'5u',market_class='prop',espn_league=LE,player='Williams',market='receptions',line=2.5,side='over')),
    ('unknown player','REFUSED', P('401000001',66,-194,'5u',market_class='prop',espn_league=LE,player='Ghost Player',market='receptions',line=2.5,side='over')),
    ('ungradeable market','REFUSED', P('401000001',66,-194,'5u',market_class='prop',espn_league=LE,player='Kyren Williams',market='double_double',line=0.5,side='over')),
]:
    try: got = fw.grade(pick, {'home_score': 0, 'away_score': 0})[0]
    except ValueError as e: got = 'REFUSED' if ('fail closed' in str(e) or 'REFUSING' in str(e)) else f'RAISED: {e}'
    except Exception as e: got = f'RAISED {type(e).__name__}: {e}'
    check(f'grade props: {label}', got, want)

# ---------- 4. anchor alt-side math ----------
sf = load('sf', f'{SCRIPTS}/st_fair.py')
sf.kalshi_markets = lambda series: [
    {'ticker': 'KXNFLSPREAD-T1-MIA', 'event_ticker': 'BUFMIA', 'title': 'MIA Dolphins wins by over 6.5 points',
     'yes_ask_dollars': '0.55', 'yes_bid_dollars': '0.50'}]
r = sf.anchor_kalshi({'match': 'Buffalo Bills @ Miami Dolphins', 'away': 'Buffalo Bills', 'home': 'Miami Dolphins',
                      'sport': 'nfl', 'commence': '2026-09-28T17:00Z', 'cls': 'spread', 'consensus_line': -6.5,
                      'fair_home_or_over_c': 68.4, 'n_books': 4, 'confidence': 'OK'})
# ---------- 4. MLB + soccer grading suites (9/27 finish-grading directive) ----------
mlbvars = [
 ('Shohei Ohtani','bat_hits',1.5,'over'), ('Shohei Ohtani','bat_hits',2,'over'),
 ('Shohei Ohtani','pit_hits_allowed',4.5,'over'), ('Shohei Ohtani','pit_strikeouts',7.5,'over'),
 ('Shohei Ohtani','pit_outs',18.5,'over'), ('Shohei Ohtani','pit_outs',19,'over'),
 ('Sean Manaea','pit_outs',16.5,'over'), ('Mookie Betts','bat_walks',0.5,'over'),
 ('Shohei Ohtani','bat_total_bases',1.5,'over'), ('Ghost Batter','bat_hits',0.5,'over'),
]
with open(LEDGER, 'a') as f:
    for player, market, line, side in mlbvars:
        f.write(json.dumps({'kind':'pick','event_id':'401000100','market_class':'prop','player':player,
                            'market':market,'line':line,'side':side,'entry_c':66,'card_american':-194,
                            'name':'t','units':'5u','card_ts':'x','kalshi_ticker':'T','commence':'c','preview':True}) + '\n')
fw._PROP_BOX[('baseball/mlb', '401000100')] = json.load(open(f'{FIX}/mlb_boxscore.json'))
for label, want, pick in [
    ('bat_hits 2 over 1.5','W', P('401000100',66,-194,'5u',market_class='prop',espn_league='baseball/mlb',player='Shohei Ohtani',market='bat_hits',line=1.5,side='over')),
    ('bat_hits 2 push 2','PUSH', P('401000100',66,-194,'5u',market_class='prop',espn_league='baseball/mlb',player='Shohei Ohtani',market='bat_hits',line=2,side='over')),
    ('two-way: pit_hits_allowed reads pitching group (5 not 2)','W', P('401000100',66,-194,'5u',market_class='prop',espn_league='baseball/mlb',player='Shohei Ohtani',market='pit_hits_allowed',line=4.5,side='over')),
    ('pit_strikeouts 8 over 7.5','W', P('401000100',66,-194,'5u',market_class='prop',espn_league='baseball/mlb',player='Shohei Ohtani',market='pit_strikeouts',line=7.5,side='over')),
    ('pit_outs 6.1 = 19 over 18.5','W', P('401000100',66,-194,'5u',market_class='prop',espn_league='baseball/mlb',player='Shohei Ohtani',market='pit_outs',line=18.5,side='over')),
    ('pit_outs 19 push','PUSH', P('401000100',66,-194,'5u',market_class='prop',espn_league='baseball/mlb',player='Shohei Ohtani',market='pit_outs',line=19,side='over')),
    ('pit_outs 5.2 = 17 over 16.5','W', P('401000100',66,-194,'5u',market_class='prop',espn_league='baseball/mlb',player='Sean Manaea',market='pit_outs',line=16.5,side='over')),
    ('bat_walks 1 over 0.5','W', P('401000100',66,-194,'5u',market_class='prop',espn_league='baseball/mlb',player='Mookie Betts',market='bat_walks',line=0.5,side='over')),
    ('bat_total_bases REFUSED (no 2B/3B in ESPN)','REFUSED', P('401000100',66,-194,'5u',market_class='prop',espn_league='baseball/mlb',player='Shohei Ohtani',market='bat_total_bases',line=1.5,side='over')),
    ('ghost batter REFUSED','REFUSED', P('401000100',66,-194,'5u',market_class='prop',espn_league='baseball/mlb',player='Ghost Batter',market='bat_hits',line=0.5,side='over')),
]:
    try:
        got = fw.grade(pick, {'home_score':5,'away_score':2})[0]
        if want == 'REFUSED': got = 'NOT-REFUSED'  # grade must raise
    except Exception as e:
        got = 'REFUSED' if want == 'REFUSED' else f'RAISED: {e}'
    check(f'grade mlb: {label}', got, want)

socvars = [  # Bouanga anytime_goal 0.5 comes from the manifest build (feed fixture row)
 ('Denis Bouanga','first_goal',0.5,'over'),
 ('Denis Bouanga','last_goal',0.5,'over'), ('Son Heung-min','last_goal',0.5,'over'),
 ('Josef Martinez','anytime_goal',0.5,'over'), ('Diego Rossi','anytime_goal',0.5,'over'),
 ('Rodriguez','anytime_goal',0.5,'over'), ('Ghost Player','anytime_goal',0.5,'over'),
 ('Denis Bouanga','shots_on_target',0.5,'over'),
]
with open(LEDGER, 'a') as f:
    for player, market, line, side in socvars:
        f.write(json.dumps({'kind':'pick','event_id':'761844','market_class':'prop','player':player,
                            'market':market,'line':line,'side':side,'entry_c':60,'card_american':-150,
                            'name':'t','units':'5u','card_ts':'x','kalshi_ticker':'T','commence':'c','preview':True}) + '\n')
fw._PROP_BOX[('soccer/usa.1', '761844')] = json.load(open(f'{FIX}/soccer_summary.json'))
SOCP = lambda player, market, line=0.5: P('761844',60,-150,'5u',market_class='prop',espn_league='soccer/usa.1',player=player,market=market,line=line,side='over')
for label, want, pick in [
    ('anytime_goal 2 goals W','W', SOCP('Denis Bouanga','anytime_goal')),
    ('first_goal earliest clock W','W', SOCP('Denis Bouanga','first_goal')),
    ('last_goal latest clock W','W', SOCP('Denis Bouanga','last_goal')),
    ('last_goal wrong player L','L', SOCP('Son Heung-min','last_goal')),
    ('shootout goal excluded -> L','L', SOCP('Josef Martinez','anytime_goal')),
    ('own goal never credits -> L','L', SOCP('Diego Rossi','anytime_goal')),
    ('ambiguous roster name REFUSED','REFUSED', SOCP('Rodriguez','anytime_goal')),
    ('unknown player REFUSED','REFUSED', SOCP('Ghost Player','anytime_goal')),
    ('shots_on_target REFUSED (no player tables)','REFUSED', SOCP('Denis Bouanga','shots_on_target')),
]:
    try:
        got = fw.grade(pick, {'home_score':3,'away_score':0})[0]
        if want == 'REFUSED': got = 'NOT-REFUSED'
    except Exception as e:
        got = 'REFUSED' if want == 'REFUSED' else f'RAISED: {e}'
    check(f'grade mls: {label}', got, want)
# fail-closed goal-text variants
for fx, why in [('soccer_summary_bad_text', 'unparseable goal text'), ('soccer_summary_bad_scorer', 'scorer not on roster')]:
    fw._PROP_BOX[('soccer/usa.1', f'bad-{fx}')] = json.load(open(f'{FIX}/{fx}.json'))
    pk = P(f'bad-{fx}',60,-150,'5u',market_class='prop',espn_league='soccer/usa.1',player='Denis Bouanga',market='anytime_goal',line=0.5,side='over')
    try:
        fw.grade(pk, {'home_score':3,'away_score':0}); got = 'NOT-REFUSED'
    except Exception: got = 'REFUSED'
    check(f'grade mls: {why} REFUSED (fail closed)', got, 'REFUSED')
# D.C. United and St. Louis CITY SC (Oct 2 re-check): the goal text's first '. ' can fall inside a
# team name ('Goal! D.C. United 0, FC Dallas 1. Logan Farrington (FC Dallas) ...'), so the scorer is
# read after the scoreline. Trimmed real ESPN summaries: 761518 FC Dallas 4 at D.C. United 0 and
# 761439 Charlotte FC 1 at St. Louis 1; record_final.py reads the same events (kept in step below).
realvars = [('761518', 'Petar Musa', 'anytime_goal', 'W'), ('761518', 'Logan Farrington', 'first_goal', 'W'),
            ('761518', 'Petar Musa', 'last_goal', 'W'), ('761518', 'Logan Farrington', 'last_goal', 'L'),
            ('761518', 'Tai Baribo', 'anytime_goal', 'L'), ('761439', 'Marcel Hartel', 'first_goal', 'W'),
            ('761439', 'Pep Biel', 'last_goal', 'W'), ('761439', 'Marcel Hartel', 'anytime_goal', 'W'),
            ('761439', 'Marcel Hartel', 'last_goal', 'L')]
REALSUM = {'761518': json.load(open(f'{FIX}/soccer_summary_dc_761518.json')),
           '761439': json.load(open(f'{FIX}/soccer_summary_stl_761439.json'))}
with open(LEDGER, 'a') as f:
    for eid, player, market, _ in realvars:
        f.write(json.dumps({'kind':'pick','event_id':eid,'market_class':'prop','player':player,'market':market,'line':0.5,
                            'side':'over','entry_c':60,'card_american':-150,'name':'t','units':'5u','card_ts':'x',
                            'kalshi_ticker':'T','commence':'c','preview':True}) + '\n')
for eid, d in REALSUM.items():
    fw._PROP_BOX[('soccer/usa.1', eid)] = d
for eid, player, market, want in realvars:
    pk = P(eid,60,-150,'5u',market_class='prop',espn_league='soccer/usa.1',player=player,market=market,line=0.5,side='over')
    try: got = fw.grade(pk, {'home_score':0,'away_score':4})[0]
    except Exception as e: got = f'RAISED: {e}'
    check(f'grade mls real {eid}: {player} {market}', got, want)
# Scorers ESPN's goal text names differently from its roster (Oct 2 review: 40 of 571 goals in 187
# real games, so 34 games refused every scorer prop): 'Guilherme' is roster Guilherme Augusto, 'Luighi'
# is Luighi Hanri, 'Christian Ramirez' is Christian Ramírez, 'Tomás Ostrák' is Tomas Ostrak. The
# scorer is the key event's own participants[0] athlete id; the text name only cross-checks it, and
# names match with accents folded. Trimmed real ESPN summaries, participants kept: 761674 Seattle 1 at
# Austin 3, 761469 Houston 2 at New England 0, 761722 Philadelphia 3 at NYCFC 2, 761688 Colorado 0 at St. Louis 1.
namevars = [('761674', 'Myrto Uzuni', 'anytime_goal', 'W'), ('761674', 'Ilie Sánchez', 'first_goal', 'W'),
            ('761674', 'Christian Ramírez', 'last_goal', 'W'), ('761674', 'Christian Ramírez', 'anytime_goal', 'W'),
            ('761674', 'Paul Rothrock', 'anytime_goal', 'W'), ('761674', 'Myrto Uzuni', 'first_goal', 'L'),
            ('761469', 'Agustín Resch', 'anytime_goal', 'W'), ('761469', 'Guilherme Augusto', 'first_goal', 'W'),
            ('761469', 'Agustín Resch', 'last_goal', 'W'), ('761469', 'Guilherme Augusto', 'last_goal', 'L'),
            ('761722', 'Bruno Damiani', 'anytime_goal', 'W'), ('761722', 'Bruno Damiani', 'last_goal', 'W'),
            ('761722', 'Bénie Traoré', 'first_goal', 'W'), ('761722', 'Luighi Hanri', 'anytime_goal', 'W'),
            ('761722', 'Danley Jean Jacques', 'first_goal', 'L'),
            ('761688', 'Tomás Ostrák', 'anytime_goal', 'W'), ('761688', 'Tomás Ostrák', 'first_goal', 'W'),
            ('761688', 'Tomas Ostrak', 'last_goal', 'W'), ('761688', 'Tomas Totland', 'anytime_goal', 'L')]
NAMESUM = {'761674': json.load(open(f'{FIX}/soccer_summary_atx_761674.json')),
           '761469': json.load(open(f'{FIX}/soccer_summary_hou_761469.json')),
           '761722': json.load(open(f'{FIX}/soccer_summary_nyc_761722.json')),
           '761688': json.load(open(f'{FIX}/soccer_summary_stl_761688.json'))}
def _doctored(eid, edit):
    d = json.loads(json.dumps(NAMESUM[eid]))
    edit([e for e in d['keyEvents'] if e.get('scoringPlay') is True])
    return d
def _swap_id(goals):  # Resch's goal (text 'Agustin Resch') credited to Guilherme Augusto's id
    goals[1]['participants'][0]['athlete']['id'] = goals[0]['participants'][0]['athlete']['id']
def _unrostered(goals):
    goals[0]['participants'][0]['athlete']['id'] = '999999999'
def _no_participants(goals):  # with no participant id the text must resolve, as before: 'Guilherme' does not
    for g in goals: g.pop('participants', None)
def _own_goal_text(goals):  # an own goal typed as a goal is never credited to the player who put it in
    goals[1]['text'] = 'Own Goal by Agustin Resch, Houston Dynamo FC. New England Revolution 1, Houston Dynamo FC 1.'
DOCTORED = {'761469-swap': _doctored('761469', _swap_id), '761469-unrostered': _doctored('761469', _unrostered),
            '761469-noparts': _doctored('761469', _no_participants), '761469-owngoal': _doctored('761469', _own_goal_text)}
with open(LEDGER, 'a') as f:
    for eid, player, market, _ in namevars + [(k, 'Agustín Resch', 'anytime_goal', None) for k in DOCTORED]:
        f.write(json.dumps({'kind':'pick','event_id':eid,'market_class':'prop','player':player,'market':market,'line':0.5,
                            'side':'over','entry_c':60,'card_american':-150,'name':'t','units':'5u','card_ts':'x',
                            'kalshi_ticker':'T','commence':'c','preview':True}) + '\n')
for eid, d in list(NAMESUM.items()) + list(DOCTORED.items()):
    fw._PROP_BOX[('soccer/usa.1', eid)] = d
for eid, player, market, want in namevars:
    pk = P(eid,60,-150,'5u',market_class='prop',espn_league='soccer/usa.1',player=player,market=market,line=0.5,side='over')
    try: got = fw.grade(pk, {'home_score':0,'away_score':0})[0]
    except Exception as e: got = f'RAISED: {e}'
    check(f'grade mls real {eid}: {player} {market} (scorer by ESPN id)', got, want)
for eid, why in [('761469-swap', 'a participant id the goal text names as someone else'),
                 ('761469-unrostered', 'a participant id on neither roster'),
                 ('761469-noparts', 'no participant id and a goal text name the rosters spell differently'),
                 ('761469-owngoal', 'own-goal text on a goal-typed event')]:
    pk = P(eid,60,-150,'5u',market_class='prop',espn_league='soccer/usa.1',player='Agustín Resch',market='anytime_goal',line=0.5,side='over')
    try: fw.grade(pk, {'home_score':0,'away_score':0}); got = 'NOT-REFUSED'
    except Exception: got = 'REFUSED'
    check(f'grade mls: {why} REFUSED (fail closed)', got, 'REFUSED')
REALSUM.update(NAMESUM)
# both record writers read a scorer prop the same way: every rostered player, every market, every game
rf = load('rf', f'{SCRIPTS}/record_final.py')
def _both(fn, *a):
    try: return float(fn(*a) if fn is fw._soccer_scorer_stat else fn(*a)[0])
    except ValueError as e: return 'REFUSED'
mism, n = [], 0
for eid, d in REALSUM.items():
    for ros in d['rosters']:
        for e in ros['roster']:
            for market in ('anytime_goal', 'first_goal', 'last_goal'):
                nm = e['athlete']['displayName']; n += 1
                a, b = _both(fw._soccer_scorer_stat, d, nm, market), _both(rf._soccer_scorer, d, nm, market)
                if a != b: mism.append((eid, nm, market, a, b))
check(f'finals_watch and record_final agree on all {n} real scorer reads', mism, [])
# every rostered player is graded, but one: in 761722 Philadelphia's 'N. Pierre' (Neil Pierre) sits
# inside 'Kevin Pierre', so NYCFC's Kevin Pierre is not one player on the rosters and stays refused
check('real scorer reads are graded, not refused', [(eid, e['athlete']['displayName']) for eid, d in REALSUM.items()
      for ros in d['rosters'] for e in ros['roster']
      if _both(rf._soccer_scorer, d, e['athlete']['displayName'], 'anytime_goal') == 'REFUSED'], [('761722', 'Kevin Pierre')])

check('anchor: away-cover NO ask = 1 - yes_bid', abs(r['alt']['kalshi']['ask'] - 0.50) < 1e-9, True)

print()
if failures:
    print(f'REGRESSION GATE: {len(failures)} FAILURES')
    sys.exit(1)
print('REGRESSION GATE: ALL PASS')
