#!/usr/bin/env python3
"""Durable card manifest builder. CARD PRICE BASIS (his call 9/26 10:14 PM PT,
phonemsg-01M3GMJBQVQX5099CH3AN4TB3E): card_american converts from the KALSHI ASK the gate
consumed (units.cents_to_american), card_source = 'Kalshi ask at lock', and the card shows the
gate's own numbers (model vs Kalshi ask, gross/net edge) - never book-consensus display.
Forward-only: previously published cards keep their published prices.
Usage: build_manifest.py candidates.json out_manifest.json [--preview]
candidate row: {num,name,side,away,home,commence,eid,espn_league,units,kalshi:{cents,team,url,ticker},model,gross_c,net_c}

PUBLICATION SHAPE (swamp rounds 4): a preview NEVER touches the production ledger - it writes
to picks.preview.jsonl. Production publication holds a single-writer flock, reads the ledger
INSIDE the lock, appends canonical rows, publishes the manifest via os.replace, then reads
back and verifies every appended row. Crash recovery: re-running with the same candidates is
idempotent (identical rows skip, manifest publishes); re-running with different candidates on
the same key refuses closed rather than forking the card record."""
import json, sys, datetime, os, fcntl, hashlib
from zoneinfo import ZoneInfo
sys.path.insert(0, '/home/sandbox/rix_tmp')
from core.units import cents_to_american
from core.fill_leak import PICKS_LEDGER as _DEFAULT_PICKS_LEDGER
PICKS_LEDGER = os.environ.get('RIX_PICKS_LEDGER', _DEFAULT_PICKS_LEDGER)  # test-isolation hook


LEAGUE_KEY = {'baseball/mlb':'MLB','football/nfl':'NFL','football/college-football':'CFB',
              'basketball/wnba':'WNBA','basketball/nba':'NBA','hockey/nhl':'NHL',
              'soccer/usa.1':'MLS','mma/ufc':'UFC'}  # values must match config_leagues.json keys

def _pick_content_hash(m):
    # VERBATIM contract copy of build_gh_page.py's gate - declared hash must equal its computed hash.
    _EXCL_TOP={'num','result','_final','polycents'}
    def _canon(p):
        c={k:v for k,v in p.items() if k not in _EXCL_TOP}
        if isinstance(c.get('kalshi'),dict):
            c['kalshi']={k:v for k,v in c['kalshi'].items() if k!='cents'}
        c.pop('dkp_note',None)
        if isinstance(c.get('dkp'),dict):
            c['dkp']={k:v for k,v in c['dkp'].items() if k not in ('team_cents','home_cents','away_cents','derived','harvested')}
            if not c['dkp']: c.pop('dkp')
        return c
    rows=sorted(json.dumps(_canon(p),sort_keys=True) for p in m.get('picks',[]))
    return hashlib.sha256('\n'.join(rows).encode()).hexdigest()

PROD_MANIFEST_PATH = '/home/sandbox/rix_tmp/manifest.json'

PREVIEW_LEDGER = PICKS_LEDGER.replace('picks.jsonl', 'picks.preview.jsonl')
LOCK_PATH = PICKS_LEDGER + '.lock'

def main():
    cands = json.load(open(sys.argv[1]))
    preview = '--preview' in sys.argv
    out = sys.argv[2] if not sys.argv[2].startswith('--') else sys.argv[3]
    meta = {}
    if '--meta' in sys.argv:
        meta = json.load(open(sys.argv[sys.argv.index('--meta')+1]))
    now = datetime.datetime.now(ZoneInfo('America/Los_Angeles')).isoformat(timespec='seconds')
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
                _ts_map[(str(_r.get('event_id')), _r.get('market_class','ml'), _r.get('side'))] = _r['card_ts']
    _prod_ts = {}
    if not preview and os.path.exists(PROD_MANIFEST_PATH):
        try:
            for _p in json.load(open(PROD_MANIFEST_PATH)).get('picks', []):
                _g = _p.get('game') or {}
                if _p.get('card_ts') and _g.get('eid'):
                    _prod_ts[(str(_g['eid']), 'ml', _p.get('side'))] = _p['card_ts']
        except Exception: pass
    picks = []
    for c in cands:
        # ML-ONLY GATE (swamp round 9): spread/total manifest + scoring + grading + market
        # identity are NOT implemented end to end (finals_watch hard-codes eid|ml|side with an
        # ML comparator; fill_leak.card_price hunts the ml row). A ladder candidate through this
        # path would render on the card and then grade as ML. Refuse anything that is not
        # explicitly market_class=='ml' - never silently accept a ladder candidate.
        if c.get('market_class') != 'ml':
            raise ValueError(f"fail closed: candidate {c.get('name')} has market_class={c.get('market_class')!r} - only explicit 'ml' is buildable until spread/total grading exists end to end")
        cents = c['kalshi']['cents']
        if type(cents) is not int or not (1 <= cents <= 99):  # strict: bool is not int here
            raise ValueError(f"fail closed: bad kalshi cents {cents!r} on {c.get('name')}")
        am = cents_to_american(cents)
        picks.append({
            'num': c['num'], 'name': c['name'],
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
            'card_ts': _ts_map.get((str(c['eid']), c.get('market_class','ml'), c['side']))
                       or _prod_ts.get((str(c['eid']), 'ml', c['side']))
                       or now,  # first lock only; regenerations inherit, never restamp
            'polymarket': c.get('polymarket'), 'dkp': c.get('dkp')})
    # FULL MANIFEST CONTRACT (swamp round 8): build_gh_page.py (publish.yml publish path) reads
    # date_label, status_note, record, updated, units_pl, units_ledger, yesterday, parlay and
    # verifies pick_content_hash against its own canonicalization. Metadata comes from --meta
    # (pipeline-supplied, record tab canonical per J-100) with inherit-from-production fallback;
    # a required field available from neither fails closed - the record is never invented.
    date_s = cands[0].get('date') if cands else None
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
        'record': _field('record'), 'units_pl': _field('units_pl'),
        'units_ledger': _field('units_ledger', required=False),
        'yesterday': _field('yesterday', required=False),
        'yesterday_by_league': meta.get('yesterday_by_league', inherit.get('yesterday_by_league')),  # per-league Yesterday strip (9/27): tab-scoped, never global
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
                published_keys = {(str(x.get('game',{}).get('eid')), x.get('market_class','ml'), x.get('side'))
                                  for x in pub.get('picks',[])}
            except Exception as e:
                # FAIL CLOSED (swamp round 7): an unreadable manifest is NEVER 'nothing published' -
                # treating it as empty would let orphan rollback delete genuinely published rows.
                raise ValueError(f"fail closed: published manifest {out} exists but is unreadable ({e}) - refusing any ledger rewrite until it is repaired or removed deliberately")
        # batch-level duplicate rejection: one (event|class|side) per build
        keys = [(str(c['eid']), c.get('market_class','ml'), c['side']) for c in cands]
        dupes = {k for k in keys if keys.count(k) > 1}
        if dupes: raise ValueError(f"fail closed: duplicate candidates in batch for {sorted(dupes)} - refusing to build")
        ledger_rows = []
        for c, p in zip(cands, picks):
            key = (str(c['eid']), c.get('market_class','ml'), c['side'])
            same = [r for r in existing if r.get('kind')=='pick' and str(r.get('event_id'))==key[0]
                    and r.get('market_class','ml')==key[1] and r.get('side')==key[2]]
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
                          'kalshi_ticker':p['kalshi']['ticker'],'commence':c['commence']}
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
                                'card_source':'Kalshi ask at lock','card_ts':p['card_ts'],
                                'kalshi_ticker':p['kalshi']['ticker'],'commence':c['commence'],
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
        # READBACK VERIFICATION: staged ledger must read back exactly; appended rows must match.
        rb = [json.loads(l) for l in open(ledger)]
        if rb != final_ledger:
            raise ValueError("fail closed: ledger readback mismatch after commit - staged content does not verify")
        print(f"wrote {out}: {len(picks)} picks, preview={preview} | ledger rows appended: {len(ledger_rows)} -> {ledger} (readback verified)")
    finally:
        fcntl.flock(lockf, fcntl.LOCK_UN); lockf.close()
    for p in picks: print(f"  #{p['num']} {p['name']} {p['units']} @{p['odds']} (Kalshi {p['kalshi']['cents']}c) | {p['sub']}")
if __name__ == '__main__': main()
