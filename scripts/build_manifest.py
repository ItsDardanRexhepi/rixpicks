#!/usr/bin/env python3
"""Durable card manifest builder.
CARD PRICE BASIS. Owner ruling 2026-10-02 (1), relayed verbatim: "Card price is the ASK across ALL markets,
not just Kalshi - compare everywhere, take the ask." A candidate may carry a best_ask block
{venue, price, read_at, compared:[{venue, price, read_at}]} (venues as in RixPicksSystem scripts/hand/edge.py:
kalshi and poly in cents, the books dk fd mgm czr espnbet br fanatics b365 in American odds). The market must
still be on Kalshi: every candidate carries the kalshi block (ticker + cents), the eligibility test (J-122).
The card price is the cheapest cost to buy across kalshi.cents and every venue compared (a book's American
price as its implied probability; on equal cost the lower fee wins); card_american is that venue's own price,
card_source '<venue> ask at <read_at>', best_book the venue, and the edge is measured again from the fair
against that cost with that venue's own fee (the Kalshi taker fee only for Kalshi; Polymarket and the books 0).
The manifest pick (best_ask) and the ledger row (card_venue, card_read_at, card_compared) record the venue, its
read time and every venue compared. A NON-preview pick MUST carry a best_ask block (owner ruling 2026-10-02 (1):
build_manifest never silently ships a non-compared Kalshi price); the card refuses closed otherwise. Only a
--preview build may skip it and be priced Kalshi-only (card_american from the KALSHI ASK the gate consumed via
units.cents_to_american, card_source 'Kalshi ask at lock'). Either way the edge is measured from the fair against
the CARD price with the winning venue's fee, never a candidate's self-reported gross_c/net_c. Never book-consensus
display. Forward-only: previously published cards keep their published prices.
ONE LINE, ONE MARKET. A venue's quote prices one line: Kalshi lists half-point rungs and a book posts whole numbers
with a push, so a book's -3 is another market than Kalshi's 2.5 rung and can never be its best ask. On a spread,
total or prop candidate every quote from a venue other than Kalshi (each compared entry and the declared best_ask)
names its line, read from the picked side as the page's pick_line is ('Falcons +2.5' quotes +2.5, 'Under 54.5'
quotes 54.5), and that line must be the pick's own; a quote on a moneyline names none. The Kalshi quote is the kalshi
block's own market, so it names a line only optionally, and then the same one. A quote that breaks this refuses the
card (nothing written); the lines given ride into best_ask and its compared list.
Usage: build_manifest.py candidates.json out_manifest.json [--preview] [--meta meta.json]
candidate row: {num,name,side,away,home,commence,eid,espn_league,units,kalshi:{cents,team,url,ticker,[side]},model,gross_c,net_c,
                [best_ask:{venue,price,read_at,[line],compared:[{venue,price,read_at,[line]}...]}], [fragility]}
STANDING RULES ARE HARD GATES (owner ruling 2026-10-02 (4): "NO - an owner-approved card cannot break a standing
rule. Vegas rule, ladder sizes, all of it: hard gates, no exceptions."). The card refuses closed, nothing
written, on a pick on or against a Las Vegas team, units off the J-096 ladder, and on every standing bar:
fair (model) < 60c, card ask >= 85c, gross < 2c, net < 0.5c (ml) or < 2c (spread, total, prop), units other
than the J-096 rung of its fair and gross (60-69 = 5u; 70-79 = 10u with gross >= 3c else 5u; 80-89 = 15u;
90+ = 100u; fragility 2 one rung lower, fragility 3 refuses; tennis capped at 5u), a candidate missing model,
gross_c or net_c, and a parlay short of 2c gross and 2c net (ruling (2), 2-4 legs, J-098). Every violation on
the card is named in one refusal. An owner-forced sub-bar pick is impossible, and a status_note cannot carry
one. A candidate row carrying owner_directive, or an --owner-directive argument, is an error: the override no
longer exists.

PUBLICATION SHAPE (swamp rounds 4): a preview NEVER touches the production ledger - it writes
to picks.preview.jsonl. Production publication holds a single-writer flock, reads the ledger
INSIDE the lock, appends canonical rows, publishes the manifest via os.replace, then reads
back and verifies every appended row. Crash recovery: re-running with the same candidates is
idempotent (identical rows skip, manifest publishes); re-running with different candidates on
the same key refuses closed rather than forking the card record."""
import json, sys, datetime, os, fcntl, hashlib, math, re
import urllib.request as _urlreq
from zoneinfo import ZoneInfo
sys.path.insert(0, '/home/sandbox/rix_tmp')
from core.units import cents_to_american
from core.fill_leak import PICKS_LEDGER as _DEFAULT_PICKS_LEDGER
PICKS_LEDGER = os.environ.get('RIX_PICKS_LEDGER', _DEFAULT_PICKS_LEDGER)  # test-isolation hook

def _ikey(mc, side, obj):
    # Pick identity key. Props add player|market|line - multiple props share one game, so
    # eid|prop|side alone collides. Spread/total carry the line (alt lines must never collide).
    # ml keeps an empty 4th element.
    if mc == 'prop':
        np = re.sub(r'[^a-z0-9]', '', (obj.get('player') or '').lower())
        return (mc, side, f"{np}|{obj.get('market')}|{obj.get('line')}")
    if mc in ('spread', 'total'):
        return (mc, side, str(obj.get('line')))
    return (mc, side, '')

def _ikey(mc, side, obj):
    # Pick identity key. Props add player|market|line - multiple props share one game, so
    # eid|prop|side alone collides. Spread/total carry the line (alt lines must never collide).
    # ml keeps an empty 4th element.
    if mc == 'prop':
        np = re.sub(r'[^a-z0-9]', '', (obj.get('player') or '').lower())
        return (mc, side, f"{np}|{obj.get('market')}|{obj.get('line')}")
    if mc in ('spread', 'total'):
        return (mc, side, str(obj.get('line')))
    return (mc, side, '')


LEAGUE_KEY = {'baseball/mlb':'MLB','football/nfl':'NFL','football/college-football':'CFB',
              'basketball/wnba':'WNBA','basketball/nba':'NBA','hockey/nhl':'NHL',
              'soccer/usa.1':'MLS','mma/ufc':'UFC',
              # all-13 standard (lane 6, 2026-09-29): remaining config_leagues.json espn paths.
              # Boxing has espn:null (no espn_league to map); unknown slugs keep the loud
              # UPPER fallback below, never a silent wrong key.
              'basketball/mens-college-basketball':'NCAAB','soccer/usa.nwsl':'NWSL',
              'tennis/atp':'ATP','tennis/wta':'WTA','golf/pga':'PGA',
              'racing/nascar-premier':'NASCAR','racing/nascar':'NASCAR'}  # values must match config_leagues.json keys

def _pick_content_hash(m, legacy=False):
    # VERBATIM contract copy of build_gh_page.py's gate - declared hash must equal its computed hash.
    _EXCL_TOP={'num','result','_final','polycents','card_ts','line_shop','books','books_sp','prop_books'}
    # Sep 30 K23 drift kill: this copy had drifted from the builder's gate (missing the Sep 29
    # line-shop pricing-snapshot exclusions) - every lane manifest failed the page build closed.
    # scripts/test_hash_canon_parity.py now asserts all four copies hash identically.
    def _canon(p):
        c={k:v for k,v in p.items() if k not in _EXCL_TOP}
        if isinstance(c.get('kalshi'),dict):
            c['kalshi']={k:v for k,v in c['kalshi'].items() if k!='cents'}
        # polymarket(.us) cents = per-refresh price snapshots, excluded like kalshi.cents (mirror of the
        # builder); legacy=True is the canonicalization before that exclusion.
        if not legacy:
            for _pk in ('polymarket','polymarket_us'):
                if isinstance(c.get(_pk),dict):
                    c[_pk]={k:v for k,v in c[_pk].items() if k!='cents'}
        c.pop('dkp_note',None)
        if isinstance(c.get('dkp'),dict):
            c['dkp']={k:v for k,v in c['dkp'].items() if k not in ('team_cents','home_cents','away_cents','derived','harvested')}
            if not c['dkp']: c.pop('dkp')
        return c
    rows=sorted(json.dumps(_canon(p),sort_keys=True) for p in m.get('picks',[]))
    return hashlib.sha256('\n'.join(rows).encode()).hexdigest()

# OWNER RULES (RUNBOOK_daily_card 2.5 and 2.8), enforced where a card is assembled. The page
# builder (build_gh_page_v2.py and its twin) holds a landed card that breaks the Vegas rule or the ladder
# (exit 3, CARD HOLD); every other bar below is checked here, where the fair and the edge are known.
#  - Vegas (L-VEGAS-GATE-001, Sep 25): "never gamble on or against any Vegas teams ever" and
#    "Exclude A's going forward from today too". A pick in a game involving a Las Vegas team is
#    refused: Raiders (NFL), Golden Knights (NHL), Aces (WNBA), Athletics/A's (MLB), UNLV
#    (college), read by the vegas-rule contract block below (the page builder twins carry it byte
#    for byte): a league's nickname, home city or abbreviation as whole words anywhere in a team or
#    pick name, inside its own league, and 'Las Vegas', 'Vegas' or UNLV in any league (the league
#    is read case- and space-blind). Only a named non-Vegas team (Texas Tech Red Raiders filed
#    under the NFL) is let through. The rule is about teams: the individual sports (racing, golf,
#    tennis, MMA, boxing) skip it - a NASCAR race at Las Vegas Motor Speedway is no Vegas team -
#    and any other league, listed or not, keeps it.
#  - Units (J-096): 5u, 10u, 15u or 100u - no other size, and exactly the rung of the pick's fair and gross.
#  - The standing bars (RUNBOOK 2.3, J-096/J-097/J-098, owner rulings 2026-10-02 (1) and (2)): see bar_problems
#    and parlay_problems.
# All are hard gates (owner ruling 2026-10-02 (4): "an owner-approved card cannot break a standing rule
# ... hard gates, no exceptions"): a pick breaking any refuses the card closed before any write, and
# nothing overrides it. The old override (an owner_directive on the candidate row or an
# --owner-directive argument) is gone; either one given is an error, and its words are never printed.
UNIT_LADDER = (5, 10, 15, 100)
HARD_GATES = ('Vegas, the J-096 unit ladder and every standing bar are hard gates with no override (owner ruling '
              '2026-10-02 (4): an owner-approved card cannot break a standing rule): an owner-forced sub-bar pick is '
              'impossible, and a status_note cannot carry one')
REMOVED_FLAG = '--owner-directive'

# >>> vegas-rule contract copy (build_manifest.py and both page-builder twins carry this block byte for byte;
# scripts/test_vegas_rule_exact.py checks the copies and runs one case table through each)
# Owner rule L-VEGAS-GATE-001 (Sep 25): "never gamble on or against any Vegas teams ever" and "Exclude A's going
# forward from today too". A pick is out when any of its strings - game.away, game.home or the pick name, each
# read case-, space- and punctuation-blind - carries as whole words, anywhere in it:
#  - 'Las Vegas', 'Vegas' or 'UNLV': a team named for Las Vegas, or UNLV, is a Vegas team in every team league;
#  - or one of its league's Vegas words in _VEGAS_WORDS: the nickname (Raiders NFL, Golden Knights NHL, Aces WNBA,
#    Athletics/A's MLB), a home city the team has played under, or an abbreviation. A Vegas word counts only in its
#    own league: 'LV' is the Raiders in the NFL and the Aces in the WNBA, nothing in the NBA, and the Wright State
#    Raiders in college basketball are no Vegas team.
# Anywhere means anywhere: 'Raiders 1H +3.5', "A's F5 ML", 'Brock Bowers (LV) over 4.5 receptions', "Sacramento
# A's" and 'Golden Knights (VGK)' all count. The one way out is by name: each non-Vegas team in _VEGAS_NOT (Texas
# Tech Red Raiders, Evansville Purple Aces, UCF Golden Knights, ...) is blanked out of a string before it is read,
# so that team filed under the nickname's league builds, while any other Vegas word in the same string still holds
# the pick. Nothing else ever narrows the rule. An entry there is a whole multi-word team name, never a Vegas word
# on its own, and never carries 'Vegas', 'Las Vegas' or 'UNLV'.
# The individual sports (racing, golf, tennis, MMA, boxing) have no teams: a NASCAR race at Las Vegas Motor
# Speedway is no Vegas team. The league is read case- and space-blind ('Hockey/NHL ' is the NHL).
_VEGAS_WORDS = {
    'football/nfl': ('raiders', 'oakland', 'lv'),
    'hockey/nhl': ('golden knights', 'vgk'),
    'basketball/wnba': ('aces', 'lv', 'lva'),
    'baseball/mlb': ('athletics', "a's", 'oakland', 'sacramento', 'ath', 'oak'),
}
_VEGAS_CITY = ('las vegas', 'vegas', 'unlv')
_VEGAS_NOT = ('red raiders', 'colgate raiders', 'wright state raiders', 'purple aces', 'ucf golden knights',
              'clarkson golden knights')
_VEGAS_NO_TEAMS = ('racing', 'golf', 'tennis', 'mma', 'boxing')


def _vg_words(s):
    """' <words> ': lower-cased, each run of characters other than a-z, 0-9 and the apostrophe one space."""
    return ' ' + re.sub(r"[^a-z0-9']+", ' ', str(s or '').lower().replace('\u2019', "'")) + ' '


def vegas_hit_fields(league, fields):
    """'<field> <value>' for the first (field, value) that puts a Las Vegas team on this pick, else None."""
    lg = str(league or '').strip().lower()
    if lg.split('/')[0] in _VEGAS_NO_TEAMS:
        return None
    for f, v in fields:
        w = _vg_words(v)
        for n in _VEGAS_NOT:
            while f' {n} ' in w:
                w = w.replace(f' {n} ', ' ')
        if any(f' {n} ' in w for n in _VEGAS_CITY + _VEGAS_WORDS.get(lg, ())):
            return f'{f} {v!r}'
    return None
# <<< vegas-rule contract copy

def vegas_hit(c):
    """Which field puts a Las Vegas team on this candidate (on it or against it), else None."""
    return vegas_hit_fields(c.get('espn_league'), [(f, c.get(f)) for f in ('home', 'away', 'name')])


def units_rung(u):
    """The J-096 rung a units value names (5u -> 5), else None."""
    if isinstance(u, bool):
        return None
    if isinstance(u, (int, float)):
        v = float(u)
    else:
        m = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*u?\s*', str(u or ''), re.I)
        if not m:
            return None
        v = float(m.group(1))
    return int(v) if v in UNIT_LADDER else None

# ---- the card price: the best ask across venues (owner ruling 2026-10-02 (1)) ----
# venue key -> (name as best_book and card_source spell it - the page builder's chip names, so the best-line
# star lands on that venue's chip - and kind). Keys and aliases are RixPicksSystem scripts/hand/edge.py's.
VENUES = {'kalshi': ('Kalshi', 'exchange'), 'poly': ('Polymarket', 'exchange'),
          'dk': ('DraftKings', 'book'), 'fd': ('FanDuel', 'book'), 'mgm': ('BetMGM', 'book'), 'czr': ('Caesars', 'book'),
          'espnbet': ('theScore', 'book'), 'br': ('BetRivers', 'book'), 'fanatics': ('Fanatics', 'book'),
          'b365': ('bet365', 'book')}
VENUE_ALIASES = {'polymarket': 'poly', 'draftkings': 'dk', 'fanduel': 'fd', 'betmgm': 'mgm', 'caesars': 'czr',
                 'betrivers': 'br', 'bet365': 'b365'}
_VENUE_ORDER = list(VENUES)

def kalshi_fee_c(ask_c):
    """Kalshi taker fee in cents per contract, 0.07 x ask x (1 - ask) (st_fair.fee, edge.py fee_c)."""
    a = ask_c / 100
    return 7 * a * (1 - a)

def _real(v):
    """A finite int or float (never a bool or a string), as float, else None."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None
    return float(v)

def _read_time(s, where):
    if s is None:
        return None
    try:
        t = datetime.datetime.fromisoformat(str(s).replace('Z', '+00:00')) if isinstance(s, str) else None
    except ValueError:
        t = None
    if t is None or t.tzinfo is None:
        raise ValueError(f"{where}.read_at {s!r} is not ISO 8601 with a zone (e.g. 2026-10-02T14:51Z)")
    return s

def venue_quote(q, where):
    """{venue, price, read_at} -> its cost to buy: {venue, name, price, read_at, cost_c, fee_c, american}.
    An exchange (kalshi, poly) quotes cents 1-99; a book quotes whole American odds (>= +100 or <= -101)."""
    if not isinstance(q, dict):
        raise ValueError(f'{where}: not an object {{venue, price, read_at}}')
    raw = str(q.get('venue') or '').strip().lower()
    v = VENUE_ALIASES.get(raw, raw)
    if v not in VENUES:
        raise ValueError(f"{where}: unknown venue {q.get('venue')!r} (known: {', '.join(VENUES)})")
    name, kind = VENUES[v]
    price = q.get('price')
    if kind == 'exchange':
        c = _real(price)
        if c is None or not 1 <= c <= 99:
            raise ValueError(f'{where}: a {v} ask is cents from 1 to 99, got {price!r}')
        cost, fee, am = c, (kalshi_fee_c(c) if v == 'kalshi' else 0.0), cents_to_american(c)
    else:
        am = price if type(price) is int else (int(price) if isinstance(price, str) and re.fullmatch(r'\s*[+-]?\d+\s*', price) else None)
        if am is None or not (am >= 100 or am <= -101):
            raise ValueError(f'{where}: a {v} price is whole American odds as quoted (-162, +150), got {price!r}')
        cost, fee, price = (100 * -am / (-am + 100) if am < 0 else 100 * 100 / (am + 100)), 0.0, am
    return {'venue': v, 'name': name, 'price': price, 'read_at': _read_time(q.get('read_at'), where),
            'cost_c': cost, 'fee_c': fee, 'american': am}

def pick_side_line(c):
    """The candidate's own line read from its picked side, the page builder's pick_line: a spread's line is the HOME
    spread, so an away pick reads -line and a home pick line; a total's or a prop's line is the number itself. None
    when it cannot be read (a moneyline has no line; a spread side other than home/away)."""
    mc, ln = c.get('market_class'), _real(c.get('line'))
    if isinstance(c.get('line'), str):
        try: ln = _real(float(c['line']))
        except ValueError: ln = None
    if ln is None: return None
    if mc == 'spread' and c.get('side') in ('home', 'away'): return (0.0 - ln) if c['side'] == 'away' else ln
    if mc in ('total', 'prop'): return ln
    return None

def quote_line_problem(c, q, v):
    """Why one best_ask quote (venue key v) is not a quote of the pick's own line (ONE LINE, ONE MARKET above),
    else None."""
    mc = c.get('market_class')
    given = isinstance(q, dict) and q.get('line') is not None
    if mc not in ('spread', 'total', 'prop'):
        return f"a {v} quote at line {q['line']!r} is another market than a moneyline (a moneyline quote names no line)" if given else None
    if not given:
        if v == 'kalshi': return None  # the kalshi block's own market
        return (f"a {v} quote on a {mc} pick names no line: it must name the picked side's line ('Falcons +2.5' quotes +2.5) - "
                f"a book's -3 is another market than Kalshi's 2.5 rung, never its best ask")
    ql = _real(q['line'])
    if ql is None: return f"{v} line {q['line']!r} is not a number"
    own = pick_side_line(c)
    fmt = (lambda x: f'{x:+g}') if mc == 'spread' else (lambda x: f'{x:g}')
    if own is None:
        return f"the pick's own line cannot be read (line {c.get('line')!r}, side {c.get('side')!r}) to bind a {v} quote at {fmt(ql)}"
    if abs(ql - own) > 1e-9:
        return (f"a {v} quote at line {fmt(ql)} is another market than the pick's own {fmt(own)} - one line, one market: "
                f"a book's -3 is never the best ask of Kalshi's 2.5 rung")
    return None

def price_card(c):
    """The card price of one candidate: the cheapest ask to buy across Kalshi and every venue its best_ask
    block compared (owner ruling 2026-10-02 (1)). ValueError on anything that cannot be trusted."""
    k = c.get('kalshi')
    if not isinstance(k, dict):
        raise ValueError('no kalshi block: the market must be on Kalshi (J-122) - a book-only market never cards')
    if not isinstance(k.get('ticker'), str) or not k['ticker'].strip():
        raise ValueError('the kalshi block has no ticker: the market must be on Kalshi (J-122)')
    if 'side' in k and k['side'] not in ('yes', 'no'):
        # explicit side (an Under is the NO side of an Over market): kalshi.cents is THAT side's ask, and the
        # page builder prices the exact market ticker from it. Anything but yes|no is refused, never guessed.
        raise ValueError(f"kalshi side {k['side']!r}: an explicit side is 'yes' or 'no'")
    cents = k.get('cents')
    if type(cents) is not int or not (1 <= cents <= 99):  # strict: bool is not int here
        raise ValueError(f'bad kalshi cents {cents!r}')
    kal = venue_quote({'venue': 'kalshi', 'price': cents}, 'kalshi')
    ba = c.get('best_ask')
    if ba is None:
        return dict(kal, legacy=True, compared=None)
    if not isinstance(ba, dict):
        raise ValueError('best_ask is not an object {venue, price, read_at, compared}')
    comp = ba.get('compared')
    if not isinstance(comp, list):
        raise ValueError('best_ask.compared must list every venue read, [{venue, price, read_at}, ...]')
    pool, seen = {'kalshi': kal}, set()
    for i, q in enumerate(comp + [ba]):
        declared = i == len(comp)
        where = 'best_ask' if declared else f'best_ask.compared[{i}]'
        qq = venue_quote({'venue': q.get('venue'), 'price': q.get('price'), 'read_at': q.get('read_at')}
                         if isinstance(q, dict) else q, where)
        v = qq['venue']
        if not declared:
            if v in seen:
                raise ValueError(f'{where}: venue {v} compared twice - one ask per venue for one market')
            seen.add(v)
        if v == 'kalshi' and qq['cost_c'] != cents:
            raise ValueError(f"{where}: the Kalshi ask {qq['price']!r} is not the kalshi block's {cents}c")
        lp = quote_line_problem(c, q, v)
        if lp:
            raise ValueError(f'{where}: {lp}')
        if isinstance(q, dict) and q.get('line') is not None:
            qq['line'] = q['line']  # checked: the pick's own line
        have = pool.get(v)
        if have is None:
            pool[v] = qq
            continue
        if have['cost_c'] != qq['cost_c']:
            raise ValueError(f"{where}: {v} at {qq['price']!r} disagrees with {v} at {have['price']!r} in compared")
        if have['read_at'] and qq['read_at'] and have['read_at'] != qq['read_at']:
            raise ValueError(f"{where}: {v} read at {qq['read_at']!r} disagrees with {have['read_at']!r} in compared")
        have['read_at'] = have['read_at'] or qq['read_at']
        if have.get('line') is None and qq.get('line') is not None: have['line'] = qq['line']
    ranked = sorted(pool.values(), key=lambda q: (q['cost_c'], q['fee_c'], _VENUE_ORDER.index(q['venue'])))
    best = ranked[0]
    named = VENUE_ALIASES.get(str(ba.get('venue') or '').strip().lower(), str(ba.get('venue') or '').strip().lower())
    if named != best['venue']:
        raise ValueError(f"best_ask names {named} ({pool[named]['cost_c']:.2f}c to buy) but {best['venue']} is cheaper "
                         f"({best['cost_c']:.2f}c) - the card price is the cheapest ask")
    if not best['read_at']:
        raise ValueError(f"best_ask.read_at is missing: record when the {best['venue']} ask was read (owner ruling 2026-10-02 (1))")
    return dict(best, legacy=False, compared=[{'venue': q['venue'], 'price': q['price'], 'read_at': q['read_at'],
                                               **({'line': q['line']} if q.get('line') is not None else {})} for q in ranked])

# ---- the standing bars (RUNBOOK 2.3, J-096/J-097/J-098, owner rulings 2026-10-02) ----
CARD_BAND_C, ASK_CUT_C, GROSS_BAR_C = 60, 85, 2.0
NET_BAR_C = {'ml': 0.5}  # spread, total and prop: 2c
_RUNG_DOWN = {100: 15, 15: 10, 10: 5, 5: 5}  # fragility 2: one rung lower (5u is the lowest card rung)

def j096_rung(fair_c, gross_c):
    """J-096: 60-69 = 5u, 70-79 = 10u when gross >= 3c else 5u, 80-89 = 15u, 90+ = 100u; below 60, 0."""
    if fair_c >= 90: return 100
    if fair_c >= 80: return 15
    if fair_c >= 70: return 10 if gross_c >= 3 else 5
    if fair_c >= 60: return 5
    return 0

def _c(x):
    return f'{round(x, 2):g}c'

def bar_problems(c, pr):
    """Every standing bar this pick fails, at its card price pr (price_card)."""
    vals = {k: _real(c.get(k)) for k in ('model', 'gross_c', 'net_c')}
    missing = [k for k, v in vals.items() if v is None]
    if missing:
        return [f"missing {', '.join(missing)} (a number each): a pick carries its fair and its gross and net edge, "
                'or it cannot be checked against the bars']
    fair = vals['model']
    # ruling (1)/(4): the edge is ALWAYS measured from the fair against the CARD price (the best ask, or the
    # Kalshi ask on a preview-only legacy pick), with the winning venue's own fee - never the candidate's
    # self-reported gross_c/net_c. The J-096 rung below is computed from that fair and gross.
    gross, net = round(fair - pr['cost_c'], 6), round(fair - pr['cost_c'] - pr['fee_c'], 6)
    mc = c.get('market_class')
    net_bar = NET_BAR_C.get(mc, 2.0)
    out = []
    if fair < CARD_BAND_C:
        out.append(f'fair {_c(fair)} below the {CARD_BAND_C}c card band')
    if pr['cost_c'] >= ASK_CUT_C:
        out.append(f"card ask {_c(pr['cost_c'])} at or above the {ASK_CUT_C}c cut")
    if gross < GROSS_BAR_C:
        out.append(f'gross {_c(gross)} below the 2c bar')
    if net < net_bar:
        out.append(f"net {_c(net)} below the {net_bar:g}c {'ml' if mc == 'ml' else 'spread/total/prop'} bar")
    frag = c.get('fragility')
    if frag is not None and (type(frag) is not int or frag < 0):
        out.append(f'fragility {frag!r} is not a whole number from 0 (J-097)')
        frag = None
    if frag is not None and frag >= 3:
        out.append(f'fragility {frag} refuses the pick (J-097)')
    rung = j096_rung(fair, gross)
    if rung and units_rung(c.get('units')) is not None and not (frag is not None and frag >= 3):
        notes = []
        if frag == 2:
            rung = _RUNG_DOWN[rung]; notes.append('fragility 2: one rung lower')
        if str(c.get('espn_league') or '').split('/')[0] == 'tennis' and rung > 5:
            rung = 5; notes.append('tennis capped at 5u')
        want = f'{rung}u'
        if units_rung(c.get('units')) != rung:
            out.append(f"units {c.get('units')!r} is not the J-096 rung {want} (fair {_c(fair)}, gross {_c(gross)}"
                       + ''.join('; ' + n for n in notes) + ')')
        elif c.get('units') != want:
            out.append(f"units {c.get('units')!r} must be written {want!r}")
    return out

def parlay_problems(parlay, cands, priced):
    """Ruling (2): a parlay clears 2c gross and 2c net, 2-4 legs (J-098), every leg one pick on this card. Price =
    the cheaper of the product of the legs' card prices (each leg paying its own venue fee) and parlay.best_ask."""
    if parlay in (None, {}):
        return []
    legs = parlay.get('legs') if isinstance(parlay, dict) else None
    if not isinstance(legs, list) or len(legs) < 2 or not all(isinstance(x, str) and x for x in legs):
        return [f'a parlay needs 2-4 named legs (J-098), got {legs!r} - set parlay to null for no parlay']
    out = []
    if len(set(legs)) != len(legs):
        out.append(f'duplicate legs {legs}')
    if len(legs) > 4:
        out.append(f'{len(legs)} legs: J-098 allows 2-4')
    picked = []
    for leg in legs:
        hits = [i for i, c in enumerate(cands) if c.get('name') == leg]
        if len(hits) != 1:
            out.append(f"leg {leg!r} is {'not a pick' if not hits else 'more than one pick'} on this card")
        else:
            picked.append(hits[0])
    if out:
        return out
        # J-098: parlay legs must be independent - no same-game or shared-team legs
    _by_eid = {}
    for i in picked:
        _by_eid.setdefault(cands[i].get('eid'), []).append(cands[i].get('name'))
    for _e, _ns in _by_eid.items():
        if len(_ns) > 1:
            out.append(f'same-game legs need a joint fair: {", ".join(_ns)} (J-098)')
    _mkt = {'ml', 'over', 'under', '1h', 'f5', 'q1', 'p1', 'reg', 'to'}
    _by_team = {}
    for i in picked:
        _team_toks = []
        for _tok in str(cands[i].get('name') or '').split():
            _num = _tok.lstrip('+-')
            if _tok.lower() in _mkt or (_num[:1].isdigit() and all(c.isdigit() or c == '.' for c in _num)):
                break
            _team_toks.append(_tok)
        _team = ' '.join(_team_toks)
        if _team:
            _by_team.setdefault(_team, []).append(cands[i].get('name'))
    for _tm, _ns in _by_team.items():
        if len(_ns) > 1:
            out.append(f'shared-team legs are not independent: {", ".join(_ns)} (J-098)')
    dec, all_in, fair = 1.0, 1.0, 1.0
    for i in picked:
        am, fee = priced[i]['american'], priced[i]['fee_c']
        d = (1 + 100 / abs(am)) if am < 0 else (1 + am / 100)
        dec *= d; all_in *= (100 / d + fee) / 100; fair *= _real(cands[i].get('model')) / 100
    best = {'cost_c': 100 / dec, 'fee_c': 100 * all_in - 100 / dec, 'what': "the product of the legs' card prices"}
    q = parlay.get('best_ask')
    if q is not None:
        try:
            qq = venue_quote(q, 'parlay.best_ask')
        except ValueError as e:
            return [str(e)]
        if not qq['read_at']:
            return [f"parlay.best_ask.read_at is missing: record when the {qq['venue']} parlay price was read"]
        if (qq['cost_c'], qq['fee_c']) < (best['cost_c'], best['fee_c']):
            best = dict(qq, what=f"the {qq['name']} parlay price {qq['american']:+d}")
    gross = round(100 * fair - best['cost_c'], 6); net = round(gross - best['fee_c'], 6)
    for what, v in (('gross', gross), ('net', net)):
        if v < 2:
            out.append(f"{what} {_c(v)} below the 2c parlay bar (combined fair {_c(100 * fair)} against {best['what']}, "
                       f"{_c(best['cost_c'])} to buy, fee {_c(best['fee_c'])})")
    return out

_SUB_BAR_NOTE = re.compile(r'owner[\s_-]*directive|sub[\s_-]*bar', re.I)

def owner_rules_gate(cands, argv, parlay=None, status_note=None, preview=False):
    """Refuse closed (ValueError, nothing written) on any pick that breaks an owner rule or a standing bar, on a
    parlay short of its bar, on a status_note announcing a sub-bar card, on any owner-directive override
    (removed: owner ruling 2026-10-02), on a non-preview pick with no best_ask block (owner ruling 2026-10-02
    (1): the card price is the best ask compared across venues, never a silently non-compared Kalshi price), or
    on two picks sharing a num. Returns each candidate's card price."""
    # never echo the argument or the field: they were meant to carry his words
    if any(a == REMOVED_FLAG or a.startswith(REMOVED_FLAG + '=') for a in argv):
        raise ValueError(f'fail closed: {REMOVED_FLAG} does not exist - {HARD_GATES}')
    # a pick num names exactly one pick on the card
    _nums = [c.get('num') for c in cands]
    _shared = sorted({repr(n) for n in _nums if _nums.count(n) > 1})
    if _shared:
        raise ValueError(f"fail closed: pick num {', '.join(_shared)} is on more than one candidate - a pick num names one pick")
    problems, priced = [], []
    for c in cands:
        if 'owner_directive' in c:
            problems.append(f"#{c.get('num')} {c.get('name')}: owner_directive is not accepted")
            priced.append(None)
            continue
        broken = []
        v = vegas_hit(c)
        if v:
            broken.append(f'Las Vegas team ({v}): never on or against a Vegas team')
        if units_rung(c.get('units')) is None:
            broken.append(f"units {c.get('units')!r} not on the J-096 ladder (5u, 10u, 15u, 100u)")
        try:
            pr = price_card(c)
        except ValueError as e:
            pr = None
            broken.append(f'card price: {e}')
        priced.append(pr)
        if pr is not None:
            if not preview and pr['legacy']:
                broken.append('no best_ask block: a non-preview card price must be the best ask compared across '
                              'venues (best_ask {venue, price, read_at, compared}) whose cheapest-to-buy is the card '
                              'price (owner ruling 2026-10-02 (1)); only a --preview build may ship a Kalshi-only price')
            broken += bar_problems(c, pr)
        if broken:
            problems.append(f"#{c.get('num')} {c.get('name')}: " + '; '.join(broken))
    if not problems:
        problems += [f'parlay: {p}' for p in parlay_problems(parlay, cands, priced)]
    if isinstance(status_note, str) and _SUB_BAR_NOTE.search(status_note):
        problems.append('status_note announces an owner-directive or sub-bar pick: a status_note cannot carry a sub-bar card')
    if problems:
        raise ValueError('fail closed (standing rules, runbook 2.3/2.5/2.8): ' + ' | '.join(problems) + f' - {HARD_GATES}')
    return priced

PROD_MANIFEST_PATH = os.environ.get('RIX_PROD_MANIFEST', '/home/sandbox/rix_tmp/manifest.json')  # env override = test-isolation hook (same pattern as RIX_PICKS_LEDGER); non-preview publishes mirror here (Sep 29 stale-grader fix)

PREVIEW_LEDGER = PICKS_LEDGER.replace('picks.jsonl', 'picks.preview.jsonl')
LOCK_PATH = PICKS_LEDGER + '.lock'


# K19 root fix (MMA eid, 2026-09-30): ESPN MMA scoreboard events ARE the fight cards, so
# game.eid for mma/ufc picks is the CARD event id (ceid) - the page's ceid fail-safe keys on
# it. Resolve from the mma/ufc scoreboard by fighter-pair match across EVERY competition of
# every event (fights, not just [0]); competitors are athletes, not teams. FAIL-CLOSED loud
# when no unique match - same standard as st_card_candidates.resolve_eid. Manual/other-lane
# rows arrive with eid null (the adapter skips MMA fail-closed upstream); this is the single
# assembly-point backstop that covers every lane.
_MMA_SB_CACHE = {}
def _mma_ceid(c):
    ymd = datetime.datetime.fromisoformat(c['commence'].replace('Z', '+00:00')).astimezone(ZoneInfo('America/Los_Angeles')).strftime('%Y%m%d')
    if ymd not in _MMA_SB_CACHE:
        _req = _urlreq.Request(
            f'https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard?dates={ymd}&limit=200',
            headers={'User-Agent': 'python-urllib/3.10'})
        with _urlreq.urlopen(_req, timeout=20) as _r:
            _MMA_SB_CACHE[ymd] = json.load(_r).get('events', [])
    _a, _h = (c.get('away') or '').casefold(), (c.get('home') or '').casefold()
    hits = []
    for _ev in _MMA_SB_CACHE[ymd]:
        for _comp in _ev.get('competitions', []):
            _names = {(((_x.get('athlete') or _x.get('team') or {}).get('displayName')) or '').casefold()
                      for _x in _comp.get('competitors', [])}
            if _a in _names and _h in _names:
                hits.append(_ev.get('id'))
                break
    _uniq = list(dict.fromkeys(hits))
    return _uniq[0] if len(_uniq) == 1 else None

def card_date_of(picks):
    """The builder's _card_date_of (record_final.card_date_of is the same rule): a card's date is the
    most common PT game date across its picks, so a game starting after PT midnight stays on the card
    it was published with, whatever order the candidates came in. None when no pick has a
    timezone-aware commence."""
    from collections import Counter
    ds = []
    for p in picks:
        try:
            dt = datetime.datetime.fromisoformat(str((p.get('game') or {}).get('commence') or '').replace('Z', '+00:00'))
        except ValueError:
            continue
        if dt.tzinfo is not None:
            ds.append(dt.astimezone(ZoneInfo('America/Los_Angeles')).date().isoformat())
    return Counter(ds).most_common(1)[0][0] if ds else None

def posted_at_of(picks, now_utc):
    """posted_at (UTC ISO) of a production card: the newest card_ts across its picks. card_ts is each
    pick's first lock (ledger -> production manifest -> this build), so for a new card this is the
    build time, a regeneration keeps it (never restamped), and a pick added later moves it to that
    pick's own lock - no pick ever claims a lock from before it was carded. The page builder prefers
    posted_at and marks a game that began before it "after start" instead of "locked". An unreadable
    or zoneless card_ts counts as this build."""
    newest = None
    for p in picks:
        try:
            dt = datetime.datetime.fromisoformat(str(p.get('card_ts') or '').replace('Z', '+00:00'))
        except ValueError:
            dt = None
        if dt is None or dt.tzinfo is None:
            dt = now_utc
        newest = dt if newest is None or dt > newest else newest
    return (newest or now_utc).astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def _card_venue_fields(p, compared=True):
    """Ledger fields of a best-ask card price (ruling (1)): the venue, its read time and (on the row) every venue
    compared. A Kalshi-priced pick with no best_ask block adds none, so its row is exactly as before."""
    ba = p.get('best_ask')
    if not ba:
        return {}
    return {'card_venue': ba['venue'], 'card_read_at': ba['read_at'], **({'card_compared': ba['compared']} if compared else {})}

def main():
    cands = json.load(open(sys.argv[1]))
    preview = '--preview' in sys.argv
    out = sys.argv[2] if not sys.argv[2].startswith('--') else sys.argv[3]
    meta = {}
    if '--meta' in sys.argv:
        meta = json.load(open(sys.argv[sys.argv.index('--meta')+1]))
    # the production manifest a field not in --meta inherits from (read only; a preview inherits nothing)
    inherit = {}
    if not preview and os.path.exists(PROD_MANIFEST_PATH):
        try: inherit = json.load(open(PROD_MANIFEST_PATH))
        except Exception: inherit = {}
    parlay = meta.get('parlay', inherit.get('parlay'))
    status_note = meta['status_note'] if 'status_note' in meta else inherit.get('status_note')
    # every standing rule and bar, before any lookup or write; each candidate's card price (ruling (1))
    priced = owner_rules_gate(cands, sys.argv, parlay=parlay, status_note=status_note, preview=preview)
    now_utc = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    now = now_utc.astimezone(ZoneInfo('America/Los_Angeles')).isoformat(timespec='seconds')
    ledger = PREVIEW_LEDGER if preview else PICKS_LEDGER
    # card_ts canon (restamp fork fix, third surfacing): card_ts is the FIRST-LOCK time and must
    # never be restamped on regeneration. Resolve per pick: existing canonical ledger row card_ts ->
    # production manifest pick card_ts -> `now` ONLY for a genuinely new lock. Never a literal.
    _ts_map = {}
    if not preview and os.path.exists(PICKS_LEDGER):
        for _l in open(PICKS_LEDGER):
            try: _r = json.loads(_l)
            except Exception: continue
            if _r.get('kind') == 'pick' and _r.get('card_ts'):
                _ts_map[(str(_r.get('event_id')),) + _ikey(_r.get('market_class','ml'), _r.get('side'), _r)] = _r['card_ts']
    _prod_ts = {}
    if not preview and os.path.exists(PROD_MANIFEST_PATH):
        try:
            for _p in json.load(open(PROD_MANIFEST_PATH)).get('picks', []):
                _g = _p.get('game') or {}
                if _p.get('card_ts') and _g.get('eid'):
                    _prod_ts[(str(_g['eid']),) + _ikey(_p.get('market_class', 'ml'), _p.get('side'), _p)] = _p['card_ts']
        except Exception: pass
    picks = []
    for c in cands:
        # market-class gate (s/t wired 9/27): ml | spread | total are buildable end to end
        # (finals_watch grades all three incl. push; fill_leak is market-class-aware). Refuse
        # anything without an explicit, known class; spread/total MUST carry a numeric line.
        mc = c.get('market_class')
        if c.get('espn_league') == 'mma/ufc' and not c.get('eid'):
            _ce = _mma_ceid(c)
            if not _ce:
                raise ValueError(f"fail closed: MMA candidate {c.get('name')} has no unique ESPN fight-card eid on the mma/ufc scoreboard (fighter-pair match across all competitions)")
            c['eid'] = str(_ce)  # in-place: the ledger key pass below re-reads cands
        if mc not in ('ml', 'spread', 'total', 'prop'):
            raise ValueError(f"fail closed: candidate {c.get('name')} has market_class={mc!r} - must be explicit ml|spread|total|prop")
        if mc in ('spread', 'total', 'prop'):
            try:
                float(c.get('line'))
            except (TypeError, ValueError):
                raise ValueError(f"fail closed: {mc} candidate {c.get('name')} missing numeric line")
        if mc == 'prop':
            # props-on-card wiring 9/27: player + verified-gradeable market required;
            # keep in sync with finals_watch.PROP_STAT_KEYS + specials.
            if not (c.get('player') or '').strip():
                raise ValueError(f"fail closed: prop candidate {c.get('name')} missing player")
            gradeable = {'passing_yards','pass_td','rushing_yards','rush_attempts','receiving_yards',
                         'receptions','reception_tds','rush_tds','points','rebounds','assists','threes',
                         'goals','shots_on_goal','saves','blocked_shots','anytime_td','hockey_points',
                         # MLB + soccer grading shipped 9/27 - keep in sync with finals_watch
                         'bat_hits','bat_home_runs','bat_rbis','bat_runs','bat_walks','bat_strikeouts',
                         'pit_strikeouts','pit_hits_allowed','pit_walks','pit_outs','pit_earned_runs',
                         'anytime_goal','first_goal','last_goal'}
            if c.get('market') not in gradeable:
                raise ValueError(f"fail closed: prop candidate {c.get('name')} market {c.get('market')!r} not in the verified gradeable map")
            if c.get('side') not in ('over', 'under'):
                raise ValueError(f"fail closed: prop candidate {c.get('name')} side {c.get('side')!r} - must be over|under")
        cents = c['kalshi']['cents']  # checked (strict int 1-99, bool refused) by the gate's price_card
        pr = priced[len(picks)]
        am = pr['american']  # the card price: the best ask (ruling (1)); the Kalshi ask when no best_ask block
        picks.append({
            'num': c['num'], 'name': c['name'],
            'market_class': mc,
            **({'line': c['line']} if mc in ('spread', 'total', 'prop') else {}),
            **({'player': c['player'], 'market': c['market']} if mc == 'prop' else {}),
            'sub': f"{c.get('sub_context','')} - model {c['model']:.1f}".strip(' -'),
            'odds': f"{am:+d}", 'units': c['units'], 'side': c['side'],
            'game': {'away': c['away'], 'home': c['home'], 'commence': c['commence'], 'eid': c['eid']},
            'espn_league': c['espn_league'],
            'league': LEAGUE_KEY.get(c['espn_league'], c['espn_league'].split('/')[-1].upper()),  # refresh.sh SPORTS derivation reads p['league'] (config_leagues.json key) - Sep 27: NFL/WNBA got zero prefill when this was absent
            'best_book': pr['name'],
            'kalshi': {'url': c['kalshi'].get('url') or 'https://kalshi.com/markets/{}/{}'.format(c['kalshi']['ticker'].split('-')[0].lower(), c['kalshi']['ticker'].rsplit('-',1)[0].lower()),  # event-level URL: build_gh_page resolves the gate via the LAST segment (event ticker)
                       'cents': cents, 'team': c['kalshi']['team'], 'gate_cents': cents,
                       'ticker': c['kalshi']['ticker'],
                       **({'side': c['kalshi']['side']} if 'side' in c['kalshi'] else {})},  # explicit market side (yes|no): build_gh_page prices that side's ask
            'card_american': am,
            'card_source': 'Kalshi ask at lock' if pr['legacy'] else f"{pr['name']} ask at {pr['read_at']}",
            # ruling (1): the venue, its read time, every venue compared and the edge against that price
            **({} if pr['legacy'] else {'best_ask': {
                'venue': pr['venue'], 'price': pr['price'], 'read_at': pr['read_at'],
                **({'line': pr['line']} if pr.get('line') is not None else {}),  # one line, one market (checked in price_card)
                'cost_c': round(pr['cost_c'], 2), 'fee_c': round(pr['fee_c'], 2),
                'gross_c': round(c['model'] - pr['cost_c'], 2), 'net_c': round(c['model'] - pr['cost_c'] - pr['fee_c'], 2),
                'compared': pr['compared']}}),
            'card_ts': _ts_map.get((str(c['eid']),) + _ikey(mc, c['side'], c))
                       or _prod_ts.get((str(c['eid']),) + _ikey(mc, c['side'], c))
                       or now,  # first lock only; regenerations inherit, never restamp
            'polymarket': c.get('polymarket'), 'dkp': c.get('dkp')})
    # FULL MANIFEST CONTRACT (swamp round 8): build_gh_page.py (publish.yml publish path) reads
    # date_label, status_note, record, updated, units_pl, units_ledger, yesterday, parlay and
    # verifies pick_content_hash against its own canonicalization. Metadata comes from --meta
    # (pipeline-supplied, record tab canonical per J-100) with inherit-from-production fallback;
    # a required field available from neither fails closed - the record is never invented.
    # the card date is the builder's rule (most common PT game date), never cands[0]['date']: a card
    # whose first-listed pick starts after PT midnight was dated a day late and every grade refused
    date_s = card_date_of(picks) if picks else None
    if picks and not date_s:
        raise ValueError('fail closed: no pick has a timezone-aware commence - the card date (most common PT game date) cannot be set')
    if cands and cands[0].get('date') and cands[0].get('date') != date_s:
        print(f"card date {date_s} (most common PT game date across {len(picks)} picks), not the first candidate's {cands[0].get('date')}")
    dpt = datetime.datetime.now(ZoneInfo('America/Los_Angeles'))
    try:
        dlab = datetime.datetime.strptime(date_s, '%Y-%m-%d').strftime('%A, %b %-d') if date_s else dpt.strftime('%A, %b %-d')
    except Exception:
        dlab = dpt.strftime('%A, %b %-d')
    def _field(name, required=True):
        if name in meta: return meta[name]
        if name in inherit: return inherit[name]
        if required: raise ValueError(f"fail closed: manifest metadata '{name}' missing from --meta and no readable production manifest to inherit from")
        return None
    manifest = {
        'date': date_s, 'date_label': meta.get('date_label', dlab),
        'updated': meta.get('updated', dpt.strftime('%b %-d, %-I:%M %p PT')),
        # an empty card has no pick to lock: no posted_at (the day's game pages are the last card's)
        **({} if preview or not picks else {'posted_at': posted_at_of(picks, now_utc)}),
        'record': _field('record'), 'units_pl': _field('units_pl'),
        'units_ledger': _field('units_ledger', required=False),
        'yesterday': _field('yesterday', required=False),
        'status_note': _field('status_note', required=False),
        'parlay': parlay,
        'built_by': 'build_manifest',
        'preview': preview, 'picks': picks}
    manifest['pick_content_hash'] = _pick_content_hash(manifest)
    manifest['lock_ref'] = LOCK_PATH

    # Single-writer lock: held across read-decide-stage-publish-verify so concurrent builds
    # can never both read the pre-publish ledger and duplicate a canonical row.
    # TWO-FILE COMMIT + RECOVERY (swamp round 6): the ledger is staged whole and os.replace'd
    # first (single commit point), then the manifest is os.replace'd. A crash between the two
    # replaces leaves ORPHAN rows - ledger entries whose key is absent from the published
    # manifest. The next run detects orphans against the manifest: identical candidates finish
    # the interrupted publish (idempotent), changed candidates roll orphans back through the
    # same staged write (explicit, logged) instead of stranding as a conflict refusal. A key
    # present in BOTH the ledger and the manifest with different values is a real fork: refuse.
    if preview and os.path.abspath(out) == PROD_MANIFEST_PATH:
        raise ValueError(f"fail closed: --preview refuses production manifest path {out} - preview output is isolated")
    os.makedirs(os.path.dirname(ledger), exist_ok=True)
    lockf = open(LOCK_PATH, 'w')
    fcntl.flock(lockf, fcntl.LOCK_EX)
    try:
        existing = [json.loads(l) for l in open(ledger)] if os.path.exists(ledger) else []
        published_keys = set()
        if not preview and os.path.exists(out):
            try:
                pub = json.load(open(out))
                published_keys = {(str(x.get('game',{}).get('eid')),) + _ikey(x.get('market_class','ml'), x.get('side'), x)
                                  for x in pub.get('picks',[])}
            except Exception as e:
                # FAIL CLOSED (swamp round 7): an unreadable manifest is NEVER 'nothing published' -
                # treating it as empty would let orphan rollback delete genuinely published rows.
                raise ValueError(f"fail closed: published manifest {out} exists but is unreadable ({e}) - refusing any ledger rewrite until it is repaired or removed deliberately")
        # batch-level duplicate rejection: one (event|class|side) per build
        keys = [(str(c['eid']),) + _ikey(c.get('market_class','ml'), c['side'], c) for c in cands]
        dupes = {k for k in keys if keys.count(k) > 1}
        if dupes: raise ValueError(f"fail closed: duplicate candidates in batch for {sorted(dupes)} - refusing to build")
        ledger_rows = []
        for c, p in zip(cands, picks):
            key = (str(c['eid']),) + _ikey(c.get('market_class','ml'), c['side'], c)
            same = [r for r in existing if r.get('kind')=='pick' and str(r.get('event_id'))==key[0]
                    and _ikey(r.get('market_class','ml'), r.get('side'), r) == key[1:]]
            if len(same) > 1:
                raise ValueError(f"fail closed: ledger already ambiguous for {key} ({len(same)} rows) - refusing to add to an ambiguous key")
            if same:
                r = same[0]
                # FULL payload equality (swamp round 7): identity + stake + price. A units/name/
                # ticker/commence change on a published key is a REFUSAL, never a silent re-size.
                # card_ts excluded: it is per-run write provenance, not pick identity.
                newrow = {'kind':'pick','event_id':key[0],'market_class':key[1],'side':key[2],
                          'name':c['name'],'units':c['units'],
                          'entry_c':p['kalshi']['cents'],'card_american':p['card_american'],
                          'kalshi_ticker':p['kalshi']['ticker'],'commence':c['commence'],
                          **({'line': c.get('line')} if key[1] in ('spread','total','prop') else {}),
                          **({'player': c.get('player'), 'market': c.get('market')} if key[1] == 'prop' else {}),
                          **_card_venue_fields(p, compared=False)}
                identical = all(r.get(f) == v for f, v in newrow.items())
                if identical and not r.get('preview'):
                    continue  # idempotent re-run: finishes an interrupted publish or no-ops a completed one
                if identical and r.get('preview') and not preview:
                    # STAGED PROMOTION: a legacy preview marker on this key must never satisfy a
                    # production publish. Retire it through the staged write below.
                    existing = [x for x in existing if x is not r]
                    print(f"STAGED PROMOTION: retired preview marker on {key}, publishing canonical row")
                elif not identical and not preview and key not in published_keys and not r.get('preview'):
                    # ORPHAN ROLLBACK: row exists but its key was never published (interrupted
                    # publication). Roll it back through the staged write and proceed with the
                    # new values - this is recovery, not a fork.
                    existing = [x for x in existing if x is not r]
                    print(f"ORPHAN ROLLBACK: removed unpublished ledger row on {key} ({r.get('entry_c')}c) - recovering interrupted publication")
                elif not identical and preview:
                    existing = [x for x in existing if x is not r]  # preview ledger: replace freely, previews are disposable
                else:
                    diffs = {f: (r.get(f), v) for f, v in newrow.items() if r.get(f) != v}
                    raise ValueError(f"fail closed: conflicting canonical pick row for {key} - fields differ {diffs} - refusing to fork the card record")
            ledger_rows.append({'kind':'pick','event_id':key[0],'market_class':key[1],'side':key[2],
                                'name':c['name'],'units':c['units'],
                                'entry_c':p['kalshi']['cents'],'card_american':p['card_american'],
                                'card_source':p['card_source'],'card_ts':p['card_ts'],
                                **_card_venue_fields(p),
                                'kalshi_ticker':p['kalshi']['ticker'],'commence':c['commence'],
                                **({'line': c.get('line')} if key[1] in ('spread','total','prop') else {}),
                                **({'player': c.get('player'), 'market': c.get('market')} if key[1] == 'prop' else {}),
                                'preview':preview})
        # stage manifest + whole ledger; commit ledger first, then publish manifest
        tmp = out + '.tmp'
        with open(tmp, 'w') as mf:
            json.dump(manifest, mf, indent=1); mf.flush(); os.fsync(mf.fileno())
        final_ledger = existing + ledger_rows
        ltmp = ledger + '.stage'
        with open(ltmp, 'w') as sf:
            for r in final_ledger: sf.write(json.dumps(r) + '\n')
            sf.flush(); os.fsync(sf.fileno())
        os.replace(ltmp, ledger)   # ledger commit point
        os.replace(tmp, out)       # manifest publish
        # PROD MIRROR (Sep 29 stale-grader incident): finals_watch runs from the /home/sandbox/rix_tmp
        # clone and reads ITS manifest.json. When the daily build publishes elsewhere (e.g.
        # /tmp/rix_repo/manifest.json), the grader silently reads the stale rix_tmp copy and finals
        # never grade. Mirror every non-preview publish onto PROD_MANIFEST_PATH (same box, atomic)
        # so the grader's input is always the manifest just built. Mirror failure fails LOUD -
        # a silent miss is exactly the incident being fixed.
        if not preview and os.path.abspath(out) != os.path.abspath(PROD_MANIFEST_PATH):
            if os.path.isdir(os.path.dirname(PROD_MANIFEST_PATH)):
                import shutil
                _mtmp = PROD_MANIFEST_PATH + '.mirror-tmp'
                with open(out) as _src, open(_mtmp, 'w') as _dst:
                    shutil.copyfileobj(_src, _dst); _dst.flush(); os.fsync(_dst.fileno())
                os.replace(_mtmp, PROD_MANIFEST_PATH)
                print(f"prod mirror: {out} -> {PROD_MANIFEST_PATH} (finals_watch input refreshed)")
            else:
                raise SystemExit(f"fail loud: prod mirror skipped - {os.path.dirname(PROD_MANIFEST_PATH)} missing; finals_watch would read a stale manifest")
        # READBACK VERIFICATION: staged ledger must read back exactly; appended rows must match.
        rb = [json.loads(l) for l in open(ledger)]
        if rb != final_ledger:
            raise ValueError("fail closed: ledger readback mismatch after commit - staged content does not verify")
        print(f"wrote {out}: {len(picks)} picks, preview={preview} | ledger rows appended: {len(ledger_rows)} -> {ledger} (readback verified)")
    finally:
        fcntl.flock(lockf, fcntl.LOCK_UN); lockf.close()
    for p in picks:
        _ba = p.get('best_ask')
        _px = f"{p['card_source']}; Kalshi {p['kalshi']['cents']}c" if _ba else f"Kalshi {p['kalshi']['cents']}c"
        print(f"  #{p['num']} {p['name']} {p['units']} @{p['odds']} ({_px}) | {p['sub']}")
if __name__ == '__main__': main()
