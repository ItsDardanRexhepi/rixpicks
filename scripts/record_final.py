#!/usr/bin/env python3
"""record_final.py - GHA-side record write on graded finals (main 9/27: record write moves into
a workflow, secrets never move; GITHUB_TOKEN commits). Self-contained: no private infra.

Input: record_request.json at repo root (analysis drops graded, ledger-verified requests;
each carries result, exact unit delta, record_after, units_after_exact, two-source attestation).
For each request, in order (any failure -> stop, exit 3, NO write at all; in-order processing:
later finals wait for the next fire):
  1. CARD: the grade must belong to a pick on a published card - a manifests/ snapshot (every
     build leaves one) or the live manifest - matched on its grade key. The card date is the
     builder's card-date rule (most common PT game date across the card's picks, which must equal
     the snapshot's date); the row is filed under it, never under whatever date the manifest
     carries now, and never under a late game's own date. A pick counts only when its own PT game
     date is the card's date or the next day (an after-midnight start), never an earlier game.
  2. INDEPENDENT verify against ESPN core (completed + scores match), and the result must follow
     from the verified score, side and line (ml/spread/total), from the ESPN box score (props;
     soccer scorer props from the summary's goal events), or from the winner flags (MMA). The
     request's own label is never taken on trust.
  3. Units: the delta must follow from the card price, card stake and result; units_after_exact
     must continue the running units (exact anchor kept in record_done.json).
  4. Running record from manifest must chain into request.record_after exactly.
  5. A pick already on its card date's row (same pick and final score) is refused; a grade key
     already in record_done.json is skipped, never applied twice.
  6. Late-post disclosure: a card pick posted after its game began carries added_after_kickoff
     (and added_after_final when the game had ended) - the row carries it too, fail-closed when
     malformed (see disclosure_of).
Apply: manifest record/units_pl, history.json day row (+day record/units), record_done.json.
Writes NOTHING to any private ledger - that stays analysis-side.
"""
import glob, json, os, re, sys, unicodedata, urllib.request
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path.insert(0, ROOT)
from core.accepted_entry import accepted_entry, entry_delta
REQ = os.path.join(ROOT, 'record_request.json')
MAN = os.path.join(ROOT, 'manifest.json')
HIST = os.path.join(ROOT, 'history.json')
DONE = os.path.join(ROOT, 'record_done.json')
MANIFESTS = os.path.join(ROOT, 'manifests')
PT = ZoneInfo('America/Los_Angeles')
EXACT = Decimal('0.000001')  # float transport noise on full-precision ledger values

def _get(url, timeout=20, ua='Mozilla/5.0'):
    req = urllib.request.Request(url, headers={'User-Agent': ua})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def _deref(node):
    return _get(node['$ref']) if isinstance(node, dict) and '$ref' in node else node

def espn_verify(league, eid, away_score, home_score):
    """Independent check: event completed AND scores match. Returns competitor map or None."""
    lg = league.replace('/', '/leagues/')
    base = f'https://sports.core.api.espn.com/v2/sports/{lg}/events/{eid}/competitions/{eid}'
    try:
        c = _get(base)
        st = _deref(c.get('status', {})).get('type', {})
        if not st.get('completed'):
            print(f'  verify {eid}: not completed ({st.get("name")})', file=sys.stderr)
            return None
        out = {}
        for comp in c.get('competitors', []):
            comp = _deref(comp)
            team = _deref(comp.get('team', {}))
            sc = _deref(comp.get('score', {}))
            val = sc.get('value') if isinstance(sc, dict) else None
            try: val = int(float(val))
            except (TypeError, ValueError): val = None
            out[comp.get('homeAway')] = {'name': team.get('displayName', ''), 'score': val}
        if out.get('home', {}).get('score') != home_score or out.get('away', {}).get('score') != away_score:
            print(f'  verify {eid}: score mismatch espn {out} vs req {away_score}-{home_score}', file=sys.stderr)
            return None
        return out
    except Exception as e:
        print(f'  verify {eid}: espn error {type(e).__name__}: {e}', file=sys.stderr)
        return None


def espn_verify_mma(league, eid, comp_id, q):
    """MMA independent check (9/29 Abushaar DWCS class): ESPN core MMA carries NO point scores
    and NO home/away assignment, so the generic score-compare cannot run. Verification is:
    competition completed + exactly 2 fighters with exactly one winner flag + the row's picked
    fighter identified uniquely by displayName inside the pick text + result consistent with
    the winner flag + opponent identity bound to the attested graded_pick text. competition_id
    is REQUIRED: MMA event ids and competition ids differ (event 600060739, comp 401891663)."""
    if not comp_id:
        print('  verify mma: competition_id required - MMA event ids and competition ids differ', file=sys.stderr)
        return None
    lg = league.replace('/', '/leagues/')
    base = f'https://sports.core.api.espn.com/v2/sports/{lg}/events/{eid}/competitions/{comp_id}'
    try:
        c = _get(base)
        st = _deref(c.get('status', {})).get('type', {})
        if not st.get('completed'):
            print(f'  verify mma {eid}/{comp_id}: not completed ({st.get("name")})', file=sys.stderr)
            return None
        fighters = []
        for comp in c.get('competitors', []):
            comp = _deref(comp)
            ath = _deref(comp.get('athlete', comp.get('team', {})))
            fighters.append({'name': ath.get('displayName', ''), 'winner': bool(comp.get('winner'))})
        if len(fighters) != 2 or sum(1 for f in fighters if f['winner']) != 1:
            print(f'  verify mma {eid}/{comp_id}: need 2 fighters and exactly one winner, got {fighters}', file=sys.stderr)
            return None
        def _name_hit(fname, text, other):
            # attestation texts may carry last names only ("Staines def. Abushaar"): word-bounded
            # full-name hit, else word-bounded last-name hit when the two fighters' last names
            # differ (fail-closed; bare substring would false-hit "Schmabushaar").
            t = (text or '').lower()
            full = (fname or '').lower()
            if full and re.search(r'\b' + re.escape(full) + r'\b', t):
                return True
            last, olast = full.split()[-1], (other or '').lower().split()[-1]
            return bool(last) and last != olast and bool(re.search(r'\b' + re.escape(last) + r'\b', t))
        pick_txt = q.get('pick') or ''
        picked = [f for f in fighters if f['name'] and _name_hit(f['name'], pick_txt, next(g['name'] for g in fighters if g is not f))]
        if len(picked) != 1:
            print(f'  verify mma {eid}/{comp_id}: picked fighter not uniquely identified in {q.get("pick")!r}', file=sys.stderr)
            return None
        picked = picked[0]
        opp = next(f for f in fighters if f is not picked)
        res = q.get('result')
        # exactly one winner flag: the picked fighter WON or LOST - nothing else (a PUSH label
        # on a fight with a winner is a contradiction, not a pass)
        if res != ('WON' if picked['winner'] else 'LOST'):
            print(f'  verify mma {eid}/{comp_id}: result {res} contradicts winner flags {fighters}', file=sys.stderr)
            return None
        gp = q.get('graded_pick') or ''
        if not _name_hit(opp['name'], gp, picked['name']):
            print(f'  verify mma {eid}/{comp_id}: opponent {opp["name"]!r} absent from attested graded_pick', file=sys.stderr)
            return None
        return {'picked': picked['name'], 'opp': opp['name'],
                'winner': next(f['name'] for f in fighters if f['winner'])}
    except Exception as e:
        print(f'  verify mma {eid}/{comp_id}: espn error {type(e).__name__}: {e}', file=sys.stderr)
        return None

SCORE_RE = re.compile(r'^([A-Z]{2,4})\s+(\d+)\s*@\s*([A-Z]{2,4})\s+(\d+)$')

def fmt_units(d):
    # the owner's display rule (core/units.display_units): half-up to the cent; a total that rounds
    # to zero prints '+0.00u', never '+-0.00u' (units_anchor reads this text back from the manifest)
    d = Decimal(d).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if d == 0:
        d = abs(d)
    return ('+' if d >= 0 else '') + f'{d}u'

_TWO_WORD_NICKS = ('White Sox', 'Red Sox', 'Blue Jays', 'Maple Leafs', 'Red Wings', 'Blue Jackets',
                   'Golden Knights', 'Trail Blazers')

def nick(display):
    # "New York Jets" -> "Jets"; "New York Liberty" -> "Liberty"; "Chicago White Sox" -> "White Sox"
    for t in _TWO_WORD_NICKS:
        if display == t or display.endswith(' ' + t):
            return t
    parts = display.split()
    return parts[-1] if parts else display


def _norm_name(x):
    return re.sub(r'[^a-z0-9]', '', (x or '').lower())

def _fold_name(x):
    """_norm_name with accents folded first ('Tomás Ostrák' -> 'tomasostrak'): ESPN spells one player
    both ways across its rosters and goal text, and a card name may differ from both. Used only to
    match names; grade keys keep _norm_name, so no queued or processed key changes."""
    x = unicodedata.normalize('NFKD', str(x or '')).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]', '', x.lower())

def _market_class(p):
    # explicit class wins; a classless row is a moneyline only when it names no other market
    return p.get('market_class') or (None if p.get('market') else 'ml')

def card_key(p):
    """Grade key of a published card pick - the key finals_watch grades it under."""
    eid, mc = (p.get('game') or {}).get('eid'), _market_class(p)
    if not eid or mc is None:
        return None
    if mc == 'prop':
        return f"{eid}|prop|{_norm_name(p.get('player'))}|{p.get('market')}|{p.get('side')}|{p.get('line')}"
    if mc in ('spread', 'total'):
        return f"{eid}|{mc}|{p.get('side')}|{p.get('line')}"
    return f"{eid}|{mc}|{p.get('side')}"

def _pt_date(iso):
    try:
        dt = datetime.fromisoformat(str(iso).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    return dt.astimezone(PT).date().isoformat() if dt.tzinfo else None

def card_date_of(snap):
    """The builder's _card_date_of: a card's date is the most common PT game date across its picks
    (so a game starting after midnight PT still belongs to the card it was published on)."""
    from collections import Counter
    ds = [_pt_date((p.get('game') or {}).get('commence')) for p in snap.get('picks') or [] if isinstance(p, dict)]
    ds = [d for d in ds if d]
    return Counter(ds).most_common(1)[0][0] if ds else None

def card_pick(q):
    """(card_date, published card pick) this grade belongs to, else (None, reason). See card_rows."""
    day, rows = card_rows(q)
    return (day, rows[0]) if day is not None else (None, rows)

# Late-post disclosure (Oct 2 owner override): a pick carded after its game began carries
# added_after_kickoff: true on the published card, and added_after_final: true too when the game had
# already ended at posting. The record row carries the same flags, so record.html, yesterday.html and
# the Home learnings panel keep saying so after the card is gone (the row used to drop them).
# Fail-closed (exit 3, nothing written): a flag that is not a JSON true/false, published copies that
# contradict each other (true on one, false on another), after-the-final without after-kickoff, or a
# request that states a different disclosure than the card. A copy that omits a flag makes no claim
# either way, so a disclosure published on any copy of the card is kept, never dropped.
DISCLOSURE_FIELDS = ('added_after_kickoff', 'added_after_final')

def disclosure_of(rows):
    """{flag: True} for each late-post disclosure the published copies carry. Raises ValueError."""
    out = {}
    for f in DISCLOSURE_FIELDS:
        vals = [r[f] for r in rows if isinstance(r, dict) and f in r]
        bad = [v for v in vals if not isinstance(v, bool)]
        if bad:
            raise ValueError(f'{f} must be true or false, got {bad[0]!r}')
        if len(set(vals)) > 1:
            raise ValueError(f'published copies disagree on {f}')
        if True in vals:
            out[f] = True
    if out.get('added_after_final') and not out.get('added_after_kickoff'):
        raise ValueError('added_after_final without added_after_kickoff (a pick added after the final was added after kickoff)')
    return out

def card_rows(q):
    """(card_date, [every published copy of the card pick]) this grade belongs to, else (None, reason).
    The card date belongs to the CARD (builder _card_date_of): the most common PT game date across
    the snapshot's picks, and the snapshot counts only when its own date agrees - an archive copy
    filed under another date (the Sep 30 snapshot carrying Sep 29's picks) is no card at all, so
    nothing on it is graded. A pick is filed under its card's date, even when its own game starts
    after midnight PT (its PT date is the card's date or the next day); a pick whose game began
    before the card's date is not on that card. Every build snapshots the manifest it published
    into manifests/; the live manifest.json counts too. An MMA pick binds on league + pick text and,
    when any copy of that day's row carries game.eid, on that event too (a copy without one never
    stands in for it, and copies naming different events bind none); an MMA pick on cards of
    several dates needs the request's card_date."""
    mma = str(q.get('league') or '').startswith('mma/')
    found, mma_rows = {}, {}
    for path in sorted(glob.glob(os.path.join(MANIFESTS, 'manifest-*.json'))) + [MAN]:
        try:
            snap = json.load(open(path))
        except (OSError, ValueError):
            continue
        day = card_date_of(snap)
        if not day or snap.get('date') != day:
            continue
        nxt = (datetime.strptime(day, '%Y-%m-%d') + timedelta(days=1)).date().isoformat()
        for p in snap.get('picks') or []:
            if not isinstance(p, dict):
                continue
            pd = _pt_date((p.get('game') or {}).get('commence'))
            # the pick's own game must be on the card's date, or start after midnight PT into the
            # next day - a game that began before the card's date was never this card's pick
            if not (pd and day <= pd <= nxt):
                continue
            if mma:
                # MMA rows bind on league + exact pick text; the event is bound per day below
                if str(p.get('espn_league') or '').startswith('mma/') and p.get('name') == q.get('pick'):
                    mma_rows.setdefault(day, []).append(p)
            elif card_key(p) == str(q.get('grade_id')):
                found.setdefault(day, []).append(p)
    forked = set()
    for day, rows in mma_rows.items():
        # a K19 row carries game.eid (the ESPN fight-card event id). When any copy of the day's row
        # carries one, the grade must name that event - a later fight of the same fighter is never
        # graded against this card's pick, and a copy with no eid (a hand-landed or older copy) never
        # lets another event through. Copies naming different events bind none. With no eid on any
        # copy (before K19) the row binds on league + pick text, as it always has.
        eids = {str(r['game']['eid']) for r in rows if (r.get('game') or {}).get('eid')}
        if not eids:
            found[day] = rows
        elif len(eids) > 1:
            if str(q.get('event_id')) in eids:
                found[day], forked = rows, forked | {day}
        elif eids == {str(q.get('event_id'))}:
            # the bound copy first: main() checks the request's event against the row it is given
            found[day] = sorted(rows, key=lambda r: not (r.get('game') or {}).get('eid'))
    if mma and len(mma_rows) > 1 and q.get('card_date') is None:
        return None, f'carded on several dates {sorted(mma_rows)} - an MMA grade must name its card_date'
    if q.get('card_date') is not None:
        found = {d: v for d, v in found.items() if d == q['card_date']}
    if len(found) != 1:
        return None, ('not on any published card' + (f" dated {q['card_date']}" if q.get('card_date') else '')
                      if not found else f'on published cards for several dates {sorted(found)}')
    day, rows = next(iter(found.items()))
    if day in forked:
        return None, f'published copies of the {day} card disagree on the event this MMA pick is bound to'
    if len({(r.get('name'), str(r.get('odds')), str(r.get('card_american')), str(r.get('units'))) for r in rows}) != 1:
        return None, f'published copies of the {day} card disagree on name, price or stake'
    return day, rows

def _same_num(a, b):
    if a is None or b is None:
        return a is None and b is None  # a moneyline carries no line on either side
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except (InvalidOperation, ValueError):
        return False

def american(v):
    if v is None or isinstance(v, bool):
        return None
    s = str(v).strip()
    if not re.fullmatch(r'[+-]?\d+', s):
        return None
    a = int(s)
    return a if (a >= 100 or a <= -100) else None

def stake_of(v):
    try:
        u = Decimal(str(v).strip().rstrip('u'))
    except (InvalidOperation, ValueError):
        return None
    return u if u > 0 else None

def expected_delta(res, price, stake):
    """Card-price grading: win pays stake at the published American price, loss -stake, push 0."""
    if res == 'WON':
        return stake * Decimal(100) / Decimal(-price) if price < 0 else stake * Decimal(price) / Decimal(100)
    return -stake if res == 'LOST' else Decimal(0)

def score_result(mc, side, line, away_sc, home_sc):
    """WON/LOST/PUSH from the verified final (line = HOME spread / game total, the card's
    convention). None when the market, side or line cannot be graded from a score."""
    if mc in ('ml', 'spread') and side not in ('home', 'away'):
        return None
    if mc == 'total' and side not in ('over', 'under'):
        return None
    if mc == 'ml':
        if home_sc == away_sc:
            return 'PUSH'
        won = (side == 'home') == (home_sc > away_sc)
    elif mc in ('spread', 'total'):
        try:
            ln = Decimal(str(line))
        except (InvalidOperation, ValueError):
            return None
        if mc == 'spread':
            diff = Decimal(home_sc) + ln - Decimal(away_sc)  # >0 home covers
            if diff == 0:
                return 'PUSH'
            won = (side == 'home') == (diff > 0)
        else:
            tot = Decimal(home_sc + away_sc)
            if tot == ln:
                return 'PUSH'
            won = (side == 'over') == (tot > ln)
    else:
        return None
    return 'WON' if won else 'LOST'

# Box-score prop check: the same verified market map finals_watch grades with. Soccer scorer
# props read the summary's goal events (see _soccer_scorer). Markets outside the map have no
# independent check here and are refused, never trusted.
PROP_STAT_KEYS = {
    'passing_yards': ('passingYards',), 'pass_td': ('passingTouchdowns',),
    'rushing_yards': ('rushingYards',), 'rush_attempts': ('rushingAttempts',),
    'receiving_yards': ('receivingYards',), 'receptions': ('receptions',),
    'reception_tds': ('receivingTouchdowns',), 'rush_tds': ('rushingTouchdowns',),
    'points': ('points',), 'rebounds': ('rebounds',), 'assists': ('assists',),
    'threes': ('threePointFieldGoalsMade-threePointFieldGoalsAttempted',),
    'goals': ('goals',), 'shots_on_goal': ('shotsTotal',),
    'saves': ('saves',), 'blocked_shots': ('blockedShots',)}
PROP_GROUP_SCOPED = {  # MLB: batting keys also appear in the pitching group - scope by marker key
    'bat_hits': ('atBats', 'hits'), 'bat_home_runs': ('atBats', 'homeRuns'),
    'bat_rbis': ('atBats', 'RBIs'), 'bat_runs': ('atBats', 'runs'),
    'bat_walks': ('atBats', 'walks'), 'bat_strikeouts': ('atBats', 'strikeouts'),
    'pit_strikeouts': ('earnedRuns', 'strikeouts'), 'pit_hits_allowed': ('earnedRuns', 'hits'),
    'pit_walks': ('earnedRuns', 'walks'), 'pit_earned_runs': ('earnedRuns', 'earnedRuns'),
    'pit_outs': ('earnedRuns', 'fullInnings.partInnings')}

SOCCER_SCORER_MARKETS = ('anytime_goal', 'first_goal', 'last_goal')
_GOAL_NAME = re.compile(r'^(?:Own Goal by )?(.+?) \(([^()]*)\)')
_SCORELINE_END = re.compile(r'(?<=\d)\. ')  # the '. ' after the away score, never one inside a team name
_OWN_GOAL_TEXT = re.compile(r'\s*own goal\b', re.I)

def _goal_scorer_id(ev, aliases, rostered):
    """Scorer of one goal event: ESPN's own participants[0] athlete id, which must be on a roster. The
    goal text's name (after the scoreline, 'Goal! <home> <n>, <away> <n>. <Scorer> (<Team>) ...' - the
    first '. ' can fall inside 'D.C. United' or 'St. Louis City SC') only cross-checks it: a name that
    resolves on the rosters to anyone else refuses, while a name the rosters spell differently
    ('Guilherme' for Guilherme Augusto, 'Luighi' for Luighi Hanri) leaves the id standing. With no
    participant id the name must resolve to exactly one rostered player. Raises ValueError."""
    text = ev.get('text') or ''
    if _OWN_GOAL_TEXT.match(text):
        raise ValueError(f'goal event text names an own goal ({text[:80]!r})')
    parts = ev.get('participants')
    first = parts[0] if isinstance(parts, list) and parts and isinstance(parts[0], dict) else {}
    ath = first.get('athlete') if isinstance(first.get('athlete'), dict) else {}
    sid = str(ath.get('id') or '')
    mm = _GOAL_NAME.search(_SCORELINE_END.split(text, maxsplit=1)[-1])
    named = aliases.get(_fold_name(mm.group(1)), set()) if mm else set()
    if sid:
        if sid not in rostered:
            raise ValueError(f'goal scorer id {sid} not on the rosters')
        if named and sid not in named:
            raise ValueError(f'goal scorer id {sid} is not the goal text\'s {mm.group(1)!r}')
        return sid
    if not mm:
        raise ValueError(f'goal event text unparsable ({text[:80]!r})')
    if len(named) != 1:
        raise ValueError(f'goal scorer {mm.group(1)!r} not uniquely on the rosters ({len(named)} matches)')
    return next(iter(named))

def _soccer_scorer(d, player, market):
    """Soccer scorer props (MLS): ESPN's soccer summary carries no player stat tables, so the check
    reads the same source with the same rules finals_watch grades by - keyEvents with scoringPlay
    true, own goals never credit, periods 1-2 only (no extra time or shootout), each goal's scorer by
    ESPN's athlete id (_goal_scorer_id), the pick's player resolved strictly against the two rosters
    with accents folded, and a tied clock on first/last refused.
    Returns (goal count, or 1/0 for first/last, as Decimal; home|away of the player's roster); raises
    ValueError when any of it cannot be established."""
    aliases, side_of, sides = {}, {}, []
    for r in d.get('rosters') or []:
        sides.append(r.get('homeAway'))
        for e in r.get('roster') or []:
            a = e.get('athlete') or {}
            aid = str(a.get('id') or '')
            if not aid:
                continue
            side_of.setdefault(aid, set()).add(r.get('homeAway'))
            for nm in (a.get('displayName'), a.get('fullName'), a.get('shortName')):
                n = _fold_name(nm)
                if n:
                    aliases.setdefault(n, set()).add(aid)
    if sorted(map(str, sides)) != ['away', 'home']:
        raise ValueError(f'rosters are not one home and one away ({sides})')
    want = _fold_name(player)
    ids = {aid for alias, aids in aliases.items() if want and (alias == want or want in alias or alias in want) for aid in aids}
    if len(ids) != 1:
        raise ValueError(f'player {player!r} not uniquely on the rosters ({len(ids)} matches)')
    pid = next(iter(ids))
    pside = side_of[pid]
    if len(pside) != 1:
        raise ValueError(f'player {player!r} on both rosters')
    goals = []  # (clock seconds, scorer athlete id); own goals, extra time and shootout excluded
    for ev in d.get('keyEvents') or []:
        if ev.get('scoringPlay') is not True or (ev.get('type') or {}).get('type') == 'own-goal':
            continue
        if (ev.get('period') or {}).get('number') not in (1, 2):
            continue
        goals.append(((ev.get('clock') or {}).get('value'), _goal_scorer_id(ev, aliases, side_of)))
    if market == 'anytime_goal':
        val = sum(1 for _, aid in goals if aid == pid)
    elif not goals:
        val = 0  # no credited goal: a first/last scorer prop loses
    else:
        if any(isinstance(c, bool) or not isinstance(c, (int, float)) for c, _ in goals):
            raise ValueError(f'{market}: a goal event carries no clock - order unknown')
        edge = (min if market == 'first_goal' else max)(c for c, _ in goals)
        if sum(1 for c, _ in goals if c == edge) > 1:
            raise ValueError(f'{market} order ambiguous (tied clock)')
        val = 1 if any(c == edge and aid == pid for c, aid in goals) else 0
    return Decimal(val), next(iter(pside))

def espn_prop(league, eid, player, market):
    """Independent prop check: (stat value, home|away of the player's team) from the ESPN box
    score, or None. Strict identity: exactly one athlete, on a team the header places home/away.
    Soccer scorer props read the summary's goal events and rosters instead (_soccer_scorer)."""
    if (market not in PROP_STAT_KEYS and market not in PROP_GROUP_SCOPED and market not in ('anytime_td', 'hockey_points')
            and market not in SOCCER_SCORER_MARKETS):
        print(f'  verify prop {eid}: market {market!r} has no box-score check here', file=sys.stderr)
        return None
    try:
        d = _get(f'https://site.api.espn.com/apis/site/v2/sports/{league}/summary?event={eid}', ua='python-urllib/3')
        if market in SOCCER_SCORER_MARKETS:
            return _soccer_scorer(d, player, market)
        sides = {str((c.get('team') or {}).get('id')): c.get('homeAway')
                 for c in ((d.get('header') or {}).get('competitions') or [{}])[0].get('competitors', [])}
        want = _norm_name(player)
        ids, rows = {}, []
        for team in (d.get('boxscore') or {}).get('players', []):
            tside = sides.get(str((team.get('team') or {}).get('id')))
            for grp in team.get('statistics', []):
                for ath in grp.get('athletes', []):
                    a = ath.get('athlete') or {}
                    nm = _norm_name(a.get('displayName'))
                    if want and nm and (nm == want or want in nm or nm in want):
                        ids[a.get('id') or a.get('displayName')] = tside
                        rows.append((grp.get('keys') or [], ath.get('stats') or []))
        if len(ids) != 1 or next(iter(ids.values())) not in ('home', 'away'):
            print(f'  verify prop {eid}: player {player!r} not uniquely placed in the box score ({ids})', file=sys.stderr)
            return None
        def stat(key, marker=None):
            for keys, stats in rows:
                if key in keys and (marker is None or marker in keys) and keys.index(key) < len(stats):
                    return stats[keys.index(key)]
            return None
        if market == 'pit_outs':
            raw = stat('fullInnings.partInnings', 'earnedRuns')
            full, _, part = str(raw).partition('.')
            if raw is None or not full.isdigit() or (part or '0') not in ('0', '1', '2'):
                raise ValueError(f'innings line {raw!r}')
            val = Decimal(int(full) * 3 + int(part or 0))
        elif market in ('anytime_td', 'hockey_points'):
            parts = [stat(k) for k in (('rushingTouchdowns', 'receivingTouchdowns') if market == 'anytime_td' else ('goals', 'assists'))]
            if (market == 'hockey_points' and None in parts) or all(v is None for v in parts):
                raise ValueError(f'stat line missing {parts}')
            val = sum((Decimal(str(v).split('-')[0]) for v in parts if v is not None), Decimal(0))
        else:
            marker, key = PROP_GROUP_SCOPED[market] if market in PROP_GROUP_SCOPED else (None, PROP_STAT_KEYS[market][0])
            raw = stat(key, marker)
            if raw is None:
                raise ValueError('stat line missing (DNP or group absent)')
            val = Decimal(str(raw).split('-')[0])  # compound made-attempted -> made
        return val, next(iter(ids.values()))
    except Exception as e:
        print(f'  verify prop {eid}: {type(e).__name__}: {e}', file=sys.stderr)
        return None

def units_anchor(man, done):
    """(exact running units the next grade must continue, tolerance). The exact value this job
    last wrote is kept in record_done.json; it is used while the manifest still shows that same
    record and units. Otherwise the displayed manifest units bound the exact value to half a cent."""
    shown = Decimal(str(man.get('units_pl') or '').strip().rstrip('u'))
    ex = done.get('units_after_exact')
    if ex is not None and done.get('record_after') == man.get('record') and fmt_units(Decimal(str(ex))) == fmt_units(shown):
        return Decimal(str(ex)), EXACT
    return shown, Decimal('0.005') + EXACT


def eod_day_close(p):
    """EOD DAY CLOSE wire (analysis, Sep 28): the brief travels IN the payload.
    eod_day_close.py itself can NEVER run here - its sheet reads shell out to the
    analysis runtime. Verify anchors fail-closed, then fill the day-row brief ONLY, and only
    while it is empty - a brief already on the row is never replaced (append-only record).
    Canonical pick rows and _delta fields are never touched; no row creation."""
    date = p.get('date')
    brief = p.get('brief')
    if not date or not isinstance(brief, str) or not brief.strip():
        print('  REFUSE eod_day_close: missing date or empty brief', file=sys.stderr)
        return 3
    hist = json.load(open(HIST))
    day = next((d for d in hist['days'] if d.get('date') == date), None)
    if day is None:
        print(f'  REFUSE eod_day_close: no chain-written day row for {date} - no row creation', file=sys.stderr)
        return 3
    if not day['picks'] or any(pk.get('result') not in ('W', 'L', 'P') for pk in day['picks']):
        print(f'  REFUSE eod_day_close: ungraded picks remain in {date} row', file=sys.stderr)
        return 3
    if p.get('record') != day.get('record'):
        print(f'  REFUSE eod_day_close: record anchor {p.get("record")} != day row {day.get("record")}', file=sys.stderr)
        return 3
    if not any('_delta' in pk for pk in day['picks']):
        print(f'  REFUSE eod_day_close: no _delta ledger fields in {date} row - not chain-written', file=sys.stderr)
        return 3
    du = sum((Decimal(pk['_delta']) for pk in day['picks'] if '_delta' in pk), Decimal('0'))
    try:
        pu = Decimal(str(p.get('units', '')).strip().rstrip('u'))
    except Exception:
        print(f'  REFUSE eod_day_close: unparsable units anchor {p.get("units")!r}', file=sys.stderr)
        return 3
    if pu != du and pu != du.quantize(Decimal('0.01')):
        print(f'  REFUSE eod_day_close: units anchor {pu} != exact day sum {du}', file=sys.stderr)
        return 3
    # a day eod already closed (its receipt is in record_done.json) is skipped and the eod part of
    # the request cleared, whatever brief text the re-send carries - nothing is written either way.
    # Grades finals_watch queued into the same file stay queued (main() processes them next).
    gid = 'eod_day_close:' + date
    done = {'processed': [], 'at': None}
    if os.path.exists(DONE):
        done = json.load(open(DONE))
    if gid in done.get('processed', []):
        print(f'  skip {gid}: already processed')
        json.dump({'requests': p.get('requests') or []}, open(REQ, 'w'), indent=2)
        return 0
    # append-only: the fill writes an EMPTY brief only. A day whose brief was filed another way
    # (Sep 27: brief on the row, no eod receipt) keeps it - a stored note is never replaced.
    if (day.get('brief') or '').strip() and day['brief'] != brief:
        print(f'  REFUSE eod_day_close: {date} already carries a filed brief - a stored note is never replaced', file=sys.stderr)
        return 3
    day['brief'] = brief
    json.dump(hist, open(HIST, 'w'), indent=2)
    done.setdefault('processed', []).append(gid)
    done['at'] = datetime.now(timezone.utc).isoformat()
    json.dump(done, open(DONE, 'w'), indent=2)
    json.dump({'requests': p.get('requests') or []}, open(REQ, 'w'), indent=2)  # queued grades are never dropped
    print(f'EOD DAY CLOSE: brief filled for {date} (record {day["record"]}, units {fmt_units(du)})')
    # combo expiry wire: day close marks every combo dated on/before the cutoff as expired.
    # MARK, never delete - the audit trail stays; the display layer filters on status too.
    ce = p.get('combo_expiry')
    if isinstance(ce, dict) and ce.get('action') == 'mark_expired':
        target = ce.get('target'); cutoff = str(ce.get('expire_on_or_before') or '')
        if not target or not re.match(r'^\d{4}-\d{2}-\d{2}$', cutoff):
            print('  REFUSE combo_expiry: bad target or cutoff', file=sys.stderr)
        else:
            tp = os.path.join(ROOT, target)
            try:
                cj = json.load(open(tp))
                n = 0
                for c in cj.get('combos') or []:
                    d = str(c.get('date') or c.get('game_date') or '')
                    if not d:
                        m = re.search(r'(\d{4})(\d{2})(\d{2})\s*$', str(c.get('id') or ''))
                        d = '%s-%s-%s' % m.groups() if m else ''
                    if d and d <= cutoff and c.get('status') != 'expired':
                        c['status'] = 'expired'
                        c['expired_at'] = datetime.now(timezone.utc).isoformat()
                        n += 1
                if n:
                    json.dump(cj, open(tp, 'w'), indent=2)
                print(f'  combo_expiry: {n} marked expired in {target} (cutoff {cutoff})')
            except FileNotFoundError:
                print(f'  combo_expiry: {target} absent - nothing to mark')
    return 0

def main():
    if not os.path.exists(REQ):
        print('no record_request.json - nothing to do')
        return 0
    payload = json.load(open(REQ))
    if payload.get('kind') == 'eod_day_close':
        # finals_watch appends its grades to this same file, so an eod payload can carry queued
        # grades in 'requests'. No queued grade is ever dropped: the eod writes them back as the
        # queue and they are processed right after it, in this run. An eod that refuses leaves the
        # whole file as it was.
        rc = eod_day_close(payload)
        if rc != 0 or not (payload.get('requests') or []):
            return rc
        payload = {'requests': payload.get('requests') or []}
    reqs = payload.get('requests') or []
    if not reqs:
        print('record_request.json empty - nothing to do')
        return 0
    man = json.load(open(MAN))
    hist = json.load(open(HIST))
    done = {'processed': [], 'at': None}
    if os.path.exists(DONE):
        done = json.load(open(DONE))

    rw, rl = [int(x) for x in man['record'].split('-')[:2]]
    try:
        units_run, units_tol = units_anchor(man, done)
    except (InvalidOperation, ValueError):
        print(f'  REFUSE: manifest units {man.get("units_pl")!r} unparsable - no units chain to continue', file=sys.stderr)
        return 3
    processed = []
    touched = []
    for q in reqs:
        gid = q['grade_id']
        if gid in done.get('processed', []):
            print(f'  skip {gid}: already processed')
            continue
        m = SCORE_RE.match(q['score'].strip())
        if not m:
            print(f'  REFUSE {gid}: unparseable score {q["score"]!r}', file=sys.stderr)
            return 3
        away_ab, away_sc, home_ab, home_sc = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
        # per-pick learnings (his 6:41 directive): optional, display-only, fail-closed on malformed.
        if 'learning' in q and (not isinstance(q['learning'], str) or not q['learning'].strip() or len(q['learning']) > 400):
            print(f'  REFUSE {gid}: learning must be a non-empty string <= 400 chars', file=sys.stderr)
            return 3
        res = q.get('result')
        if res not in ('WON', 'LOST', 'PUSH'):
            print(f'  REFUSE {gid}: unknown result {res!r}', file=sys.stderr)
            return 3
        # 1. CARD: only a published pick is graded, and it is filed under its own card date
        card_date, rows = card_rows(q)
        if card_date is None:
            print(f'  REFUSE {gid}: {q.get("pick")!r} {rows} - only published picks are graded', file=sys.stderr)
            return 3
        cp = rows[0]
        # 6. late-post disclosure: carried from the card onto the row, never dropped, never guessed
        try:
            disclosure = disclosure_of(rows)
        except ValueError as e:
            print(f'  REFUSE {gid}: late-post disclosure on the {card_date} card pick {cp.get("name")!r} is malformed: {e}', file=sys.stderr)
            return 3
        for f in DISCLOSURE_FIELDS:
            if f in q and q[f] is not disclosure.get(f, False):
                print(f'  REFUSE {gid}: request {f}={q[f]!r} disagrees with the {card_date} card pick {cp.get("name")!r}', file=sys.stderr)
                return 3
        mc = _market_class(cp)
        mma = str(q.get('league') or '').startswith('mma/')
        if (q.get('pick') != cp.get('name') or str(q.get('league')) != str(cp.get('espn_league'))
                or (not mma and (str(q.get('event_id')) != str(cp['game']['eid']) or q.get('side') != cp.get('side')))
                or (mma and (cp.get('game') or {}).get('eid') and str(q.get('event_id')) != str(cp['game']['eid']))
                or ('market_class' in q and q['market_class'] != mc)
                or ('line' in q and not _same_num(q['line'], cp.get('line')))):
            print(f'  REFUSE {gid}: request disagrees with the {card_date} card pick {cp.get("name")!r}', file=sys.stderr)
            return 3
        # 3a. price and stake are the card's; the delta must follow from them
        price = american(cp.get('card_american')) if cp.get('card_american') is not None else american(cp.get('odds'))
        if price is None or (cp.get('card_american') is not None and american(cp.get('odds')) not in (None, price)):
            print(f'  REFUSE {gid}: card price missing or forked ({cp.get("odds")!r} vs {cp.get("card_american")!r})', file=sys.stderr)
            return 3
        stake = stake_of(cp.get('units'))
        if stake is None or american(q.get('locked_american')) != price or stake_of(q.get('stake_units')) != stake:
            print(f'  REFUSE {gid}: request price/stake {q.get("locked_american")!r} {q.get("stake_units")!r} '
                  f'!= card {price:+d} {cp.get("units")!r}', file=sys.stderr)
            return 3
        try:
            delta = Decimal(str(q['delta_units_exact']))
            units_after = Decimal(str(q['units_after_exact']))
        except (KeyError, InvalidOperation, ValueError):
            print(f'  REFUSE {gid}: delta_units_exact / units_after_exact missing or unparsable', file=sys.stderr)
            return 3
        accepted = accepted_entry(cp)
        if accepted is not None:
            accepted_basis = {k: accepted[k] for k in ('accepted_entry_id', 'card_venue', 'entry_c', 'entry_basis')}
            if q.get('accepted_entry') != accepted_basis:
                print(f'  REFUSE {gid}: accepted-entry provenance mismatch', file=sys.stderr)
                return 3
        want_delta = entry_delta(res, stake, accepted) if accepted is not None else expected_delta(res, price, stake)
        if abs(delta - want_delta) > EXACT:
            print(f'  REFUSE {gid}: delta {delta} does not follow from {res} at {price:+d} on {stake}u (want {want_delta})', file=sys.stderr)
            return 3
        # 3b. units chain: prior exact running units + this delta == units_after_exact
        if abs(units_after - (units_run + delta)) > units_tol:
            print(f'  REFUSE {gid}: units chain broken - running {units_run} + {delta} != units_after_exact {units_after}', file=sys.stderr)
            return 3
        units_run, units_tol = units_after, EXACT
        if mma:
            # MMA rows: winner-flag verification, no score compare (ESPN carries no MMA scores).
            info = espn_verify_mma(q['league'], q['event_id'], q.get('competition_id'), q)
            if info is None:
                print(f'  REFUSE {gid}: independent verification failed - chain stops, no write', file=sys.stderr)
                return 3
            if sorted((away_sc, home_sc)) != [0, 1]:
                print(f'  REFUSE {gid}: mma score convention is winner 1 / loser 0, got {q["score"]!r}', file=sys.stderr)
                return 3
            game = 'vs ' + nick(info['opp'])
            # display truth (main 6:46): the 1-0 encoding is a machine convention, never a shown
            # score - the stored/served row carries "Winner def. Loser" (build_history renders
            # the score field verbatim, so the display string lives in the data).
            _loser = info['picked'] if info['winner'] != info['picked'] else info['opp']
            score_txt = f'{nick(info["winner"])} def. {nick(_loser)}'
        else:
            comp = espn_verify(q['league'], q['event_id'], away_sc, home_sc)
            if comp is None:
                print(f'  REFUSE {gid}: independent verification failed - chain stops, no write', file=sys.stderr)
                return 3
            # 2. the result must follow from the verified final - never from the request's label
            away_nm, home_nm = nick(comp['away']['name']), nick(comp['home']['name'])
            if mc == 'prop':
                if cp.get('side') not in ('over', 'under'):
                    print(f'  REFUSE {gid}: prop side {cp.get("side")!r} must be over|under', file=sys.stderr)
                    return 3
                pv = espn_prop(q['league'], q['event_id'], cp.get('player'), cp.get('market'))
                try:
                    ln = Decimal(str(cp.get('line')))
                except (InvalidOperation, ValueError):
                    pv = None
                if pv is None:
                    print(f'  REFUSE {gid}: independent prop verification failed - chain stops, no write', file=sys.stderr)
                    return 3
                val, pside = pv
                want_res = 'PUSH' if val == ln else ('WON' if (cp['side'] == 'over') == (val > ln) else 'LOST')
                # a prop's game context is the player's own team, not the over/under side
                game = ('vs ' + away_nm) if pside == 'home' else ('at ' + home_nm)
            else:
                want_res = score_result(mc, cp.get('side'), cp.get('line'), away_sc, home_sc)
                if mc == 'total':
                    game = f'{away_nm} at {home_nm}'
                else:
                    game = ('vs ' + away_nm) if cp.get('side') == 'home' else ('at ' + home_nm)
            if want_res is None or res != want_res:
                print(f'  REFUSE {gid}: result {res} contradicts the verified final ({mc} {cp.get("side")} '
                      f'{cp.get("line")} on {q["score"]!r} -> {want_res})', file=sys.stderr)
                return 3
            score_txt = f'{away_ab} {away_sc}, {home_ab} {home_sc}'
        if res == 'WON': rw += 1
        elif res == 'LOST': rl += 1
        expected = q['record_after']
        if f'{rw}-{rl}' != expected:
            print(f'  REFUSE {gid}: chain mismatch - running {rw}-{rl} != record_after {expected}', file=sys.stderr)
            return 3
        # 5. a pick already on its card date's row (same pick, same final) is never counted twice;
        # across days the grade key in record_done.json and the card-date filing above hold
        days = hist['days']
        if any(p.get('name') == q['pick'] and p.get('score') == score_txt
               for d in days if d.get('date') == card_date for p in d['picks']):
            print(f'  REFUSE {gid}: {q["pick"]} {score_txt} is already on the record - duplicate', file=sys.stderr)
            return 3
        # history day row: the pick's own card date, inserted in date order when new
        day = next((d for d in days if d.get('date') == card_date), None)
        if day is None:
            d0 = datetime.strptime(card_date, '%Y-%m-%d')
            day = {'date': card_date, 'label': d0.strftime('%A, %b %-d'), 'record': '0-0', 'units': '+0.00u',
                   'brief': '', 'picks': []}
            days.insert(next((i for i, d in enumerate(days) if str(d.get('date')) > card_date), len(days)), day)
        _row = {'name': q['pick'], 'game': game, 'odds': q['locked_american'],
                'units': q['stake_units'], 'result': {'WON': 'W', 'LOST': 'L', 'PUSH': 'P'}[res],
                'score': score_txt, '_delta': str(Decimal(str(q['delta_units_exact'])))}
        if accepted is not None:
            _row['accepted_entry'] = accepted_basis
        _row.update(disclosure)
        if isinstance(q.get('learning'), str) and q['learning'].strip():
            _row['learning'] = q['learning'].strip()
        day['picks'].append(_row)
        dw = sum(1 for p in day['picks'] if p['result'] == 'W')
        dl = sum(1 for p in day['picks'] if p['result'] == 'L')
        day['record'] = f'{dw}-{dl}'
        if not any(t is day for t in touched):
            touched.append(day)
        processed.append((q, Decimal(str(q['delta_units_exact']))))
        print(f'  graded {gid}: {q["pick"]} {res} {score_txt} [{card_date} card] -> record {rw}-{rl}')

    if not processed:
        print('nothing new processed')
        return 0
    # ROUND-ONCE CORE RULE (main 9/27 3:19): deltas and units_after_exact travel at FULL
    # ledger precision; every displayed total is computed from exact canonical values and
    # quantized ONCE at display time. Never sum pre-rounded deltas - one-cent drift results.
    # day units = exact sum of per-pick deltas graded into each day this run wrote to
    for day in touched:
        du = sum((Decimal(p['_delta']) for p in day['picks'] if '_delta' in p), Decimal('0'))
        if any('_delta' in p for p in day['picks']):
            day['units'] = fmt_units(du)

    last = processed[-1][0]
    man['record'] = last['record_after']
    man['units_pl'] = fmt_units(Decimal(str(last['units_after_exact'])))
    # freshness truth (main Sep 27): the write moves manifest state, so its freshness label
    # must move with it - stamp `updated` at write time, PT, same display format ingest uses.
    from zoneinfo import ZoneInfo as _ZI
    import datetime as _dtc
    _now=_dtc.datetime.now(_ZI('America/Los_Angeles'))
    man['updated']=re.sub(r'(\d), 0', r'\1, ', _now.strftime('%b %d, %I:%M %p PT').replace(' 0',' '))
    done.setdefault('processed', []).extend(q['grade_id'] for q, _ in processed)
    done['at'] = datetime.now(timezone.utc).isoformat()
    # exact units anchor for the next grade's chain check (the manifest shows units rounded)
    done['record_after'] = last['record_after']
    done['units_after_exact'] = str(Decimal(str(last['units_after_exact'])))
    remaining = [q for q in reqs if q['grade_id'] not in done['processed']]

    json.dump(man, open(MAN, 'w'), indent=2)
    json.dump(hist, open(HIST, 'w'), indent=2)
    json.dump(done, open(DONE, 'w'), indent=2)
    json.dump({'requests': remaining}, open(REQ, 'w'), indent=2)
    # API MIRROR (main 9/27 6:20, option B): slates/api_record.json in the
    # api.rix-picks.com/record worker's exact GET shape, emitted on every apply.
    # graded_pick/source ride in analysis's request payload; omitted when absent -
    # no invented state.
    mirror = {
        'w': rw, 'l': rl,
        'pct': float((Decimal(rw * 100) / (rw + rl)).quantize(Decimal('0.1'))) if (rw + rl) else 0.0,
        'units': float(fmt_units(Decimal(str(last['units_after_exact'])))[:-1]),  # the manifest's own display value
        'updated': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
    }
    if last.get('graded_pick'):
        mirror['graded_pick'] = last['graded_pick']
    if last.get('source'):
        mirror['source'] = last['source']
    json.dump(mirror, open(os.path.join(ROOT, 'slates', 'api_record.json'), 'w'), indent=1)
    print(f'RECORD WRITE: record {man["record"]} units {man["units_pl"]}; {len(processed)} graded, {len(remaining)} remain')
    return 0

if __name__ == '__main__':
    sys.exit(main())
