#!/usr/bin/env python3
"""Promo-sentinel 9/29 7:07 regression fixtures: explicit betting tout/acquisition posts
entered the served x_feed.json while soc_match admitted none - the serialization boundary
lacked a commercial-publishability predicate. These fixtures lock the class:

  1. the four verbatim sentinel posts are REJECTED by x_feed._commercial / _banned and the
     news_social.py mirror, and by the extracted client patterns (index_v2.js RP_COMM_CTA /
     RP_COMM_TAG - byte-parity with the python regexes is asserted);
  2. innocuous sports commentary (including one post WITH an outbound link) is ADMITTED;
  3. boundary simulation: the merge filter applied to a 24h carryover containing the four
     posts purges every one, so the fixture IDs cannot appear in x_feed items, pairs, more,
     nearest, latest, admit, or the client ticker pool (which reads the same gated file).

Fail-closed intent: a genuine post wrongly rejected is a blank, never a wrong render.
Run: python3 scripts/test_commercial_publishability.py   (exit 1 + FAILED line on any miss)
"""
import json, re, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import x_feed, news_social

# verbatim sentinel captures (served x_feed.json, 2026-09-30 ~01:00-01:03Z)
TOUTS = [
    {'id': '2105101030337970587', 'author_username': 'demiral28', 'author_name': 'sedat',
     'url': 'https://x.com/demiral28/status/2105101030337970587',
     'text': 'NHL FREE PLAY @PLAYBOOK https://t.co/q9RZ0BqUAm'},
    {'id': '2105100734702166432', 'author_username': 'BoseLockz', 'author_name': 'Bose',
     'url': 'https://x.com/BoseLockz/status/2105100734702166432',
     'text': 'CASH THE  NHL POTD\U0001f3d2\n\nYALL KNOW HOW WE COMIN ALL YEAR\U0001f4b0\n\n1-0.\n\nJOIN UP MAN\U0001f525\n\nhttps://t.co/l7r1suHp6x\n\n#Prizepicks #GamblingX https://t.co/WEncqAVdYJ'},
    {'id': '2105100416664867308', 'author_username': 'FI7772804', 'author_name': 'YURII',
     'url': 'https://x.com/FI7772804/status/2105100416664867308',
     'text': 'Montreal takes the lead! 2\ufe0f\u20e3\u27961\ufe0f\u20e3 and the pressure is on. Great execution to turn the game around! \U0001f525\U0001f3d2\nMore MLB, NHL, and NBA analytics, tracking, and picks like this. Check the link in my bio! \U0001f4c8\n#MontrealCanadiens #GoHabsGo #NHL #Hockey #FreePicks'},
    {'id': '2105101068732612851', 'author_username': 'nickmarshalli', 'author_name': 'PLAYS X GODDESS',
     'url': 'https://x.com/nickmarshalli/status/2105101068732612851',
     'text': '\U0001f3d2 NHL Anytime Goalscorer Parlay: (+6311)\nBoosted Odds: +9467\n\n#GamblingTwitter\n\nhttps://t.co/OLMg80SJ6T\n\n#NBA | #PrizePicks | #PROPS | #POTD | #Picks | #MLB | #Parlay @Playbook\n#Sportsbetting #NFL\n#DraftKings #Fanduel https://t.co/0185ji7ZZD'},
]
# same classes, reworded - the gate bites the CLASS, not the four strings (his fixture bar)
TOUT_VARIANTS = [
    {'id': 'var1', 'text': 'nhl free play https://t.co/a1', 'author_name': 'fan', 'author_username': 'fan1'},
    {'id': 'var2', 'text': 'great read on the game - LINK IN THE BIO https://t.co/a2', 'author_name': 'fan', 'author_username': 'fan2'},
    {'id': 'var3', 'text': 'we cashed again. join up now https://t.co/a3 #gamblingtwitter', 'author_name': 'fan', 'author_username': 'fan3'},
    {'id': 'var4', 'text': 'POTD incoming \U0001f512 boosted parlay below https://t.co/a4', 'author_name': 'fan', 'author_username': 'fan4'},
    {'id': 'var5', 'text': 'leafs play of the day, tail free at https://t.co/a5', 'author_name': 'fan', 'author_username': 'fan5'},
]
# free betting-sheet class (sentinel 9/29 7:38, TianaLocks verbatim): sport + Free + concrete
# priced lines + acquisition links, no pick/play wording - rejected by the FREE+ODDS+link leg,
# NEVER by the CTA regex. Ordinary free-agent/free-throw reporting stays publishable (ok5-ok7).
SHEET_TOUTS = [
    {'id': '2105097171011862752', 'author_username': 'TianaLocks', 'author_name': 'Tiana Locks',
     'url': 'https://x.com/TianaLocks/status/2105097171011862752',
     'text': "Today's Early MLB Free\n\nPHI ATL Over 6.5 -117\nPhillies TTO 2.5 -113\nBraves TTO 3.5 -108\nPHI ATL Over 8.5 +212\nPHI ATL Over 10.5 +426\n\nhttps://t.co/AcqLink1 https://t.co/AcqLink2"}
]

# handle-only tout class (sentinel 7:24 ingestX defect): clean text and display name, but the
# HANDLE is operator branding - only reachable if ingestX retains author_username. Asserted
# against _banned/isPublishablePost (operator rule), NOT _commercial (not a CTA/destination case).
HANDLE_TOUTS = [
    {'id': 'hnd1', 'text': 'Rangers look great tonight, hockey is so back', 'author_name': 'Fan', 'author_username': 'draftkings'},
    {'id': 'hnd2', 'text': 'what a catch by Jefferson, Vikings steal it late', 'author_name': 'Fan', 'author_username': 'prizepicks'},
]

# innocuous sports commentary - must ADMIT (post 3 carries a bare link to prove the
# destination rule never blanket-bans links, post 4 says "free" in a non-tout sense)
INNOCUOUS = [
    {'id': 'ok1', 'text': 'Connor McDavid with the hat trick tonight, absolutely unreal #LetsGoOilers', 'author_name': 'Kyle', 'author_username': 'kyleyeg'},
    {'id': 'ok2', 'text': 'Bruins power play looks lost. Fire the coach into the sun. #NHLBruins', 'author_name': 'Dee', 'author_username': 'dee_bos'},
    {'id': 'ok3', 'text': 'Unreal touchdown catch by Jefferson, Vikings win it at the death https://t.co/zz99 #SKOL', 'author_name': 'Sam', 'author_username': 'sam_mn'},
    {'id': 'ok4', 'text': 'Yankees bullpen blew another save, season is cooked', 'author_name': 'Mel', 'author_username': 'mel_ny'},
    {'id': 'ok5', 'text': 'Max Scherzer is the top free agent this winter - Mets or Rangers? https://t.co/hotstove1', 'author_name': 'Kyle', 'author_username': 'kyle_mlb'},
    {'id': 'ok6', 'text': 'Giannis went 12 of 14 at the free throw line, huge bounce back for the Bucks', 'author_name': 'Dee', 'author_username': 'dee_mke'},
    {'id': 'ok7', 'text': 'NFL tickets were free for kids at the preseason game, great night https://t.co/fam1', 'author_name': 'Sam', 'author_username': 'sam_fam'},
]

_xc = getattr(x_feed, '_commercial', None)          # missing on unfixed sources -> red, not crash
_nc = getattr(news_social, '_commercial', None)
_xcta = getattr(x_feed, 'COMMERCIAL_CTA_RE', None)
_xtag = getattr(x_feed, 'COMMERCIAL_TAG_RE', None)

fails = []
def check(name, cond):
    print(('PASS ' if cond else 'FAILED ') + name)
    if not cond:
        fails.append(name)

# --- 1 + 2: python mirrors reject every tout, admit every innocuous post
for p in TOUTS + TOUT_VARIANTS:
    check(f'x_feed._commercial rejects {p["id"]}', bool(_xc and _xc(p)))
    check(f'x_feed._banned rejects {p["id"]}', x_feed._banned(p))
    check(f'news_social._commercial rejects {p["id"]}', bool(_nc and _nc(p)))
    check(f'news_social._banned rejects {p["id"]}', news_social._banned(p))
for p in INNOCUOUS:
    check(f'x_feed admits {p["id"]}', _xc is not None and not _xc(p) and not x_feed._banned(p) and x_feed._sports_post(p))
    check(f'news_social admits {p["id"]}', _nc is not None and not _nc(p) and not news_social._banned(p) and news_social._sports_post(p))

# --- client parity: extract RP_COMM_CTA / RP_COMM_TAG from index_v2.js, byte-compare, re-test
js = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'index_v2.js')).read()
m_cta = re.search(r'var RP_COMM_CTA=/((?:[^/\\]|\\.)+)/i;', js)
m_tag = re.search(r'var RP_COMM_TAG=/((?:[^/\\]|\\.)+)/i;', js)
m_free = re.search(r'var RP_COMM_FREE=/((?:[^/\\]|\\.)+)/i;', js)
m_odds = re.search(r'var RP_COMM_ODDS=/((?:[^/\\]|\\.)+)/g;', js)
check('client RP_COMM_CTA present', bool(m_cta))
check('client RP_COMM_TAG present', bool(m_tag))
check('client RP_COMM_FREE present', bool(m_free))
check('client RP_COMM_ODDS present', bool(m_odds))
if m_cta:
    check('client CTA byte-parity with x_feed', bool(_xcta) and m_cta.group(1) == _xcta.pattern)
    cta = re.compile(m_cta.group(1), re.I)
    for p in TOUTS + TOUT_VARIANTS:
        t = re.sub(r'#\s+', '#', ' '.join([p.get('text') or '', str(p.get('author_name') or ''), str(p.get('author_username') or ''), str(p.get('url') or '')]))
        check(f'client CTA rejects {p["id"]}', bool(cta.search(t)))
if m_tag:
    check('client TAG byte-parity with x_feed', bool(_xtag) and m_tag.group(1) == _xtag.pattern)
    _xfree = getattr(x_feed, 'COMMERCIAL_FREE_RE', None)
    _xodds = getattr(x_feed, 'COMMERCIAL_ODDS_RE', None)
    check('client FREE byte-parity with x_feed', bool(m_free and _xfree) and m_free.group(1) == _xfree.pattern)
    check('client ODDS byte-parity with x_feed', bool(m_odds and _xodds) and m_odds.group(1) == _xodds.pattern)
    if m_free and m_odds:
        free_re = re.compile(m_free.group(1), re.I)
        odds_re = re.compile(m_odds.group(1))
        tiana = SHEET_TOUTS[0]
        check('client sheet rule rejects Tiana', bool(free_re.search(tiana['text']))
              and len(odds_re.findall(tiana['text'])) >= 2 and 'https://' in tiana['text'])
        for cid in ('ok5', 'ok6', 'ok7'):
            cp = [p for p in INNOCUOUS if p['id'] == cid][0]
            hit = bool(free_re.search(cp['text'])) and len(odds_re.findall(cp['text'])) >= 2 and 'https://' in cp['text']
            check(f'client sheet rule admits {cid}', not hit)
    tag = re.compile(m_tag.group(1), re.I)
    nick = TOUTS[3]
    check('client destination rule rejects nickmarshalli',
          bool(tag.search(nick['text'])) and bool(re.search(r'https?://', nick['text'])))
for p in INNOCUOUS:
    t = re.sub(r'#\s+', '#', ' '.join([p.get('text') or '', str(p.get('author_name') or ''), str(p.get('author_username') or ''), str(p.get('url') or '')]))
    ok = not (m_cta and re.compile(m_cta.group(1), re.I).search(t))
    ok = ok and not (m_tag and re.compile(m_tag.group(1), re.I).search(t) and re.search(r'https?://', p['text']))
    check(f'client admits {p["id"]}', ok)

# --- 2a: sheet fixtures - _commercial (sheet leg) + _banned reject, both mirrors
for p in SHEET_TOUTS:
    check(f'x_feed._commercial rejects sheet {p["id"]}', bool(_xc and _xc(p)))
    check(f'x_feed._banned rejects sheet {p["id"]}', x_feed._banned(p))
    check(f'news_social._commercial rejects sheet {p["id"]}', bool(_nc and _nc(p)))
    check(f'news_social._banned rejects sheet {p["id"]}', news_social._banned(p))

# --- 2b: handle-only fixtures - python mirror rejects via the who-rule
for p in HANDLE_TOUTS:
    check(f'x_feed._banned rejects handle-tout {p["id"]}', x_feed._banned(p))
    check(f'news_social._banned rejects handle-tout {p["id"]}', news_social._banned(p))

# --- 2c: client-surface harness - run the REAL ingestX + zeroPairSocial from index_v2.js under
# node vm and prove the fixture ids cannot reach the independent latest-12, modal, or ticker.
import subprocess, tempfile
HARN = r'''
const fs=require('fs'),vm=require('vm');
const src=fs.readFileSync(process.argv[2],'utf8');
const varLines=src.split('\n').filter(l=>/^var (RP_AD_KW|RP_TOUT_KW|RP_OPERATOR|RP_NONSPORT_KILL|RP_SPORT_ACRO|RP_SPORT_STRONG|RP_SPORT_TEAMS|RP_SPORT_WEAK|RP_COMM_CTA|RP_COMM_TAG|RP_COMM_FREE|RP_COMM_ODDS)=/.test(l)&&/;\s*$/.test(l));
if(varLines.length!==12){console.log('FAIL rp-vars '+varLines.length);process.exit(1);}
function extractFn(name){const s=src.indexOf('function '+name+'(');if(s<0){console.log('FAIL missing '+name);process.exit(1);}let d=0,i=src.indexOf('{',s);for(;i<src.length;i++){if(src[i]==='{')d++;else if(src[i]==='}'){d--;if(!d)return src.slice(s,i+1);}}console.log('FAIL unterminated '+name);process.exit(1);}
const ctx={console,Date,JSON};
vm.createContext(ctx);
vm.runInContext(varLines.join('\n')+'\n'+extractFn('isPublishablePost')+'\n'+extractFn('isSportsPost')+'\n'+extractFn('zeroPairSocial')+'\n'+extractFn('ingestX')+'\nthis.SOC_MATCH_OK=false;this.socMapRetry=function(){};',ctx);
const doc=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
vm.runInContext('ingestX('+JSON.stringify(doc)+')',ctx);
const XNEWS=vm.runInContext('XNEWS',ctx);
const zp=vm.runInContext('zeroPairSocial(12)',ctx);
console.log(JSON.stringify({xnews:XNEWS.map(p=>({id:p.id,handle:p.handle||''})),zp:zp.map(e=>e.post.id)}));
'''
pool = {'generated_at': '2026-09-30T02:00:00Z', 'items': []}
for p in TOUTS:
    pool['items'].append({'id': p['id'], 'created_at': '2026-09-30T01:00:00Z', 'text': p['text'],
                          'author_name': p.get('author_name',''), 'author_username': p.get('author_username',''), 'url': p.get('url','')})
for p in SHEET_TOUTS:
    pool['items'].append({'id': p['id'], 'created_at': '2026-09-30T01:00:30Z', 'text': p['text'],
                          'author_name': p.get('author_name',''), 'author_username': p.get('author_username',''), 'url': p.get('url','')})
for p in HANDLE_TOUTS:
    pool['items'].append({'id': p['id'], 'created_at': '2026-09-30T01:01:00Z', 'text': p['text'],
                          'author_name': p['author_name'], 'author_username': p['author_username'],
                          'url': 'https://x.com/%s/status/%s' % (p['author_username'], p['id'])})
for i in range(16):  # enough innocuous volume that the latest-12 stays full after the purge
    oid = str(9900000000000000000 + i)  # ingestX admits numeric status ids only
    pool['items'].append({'id': oid, 'created_at': '2026-09-30T01:02:%02dZ' % i,
                          'text': 'Yankees bullpen blew another save, season is cooked %d' % i,
                          'author_name': 'Fan%d' % i, 'author_username': 'fan%d' % i,
                          'url': 'https://x.com/fan%d/status/%s' % (i, oid)})
js_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'index_v2.js')
with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as hf:
    hf.write(HARN); harn_path = hf.name
with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as pf:
    json.dump(pool, pf); pool_path = pf.name
try:
    r = subprocess.run(['node', harn_path, js_path, pool_path], capture_output=True, text=True, timeout=60)
    check('client harness runs', r.returncode == 0)
    if r.returncode == 0:
        res = json.loads(r.stdout.strip().splitlines()[-1])
        xids = {str(p['id']) for p in res['xnews']}
        tout_all = {str(p['id']) for p in TOUTS} | {str(p['id']) for p in HANDLE_TOUTS} | {str(p['id']) for p in SHEET_TOUTS}
        check('ingestX drops every tout + handle-tout id', not (xids & tout_all))
        check('ingestX retains the handle field', all('handle' in p for p in res['xnews']))
        check('latest-12 stays full from innocuous posts', len(res['zp']) == 12)
        check('zeroPairSocial(12) carries no tout id', not ({str(i) for i in res['zp']} & tout_all))
        # modal + ticker render only from XNEWS with isPublishablePost re-checks; XNEWS is clean,
        # and the static asserts below prove both surfaces still re-check the predicate.
finally:
    os.unlink(harn_path); os.unlink(pool_path)

# --- 2d: static surface checks - independent fallback, modal and ticker all re-check the predicate
check('zeroPairSocial re-checks isPublishablePost', 'zeroPairSocial' in js and re.search(r'function zeroPairSocial\(n\)\{\s*var fp=\[\],seen=\{\};\s*for\(var i=0;i<XNEWS\.length&&fp\.length<n;i\+\+\)\{var p=XNEWS\[i\];if\(p&&isPublishablePost\(p\)&&isSportsPost\(p\)', js) is not None)
check('modal (socMore) re-checks isPublishablePost', 'var p=XNEWS[xi];if(!isPublishablePost(p))return;' in js)
check('paired-slide take() re-checks isPublishablePost', 'if(p&&!usedA[p.id]&&isPublishablePost(p))' in js)
check('ingestX retains author_username as handle', "handle:typeof p.author_username==='string'?p.author_username.slice(0,80):''" in js)

# --- 3: serialization-boundary simulation - gated carryover purges the fixtures from EVERY surface
pool = TOUTS + SHEET_TOUTS + INNOCUOUS  # as if all had entered yesterday's pool
gated = [pp for pp in pool if not x_feed._banned(pp)]  # the exact boundary filter expression
gated_ids = {str(p['id']) for p in gated}
tout_ids = {str(p['id']) for p in TOUTS} | {str(p['id']) for p in SHEET_TOUTS}
check('boundary purges every tout fixture id', not (gated_ids & tout_ids))
check('boundary keeps innocuous ids', {'ok1', 'ok2', 'ok3', 'ok4'} <= gated_ids)
# downstream surfaces are built ONLY from the gated pool (soc_match pairs/more/nearest/latest/
# admit + the client ticker reading x_feed.json) - assert no fixture id can appear in any of them
sim_map = {'pairs': {}, 'more': {}, 'nearest': {}, 'latest': {}, 'admit': []}
for i, p in enumerate(gated):
    nk = f'https://www.espn.com/story/{i}'
    sim_map['pairs'][nk] = {'post_id': p['id']}
    sim_map['more'][nk] = [{'post_id': p['id']}]
    sim_map['nearest'][nk] = {'post_id': p['id']}
    sim_map['latest'][nk] = {'post_id': p['id']}
    sim_map['admit'].append(p['id'])
surf_ids = {str(v['post_id']) for v in sim_map['pairs'].values()}
surf_ids |= {str(e['post_id']) for v in sim_map['more'].values() for e in v}
surf_ids |= {str(v['post_id']) for v in sim_map['nearest'].values()}
surf_ids |= {str(v['post_id']) for v in sim_map['latest'].values()}
surf_ids |= {str(x) for x in sim_map['admit']}
check('no fixture id in pairs/more/nearest/latest/admit', not (surf_ids & tout_ids))
ticker_pool = [p for p in gated]  # the ticker renders the same gated x_feed items
check('no fixture id in ticker pool', not ({str(p['id']) for p in ticker_pool} & tout_ids))

print()
if fails:
    print(f'{len(fails)} FAILED')
    sys.exit(1)
print('all commercial-publishability fixtures pass')
