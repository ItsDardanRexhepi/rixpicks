#!/usr/bin/env python3
"""push_gate.py - may this card send the subscriber push? (C-4.1)

A card whose card_note carries the owner-directed / sub-bar disclosure ("owner-directed", "owner directive(s)",
"sub-bar(s)", any case, as whole words) is the only way a card holding a waived numeric bar can build, and the push
is the one surface with no room for that disclosure, so such a card never pushes. Any mention withholds, negated or
not: the rule errs toward silence. The api.rix-picks.com worker's new-pick push applies the same rule.

  python3 scripts/push_gate.py manifest.json
Exit 0 = the push may go, 1 = withheld (the card discloses), 2 = the manifest cannot be read (withheld).
Read-only."""
import json, re, sys

DISCLOSE = re.compile(r'(?<![a-z0-9])(owner[- ]directed|owner directives?|sub-bars?)(?![a-z0-9])', re.I)


def withheld(manifest):
    """None when the push may go, else the reason it is withheld."""
    note = manifest.get('card_note') if isinstance(manifest, dict) else None
    m = DISCLOSE.search(note) if isinstance(note, str) else None
    return f'card_note carries the disclosure ("{m.group(1)}")' if m else None


def main(argv):
    if len(argv) != 2:
        print('usage: push_gate.py manifest.json', file=sys.stderr)
        return 2
    try:
        man = json.load(open(argv[1], encoding='utf-8'))
    except (OSError, ValueError) as e:
        print(f'PUSH WITHHELD: manifest unreadable ({type(e).__name__})')
        return 2
    why = withheld(man)
    if why:
        print('PUSH WITHHELD: ' + why)
        return 1
    print('push allowed')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
