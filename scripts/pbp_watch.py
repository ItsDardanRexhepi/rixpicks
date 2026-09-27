#!/usr/bin/env python3
"""J-117 TRIGGER (production): instant unverified PBP relays off ESPN core, dedup'd.
Activated ONLY when he asks for play-by-play on a specific game (J-117 scope) - the
requester's wake chain calls this on its poll cadence.
Usage: pbp_watch.py <espn_league e.g. football/college-football> <event_id>
Prints new relays (single-source labeled per J-117); state persists in KB ledger."""
import json, os, sys, urllib.request
sys.path.insert(0, '/home/sandbox/rix_tmp')
from core import pbp_relay
STATE_DIR = '/home/sandbox/rps_tmp/kb/ledger/pbp_seen'
def fetch(league, eid):
    url = (f'https://sports.core.api.espn.com/v2/sports/{league}/events/{eid}'
           f'/competitions/{eid}/plays?limit=300')
    with urllib.request.urlopen(url, timeout=20) as r:
        items = json.load(r).get('items', [])
    return [{'id': p.get('id'), 'clock': p.get('clock', {}).get('displayValue', '?')
             if isinstance(p.get('clock'), dict) else '?',
             'text': p.get('text', '')} for p in items]
def main():
    league, eid = sys.argv[1], sys.argv[2]
    os.makedirs(STATE_DIR, exist_ok=True)
    sp = os.path.join(STATE_DIR, f'{eid}.json')
    try: seen = set(json.load(open(sp)))
    except Exception: seen = set()
    sent = pbp_relay.poll_once(lambda: fetch(league, eid), seen, print)
    json.dump(sorted(seen), open(sp, 'w'))
    if not sent: print('(no new plays)')
if __name__ == '__main__': main()
