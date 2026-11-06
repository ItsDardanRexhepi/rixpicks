#!/usr/bin/env python3
"""validate_ticket_data.py - pre-publish check for the public ticket data files.

The Nov 2 incident: a manual archive edit left slates/wooder_tickets.json briefly malformed while it was
live (Pages serves main directly). This validator is the check that runs BEFORE a ticket-data change is
committed or published, and again in CI on every push that touches these files.

Checks (all fail closed, exit 1 with one FAIL line each; exit 2 = usage/IO error):
  - every file is strict UTF-8 JSON: no BOM, no NaN/Infinity, no duplicate object keys
  - shape: past_tickets.entries[] and wooder_tickets.tickets[] are lists of objects with a unique
    non-empty string id and a non-empty title; an active ticket has >=1 leg, each with player+market (archived legacy legs only need to be objects)
  - past entries: result in won/lost/void, archived_at ISO when present
  - an id is never both active (wooder_tickets) and archived (past_tickets)
  - wooder_tickets.json carries no dollar amounts (public cards show no money)
  - wooder_combos / wooder_dingers / wooder_first_td / ultrix_record parse with their top-level shape
With --base REF (git ref, e.g. HEAD~1 or origin/main):
  - the Past Tickets archive is append-only: no id in REF may disappear, entry count may not shrink
  - entries NEW since REF carry no dollar amounts (older entries are grandfathered)

  python3 scripts/validate_ticket_data.py [--root DIR] [--base REF]
Read-only."""
import json, os, re, subprocess, sys
from datetime import datetime

MONEY = re.compile(r'\$\s?\d')
FILES = {
    'past': 'slates/past_tickets.json', 'tickets': 'slates/wooder_tickets.json',
    'combos': 'slates/wooder_combos.json', 'dingers': 'slates/wooder_dingers.json',
    'first_td': 'slates/wooder_first_td.json', 'ultrix': 'slates/ultrix_record.json',
}
fails = []


def fail(msg):
    fails.append(msg)
    print('FAIL ' + msg)


def _pairs(pairs):
    seen = {}
    for k, v in pairs:
        if k in seen:
            raise ValueError('duplicate key ' + repr(k))
        seen[k] = v
    return seen


def _const(c):
    raise ValueError('non-finite number ' + c)


def parse(raw, name):
    """raw bytes -> object, or None after a FAIL."""
    if raw.startswith(b'\xef\xbb\xbf'):
        fail(name + ': starts with a BOM')
        return None
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_const)
    except Exception as e:
        fail(name + ': not valid strict JSON (' + type(e).__name__ + ': ' + str(e)[:120] + ')')
        return None


def iso_ok(s):
    try:
        datetime.fromisoformat(s.replace('Z', '+00:00'))
        return True
    except Exception:
        return False


def nes(v):
    return isinstance(v, str) and v.strip() != ''


def check_list(doc, key, name, ticket):
    rows = doc.get(key) if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        fail(name + ': top-level "' + key + '" is not a list')
        return []
    if isinstance(doc.get('generated_at'), str) and not iso_ok(doc['generated_at']):
        fail(name + ': generated_at is not an ISO timestamp')
    ids = set()
    for i, e in enumerate(rows):
        tag = name + ' ' + key + '[' + str(i) + ']'
        if not isinstance(e, dict):
            fail(tag + ': not an object')
            continue
        tag += ' id=' + str(e.get('id'))
        if not nes(e.get('id')):
            fail(tag + ': missing id')
            continue
        if e['id'] in ids:
            fail(tag + ': duplicate id')
        ids.add(e['id'])
        if not nes(e.get('title')):
            fail(tag + ': missing title')
        legs = e.get('legs')
        if legs is not None and not isinstance(legs, list):
            fail(tag + ': legs is not a list')
            legs = None
        if ticket and e.get('kind') == 'ticket' and not legs:
            fail(tag + ': ticket has no legs')
        for j, l in enumerate(legs or []):
            if not isinstance(l, dict) or not l:
                fail(tag + ' leg ' + str(j) + ': not a non-empty object')
            elif ticket and (not nes(l.get('player')) or not nes(l.get('market'))):
                fail(tag + ' leg ' + str(j) + ': active ticket leg needs player and market')
        if not ticket:
            if e.get('result') not in ('won', 'lost', 'void'):
                fail(tag + ': result must be won/lost/void, got ' + repr(e.get('result')))
            if 'archived_at' in e and not (isinstance(e['archived_at'], str) and iso_ok(e['archived_at'])):
                fail(tag + ': archived_at is not an ISO timestamp')
    return rows


def git_show(root, ref, path):
    try:
        return subprocess.check_output(['git', '-C', root, 'show', ref + ':' + path], stderr=subprocess.DEVNULL)
    except Exception:
        return None


def main(argv):
    root, base = '.', None
    a = argv[1:]
    while a:
        if a[0] == '--root' and len(a) > 1:
            root = a[1]; a = a[2:]
        elif a[0] == '--base' and len(a) > 1:
            base = a[1]; a = a[2:]
        else:
            print(__doc__.split('\n\n')[0]); return 2
    docs = {}
    for k, p in FILES.items():
        fp = os.path.join(root, p)
        try:
            raw = open(fp, 'rb').read()
        except OSError as e:
            fail(p + ': unreadable (' + type(e).__name__ + ')')
            continue
        docs[k] = parse(raw, p)
        if k == 'tickets' and MONEY.search(raw.decode('utf-8', 'replace')):
            fail(p + ': contains a dollar amount (public cards show no money)')
    past = check_list(docs['past'], 'entries', FILES['past'], False) if docs.get('past') is not None else []
    tix = check_list(docs['tickets'], 'tickets', FILES['tickets'], True) if docs.get('tickets') is not None else []
    both = {e.get('id') for e in past if isinstance(e, dict)} & {e.get('id') for e in tix if isinstance(e, dict)}
    for i in sorted(x for x in both if x):
        fail('id ' + i + ' is in both wooder_tickets (active) and past_tickets (archived)')
    if docs.get('combos') is not None and not (isinstance(docs['combos'], dict) and isinstance(docs['combos'].get('combos'), list)):
        fail(FILES['combos'] + ': "combos" is not a list')
    if docs.get('dingers') is not None and not (isinstance(docs['dingers'], dict) and isinstance(docs['dingers'].get('picks'), list)):
        fail(FILES['dingers'] + ': "picks" is not a list')
    if docs.get('first_td') is not None and not isinstance(docs['first_td'], dict):
        fail(FILES['first_td'] + ': not an object')
    if docs.get('ultrix') is not None and not (isinstance(docs['ultrix'], dict) and 'record' in docs['ultrix'] and 'picks' in docs['ultrix']):
        fail(FILES['ultrix'] + ': missing record/picks')
    if base:
        raw = git_show(root, base, FILES['past'])
        if raw is None:
            print('NOTE no ' + FILES['past'] + ' at ' + base + ' - append-only check skipped')
        else:
            old = parse(raw, base + ':' + FILES['past'])
            oldrows = old.get('entries') if isinstance(old, dict) and isinstance(old.get('entries'), list) else []
            oldmap = {e.get('id'): e for e in oldrows if isinstance(e, dict)}
            newids = {e.get('id') for e in past if isinstance(e, dict)}
            for i in sorted(str(x) for x in set(oldmap) - newids):
                fail('past_tickets: archived entry ' + i + ' disappeared since ' + base)
            if len(past) < len(oldrows):
                fail('past_tickets: entry count shrank ' + str(len(oldrows)) + ' -> ' + str(len(past)))
            for e in past:
                if isinstance(e, dict) and e.get('id') not in oldmap and MONEY.search(json.dumps(e)):
                    fail('past_tickets: new entry ' + str(e.get('id')) + ' contains a dollar amount')
    if fails:
        print(str(len(fails)) + ' FAIL - ticket data must not publish')
        return 1
    print('TICKET DATA OK (' + str(len(past)) + ' archived, ' + str(len(tix)) + ' active)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
