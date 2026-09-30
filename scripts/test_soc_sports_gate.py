#!/usr/bin/env python3
"""Feed guard 3 zero-pair class (Sep 29): server mirror of the sports-context intake gate
(x_feed._banned / news_social._banned admit genuine sports posts only - the poisoned-pool
fix) + title-case entity-gate silence (ESPN video-clip false principals must not kill
on-story candidates pre-probe). Run: python3 scripts/test_soc_sports_gate.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import x_feed, news_social, soc_match

fails = 0
def check(label, cond):
    global fails
    print(('OK   ' if cond else 'FAIL ') + label)
    if not cond: fails += 1

S = lambda id_, text, author='Fan', user='fanacct': {'id': id_, 'text': text, 'author_name': author, 'author_username': user, 'url': 'https://x.com/%s/status/%s' % (user, id_), 'created_at': '2026-09-29T23:00:00Z'}

SPORTS = [
    ('strong term (homer)', S('1', 'Yordan Alvarez goes deep AGAIN. Third homer in two games for the Astros slugger.', 'Astros Talk', 'astrostalk')),
    ('team name (Red Sox)', S('2', 'Willson Contreras batting third and playing first for the Red Sox tonight in the Bronx', 'Sox Beat', 'soxbeat')),
    ('strong (football)', S('3', 'Thursday Night Football should be a good one between two desperate teams', 'NFL Update', 'nflupdate')),
    ('weak x2 (OT comeback)', S('4', 'UCLA survives in OT, what a comeback win', 'College Fan', 'cfbfan')),
    ('team (Yankees)', S('5', 'Judge sends one into the second deck, 3-0 Yankees', 'NYY Fan', 'nyyfan')),
    ('NHL opening post', S('6', 'The NHL season opens tonight. Every new sweater for 2026-27 ranked', 'Hockey Night', 'hnic')),
    ('acronym+weak (NHL win)', S('7', 'The First Goal of The NHL Season is a OT Winner and gives the Panthers a 1-0 Win', 'Puck Talk', 'pucktalk')),
    ('single acronym (NBA)', S('8', 'NBA is so back, opening night was a movie', 'Hoops', 'hoops')),
]
NONSPORT = [
    ('finance solicitation', S('11', 'NASDAQ ripping today, passive income stock tips inside')),
    ('politics', S('12', 'The president addressed congress on the election results tonight')),
    ('fashion promo', S('13', 'New fashion drop just hit the runway, shop the look now')),
    ('sexual solicitation', S('14', '18+ spicy content on my only fans page tonight')),
    ('lost luggage', S('15', 'Airline lost my luggage again, worst travel day ever')),
    ('art post', S('16', 'What? At least I feel beautiful. I don\'t need your approval.. (Art by @M1ddi3Kira)')),
    ('dating thread', S('17', 'Dating Threads Dear Future Boyfriend, I don\'t know where you are right now')),
    ('quiet luxury spam', S('18', 'Quiet luxury isn\'t just a $3,000 handbag. It\'s knowing what you want')),
    ('bare-acronym stuffing', S('19', 'Thursday Silver Squarely NFL NBA MLB, big day')),
    ('random life post', S('20', 'Just got my coffee and the line was so long')),
]

for name, p in SPORTS:
    check(f'x_feed._banned passes {name}', not x_feed._banned(p))
    check(f'news_social._banned passes {name}', not news_social._banned(p))
for name, p in NONSPORT:
    check(f'x_feed._banned drops {name}', x_feed._banned(p))
    check(f'news_social._banned drops {name}', news_social._banned(p))

# residual-leak fixtures (9/29): hashtag/author/URL hits never establish sports relevance;
# a bare team word needs a second game signal. Emmagrace51 post text verbatim from the served pool.
LEAK_DROP = [
    ('hashtag-stuffed relationship post (Emmagrace51 2105093648232882322)',
     S('2105093648232882322', 'Why You Feel Attached to Someone After Only a Few Dates\nRead More Here : https://t.co/fz24tAouD5\n\n#JackSmith #AustinRiley #RavenJohnson #SuperIntelligence #Schmitt #Astros #OlandriaxPFWSS27 #Duran #OlandriaxRevolveMag #DWCS #Braves #WhiteSox #Caitlin #Espada #Phillies', 'Emma Grace', 'Emmagrace51')),
    ('tech giants (Giants regex false hit)', S('l2', 'Apple, Microsoft and other tech giants report earnings this week', 'Market Wire', 'marketwire')),
    ('fossil-fuel giants (Giants regex false hit)', S('l3', 'Fossil fuel giants face new emissions rules this year', 'Climate Desk', 'climatedesk')),
    ('team-hashtag stuffing on non-sports body', S('l4', 'New skincare routine changed my life #Yankees #Lakers #Chiefs', 'Glow Up', 'glowup')),
    ('sports only in author handle', S('l5', 'My skincare morning routine, link below', 'Astros Talk', 'astrostalk')),
]
LEAK_KEEP = [
    ('body team + score (Judge)', S('g1', 'Judge sends one into the second deck, 3-0 Yankees', 'NYY Fan', 'nyyfan')),
    ('body team + weak (Astros)', S('g2', 'Astros win it late, what a comeback! #Astros #LevelUp', 'Stros Fan', 'strosfan')),
    ('body matchup (two teams)', S('g3', 'Yankees vs Red Sox tonight, who you got?', 'Rivalry', 'rivalry')),
]
for name, p in LEAK_DROP:
    check(f'leak fix drops {name}', not x_feed._sports_post(p))
    check(f'leak fix drops {name} (news_social)', not news_social._sports_post(p))
for name, p in LEAK_KEEP:
    check(f'leak fix keeps {name}', x_feed._sports_post(p))
    check(f'leak fix keeps {name} (news_social)', news_social._sports_post(p))

# title-case detection (entity-gate silence class)
check('title-case: NHL video clip headline', soc_match.title_case_headline('Dreams Come True: Puck Drops On New NHL Season') is True)
check('title-case: sweater ranking clip', soc_match.title_case_headline('Every New Sweater For 2026-27 Ranked From Worst To First') is True)
check('sentence-case: Kessler Lakers', soc_match.title_case_headline("Kessler talks up Lakers' title hopes behind 'nasty' defense") is False)
check('sentence-case: Cowboys signing', soc_match.title_case_headline('Cowboys signing safety Juanyeh Thomas') is False)
check('sentence-case: wild-card live', soc_match.title_case_headline('2026 MLB wild-card series Day 1: Live updates, lineups, analysis') is False)
check('sentence-case: Ramsey wrist', soc_match.title_case_headline('Jalen Ramsey says he has a broken wrist') is False)

# the silencing is meaningful: the poisoned headline DOES extract false principals without it
tc = 'Dreams Come True: Puck Drops On New NHL Season'
check('title-case headline poisons title_entities (pre-fix condition)', len(soc_match.title_entities(tc)) > 0)
check('sentence-case keeps extraction (gate stays armed)', len(soc_match.title_entities('Jalen Ramsey says he has a broken wrist')) > 0)

print('PASS' if fails == 0 else f'{fails} FAILURES')
sys.exit(1 if fails else 0)
