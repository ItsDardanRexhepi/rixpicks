#!/usr/bin/env python3
"""Refresh slates/nfl_rec_yards.json: season receiving yards for the futures card players.
Source: ESPN site.web.api.espn.com byathlete stats (season-to-date, regular season).
Fail-closed: a player missing from the feed is omitted (card renders Unavailable), never zero-filled."""
import json, sys, datetime, urllib.request
NAMES = ["Mike Evans","Emeka Egbuka","Tetairoa McMillan","Trey McBride","Zay Flowers",
         "Chris Olave","Ladd McConkey","Drake London","Christian Watson","Wan'Dale Robinson"]
URL = "https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/statistics/byathlete?season=%d&seasontype=2&sort=receiving.receivingYards:desc&limit=400"
def main(out="slates/nfl_rec_yards.json", season=2026):
    d = json.load(urllib.request.urlopen(urllib.request.Request(URL % season, headers={"User-Agent":"Mozilla/5.0"}), timeout=30))
    cat = next(c for c in d["categories"] if c["name"] == "receiving")
    iy = cat["names"].index("receivingYards")
    players = {}
    for a in d["athletes"]:
        n = a["athlete"]["displayName"]
        if n in NAMES:
            r = next((c for c in a["categories"] if c["name"] == "receiving"), None)
            if r and r["values"][iy] is not None:
                players[n] = {"yards": int(r["values"][iy]), "espn_id": a["athlete"]["id"]}
    doc = {"source": "ESPN season receiving yards (regular season to date)", "season": season,
           "fetched_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "players": players}
    if len(players) < 1:
        print("no players parsed - refusing to write", file=sys.stderr); sys.exit(1)
    json.dump(doc, open(out, "w"), indent=1)
    print("wrote", out, len(players), "players")
if __name__ == "__main__": main()
