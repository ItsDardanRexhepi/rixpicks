"""J-117 (verbatim 9/26 8:25 PM "No verification for these updates. Just fire them.",
standing 8:28 PM): live PBP relays fire INSTANTLY off ESPN core, single-source labeled.
Delivery path included: poll_once fetches plays, dedupes against seen ids, dispatches each
new play through the injected dispatcher. Scores/FINAL/money still follow J-115 two-source."""
def format_relay(play, source='ESPN core'):
    return f"[PBP|{source}, single-source per J-117] {play.get('clock','?')} {play.get('text','')}"
def is_pbp_relay(content_kind):
    return content_kind == 'pbp'
def poll_once(fetch_plays, seen, dispatch):
    """fetch_plays() -> iterable of {'id','clock','text'}; seen: mutable set; dispatch(str).
    Only NEW plays relay; returns the relays sent."""
    sent = []
    for play in fetch_plays():
        pid = play.get('id')
        if pid is None or pid in seen: continue
        seen.add(pid)
        relay = format_relay(play)
        dispatch(relay)
        sent.append(relay)
    return sent
