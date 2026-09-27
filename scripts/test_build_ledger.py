import json, os, subprocess, sys, tempfile, shutil

tmp=tempfile.mkdtemp()
prod_ledger=f'{tmp}/picks.jsonl'
MAN=f'{tmp}/manifest.json'  # stable production manifest path for this test
CAND=[{'num':1,'name':'Test ML','side':'home','away':'AAA','home':'BBB','commence':'2026-09-28T00:00Z',
 'eid':999001,'espn_league':'MLB','units':5,'date':'2026-09-28',
 'kalshi':{'cents':57,'team':'BBB','ticker':'KXT-BBB'},'model':60.7,'gross_c':3.7,'net_c':2.0,'market_class':'ml'}]
cf=f'{tmp}/cands.json'
S='/home/sandbox/rix_tmp/scripts/build_manifest.py'
env=dict(os.environ); env['PYTHONPATH']='/home/sandbox/rix_tmp'; env['RIX_PICKS_LEDGER']=prod_ledger
META={'record':'13-6','units_pl':'+3.89u','units_ledger':'test ledger','yesterday':'3-0 sweep','status_note':'test note','parlay':None}
mp=f'{tmp}/meta.json'; json.dump(META,open(mp,'w'))
fails=[]
def run(args,expect_ok=True):
    r=subprocess.run(['python3',S]+args+['--meta',mp],capture_output=True,text=True,env=env)
    if expect_ok and r.returncode!=0: fails.append(f'run failed: {args}: {r.stderr[-300:]}')
    if not expect_ok and r.returncode==0: fails.append(f'run should have failed: {args}')
    return r
def rows(p=prod_ledger): return [json.loads(l) for l in open(p)] if os.path.exists(p) else []
def write_cands(c): json.dump(c,open(cf,'w'))

# T1 preview isolation
write_cands(CAND); r=run([cf,f'{tmp}/prev.json','--preview'])
if rows(): fails.append('T1: production ledger got a preview row')
pr=rows(f'{tmp}/picks.preview.jsonl')
if not (len(pr)==1 and pr[0].get('preview')==True): fails.append(f'T1: preview ledger wrong {pr}')
print('T1 OK')
# T2 production canonical + readback
r=run([cf,MAN])
pr=rows()
if not (len(pr)==1 and pr[0]['preview']==False and pr[0]['entry_c']==57 and pr[0]['card_american']==-133): fails.append(f'T2 wrong {pr}')
if 'readback verified' not in r.stdout: fails.append('T2 no readback')
print('T2 OK')
# T3 idempotent
run([cf,MAN])
if len(rows())!=1: fails.append('T3 appended')
print('T3 OK')
# T4 staged promotion (legacy preview marker + identical candidate)
rows0=rows(); rows0[0]['preview']=True
open(prod_ledger,'w').write('\n'.join(json.dumps(x) for x in rows0)+'\n')
r=run([cf,MAN])
pr=rows()
if not (len(pr)==1 and pr[0]['preview']==False): fails.append(f'T4 marker survived {pr}')
if 'STAGED PROMOTION' not in r.stdout: fails.append('T4 not logged')
print('T4 OK')
# T5 real fork refuses (manifest HAS the key, different price)
c2=[dict(CAND[0])]; c2[0]['kalshi']=dict(CAND[0]['kalshi']); c2[0]['kalshi']['cents']=60
write_cands(c2); r=run([cf,MAN],expect_ok=False)
if 'refusing to fork' not in r.stderr+r.stdout: fails.append('T5 no fork refusal')
if len(rows())!=1: fails.append('T5 mutated')
print('T5 OK')
# T6 bool rejection
c3=[dict(CAND[0])]; c3[0]['kalshi']=dict(CAND[0]['kalshi']); c3[0]['kalshi']['cents']=True
write_cands(c3); run([cf,MAN],expect_ok=False)
if len(rows())!=1: fails.append('T6 mutated')
print('T6 OK')
# T7 batch duplicate rejection (fresh ledger)
os.remove(prod_ledger)
dup=[dict(CAND[0]),dict(CAND[0])]
write_cands(dup); r=run([cf,MAN],expect_ok=False)
if 'duplicate candidates' not in r.stderr+r.stdout: fails.append('T7 no dupe refusal')
if rows(): fails.append('T7 wrote rows')
print('T7 OK')
# T8 orphan rollback: interrupted publish (row, no manifest) + CHANGED price -> recover
write_cands(CAND); run([cf,MAN])          # publish 57c
os.remove(MAN)                             # simulate manifest never published / lost
c4=[dict(CAND[0])]; c4[0]['kalshi']=dict(CAND[0]['kalshi']); c4[0]['kalshi']['cents']=61
write_cands(c4); r=run([cf,MAN])
pr=rows()
if not (len(pr)==1 and pr[0]['entry_c']==61): fails.append(f'T8 wrong {pr}')
if 'ORPHAN ROLLBACK' not in r.stdout: fails.append('T8 rollback not logged')
print('T8 OK')
# T9 interrupted publish + IDENTICAL candidates finishes (no new row, manifest published)
os.remove(prod_ledger); os.remove(MAN)
# hand-write a canonical row as the crashed publish left it
row={'kind':'pick','event_id':'999001','market_class':'ml','side':'home','name':'Test ML','units':5,
 'entry_c':57,'card_american':-133,'card_source':'Kalshi ask at lock','card_ts':'2026-09-26T22:30:00-07:00',
 'kalshi_ticker':'KXT-BBB','commence':'2026-09-28T00:00Z','preview':False}
open(prod_ledger,'w').write(json.dumps(row)+'\n')
write_cands(CAND); r=run([cf,MAN])
if len(rows())!=1: fails.append('T9 appended a duplicate')
if not os.path.exists(MAN): fails.append('T9 manifest not published')
print('T9 OK')
# T10 preview refuses production manifest path
r=run([cf,'/home/sandbox/rix_tmp/manifest.json','--preview'],expect_ok=False)
if 'refuses production manifest path' not in r.stderr+r.stdout: fails.append('T10 no path refusal')
print('T10 OK')
# T11 units change on published key -> refuse (swamp round 7 repro)
c5=[dict(CAND[0])]; c5[0]['units']=100
write_cands(c5); r=run([cf,MAN],expect_ok=False)
if 'refusing to fork' not in r.stderr+r.stdout: fails.append('T11 no fork refusal on units change')
if rows()[0]['units']!=5: fails.append('T11 ledger re-sized')
print('T11 OK')
# T12 corrupt manifest -> fail closed BEFORE any ledger rewrite
open(MAN,'w').write('{corrupt json')
r=run([cf,MAN],expect_ok=False)
if 'unreadable' not in r.stderr+r.stdout: fails.append('T12 no unreadable refusal')
if len(rows())!=1: fails.append('T12 ledger mutated')
print('T12 OK')
# T13 end-to-end: builder manifest -> build_gh_page.py (the real publish path) must not KeyError
os.remove(MAN)  # T12's corrupt manifest; identical rerun exercises the T9 resume path
write_cands(CAND); run([cf,MAN])
html_out=f'{tmp}/index.html'
r=subprocess.run(['python3','/home/sandbox/rix_tmp/scripts/build_gh_page.py',MAN,html_out],
                 capture_output=True,text=True,env=dict(os.environ))
# hermetic level: format contract must carry it to the live-market gate (fake ticker KXT dies THERE,
# by design); a contract break shows as KeyError/JSONDecodeError before that point.
st=r.stderr+r.stdout
if 'KeyError' in st or 'JSONDecodeError' in st: fails.append(f'T13 format contract broken: {st[-300:]}')
if 'Kalshi market unresolved' not in st and r.returncode!=0: fails.append(f'T13 unexpected failure: {st[-300:]}')
print('T13 OK' if not any(x.startswith('T13') for x in fails) else 'T13 FAILED')
# T14 market_class gate: spread candidate refused loud, nothing written
c6=[dict(CAND[0])]; c6[0]['market_class']='spread'
write_cands(c6); r=run([cf,MAN],expect_ok=False)
if "only explicit 'ml'" not in r.stderr+r.stdout: fails.append('T14 no ml-only refusal')
if len(rows())!=1: fails.append('T14 ledger mutated')
c7=[dict(CAND[0])]; c7[0].pop('market_class',None)
write_cands(c7); r=run([cf,MAN],expect_ok=False)
if "only explicit 'ml'" not in r.stderr+r.stdout: fails.append('T14b missing market_class not refused')
print('T14 OK')
print('FAILS:',fails if fails else 'none')
shutil.rmtree(tmp)
sys.exit(1 if fails else 0)
