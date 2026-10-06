#!/usr/bin/env python3
"""Explicit Kalshi market + side fixture (Oct 2: the Under 6.5 on STL @ DAL is the NO side of the Kalshi
market "Over 6.5 goals", KXNHLTOTAL-26OCT02STLDAL-7, YES ask 44c / NO ask 57c). The builder priced Kalshi
chips only from a team-matched market's YES ask, so the Under would have worn the Over's 44c (or failed to
resolve: a total has no team text) and shipped with no kalshi block at all.
A pick's kalshi block may now name its exact market and side:
    kalshi: {url, ticker: '<full market ticker>', side: 'no'|'yes', cents, gate_cents}
Builds real cards with each builder twin in a throwaway tree, the network replaced by canned Kalshi
responses (sitecustomize stub; every other host fails fast, nothing leaves the machine), and checks:
 A. a NO-side total resolves to that market's NO ask: chip 'KAL -133', data-cents 57, data-kalpx="no", and
    data-kalticker/data-kalside rebuild the exact market ticker; the market record names (event, market,
    side); the game page row shows the same price and side, never the YES-ask board.
 B. the YES side of the same market still reads the YES ask (44c, +127); an explicit YES moneyline keeps
    the both-sides board when the board's picked-side market is that ticker.
 C. the ship ceiling compares the SAME side's ask: NO 57 vs gate 57 ships, NO 58 vs gate 57 fails (exit 3)
    although the YES ask sits under the gate, and a YES ask above the gate never fails a NO pick.
 D. an unresolved explicit market (no market, a zero ask) takes the unchanged unresolved path: pre-game
    hard fail, in play the pinned snapshot.
 E. an old team-matched pick (kalshi.ticker present, no side - every build_manifest pick since Sep 29) is
    unchanged: same chip markup beside an explicit pick as alone, team-matched suffix, YES ask, no
    data-kalpx (the single-market endpoint is poisoned at 99c), and a card without an explicit pick
    emits the original YES-only client tick on the index and its game pages.
 F. the client tick (node, no DOM library) fetches the exact market and reads no_ask for a data-kalpx="no"
    chip, the YES ask for a chip without it, and settles a NO chip as won on result 'no'; the game page
    tick reads no_ask too.
 G. a malformed explicit side fails the build (exit 3); build_manifest.py carries kalshi.side into the
    manifest pick (only when given, yes|no only) and the page built from that manifest prices the NO ask.
 H. a game carrying a moneyline and a NO-side total, in play: the total's game page reads its own shipped pin
    (market class + line + market + side key, 57c NO) and never the moneyline's game-key pin (41c); the
    moneyline's page keeps it.
 I. side vs lock at pre-game publish (lock = kalshi.cents, tolerance 6c): the Oct 2 card ships; an Under declared
    YES or an Over declared NO on an "Over 6.5" market fails (and the reverse on an "Under 6.5" market); a title
    naming no single direction is not read; a picked ask past 6c from the lock fails (the neighbouring line at
    18c, a 7c move), 6c ships; the other side's ask sitting closer to the lock fails (a tie ships); settled picks and
    display-only rebuilds of the published card (also on refresh and in play) keep their existing paths, while a
    refresh or in-play build of a card that is not the published one binds its market (the wrong line fails there)
    with no lock check.
 J. an explicit ticker that is not a market of the url's event (another event, a prefix, no url, a series-level
    url that names no event, a market-level url) fails (exit 3); an event url with a slug segment binds; an old
    pick is not held to it.
 K. build_gh_page.py (the v1 preview builder) and its preview overlay copy (the file card_chain_preview.sh
    actually runs, after copying previews/overlay over scripts/) refuse any pick whose kalshi block names a side
    (exit 3) and still build a card without one.
 L. two explicit props on one game and one line: the approved publish writes one Kalshi pin per market + side;
    in play each game page wears its own pin and market record, never the other prop's, and never a shared
    class-key slot (with no pin of its own it wears its lock).
 M. a moneyline's side is bound to its team at pre-game publish: Toronto declared NO on Toronto's own near-even
    market fails (the lock checks cannot see it), YES on the opponent's market fails, NO on the opponent's
    market ships only on a two-way event, a YES naming both teams fails; same-city teams bind through the market's
    own code (NYY, ESPN's Yankees), so YES on the Mets' market fails; a refresh of a card that is not the published
    one binds the side again, the published card's refresh keeps its path.
 P. the original intent end to end: a + run line (White Sox +1.5 = NO on "Houston wins by over 1.5") prices its
    NO ask on the chip, market record, game page and client tick; the YES side (Astros -1.5) reads the YES ask;
    the + line declared YES on the opponent's market fails.
 Q. the market itself is bound to the pick at pre-game publish, so a ticker and a lock both read off the wrong market
    fail: the series class (GAME/FIGHT/MATCH, SPREAD, TOTAL, else a prop) is the pick's class; the event's game code
    names the pick's two teams (either order) and its date token is the game's Eastern date, or with an Eastern start
    time (MLB) within 90 minutes of the commence; the YES line equals the pick's line (a spread's YES on the picked
    team is its -X, on the opponent its +X) and an unreadable line fails; a prop is bound to its direction (an N+
    market's YES is the over), its player and its stat. White Sox +1.5 as YES on "Chicago WS wins by over 1.5", Astros
    -1.5 as NO there, White Sox +2.5 on the 1.5 market, an Under 6.5 on the Over 5.5 market, Astros ML on a run-line
    market, a total of another game or another day, an Over prop declared NO, another player's or another stat's
    market and a prop of another line all fail (exit 3); the good cards, an Under prop, a fight coded home-first and a
    Penn State game bound through ESPN's abbreviation still ship.
 R. the second review (Oct 6), each failing case's ticker and lock read off the same wrong market (every one shipped
    before R): a total binds its game only through ESPN's abbreviations (BUF @ CGY on BOSCAR, ANA @ CBJ on COLUTAH,
    ARI @ BUF on BALCIN and BAL @ TOR on TBBOS at the same start all fail; a total ESPN gives no abbreviation for
    fails closed; BUFCGY, CHIUTA for ESPN's UTAH and a timed BALTOR ship); a prop names its player in full or by
    initial plus the ticker's initial and surname (Matthew Tkachuk on Brady's market, on "M. Tkachuk" coded
    BTKACHUK, and Jack Hughes on Luke's fail; FLAMTKACHUK19 and Brady's own ship); a same-city moneyline binds
    through the market's code, never kalshi.team (Yankees YES on the Mets' market fails with kalshi.team NYM or
    'New York M'; Yankees as NO there ships); an approved publish after the start binds its market with no lock
    check (an Under declared YES, an Under on the Over 5.5 market and another day's event fail; the bound Under
    ships, its live ask 27c off the lock); a refresh build of a card that is not the published one binds side and
    market (an Under declared YES fails), the published card's refresh keeps its path, and a refresh never checks
    the lock.
 S. the NO side across leagues, each on the merged tree beside main's Vegas, pick_line and spread-name holds:
    NFL Falcons +2.5 is NO of "New Orleans wins by over 2.5" (KXNFLSPREAD ...ATLNO-NO3: team code NO, side no) and
    prices its NO ask on the chip, market record, game page and client tick; Saints -2.5 is its YES; the +2.5 declared
    YES, or bound to the 3.5 rung, fails; a name or pick_line off its line is held by main's holds, a pick_line that
    agrees builds; a Raiders game is held by the Vegas rule before any market is read. NFL Under 41.5 is NO of
    KXNFLTOTAL. CFB Iowa +27.5 is NO of OSU28 (82c), PITT @ VT Under 54.5 NO of KXNCAAFTOTAL ...-55 at 51c. WNBA
    Liberty +3.5 is NO of KXWNBASPREAD ...NYATL-ATL4. NWSL "Houston or Draw" is exactly NO of Washington's market on
    the three-way event KXNWSLGAME ...HDAWSP, but the card has no double-chance class yet: carded as a moneyline
    (or under an unknown class) it would be graded as a Houston win, so it fails, as does Houston ML as that NO - M's
    three-way refusal holds. A zoneless commence binds its event as UTC, main's convention, on a Pacific machine too.
    The Oct 5 Flyers +1.5 (shipped kalshi:null, manifest-24105e3e4c2b.json) replayed with its NO market (NO of
    "Tampa Bay wins by over 1.5", KXNHLSPREAD ...PHITB-TB2) prices the NO ask (58c), and declared YES there fails.
 T. one line, one market (the page builder's best-ask line hold): on a spread, total or prop every best_ask quote
    from a venue other than Kalshi names the picked side's line and it is the pick's own; a DraftKings +3, or the
    game's book line -3, quoted against the 2.5 rung is held (exit 3), a quote naming no line is held, a moneyline
    quote naming a line is held; the same quote at +2.5 builds.
 G (cont). build_manifest refuses the Oct 5 Flyers +1.5 as it was carded (no kalshi block, J-122) and carries its NO
    market to a page that prices the NO ask: the replay never ships kalshi:null. price_card refuses a book +3 or -3
    against the Falcons' 2.5 rung (cheaper or not), a book quote naming no line, a book Under 41 against an Under
    41.5 and a moneyline quote naming a line, and builds the same book at +2.5, carrying its line into best_ask; an
    unknown class ("dc", a double chance) refuses.
Run: python3 scripts/test_kalshi_no_side.py [builder.py ...]   (default: both twins)
"""
import copy, datetime, hashlib, json, os, re, shutil, subprocess, sys, tempfile, warnings
warnings.simplefilter("ignore", SyntaxWarning)

SD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SD)
BUILDERS = [os.path.abspath(a) for a in sys.argv[1:]] or [os.path.join(SD, 'build_gh_page_v2.py'), os.path.join(SD, '_build_nocanon_v2.py')]
failures = 0
def check(name, ok, detail=''):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name + ('' if ok or not detail else '  [' + str(detail)[-600:] + ']'))
    if not ok: failures += 1

DEAD = 'http://127.0.0.1:9'
FAKENET = r'''
import io, json, os, re, socket, urllib.request
_ROUTES = json.load(open(os.environ['RP_FAKENET']))
class _Resp(io.BytesIO):
    status = 200
    def __enter__(self): return self
    def __exit__(self, *a): self.close()
    def getcode(self): return 200
def _fake(req, *a, **k):
    url = req.full_url if hasattr(req, 'full_url') else str(req)
    for pat, body in _ROUTES:
        if re.search(pat, url): return _Resp(json.dumps(body).encode())
    raise OSError('offline fixture: no route for ' + url)
def _blocked(*a, **k): raise OSError('offline fixture')
urllib.request.urlopen = _fake
socket.create_connection = _blocked
'''

NOW = datetime.datetime.now(datetime.timezone.utc)
FUT = (NOW + datetime.timedelta(days=2)).strftime('%Y-%m-%dT00:00Z')
PAST = (NOW - datetime.timedelta(hours=1)).strftime('%Y-%m-%dT%H:%MZ')
SOON = (NOW + datetime.timedelta(hours=3)).strftime('%Y-%m-%dT%H:%MZ')
from zoneinfo import ZoneInfo
def dtok(iso, hhmm=False):
    # a Kalshi event's date token (26OCT02) is the game's Eastern date; MLB events add the Eastern start (1830).
    # Every fixture event is dated from its pick's commence: the publish check binds the event to the game's day.
    t = datetime.datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(ZoneInfo('America/New_York'))
    return t.strftime('%y%b%d%H%M' if hhmm else '%y%b%d').upper()
D = dtok(FUT)
EV = 'KXNHLTOTAL-' + D + 'STLDAL'
TK = EV + '-7'
KURL = 'https://kalshi.com/markets/kxnhltotal/' + EV.lower()
LEV = 'KXNHLGAME-' + D + 'MTLTOR'
LURL = 'https://kalshi.com/markets/kxnhlgame/' + LEV.lower()
GEV = 'KXNHLGAME-' + D + 'STLDAL'
GURL = 'https://kalshi.com/markets/kxnhlgame/' + GEV.lower()

def total_mkt(sfx, ya, na, **kw):
    return dict({'ticker': EV + '-' + sfx, 'title': 'Over %s goals' % sfx, 'yes_sub_title': 'Over %d.5 goals scored' % (int(sfx) - 1),
                 'yes_ask_dollars': ya, 'no_ask_dollars': na, 'status': 'active'}, **kw)
LEAFS_MKTS = [{'ticker': LEV + '-TOR', 'title': 'Toronto', 'yes_sub_title': 'Toronto', 'yes_ask_dollars': '0.50', 'no_ask_dollars': '0.51'},
              {'ticker': LEV + '-MTL', 'title': 'Montreal', 'yes_sub_title': 'Montreal', 'yes_ask_dollars': '0.51', 'no_ask_dollars': '0.50'}]

def routes(seven=None, poison=True, extra=()):
    """seven: the KXNHLTOTAL ...-7 market (None = the API has no such market). poison: the Leafs single-market
    endpoint answers 99c both sides - a team-matched pick that reached it would change its chip. extra: more
    markets answered by the single-market endpoint (a pick bound to another line of the event)."""
    rows = [total_mkt('6', '0.62', '0.39'), total_mkt('8', '0.27', '0.74')] + ([seven] if seven else [])
    r = [[r'markets\?event_ticker=' + EV + '&', {'markets': rows}]]
    if seven: r.append([r'trade-api/v2/markets/' + TK + r'(\?|$)', {'market': seven}])
    for m in extra: r.append([r'trade-api/v2/markets/' + m['ticker'] + r'(\?|$)', {'market': m}])
    r.append([r'markets\?event_ticker=' + LEV + '&', {'markets': LEAFS_MKTS}])
    for m in LEAFS_MKTS:
        r.append([r'trade-api/v2/markets/' + m['ticker'] + r'(\?|$)', {'market': dict(m, yes_ask_dollars='0.99', no_ask_dollars='0.99') if poison else m}])
    return r
SEVEN = total_mkt('7', '0.44', '0.57')

# two player props on one game and one line (L): each its own market and lock
PEV = 'KXNHLGOAL-' + dtok(SOON) + 'STLDAL'  # L publishes these props at SOON
PURL = 'https://kalshi.com/markets/kxnhlgoal/' + PEV.lower()
PTA, PTB = PEV + '-RTHOMAS1', PEV + '-JROBERTSON1'
PMA = {'ticker': PTA, 'title': 'Robert Thomas: 1+ goals', 'yes_sub_title': 'Robert Thomas', 'yes_ask_dollars': '0.38', 'no_ask_dollars': '0.64', 'status': 'active'}
PMB = {'ticker': PTB, 'title': 'Jason Robertson: 1+ goals', 'yes_sub_title': 'Jason Robertson', 'yes_ask_dollars': '0.45', 'no_ask_dollars': '0.57', 'status': 'active'}
def prop_pick(player, tk, cents, commence):
    return {'num': 1, 'name': player + ' Over 0.5 goals', 'market_class': 'prop', 'player': player, 'line': 0.5, 'sub': 'STL @ DAL',
            'odds': '+160', 'units': '5u', 'side': 'over', 'game': {'away': 'St. Louis Blues', 'home': 'Dallas Stars', 'commence': commence, 'eid': ''},
            'espn_league': 'hockey/nhl', 'league': 'NHL', 'best_book': 'Kalshi',
            'kalshi': {'url': PURL, 'ticker': tk, 'side': 'yes', 'cents': cents, 'gate_cents': cents, 'team': player}}
PROP_ROUTES = [[r'trade-api/v2/markets/' + PTA + r'(\?|$)', {'market': PMA}], [r'trade-api/v2/markets/' + PTB + r'(\?|$)', {'market': PMB}],
               [r'markets\?event_ticker=' + PEV + '&', {'markets': [PMA, PMB]}]]

# a run line (P): White Sox +1.5 is the NO side of "Houston wins by over 1.5 runs"
SEV = 'KXMLBSPREAD-' + D + 'CWSHOU'
SURL = 'https://kalshi.com/markets/kxmlbspread/' + SEV.lower()
STK = SEV + '-HOU2'
HOU2 = {'ticker': STK, 'title': 'Houston wins by over 1.5 runs?', 'yes_sub_title': 'Houston wins by over 1.5 runs',
        'yes_ask_dollars': '0.35', 'no_ask_dollars': '0.66', 'status': 'active'}
SOX = {'num': 1, 'name': 'White Sox +1.5', 'market_class': 'spread', 'line': -1.5, 'sub': 'CWS @ HOU', 'odds': '-194', 'units': '5u', 'side': 'away',
       'game': {'away': 'Chicago White Sox', 'home': 'Houston Astros', 'commence': FUT, 'eid': ''},
       'espn_league': 'baseball/mlb', 'league': 'MLB', 'best_book': 'Kalshi',
       'kalshi': {'url': SURL, 'ticker': STK, 'side': 'no', 'cents': 66, 'gate_cents': 66, 'team': 'Chicago WS'}}
ASTROS = dict(copy.deepcopy(SOX), name='Astros -1.5', odds='+186', side='home',
              kalshi={'url': SURL, 'ticker': STK, 'side': 'yes', 'cents': 35, 'gate_cents': 35, 'team': 'Houston'})
def spread_routes(m=HOU2):
    return [[r'trade-api/v2/markets/' + STK + r'(\?|$)', {'market': m}]]

# same-city moneyline (M): the names alone cannot tell New York Y from New York M; kalshi.team (the market code) can
YEV = 'KXMLBGAME-' + D + 'NYMNYY'
YURL = 'https://kalshi.com/markets/kxmlbgame/' + YEV.lower()
YMKTS = [{'ticker': YEV + '-NYY', 'title': 'New York M vs New York Y Winner?', 'yes_sub_title': 'New York Y', 'yes_ask_dollars': '0.52', 'no_ask_dollars': '0.49'},
         {'ticker': YEV + '-NYM', 'title': 'New York M vs New York Y Winner?', 'yes_sub_title': 'New York M', 'yes_ask_dollars': '0.49', 'no_ask_dollars': '0.52'}]
YANKS = {'num': 1, 'name': 'Yankees ML', 'market_class': 'ml', 'sub': 'NYM @ NYY', 'odds': '-108', 'units': '5u', 'side': 'home',
         'game': {'away': 'New York Mets', 'home': 'New York Yankees', 'commence': FUT, 'eid': ''},
         'espn_league': 'baseball/mlb', 'league': 'MLB', 'best_book': 'Kalshi',
         'kalshi': {'url': YURL, 'ticker': YEV + '-NYY', 'side': 'yes', 'cents': 52, 'gate_cents': 52, 'team': 'NYY'}}
YROUTES = [[r'trade-api/v2/markets/' + m['ticker'] + r'(\?|$)', {'market': m}] for m in YMKTS] + [[r'markets\?event_ticker=' + YEV + '&', {'markets': YMKTS}]]

UNDER = {'num': 1, 'name': 'Under 6.5', 'market_class': 'total', 'line': 6.5, 'sub': 'STL @ DAL', 'odds': '-133', 'units': '5u', 'side': 'under',
         'game': {'away': 'St. Louis Blues', 'home': 'Dallas Stars', 'commence': FUT, 'eid': ''},
         'espn_league': 'hockey/nhl', 'league': 'NHL', 'best_book': 'Kalshi',
         'kalshi': {'url': KURL, 'ticker': TK, 'side': 'no', 'cents': 57, 'gate_cents': 57, 'team': ''}}
OVER = dict(copy.deepcopy(UNDER), name='Over 6.5', odds='+127', side='over',
            kalshi={'url': KURL, 'ticker': TK, 'side': 'yes', 'cents': 44, 'gate_cents': 44, 'team': ''})
# build_manifest shape of an old pick: ticker present, NO side - the team-matched path
LEAFS = {'num': 2, 'name': 'Maple Leafs ML', 'market_class': 'ml', 'sub': 'MTL @ TOR', 'odds': '+100', 'units': '5u', 'side': 'home',
         'game': {'away': 'Montreal Canadiens', 'home': 'Toronto Maple Leafs', 'commence': FUT, 'eid': ''},
         'espn_league': 'hockey/nhl', 'league': 'NHL', 'best_book': 'Kalshi',
         'kalshi': {'url': LURL, 'cents': 50, 'team': 'Toronto', 'gate_cents': 50, 'ticker': LEV + '-TOR'}}
BASE = {'date_label': 'Fixture', 'updated': '', 'record': '1-0', 'units_pl': '+1.00u', 'units_ledger': None,
        'yesterday': '', 'status_note': '', 'preview': False, 'parlay': None}

def card(*picks):
    m = copy.deepcopy(BASE); m['picks'] = [copy.deepcopy(p) for p in picks]
    for i, p in enumerate(m['picks'], 1): p['num'] = i
    return m

# ESPN's scoreboard for the fixture leagues: each team's ESPN abbreviation (CHW for the White Sox, UTAH for Utah, NJ
# for New Jersey). A total's or a prop's event code binds its game only through these, so every build gets them unless
# it asks for none (espn=False). No homeAway and no date: the builder's eid binding never matches these events.
def espn_sb(lg, teams):
    return [r'site\.api\.espn\.com/apis/site/v2/sports/' + re.escape(lg) + r'/scoreboard',
            {'events': [{'competitions': [{'competitors': [{'team': {'displayName': n, 'abbreviation': a}} for n, a in teams]}]}]}]
ESPN = [espn_sb('hockey/nhl', [('St. Louis Blues', 'STL'), ('Dallas Stars', 'DAL'), ('Montreal Canadiens', 'MTL'), ('Toronto Maple Leafs', 'TOR'),
                               ('Boston Bruins', 'BOS'), ('New York Rangers', 'NYR'), ('Buffalo Sabres', 'BUF'), ('Calgary Flames', 'CGY'),
                               ('Carolina Hurricanes', 'CAR'), ('Anaheim Ducks', 'ANA'), ('Columbus Blue Jackets', 'CBJ'), ('Colorado Avalanche', 'COL'),
                               ('Utah Mammoth', 'UTAH'), ('Chicago Blackhawks', 'CHI'), ('Ottawa Senators', 'OTT'), ('Florida Panthers', 'FLA'),
                               ('New Jersey Devils', 'NJ')]),
        espn_sb('baseball/mlb', [('Chicago White Sox', 'CHW'), ('Houston Astros', 'HOU'), ('New York Mets', 'NYM'), ('New York Yankees', 'NYY'),
                                 ('Baltimore Orioles', 'BAL'), ('Toronto Blue Jays', 'TOR'), ('Tampa Bay Rays', 'TB'), ('Boston Red Sox', 'BOS')]),
        espn_sb('football/nfl', [('Arizona Cardinals', 'ARI'), ('Buffalo Bills', 'BUF'), ('Baltimore Ravens', 'BAL'), ('Cincinnati Bengals', 'CIN')])]

# S, T and G: the leagues' own ESPN abbreviations (CFB IOWA/OSU/PITT/VT, WNBA NY/ATL, NWSL HOU/WAS as ESPN's
# scoreboard gives them). Passed ahead of ESPN in a build's routes (the first matching route answers), so every
# build above keeps its own ESPN answers.
S_ESPN = [espn_sb('hockey/nhl', [('Philadelphia Flyers', 'PHI'), ('Tampa Bay Lightning', 'TB')]),
          espn_sb('football/nfl', [('Atlanta Falcons', 'ATL'), ('New Orleans Saints', 'NO'), ('Kansas City Chiefs', 'KC'), ('Las Vegas Raiders', 'LV')]),
          espn_sb('football/college-football', [('Iowa Hawkeyes', 'IOWA'), ('Ohio State Buckeyes', 'OSU'), ('Pittsburgh Panthers', 'PITT'), ('Virginia Tech Hokies', 'VT')]),
          espn_sb('basketball/wnba', [('New York Liberty', 'NY'), ('Atlanta Dream', 'ATL')]),
          espn_sb('soccer/usa.nwsl', [('Houston Dash', 'HOU'), ('Washington Spirit', 'WAS')])]
def xm(tk, text, ya, na):
    # one Kalshi market whose title and YES text read `text` ('New Orleans wins by over 2.5 points')
    return {'ticker': tk, 'title': text + '?', 'yes_sub_title': text, 'yes_ask_dollars': ya, 'no_ask_dollars': na, 'status': 'active'}
def xr(*ms):
    return [[r'trade-api/v2/markets/' + m['ticker'] + r'(\?|$)', {'market': m}] for m in ms]
def xurl(tk):
    ev = tk.rsplit('-', 1)[0]
    return 'https://kalshi.com/markets/' + ev.split('-')[0].lower() + '/' + ev.lower()
def xpick(name, mc, side, away, home, lg, league, tk, kside, cents, line=None, commence=FUT):
    p = {'num': 1, 'name': name, 'market_class': mc, 'sub': '', 'odds': '-110', 'units': '5u', 'side': side,
         'game': {'away': away, 'home': home, 'commence': commence, 'eid': ''}, 'espn_league': lg, 'league': league, 'best_book': 'Kalshi',
         'kalshi': {'url': xurl(tk), 'ticker': tk, 'side': kside, 'cents': cents, 'gate_cents': cents, 'team': ''}}
    if line is not None: p['line'] = line
    return p
# NFL: Falcons +2.5 at New Orleans is the NO of "New Orleans wins by over 2.5" - the Saints' code is NO, beside side no
NFL_EV = 'KXNFLSPREAD-' + D + 'ATLNO'
NO3 = xm(NFL_EV + '-NO3', 'New Orleans wins by over 2.5 points', '0.45', '0.56')
NO4 = xm(NFL_EV + '-NO4', 'New Orleans wins by over 3.5 points', '0.37', '0.64')
FALCONS = xpick('Falcons +2.5', 'spread', 'away', 'Atlanta Falcons', 'New Orleans Saints', 'football/nfl', 'NFL', NO3['ticker'], 'no', 56, line=-2.5)
# the Oct 5 Flyers +1.5 exactly as it shipped (no kalshi block), and the NO market of its rung
OCT5 = json.load(open(os.path.join(ROOT, 'manifests', 'manifest-24105e3e4c2b.json')))
FLYERS = [p for p in OCT5['picks'] if p.get('name') == 'Flyers +1.5'][0]
TB2 = xm('KXNHLSPREAD-' + D + 'PHITB-TB2', 'Tampa Bay wins by over 1.5 goals', '0.43', '0.58')
def flyers_replay(kside='no', cents=58):
    # the shipped pick, re-dated to a pre-game publish (its event dated from the same commence), its card source
    # (Polymarket 58c, +1.5) recorded as its best ask, and the NO market of its rung as its kalshi block
    p = copy.deepcopy(FLYERS); p['game']['commence'] = FUT
    p['kalshi'] = {'url': xurl(TB2['ticker']), 'ticker': TB2['ticker'], 'side': kside, 'cents': cents, 'gate_cents': cents, 'team': ''}
    p['best_ask'] = {'venue': 'poly', 'price': 58, 'line': 1.5, 'read_at': p['card_ts'], 'cost_c': 58.0, 'fee_c': 0.0,
                     'compared': [{'venue': 'poly', 'price': 58, 'line': 1.5, 'read_at': p['card_ts']}, {'venue': 'kalshi', 'price': 58, 'read_at': p['card_ts']}]}
    return p

GAME_PAGES = {}
LEDGER = {}
def build(builder, manifest, rts, refresh=False, files=None, as_name='build_gh_page_v2.py', extra_env=None, espn=True):
    """files: {name: text} written at the tree root before the build (shipped_books.json, shipped_pick_hash.txt).
    as_name: the builder's file name in the tree (build_gh_page.py for the v1 preview builder).
    extra_env: more environment for the build (RP_PUBLISH=1, the only ledger writer). LEDGER holds the
    tree's shipped_books.json after the build ({} when none). espn: answer ESPN's scoreboard (ESPN above) after
    the build's own routes; False leaves ESPN unreachable."""
    rts = list(rts) + (ESPN if espn else [])
    d = tempfile.mkdtemp(prefix='rp-kalno-')
    try:
        os.makedirs(os.path.join(d, 'scripts')); os.makedirs(os.path.join(d, 'slates')); os.makedirs(os.path.join(d, '_net'))
        bsrc = os.path.dirname(builder)
        shutil.copy(builder, os.path.join(d, 'scripts', as_name))
        for f in ('index_v2.js', 'index_v2.css', 'game_page_template.html', 'team_page_template.html', 'poly_us.py'):
            shutil.copy(os.path.join(bsrc if os.path.exists(os.path.join(bsrc, f)) else SD, f), os.path.join(d, 'scripts', f))
        for f in ('feed_arbiter.js', 'feed_registry.json', 'config_leagues.json'):
            shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
        json.dump(manifest, open(os.path.join(d, 'manifest.json'), 'w'), indent=1)
        json.dump([], open(os.path.join(d, 'slates', 'odds_prefill.json'), 'w'))
        open(os.path.join(d, '_net', 'sitecustomize.py'), 'w').write(FAKENET)
        json.dump(rts, open(os.path.join(d, '_net', 'routes.json'), 'w'))
        for fn, body in (files or {}).items(): open(os.path.join(d, fn), 'w').write(body)
        env = dict(os.environ, http_proxy=DEAD, https_proxy=DEAD, HTTP_PROXY=DEAD, HTTPS_PROXY=DEAD, NO_PROXY='',
                   PYTHONPATH=os.path.join(d, '_net'), RP_FAKENET=os.path.join(d, '_net', 'routes.json'), PYTHONWARNINGS='ignore')
        for k in ('RP_REFRESH', 'RP_PUBLISH', 'RP_KAL_TICKER'): env.pop(k, None)
        if refresh: env['RP_REFRESH'] = '1'
        env.update(extra_env or {})
        r = subprocess.run([sys.executable, os.path.join(d, 'scripts', as_name), 'manifest.json', 'index.html'],
                           cwd=d, env=env, capture_output=True, text=True, timeout=600)
        page = open(os.path.join(d, 'index.html')).read() if os.path.exists(os.path.join(d, 'index.html')) else ''
        GAME_PAGES.clear()
        for f in os.listdir(d):
            if re.fullmatch(r'game-\d+\.html', f): GAME_PAGES[f] = open(os.path.join(d, f)).read()
        LEDGER.clear()
        try: LEDGER.update(json.load(open(os.path.join(d, 'shipped_books.json'))))
        except (OSError, ValueError): pass
        return r.returncode, page, r.stderr
    finally:
        shutil.rmtree(d, ignore_errors=True)

def kal_chips(page):
    return re.findall(r'<a class="chip[^"]*"[^>]*data-book="KAL"[^>]*>.*?</a>', page)
def chip_for(page, href):
    c = [x for x in kal_chips(page) if 'href="%s"' % href in x]
    return c[0] if len(c) == 1 else ''
def label(markup):
    return re.sub(r'<[^>]+>', '', markup).replace('★', '').strip()
def attr(markup, name):
    m = re.search(r' data-%s="([^"]*)"' % name, markup)
    return m.group(1) if m else None
def records(html_):
    m = re.search(r'let RP_MARKETS=(\[.*?\]);', html_)
    return json.loads(m.group(1)) if m else []
def kal_row(gp):
    m = re.search(r'<div class="mrow" data-book="KAL">.*?</div>', gp)
    return m.group(0) if m else ''
def js_fn(src, name):
    i = src.find('function ' + name + '(')
    if i < 0: return ''
    d = 0
    for k in range(src.find('{', i), len(src)):
        if src[k] == '{': d += 1
        elif src[k] == '}':
            d -= 1
            if not d: return src[i:k + 1]
    return ''

def run_tick(page, fn_name, anchors, markets):
    """Run the built page's own tick function in node with a stub DOM: anchors = [{dataset, innerHTML}],
    markets = {ticker: market}. Returns {fetched: [market tickers], anchors: [{dataset, innerHTML}]}."""
    code = '\n'.join([
        js_fn(page, 'rpC2ML'), js_fn(page, 'rpMLF'),
        'const A=%s.map(function(x){x.closest=function(){return null;};return x;});' % json.dumps(anchors),
        'const MK=%s;const fetched=[];' % json.dumps(markets),
        'var window={};var document={querySelectorAll:function(){return A;}};',
        'function rpMkt(){return null;}function rpInPlay(){return false;}function rpCxUpd(){}function rpQuoteMut(){}',
        'function fetch(u){const inner=decodeURIComponent(String(u).split("url=")[1]||"");const t=inner.split("/markets/")[1].split("?")[0];'
        'fetched.push(t);return Promise.resolve({json:function(){return Promise.resolve({market:MK[t]});}});}',
        js_fn(page, fn_name),
        fn_name + '();',
        'setTimeout(function(){console.log(JSON.stringify({fetched:fetched,anchors:A.map(function(a){return {dataset:a.dataset,innerHTML:a.innerHTML};})}));},30);'])
    r = subprocess.run(['node', '-e', code], capture_output=True, text=True, timeout=60)
    try: return json.loads(r.stdout)
    except ValueError: return {'error': r.stderr[-800:]}

def ds(markup):
    return {k: v for k, v in re.findall(r' data-(\w+)="([^"]*)"', markup.split('>', 1)[0])}

def published(builder, manifest):
    """shipped_pick_hash.txt naming this card as the last published one (the hash only an RP_PUBLISH=1 build writes):
    a build of it is a display-only rebuild of the published card."""
    src = open(builder).read(); i = src.index('def _pick_content_hash'); ns = {'json': json, '_hl': hashlib}
    exec(src[i:src.index('\n_PC_HASH=', i)], ns)
    return {'shipped_pick_hash.txt': ns['_pick_content_hash'](manifest) + '\n'}

for B in BUILDERS:
    tag = os.path.basename(B)

    # A. NO-side total, pre-game publish build (ship ceiling live): NO ask 57 vs gate 57
    rc, page, log = build(B, card(UNDER), routes(SEVEN))
    ch = chip_for(page, KURL)
    check(f'{tag}: A NO-side card builds (NO ask 57c at the 57c gate)', rc == 0 and bool(ch), log[-800:])
    check(f'{tag}: A chip shows the NO ask as American: KAL -133 (never the Over\'s 44c / +127)', label(ch) == 'KAL -133', label(ch))
    check(f'{tag}: A chip data-cents is the NO ask 57', attr(ch, 'cents') == '57', ch)
    check(f'{tag}: A chip names the side (data-kalpx="no") and its kalticker-kalside pair is the exact market ticker',
          attr(ch, 'kalpx') == 'no' and '%s-%s' % (attr(ch, 'kalticker'), attr(ch, 'kalside')) == TK, ch)
    rec = records(page)[int(attr(ch, 'mr'))] if attr(ch, 'mr') else {}
    check(f'{tag}: A market record is (event, exact market, side no) at 57c',
          (rec.get('src'), rec.get('ev'), rec.get('mkt'), rec.get('side'), rec.get('c')) == ('Kalshi', EV, TK, 'no', 57), rec)
    gp = GAME_PAGES.get('game-1.html', '')
    row = kal_row(gp)
    check(f'{tag}: A game page Kalshi row: Under 6.5, KAL -133, data-cents 57, data-kalpx no, exact market pair',
          '>Under 6.5</a>' in row and '>KAL -133</a>' in row and 'data-kalticker="%s" data-kalside="7" data-kalpx="no" data-cents="57"' % EV in row, row)
    check(f'{tag}: A game page never shows the YES-ask board for a NO pick (no data-kalmkt row; listing was available)', 'data-kalmkt="' not in gp)
    check(f'{tag}: A game page chip matches the index chip (KAL -133, data-kalpx no)',
          any(label(x) == 'KAL -133' and attr(x, 'kalpx') == 'no' for x in kal_chips(gp)))
    # F. the client ticks of this build (index + game page)
    if ch:
        t = run_tick(page, 'rpKalTick', [{'dataset': ds(ch), 'innerHTML': 'KAL -133'}], {TK: dict(SEVEN, no_ask_dollars='0.60', yes_ask_dollars='0.41')})
        a = (t.get('anchors') or [{}])[0]
        check(f'{tag}: F index tick fetches the exact market {TK} (got {t.get("fetched")})', t.get('fetched') == [TK], t)
        check(f'{tag}: F index tick reads no_ask for data-kalpx="no" (60c -> KAL -150, not the 41c YES)',
              a.get('dataset', {}).get('cents') == 60 and a.get('innerHTML') == 'KAL -150', a)
        t = run_tick(page, 'rpKalTick', [{'dataset': ds(ch), 'innerHTML': 'KAL -133'}], {TK: dict(SEVEN, result='no')})
        a = (t.get('anchors') or [{}])[0].get('dataset', {})
        check(f'{tag}: F index tick settles a NO chip as won on result "no"', a.get('won') == '1' and a.get('lost') == '', a)
        t = run_tick(page, 'rpKalTick', [{'dataset': ds(ch), 'innerHTML': 'KAL -133'}], {TK: dict(SEVEN, result='yes')})
        a = (t.get('anchors') or [{}])[0].get('dataset', {})
        check(f'{tag}: F index tick settles a NO chip as lost on result "yes"', a.get('lost') == '1' and a.get('won') == '', a)
    pr = re.search(r'<a data-kalticker[^>]*>KAL[^<]*</a>', row)
    if pr:
        t = run_tick(gp, 'rpKalTick', [{'dataset': ds(pr.group(0)), 'innerHTML': 'KAL -133'}], {TK: dict(SEVEN, no_ask_dollars='0.60', yes_ask_dollars='0.41')})
        a = (t.get('anchors') or [{}])[0]
        check(f'{tag}: F game page tick reads no_ask for the NO row (60c -> KAL -150)',
              t.get('fetched') == [TK] and a.get('dataset', {}).get('cents') == 60 and a.get('innerHTML') == 'KAL -150', t)
    else:
        check(f'{tag}: F game page NO row present for the tick', False, row)

    # B. YES side of the same market: the YES ask, unchanged reading
    rc, page, log = build(B, card(OVER), routes(SEVEN))
    ch = chip_for(page, KURL)
    check(f'{tag}: B YES-side total reads the YES ask: KAL +127, data-cents 44, data-kalpx yes',
          rc == 0 and label(ch) == 'KAL +127' and attr(ch, 'cents') == '44' and attr(ch, 'kalpx') == 'yes', log[-400:] + ch)
    row = kal_row(GAME_PAGES.get('game-1.html', ''))
    check(f'{tag}: B YES-side game page row: Over 6.5 at KAL +127', '>Over 6.5</a>' in row and '>KAL +127</a>' in row and 'data-kalpx="yes"' in row, row)
    LEAFS_YES = copy.deepcopy(LEAFS); LEAFS_YES['kalshi']['side'] = 'yes'
    rc, page, log = build(B, card(LEAFS_YES), routes(SEVEN, poison=False))
    ch = chip_for(page, LURL); gp = GAME_PAGES.get('game-1.html', '')
    check(f'{tag}: B explicit YES moneyline prices its exact market from the single-market read (data-kalpx yes, 50c)',
          rc == 0 and attr(ch, 'kalpx') == 'yes' and attr(ch, 'cents') == '50' and '%s-%s' % (attr(ch, 'kalticker'), attr(ch, 'kalside')) == LEV + '-TOR', log[-400:] + ch)
    check(f'{tag}: B explicit YES moneyline keeps the both-sides board when its ticker is the picked side\'s market',
          'data-kalmkt="%s-TOR"' % LEV in gp and 'data-kalmkt="%s-MTL"' % LEV in gp)

    # C. ship ceiling on the side's own ask
    rc, page, log = build(B, card(UNDER), routes(total_mkt('7', '0.43', '0.58')))
    check(f'{tag}: C NO ask 58c over the 57c gate fails the build (exit 3) though the YES ask is 43c',
          rc == 3 and 'BUILD FAILED: Under 6.5 Kalshi ask 58c exceeds ship-condition ceiling 57c' in log, log[-600:])
    rc, page, log = build(B, card(UNDER), routes(total_mkt('7', '0.58', '0.57')))
    check(f'{tag}: C a YES ask of 58c never fails a NO pick at its 57c NO ask', rc == 0 and label(chip_for(page, KURL)) == 'KAL -133', log[-600:])
    rc, page, log = build(B, card(UNDER), routes(SEVEN), refresh=True)
    check(f'{tag}: C refresh build of the same card ships (exit 0)', rc == 0 and label(chip_for(page, KURL)) == 'KAL -133', log[-400:])

    # D. unresolved explicit market: unchanged unresolved path
    rc, page, log = build(B, card(UNDER), routes(None))
    check(f'{tag}: D no such market pre-game: hard fail naming the exact market and side',
          rc == 3 and 'BUILD FAILED: Kalshi market unresolved for Under 6.5 market %s side no under %s' % (TK, EV) in log, log[-600:])
    rc, page, log = build(B, card(UNDER), routes(total_mkt('7', '0.44', '0.0000')))
    check(f'{tag}: D a zero NO ask is unresolved (hard fail), never a 0c or the YES ask',
          rc == 3 and 'Kalshi market unresolved for Under 6.5 market %s side no' % TK in log, log[-600:])
    U_LIVE = copy.deepcopy(UNDER); U_LIVE['game']['commence'] = PAST
    rc, page, log = build(B, card(U_LIVE), routes(None), refresh=True)
    ch = chip_for(page, KURL)
    check(f'{tag}: D in play, market gone: degrades to the pinned 57c snapshot (KAL -133), build continues',
          rc == 0 and 'IN-PLAY DEGRADE: Under 6.5 Kalshi market unresolved under %s - pinned snapshot 57c' % EV in log
          and label(ch) == 'KAL -133' and attr(ch, 'cents') == '57' and attr(ch, 'kalpx') == 'no', log[-600:] + ch)
    row = kal_row(GAME_PAGES.get('game-1.html', ''))
    check(f'{tag}: D in play, the game page snapshot row wears the pinned NO price (Under 6.5, KAL -133, data-kalpx no)',
          '>Under 6.5</a>' in row and '>KAL -133</a>' in row and 'data-kalside="7" data-kalpx="no" data-cents="57"' in row and 'pre-game snapshot' in row, row)

    # E. old team-matched pick: unchanged alone and beside an explicit pick
    rc, page_old, log = build(B, card(LEAFS), routes(SEVEN))
    old_alone = chip_for(page_old, LURL); gp_old = GAME_PAGES.get('game-1.html', '')
    check(f'{tag}: E old pick (ticker, no side) builds and stays team-matched: data-kalticker = url event, data-kalside TOR, YES ask 50c (endpoint poisoned at 99c)',
          rc == 0 and attr(old_alone, 'kalticker') == LEV and attr(old_alone, 'kalside') == 'TOR' and attr(old_alone, 'cents') == '50'
          and label(old_alone) == 'KAL -100' and 'data-kalpx' not in old_alone, log[-400:] + old_alone)
    check(f'{tag}: E a card without an explicit pick emits the original YES-only index tick and no data-kalpx',
          "if(m.result==='yes'){a.dataset.won='1'" in page_old and "if(m.result==='no'){a.dataset.lost='1'" in page_old
          and 'const d=parseFloat(m.yes_ask_dollars);if(!(d>0&&d<=1))return;' in page_old and 'kalpx' not in page_old)
    check(f'{tag}: E its game page keeps the template tick line verbatim and the both-sides board',
          'const d=parseFloat(m.yes_ask_dollars);' in gp_old and 'kalpx' not in gp_old and 'data-kalmkt="%s-TOR"' % LEV in gp_old)
    rc, page_mix, log = build(B, card(UNDER, LEAFS), routes(SEVEN))
    strip = lambda s: re.sub(r' data-mr="\d+"', '', s)
    old_mixed = chip_for(page_mix, LURL)
    check(f'{tag}: E the old chip\'s markup is identical beside an explicit pick (data-mr index aside)',
          rc == 0 and bool(old_alone) and strip(old_alone) == strip(old_mixed), old_mixed)
    t = run_tick(page_mix, 'rpKalTick', [{'dataset': ds(old_mixed), 'innerHTML': 'KAL -100'}, {'dataset': ds(chip_for(page_mix, KURL)), 'innerHTML': 'KAL -133'}],
                 {LEV + '-TOR': dict(LEAFS_MKTS[0], yes_ask_dollars='0.55', no_ask_dollars='0.46'), TK: SEVEN})
    a = t.get('anchors') or [{}, {}]
    check(f'{tag}: F on a mixed card the old chip still ticks its YES ask (55c -> KAL -122) and the NO chip its NO ask (57c)',
          sorted(t.get('fetched') or []) == sorted([LEV + '-TOR', TK]) and a[0].get('dataset', {}).get('cents') == 55
          and a[0].get('innerHTML') == 'KAL -122' and a[1].get('dataset', {}).get('cents') == 57, t)
    t = run_tick(page_mix, 'rpKalTick', [{'dataset': ds(old_mixed), 'innerHTML': 'KAL -100'}], {LEV + '-TOR': dict(LEAFS_MKTS[0], result='no')})
    a = ((t.get('anchors') or [{}])[0]).get('dataset', {})
    check(f'{tag}: F an old (YES) chip still settles lost on result "no"', a.get('lost') == '1' and a.get('won') == '', a)

    # G. malformed explicit sides fail closed
    bad = copy.deepcopy(UNDER); bad['kalshi']['side'] = 'under'
    rc, page, log = build(B, card(bad), routes(SEVEN))
    check(f'{tag}: G side "under" fails the build (exit 3)', rc == 3 and 'an explicit side needs side yes|no' in log, log[-400:])
    bad = copy.deepcopy(UNDER); bad['kalshi'].pop('ticker')
    rc, page, log = build(B, card(bad), routes(SEVEN))
    check(f'{tag}: G a side without the market ticker fails the build (exit 3)', rc == 3 and 'an explicit side needs side yes|no' in log, log[-400:])

    # H. same game, a moneyline and a NO-side total, in play: each game page reads its own shipped pin
    BLUES = {'num': 1, 'name': 'Blues ML', 'market_class': 'ml', 'sub': 'STL @ DAL', 'odds': '+144', 'units': '5u', 'side': 'away',
             'game': {'away': 'St. Louis Blues', 'home': 'Dallas Stars', 'commence': PAST, 'eid': ''},
             'espn_league': 'hockey/nhl', 'league': 'NHL', 'best_book': 'Kalshi',
             'kalshi': {'url': GURL, 'cents': 41, 'team': 'St. Louis', 'gate_cents': 41, 'ticker': GEV + '-STL'}}
    GK = 'St. Louis Blues|Dallas Stars|' + PAST[:10]
    shipped = {GK: {'Kalshi': {'link': GURL, 'cents': 41, 'commence': PAST}},
               GK + '|total|6.5|' + TK + '|no': {'Kalshi': {'link': KURL, 'cents': 57, 'commence': PAST}}}
    # the published card rebuilt in play (its fixture event is dated for the pre-game card: a card that was never
    # published would have its market bound again, and refused, on this build - R below)
    rc, page, log = build(B, card(BLUES, U_LIVE), routes(SEVEN), refresh=True,
                          files=dict({'shipped_books.json': json.dumps(shipped)}, **published(B, card(BLUES, U_LIVE))))
    gp_ml, gp_tot = GAME_PAGES.get('game-1.html', ''), GAME_PAGES.get('game-2.html', '')
    row = kal_row(gp_tot)
    check(f'{tag}: H in play, the total\'s game page shows its own pinned NO price (KAL -133, 57c), not the moneyline\'s 41c (+144)',
          rc == 0 and '>Under 6.5</a>' in row and '>KAL -133</a>' in row and 'data-kalpx="no" data-cents="57"' in row
          and 'pre-game snapshot' in row and '+144' not in row, log[-600:] + row)
    m = re.search(r' data-mr="(\d+)"', row)
    rec = records(gp_tot)[int(m.group(1))] if m else {}
    check(f'{tag}: H the total\'s game page market record is (event, exact market, side no) at its own 57c pin',
          (rec.get('src'), rec.get('ev'), rec.get('mkt'), rec.get('side'), rec.get('c')) == ('Kalshi', EV, TK, 'no', 57), rec)
    row = kal_row(gp_ml)
    check(f'{tag}: H the moneyline\'s game page keeps its game-key pin (Blues, KAL +144, 41c, no data-kalpx)',
          '>St. Louis Blues</a>' in row and '>KAL +144</a>' in row and 'data-cents="41"' in row and 'kalpx' not in row, row)
    check(f'{tag}: H the index chips agree (Under KAL -133, Blues KAL +144)',
          label(chip_for(page, KURL)) == 'KAL -133' and label(chip_for(page, GURL)) == 'KAL +144', [label(x) for x in kal_chips(page)])

    # I. side vs lock sanity at pre-game publish (lock = kalshi.cents; tolerance 6c)
    rc, page, log = build(B, card(UNDER), routes(SEVEN))
    check(f'{tag}: I the Oct 2 card passes: Under 6.5, NO ask 57c, lock 57, YES 44c (KAL -133)',
          rc == 0 and label(chip_for(page, KURL)) == 'KAL -133' and 'BUILD FAILED' not in log, log[-400:])
    u = copy.deepcopy(UNDER); u['kalshi']['side'] = 'yes'
    rc, page, log = build(B, card(u), routes(SEVEN))
    check(f'{tag}: I an Under declared YES on an "Over 6.5" market fails (exit 3): an Under there is NO',
          rc == 3 and 'BUILD FAILED: Under 6.5 is the under on %s, whose YES is the over - its side is no, the kalshi block says yes' % TK in log, log[-600:])
    o = copy.deepcopy(OVER); o['kalshi'].update(side='no', cents=57, gate_cents=57)
    rc, page, log = build(B, card(o), routes(SEVEN))
    check(f'{tag}: I an Over declared NO on an "Over 6.5" market fails (exit 3) though its NO ask equals the lock',
          rc == 3 and 'BUILD FAILED: Over 6.5 is the over on %s, whose YES is the over - its side is yes, the kalshi block says no' % TK in log, log[-600:])
    UNDER_MKT = total_mkt('7', '0.57', '0.44', title='Under 7 goals', yes_sub_title='Under 6.5 goals scored')
    u = copy.deepcopy(UNDER); u['kalshi']['side'] = 'yes'
    rc, page, log = build(B, card(u), routes(UNDER_MKT))
    ch = chip_for(page, KURL)
    check(f'{tag}: I on an "Under 6.5" market the Under is YES: side yes at the 57c YES ask ships (KAL -133, data-kalpx yes)',
          rc == 0 and label(ch) == 'KAL -133' and attr(ch, 'kalpx') == 'yes', log[-400:] + ch)
    rc, page, log = build(B, card(UNDER), routes(UNDER_MKT))
    check(f'{tag}: I on an "Under 6.5" market an Under declared NO fails (exit 3)',
          rc == 3 and 'whose YES is the under - its side is yes, the kalshi block says no' in log, log[-600:])
    for title, ysub in (('St. Louis at Dallas: Total Goals', '7 or more goals'), ('Over/Under 6.5 goals', 'Over/Under 6.5 goals')):
        amb = total_mkt('7', '0.44', '0.57', title=title, yes_sub_title=ysub)
        rc, page, log = build(B, card(UNDER), routes(amb))
        check(f'{tag}: I a title naming no single direction ({title!r}) is not read: the NO Under at its lock ships',
              rc == 0 and label(chip_for(page, KURL)) == 'KAL -133', log[-400:])
    rc, page, log = build(B, card(u), routes(total_mkt('7', '0.44', '0.57', title='Total Goals', yes_sub_title='7 or more goals')))
    check(f'{tag}: I direction unread, the lock still catches a swapped side: YES 44c is 13c from the 57c lock (exit 3)',
          rc == 3 and 'BUILD FAILED: Under 6.5 Kalshi YES ask 44c on %s is 13c from the 57c lock (tolerance 6c)' % TK in log, log[-600:])
    SIX = total_mkt('6', '0.62', '0.39')
    wrong = copy.deepcopy(UNDER); wrong['kalshi']['ticker'] = EV + '-6'
    rc, page, log = build(B, card(wrong), routes(SEVEN, extra=[SIX]))
    check(f'{tag}: I a pick bound to the neighbouring line (Over 5.5, NO 39c) fails: 18c from the 57c lock (exit 3)',
          rc == 3 and 'BUILD FAILED: Under 6.5 Kalshi NO ask 39c on %s-6 is 18c from the 57c lock (tolerance 6c)' % EV in log, log[-600:])
    rc, page, log = build(B, card(UNDER), routes(total_mkt('7', '0.30', '0.51')))
    check(f'{tag}: I a NO ask 6c under the lock is inside the tolerance and ships at the lock (KAL -133)',
          rc == 0 and label(chip_for(page, KURL)) == 'KAL -133', log[-400:])
    rc, page, log = build(B, card(UNDER), routes(total_mkt('7', '0.30', '0.50')))
    check(f'{tag}: I a NO ask 7c under the lock is past the tolerance (exit 3)',
          rc == 3 and 'NO ask 50c on %s is 7c from the 57c lock (tolerance 6c)' % TK in log, log[-600:])
    swp = copy.deepcopy(LEAFS); swp['kalshi'].update(side='yes', cents=51, gate_cents=51)
    rc, page, log = build(B, card(swp), routes(SEVEN, poison=False))
    check(f'{tag}: I a 51c lock on a YES 50c / NO 51c market declared YES fails: the NO ask is the closer one (exit 3)',
          rc == 3 and 'BUILD FAILED: Maple Leafs ML NO ask 51c on %s-TOR is closer to the 51c lock than the picked YES ask 50c' % LEV in log, log[-600:])
    u = copy.deepcopy(UNDER); u['kalshi'].update(cents=50, gate_cents=51)
    rc, page, log = build(B, card(u), routes(total_mkt('7', '0.50', '0.51')))
    check(f'{tag}: I a NO pick locked at 50c on a YES 50c / NO 51c market fails: the YES ask sits on the lock (exit 3)',
          rc == 3 and 'YES ask 50c on %s is closer to the 50c lock than the picked NO ask 51c' % TK in log, log[-600:])
    LEAFS_YES_TIE = copy.deepcopy(LEAFS); LEAFS_YES_TIE['kalshi']['side'] = 'yes'
    tie = [[r'trade-api/v2/markets/' + LEV + r'-TOR(\?|$)', {'market': dict(LEAFS_MKTS[0], no_ask_dollars='0.50')}]] + routes(SEVEN, poison=False)
    rc, page, log = build(B, card(LEAFS_YES_TIE), tie)  # first matching route wins: TOR answers YES 50c / NO 50c
    check(f'{tag}: I an explicit YES at a 50c lock on a YES 50c / NO 50c market ships (a tie is not closer)',
          rc == 0 and attr(chip_for(page, LURL), 'kalpx') == 'yes' and attr(chip_for(page, LURL), 'cents') == '50', log[-400:])
    # The lock checks are price checks: they stay out of every non-publish path. A settled pick and a display-only
    # rebuild of the published card (bound when it shipped) keep their existing paths entirely: the wrong-line pick
    # builds and wears its lock. The market binding is not a price check, so a refresh or in-play build of a card that
    # is not the published one binds the market again (R below): there the wrong-line pick fails, with no lock check.
    live_wrong = card(dict(copy.deepcopy(wrong), game=dict(wrong['game'], commence=PAST)))
    for what, mf, kw in (('settled', card(dict(copy.deepcopy(wrong), result='WIN')), {}),
                         ('display-only refresh', card(wrong), {'refresh': True, 'files': published(B, card(wrong))}),
                         ('display-only in-play', live_wrong, {'files': published(B, live_wrong)})):
        rc, page, log = build(B, mf, routes(SEVEN, extra=[SIX]), **kw)
        check(f'{tag}: I {what} build of the wrong-line pick keeps its existing path (exit 0, chip at the 57c lock)',
              rc == 0 and label(chip_for(page, KURL)) == 'KAL -133' and 'from the 57c lock' not in log, log[-600:])
    mf = card(wrong)
    rc, page, log = build(B, mf, routes(SEVEN, extra=[SIX]), files=published(B, mf))
    check(f'{tag}: I display-only build of the wrong-line pick keeps its existing path (exit 0, chip at the 57c lock)',
          rc == 0 and 'DISPLAY-ONLY' in log and label(chip_for(page, KURL)) == 'KAL -133' and 'from the 57c lock' not in log, log[-600:])
    for what, mf, kw, msg in (('refresh', card(wrong), {'refresh': True}, "the YES of %s-6 is 'Over 5.5 goals scored', line 5.5: the pick's line is 6.5" % EV),
                              ('in-play', live_wrong, {}, 'event %s is dated %s' % (EV, D))):
        rc, page, log = build(B, mf, routes(SEVEN, extra=[SIX]), **kw)
        check(f'{tag}: I a {what} build of the wrong-line pick, not the published card, binds its market and fails (exit 3) with no lock check',
              rc == 3 and 'BUILD FAILED: Under 6.5 - ' + msg in log and 'from the 57c lock' not in log and not page, log[-600:])

    # J. the explicit ticker must be a market of the url's event
    for what, url in (("another event's url", LURL), ('an event url that is only a prefix of the ticker', 'https://kalshi.com/markets/kxnhltotal/' + EV[:-3].lower()),
                      ('no url', None)):
        bad = copy.deepcopy(UNDER)
        if url: bad['kalshi']['url'] = url
        else: bad['kalshi'].pop('url')
        rc, page, log = build(B, card(bad), routes(SEVEN))
        check(f'{tag}: J {what} fails the build (exit 3)',
              rc == 3 and 'BUILD FAILED: kalshi ticker %s is not a market of the url\'s event' % TK in log and not page, log[-600:])
    old = copy.deepcopy(LEAFS); old['kalshi']['ticker'] = TK
    rc, page, log = build(B, card(old), routes(SEVEN))
    check(f'{tag}: J an old pick (no side) is not held to it: a foreign ticker still builds the team-matched chip',
          rc == 0 and attr(chip_for(page, LURL), 'kalside') == 'TOR' and attr(chip_for(page, LURL), 'cents') == '50', log[-400:])
    for what, url in (('a series-level url (names no event) with another game\'s market', 'https://kalshi.com/markets/kxnhltotal'),
                      ('a series-level url with the pick\'s own market', 'https://kalshi.com/markets/kxnhltotal/'),
                      ('a market-level url', KURL + '-7')):
        bad = copy.deepcopy(UNDER); bad['kalshi']['url'] = url
        if 'another game' in what: bad['kalshi']['ticker'] = 'KXNHLTOTAL-' + D + 'BOSCHI-7'
        other = dict(total_mkt('7', '0.45', '0.56'), ticker='KXNHLTOTAL-' + D + 'BOSCHI-7')
        rc, page, log = build(B, card(bad), routes(SEVEN, extra=[other]))
        check(f'{tag}: J {what} fails the build (exit 3): the url must end at the event itself',
              rc == 3 and 'BUILD FAILED: kalshi ticker %s is not a market of the url\'s event' % bad['kalshi']['ticker'] in log and not page, log[-600:])
    ok_url = copy.deepcopy(UNDER); ok_url['kalshi']['url'] = 'https://kalshi.com/markets/kxnhltotal/total-goals/' + EV.lower() + '/'
    rc, page, log = build(B, card(ok_url), routes(SEVEN))
    check(f'{tag}: J an event url with a slug segment and a trailing slash still binds (KAL -133)',
          rc == 0 and label(chip_for(page, ok_url['kalshi']['url'])) == 'KAL -133', log[-400:])

    # L. two explicit props on one game and one line: each pin is its own market + side, never one shared slot
    rc, page, log = build(B, card(prop_pick('Robert Thomas', PTA, 38, SOON), prop_pick('Jason Robertson', PTB, 45, SOON)),
                          PROP_ROUTES + routes(SEVEN), extra_env={'RP_PUBLISH': '1'})
    pk = 'St. Louis Blues|Dallas Stars|' + SOON[:10] + '|prop|0.5'
    pins = {k: (v.get('Kalshi') or {}).get('cents') for k, v in LEDGER.items() if k != '__card__' and (v or {}).get('Kalshi')}
    check(f'{tag}: L the approved publish of two explicit props on one game and line writes two Kalshi pins, each under its market + side',
          rc == 0 and pins == {pk + '|' + PTA + '|yes': 38, pk + '|' + PTB + '|yes': 45}, log[-400:] + str(pins))
    PK = 'St. Louis Blues|Dallas Stars|' + PAST[:10] + '|prop|0.5'
    # in play: own pins 40 / 47 (distinct from the 38 / 45 locks), plus the shared class-key slot an earlier build wrote (45)
    led = {PK: {'Kalshi': {'link': PURL, 'cents': 45, 'commence': PAST}},
           PK + '|' + PTA + '|yes': {'Kalshi': {'link': PURL, 'cents': 40, 'commence': PAST}},
           PK + '|' + PTB + '|yes': {'Kalshi': {'link': PURL, 'cents': 47, 'commence': PAST}}}
    # in play these are rebuilds of the published card (its props' event is dated from SOON, the publish above)
    for refresh in (False, True):
        mf = card(prop_pick('Robert Thomas', PTA, 38, PAST), prop_pick('Jason Robertson', PTB, 45, PAST))
        rc, page, log = build(B, mf, PROP_ROUTES + routes(SEVEN), refresh=refresh, files=dict({'shipped_books.json': json.dumps(led)}, **published(B, mf)))
        got = []
        for gpn, tk in (('game-1.html', PTA), ('game-2.html', PTB)):
            gp = GAME_PAGES.get(gpn, ''); row = kal_row(gp); m = re.search(r' data-mr="(\d+)"', row)
            rec = records(gp)[int(m.group(1))] if m else {}
            got.append((re.sub(r'<[^>]+>', ' ', row).split()[-3:-2], '%s-%s' % (attr(row, 'kalticker'), attr(row, 'kalside')), rec.get('mkt'), rec.get('c')))
        check(f'{tag}: L in play (refresh={refresh}) each prop\'s game page wears its own pin and market (Thomas 40c +150, Robertson 47c +113), never the shared 45c slot',
              rc == 0 and got == [(['+150'], PTA, PTA, 40), (['+113'], PTB, PTB, 47)], log[-400:] + str(got))
    mf = card(prop_pick('Robert Thomas', PTA, 38, PAST))
    rc, page, log = build(B, mf, PROP_ROUTES + routes(SEVEN), refresh=True, files=dict({'shipped_books.json': json.dumps({PK: led[PK]})}, **published(B, mf)))
    row = kal_row(GAME_PAGES.get('game-1.html', ''))
    check(f'{tag}: L an explicit prop never inherits the shared class-key slot (45c): with no pin of its own it wears its 38c lock (+163)',
          rc == 0 and '>KAL +163</a>' in row and 'data-cents="38"' in row, log[-400:] + row)

    # M. moneyline side bound to the team at pre-game publish (a near-even swap passes the lock checks)
    sw = copy.deepcopy(LEAFS); sw['kalshi'].update(side='no', cents=50, gate_cents=50)
    tor = dict(LEAFS_MKTS[0], yes_ask_dollars='0.51', no_ask_dollars='0.50')
    near = [[r'trade-api/v2/markets/' + LEV + r'-TOR(\?|$)', {'market': tor}]] + routes(SEVEN, poison=False)
    rc, page, log = build(B, card(sw), near)
    check(f'{tag}: M Toronto ML declared NO on Toronto\'s own market (YES 51c / NO 50c, lock 50) fails (exit 3): its side is yes',
          rc == 3 and "BUILD FAILED: Maple Leafs ML - the YES of %s-TOR is 'Toronto', the picked team: its side is yes, the kalshi block says no" % LEV in log and not page, log[-600:])
    rc, page, log = build(B, card(sw), near, refresh=True)
    check(f'{tag}: M the same card on a refresh build, not the published card, has its side bound again: fails (exit 3)',
          rc == 3 and "BUILD FAILED: Maple Leafs ML - the YES of %s-TOR is 'Toronto', the picked team: its side is yes, the kalshi block says no" % LEV in log, log[-600:])
    rc, page, log = build(B, card(sw), near, refresh=True, files=published(B, card(sw)))
    check(f'{tag}: M a refresh of the published card keeps its existing path (its side was bound when it shipped)', rc == 0, log[-400:])
    nom = copy.deepcopy(LEAFS); nom['kalshi'].update(ticker=LEV + '-MTL', side='no', cents=50, gate_cents=50)
    rc, page, log = build(B, card(nom), routes(SEVEN, poison=False))
    ch = chip_for(page, LURL)
    check(f'{tag}: M Toronto ML as NO on Montreal\'s market of a two-way event ships at the NO ask (KAL -100, data-kalpx no, pair -MTL)',
          rc == 0 and label(ch) == 'KAL -100' and attr(ch, 'kalpx') == 'no' and '%s-%s' % (attr(ch, 'kalticker'), attr(ch, 'kalside')) == LEV + '-MTL', log[-400:] + ch)
    yom = copy.deepcopy(LEAFS); yom['kalshi'].update(ticker=LEV + '-MTL', side='yes', cents=51, gate_cents=51)
    rc, page, log = build(B, card(yom), routes(SEVEN, poison=False))
    check(f'{tag}: M Toronto ML declared YES on Montreal\'s market fails (exit 3): the opponent\'s YES is the pick\'s NO',
          rc == 3 and "the YES of %s-MTL is 'Montreal', the opponent: its side is no, the kalshi block says yes" % LEV in log, log[-600:])
    three = LEAFS_MKTS + [{'ticker': LEV + '-TIE', 'title': 'Tie', 'yes_sub_title': 'Tie', 'yes_ask_dollars': '0.20', 'no_ask_dollars': '0.81'}]
    rt3 = [[r'markets\?event_ticker=' + LEV + '&', {'markets': three}]] + routes(SEVEN, poison=False)
    rc, page, log = build(B, card(nom), rt3)
    check(f'{tag}: M NO on the opponent\'s market of a three-way event fails (exit 3): a NO there is not the picked team\'s win',
          rc == 3 and 'is the picked team\'s win only on a two-way event; %s lists 3 market(s)' % LEV in log, log[-600:])
    both = [[r'trade-api/v2/markets/' + LEV + r'-TOR(\?|$)', {'market': dict(LEAFS_MKTS[0], yes_sub_title='Montreal vs Toronto')}]] + routes(SEVEN, poison=False)
    unb = copy.deepcopy(LEAFS); unb['kalshi'].update(side='yes', team='')
    rc, page, log = build(B, card(unb), both)
    check(f'{tag}: M a market whose YES names both teams (and no kalshi.team) cannot bind the side: fails (exit 3)',
          rc == 3 and 'names neither team of the pick or both, so side yes cannot be bound' in log, log[-600:])
    rc, page, log = build(B, card(YANKS), YROUTES)
    ch = chip_for(page, YURL)
    check(f'{tag}: M same-city teams (New York Y / New York M): the market\'s own code NYY (ESPN\'s Yankees) binds the YES side (ships, 52c)',
          rc == 0 and attr(ch, 'kalpx') == 'yes' and attr(ch, 'cents') == '52', log[-400:] + ch)
    ym = copy.deepcopy(YANKS); ym['kalshi'].update(ticker=YEV + '-NYM', side='yes', cents=49, gate_cents=49)
    rc, page, log = build(B, card(ym), YROUTES)
    check(f'{tag}: M same-city teams: YES on the Mets\' market (code NYM, the opponent) fails (exit 3)',
          rc == 3 and "BUILD FAILED: Yankees ML - the YES of %s-NYM is 'New York M', the opponent: its side is no, the kalshi block says yes" % YEV in log, log[-600:])

    # P. the original intent end to end: a + run line priced from its NO ask; the YES side unchanged
    rc, page, log = build(B, card(SOX), spread_routes())
    ch = chip_for(page, SURL)
    check(f'{tag}: P White Sox +1.5 (NO on "Houston wins by over 1.5", NO 66c / YES 35c) ships at the NO ask: KAL -194, data-cents 66, data-kalpx no',
          rc == 0 and label(ch) == 'KAL -194' and attr(ch, 'cents') == '66' and attr(ch, 'kalpx') == 'no'
          and '%s-%s' % (attr(ch, 'kalticker'), attr(ch, 'kalside')) == STK, log[-400:] + ch)
    rec = records(page)[int(attr(ch, 'mr'))] if attr(ch, 'mr') else {}
    check(f'{tag}: P its market record is (event, exact market, side no) at 66c', (rec.get('ev'), rec.get('mkt'), rec.get('side'), rec.get('c')) == (SEV, STK, 'no', 66), rec)
    row = kal_row(GAME_PAGES.get('game-1.html', ''))
    check(f'{tag}: P its game page row: Chicago White Sox at KAL -194, data-kalpx no, never the YES board',
          '>Chicago White Sox</a>' in row and '>KAL -194</a>' in row and 'data-kalpx="no" data-cents="66"' in row, row)
    if ch:
        t = run_tick(page, 'rpKalTick', [{'dataset': ds(ch), 'innerHTML': 'KAL -194'}], {STK: dict(HOU2, no_ask_dollars='0.70', yes_ask_dollars='0.31')})
        a = (t.get('anchors') or [{}])[0]
        check(f'{tag}: P the client tick reads the run line\'s NO ask (70c -> KAL -233, not the 31c YES)',
              t.get('fetched') == [STK] and a.get('dataset', {}).get('cents') == 70 and a.get('innerHTML') == 'KAL -233', t)
    rc, page, log = build(B, card(ASTROS), spread_routes())
    ch = chip_for(page, SURL)
    check(f'{tag}: P Astros -1.5 (YES on the same market) still reads the YES ask: KAL +186, data-cents 35, data-kalpx yes',
          rc == 0 and label(ch) == 'KAL +186' and attr(ch, 'cents') == '35' and attr(ch, 'kalpx') == 'yes', log[-400:] + ch)
    sw = copy.deepcopy(SOX); sw['kalshi'].update(side='yes')
    rc, page, log = build(B, card(sw), spread_routes(dict(HOU2, yes_ask_dollars='0.66', no_ask_dollars='0.35')))
    check(f'{tag}: P White Sox +1.5 declared YES on Houston\'s market fails (exit 3) even when the YES ask sits on the lock',
          rc == 3 and "the YES of %s is 'Houston wins by over 1.5 runs', the opponent: its side is no, the kalshi block says yes" % STK in log, log[-600:])

    # Q. the market itself is bound to the pick (pre-game publish). Each failing case reads its ticker AND its lock off
    # the same wrong market, so the side and lock checks above see nothing wrong; before Q each one shipped (exit 0).
    def qfail(what, rc, page, log, msg):
        check(f'{tag}: Q {what} fails the build (exit 3, no page)', rc == 3 and msg in log and not page, log[-600:])
    CWS2 = {'ticker': SEV + '-CWS2', 'title': 'Chicago WS wins by over 1.5 runs?', 'yes_sub_title': 'Chicago WS wins by over 1.5 runs',
            'yes_ask_dollars': '0.22', 'no_ask_dollars': '0.79', 'status': 'active'}
    cws2 = [[r'trade-api/v2/markets/' + SEV + r'-CWS2(\?|$)', {'market': CWS2}]]
    q = copy.deepcopy(SOX); q['kalshi'].update(ticker=SEV + '-CWS2', side='yes', cents=22, gate_cents=22)
    qfail('White Sox +1.5 declared YES on "Chicago WS wins by over 1.5" (22c lock): that YES is White Sox -1.5', *build(B, card(q), cws2),
          "BUILD FAILED: White Sox +1.5 - the YES of %s-CWS2 is 'Chicago WS wins by over 1.5 runs', the picked team by over 1.5: it binds the pick at -1.5, the pick's line is +1.5" % SEV)
    q = copy.deepcopy(ASTROS); q['kalshi'].update(ticker=SEV + '-CWS2', side='no', cents=79, gate_cents=79)
    qfail('Astros -1.5 declared NO on "Chicago WS wins by over 1.5" (79c lock): that NO is Houston +1.5', *build(B, card(q), cws2),
          "the YES of %s-CWS2 is 'Chicago WS wins by over 1.5 runs', the opponent by over 1.5: it binds the pick at +1.5, the pick's line is -1.5" % SEV)
    q = copy.deepcopy(SOX); q['name'] = 'White Sox +2.5'; q['line'] = -2.5
    qfail('White Sox +2.5 bound to the 1.5 run line (NO 66c lock)', *build(B, card(q), spread_routes()),
          "BUILD FAILED: White Sox +2.5 - the YES of %s is 'Houston wins by over 1.5 runs', the opponent by over 1.5: it binds the pick at +1.5, the pick's line is +2.5" % STK)
    q = copy.deepcopy(UNDER); q['kalshi'].update(ticker=EV + '-6', cents=39, gate_cents=39)
    qfail('Under 6.5 bound to the Over 5.5 market with its own NO 39c lock', *build(B, card(q), routes(SEVEN, extra=[SIX])),
          "BUILD FAILED: Under 6.5 - the YES of %s-6 is 'Over 5.5 goals scored', line 5.5: the pick's line is 6.5" % EV)
    q = copy.deepcopy(UNDER)
    rc, page, log = build(B, card(q), routes(total_mkt('7', '0.44', '0.57', title='St. Louis at Dallas: Total Goals', yes_sub_title='Total goals')))
    qfail('a total whose market names no line', rc, page, log,
          "BUILD FAILED: Under 6.5 - the line of %s cannot be read from its market ('Total goals'), so it cannot be bound to the pick's 6.5" % TK)
    q = dict(copy.deepcopy(ASTROS), name='Astros ML', market_class='ml'); q.pop('line')
    qfail('Astros ML bound to the run-line market (YES 35c lock)', *build(B, card(q), spread_routes()),
          'BUILD FAILED: Astros ML is a ml pick and %s is a spread market (series KXMLBSPREAD)' % STK)
    OEV = 'KXNHLTOTAL-' + D + 'BOSNYR'
    q = copy.deepcopy(UNDER); q['kalshi'].update(url='https://kalshi.com/markets/kxnhltotal/' + OEV.lower(), ticker=OEV + '-7', cents=71, gate_cents=71)
    qfail('STL @ DAL Under 6.5 bound to the BOS @ NYR total (NO 71c lock)',
          *build(B, card(q), [[r'trade-api/v2/markets/' + OEV + r'-7(\?|$)', {'market': dict(total_mkt('7', '0.30', '0.71'), ticker=OEV + '-7')}]]),
          'BUILD FAILED: Under 6.5 - event %s is game BOSNYR, not St. Louis Blues at Dallas Stars' % OEV)
    NEV = 'KXNHLTOTAL-' + dtok((datetime.datetime.fromisoformat(FUT.replace('Z', '+00:00')) + datetime.timedelta(days=1)).strftime('%Y-%m-%dT%H:%MZ')) + 'STLDAL'
    q = copy.deepcopy(UNDER); q['kalshi'].update(url='https://kalshi.com/markets/kxnhltotal/' + NEV.lower(), ticker=NEV + '-7')
    qfail('the same teams\' total dated the next day',
          *build(B, card(q), [[r'trade-api/v2/markets/' + NEV + r'-7(\?|$)', {'market': dict(SEVEN, ticker=NEV + '-7')}]]),
          'BUILD FAILED: Under 6.5 - event %s is dated %s, the pick\'s game starts %s' % (NEV, NEV.split('-')[1][:7], FUT))
    # an MLB event carries the Eastern start: the commence's own start binds, a doubleheader's other game does not
    for what, when, ok in (('its own start', FUT, True),
                           ('a doubleheader game 4 hours earlier', (datetime.datetime.fromisoformat(FUT.replace('Z', '+00:00')) - datetime.timedelta(hours=4)).strftime('%Y-%m-%dT%H:%MZ'), False)):
        HEV = 'KXMLBSPREAD-' + dtok(when, hhmm=True) + 'CWSHOU'
        q = copy.deepcopy(SOX); q['kalshi'].update(url='https://kalshi.com/markets/kxmlbspread/' + HEV.lower(), ticker=HEV + '-HOU2')
        rc, page, log = build(B, card(q), [[r'trade-api/v2/markets/' + HEV + r'-HOU2(\?|$)', {'market': dict(HOU2, ticker=HEV + '-HOU2')}]])
        if ok:
            check(f'{tag}: Q an MLB event timed at {what} binds: White Sox +1.5 ships (KAL -194)', rc == 0 and label(chip_for(page, q['kalshi']['url'])) == 'KAL -194', log[-600:])
        else:
            qfail(f'an MLB event timed at {what}', rc, page, log, 'BUILD FAILED: White Sox +1.5 - event %s is dated %s %s ET, the pick\'s game starts %s' % (HEV, HEV.split('-')[1][:7], HEV.split('-')[1][7:11], FUT))
    # props: direction, player, stat and line
    q = prop_pick('Robert Thomas', PTA, 64, SOON); q['kalshi']['side'] = 'no'
    qfail('Robert Thomas Over 0.5 goals declared NO on his own 1+ goals market (NO 64c lock): the Over of an N+ market is YES',
          *build(B, card(q), PROP_ROUTES),
          "BUILD FAILED: Robert Thomas Over 0.5 goals is the over on %s, whose YES is the over - its side is yes, the kalshi block says no" % PTA)
    q = prop_pick('Robert Thomas', PTB, 45, SOON)
    qfail('Robert Thomas bound to Jason Robertson\'s market (YES 45c lock)', *build(B, card(q), PROP_ROUTES),
          "BUILD FAILED: Robert Thomas Over 0.5 goals - %s does not name the pick's player 'Robert Thomas'" % PTB)
    q = prop_pick('Robert Thomas', PTA, 38, SOON); q['name'] = 'Robert Thomas Over 1.5 goals'; q['line'] = 1.5
    qfail('Robert Thomas Over 1.5 goals bound to his 1+ goals market (YES 38c lock)', *build(B, card(q), PROP_ROUTES),
          "BUILD FAILED: Robert Thomas Over 1.5 goals - the YES of %s is 'Robert Thomas: 1+ goals', line 0.5: the pick's line is 1.5" % PTA)
    XEV = 'KXNHLPTS-' + dtok(SOON) + 'STLDAL'
    XM = {'ticker': XEV + '-RTHOMAS1', 'title': 'Robert Thomas: 1+ points', 'yes_sub_title': 'Robert Thomas', 'yes_ask_dollars': '0.61', 'no_ask_dollars': '0.41', 'status': 'active'}
    q = prop_pick('Robert Thomas', XEV + '-RTHOMAS1', 61, SOON); q['kalshi']['url'] = 'https://kalshi.com/markets/kxnhlpts/' + XEV.lower()
    qfail('Robert Thomas Over 0.5 goals bound to his 1+ points market (YES 61c lock)',
          *build(B, card(q), [[r'trade-api/v2/markets/' + XEV + r'-RTHOMAS1(\?|$)', {'market': XM}]]),
          "BUILD FAILED: Robert Thomas Over 0.5 goals - %s does not name the pick's stat (goal)" % (XEV + '-RTHOMAS1'))
    # the good cards still ship: an Under prop on its own N+ market, a fight whose code is home-first
    q = prop_pick('Robert Thomas', PTA, 64, SOON); q.update(name='Robert Thomas Under 0.5 goals', side='under'); q['kalshi']['side'] = 'no'
    rc, page, log = build(B, card(q), PROP_ROUTES)
    check(f'{tag}: Q Robert Thomas Under 0.5 goals as NO on his 1+ goals market ships at the NO ask (KAL -178, data-kalpx no)',
          rc == 0 and label(chip_for(page, PURL)) == 'KAL -178' and attr(chip_for(page, PURL), 'kalpx') == 'no', log[-600:])
    FEV = 'KXUFCFIGHT-' + D + 'ABUSTA'
    FM = {'ticker': FEV + '-ABU', 'title': 'Will Loai Abushaar win?', 'yes_sub_title': 'Loai Abushaar', 'yes_ask_dollars': '0.26', 'no_ask_dollars': '0.75', 'status': 'active'}
    q = {'num': 1, 'name': 'Loai Abushaar ML', 'market_class': 'ml', 'sub': 'Staines vs Abushaar', 'odds': '+285', 'units': '5u', 'side': 'home',
         'game': {'away': 'George Staines', 'home': 'Loai Abushaar', 'commence': FUT, 'eid': ''}, 'espn_league': 'mma/ufc', 'league': 'UFC', 'best_book': 'Kalshi',
         'kalshi': {'url': 'https://kalshi.com/markets/kxufcfight/' + FEV.lower(), 'ticker': FEV + '-ABU', 'side': 'yes', 'cents': 26, 'gate_cents': 26, 'team': 'Abushaar'}}
    rc, page, log = build(B, card(q), [[r'trade-api/v2/markets/' + FEV + r'-ABU(\?|$)', {'market': FM}]])
    check(f'{tag}: Q a fight whose event code names the home fighter first (ABUSTA) binds and ships (KAL +285)',
          rc == 0 and label(chip_for(page, q['kalshi']['url'])) == 'KAL +285', log[-600:])
    # a code the names cannot spell (PSU for Penn State Nittany Lions) binds only through ESPN's own abbreviation
    PSEV = 'KXNCAAFGAME-' + D + 'UCLAPSU'
    PSM = {'ticker': PSEV + '-PSU', 'title': 'UCLA at Penn State Winner?', 'yes_sub_title': 'Penn State', 'yes_ask_dollars': '0.70', 'no_ask_dollars': '0.31', 'status': 'active'}
    q = {'num': 1, 'name': 'Penn State ML', 'market_class': 'ml', 'sub': 'UCLA @ PSU', 'odds': '-233', 'units': '5u', 'side': 'home',
         'game': {'away': 'UCLA Bruins', 'home': 'Penn State Nittany Lions', 'commence': FUT, 'eid': ''}, 'espn_league': 'football/college-football', 'league': 'NCAAF', 'best_book': 'Kalshi',
         'kalshi': {'url': 'https://kalshi.com/markets/kxncaafgame/' + PSEV.lower(), 'ticker': PSEV + '-PSU', 'side': 'yes', 'cents': 70, 'gate_cents': 70, 'team': 'Penn State'}}
    psr = [[r'trade-api/v2/markets/' + PSEV + r'-PSU(\?|$)', {'market': PSM}]]
    espn = [[r'site\.api\.espn\.com/apis/site/v2/sports/football/college-football/scoreboard', {'events': [{'competitions': [{'competitors': [
        {'team': {'id': '213', 'displayName': 'Penn State Nittany Lions', 'abbreviation': 'PSU'}}, {'team': {'id': '26', 'displayName': 'UCLA Bruins', 'abbreviation': 'UCLA'}}]}]}]}]]
    qfail('a Penn State game coded UCLAPSU with no abbreviation source for PSU', *build(B, card(q), psr),
          'BUILD FAILED: Penn State ML - event %s is game UCLAPSU, not UCLA Bruins at Penn State Nittany Lions' % PSEV)
    rc, page, log = build(B, card(q), psr + espn)
    check(f'{tag}: Q the same Penn State game binds through ESPN\'s abbreviation PSU and ships (KAL -233)',
          rc == 0 and label(chip_for(page, q['kalshi']['url'])) == 'KAL -233', log[-600:])

    # R. the binding holds against the second review (Oct 6). Each failing case reads its ticker AND its lock off the
    # same wrong market; on the previous head each one shipped (exit 0).
    def rfail(what, rc, page, log, msg):
        check(f'{tag}: R {what} fails the build (exit 3, no page)', rc == 3 and msg in log and not page, log[-600:])
    def tot(away, home, lg, league, line, ev, no_c, unit='goals', commence=FUT, side='no', yes_c=None):
        # an Under on the 'Over <line>' market of event ev, its lock the NO ask (or, side yes, the YES ask yes_c)
        tk = ev + '-' + str(int(line + 0.5))
        mk = {'ticker': tk, 'title': 'Over %d %s' % (int(line + 0.5), unit), 'yes_sub_title': 'Over %g %s scored' % (line, unit),
              'yes_ask_dollars': '%.2f' % ((yes_c or (101 - no_c)) / 100), 'no_ask_dollars': '%.2f' % (no_c / 100), 'status': 'active'}
        url = 'https://kalshi.com/markets/' + ev.split('-')[0].lower() + '/' + ev.lower()
        c = no_c if side == 'no' else yes_c
        pk = {'num': 1, 'name': 'Under %g' % line, 'market_class': 'total', 'line': line, 'sub': '', 'odds': '-110', 'units': '5u', 'side': 'under',
              'game': {'away': away, 'home': home, 'commence': commence, 'eid': ''}, 'espn_league': lg, 'league': league, 'best_book': 'Kalshi',
              'kalshi': {'url': url, 'ticker': tk, 'side': side, 'cents': c, 'gate_cents': c, 'team': ''}}
        return pk, [[r'trade-api/v2/markets/' + tk + r'(\?|$)', {'market': mk}]], url
    # a total's event code is its only binding to its game: a team code binds only as ESPN's abbreviation of that team.
    # Spelt from the name, BOS read as Buffalo Sabres, CAR as Calgary Flames, COL as Columbus, TB as Toronto Blue Jays.
    for what, args, code, teams in (
            ('BUF @ CGY Under 6.5 on the BOS @ CAR total of the same night (NO 57c lock)',
             ('Buffalo Sabres', 'Calgary Flames', 'hockey/nhl', 'NHL', 6.5, 'KXNHLTOTAL-' + D + 'BOSCAR', 57), 'BOSCAR', 'Buffalo Sabres at Calgary Flames'),
            ('ANA @ CBJ Under 5.5 on the COL @ UTAH total of the same night (NO 52c lock)',
             ('Anaheim Ducks', 'Columbus Blue Jackets', 'hockey/nhl', 'NHL', 5.5, 'KXNHLTOTAL-' + D + 'COLUTAH', 52), 'COLUTAH', 'Anaheim Ducks at Columbus Blue Jackets'),
            ('ARI @ BUF Under 44.5 on the BAL @ CIN total of the same day (NO 55c lock)',
             ('Arizona Cardinals', 'Buffalo Bills', 'football/nfl', 'NFL', 44.5, 'KXNFLTOTAL-' + D + 'BALCIN', 55, 'points'), 'BALCIN', 'Arizona Cardinals at Buffalo Bills'),
            ('BAL @ TOR Under 8.5 on the TB @ BOS total timed at the same start (NO 54c lock)',
             ('Baltimore Orioles', 'Toronto Blue Jays', 'baseball/mlb', 'MLB', 8.5, 'KXMLBTOTAL-' + dtok(FUT, hhmm=True) + 'TBBOS', 54, 'runs'), 'TBBOS', 'Baltimore Orioles at Toronto Blue Jays')):
        pk, rt, url = tot(*args)
        rfail(what, *build(B, card(pk), rt), 'BUILD FAILED: Under %g - event %s is game %s, not %s' % (args[4], args[5], code, teams))
    for what, args, cents in (('BUF @ CGY Under 6.5 on its own BUF @ CGY total', ('Buffalo Sabres', 'Calgary Flames', 'hockey/nhl', 'NHL', 6.5, 'KXNHLTOTAL-' + D + 'BUFCGY', 57), 'KAL -133'),
                              ('CHI @ UTAH Under 6.5 on Kalshi\'s CHIUTA (UTA for ESPN\'s UTAH)', ('Chicago Blackhawks', 'Utah Mammoth', 'hockey/nhl', 'NHL', 6.5, 'KXNHLTOTAL-' + D + 'CHIUTA', 57), 'KAL -133'),
                              ('BAL @ TOR Under 8.5 on its own total timed at its start', ('Baltimore Orioles', 'Toronto Blue Jays', 'baseball/mlb', 'MLB', 8.5, 'KXMLBTOTAL-' + dtok(FUT, hhmm=True) + 'BALTOR', 54, 'runs'), 'KAL -117')):
        pk, rt, url = tot(*args)
        rc, page, log = build(B, card(pk), rt)
        check(f'{tag}: R {what} binds through ESPN\'s abbreviations and ships ({cents})', rc == 0 and label(chip_for(page, url)) == cents, log[-600:])
    rc, page, log = build(B, card(UNDER), routes(SEVEN), espn=False)
    rfail('a total whose teams ESPN gives no abbreviation for (ESPN unreachable)', rc, page, log,
          'BUILD FAILED: Under 6.5 - ESPN gives no abbreviation for St. Louis Blues or Dallas Stars (hockey/nhl)')
    # a prop names its player in full (Matthew, not only Tkachuk), or its text gives his initial and its ticker his
    # initial and surname (FLAMTKACHUK19): a same-surname teammate's or opponent's market never binds
    TKE = 'KXNHLGOAL-' + D + 'OTTFLA'
    TKURL = 'https://kalshi.com/markets/kxnhlgoal/' + TKE.lower()
    def tk_mkt(sfx, title, ya, na):
        return {'ticker': TKE + '-' + sfx, 'title': title + ': 1+ goals', 'yes_sub_title': title, 'yes_ask_dollars': ya, 'no_ask_dollars': na, 'status': 'active'}
    def tk_pick(player, sfx, cents):
        q = prop_pick(player, TKE + '-' + sfx, cents, FUT)
        q.update(sub='OTT @ FLA', game={'away': 'Ottawa Senators', 'home': 'Florida Panthers', 'commence': FUT, 'eid': ''})
        q['kalshi']['url'] = TKURL
        return q
    BTK, MTK, MTKB = tk_mkt('BTKACHUK7', 'Brady Tkachuk', '0.36', '0.66'), tk_mkt('FLAMTKACHUK19', 'M. Tkachuk', '0.40', '0.62'), tk_mkt('OTTBTKACHUK7', 'M. Tkachuk', '0.40', '0.62')
    tkr = [[r'trade-api/v2/markets/' + m['ticker'] + r'(\?|$)', {'market': m}] for m in (BTK, MTK, MTKB)]
    rfail('Matthew Tkachuk Over 0.5 goals on Brady Tkachuk\'s 1+ goals market (YES 36c lock)', *build(B, card(tk_pick('Matthew Tkachuk', 'BTKACHUK7', 36)), tkr),
          "BUILD FAILED: Matthew Tkachuk Over 0.5 goals - %s-BTKACHUK7 does not name the pick's player 'Matthew Tkachuk'" % TKE)
    rfail('Matthew Tkachuk on a market reading "M. Tkachuk" whose ticker names B Tkachuk (YES 40c lock)', *build(B, card(tk_pick('Matthew Tkachuk', 'OTTBTKACHUK7', 40)), tkr),
          "BUILD FAILED: Matthew Tkachuk Over 0.5 goals - %s-OTTBTKACHUK7 does not name the pick's player 'Matthew Tkachuk'" % TKE)
    for what, q, cents in (('Matthew Tkachuk on "M. Tkachuk" with the ticker FLAMTKACHUK19', tk_pick('Matthew Tkachuk', 'FLAMTKACHUK19', 40), 'KAL +150'),
                           ('Brady Tkachuk on his own market', tk_pick('Brady Tkachuk', 'BTKACHUK7', 36), 'KAL +178')):
        rc, page, log = build(B, card(q), tkr)
        check(f'{tag}: R {what} binds and ships ({cents})', rc == 0 and label(chip_for(page, TKURL)) == cents, log[-600:])
    HEV = 'KXNHLGOAL-' + D + 'NJCAR'
    LH = {'ticker': HEV + '-NJLHUGHES43', 'title': 'Luke Hughes: 1+ goals', 'yes_sub_title': 'Luke Hughes', 'yes_ask_dollars': '0.20', 'no_ask_dollars': '0.82', 'status': 'active'}
    q = prop_pick('Jack Hughes', HEV + '-NJLHUGHES43', 20, FUT)
    q.update(sub='NJ @ CAR', game={'away': 'New Jersey Devils', 'home': 'Carolina Hurricanes', 'commence': FUT, 'eid': ''})
    q['kalshi']['url'] = 'https://kalshi.com/markets/kxnhlgoal/' + HEV.lower()
    rfail('Jack Hughes Over 0.5 goals on his teammate Luke Hughes\'s market (YES 20c lock)', *build(B, card(q), [[r'trade-api/v2/markets/' + LH['ticker'] + r'(\?|$)', {'market': LH}]]),
          "BUILD FAILED: Jack Hughes Over 0.5 goals - %s-NJLHUGHES43 does not name the pick's player 'Jack Hughes'" % HEV)
    # same-city moneyline: when the names cannot tell the teams apart the market's own code decides (NYM is ESPN's
    # Mets), never kalshi.team, which is part of the block being checked
    for team in ('NYM', 'New York M'):
        q = copy.deepcopy(YANKS); q['kalshi'].update(ticker=YEV + '-NYM', side='yes', cents=49, gate_cents=49, team=team)
        rfail(f'Yankees ML declared YES on the Mets\' market with kalshi.team {team!r} (YES 49c lock)', *build(B, card(q), YROUTES),
              "BUILD FAILED: Yankees ML - the YES of %s-NYM is 'New York M', the opponent: its side is no, the kalshi block says yes" % YEV)
    q = copy.deepcopy(YANKS); q['kalshi'].update(ticker=YEV + '-NYM', side='no', cents=52, gate_cents=52)
    rc, page, log = build(B, card(q), YROUTES)
    ch = chip_for(page, YURL)
    check(f'{tag}: R Yankees ML as NO on the Mets\' market of a two-way event binds through its code and ships (52c NO, data-kalpx no)',
          rc == 0 and attr(ch, 'kalpx') == 'no' and attr(ch, 'cents') == '52', log[-600:] + ch)
    # an approved publish of a pick whose game is under way binds its market too (no lock check: an in-play ask is not
    # an entry price). Its event is dated from the in-play commence.
    EVP = 'KXNHLTOTAL-' + dtok(PAST) + 'STLDAL'
    KURLP = 'https://kalshi.com/markets/kxnhltotal/' + EVP.lower()
    SEVENP, SIXP = dict(SEVEN, ticker=EVP + '-7'), dict(total_mkt('6', '0.62', '0.39'), ticker=EVP + '-6')
    def live_routes(seven=SEVENP):
        return [[r'trade-api/v2/markets/' + EVP + r'-7(\?|$)', {'market': seven}], [r'trade-api/v2/markets/' + EVP + r'-6(\?|$)', {'market': SIXP}],
                [r'markets\?event_ticker=' + EVP + '&', {'markets': [SIXP, seven]}]]
    ULP = copy.deepcopy(UNDER); ULP['game']['commence'] = PAST; ULP['kalshi'].update(url=KURLP, ticker=EVP + '-7')
    PUB = {'RP_PUBLISH': '1'}
    q = copy.deepcopy(ULP); q['kalshi'].update(side='yes', cents=44, gate_cents=44)
    rfail('an in-play publish of the Under declared YES on the "Over 6.5" market (YES 44c lock)', *build(B, card(q), live_routes(), extra_env=PUB),
          'BUILD FAILED: Under 6.5 is the under on %s-7, whose YES is the over - its side is no, the kalshi block says yes' % EVP)
    q = copy.deepcopy(ULP); q['kalshi'].update(ticker=EVP + '-6', cents=39, gate_cents=39)
    rfail('an in-play publish of the Under 6.5 on the Over 5.5 market (NO 39c lock)', *build(B, card(q), live_routes(), extra_env=PUB),
          "BUILD FAILED: Under 6.5 - the YES of %s-6 is 'Over 5.5 goals scored', line 5.5: the pick's line is 6.5" % EVP)
    q = copy.deepcopy(UNDER); q['game']['commence'] = PAST
    rfail('an in-play publish of the Under on another day\'s market (the pre-game card\'s event)', *build(B, card(q), routes(SEVEN), extra_env=PUB),
          'BUILD FAILED: Under 6.5 - event %s is dated %s' % (EV, D))
    for what, seven in (('at its lock', SEVENP), ('with its live NO ask 27c from the lock (no lock check in play)', dict(SEVENP, yes_ask_dollars='0.71', no_ask_dollars='0.30'))):
        rc, page, log = build(B, card(ULP), live_routes(seven), extra_env=PUB)
        ch = chip_for(page, KURLP)
        check(f'{tag}: R an in-play publish of the bound Under ships {what} (KAL -133, data-kalpx no)',
              rc == 0 and label(ch) == 'KAL -133' and attr(ch, 'kalpx') == 'no' and 'from the 57c lock' not in log, log[-600:] + ch)
    # a refresh build of a card that is not the published one (it reached main some other way) binds its market and
    # side; the published card's refresh keeps its path, and a refresh never re-checks the lock
    u = copy.deepcopy(UNDER); u['kalshi'].update(side='yes', cents=44, gate_cents=44)
    rfail('a refresh build (not the published card) of the Under declared YES (YES 44c lock)', *build(B, card(u), routes(SEVEN), refresh=True),
          'BUILD FAILED: Under 6.5 is the under on %s, whose YES is the over - its side is no, the kalshi block says yes' % TK)
    rc, page, log = build(B, card(u), routes(SEVEN), refresh=True, files=published(B, card(u)))
    check(f'{tag}: R a refresh of the same card as the published one keeps its existing path (exit 0)', rc == 0, log[-600:])
    rc, page, log = build(B, card(UNDER), routes(total_mkt('7', '0.70', '0.30')), refresh=True)
    check(f'{tag}: R a refresh of the bound Under whose NO ask moved 27c from its lock ships at the lock (KAL -133, no lock check)',
          rc == 0 and label(chip_for(page, KURL)) == 'KAL -133' and 'from the 57c lock' not in log, log[-600:])

    # S. the NO side across leagues, on the merged tree beside main's Vegas, pick_line and spread-name holds
    def sbuild(p, *ms, **kw):
        return build(B, card(p), S_ESPN + xr(*ms) + kw.pop('rts', []), **kw)
    def sfail(what, rc, page, log, msg):
        check(f'{tag}: S {what} fails the build (exit 3, no page)', rc == 3 and msg in log and not page, log[-600:])
    # NFL spread: a + spread is the NO of the favourite's rung, and the Saints' code NO never reads as the side
    rc, page, log = sbuild(FALCONS, NO3, NO4)
    ch = chip_for(page, xurl(NO3['ticker']))
    check(f'{tag}: S NFL Falcons +2.5 as NO of "New Orleans wins by over 2.5" ships at the NO ask: KAL -127, data-cents 56, data-kalpx no, pair -NO3',
          rc == 0 and label(ch) == 'KAL -127' and attr(ch, 'cents') == '56' and attr(ch, 'kalpx') == 'no' and attr(ch, 'kalside') == 'NO3'
          and '%s-%s' % (attr(ch, 'kalticker'), attr(ch, 'kalside')) == NO3['ticker'], log[-600:] + ch)
    rec = records(page)[int(attr(ch, 'mr'))] if attr(ch, 'mr') else {}
    check(f'{tag}: S its market record is (event, the -NO3 market, side no) at 56c',
          (rec.get('ev'), rec.get('mkt'), rec.get('side'), rec.get('c')) == (NFL_EV, NO3['ticker'], 'no', 56), rec)
    row = kal_row(GAME_PAGES.get('game-1.html', ''))
    check(f'{tag}: S its game page row: Atlanta Falcons at KAL -127, data-kalside NO3, data-kalpx no',
          '>Atlanta Falcons</a>' in row and '>KAL -127</a>' in row and 'data-kalside="NO3" data-kalpx="no" data-cents="56"' in row, row)
    if ch:
        t = run_tick(page, 'rpKalTick', [{'dataset': ds(ch), 'innerHTML': 'KAL -127'}], {NO3['ticker']: dict(NO3, no_ask_dollars='0.60', yes_ask_dollars='0.41')})
        a = (t.get('anchors') or [{}])[0]
        check(f'{tag}: S the client tick fetches -NO3 and reads its NO ask (60c -> KAL -150, not the 41c YES)',
              t.get('fetched') == [NO3['ticker']] and a.get('dataset', {}).get('cents') == 60 and a.get('innerHTML') == 'KAL -150', t)
    q = xpick('Saints -2.5', 'spread', 'home', 'Atlanta Falcons', 'New Orleans Saints', 'football/nfl', 'NFL', NO3['ticker'], 'yes', 45, line=-2.5)
    rc, page, log = sbuild(q, NO3)
    ch = chip_for(page, xurl(NO3['ticker']))
    check(f'{tag}: S Saints -2.5 is the YES of the same rung: KAL +122, data-cents 45, data-kalpx yes',
          rc == 0 and label(ch) == 'KAL +122' and attr(ch, 'cents') == '45' and attr(ch, 'kalpx') == 'yes', log[-600:] + ch)
    q = copy.deepcopy(FALCONS); q['kalshi'].update(side='yes', cents=45, gate_cents=45)
    sfail('Falcons +2.5 declared YES on "New Orleans wins by over 2.5" (YES 45c lock)', *sbuild(q, NO3),
          "BUILD FAILED: Falcons +2.5 - the YES of %s is 'New Orleans wins by over 2.5 points', the opponent: its side is no, the kalshi block says yes" % NO3['ticker'])
    q = copy.deepcopy(FALCONS); q['kalshi'].update(ticker=NO4['ticker'], cents=64, gate_cents=64)
    sfail('Falcons +2.5 bound to the 3.5 rung with its own NO 64c lock', *sbuild(q, NO4),
          "BUILD FAILED: Falcons +2.5 - the YES of %s is 'New Orleans wins by over 3.5 points', the opponent by over 3.5: it binds the pick at +3.5, the pick's line is +2.5" % NO4['ticker'])
    # main's holds stand beside the explicit side: they hold the card before any market is read
    sfail("Falcons +3 named on the 2.5 rung (line -2.5): main's spread-name hold", *sbuild(dict(copy.deepcopy(FALCONS), name='Falcons +3'), NO3),
          "BUILD FAILED: card hold - standing rules are hard gates with no override (owner ruling 2026-10-02 (4)): pick 1 'Falcons +3': name says +3 but the away side's line is +2.5")
    sfail("a pick_line of -2.5 on the away +2.5: main's pick_line hold", *sbuild(dict(copy.deepcopy(FALCONS), pick_line=-2.5), NO3),
          "pick 1 'Falcons +2.5': pick_line -2.5 is not the away side's line +2.5")
    rc, page, log = sbuild(dict(copy.deepcopy(FALCONS), pick_line=2.5), NO3)
    check(f'{tag}: S a pick_line that agrees (+2.5) builds at the NO ask (KAL -127)', rc == 0 and label(chip_for(page, xurl(NO3['ticker']))) == 'KAL -127', log[-600:])
    LV3 = xm('KXNFLSPREAD-' + D + 'KCLV-LV3', 'Las Vegas wins by over 2.5 points', '0.45', '0.56')
    q = xpick('Chiefs +2.5', 'spread', 'away', 'Kansas City Chiefs', 'Las Vegas Raiders', 'football/nfl', 'NFL', LV3['ticker'], 'no', 56, line=-2.5)
    sfail('Chiefs +2.5 as NO on the Raiders\' rung: the Vegas rule holds an explicit NO side', *sbuild(q, LV3),
          "BUILD FAILED: card hold - standing rules are hard gates with no override (owner ruling 2026-10-02 (4)): pick 1 'Chiefs +2.5': Las Vegas team (home 'Las Vegas Raiders')")
    # NFL total: an Under is the NO of KXNFLTOTAL's Over
    pk, rt, url = tot('Atlanta Falcons', 'New Orleans Saints', 'football/nfl', 'NFL', 41.5, 'KXNFLTOTAL-' + D + 'ATLNO', 55, 'points')
    rc, page, log = build(B, card(pk), S_ESPN + rt)
    ch = chip_for(page, url)
    check(f'{tag}: S NFL Under 41.5 as NO of KXNFLTOTAL ...ATLNO-42 ships at the NO ask: KAL -122, data-cents 55, data-kalpx no',
          rc == 0 and label(ch) == 'KAL -122' and attr(ch, 'cents') == '55' and attr(ch, 'kalpx') == 'no' and pk['kalshi']['ticker'].endswith('ATLNO-42'), log[-600:] + ch)
    # CFB: Iowa +27.5 is the NO of OSU28 (82c); PITT @ VT Under 54.5 is the NO of KXNCAAFTOTAL ...-55 at 51c
    OSU28 = xm('KXNCAAFSPREAD-' + D + 'IOWAOSU-OSU28', 'Ohio State wins by over 27.5 points', '0.19', '0.82')
    q = xpick('Iowa +27.5', 'spread', 'away', 'Iowa Hawkeyes', 'Ohio State Buckeyes', 'football/college-football', 'NCAAF', OSU28['ticker'], 'no', 82, line=-27.5)
    rc, page, log = sbuild(q, OSU28)
    ch = chip_for(page, xurl(OSU28['ticker']))
    check(f'{tag}: S CFB Iowa +27.5 as NO of OSU28 ships at the 82c NO ask: KAL -456, data-kalpx no, pair -OSU28',
          rc == 0 and label(ch) == 'KAL -456' and attr(ch, 'cents') == '82' and attr(ch, 'kalpx') == 'no'
          and '%s-%s' % (attr(ch, 'kalticker'), attr(ch, 'kalside')) == OSU28['ticker'], log[-600:] + ch)
    # YES ask 52c beside the 51c NO: a build that read the YES side would break the 51c ceiling
    pk, rt, url = tot('Pittsburgh Panthers', 'Virginia Tech Hokies', 'football/college-football', 'NCAAF', 54.5, 'KXNCAAFTOTAL-' + D + 'PITTVT', 51, 'points', yes_c=52)
    rc, page, log = build(B, card(pk), S_ESPN + rt)
    ch = chip_for(page, url)
    check(f'{tag}: S CFB PITT @ VT Under 54.5 as NO of KXNCAAFTOTAL ...PITTVT-55 ships at the 51c NO ask: KAL -104, data-kalpx no',
          rc == 0 and label(ch) == 'KAL -104' and attr(ch, 'cents') == '51' and attr(ch, 'kalpx') == 'no' and pk['kalshi']['ticker'].endswith('PITTVT-55'), log[-600:] + ch)
    # WNBA: Liberty +3.5 is the NO of KXWNBASPREAD ...NYATL-ATL4
    ATL4 = xm('KXWNBASPREAD-' + D + 'NYATL-ATL4', 'Atlanta wins by over 3.5 points', '0.40', '0.61')
    q = xpick('Liberty +3.5', 'spread', 'away', 'New York Liberty', 'Atlanta Dream', 'basketball/wnba', 'WNBA', ATL4['ticker'], 'no', 61, line=-3.5)
    rc, page, log = sbuild(q, ATL4)
    ch = chip_for(page, xurl(ATL4['ticker']))
    check(f'{tag}: S WNBA Liberty +3.5 as NO of ...NYATL-ATL4 ships at the NO ask: KAL -156, data-kalpx no, pair -ATL4',
          rc == 0 and label(ch) == 'KAL -156' and attr(ch, 'cents') == '61' and attr(ch, 'kalpx') == 'no'
          and '%s-%s' % (attr(ch, 'kalticker'), attr(ch, 'kalside')) == ATL4['ticker'], log[-600:] + ch)
    # NWSL: "Houston or Draw" is exactly NO of Washington's market on the three-way event (HOME-first HDAWSP), but the card
    # has no double-chance class yet: as a moneyline it would grade as a Houston win, so it fails, never ships
    NEV = 'KXNWSLGAME-' + D + 'HDAWSP'
    NW3 = [xm(NEV + '-HDA', 'Houston', '0.38', '0.63'), xm(NEV + '-WSP', 'Washington', '0.36', '0.65'), xm(NEV + '-TIE', 'Tie', '0.28', '0.73')]
    hod = xpick('Houston or Draw', 'ml', 'home', 'Washington Spirit', 'Houston Dash', 'soccer/usa.nwsl', 'NWSL', NEV + '-WSP', 'no', 65)
    for what, q in (('"Houston or Draw" carded as a moneyline', hod), ('"Houston or Draw" under an unknown class "dc"', dict(copy.deepcopy(hod), market_class='dc')),
                    ('Houston Dash ML', dict(copy.deepcopy(hod), name='Houston Dash ML'))):
        sfail(f'{what} as NO on Washington\'s market of the three-way HDAWSP (NO 65c lock)',
              *sbuild(q, *NW3, rts=[[r'markets\?event_ticker=' + NEV + '&', {'markets': NW3}]]),
              "BUILD FAILED: %s - NO on %s-WSP is the picked team's win only on a two-way event; %s lists 3 market(s)" % (q['name'], NEV, NEV))
    # a zoneless commence binds its event as UTC (main's convention for a naive commence), on a Pacific machine too
    zl = copy.deepcopy(UNDER); zl['game']['commence'] = FUT[:-1]
    rc, page, log = build(B, card(zl), routes(SEVEN), extra_env={'TZ': 'America/Los_Angeles'})
    check(f'{tag}: S a zoneless commence ({FUT[:-1]}) binds the event dated {D} as UTC, on a Pacific machine (KAL -133)',
          rc == 0 and label(chip_for(page, KURL)) == 'KAL -133', log[-600:])
    # the Oct 5 Flyers +1.5 (shipped kalshi:null) replayed with the NO market of its rung: it prices the NO ask or refuses
    rc, page, log = sbuild(flyers_replay(), TB2)
    ch = chip_for(page, xurl(TB2['ticker']))
    check(f'{tag}: S the Oct 5 Flyers +1.5 replayed with its NO market prices the NO ask: KAL -138, data-cents 58, data-kalpx no, pair -TB2',
          rc == 0 and label(ch) == 'KAL -138' and attr(ch, 'cents') == '58' and attr(ch, 'kalpx') == 'no'
          and '%s-%s' % (attr(ch, 'kalticker'), attr(ch, 'kalside')) == TB2['ticker'], log[-600:] + ch)
    row = kal_row(GAME_PAGES.get('game-1.html', ''))
    check(f'{tag}: S its game page row: Philadelphia Flyers at KAL -138, data-kalpx no',
          '>Philadelphia Flyers</a>' in row and '>KAL -138</a>' in row and 'data-kalpx="no" data-cents="58"' in row, row)
    sfail('the Flyers replay whose NO ask moved to 60c over its 58c lock', *sbuild(flyers_replay(), dict(TB2, no_ask_dollars='0.60')),
          'BUILD FAILED: Flyers +1.5 Kalshi ask 60c exceeds ship-condition ceiling 58c')

    # T. one line, one market: the page builder holds a best ask quoted at another line than the pick's own
    def tpick(qline, price=-110, base=FALCONS):
        p = copy.deepcopy(base); p['odds'] = '%+d' % price; p['card_american'] = price; p['best_book'] = 'DraftKings'
        q = dict({'venue': 'dk', 'price': price, 'read_at': PAST}, **({} if qline is None else {'line': qline}))
        p['best_ask'] = dict(q, compared=[dict(q), {'venue': 'kalshi', 'price': p['kalshi']['cents'], 'read_at': PAST}])
        return p
    for what, q, msg in (('a DraftKings +3 (-110, 52.4c) against the 2.5 rung', tpick(3), "best_ask: a dk quote at line +3 is another market than the pick's own +2.5"),
                         ("the game's book line as posted, Saints -3", tpick(-3), "best_ask: a dk quote at line -3 is another market than the pick's own +2.5"),
                         ('a DraftKings quote naming no line', tpick(None), 'best_ask: a dk quote on a spread pick names no line')):
        rc, page, log = sbuild(q, NO3)
        check(f'{tag}: T {what} as the best ask is held (exit 3, no page, never suspendable)',
              rc == 3 and 'BUILD FAILED: card hold' in log and msg in log and not page, log[-600:])
    ml = tpick(-3, price=-130, base=xpick('Saints ML', 'ml', 'home', 'Atlanta Falcons', 'New Orleans Saints', 'football/nfl', 'NFL', 'KXNFLGAME-' + D + 'ATLNO-NO', 'yes', 58))
    rc, page, log = sbuild(ml)
    check(f'{tag}: T a moneyline whose DraftKings quote names a line (-3) is held (exit 3)',
          rc == 3 and "best_ask: a dk quote at line -3 is another market than a moneyline" in log and not page, log[-600:])
    rc, page, log = sbuild(tpick(2.5, price=-115), NO3)
    check(f'{tag}: T the same DraftKings at +2.5 (-115) is the pick\'s own market: the card builds (Kalshi chip at its NO ask, KAL -127)',
          rc == 0 and 'best_ask_line' not in log and 'another market' not in log and label(chip_for(page, xurl(NO3['ticker']))) == 'KAL -127', log[-600:])

# K. the v1 preview builder (card_chain_preview.sh) cannot price a side: it refuses any pick that names one
V1 = os.path.join(SD, 'build_gh_page.py')
rc, page, log = build(V1, card(LEAFS, UNDER), routes(SEVEN), as_name='build_gh_page.py')
check('K build_gh_page.py refuses a card with a kalshi.side pick (exit 3, names the pick, no page written)',
      rc == 3 and 'BUILD FAILED: kalshi.side on Under 6.5 - this builder prices Kalshi from a team-matched YES ask' in log and not page, log[-600:])
yes_only = copy.deepcopy(LEAFS); yes_only['kalshi']['side'] = 'yes'
rc, page, log = build(V1, card(yes_only), routes(SEVEN), as_name='build_gh_page.py')
check('K build_gh_page.py refuses a YES side too (it reads a team match, never the named market)',
      rc == 3 and 'BUILD FAILED: kalshi.side on Maple Leafs ML' in log and not page, log[-600:])
rc, page, log = build(V1, card(LEAFS), routes(SEVEN), as_name='build_gh_page.py')
check('K build_gh_page.py still builds a card without a side (old pick, team-matched chip)',
      rc == 0 and 'kalshi.side' not in log and 'data-book="KAL"' in page, log[-600:])
# card_chain_preview.sh runs 'cp -rf previews/overlay/. .' before it builds the preview, so the v1 builder it
# runs is the overlay copy: that copy must refuse a side too
OV1 = os.path.join(ROOT, 'previews', 'overlay', 'scripts', 'build_gh_page.py')
ccp = open(os.path.join(SD, 'card_chain_preview.sh')).read()
check('K card_chain_preview.sh applies the overlay and then builds with scripts/build_gh_page.py (the overlay copy)',
      'cp -rf previews/overlay/. .' in ccp and 'python3 scripts/build_gh_page.py' in ccp and os.path.exists(OV1))
rc, page, log = build(OV1, card(LEAFS, UNDER), routes(SEVEN), as_name='build_gh_page.py')
check('K the overlay v1 builder (card_chain_preview.sh) refuses a card with a kalshi.side pick (exit 3, no page)',
      rc == 3 and 'BUILD FAILED: kalshi.side on Under 6.5 - this builder prices Kalshi from a team-matched YES ask' in log and not page, log[-600:])
rc, page, log = build(OV1, card(LEAFS), routes(SEVEN), as_name='build_gh_page.py')
check('K the overlay v1 builder still builds a card without a side',
      rc == 0 and 'kalshi.side' not in log and 'data-book="KAL"' in page, log[-600:])

# G. build_manifest.py carries the side through to the manifest, and the page prices it
T0 = (NOW - datetime.timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ')
def bm_cand(**kal):
    c = {'num': 1, 'date': FUT[:10], 'market_class': 'total', 'line': 6.5, 'name': 'Under 6.5', 'side': 'under',
         'away': 'St. Louis Blues', 'home': 'Dallas Stars', 'commence': FUT, 'eid': '401999777', 'espn_league': 'hockey/nhl',
         'units': '5u', 'model': 62.0, 'gross_c': 5.0, 'net_c': 3.28, 'sub_context': 'STL @ DAL',
         'kalshi': dict({'cents': 57, 'team': '', 'ticker': TK, 'url': KURL}, **kal),
         'best_ask': {'venue': 'kalshi', 'price': 57, 'read_at': T0, 'compared': [{'venue': 'kalshi', 'price': 57, 'read_at': T0}]}}
    return c
def build_manifest(cands):
    d = tempfile.mkdtemp(prefix='rp-kalno-bm-')
    try:
        os.makedirs(os.path.join(d, 'ledger')); os.makedirs(os.path.join(d, 'prod'))
        cf, mf, out = (os.path.join(d, x) for x in ('cands.json', 'meta.json', 'manifest.json'))
        env = dict(os.environ, PYTHONPATH=ROOT, RIX_PICKS_LEDGER=os.path.join(d, 'ledger', 'picks.jsonl'),
                   RIX_PROD_MANIFEST=os.path.join(d, 'prod', 'manifest.json'), http_proxy=DEAD, https_proxy=DEAD, HTTP_PROXY=DEAD, HTTPS_PROXY=DEAD)
        json.dump(cands, open(cf, 'w'))
        json.dump({'record': '1-0', 'units_pl': '+1.00u', 'units_ledger': None, 'yesterday': '', 'status_note': '', 'parlay': None}, open(mf, 'w'))
        r = subprocess.run([sys.executable, os.path.join(SD, 'build_manifest.py'), cf, out, '--meta', mf], capture_output=True, text=True, env=env, timeout=120)
        return r.returncode, (json.load(open(out)) if os.path.exists(out) else None), r.stdout + r.stderr
    finally:
        shutil.rmtree(d, ignore_errors=True)
rc, man, log = build_manifest([bm_cand(side='no')])
kb = ((man or {}).get('picks') or [{}])[0].get('kalshi') or {}
check('G build_manifest carries kalshi.side "no" with the full ticker into the manifest pick',
      rc == 0 and kb.get('side') == 'no' and kb.get('ticker') == TK and kb.get('cents') == 57 and kb.get('gate_cents') == 57, log[-600:])
if man:
    for B in BUILDERS:
        brc, page, blog = build(B, man, routes(SEVEN))
        ch = chip_for(page, KURL)
        check(f'G {os.path.basename(B)}: the page built from that manifest prices the NO ask (KAL -133, data-kalpx no)',
              brc == 0 and label(ch) == 'KAL -133' and attr(ch, 'kalpx') == 'no', blog[-600:] + ch)
rc, man, log = build_manifest([bm_cand()])
kb = ((man or {}).get('picks') or [{}])[0].get('kalshi') or {}
check('G build_manifest without a side writes no side key (old picks unchanged)', rc == 0 and 'side' not in kb and kb.get('ticker') == TK, log[-600:])
rc, man, log = build_manifest([bm_cand(side='NO')])
check('G build_manifest refuses a side other than yes|no (nothing written)', rc != 0 and man is None and "kalshi side 'NO'" in log, log[-600:])

# G (cont). the Oct 5 Flyers +1.5 replayed through build_manifest: refused as it was carded, its NO market priced
check('G the Oct 5 Flyers +1.5 shipped with no kalshi block (manifests/manifest-24105e3e4c2b.json): the pick this replays',
      FLYERS.get('kalshi') is None and FLYERS.get('market_class') == 'spread' and FLYERS.get('line') == -1.5 and FLYERS.get('side') == 'away', FLYERS)
def fly_cand(kalshi=True):
    c = {'num': 1, 'date': FUT[:10], 'market_class': 'spread', 'line': FLYERS['line'], 'name': FLYERS['name'], 'side': FLYERS['side'],
         'away': FLYERS['game']['away'], 'home': FLYERS['game']['home'], 'commence': FUT, 'eid': FLYERS['game']['eid'],
         'espn_league': FLYERS['espn_league'], 'units': FLYERS['units'], 'model': float(re.search(r'model (\d+(?:\.\d+)?)', FLYERS['sub']).group(1)),
         'gross_c': 2.7, 'net_c': 2.7, 'sub_context': 'PHI @ TB',
         # its card source (Polymarket 58c) as the best ask, quoting the pick's own +1.5
         'best_ask': {'venue': 'poly', 'price': 58, 'line': 1.5, 'read_at': T0,
                      'compared': [{'venue': 'poly', 'price': 58, 'line': 1.5, 'read_at': T0}, {'venue': 'kalshi', 'price': 58, 'read_at': T0}]}}
    if kalshi: c['kalshi'] = {'cents': 58, 'team': '', 'ticker': TB2['ticker'], 'url': xurl(TB2['ticker']), 'side': 'no'}
    return c
rc, man, log = build_manifest([fly_cand(kalshi=False)])
check('G the Flyers +1.5 as it was carded (no kalshi block) is refused by build_manifest (J-122, nothing written)',
      rc != 0 and man is None and 'no kalshi block' in log, log[-600:])
rc, man, log = build_manifest([fly_cand()])
p0 = ((man or {}).get('picks') or [{}])[0]
check('G the Flyers +1.5 with its NO market: the manifest pick carries kalshi side no on -TB2 (never kalshi:null) and the Polymarket best ask at +1.5',
      rc == 0 and (p0.get('kalshi') or {}).get('side') == 'no' and (p0.get('kalshi') or {}).get('ticker') == TB2['ticker']
      and (p0.get('best_ask') or {}).get('venue') == 'poly' and (p0.get('best_ask') or {}).get('line') == 1.5, log[-600:])
if man:
    for B in BUILDERS:
        brc, page, blog = build(B, man, S_ESPN + xr(TB2))
        ch = chip_for(page, xurl(TB2['ticker']))
        check(f'G {os.path.basename(B)}: the page built from the replayed manifest prices the NO ask (KAL -138, data-kalpx no)',
              brc == 0 and label(ch) == 'KAL -138' and attr(ch, 'kalpx') == 'no', blog[-600:] + ch)

# G (cont). one line, one market in price_card: a book's -3 never best-asks Kalshi's 2.5 rung
K56 = {'venue': 'kalshi', 'price': 56, 'read_at': T0}
def dkq(price, line=None):
    return dict({'venue': 'dk', 'price': price, 'read_at': T0}, **({} if line is None else {'line': line}))
def bq(best, *comp):
    return dict(best, compared=list(comp))
def fal_cand(best_ask, **kw):
    c = {'num': 1, 'date': FUT[:10], 'market_class': 'spread', 'line': -2.5, 'name': 'Falcons +2.5', 'side': 'away',
         'away': 'Atlanta Falcons', 'home': 'New Orleans Saints', 'commence': FUT, 'eid': '401999778', 'espn_league': 'football/nfl',
         'units': '5u', 'model': 62.0, 'gross_c': 6.0, 'net_c': 4.3, 'sub_context': 'ATL @ NO',
         'kalshi': {'cents': 56, 'team': '', 'ticker': NO3['ticker'], 'url': xurl(NO3['ticker']), 'side': 'no'}, 'best_ask': best_ask}
    c.update(kw)
    return c
for what, ba, msg in (
        ('a DraftKings +3 at -110 (52.4c, cheaper than the 56c NO ask)', bq(dkq(-110, 3), K56, dkq(-110, 3)),
         "a dk quote at line +3 is another market than the pick's own +2.5"),
        ("the game's book line as posted, Saints -3 at -110", bq(dkq(-110, -3), K56, dkq(-110, -3)),
         "a dk quote at line -3 is another market than the pick's own +2.5"),
        ('a DraftKings +3 at -130 that loses to the 56c Kalshi ask (an off-line quote is never compared at all)', bq(K56, K56, dkq(-130, 3)),
         "a dk quote at line +3 is another market than the pick's own +2.5"),
        ('a DraftKings quote naming no line', bq(dkq(-110), K56, dkq(-110)), 'a dk quote on a spread pick names no line')):
    rc, man, log = build_manifest([fal_cand(ba)])
    check(f"G price_card: {what} against the Falcons' 2.5 rung refuses (nothing written)", rc != 0 and man is None and msg in log, log[-600:])
UEV = 'KXNFLTOTAL-' + D + 'ATLNO'
rc, man, log = build_manifest([fal_cand(bq(dkq(-110, 41), {'venue': 'kalshi', 'price': 55, 'read_at': T0}, dkq(-110, 41)),
                                        market_class='total', line=41.5, name='Under 41.5', side='under',
                                        kalshi={'cents': 55, 'team': '', 'ticker': UEV + '-42', 'url': xurl(UEV + '-42'), 'side': 'no'})])
check('G price_card: a DraftKings Under 41 against an Under 41.5 refuses (nothing written)',
      rc != 0 and man is None and "a dk quote at line 41 is another market than the pick's own 41.5" in log, log[-600:])
mlc = fal_cand(bq(dkq(-130, -3), {'venue': 'kalshi', 'price': 58, 'read_at': T0}, dkq(-130, -3)), market_class='ml', name='Saints ML', side='home',
               kalshi={'cents': 58, 'team': 'New Orleans', 'ticker': 'KXNFLGAME-' + D + 'ATLNO-NO', 'url': xurl('KXNFLGAME-' + D + 'ATLNO-NO')})
mlc.pop('line')
rc, man, log = build_manifest([mlc])
check('G price_card: a moneyline whose DraftKings quote names a line (-3) refuses (nothing written)',
      rc != 0 and man is None and 'a dk quote at line -3 is another market than a moneyline' in log, log[-600:])
rc, man, log = build_manifest([fal_cand(bq(dkq(-115, 2.5), K56, dkq(-115, 2.5)))])
p0 = ((man or {}).get('picks') or [{}])[0]; pba = p0.get('best_ask') or {}
check('G price_card: the same DraftKings at +2.5 (-115, 53.5c) is the best ask: card -115, its line rides into best_ask and compared',
      rc == 0 and p0.get('card_american') == -115 and pba.get('venue') == 'dk' and pba.get('line') == 2.5
      and [(q.get('venue'), q.get('line')) for q in pba.get('compared') or []] == [('dk', 2.5), ('kalshi', None)]
      and (p0.get('kalshi') or {}).get('side') == 'no', log[-600:])
if man:
    for B in BUILDERS:
        brc, page, blog = build(B, man, S_ESPN + xr(NO3))
        check(f'G {os.path.basename(B)}: the page built from that manifest passes the best-ask line hold and prices the NO ask (KAL -127)',
              brc == 0 and 'another market' not in blog and label(chip_for(page, xurl(NO3['ticker']))) == 'KAL -127', blog[-600:])
# a double chance ("Houston or Draw", NO on the opponent of a three-way event) has no class yet: refused closed
NEV = 'KXNWSLGAME-' + D + 'HDAWSP'
rc, man, log = build_manifest([fal_cand({'venue': 'kalshi', 'price': 60, 'read_at': T0, 'compared': [{'venue': 'kalshi', 'price': 60, 'read_at': T0}]},
                                        market_class='dc', name='Houston or Draw', side='home', away='Washington Spirit', home='Houston Dash',
                                        espn_league='soccer/usa.nwsl', model=68.0, gross_c=8.0, net_c=6.3, sub_context='WAS @ HOU',
                                        kalshi={'cents': 60, 'team': '', 'ticker': NEV + '-WSP', 'url': xurl(NEV + '-WSP'), 'side': 'no'})])
check('G build_manifest refuses "Houston or Draw" as a double chance (market_class "dc": no such class yet, nothing written)',
      rc != 0 and man is None and "market_class='dc'" in log, log[-600:])

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
