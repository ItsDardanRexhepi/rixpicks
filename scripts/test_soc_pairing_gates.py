#!/usr/bin/env python3
"""Feed guard 2 zero-admission class (Sep 29): the cleaned pool still admitted ZERO pairs.
Three verified defects, three standing fixtures so the class cannot regress:
1. possessive/HTML-entity headline principals unmatched by post token hits (eg1 false kills),
   + blurb co-principal exemption in post_persons (Bussi-in-Forsling-blurb class);
   the headline stays the subject anchor - names NOT in the blurb stay foreign (Riley class).
2. probe prompt: a reaction DISPUTING the story's exact claim is on-story (Kessler class) -
   fixture asserts the guidance + the verdict-cache salt bump (stale NOs must re-probe).
3. reason_integrity stays default-deny: a YES reason citing a post-only aside fails;
   repair prompt must demand the claim shared by BOTH inputs (Nomadmojo class).
Run: python3 scripts/test_soc_pairing_gates.py
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soc_match

fails = 0
def check(label, cond):
    global fails
    print(('OK   ' if cond else 'FAIL ') + label)
    if not cond: fails += 1

# --- fix 1: normalization ---
check('possessive headline extracts base principal', 'mattingly' in soc_match.title_entities("Mattingly's three-run homer caps Jays rally"))
check('no possessive residue in entities', not any(e.endswith(("'s", "'")) for e in soc_match.title_entities("Mattingly's three-run homer caps Jays rally")))
check('HTML entity headline extracts base principal', 'forsling' in soc_match.title_entities('Forsling&#039;s OT winner stuns Rangers'))
check('entity_hits: bare post name hits possessive headline ent', soc_match.entity_hits({'mattingly'}, 'Don Mattingly did it again tonight') == 1)
check('entity_hits: HTML-entity post text hits base ent', soc_match.entity_hits({'forsling'}, 'Forsling&#039;s winner was unreal') == 1)
check('entity_hits: possessive post text hits base ent', soc_match.entity_hits({'mattingly'}, "Mattingly's best game as a Jay") == 1)
check('entity_hits: non-match still zero', soc_match.entity_hits({'mattingly'}, 'totally unrelated hockey talk') == 0)

# eg1 no longer kills the Mattingly-class candidate (both headline ents present in post)
HEAD = "Mattingly's three-run homer caps Jays rally"
ENTS = soc_match.title_entities(HEAD)
check('fixture headline extracts two ents', ENTS == {'mattingly', 'jays'})
check('eg1 passes on-story post (bare names)', not soc_match.entity_conflict(ENTS, 'Don Mattingly goes deep and the Jays win it', 2))

# blurb co-principal exemption: Bussi named in the Forsling blurb -> not foreign
check('blurb co-principal exempt (Bussi/Forsling)',
      not soc_match.post_persons('Brandon Bussi stood on his head, 41 saves tonight', {'forsling'},
                                 blurb='Gustav Forsling scored in overtime as Brandon Bussi made 41 saves'))
# parent precision: the Mattingly blurb names Don Mattingly + Jhoan Duran, NOT Austin Riley -
# Riley must NOT be whitelisted from that blurb (still a foreign principal)
check('blurb non-named person stays foreign (Riley/Mattingly)',
      soc_match.post_persons('Austin Riley goes yard twice tonight', {'mattingly'},
                             blurb='Don Mattingly praised Jhoan Duran after the win') == {'riley'})
# no blurb given: same candidate still foreign (exemption needs the actual blurb text)
check('exemption requires the blurb (no blurb -> foreign)',
      soc_match.post_persons('Brandon Bussi stood on his head tonight', {'forsling'}) == {'bussi'})
# wrong-player negatives retained
check('wrong-player negative retained (Hokit/Rosas)',
      soc_match.post_persons('Josh Hokit dominant again on the mound', {'rosas'}, blurb='Rosas takes the mound Tuesday') == {'hokit'})
# eg3 fallback normalization: possessive headline no longer false-foreigns the bare name
check('eg3 possessive headline passes bare name',
      not soc_match.foreign_person_vs_title("Mattingly&#039;s heroics", 'Don Mattingly did it again'))
check('eg3 still catches a true foreign principal',
      soc_match.foreign_person_vs_title('Jays rally late', 'Connor McDavid scores twice') == {'mcdavid'})

# --- fix 2: disagreement guidance + cache salt bump ---
SRC = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'soc_match.py')).read()
check('probe prompt carries dispute-is-on-story guidance',
      'DISPUTES the story' in SRC and 'agreement is not required' in SRC)
check('prompt version bumped to v17 (stale disagree-NOs re-probe)',
      "PROMPT_VERSION = 'v17-disagreement-on-story'" in SRC)
check('SALT still derives from PROMPT_VERSION', 'PROMPT_VERSION, ENTITY_GATE_VERSION' in SRC)

# --- fix 3: reason integrity + repair prompt ---
story = "Kessler talks up Lakers' title hopes behind 'nasty' defense - Kessler discusses the Lakers as a nasty defensive team."
post = 'Lakers are NOT a nasty defensive team, effort > excuses. Kessler discusses it but he is wrong.'
check('YES reason citing only the post aside is denied',
      soc_match.reason_integrity('Effort over excuses wins games', story, post) is False)
check('invented action denied (reason action absent from both inputs)',
      soc_match.reason_integrity('Kessler scores twice in win', story, post) is False)
check('invented number denied',
      soc_match.reason_integrity('Lakers win 114-100 behind defense', story, post) is False)
story2 = 'Kessler discusses the Lakers nasty defensive identity ahead of the season.'
post2 = 'Kessler discusses nasty defense - I disagree, Lakers are soft. #NBA'
check('grounded shared-action YES reason still passes',
      soc_match.reason_integrity('Kessler discusses Lakers nasty defense', story2, post2) is True)
check('repair prompt demands the shared claim in BOTH inputs',
      'present in BOTH the story and' in SRC and 'is not a shared reason' in SRC)

print()
print('FAILURES: %d' % fails if fails else 'ALL PASS')
sys.exit(1 if fails else 0)
