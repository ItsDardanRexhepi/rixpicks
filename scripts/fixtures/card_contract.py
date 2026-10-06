"""Synthetic prerequisites for isolated renderer fixtures, never production picks.
The display-only marker models a card already published; standing-rule holds still run.
Only tests explicitly opting in use these helpers. Original historical fixtures stay unchanged.
"""
import ast,copy,hashlib,json,re
from pathlib import Path

def content_hash(builder,manifest):
    tree=ast.parse(Path(builder).read_text())
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_pick_content_hash')
    ns={'json':json,'_hl':hashlib}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(builder),'exec'),ns)
    return ns['_pick_content_hash'](manifest)

def stamped(builder,manifest):
    m=copy.deepcopy(manifest)
    m['built_by']='build_manifest'
    # Preserve intentional bad-hash test inputs.
    m.setdefault('pick_content_hash',content_hash(builder,m))
    return m

def market(p):
    """Give a SYNTHETIC policy/renderer pick explicit market identity, not real data."""
    p=copy.deepcopy(p)
    mc=p.get('market_class') or p.get('market') or ('total' if p.get('side') in ('over','under') else 'ml')
    series={'spread':'KXFIXSPREAD','total':'KXFIXTOTAL','ml':'KXFIXGAME'}.get(mc,'KXFIXPROP')
    identity=hashlib.sha256(json.dumps(p.get('game') or {},sort_keys=True).encode()).hexdigest()[:10].upper()
    event=series+'-99OCT04'+identity
    tick=event+'-H'
    old=p.get('kalshi')
    if old is None:
        p['kalshi']={'ticker':tick,'side':'yes','url':'https://kalshi.com/markets/'+series.lower()+'/'+event.lower(),'cents':60}
    return p

def published_snapshot(root,builder,manifest):
    Path(root,'shipped_pick_hash.txt').write_text(content_hash(builder,manifest)+'\n')
