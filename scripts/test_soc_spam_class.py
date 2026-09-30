#!/usr/bin/env python3
"""Crypto-spam class (Sep 29, lane 3): free-signals / VIP-trade / take-profit X spam
(@Cry_Fortress class, ~12 posts rendering in the unpaired social feed) must be denied at
EVERY server intake gate (x_feed._banned, news_social._banned, soc_match generation gate)
and by the crypto-handle author class - while legit sports posts pass. Query-term
extraction (news_social.entities/phrase) must drop dictionary-common words spam accounts
keyword-stuff (Thursday/Silver/Squarely class) WITHOUT banning those words in posts.

Run: python3 scripts/test_soc_spam_class.py
"""
import sys, os, unicodedata, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import x_feed, news_social, soc_match

fails = 0
def check(label, cond):
    global fails
    print(('OK   ' if cond else 'FAIL ') + label)
    if not cond: fails += 1

def soc_gate(p):
    t = unicodedata.normalize('NFKC', ' '.join([p.get('text') or '', str(p.get('author_name') or ''), str(p.get('author_username') or ''), str(p.get('url') or '')]))
    if soc_match.RP_AD.search(t) or soc_match.RP_TOUT.search(t) or soc_match.RP_PROMO_CAPS.search(t):
        return True
    return soc_match.operator_author(p.get('author_name'), p.get('author_username'))

SPAM = [
    ('free-signals VIP-trade', {'text': 'FREE SIGNALS!! VIP-1 TRADE: LONG $BTC entry 64500, TP1 66000, TP2 67500. Thursday Silver Squarely NFL NBA MLB', 'author_name': 'Cry Fortress', 'author_username': 'Cry_Fortress', 'url': 'https://x.com/Cry_Fortress/status/123'}),
    ('clean text, crypto handle', {'text': 'Big night of baseball ahead, who you got?', 'author_name': 'Cry Fortress', 'author_username': 'Cry_Fortress', 'url': 'https://x.com/Cry_Fortress/status/124'}),
    ('take-profit phrasing', {'text': 'TP1 smashed. TP2 loading. Take-profit secured, stop-loss moved to entry. VIP-2 TRADE drops soon', 'author_name': 'Joe Sports', 'author_username': 'joe_sports', 'url': 'https://x.com/joe_sports/status/125'}),
    ('exchange/airdrop/100x', {'text': 'Airdrop live on Binance and Bybit, 100x gem, do not miss this one', 'author_name': 'Sports Fan', 'author_username': 'sportsfan99', 'url': 'https://x.com/sportsfan99/status/126'}),
    ('caps FREE SIGNALS', {'text': 'FREE SIGNALS for tonight\'s slate, tail at your own risk', 'author_name': 'Pick Pro', 'author_username': 'pickpro', 'url': 'https://x.com/pickpro/status/127'}),
]
LEGIT = [
    ('Alvarez HR post', {'text': 'Yordan Alvarez goes deep AGAIN. Third homer in two games for the Astros slugger.', 'author_name': 'Astros Talk', 'author_username': 'astrostalk', 'url': 'https://x.com/astrostalk/status/200'}),
    ('Contreras lineup post', {'text': 'Willson Contreras batting third and playing first for the Red Sox tonight in the Bronx', 'author_name': 'Sox Beat', 'author_username': 'soxbeat', 'url': 'https://x.com/soxbeat/status/201'}),
    ('Silver Slugger post', {'text': 'Silver Slugger watch: Alvarez has to be in the conversation after this stretch', 'author_name': 'ESPN MLB', 'author_username': 'espnmlb', 'url': 'https://x.com/espnmlb/status/202'}),
    ('mixed signals post', {'text': 'Lakers showing mixed signals in the halfcourt, but the defense travels', 'author_name': 'Lake Show', 'author_username': 'lakeshow', 'url': 'https://x.com/lakeshow/status/203'}),
    ('Thursday Night Football post', {'text': 'Thursday Night Football should be a good one between two desperate teams', 'author_name': 'NFL Update', 'author_username': 'nflupdate', 'url': 'https://x.com/nflupdate/status/204'}),
]

for name, p in SPAM:
    check(f'x_feed._banned rejects {name}', x_feed._banned(p))
    check(f'news_social._banned rejects {name}', news_social._banned(p))
    check(f'soc_match gate rejects {name}', soc_gate(p))
for name, p in LEGIT:
    check(f'x_feed._banned passes {name}', not x_feed._banned(p))
    check(f'news_social._banned passes {name}', not news_social._banned(p))
    check(f'soc_match gate passes {name}', not soc_gate(p))

ents = news_social.entities('Thursday night, Silver speaks squarely about Willson Contreras')
check('entities drops Thursday/Silver/Squarely', not any(e.lower() in ('thursday', 'silver', 'squarely') for e in ents))
check('entities keeps Willson Contreras', 'Willson Contreras' in ents)
ph = news_social.phrase('Silver speaks squarely about Thursday night football')
check('phrase drops dictionary-common words', all(w not in ph.lower().split() for w in ('silver', 'squarely', 'thursday', 'night')))

print('PASS' if fails == 0 else f'{fails} FAILURES')
sys.exit(1 if fails else 0)
