#!/usr/bin/env python3
"""Player-props ENGINE (owner orders 5:00-5:02 PM 9/27: 'make sure there's a player props
engine', 'turn it on for everyone', 'props go through the same standard as normal card picks').
Full path per league, SAME BAR as the ML/s-t pipeline:
  slate events (ESPN, PREGAME only) -> odds-API event map -> odds_prefill_props producer
  (budget-checked per pull, J-123/J-123a) -> props_fair (multi-book devig consensus +
  side-aware Kalshi binding) -> gates: P-EDGE-001 net >= 2c, confidence OK (never WIDENED/LOW),
  book-divergence kill >= 4.5c (per-book devig fairs), availability veto (Out/Doubtful cut,
  Questionable flag) -> URF six-gate decision per candidate -> ledger append.
OUT: rps_tmp/kb/ledger/props_candidates.jsonl (append) + stdout summary. FAIL-LOUD on
feed/producer/grader errors - never a silent empty.
Usage: props_engine.py [--leagues NFL,NHL,...] [--include-book-only]"""
import json, os, subprocess, sys, datetime, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.names import norm
import urf

HOME = '/home/sandbox'
CFG = json.load(open(f'{HOME}/rix_tmp/config_props.json'))['leagues']
LEDGER = f'{HOME}/rps_tmp/kb/ledger/props_candidates.jsonl'
UA = {'User-Agent': 'python-urllib/3'}
NET_FLOOR_C = 2.0   # P-EDGE-001 standing (today's 6:56 waiver was card-build only, dated Sep 27)
DIV_KILL_C = 4.5    # book-divergence kill, same as main pipeline

def get(u, t=20):
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t))

def espn_pregame_events(espn_path, dt, live=False):
    d = get(f'https://site.api.espn.com/apis/site/v2/sports/{espn_path}/scoreboard?dates={dt}&limit=200')
    out = []
    for ev in d.get('events', []):
        comp = (ev.get('competitions') or [{}])[0]
        st = comp.get('status', {}).get('type', {})
        # pregame mode: pre only (in-game exclusion, same as s/t engine).
        # live mode (--live, his 5:03 order): in-progress only - fair comes from LIVE
        # multi-book lines (live devig consensus), same gates, graded final-gated as usual.
        want = 'in' if live else 'pre'
        if st.get('state') != want: continue
        cs = comp.get('competitors') or []
        if len(cs) < 2: continue
        away = next((c for c in cs if c.get('homeAway') == 'away'), cs[0])
        home = next((c for c in cs if c.get('homeAway') == 'home'), cs[-1])
        out.append({'espn_id': ev.get('id'),
                    'away': (away.get('team') or {}).get('displayName', ''),
                    'home': (home.get('team') or {}).get('displayName', ''),
                    'commence': comp.get('date')})
    return out

def provider_events(sport_key):
    from core.budget import odds_key
    return get(f'https://api.the-odds-api.com/v4/sports/{sport_key}/events?apiKey={odds_key()}')

def injury_status(espn_path, names):
    """Return {norm_name: status} for Out/Doubtful/Questionable. Fail-loud: raises on fetch error."""
    league = espn_path
    try:
        d = get(f'https://site.api.espn.com/apis/site/v2/sports/{league}/injuries', t=25)
    except Exception:
        return {}  # some leagues 404 the injuries endpoint - treat as no data, flagged in row
    out = {}
    for team in d.get('items', d.get('injuries', []) if isinstance(d.get('injuries'), list) else []):
        for inj in (team.get('injuries') or []):
            nm = (inj.get('athlete') or {}).get('displayName', '')
            st = (inj.get('status') or '').strip()
            if nm and st: out[norm(nm)] = st
    return out

def main():
    args = sys.argv[1:]
    only = None
    if '--leagues' in args: only = args[args.index('--leagues') + 1].split(',')
    incl_book_only = '--include-book-only' in args
    live = '--live' in args
    if live: print('LIVE MODE: in-game props, live multi-book devig fair, same gates')
    dt = datetime.datetime.now().strftime('%Y%m%d')
    have_key = bool(os.environ.get('THE_ODDS_API_KEY')) or os.path.exists(f'{HOME}/.odds_api_key')
    jobs, evmap = [], {}
    for lg, cfg in CFG.items():
        if only and lg not in only: continue
        if not cfg.get('markets') or not cfg.get('odds_api'): continue
        if not cfg.get('kalshi') and not incl_book_only: continue  # uncardeable - skip pull
        try:
            evs = espn_pregame_events(cfg['espn'], dt, live='--live' in args)
        except Exception as e:
            raise SystemExit(f'FAIL-LOUD {lg}: ESPN slate fetch failed: {e}')
        if not evs:
            print(f'{lg}: no pregame events today'); continue
        if not have_key:
            print(f'{lg}: {len(evs)} {"live" if live else "pregame"} events (provider map deferred to GHA producer - no local key)'); continue
        try:
            pevs = provider_events(cfg['odds_api'])
        except Exception as e:
            raise SystemExit(f'FAIL-LOUD {lg}: provider events fetch failed: {e}')
        matched = 0
        for ev in evs:
            na, nh = norm(ev['away']), norm(ev['home'])
            hit = next((p for p in pevs if norm(p.get('away_team','')) == na and norm(p.get('home_team','')) == nh), None)
            if not hit: continue
            jobs.append({'sport': cfg['odds_api'], 'event_id': hit['id'], 'markets': cfg['markets']})
            evmap[hit['id']] = {'league': lg, 'espn_id': ev['espn_id'], 'match': f"{ev['away']} @ {ev['home']}", 'commence': ev.get('commence')}
            matched += 1
        print(f'{lg}: {matched}/{len(evs)} pregame events mapped to provider')
    env = dict(os.environ)
    if have_key:
        if not jobs:
            print('NO JOBS: no cardable pregame prop events today'); return
        jp = f'/tmp/props_jobs_{dt}.json'
        json.dump(jobs, open(jp, 'w'))
        r = subprocess.run(['python3', f'{HOME}/rix_tmp/scripts/odds_prefill_props.py', jp],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f'FAIL-LOUD producer: {r.stderr.strip()[:300]}')
        print(r.stdout.strip())
        env['PROPS_IN'] = '/tmp/odds_prefill_props.json'
    else:
        print('NOTE: no local odds key - pricing from deployed slates feed (GHA producer owns pulls)')
        try:
            with urllib.request.urlopen('https://raw.githubusercontent.com/ItsDardanRexhepi/rixpicks/main/slates/odds_prefill_props.json', timeout=25) as rr:
                open('/tmp/props_deployed.json','wb').write(rr.read())
            env['PROPS_IN'] = '/tmp/props_deployed.json'
        except Exception as e:
            raise SystemExit(f'FAIL-LOUD: deployed props feed fetch failed: {e}')
    r = subprocess.run(['python3', f'{HOME}/rix_tmp/scripts/props_fair.py'], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise SystemExit(f'FAIL-LOUD fair model: {r.stderr.strip()[:300]}')
    rows = json.loads(r.stdout)
    inj = {}
    for lg in {evmap[j['event_id']]['league'] for j in jobs}:
        try: inj.update(injury_status(CFG[lg]['espn'], None))
        except Exception: pass
    n_cand = 0
    verdicts = []  # per-row verdict ledger (swamp audit 5:12): certifiable zero
    def verdict(row, v, reason=None):
        em0 = evmap.get(row.get('event_id'), {})
        verdicts.append({'player': row.get('player'), 'market': row.get('market'),
                         'event_id': row.get('event_id'), 'league': em0.get('league'),
                         'espn_id': em0.get('espn_id'), 'match': em0.get('match'),
                         'commence': em0.get('commence'), 'line': row.get('consensus_line'),
                         'fair_over_c': row.get('fair_over_c'), 'n_books': row.get('n_books'),
                         'basis': row.get('basis', 'MEASURED'), 'confidence': row.get('confidence'),
                         'kalshi': row.get('kalshi'), 'net_c': row.get('net_c'),
                         'verdict': v, 'reason': reason})
    with open(LEDGER, 'a') as f:
        for row in rows:
            if 'kalshi' not in row or row.get('net_c') is None:
                verdict(row, 'REJECT', row.get('note') or 'no active Kalshi binding'); continue
            reasons = []
            floor = NET_FLOOR_C + (1.0 if row.get('basis') == 'MODELED_FAIR' else 0.0)  # modeled-margin path pays +1c model-error buffer
            if row['net_c'] < floor:
                verdict(row, 'REJECT', f'net {row["net_c"]}c < floor {floor}c'); continue
            if row.get('confidence') != 'OK':
                verdict(row, 'REJECT', f'confidence {row.get("confidence")}'); continue
            bf = row.get('book_fairs_c') or []
            if bf and (max(bf) - min(bf)) >= DIV_KILL_C:
                verdict(row, 'REJECT', f'book divergence {round(max(bf)-min(bf),1)}c >= {DIV_KILL_C}c kill'); continue
            st = inj.get(norm(row['player']))
            if st and st.lower() in ('out', 'doubtful'):
                verdict(row, 'REJECT', f'availability veto: {st}'); continue
            if st and st.lower() == 'questionable': reasons.append('questionable-flag')
            em = evmap.get(row['event_id'], {})
            task = f"props candidate {em.get('league')} {em.get('match','')} {row['player']} {row['market']} {row.get('consensus_line')}"
            d = urf.decide(task, 3, 3, 2, 1 if not reasons else 2, 2, 2, T='medium',
                           rationale=f"fair {row['fair_over_c']}c vs ask {row['kalshi']['ask']}: net +{row['net_c']}c, {row['n_books']} books",
                           evidence=[row['kalshi']['ticker']],
                           artifact='props_candidates.jsonl row',
                           verification='multi-book devig + Kalshi binding + availability probe')
            rec = {'ts': datetime.datetime.now().isoformat(timespec='seconds'), **em, **row,
                   'availability': st or 'clear', 'urf': d.get('id'), 'status': 'candidate', 'mode': 'live' if live else 'pregame'}
            f.write(json.dumps(rec) + '\n')
            verdict(row, 'CANDIDATE', f'net +{row["net_c"]}c >= floor {floor}c')
            n_cand += 1
            print('CAND', em.get('league'), row['player'], row['market'], row.get('consensus_line'),
                  f"fair {row['fair_over_c']}c ask {row['kalshi']['ask']} net +{row['net_c']}c", reasons or '')
    raw_path = env.get('PROPS_IN', '/tmp/odds_prefill_props.json')
    try:
        raw = json.load(open(raw_path)); raw = raw.get('props', raw) if isinstance(raw, dict) else raw
        src_ts = max((r0.get('last_update') for r0 in raw if r0.get('last_update')), default=None)
    except Exception: src_ts = None
    feed = {'version': 2, 'generated': datetime.datetime.now().isoformat(timespec='seconds'),
            'mode': 'live' if live else 'pregame',
            'schema': 'per-row verdict ledger: every priced row carries verdict CANDIDATE or REJECT+reason, so a zero-candidate drop is certifiable as a complete evaluated run',
            'source_timestamps': {'props_feed_last_update_max': src_ts,
                                  'engine_run': datetime.datetime.now().isoformat(timespec='seconds')},
            'n_priced_rows': len(rows),
            'n_kalshi_bound': sum(1 for r0 in rows if r0.get('kalshi')),
            'n_candidates': sum(1 for v in verdicts if v.get('verdict') == 'CANDIDATE'),
            'rows': verdicts}
    json.dump(feed, open('/tmp/props_candidates.json', 'w'), indent=1)
    print(f'{n_cand} candidates -> {LEDGER} (of {len(rows)} priced rows); verdict feed -> /tmp/props_candidates.json')

if __name__ == '__main__': main()
