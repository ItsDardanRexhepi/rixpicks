"""Per-team timeouts fetch + normalize (owner ask Sep 27: timeouts tracker for each team in
live game updates - across all leagues, at core level).
Source: ESPN core API situation endpoint - verified live Sep 27:
  football (NFL/CFB): situation carries homeTimeouts/awayTimeouts as ints
  basketball (NBA/WNBA/NCAAB): same fields as objects {timeoutsCurrent, timeoutsRemainingCurrent}
    - remaining is the live number
  hockey (NHL): same endpoint; normalized the same way when present
Leagues without timeouts (MLB, soccer, tennis, golf, racing, mma) never call this.
Fail-closed (URF): any error or missing field -> (None, None); blank beats wrong.
"""
import json, urllib.request

CORE = "https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/events/{eid}/competitions/{eid}/situation"

def _to_int(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, dict):
        for k in ("timeoutsRemainingCurrent", "timeoutsCurrent"):
            if isinstance(v.get(k), int):
                return v[k]
    return None

def fetch_timeouts(espn_path, eid):
    """espn_path: registry path like 'football/nfl'. Returns (away_to, home_to) ints or (None, None)."""
    try:
        sport, league = espn_path.split("/", 1)
        url = CORE.format(sport=sport, league=league, eid=eid)
        req = urllib.request.Request(url, headers={"User-Agent": "python-urllib/3.10"})
        d = json.load(urllib.request.urlopen(req, timeout=15))
        return _to_int(d.get("awayTimeouts")), _to_int(d.get("homeTimeouts"))
    except Exception:
        return None, None
