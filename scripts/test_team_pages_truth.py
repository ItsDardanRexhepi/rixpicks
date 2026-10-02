#!/usr/bin/env python3
# Team-page truth fixture (Oct 1 site sweep, LS-07/LS-08/LS-09). Runs the shipped builders'
# real build_team_pages offline against canned ESPN payloads shaped like the live API:
#  - LS-08: ESPN's teams listing returns 50 rows unless asked for more, and cards name college
#    and MLS sides by short forms ('UCLA', 'Penn State', 'Atlanta United') that never equal
#    ESPN's displayName - twelve served team pages came out blank although ESPN had their games.
#  - LS-09: ESPN returns soccer schedules newest-first; 'Form - last 5', the streak and
#    'Scoring - last 10' sliced the oldest games of the season (Feb-Mar shown in late Sep).
#  - LS-07: the site.api injuries endpoint answers {} for every team; the page claimed
#    'None reported.' - only an affirmatively empty injury list may say that.
# Run: python3 scripts/test_team_pages_truth.py [builder.py ...]  (default: both twins)
import ast, datetime, html, json, os, re, sys, tempfile
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
BUILDERS = [os.path.abspath(b) for b in sys.argv[1:]] or [os.path.join(HERE, 'build_gh_page_v2.py'), os.path.join(HERE, '_build_nocanon_v2.py')]

def load_team_builder(path):
    """Exec build_team_pages plus every top-level function it (transitively) calls."""
    src = open(path).read()
    tree = ast.parse(src)
    fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    want, todo = [], ['build_team_pages']
    while todo:
        nm = todo.pop()
        if nm in want or nm not in fns: continue
        want.append(nm)
        for sub in ast.walk(fns[nm]):
            if isinstance(sub, ast.Name) and sub.id in fns: todo.append(sub.id)
    ns = {'__file__': path, '__name__': 'team_fixture', 'os': os, 're': re, 'html': html,
          'json': json, 'sys': sys, 'TEAM_META': {}, '_MLBAM': {}}
    body = [fns[n] for n in fns if n in want]
    exec(compile(ast.Module(body=body, type_ignores=[]), path, 'exec'), ns)
    return ns

PT = ZoneInfo('America/Los_Angeles')
NOW = datetime.datetime.now(datetime.timezone.utc)
def iso(dt): return dt.strftime('%Y-%m-%dT%H:%MZ')
FUTURE = iso(NOW + datetime.timedelta(days=3))

def team(tid, display, short, location, abbr, nickname=None):
    return {'team': {'id': tid, 'displayName': display, 'shortDisplayName': short, 'location': location,
                     'abbreviation': abbr, 'nickname': nickname or location, 'name': display.split()[-1]}}

# 50 filler rows first: ESPN's default page. Toledo sits past it, as on the live listing.
CFB_ROWS = [team(str(9000 + i), 'Filler %d Owls' % i, 'Filler %d' % i, 'Filler %d' % i, 'F%d' % i) for i in range(50)]
CFB_ROWS += [team('2649', 'Toledo Rockets', 'Toledo', 'Toledo', 'TOL'),
             team('26', 'UCLA Bruins', 'UCLA', 'UCLA', 'UCLA'),
             team('213', 'Penn State Nittany Lions', 'Penn State', 'Penn State', 'PSU'),
             team('7001', 'Springfield Bears', 'Springfield', 'Springfield', 'SPB'),
             team('7002', 'Springfield Pride', 'Springfield', 'Springfield', 'SPP')]
MLS_ROWS = [team('18418', 'Atlanta United FC', 'Atlanta', 'Atlanta United FC', 'ATL'),
            team('18986', 'Nashville SC', 'Nashville', 'Nashville SC', 'NSH')]

def listing(rows): return {'sports': [{'leagues': [{'teams': rows}]}]}

def ev(eid, date, me_id, me_score, opp_abbr, opp_score, home=True, done=True):
    me = {'homeAway': 'home' if home else 'away', 'team': {'id': me_id}, 'score': {'value': me_score} if done else None}
    op = {'homeAway': 'away' if home else 'home', 'team': {'id': '1' + me_id, 'abbreviation': opp_abbr, 'displayName': opp_abbr}, 'score': {'value': opp_score} if done else None}
    return {'id': eid, 'date': date, 'competitions': [{'status': {'type': {'completed': done, 'state': 'post' if done else 'pre'}}, 'competitors': [me, op]}]}

# Nashville: 27 MLS matches served newest-first, exactly as ESPN's soccer schedule does.
# Feb-Mar: five wins; Sep: L, L, W, D, L (newest last in time).
NSH = []
spring = ['2026-02-21', '2026-02-28', '2026-03-07', '2026-03-14', '2026-03-21']
for i, d in enumerate(spring): NSH.append(ev('6%02d' % i, d + 'T23:30Z', '18986', 3, 'S%d' % i, 0))
for i in range(17): NSH.append(ev('7%02d' % i, '2026-%02d-%02dT23:30Z' % (4 + i // 4, 1 + (i % 4) * 7), '18986', 2, 'M%d' % i, 1))
latest = [('2026-09-06', 0, 1), ('2026-09-13', 1, 2), ('2026-09-17', 2, 0), ('2026-09-20', 1, 1), ('2026-09-27', 0, 3)]
for i, (d, a, b) in enumerate(latest): NSH.append(ev('8%02d' % i, d + 'T23:30Z', '18986', a, 'L%d' % i, b))
NSH_NEWEST_FIRST = sorted(NSH, key=lambda e: e['date'], reverse=True)

def sched_simple(tid):
    return {'events': [ev(tid + '1', '2026-09-20T19:00Z', tid, 24, 'OPA', 10), ev(tid + '2', '2026-09-27T19:00Z', tid, 16, 'OPB', 41),
                       ev(tid + '3', FUTURE, tid, 0, 'OPC', 0, done=False)]}

CALLS = []
def fake_get(url):
    CALLS.append(url)
    m = re.match(r'https://site\.api\.espn\.com/apis/site/v2/sports/([a-z.\-]+/[a-z0-9.\-]+)/teams(?:/(\d+)(/schedule|/injuries)?)?(?:\?(.*))?$', url)
    if not m: raise OSError('no fixture route: ' + url)
    lg, tid, sub, qs = m.groups()
    if tid is None:
        rows = CFB_ROWS if lg == 'football/college-football' else MLS_ROWS if lg == 'soccer/usa.1' else []
        lim = re.search(r'limit=(\d+)', qs or '')
        return listing(rows[:int(lim.group(1)) if lim else 50])
    if sub == '/injuries':
        if tid == '213': raise OSError('injuries endpoint timed out')
        if tid == '26': return {'injuries': []}
        if tid == '18418': return {'injuries': [{'athlete': {'displayName': 'Test Keeper'}, 'status': 'Out', 'type': 'Hamstring'}]}
        return {}
    if sub == '/schedule':
        if tid == '18986': return {'events': NSH_NEWEST_FIRST}
        return sched_simple(tid)
    return {'team': {'logos': [{'href': 'https://a.espncdn.com/i/teamlogos/%s.png' % tid}], 'record': {'items': [{'type': 'total', 'summary': '3-2'}]}}}

CARD = {'picks': [
    {'num': 1, 'espn_league': 'football/college-football', 'game': {'away': 'UCLA', 'home': 'Penn State', 'commence': FUTURE}},
]}
HISTORY = {'picks': [
    {'espn_league': 'football/college-football', 'game': {'away': 'Toledo Rockets', 'home': 'Springfield'}},
    {'espn_league': 'soccer/usa.1', 'game': {'away': 'Atlanta United', 'home': 'Nashville SC'}},
]}

def text_of(page):
    body = page.split('<body>')[1].split('<script>')[0]
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' | ', body)))

def section(page, title, nxt):
    t = text_of(page)
    a = t.index(title) + len(title)
    return t[a:t.index(nxt, a)]

fails = []
def check(label, cond):
    print(('OK   ' if cond else 'FAIL ') + label)
    if not cond: fails.append(label)

for B in BUILDERS:
    tag = os.path.basename(B)
    ns = load_team_builder(B)
    work = tempfile.mkdtemp(prefix='rp-team-')
    os.makedirs(os.path.join(work, 'manifests'))
    json.dump(HISTORY, open(os.path.join(work, 'manifests', 'manifest-fixture.json'), 'w'))
    ns['out'] = os.path.join(work, 'index.html'); ns['_espn_get'] = fake_get
    cwd = os.getcwd(); os.chdir(work)
    try:
        CALLS.clear()
        pages = ns['build_team_pages'](CARD, '', 'b1')
    finally:
        os.chdir(cwd)
    get = lambda slug: pages.get('team-%s.html' % slug, '')

    # LS-08: every one of these teams exists in ESPN's listing - none may render blank
    for slug, why in (('toledo-rockets', 'listed past ESPN\'s 50-row default page'),
                      ('ucla', 'card uses the short name UCLA'),
                      ('penn-state', 'card uses the location name Penn State'),
                      ('atlanta-united', 'card drops ESPN\'s FC suffix')):
        pg = get(slug)
        check(f'{tag} LS-08 team-{slug} resolves ({why}): logo, record and games render',
              pg and '<img src=' in pg and 'Record 3-2' in pg and 'No recent games found.' not in pg
              and 'No upcoming games listed.' not in pg)
    check(f'{tag} LS-08 team listing asks ESPN for the full list, not its 50-row default page',
          any('/college-football/teams?' in u and 'limit=' in u for u in CALLS))
    sp = get('springfield')
    check(f'{tag} LS-08 ambiguous alias (two Springfield teams) is never guessed', sp and 'No recent games found.' in sp and '<img src=' not in sp)

    # LS-09: newest-first soccer schedule must still show the LATEST five, newest on top
    nsh = get('nashville-sc')
    form = section(nsh, 'Form - last 5', 'Scoring - last 10') if nsh else ''
    rows = [r.strip() for r in form.split('|') if r.strip()]
    check(f'{tag} LS-09 Form shows the five latest matches, newest first',
          [r.rsplit(' · ', 1)[-1] for r in rows] == ['09-27', '09-20', '09-17', '09-13', '09-06'])
    check(f'{tag} LS-09 Form carries no Feb-Mar match', not re.search(r'· 0[23]-', form))
    check(f'{tag} LS-09 streak comes from the latest match (L1), not the season opener', 'Streak L1' in nsh)
    l10 = sorted(NSH, key=lambda e: e['date'])[-10:]
    sc = [(e['competitions'][0]['competitors'][0]['score']['value'], e['competitions'][0]['competitors'][1]['score']['value']) for e in l10]
    want = 'Scored %.1f · allowed %.1f per game over last 10' % (sum(a for a, _ in sc) / 10, sum(b for _, b in sc) / 10)
    check(f'{tag} LS-09 Scoring - last 10 averages the latest ten matches ({want})', want in text_of(nsh))

    # LS-07: an injury source that says nothing is 'unavailable', never 'None reported'
    inj = lambda slug: section(get(slug), 'Injuries', 'Stats refresh') if get(slug) else ''
    check(f'{tag} LS-07 empty {{}} injuries payload reads unavailable', 'Injury data unavailable' in inj('toledo-rockets') and 'None reported' not in inj('toledo-rockets'))
    check(f'{tag} LS-07 failed injuries fetch reads unavailable', 'Injury data unavailable' in inj('penn-state') and 'None reported' not in inj('penn-state'))
    check(f'{tag} LS-07 team with no resolved id reads unavailable', 'Injury data unavailable' in inj('springfield') and 'None reported' not in inj('springfield'))
    check(f'{tag} LS-07 affirmatively empty injury list still reads None reported', 'None reported.' in inj('ucla'))
    check(f'{tag} LS-07 reported injuries still list the player', 'Test Keeper · Out - Hamstring' in inj('atlanta-united'))
    check(f'{tag} LS-07 no page claims None reported unless its source returned an empty list',
          [s for s, p in pages.items() if 'None reported.' in p] == ['team-ucla.html'])

print(('ALL OK' if not fails else '%d FAIL' % len(fails)))
sys.exit(1 if fails else 0)
