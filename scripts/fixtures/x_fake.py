#!/usr/bin/env python3
"""Offline X harness for the spend-safety fixtures (scripts/test_x_*.py). No fixture that uses it
can make a real X call.

As a library: scratch(...) builds a throwaway repo-shaped dir (slates/ with a burn ledger, news,
live games, feed, state); run(...) executes scripts/x_feed.py or scripts/news_social.py in it
through this file's driver mode; spend_24h(...) re-reads the ledger with the code's own rates.

As a driver (what run() executes; cwd = the scratch dir):
  FAKE_X_PLAN=plan.json FAKE_X_CALLS=calls.jsonl python3 x_fake.py x_feed pull
plan.json: {"default": RESP, "seq": [RESP, ...]}; RESP is {"posts": N} (HTTP 200 with N posts) or
{"error": 402} (urllib HTTPError with that code). Call i takes seq[i], then default. Every call is
appended to FAKE_X_CALLS as {"path", "params"}. The script's req() is replaced by the fake and
urllib.request.urlopen by a function that raises, so a path that bypasses req() fails the fixture
instead of reaching the network."""
import datetime, importlib, json, os, subprocess, sys, tempfile, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
UTC = datetime.timezone.utc
REQ_COST, POST_COST = 0.033, 0.005  # the code's measured rates (x_feed.py / news_social.py)


def iso(dt):
    return dt.astimezone(UTC).isoformat(timespec='seconds')


def ledger_row(hours_ago, results, now=None):
    now = now or datetime.datetime.now(UTC)
    return {'ts': iso(now - datetime.timedelta(hours=hours_ago)), 'endpoint': '/tweets/search/recent',
            'query': 'seed', 'results': results}


def rows_costing(dollars, hours_ago=1.0):
    """Ledger rows whose cost at the code's rates (33 mills a request + 5 a post, at most 100
    posts a request) is exactly `dollars`: the fewest requests that can carry it."""
    mills = round(dollars * 1000)
    for a in range(1, mills // 33 + 1):
        rest = mills - 33 * a
        if rest >= 0 and rest % 5 == 0 and rest // 5 <= 100 * a:
            posts = rest // 5
            return [ledger_row(hours_ago, posts // a + (1 if i < posts % a else 0)) for i in range(a)]
    raise AssertionError('no request mix costs exactly $%.3f' % dollars)


def scratch(ledger=(), headlines=8, games=4, pool=None, state=None):
    d = tempfile.mkdtemp(prefix='rp-xspend-')
    sl = os.path.join(d, 'slates'); os.makedirs(sl)
    now = datetime.datetime.now(UTC)
    with open(os.path.join(sl, 'x_burn.jsonl'), 'w') as f:
        for r in ledger:
            f.write(json.dumps(r) + '\n')
    teams = [('Yankees', 'Red Sox'), ('Dodgers', 'Padres'), ('Cubs', 'Brewers'), ('Mets', 'Braves'),
             ('Astros', 'Mariners'), ('Rays', 'Orioles')]
    gl = [{'matchup': f'{a} @ {b}', 'commence': (now + datetime.timedelta(hours=3 + i)).strftime('%Y-%m-%dT%H:%MZ'),
           'status': 'pre'} for i, (a, b) in enumerate(teams[:games])]
    json.dump({'generated_at': iso(now), 'leagues': [{'league': 'MLB', 'games': gl}]},
              open(os.path.join(sl, 'live_games.json'), 'w'))
    names = ['Aaron Judge', 'Shohei Ohtani', 'Pete Alonso', 'Kyle Tucker', 'Juan Soto', 'Bobby Witt',
             'Gunnar Henderson', 'Julio Rodriguez', 'Corbin Carroll', 'Elly De La Cruz', 'Jose Ramirez',
             'Freddie Freeman', 'Mookie Betts', 'Rafael Devers', 'Paul Skenes', 'Tarik Skubal',
             'Zack Wheeler', 'Logan Webb', 'Chris Sale', 'Jacob deGrom']
    latest = [{'headline': f'{names[i % len(names)]} Leads Yankees Comeback Win Over Red Sox In Game {i + 1}',
               'link': f'https://example.com/story/{i}', 'published': iso(now - datetime.timedelta(minutes=10 + i)),
               'league': 'baseball/mlb'} for i in range(headlines)]
    json.dump({'generated_at': iso(now), 'latest': latest}, open(os.path.join(sl, 'news.json'), 'w'))
    json.dump({'generated_at': '2026-10-01T01:02:02+00:00', 'source': 'x_recent_search', 'window': False,
               'items': pool or []}, open(os.path.join(sl, 'x_feed.json'), 'w'), indent=1)
    json.dump(state or {'since_id': '2105081081103806877', 'updated_at': '2026-09-30T01:19:58+00:00', 'news_since': {}},
              open(os.path.join(sl, 'x_feed_state.json'), 'w'), indent=1)
    return d


def run(d, script, argv=('pull',), plan=None, env=None, token='fixture-token'):
    """Run scripts/<script>.py main() in scratch dir d with the fake X. Returns (rc, output, calls)."""
    tag = str(len(os.listdir(d)))
    plan_p = os.path.join(d, f'.plan{tag}.json'); calls_p = os.path.join(d, f'.calls{tag}.jsonl')
    json.dump(plan or {'default': {'posts': 0}}, open(plan_p, 'w'))
    open(calls_p, 'w').close()
    e = {k: v for k, v in os.environ.items() if not k.startswith('X_') and k not in ('GITHUB_ENV',)}
    e.update({'FAKE_X_PLAN': plan_p, 'FAKE_X_CALLS': calls_p, 'PYTHONDONTWRITEBYTECODE': '1'})
    if token:
        e['X_BEARER_TOKEN'] = token
    e.update(env or {})
    r = subprocess.run([sys.executable, os.path.abspath(__file__), script] + list(argv), cwd=d, env=e,
                       capture_output=True, text=True, timeout=120)
    calls = [json.loads(l) for l in open(calls_p) if l.strip()]
    return r.returncode, r.stdout + r.stderr, calls


def ledger_rows(d):
    p = os.path.join(d, 'slates', 'x_burn.jsonl')
    return [json.loads(l) for l in open(p) if l.strip()] if os.path.exists(p) else []


def spend_24h(d, now=None):
    now = now or datetime.datetime.now(UTC)
    tot = 0
    for r in ledger_rows(d):
        ts = datetime.datetime.fromisoformat(r['ts'].replace('Z', '+00:00'))
        if now - ts < datetime.timedelta(hours=24):
            tot += round(REQ_COST * 1000) + round(POST_COST * 1000) * int(r.get('results', 0))
    return tot / 1000.0


def _driver():
    def _no_network(*a, **k):
        raise AssertionError('fixture attempted a real network call')
    urllib.request.urlopen = _no_network
    sys.path.insert(0, SCRIPTS)
    name = sys.argv[1]
    mod = importlib.import_module(name)
    plan = json.load(open(os.environ['FAKE_X_PLAN']))
    calls_path = os.environ['FAKE_X_CALLS']
    st = {'i': 0, 'id': 2200000000000000000}

    def fake_req(path, params=None):
        i = st['i']; st['i'] += 1
        with open(calls_path, 'a') as f:
            f.write(json.dumps({'path': path, 'params': params or {}}) + '\n')
        seq = plan.get('seq') or []
        resp = seq[i] if i < len(seq) else plan.get('default', {'posts': 0})
        if 'error' in resp:
            raise urllib.error.HTTPError('https://api.x.com/2' + path, int(resp['error']),
                                         resp.get('reason', 'Payment Required'), {}, None)
        n = int(resp.get('posts', 0))
        cap = int((params or {}).get('max_results', n) or n)
        n = min(n, cap)  # the API never returns more than max_results
        data, users = [], []
        for _ in range(n):
            st['id'] += 1
            tid = str(st['id'])
            data.append({'id': tid, 'author_id': 'u' + tid, 'created_at': iso(datetime.datetime.now(UTC)),
                         'text': 'Yankees beat the Red Sox 5-3 in the playoff opener as the bullpen held on late.',
                         'public_metrics': {'like_count': 5}})
            users.append({'id': 'u' + tid, 'username': 'fan' + tid[-4:], 'name': 'Fan ' + tid[-4:]})
        body = {'data': data, 'includes': {'users': users}, 'meta': {'newest_id': data[-1]['id']} if data else {}}
        return 200, body

    mod.req = fake_req
    sys.argv = [name + '.py'] + sys.argv[2:]
    mod.main()


if __name__ == '__main__':
    _driver()
