#!/usr/bin/env python3
"""Durable card manifest builder. CARD PRICE BASIS (his call 9/26 10:14 PM PT,
phonemsg-01M3GMJBQVQX5099CH3AN4TB3E): card_american converts from the KALSHI ASK the gate
consumed (units.cents_to_american), card_source = 'Kalshi ask at lock', and the card shows the
gate's own numbers (model vs Kalshi ask, gross/net edge) - never book-consensus display.
Forward-only: previously published cards keep their published prices.
Usage: build_manifest.py candidates.json out_manifest.json [--preview] [--meta meta.json]
                         [--owner-directive '{"num": N, "rules": ["vegas"|"units"], "words": "<his verbatim words>"}' ...]
candidate row: {num,name,side,away,home,commence,eid,espn_league,units,kalshi:{cents,team,url,ticker},model,gross_c,net_c[,owner_directive]}
Owner rules (Vegas teams, J-096 unit ladder) refuse closed unless an owner directive covers them. His
directive's verbatim words never reach the served manifest: the manifest pick carries only
{rules, via, ref}, and the words go to the private picks ledger row beside the same ref.

PUBLICATION SHAPE (swamp rounds 4): a preview NEVER touches the production ledger - it writes
to picks.preview.jsonl. Production publication holds a single-writer flock, reads the ledger
INSIDE the lock, appends canonical rows, publishes the manifest via os.replace, then reads
back and verifies every appended row. Crash recovery: re-running with the same candidates is
idempotent (identical rows skip, manifest publishes); re-running with different candidates on
the same key refuses closed rather than forking the card record."""
import json, sys, datetime, os, fcntl, hashlib, re
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
# builder renders whatever card has landed and carries no such gate.
#  - Vegas (L-VEGAS-GATE-001, Sep 25): "never gamble on or against any Vegas teams ever" and
#    "Exclude A's going forward from today too". A pick in a game involving a Las Vegas team is
#    refused: Raiders (NFL), Golden Knights (NHL), Aces (WNBA), Athletics/A's (MLB), UNLV
#    (college). A nickname counts only inside its own league (Texas Tech Red Raiders is CFB), and
#    a team named for Las Vegas counts in any league. The rule is about teams: the individual
#    sports (racing, golf, tennis, MMA, boxing) skip it - a NASCAR race at Las Vegas Motor
#    Speedway is no Vegas team - and any other league, listed or not, keeps it.
#  - Units (J-096): 5u, 10u, 15u or 100u - no other size.
# A pick breaking either passes only on an explicit owner directive that names the rule and
# carries his verbatim words - on the candidate row ('owner_directive') or on the command line
# (--owner-directive JSON, repeatable, keyed by pick num). Anything else refuses closed before any
# write. manifest.json (and every manifests/ snapshot of it) is served publicly, so the manifest
# pick records owner_directive as {rules, via, ref} only - ref is the first 12 hex digits of the
# sha256 of his words - and his verbatim words (with 'at' when given) are written only to the
# private picks ledger row (RIX_PICKS_LEDGER), beside the same ref. No message prints his words.
UNIT_LADDER = (5, 10, 15, 100)
_VEGAS_NICK = {'football/nfl': ('raiders',), 'hockey/nhl': ('golden knights',), 'basketball/wnba': ('aces',),
               'baseball/mlb': ('athletics', "a's"), 'football/college-football': ('unlv',),
               'basketball/mens-college-basketball': ('unlv',), 'basketball/womens-college-basketball': ('unlv',)}
_VEGAS_ANY = ('las vegas', 'vegas')
_INDIVIDUAL_SPORTS = ('racing', 'golf', 'tennis', 'mma', 'boxing')  # espn_league's sport segment
OWNER_RULES = ('vegas', 'units')

def _words(s):
    return ' ' + re.sub(r"[^a-z0-9']+", ' ', str(s or '').lower().replace('\u2019', "'")) + ' '

def vegas_hit(c):
    """Which field puts a Las Vegas team on this candidate (on it or against it), else None."""
    if str(c.get('espn_league') or '').split('/')[0] in _INDIVIDUAL_SPORTS:
        return None  # no teams: a venue or event named for Las Vegas is not a Vegas team
    names = _VEGAS_ANY + _VEGAS_NICK.get(str(c.get('espn_league') or ''), ())
    for field in ('home', 'away', 'name'):
        w = _words(c.get(field))
        if any(' ' + n + ' ' in w for n in names):
            return f"{field} {c.get(field)!r}"
    return None

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

def directive_ref(words):
    """The public handle of his directive: the first 12 hex digits of sha256(his words)."""
    return hashlib.sha256(words.encode('utf-8')).hexdigest()[:12]

def public_directive(d):
    """What the served manifest may say about a directive: the rules it covers, how it came, its ref."""
    return {'rules': d['rules'], 'via': d['via'], 'ref': d['ref']}

def owner_directive(d, via):
    """A well-formed owner directive {'rules': [...], 'words': <his verbatim words>}, else None.
    The result is private (it carries his words): only public_directive() of it may be published."""
    if not isinstance(d, dict):
        return None
    words = d.get('words')
    rules = d.get('rules')
    rules = [rules] if isinstance(rules, str) else rules
    if not isinstance(words, str) or not words.strip() or not isinstance(rules, list) or not rules \
            or not set(rules) <= set(OWNER_RULES):
        return None
    out = {'rules': sorted(set(rules)), 'via': via, 'ref': directive_ref(words), 'words': words}
    if d.get('at'):
        out['at'] = str(d['at'])
    return out

def owner_rules_gate(cands, argv):
    """{candidate index: directive} for the picks that pass; ValueError (nothing written) otherwise."""
    # a pick num names exactly one pick: an --owner-directive is keyed by it and must never cover two
    _nums = [c.get('num') for c in cands]
    _shared = sorted({repr(n) for n in _nums if _nums.count(n) > 1})
    if _shared:
        raise ValueError(f"fail closed: pick num {', '.join(_shared)} is on more than one candidate - a pick num names one pick")
    cli = {}
    nth = 0
    for i, a in enumerate(argv):
        if a == '--owner-directive':
            nth += 1
            try:
                raw = json.loads(argv[i + 1])
            except (IndexError, ValueError):
                raise ValueError('fail closed: --owner-directive needs a JSON object {"num", "rules", "words"}')
            d = owner_directive(raw, 'cli')
            if d is None or not isinstance(raw.get('num'), int) or isinstance(raw.get('num'), bool):
                # never echo the argument: it carries his words
                raise ValueError(f'fail closed: --owner-directive #{nth} must carry num, rules (vegas|units) and his verbatim words')
            if raw['num'] in cli:
                raise ValueError(f"fail closed: two --owner-directive entries for pick #{raw['num']}")
            cli[raw['num']] = d
    nums = {c.get('num') for c in cands}
    stray = sorted(n for n in cli if n not in nums)
    if stray:
        raise ValueError(f'fail closed: --owner-directive for pick(s) {stray} not in the candidates')
    out, problems = {}, []
    for i, c in enumerate(cands):
        d = None
        if 'owner_directive' in c:
            d = owner_directive(c['owner_directive'], 'candidate')
            if d is None:
                problems.append(f"#{c.get('num')} {c.get('name')}: owner_directive must name rules (vegas|units) and carry his verbatim words")
                continue
            if c.get('num') in cli:
                problems.append(f"#{c.get('num')} {c.get('name')}: owner directive given twice (candidate row and --owner-directive)")
                continue
        d = d or cli.get(c.get('num'))
        broken = []
        v = vegas_hit(c)
        if v:
            broken.append(('vegas', f'Las Vegas team ({v}): never on or against a Vegas team'))
        if units_rung(c.get('units')) is None:
            broken.append(('units', f"units {c.get('units')!r} not on the J-096 ladder (5u, 10u, 15u, 100u)"))
        missing = [msg for rule, msg in broken if not (d and rule in d['rules'])]
        if missing:
            problems.append(f"#{c.get('num')} {c.get('name')}: " + '; '.join(missing))
        elif d:
            out[i] = d
    if problems:
        raise ValueError('fail closed (owner rules, runbook 2.5/2.8): ' + ' | '.join(problems)
                         + ' - passes only on an owner directive naming the rule with his verbatim words')
    return out

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

def main():
    cands = json.load(open(sys.argv[1]))
    preview = '--preview' in sys.argv
    out = sys.argv[2] if not sys.argv[2].startswith('--') else sys.argv[3]
    meta = {}
    if '--meta' in sys.argv:
        meta = json.load(open(sys.argv[sys.argv.index('--meta')+1]))
    directives = owner_rules_gate(cands, sys.argv)  # before any lookup or write
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
    for ci, c in enumerate(cands):
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
        cents = c['kalshi']['cents']
        if type(cents) is not int or not (1 <= cents <= 99):  # strict: bool is not int here
            raise ValueError(f"fail closed: bad kalshi cents {cents!r} on {c.get('name')}")
        am = cents_to_american(cents)
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
            'best_book': 'Kalshi',
            'kalshi': {'url': c['kalshi'].get('url') or 'https://kalshi.com/markets/{}/{}'.format(c['kalshi']['ticker'].split('-')[0].lower(), c['kalshi']['ticker'].rsplit('-',1)[0].lower()),  # event-level URL: build_gh_page resolves the gate via the LAST segment (event ticker)
                       'cents': cents, 'team': c['kalshi']['team'], 'gate_cents': cents,
                       'ticker': c['kalshi']['ticker']},
            'card_american': am, 'card_source': 'Kalshi ask at lock',
            'card_ts': _ts_map.get((str(c['eid']),) + _ikey(mc, c['side'], c))
                       or _prod_ts.get((str(c['eid']),) + _ikey(mc, c['side'], c))
                       or now,  # first lock only; regenerations inherit, never restamp
            'polymarket': c.get('polymarket'), 'dkp': c.get('dkp'),
            **({'owner_directive': public_directive(directives[ci])} if ci in directives else {})})
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
    inherit = {}
    if not preview and os.path.exists(PROD_MANIFEST_PATH):
        try: inherit = json.load(open(PROD_MANIFEST_PATH))
        except Exception: inherit = {}
    def _field(name, required=True):
        if name in meta: return meta[name]
        if name in inherit: return inherit[name]
        if required: raise ValueError(f"fail closed: manifest metadata '{name}' missing from --meta and no readable production manifest to inherit from")
        return None
    manifest = {
        'date': date_s, 'date_label': meta.get('date_label', dlab),
        'updated': meta.get('updated', dpt.strftime('%b %-d, %-I:%M %p PT')),
        **({} if preview else {'posted_at': posted_at_of(picks, now_utc)}),
        'record': _field('record'), 'units_pl': _field('units_pl'),
        'units_ledger': _field('units_ledger', required=False),
        'yesterday': _field('yesterday', required=False),
        'status_note': _field('status_note', required=False),
        'parlay': meta.get('parlay', inherit.get('parlay')),
        'preview': preview, 'picks': picks}
    manifest['pick_content_hash'] = _pick_content_hash(manifest)

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
        for ci, (c, p) in enumerate(zip(cands, picks)):
            key = (str(c['eid']),) + _ikey(c.get('market_class','ml'), c['side'], c)
            # his directive (verbatim words) lives on the private ledger row only; its identity
            # (ref + rules) is part of the row, so other words for a published pick never fork it
            d_new = directives.get(ci)
            _did = lambda d: ((d or {}).get('ref'), sorted((d or {}).get('rules') or []))
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
                          **({'player': c.get('player'), 'market': c.get('market')} if key[1] == 'prop' else {})}
                same_dir = _did(r.get('owner_directive')) == _did(d_new)
                identical = same_dir and all(r.get(f) == v for f, v in newrow.items())
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
                    if not same_dir:  # refs only: his words are never printed
                        diffs['owner_directive ref'] = ((r.get('owner_directive') or {}).get('ref'), (d_new or {}).get('ref'))
                    raise ValueError(f"fail closed: conflicting canonical pick row for {key} - fields differ {diffs} - refusing to fork the card record")
            ledger_rows.append({'kind':'pick','event_id':key[0],'market_class':key[1],'side':key[2],
                                'name':c['name'],'units':c['units'],
                                'entry_c':p['kalshi']['cents'],'card_american':p['card_american'],
                                'card_source':'Kalshi ask at lock','card_ts':p['card_ts'],
                                'kalshi_ticker':p['kalshi']['ticker'],'commence':c['commence'],
                                **({'line': c.get('line')} if key[1] in ('spread','total','prop') else {}),
                                **({'player': c.get('player'), 'market': c.get('market')} if key[1] == 'prop' else {}),
                                **({'owner_directive': d_new} if d_new else {}),
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
    for p in picks: print(f"  #{p['num']} {p['name']} {p['units']} @{p['odds']} (Kalshi {p['kalshi']['cents']}c) | {p['sub']}")
if __name__ == '__main__': main()
