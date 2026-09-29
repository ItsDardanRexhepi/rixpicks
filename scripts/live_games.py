#!/usr/bin/env python3
"""Live games feed for the Games panel (owner ask Sep 27: in the live feed updates the games,
show a timeouts tracker for each team too - across all leagues, at core level; Sep 27 PM: it is
off and not live, fix it system wide at its core).
Registry-driven (config_leagues.json): today's ESPN scoreboard per league; keeps games in
progress, starting within 2h, or final within 4h. For in-progress games on timeout leagues
(football/basketball/hockey), per-team timeouts come from core.timeouts (ESPN core situation).
Fail-closed per league and per game: a league that errors is omitted, timeouts that fail render
blank. Times render PT only (owner rule 9/27) - ESPN shortDetail arrives ET and is shifted.
Usage: python3 scripts/live_games.py <out_path>
"""
import json, os, re, sys, time, urllib.request
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root - core/ import on GHA runners
from core.timeouts import fetch_timeouts

UA = {"User-Agent": "python-urllib/3.10"}
SB = "https://site.api.espn.com/apis/site/v2/sports/{lg}/scoreboard?dates={d}{prm}"
TO_PREFIXES = ("football/", "basketball/", "hockey/")
# Max age (seconds) an in-progress row may live past its commence time before it is
# treated as a stale scoreboard artifact and dropped (audit Sep 28: 2-4 day old ATP/WTA
# rows served as live 0-0). A match beyond its expected window is re-admitted only when a
# fresh live-source check confirms it is actually still playing; absent that, fail-closed drop.
MAX_IN_AGE = {"tennis/": 6 * 3600}
MAX_IN_AGE_DEFAULT = 6 * 3600
AL = {"WSH": "WAS"}  # ESPN abbr -> site abbr

_RE_PT = re.compile(r"(\d{1,2}):(\d{2}) ([AP])M E[DS]T")
def _pt_detail(s):
    # owner rule 9/27: ALL times render PT, never ET. ESPN shortDetail arrives ET
    # ("9/27 - 1:00 PM EDT") - shift -3h, suffix PT. Non-matching strings pass through.
    if not s:
        return s
    def _cv(m):
        h24 = (int(m.group(1)) % 12) + (12 if m.group(3) == "P" else 0)
        h24 = (h24 + 21) % 24
        ap2 = "AM" if h24 < 12 else "PM"
        return "%d:%s %s PT" % (h24 % 12 or 12, m.group(2), ap2)
    return _RE_PT.sub(_cv, s)

def main(out_path):
    reg = json.load(open("config_leagues.json"))["leagues"]
    now = datetime.now(timezone.utc)
    d = now.astimezone(timezone(timedelta(hours=-4))).strftime("%Y%m%d")  # ET game day
    out_leagues = []
    n_games = 0
    for key, v in reg.items():
        lg = v.get("espn")
        if not lg:
            continue
        prm = "&" + v["espn_params"] if v.get("espn_params") else ""
        try:
            req = urllib.request.Request(SB.format(lg=lg, d=d, prm=prm), headers=UA)
            sb = json.load(urllib.request.urlopen(req, timeout=20))
        except Exception as e:
            print("league %s fetch failed: %s" % (key, e), file=sys.stderr)
            continue  # fail-closed per league: omit, panel keeps the rest
        games = []
        for ev in sb.get("events", []):
            comps = []
            if ev.get("competitions"):
                comps.append(ev["competitions"][0])
            for g in ev.get("groupings", []):
                comps.extend(g.get("competitions") or [])
            for c in comps:
                try:
                    st = (c.get("status") or {}).get("type") or {}
                    state = st.get("state") or ""
                    dt = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")) if ev.get("date") else None
                    delta = (dt - now).total_seconds() if dt else None
                    max_age = next((v for pfx, v in MAX_IN_AGE.items() if lg.startswith(pfx)), MAX_IN_AGE_DEFAULT)
                    keep = ((state == "in" and delta is not None and delta >= -max_age)
                            or (state == "pre" and delta is not None and 0 <= delta <= 7200)
                            or (state == "post" and delta is not None and -14400 <= delta <= 0))
                    if not keep:
                        continue
                    teams = {}
                    for comp in c.get("competitors", []):
                        t = comp.get("team") or comp.get("athlete") or {}
                        ab = t.get("abbreviation") or t.get("displayName") or ""
                        ab = AL.get(ab, ab)
                        teams[comp.get("homeAway")] = (ab, comp.get("score") or "0")
                    if "away" not in teams or "home" not in teams or not teams["away"][0] or not teams["home"][0]:
                        continue
                    (aab, asc), (hab, hsc) = teams["away"], teams["home"]
                    eid = str(c.get("id") or ev.get("id") or "")
                    seen = {g["espn_event_id"] for g in games}
                    if eid in seen:  # grouped tennis comps share the tournament-level event id - disambiguate per match
                        eid = "%s-%s-%s" % (eid, aab.lower().replace(" ", ""), hab.lower().replace(" ", ""))
                    rec = {"espn_event_id": eid, "matchup": "%s @ %s" % (aab, hab),
                           "commence": ev.get("date"), "status": state,
                           "detail": _pt_detail(st.get("shortDetail") or ""),
                           "score": "%s %s - %s %s" % (aab, asc, hab, hsc)}
                    if state == "in" and lg.startswith(TO_PREFIXES):
                        a_to, h_to = fetch_timeouts(lg, ev.get("id"))
                        rec["away_to"] = a_to
                        rec["home_to"] = h_to
                        time.sleep(0.2)
                    games.append(rec)
                except Exception:
                    continue  # fail-closed per game
        if games:
            out_leagues.append({"league": key, "games": games})
            n_games += len(games)
        time.sleep(0.2)
    if n_games == 0:
        carded = False
        try:
            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            man = json.load(open(os.path.join(repo_root, "manifest.json")))
            pt_today = now.astimezone(timezone(timedelta(hours=-7))).strftime("%Y-%m-%d")
            carded = bool(man.get("picks")) and str(man.get("date", "")) == pt_today
        except Exception:
            carded = False
        prev_games = 0
        try:
            prev = json.load(open(out_path))
            prev_games = sum(len(l.get("games", [])) for l in prev.get("leagues", []))
        except Exception:
            pass
        if carded or prev_games:
            print("REFUSING 0-game overwrite of %s (carded_today=%s, prev_games=%d) - keeping last file" % (out_path, carded, prev_games), file=sys.stderr)
            sys.exit(1)
    out = {"version": 1, "generated_at": now.isoformat(), "leagues": out_leagues}
    json.dump(out, open(out_path, "w"), indent=1)
    n_to = sum(1 for L in out_leagues for g in L["games"] if g.get("away_to") is not None)
    print("wrote %s: %d leagues, %d games, %d with timeouts" % (out_path, len(out_leagues), n_games, n_to), file=sys.stderr)

if __name__ == "__main__":
    main(sys.argv[1])
