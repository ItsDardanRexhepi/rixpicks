#!/usr/bin/env python3
"""W0-07: fail-closed structural and unreadable-price holds, on both builders.
Extract only the gate's definitions, so tests cannot fetch prices or publish pages.
End-to-end refusal cases additionally run the builder in a disposable tree.
"""
import ast, copy, json, math, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
from fixtures.card_contract import stamped
ROOT=Path(__file__).resolve().parent.parent
failures=[]
def check(label,ok,detail=''):
    print(('PASS ' if ok else 'FAIL ')+label+((' '+str(detail)) if not ok else ''))
    if not ok: failures.append(label)
def gate(path):
    # Copy the contiguous, self-contained gate section, not unrelated renderer definitions.
    text=path.read_text(); start=text.index('_VEGAS_WORDS =');end=text.index('# --- owner suspension')
    ns={'re':re,'math':math}
    exec(compile(text[start:end],str(path),'exec'),ns)
    return ns
BASE={'num':1,'name':'Flyers +1.5','market_class':'spread','side':'away','line':-1.5,
      'sub':'fixture - model 66.0','odds':'-150','card_american':-150,'units':'5u',
      'espn_league':'hockey/nhl','league':'NHL','game':{'away':'Philadelphia Flyers','home':'Tampa Bay Lightning','eid':'FIX-1','commence':'2099-10-04T23:00Z'},
      'kalshi':{'ticker':'KXNHLSPREAD-26OCT05PHITB-TB2','side':'no','cents':60,'url':'https://kalshi.com/markets/kxnhlspread/kxnhlspread-26oct05phitb'}}
def holds(ns,p):return ns['_standing_rule_holds']({'picks':[p],'parlay':None})
def build(path,p):
    with tempfile.TemporaryDirectory(prefix='rp-fail-closed-') as d:
        d=Path(d);(d/'scripts').mkdir();(d/'slates').mkdir()
        for f in ('index_v2.js','index_v2.css','game_page_template.html','team_page_template.html','poly_us.py'):
            shutil.copy(ROOT/'scripts'/f,d/'scripts'/f)
        shutil.copy(path,d/'scripts/build_gh_page_v2.py')
        for f in ('feed_arbiter.js','feed_registry.json','config_leagues.json'):shutil.copy(ROOT/f,d/f)
        m={'date':'2099-10-04','date_label':'Sunday, Oct 4','updated':'Oct 4','record':'0-0','units_pl':'+0u','picks':[p],'parlay':None,'preview':False,'status_note':''}
        m=stamped(path,m)
        (d/'manifest.json').write_text(json.dumps(m));(d/'slates/odds_prefill.json').write_text('[]')
        before={str(f.relative_to(d)) for f in d.rglob('*') if f.is_file()}
        env=dict(os.environ,HTTP_PROXY='http://127.0.0.1:9',HTTPS_PROXY='http://127.0.0.1:9',http_proxy='http://127.0.0.1:9',https_proxy='http://127.0.0.1:9',NO_PROXY='')
        r=subprocess.run([sys.executable,'scripts/build_gh_page_v2.py','manifest.json','index.html'],cwd=d,env=env,capture_output=True,text=True,timeout=30)
        written={str(f.relative_to(d)) for f in d.rglob('*') if f.is_file()}-before
        written={f for f in written if '__pycache__' not in f}
        return r.returncode,r.stdout+r.stderr,written
for name in ('build_gh_page_v2.py','_build_nocanon_v2.py'):
    path=ROOT/'scripts'/name; ns=gate(path)
    check(name+': valid explicit NO market clears gate',not holds(ns,BASE),holds(ns,BASE))
    for kb in (None,{}, {'ticker':'KXFIX-1'}, {'ticker':'','side':'yes'}, {'ticker':'KXFIX-1','side':'maybe'}, {'ticker':'not a ticker','side':'yes'}):
        p=copy.deepcopy(BASE);p['kalshi']=kb
        check(name+': missing/invalid Kalshi ticker+side holds '+repr(kb),any(h[1]=='kalshi_market' for h in holds(ns,p)))
    p=copy.deepcopy(BASE);p['kalshi']=None
    rc,out,written=build(path,p)
    check(name+': Flyers kalshi:null exits 3, no writes',rc==3 and 'no Kalshi market' in out and not written,(rc,out[-400:],written))
    p=copy.deepcopy(BASE);p.update(sub='owner position',odds='-400',card_american=-400)
    rc,out,written=build(path,p)
    check(name+': owner position with no fair exits 3, no writes',rc==3 and 'fair unreadable' in out and not written,(rc,out[-400:],written))
    p=copy.deepcopy(BASE);p.update(odds='unreadable',card_american=None)
    check(name+': unreadable card price holds',any('card price unreadable' in h[2] for h in holds(ns,p)))
    p=copy.deepcopy(BASE);p['best_ask']={'venue':'poly','cost_c':60,'gross_c':6,'line':1.5,'compared':[]}
    check(name+': excluded POLY holds without compared quote',any(h[1]=='excluded_venue' for h in holds(ns,p)))
    p['best_ask']['compared']=[{'venue':'poly','price':60,'line':1.5}]
    check(name+': explicitly compared POLY clears excluded-venue hold',not any(h[1]=='excluded_venue' for h in holds(ns,p)))
    check(name+': Polymarket-best pick pays no Kalshi fee',ns['_is_kalshi_priced'](p) is False)
    check(name+': Polymarket-best pick with valid Kalshi block clears all bars',holds(ns,p)==[],holds(ns,p))
    rc,out,written=build(path,p)
    check(name+': explicit compared POLY reaches build without traceback', 'Traceback' not in out, (rc,out[-600:]))
    p=copy.deepcopy(BASE);p['sub']='owner position';p['best_ask']={'venue':'kalshi','cost_c':float('nan'),'gross_c':6}
    check(name+': nonfinite prices hold fail closed',any(h[1]=='unreadable_price' for h in holds(ns,p)))
    check(name+': empty card stays honest and clears gate',ns['_standing_rule_holds']({'picks':[]})==[])
check('builder twins byte-identical',(ROOT/'scripts/build_gh_page_v2.py').read_bytes()==(ROOT/'scripts/_build_nocanon_v2.py').read_bytes())
sys.exit(bool(failures))
