#!/usr/bin/env python3
# Standing fixture (Sep 29 standing order, phonemsg-01M3PXTWRCN8EE6YQ8WS2H6Z66): the all-books
# line-shop class cannot regress silently. Run against any emitted card page:
#   python3 scripts/test_manifest_chips_class.py manifest.json index.html
# Asserts: (1) every game-market pick emits >=2 priced book chips (line shop is computable,
# "only one book priced" can never appear for a priced card); (2) FD sportsbook never renders
# (standing spec); (3) KAL star chip present on Kalshi-priced picks; (4) chips carry data-market
# (line-shop market guard) and data-book (client state gating via rpBookLive).
import json,re,sys
man=json.load(open(sys.argv[1])); h=open(sys.argv[2]).read()
cards=re.split(r'<div class="pick" ',h)[1:]
picks=[p for p in man.get('picks',[]) if p.get('market_class')!='prop' and p.get('books')]
fails=[]
if len(cards)<len(man.get('picks',[])): fails.append(f'emitted cards {len(cards)} < manifest picks {len(man.get("picks",[]))}')
for p in picks:
    nm=p['name']
    card=next((c for c in cards if nm.split(' over ')[0] in c or nm in c),None)
    if card is None: fails.append(f'{nm}: card not found in emitted page'); continue
    seg=card[:6000]
    books=re.findall(r'data-book="([A-Z]+)"',seg)
    priced=[]
    for m in re.finditer(r'data-book="([A-Z]+)"',seg):
        w=seg[m.start():m.start()+400]
        if re.search(r'data-cents="\d+"',w) or re.search(r'>\s*(?:★\s*)?(?:<img[^>]*>)*\s*[A-Z]{2,4} [+-]\d+',w): priced.append(m.group(1))
    if len(priced)<2: fails.append(f'{nm}: only {len(priced)} priced chips {priced} - line-shop class regressed')
    if 'FD' in books: fails.append(f'{nm}: FD sportsbook chip rendered (standing FD-removal spec violated)')
    if p.get('best_book')=='Kalshi' and 'KAL' not in books: fails.append(f'{nm}: KAL chip missing on Kalshi-priced pick')
    dm=len(re.findall(r'data-book="[A-Z]+"[^>]*data-market=',seg))+len(re.findall(r'data-market="[a-z]+"[^>]*data-book=',seg))
    if priced and dm==0: fails.append(f'{nm}: chips missing data-market (market guard) ')
if fails:
    print('CHIPS CLASS FIXTURE: FAIL'); [print(' -',f) for f in fails]; sys.exit(1)
print(f'CHIPS CLASS FIXTURE: PASS ({len(picks)} game-market picks, all >=2 priced chips, no FD, KAL star intact)')
