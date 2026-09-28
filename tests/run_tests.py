#!/usr/bin/env python3
"""RIX core regression gate (stage 0 of the core merge, 9/27). Self-contained: adapters ->
build_manifest preview (isolated ledger) -> finals_watch grading suites. Exit 1 on any failure.
Run: python3 rix_tmp/tests/run_tests.py"""
import importlib.util, json, os, subprocess, sys, tempfile

HOME = '/home/sandbox'
SCRIPTS = f'{HOME}/rix_tmp/scripts'
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
    for i, c in enumerate(cands, 1): c['num'] = i
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
fw = load('fw', f'{SCRIPTS}/finals_watch.py')
_real = fw.fill_leak.card_price
fw.fill_leak.card_price = lambda pick: _real(pick, picks_path=LEDGER)

def P(eid, cents, odds, units, **kw):
    d = {'game': {'eid': eid}, 'kalshi': {'cents': cents}, 'odds': odds, 'units': units}
    d.update(kw); return d

# variant ledger rows for line/side/push variants of the published picks
variants = [
 {'kind':'pick','event_id':'401000001','market_class':'spread','side':'home','line':-7,'entry_c':52,'card_american':-110,'name':'t','units':'5u','card_ts':'x','kalshi_ticker':'T','commence':'c','preview':True},
 {'kind':'pick','event_id':'401000003','market_class':'total','side':'over','line':44,'entry_c':52,'card_american':-110,'name':'t','units':'5u','card_ts':'x','kalshi_ticker':'T','commence':'c','preview':True},
]
with open(LEDGER, 'a') as f:
    for v in variants: f.write(json.dumps(v) + '\n')
for label, want, pick, primary in [
    ('ml home win','W', P('401000010',71,-245,'10u',market_class='ml',side='home'), {'home_score':30,'away_score':20}),
    ('ml tie push','PUSH', P('401000010',71,-245,'10u',market_class='ml',side='home'), {'home_score':20,'away_score':20}),
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

check('anchor: away-cover NO ask = 1 - yes_bid', abs(r['alt']['kalshi']['ask'] - 0.50) < 1e-9, True)

print()
if failures:
    print(f'REGRESSION GATE: {len(failures)} FAILURES')
    sys.exit(1)
print('REGRESSION GATE: ALL PASS')
