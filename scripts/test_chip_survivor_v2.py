"""Offline checks for post-retirement chip selection on both production builders."""
import ast
from pathlib import Path
import re

for filename in ('build_gh_page_v2.py', '_build_nocanon_v2.py'):
    source=Path(__file__).with_name(filename).read_text()
    tree=ast.parse(source)
    parts=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('_rh','c2ml_int','_finalize_chip_rows')]
    assert len(parts)==3
    ns={'re':re}
    exec(compile(ast.Module(body=parts,type_ignores=[]), filename, 'exec'),ns)
    render=ns['_finalize_chip_rows']
    rows=['<a class="chip best" data-mr="0">★ DK +150</a>',
          '<a class="chip" data-mr="1"><img>FD +120</a>',
          '<span class="chip" data-mr="2">KAL -110</span>',
          '<a class="chip" data-mr="3"><img>DK Predictions 42c</a>']
    records=[{'st':'ok','ml':150,'c':None}, {'st':'ok','ml':120,'c':None},
             {'st':'ok','ml':None,'c':52}, {'st':'ok','ml':None,'c':42}]
    out=render(rows[1:],records)
    assert out.count('★')==1 and 'class="chip best" data-mr="3">★ <img>' in out, out
    assert ns['LAST_PRICES']==[120,-108,138], ns['LAST_PRICES']
    out=render(rows[1:3],records)
    assert 'class="chip best" data-mr="1">★ <img>' in out and ns['LAST_PRICES']==[120,-108], out
    out=render(['<a class="chip best" data-mr="0">★ Unknown +999</a>',rows[2]],
               [{'st':'unknown','ml':999,'c':None}, {'st':'unknown','ml':None,'c':None}, records[2]])
    assert out.count('★')==1 and 'data-mr="2">★ ' in out and ns['LAST_PRICES']==[-108],out
    assert render(rows[:1],[{'st':'unknown','ml':150,'c':None}]).count('★')==0
    assert ns['LAST_PRICES']==[]
    print(filename, 'offline finalizer PASS')
