"""snapshot_closes.py - W1-X05 closing line snapshot job.

Captures closing lines at T-5 (5 minutes before game start) for every game in
each carded league. Writes to slates/closes/<date>.jsonl.

Captures Kalshi plus at least 3 books where available. Each line is JSON with:

eid, league, commence (ISO timestamp), kalshi_close_c,
books: {dk: close_c, fd: close_c, mgm: close_c},
close_novig_c (no-vig fair from books).
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

SNAPSHOT_LEAD = timedelta(minutes=5)
OUT_DIR = os.path.join("slates", "closes")


def parse_iso(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def iso_utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def novig_fair(book_prices):
    """Compute a no-vig fair price from a dict of book -> decimal price."""
    prices = [float(p) for p in book_prices.values() if p]
    if not prices:
        return None
    return round(sum(prices) / len(prices), 4)


def fetch_games():
    """Placeholder: fetch every game in each carded league."""
    # TODO: pull from carded-league schedule source (returns eid, league, commence)
    return []


def fetch_close(game):
    """Placeholder: fetch closing lines at T-5 for a single game."""
    # TODO: fetch Kalshi close + at least 3 book closes via odds providers
    return {
        "eid": game["eid"],
        "league": game["league"],
        "commence": game["commence"],
        "kalshi_close_c": None,
        "books": {"dk": None, "fd": None, "mgm": None},
        "close_novig_c": None,
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = os.path.join(OUT_DIR, f"{today}.jsonl")

    games = fetch_games()
    if not games:
        print("snapshot_closes: no games returned by fetch_games(); writing empty snapshot")

    with open(out_path, "w") as fh:
        for game in games:
            record = fetch_close(game)
            book_prices = {b: p for b, p in record["books"].items() if p}
            if book_prices:
                record["close_novig_c"] = novig_fair(book_prices)
            fh.write(json.dumps(record) + "\n")

    print(f"snapshot_closes: wrote {len(games)} games to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
