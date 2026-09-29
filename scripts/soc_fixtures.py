#!/usr/bin/env python3
"""Deterministic regression fixtures for the matching gate (owner 6:58 9/28, guard 2 incident).
Runs OFFLINE against title_entities/entity_conflict/post_persons, the equivocal parser,
and story_type_gate. x_feed.yml runs this BEFORE soc_match: a failure aborts the chain
before a bad map ships. The negatives are the exact served false pairs from the 9/28
guard incidents (guards 2+3 strips, 7:00-7:11 PM); each is killed at its own layer.
The props-article/generic-odds negative (2104681322878754826) passes these deterministic
gates BY DESIGN - it is covered by the v6 probe rule and cannot be asserted offline."""
import importlib.util, sys

spec = importlib.util.spec_from_file_location("soc_match", "scripts/soc_match.py")
sm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sm)

def gate(title, post, need=2):
    ents = sm.title_entities(title)
    if not ents:
        return ents, bool(sm.foreign_person_vs_title(title, post))
    return ents, sm.entity_conflict(ents, post, need) or bool(sm.post_persons(post, ents))

fails = []
NEG = [
    ('Steph Curry ready to go for Warriors, but injuries will be factor early', 'the blazers ain’t making the playoffs but hopefully ja individual performance revives his career and he gets traded to the warriors https://t.co/zYzT23aTmc'),
    ('Luka Doncic and Austin Reaves ready to take charge of new-look Lakers', "Kristaps Porzingis' health issue is here again and his availability for the start of the season is unknown. The Warriors might be bad, bad. https://t.co/KuRNTPJ1fy"),
    ("Raul Rosas Jr. recalls terrifying UFC Vegas 121 finish of Raoni Barcelos: 'I didn't know if he died'", "Josh Hokit scoffs at Dana White dreading UFC champ possibility: 'He has to say that' https://t.co/6VKfFgU5if"),
    ('Booed on the road, Caitlin Clark and the Fever now face a must-win Game 2 at home versus Aces', 'My goodness, Steph White has done a PHENOMENAL job of TRYING to humble Caitlin Clark both with the Fever and @usabasketball but it won’t work.  CC’s too good of a person and player to let her break her down. https://t.co/UnMSvMo22D'),
    ('Braves Postseason eve chat and discussion: September 28', "Really excited about bringing 3 Yankees fans to Game 1 tomorrow. I've read all the stories, memories, and I hope we get another run this October. We've been knocking on the door for too long. It's time to break through. \n\n#TAKE28"),
    # guard 2 strip 7:11 (2104668324403826776): same-club adjacent person, foreign person in
    # subject position (Ty France) vs a Stearns/Bichette/Baty/Senga roster story.
    ("What's next for Mets? David Stearns breaks down Bo Bichette, Brett Baty, Kodai Senga and 2027 roster", 'Completely fine if you think Ty France is the answer at 1b *but* there is no chance Ty France is coming to the Mets to b'),
    # guard 2 strip 7:28 (2104681108113908031): generic CBS Top 25 update naming neither Kansas
    # nor Tre White - entity conflict + foreign principal against the Kansas rankings article.
    ('College basketball rankings: Kansas joins early Top 25 And 1 after Tre White cleared to play by court ruling', 'COLLEGE BASKETBALL RANKINGS: The 2026-27 @CBSSports Preseason Top 25 And 1 has been updated to reflect recent developments. \n\nVersion 28 \n\n1. Florida \n2. Duke \n3. Illinois \n4. UConn \n5. Texas \nhttps://t.co/kwB8r1rGhH'),
    # 7:46 re-admission (2104679415208698214, eg3 hole): the served Fever story's headline
    # yielded ZERO entities, the layer-2 check was skipped, and the Caitlin Clark post pinned.
    # Empty/unextractable headline = the production shape; foreign subject person must kill.
    ('', 'My goodness, Steph White has done a PHENOMENAL job of TRYING to humble Caitlin Clark both with the Fever and @usabasketball but it won’t work.  CC’s too good of a person and player to let her break her down. https://t.co/UnMSvMo22D'),
]
POS = [
    ('College basketball rankings: Kansas joins early Top 25 And 1 after Tre White cleared to play by court ruling', 'College basketball rankings: Kansas joins early Top 25 And 1 after Tre White cleared to play by court ruling #kansasjayhawks #jayhawks https://t.co/yVGhegNGdn'),
    ('Bears vs. Eagles preview: Philadelphia looks to remain unbeaten against Caleb Williams-less Chicago', '🏈🌃 MONDAY NIGHT FOOTBALL IN CHICAGO\n\nThe Eagles come into Soldier Field at 2-0, while the Bears are 1-1 and looking to make a statement under the lights.\n\nWith Caleb Williams ruled out, the spotlight shifts to D’Andre Swift against his former team, while Jalen Hurts looks to https://t.co/wEwprK1sXp'),
    # live-map latest survivor (2104695458157187280): side-declaring pick post on a picks
    # article - the exact keep case R1 must not burn.
    ("Today's top games to watch, best bets, odds: Eagles vs. Bears on MNF and more", 'Google and ChatGPT have the eagles winning tonight. Vegas has the eagles winning tonight. I’m picking the bears. Not because it’s reasonable, but because I still believe the right fan might keep the right game day tradition. If the bears don’t win then the fan'),
]

for title, post in NEG:
    ents, conflict = gate(title, post)
    if not conflict:
        fails.append("NEGATIVE passed entity gate: %r (ents=%s)" % (title[:60], sorted(ents)))
for title, post in POS:
    ents, conflict = gate(title, post)
    if conflict:
        fails.append("POSITIVE killed by entity gate: %r (ents=%s)" % (title[:60], sorted(ents)))

# guard 3 kill (9/28 7:51): TruGrit 2104707827759473125 vs the CBS expert-props article.
# The judge EXECUTEd on "same event (MNF) and odds ... does not contradict" - noncontradiction
# is not a match. The article-level test now demands a POSITIVE match to the article's
# concrete picks/props/expert claim; this pair must be REJECT in verdicts, not only pair-null.
CBS_PROPS = 'Eagles vs. Bears picks, player props: Experts best bets for Monday Night Football in NFL Week 3'
TRUGRIT = ('The Bears are home favorites at -122, with the Eagles at +100 for Monday Night Football. '
           'Week 3 wraps under the lights at Soldier Field. @Eagles @ChicagoBears\n\n'
           'https://t.co/J3ESD5wmGl https://t.co/uk7cNAQwI6')
pre = sm.probe_predeny(CBS_PROPS, TRUGRIT)
if not pre or pre[0] != 'REJECT':
    fails.append('guard 3: generic-odds post vs expert-props article not pre-denied: %r' % (pre,))
v, why = sm.verify(CBS_PROPS, TRUGRIT)
if v != 'REJECT':
    fails.append('guard 3: verify() verdict for TruGrit/CBS pair = %s (%s)' % (v, why))
# keep case: a post that DOES declare its own pick must reach the judge, never pre-denied
KEEP_POST = ('Google and ChatGPT have the eagles winning tonight. Vegas has the eagles winning tonight. '
             'I’m picking the bears. Not because it’s reasonable, but because I still believe.')
if sm.probe_predeny("Today's top games to watch, best bets, odds: Eagles vs. Bears on MNF and more", KEEP_POST) is not None:
    fails.append('guard 3: pick-declaring post pre-denied - would starve the judge of a legit pair')

# guard 2 story-audit kills (9/28 7:59): v6 verify() emitted fabricated YES on all four pins
# ('check-down option', 'same health status', 'direct promo of same game'). Every pair must now
# REJECT offline at the action/temporal/story-type layer; verify() asserts the exact verdict.
KEENUM = "Case Keenum's second TD pass has Bears holding 20-7 lead"
THREAD = 'Eagles vs. Bears Week 3 game thread'
CURRY = 'Steph Curry ready to go for Warriors, but injuries will be factor early'
PREVIEW = 'Bears vs. Eagles preview: Philadelphia looks to remain unbeaten against Caleb Williams-less Chicago'
GIANTS = "Does Giants' trade for J.J. McCarthy make sense? Coaches, execs explain 2 key reasons"
G2PINS = [
    (KEENUM, 'Barkley hasn’t scored a TD all season and has never scored a TD against the bears. The script is telling me that changes tonight.\n\nKeenum hasn’t seen the field in like 2 years. Swift is a receiving back. Check-downs/security blanket? I think so.\n\n#NFL #prizepicks #underdog https://t.co/rHQ0nife5N'),
    (THREAD, 'Here are the Ultegacy Team Representatives picks for today’s game between the Eagles and Bears. https://t.co/dGX2HdsDpu'),
    (CURRY, 'Steph Curry on his attempt in recruiting players to the Warriors this offseason:\n\n“Same way when you pull up to shoot a shot and you miss… If it doesn\'t happen, it doesn\'t change your vibe at all. It\'s part of the business.”\n\n(via @kenzofuku) https://t.co/IjxBdxcEml'),
    (PREVIEW, 'Chicago Bears quarterback Caleb Williams was officially inactive for Monday night’s game against the Philadelphia Eagles at Soldier Field. https://t.co/bDVgzvZYJE'),
]
for title, post in G2PINS:
    v, why = sm.verify(title, post)
    if v != 'REJECT':
        fails.append('guard 2 pin: verify() verdict = %s for %r (%s)' % (v, title[:50], why))
G2MORE = [
    (GIANTS, 'Anyone think JJ McCarthy will rock #4 in honor of Jim while playing for John? It’s one of a few QB numbers available for the Giants.\n\nHe can’t wear 9 and he can’t wear 2, which he wore in high school.'),
    (KEENUM, 'Case Keenum making his first start against the Eagles in 7 years 🦅👀 Could be a shootout tonight in Chicago 🐻🔥💨 The RaQ might be on one 😤💯#MNF 🏈 #Eagles #DaBears'),
    (PREVIEW, 'The Philadelphia Eagles hit the road for the second straight week when they travel to the Windy City to take on the Chicago Bears!\n\nTune into WEEU tonight at 8:15pm for the game! Merrill Reese and Mike Quick have the call!\n\nGo Birds 🦅'),
    (PREVIEW, 'Philadelphia Eagles (2-0) vs. Chicago Bears (1-1)\nSeptember 28, 2026 8:15 pm EDT\n\nThe Eagles have been strong in this situation, going 4-0 ATS in the second of back-to-back road games and 4-1 ATS against NFC North opponents. Meanwhile, Chicago has struggled under the Monday night'),
]
for title, post in G2MORE:
    if not sm.story_type_gate(title, post):
        fails.append('guard 2 more/nearest junk passed story_type_gate: %r' % (title[:50],))
# keeps: legit pairs must NOT die to the new gates
G2KEEPS = [
    ('Bears vs. Eagles preview: Philadelphia looks to remain unbeaten against Caleb Williams-less Chicago',
     '🏈🌃 MONDAY NIGHT FOOTBALL IN CHICAGO\n\nThe Eagles come into Soldier Field at 2-0, while the Bears are 1-1 and looking to make a statement under the lights.\n\nWith Caleb Williams ruled out, the spotlight shifts'),
    ("Today's top games to watch, best bets, odds: Eagles vs. Bears on MNF and more",
     'Google and ChatGPT have the eagles winning tonight. Vegas has the eagles winning tonight. I’m picking the bears. Not because it’s reasonable'),
]
for title, post in G2KEEPS:
    if sm.story_type_gate(title, post):
        fails.append('guard 2 KEEP killed by story_type_gate: %r' % (title[:50],))
# uniqueness invariant: cross-story repeat stripped, intra-story repetition allowed
_log = {'pairs': {'A': {'post_id': 'p1'}, 'B': {'post_id': 'p2'}},
        'nearest': {'A': {'post_id': 'p1'}, 'B': {'post_id': 'p1'}},
        'more': {'A': [{'post_id': 'p1'}], 'C': [{'post_id': 'p2'}, {'post_id': 'p3'}]},
        'latest': {'D': {'post_id': 'p1'}}, 'audit': {}}
_viol = sm.enforce_uniqueness(_log)
if not _viol or 'B' in _log['nearest'] or 'D' in _log['latest']:
    fails.append('uniqueness sweep failed to strip cross-story repeats: %r' % (_viol,))
if _log['nearest'].get('A', {}).get('post_id') != 'p1' or _log['more']['A'][0]['post_id'] != 'p1':
    fails.append('uniqueness sweep stripped allowed intra-story repetition')
if _log['more']['C'] != [{'post_id': 'p3'}]:
    fails.append('uniqueness sweep wrong on story C (p2 cross-story repeat must drop, p3 keep): %r' % (_log['more']['C'],))

# equivocal-YES parser fixtures (guard 2 parsing bug: "YES - Different team." was badged)
v, _ = sm.parse_verification('Story subject: Braves postseason discussion\nPost subject: Yankees fans attending Game 1\nYES - Different team.')
if v != "ABSTAIN": fails.append("equivocal YES (different team) parsed as %s" % v)
v, _ = sm.parse_verification('Story subject: Clark Game 2\nPost subject: unrelated\nYES - unrelated to the story.')
if v != "ABSTAIN": fails.append("equivocal YES (unrelated) parsed as %s" % v)
v, _ = sm.parse_verification('Story subject: X\nPost subject: X\nYES - exact headline quote with no contradiction.')
if v != "EXECUTE": fails.append("clean YES parsed as %s" % v)
v, _ = sm.parse_verification('Story subject: X\nPost subject: Y\nNO - different player as main subject.')
if v != "REJECT": fails.append("clean NO parsed as %s" % v)

# story_type_gate fixtures (eg2, guards 2+3 strips 7:10-7:11 PM): R1 picks-article needs
# article-pick evidence; R2 bet-slip never pairs a non-picks story; R3 historical post
# never pairs a breaking-event story. Each negative is the exact served false pair.
PICKS_TITLE = "Eagles vs. Bears picks, player props: Expert's best bets for Monday Night Football in NFL Week 3"
CONCUSSION_TITLE = 'Jalen Hurts sent to sideline concussion check; Andy Dalton throws red zone INT'
BREAKING_TITLE = 'Eagles QB Jalen Hurts leaves game vs. Bears briefly after hard hit out of bounds, evaluated for concussion'
EG2 = [
    # guard 3 strip (2104707827759473125 TruGrit): generic moneyline on an expert-picks article
    (PICKS_TITLE, 'The Bears are home favorites at -122, with the Eagles at +100 for Monday Night Football. Week 3 wraps under the lights at Soldier Field. @Eagles @ChicagoBears', 'picks-type article'),
    # guard 2 strip (2104708226851758217): inactives list on an expert-picks article
    (PICKS_TITLE, '#Eagles inactives at #Bears on Monday Night Football \n\nHollywood Brown\nTanner McKee (No. 3 QB)\nCole Payton\nA.J. Epenesa\n', 'picks-type article'),
    # guard 2 strip (2104707765688303939): bet-slip on a breaking concussion story
    (CONCUSSION_TITLE, 'NFL🏈 9/28/26 (MNF – EAGLES @ BEARS) \n\nBears +3.5 (-110) [4u] \n\nJalen Hurts OVER 0.5 INTs (+118) [2u] https://t.co/nysgJ9QM', 'betting-slip'),
    # guard 2 strip (2104708194119336029): career-retrospective post on a breaking injury story
    (BREAKING_TITLE, 'Jalen Hurts has been so good for Philadelphia since being named the starter in 2021... but he has struggled at times on Monday Night Football. 😬 \n\nHis 14 career interceptions on MNF are the most since 2020, and the Eagles have lost 3 of their last 4 MNF games. https://t.co/yNL6H3dtOF', 'historical'),
    # guard 2 strip 7:28 (2104707979190685854): generic ATS-trend post on the expert-picks
    # article - trend lines are not the article's concrete picks (R1).
    (PICKS_TITLE, 'Philadelphia Eagles (2-0) vs. Chicago Bears (1-1) \nSeptember 28, 2026 8:15 pm EDT \n\nThe Eagles have been strong in this situation, going 4-0 ATS in the second of back-to-back road games and 4-1 ATS against NFC North opponents. Meanwhile, Chicago has struggled under the Monday night https://t.co/M5xmqCOorv', 'picks-type article'),
]
for title, post, want in EG2:
    r = sm.story_type_gate(title, post)
    if not (r and r.startswith(want)):
        fails.append("EG2 negative not killed (%s): %r -> %s" % (want, title[:50], r))

# eg2 keep cases: the gate must stay silent on genuine pairs.
EG2_KEEP = [
    # picks article + a post declaring its side (live latest survivor)
    ("Today's top games to watch, best bets, odds: Eagles vs. Bears on MNF and more", 'Google and ChatGPT have the eagles winning tonight. Vegas has the eagles winning tonight. I’m picking the bears. Not because it’s reasonable, but because I still believe the right fan might keep the right game day tradition.'),
    # picks article + a bet-slip WITH concrete picks (R1 satisfied, R2 inapplicable)
    (PICKS_TITLE, 'MNF plays: Jalen Hurts OVER 1.5 passing TDs [2u], Saquon anytime scorer [1u] - tailing the expert card'),
    # historical framing on a NON-breaking story (R3 inapplicable)
    ('Braves Postseason eve chat and discussion: September 28', 'Braves have owned October since 2021 in my house - career fans only tonight. #TAKE28'),
]
for title, post in EG2_KEEP:
    r = sm.story_type_gate(title, post)
    if r:
        fails.append("EG2 keep case killed: %r -> %s" % (title[:50], r))


# guard 3 (7:21) stale-EXECUTE class assertions: the deterministic gate must run BEFORE any
# cache read or probe, and the generic-odds probe rule must stay in the v6 prompt - if either
# moves or is deleted, the stale-EXECUTE class reopens. Source-ordering is the assertion.
_src = open('scripts/soc_match.py').read()
_gate_at = _src.find('st_reason = story_type_gate')
_cache_at = _src.find('prior = vcache.get(vk)')
_probe_at = _src.find('vrd, why = verify(')
if not (-1 < _gate_at < _cache_at < _probe_at):
    fails.append("ordering broken: story_type_gate (%d) must precede cache read (%d) and probe (%d)" % (_gate_at, _cache_at, _probe_at))
if 'A generic odds, spread, moneyline, or totals post with no named expert pick NEVER' not in _src:
    fails.append("v6 probe generic-odds rule missing from prompt - TruGrit class can EXECUTE again")

if fails:
    print("FIXTURE FAILURES:")
    [print(" -", f) for f in fails]
    sys.exit(1)
print("fixtures PASS: %d entity negatives, %d positives, 4 parser fixtures, %d eg2 negatives, %d eg2 keeps, 2 source-order assertions" % (len(NEG), len(POS), len(EG2), len(EG2_KEEP)))
