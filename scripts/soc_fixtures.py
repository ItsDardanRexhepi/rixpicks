#!/usr/bin/env python3
"""Deterministic regression fixtures for the matching gate (owner 6:58 9/28, guard 2 incident).
Runs OFFLINE against title_entities/entity_conflict/post_persons and the equivocal parser.
x_feed.yml runs this BEFORE soc_match: a failure aborts the chain before a bad map ships.
The 5 negatives are the exact served false pairs; the props-article/generic-odds negative
(2104681322878754826) passes this deterministic gate BY DESIGN - it is covered by the v6
probe rule (generic odds never matches expert-picks articles) and cannot be asserted offline."""
import importlib.util, sys

spec = importlib.util.spec_from_file_location("soc_match", "scripts/soc_match.py")
sm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sm)

def gate(title, post, need=2):
    ents = sm.title_entities(title)
    return ents, sm.entity_conflict(ents, post, need) or bool(sm.post_persons(post, ents))

fails = []
NEG = [
    ('Steph Curry ready to go for Warriors, but injuries will be factor early', 'the blazers ain’t making the playoffs but hopefully ja individual performance revives his career and he gets traded to the warriors https://t.co/zYzT23aTmc'),
    ('Luka Doncic and Austin Reaves ready to take charge of new-look Lakers', "Kristaps Porzingis' health issue is here again and his availability for the start of the season is unknown. The Warriors might be bad, bad. https://t.co/KuRNTPJ1fy"),
    ("Raul Rosas Jr. recalls terrifying UFC Vegas 121 finish of Raoni Barcelos: 'I didn't know if he died'", "Josh Hokit scoffs at Dana White dreading UFC champ possibility: 'He has to say that' https://t.co/6VKfFgU5if"),
    ('Booed on the road, Caitlin Clark and the Fever now face a must-win Game 2 at home versus Aces', 'My goodness, Steph White has done a PHENOMENAL job of TRYING to humble Caitlin Clark both with the Fever and @usabasketball but it won’t work.  CC’s too good of a person and player to let her break her down. https://t.co/UnMSvMo22D'),
    ('Braves Postseason eve chat and discussion: September 28', "Really excited about bringing 3 Yankees fans to Game 1 tomorrow. I've read all the stories, memories, and I hope we get another run this October. We've been knocking on the door for too long. It's time to break through. \n\n#TAKE28"),
]
POS = [
    ('College basketball rankings: Kansas joins early Top 25 And 1 after Tre White cleared to play by court ruling', 'College basketball rankings: Kansas joins early Top 25 And 1 after Tre White cleared to play by court ruling #kansasjayhawks #jayhawks https://t.co/yVGhegNGdn'),
    ('Bears vs. Eagles preview: Philadelphia looks to remain unbeaten against Caleb Williams-less Chicago', '🏈🌃 MONDAY NIGHT FOOTBALL IN CHICAGO\n\nThe Eagles come into Soldier Field at 2-0, while the Bears are 1-1 and looking to make a statement under the lights.\n\nWith Caleb Williams ruled out, the spotlight shifts to D’Andre Swift against his former team, while Jalen Hurts looks to https://t.co/wEwprK1sXp'),
    ('Jalen Hurts sent to sideline concussion check; Andy Dalton throws red zone INT', 'NFL 9/28/26 (MNF - EAGLES @ BEARS)\n\nBears +3.5 (-110) [4u]\n\nJalen Hurts OVER 0.5 INTs (+118) [2u]'),
]

for title, post in NEG:
    ents, conflict = gate(title, post)
    if not conflict:
        fails.append("NEGATIVE passed gate: %r (ents=%s)" % (title[:60], sorted(ents)))
for title, post in POS:
    ents, conflict = gate(title, post)
    if conflict:
        fails.append("POSITIVE killed by gate: %r (ents=%s)" % (title[:60], sorted(ents)))

# equivocal-YES parser fixtures (guard 2 parsing bug: "YES - Different team." was badged)
v, _ = sm.parse_verification('Story subject: Braves postseason discussion\nPost subject: Yankees fans attending Game 1\nYES - Different team.')
if v != "ABSTAIN": fails.append("equivocal YES (different team) parsed as %s" % v)
v, _ = sm.parse_verification('Story subject: Clark Game 2\nPost subject: unrelated\nYES - unrelated to the story.')
if v != "ABSTAIN": fails.append("equivocal YES (unrelated) parsed as %s" % v)
v, _ = sm.parse_verification('Story subject: X\nPost subject: X\nYES - exact headline quote with no contradiction.')
if v != "EXECUTE": fails.append("clean YES parsed as %s" % v)
v, _ = sm.parse_verification('Story subject: X\nPost subject: Y\nNO - different player as main subject.')
if v != "REJECT": fails.append("clean NO parsed as %s" % v)

if fails:
    print("FIXTURE FAILURES:")
    [print(" -", f) for f in fails]
    sys.exit(1)
print("fixtures PASS: %d negatives killed, %d positives kept, 4 parser fixtures" % (len(NEG), len(POS)))
