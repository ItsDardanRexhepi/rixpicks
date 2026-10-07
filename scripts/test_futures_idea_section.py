#!/usr/bin/env python3
"""Futures idea section fixture (LS-23, Oct 1).

The Wooder tab listed the season-long "NFL Futures: 1000+ Receiving Yards (10 legs)" idea under
the "Same Game Parlays" heading. Items marked futures:true now render under their own "Futures
Ideas" heading; same-game items stay where they were, and the futures card stays hidden when no
such item exists. Runs the real combos module script from each builder twin in a stub page.
Run: python3 scripts/test_futures_idea_section.py [builder.py ...]
"""
import ast, json, os, re, subprocess, sys, warnings
warnings.simplefilter('ignore', SyntaxWarning)  # the builder source carries pre-existing invalid escapes inside JS templates

SD = os.path.dirname(os.path.abspath(__file__))
BUILDERS = [os.path.abspath(a) for a in sys.argv[1:]] or [os.path.join(SD, 'build_gh_page_v2.py'), os.path.join(SD, '_build_nocanon_v2.py')]
failures = 0
def check(name, ok):
    global failures
    print(('OK   ' if ok else 'FAIL ') + name)
    if not ok: failures += 1

def module_text(path):
    for node in ast.walk(ast.parse(open(path).read())):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and 'id="rpCmb"' in node.value and 'rpCmbGo' in node.value:
            return node.value
    return ''

SGP = {'id': 'idea-mlb-ks3-20990930', 'type': 'idea', 'date': '2099-09-30', 'title': 'Strikeouts Parlay (3 legs)', 'matchup': 'PHI@ATL',
       'legs': [{'player': 'Cristopher Sanchez', 'market': '7+ strikeouts', 'kalshi': '+138'}]}
FUT = {'id': 'idea-nfl-rec1000-20260930', 'type': 'idea', 'futures': True, 'date': '2026-09-30', 'time': 'Season-long',
       'title': 'NFL Futures: 1000+ Receiving Yards (10 legs)', 'matchup': 'NFL regular season',
       'legs': [{'player': 'Puka Nacua', 'market': '1000+ receiving yards', 'yds': 1000}]}

STUB = r"""
function el(id){return {id:id,innerHTML:'',hidden:(id==='rpCmbFutWrap'),style:{display:''},querySelector:function(){return null;},querySelectorAll:function(){return [];}};}
var E={rpCmb:el('rpCmb'),rpCmbWrap:el('rpCmbWrap'),rpCmbFutWrap:el('rpCmbFutWrap')};
E.rpCmb.parentNode=E.rpCmbWrap;
var HAS_FUT_BOX=%s;
if(HAS_FUT_BOX){E.rpCmbFut=el('rpCmbFut');E.rpCmbFut.parentNode=E.rpCmbFutWrap;}
var document={readyState:'complete',getElementById:function(id){return E[id]||null;},querySelectorAll:function(){return [];},createElement:function(){return {};},head:{appendChild:function(){}}};
var window={addEventListener:function(){}};window.rpComboFresh=function(){return true;};var rpComboFresh=window.rpComboFresh;
var timers=[];function setTimeout(f){timers.push(f);return 1;}function setInterval(){return 1;}
var DATA=%s;
function fetch(u){return Promise.resolve({ok:true,json:function(){return Promise.resolve(u.indexOf('wooder_combos')>=0?{combos:DATA}:null);}});}
%s
timers.forEach(function(f){f();});
setImmediate(function(){setImmediate(function(){setImmediate(function(){
 console.log(JSON.stringify({sgp:E.rpCmb.innerHTML,sgpShown:E.rpCmbWrap.style.display!=='none',fut:E.rpCmbFut?E.rpCmbFut.innerHTML:'',futShown:!E.rpCmbFutWrap.hidden}));
});});});
"""
def run(script, combos, has_fut_box):
    r = subprocess.run(['node', '-e', STUB % ('true' if has_fut_box else 'false', json.dumps(combos), script)], capture_output=True, text=True)
    try: return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception: return {'error': r.stderr[:300]}

for B in BUILDERS:
    tag = os.path.basename(B)
    mod = module_text(B)
    check(f'{tag}: combos module found', bool(mod))
    if not mod: continue
    has_fut_box = 'id="rpCmbFut"' in mod
    check(f'{tag}: page carries a separate Futures Ideas card, hidden by default',
          bool(re.search(r'<div id="rpCmbFutWrap"(?=[^>]*\shidden[\s>])[^>]*><div class="rpwhead">Futures Ideas</div><div id="rpCmbFut"[^>]*></div></div>', mod)))
    script = re.search(r'<script>([\s\S]*)</script>', mod[mod.find('<script>(function(){var box=document.getElementById("rpCmb")'):]).group(1)
    o = run(script, [SGP, FUT], has_fut_box)
    check(f'{tag}: season-long futures idea is not listed under Same Game Parlays', 'NFL Futures' not in o.get('sgp', 'NFL Futures'))
    check(f'{tag}: same-game idea stays under Same Game Parlays', 'Strikeouts Parlay' in o.get('sgp', '') and o.get('sgpShown') is True)
    check(f'{tag}: futures idea renders under Futures Ideas and that card shows', 'NFL Futures' in o.get('fut', '') and o.get('futShown') is True)
    o = run(script, [FUT], has_fut_box)
    check(f'{tag}: futures-only day hides the empty Same Game Parlays card', o.get('sgpShown') is False and 'NFL Futures' in o.get('fut', ''))
    o = run(script, [SGP], has_fut_box)
    check(f'{tag}: no futures item keeps the Futures Ideas card hidden', o.get('futShown') is False and 'Strikeouts Parlay' in o.get('sgp', ''))

print('FAILURES: ' + str(failures) if failures else 'ALL CHECKS PASS')
sys.exit(1 if failures else 0)
