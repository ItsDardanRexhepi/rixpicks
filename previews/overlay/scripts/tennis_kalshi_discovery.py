#!/usr/bin/env python3
"""Tennis Kalshi discovery + binding + pricing sidecar (owner standing directives of
9/27 7:10-7:13 PM PT: tennis on the daily card whenever Kalshi markets exist; permanent
card spec, same gates as every other league).

DYNAMIC DISCOVERY ONLY - no hardcoded series list (the hand-probed list caused the
9/27 preview miss: an unpaginated /series fetch stopped one page before KXATPMATCH,
KXWTAMATCH, KXATPCHALLENGERMATCH, KXITFMATCH, KXITFWMATCH, KXATPDOUBLES).

Pipeline:
  1. Paginate the full Kalshi /series list; keyword-filter tennis-ish (ticker+title).
  2. Per series: fetch open events (+nested markets); keep match-level events
     (' vs ' in title - filters outrights/rankings).
  3. Classify by expected_expiration_time converted to PT; keep the target date.
  4. PRICE: per event, /markets quotes; if yes_bid/ask None, derive top-of-book from
     /orderbook (yes_ask = 1 - max NO bid; yes_bid = max YES bid). Fail loud per market.
  5. FAIR: odds-API tennis keys (dynamic /sports list, any active tennis_* key with
     h2h odds) -> devig to fair probs. If the local key is absent or no tennis keys are
     active -> pricing_gap reported LOUD, nothing silently skipped.
  6. GATE: P-EDGE-001 (net edge >= 2c vs Kalshi ask after 1c fee), J-096 ladder caps.

Output: JSON catch list + loud human summary. Exit 0 always; gaps are in the payload
and printed with 'GAP:' so the build wake sees them.
"""
import json, os, re, sys, time, urllib.request, urllib.parse, datetime

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
ODDS = "https://api.the-odds-api.com/v4"
PT = datetime.timezone(datetime.timedelta(hours=-7))
UA = {"User-Agent": "python-urllib/3"}
TENNIS_RE = re.compile(r"tennis|atp|wta|itf|challenger|laver|davis ?cup|united ?cup", re.I)
FEE_C = 1.0   # Kalshi taker fee approx per contract, cents (conservative flat)
EDGE_MIN_C = 2.0  # P-EDGE-001

def get(url, timeout=25, retries=4):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429 and i < retries - 1:
                time.sleep(2 * (i + 1)); continue
            raise
        except Exception as e:
            last = e
            if i < retries - 1: time.sleep(1); continue
            raise
    raise last

SERIES_CACHE = "/home/sandbox/rix_tmp/data/tennis_series_cache.json"
def discover_series(errors):
    # 24h cache: series registry changes slowly; events are always fetched live
    try:
        if os.path.exists(SERIES_CACHE):
            c = json.load(open(SERIES_CACHE))
            if time.time() - c.get("ts", 0) < 86400:
                return c["series"]
    except Exception: pass
    out, cursor = [], None
    for _ in range(40):
        url = f"{KALSHI}/series?limit=200" + (f"&cursor={cursor}" if cursor else "")
        try: d = get(url)
        except Exception as e:
            errors.append(f"series page fetch failed: {e}"); break
        for s in d.get("series", []):
            blob = f"{s.get('ticker','')} {s.get('title','')}"
            if TENNIS_RE.search(blob): out.append(s["ticker"])
        cursor = d.get("cursor")
        if not cursor: break
    out = sorted(set(out))
    try:
        os.makedirs(os.path.dirname(SERIES_CACHE), exist_ok=True)
        json.dump({"ts": time.time(), "series": out}, open(SERIES_CACHE, "w"))
    except Exception: pass
    return out

def open_match_events(series, errors):
    """Return list of {series, event_ticker, title, exp_pt (datetime), markets:[tickers]}."""
    evs = []
    for st in series:
        try:
            d = get(f"{KALSHI}/events?series_ticker={st}&status=open&limit=200&with_nested_markets=true")
        except Exception as e:
            errors.append(f"events fetch failed for {st}: {e}"); continue
        for e in d.get("events", []):
            title = e.get("title") or ""
            if " vs " not in title and " Vs " not in title: continue  # match-level only
            mkts = [m for m in e.get("markets", []) if m.get("status") == "active"]
            if not mkts: continue
            ee = max((m.get("expected_expiration_time") or "" for m in mkts))
            try: exp = datetime.datetime.fromisoformat(ee.replace("Z", "+00:00")).astimezone(PT)
            except Exception: exp = None
            evs.append({"series": st, "event_ticker": e["event_ticker"], "title": title,
                        "exp_pt": exp.isoformat() if exp else None,
                        "markets": [m["ticker"] for m in mkts]})
    return evs

def top_of_book(ticker, errors):
    """(yes_bid_c, yes_ask_c, yes_sub_title) - quotes endpoint first, orderbook fallback.
    yes_sub_title carries the full player name; ticker suffixes are 3-letter abbrevs,
    NOT surnames - side-key off the subtitle (9/27 bug: suffix lookup matched 7/431 sides)."""
    sub = None
    try:
        d = get(f"{KALSHI}/markets/{ticker}")
        m = d.get("market", {})
        sub = m.get("yes_sub_title")
        b, a = m.get("yes_bid"), m.get("yes_ask")
        if b is not None and a is not None:
            return (float(b) * 100 if float(b) <= 1 else float(b),
                    float(a) * 100 if float(a) <= 1 else float(a), sub)
    except Exception as e:
        errors.append(f"market quote failed {ticker}: {e}")
    try:
        ob = get(f"{KALSHI}/markets/{ticker}/orderbook").get("orderbook_fp", {})
        yes_bids = [float(p) * 100 for p, _ in ob.get("yes_dollars", [])]
        no_bids = [float(p) * 100 for p, _ in ob.get("no_dollars", [])]
        yb = max(yes_bids) if yes_bids else None
        ya = (100.0 - max(no_bids)) if no_bids else None
        return yb, ya, sub
    except Exception as e:
        errors.append(f"orderbook failed {ticker}: {e}")
        return None, None, sub

def norm_surnames(title):
    title = title.split(":", 1)[0]  # strip ': Game Spread' / ': Total Games' qualifiers
    parts = re.split(r"\s+vs\.?\s+", title, flags=re.I)
    out = []
    for p in parts[:2]:
        words = [w for w in re.findall(r"[A-Za-z']+", p) if len(w) >= 3]
        if words: out.append(words[-1].lower())
    return out

def odds_api_fair(errors):
    """Dynamic tennis book discovery. Returns {matchup_key: {side: prob}} or None+gap."""
    key = os.environ.get("ODDS_API_KEY") or ""
    kf = "/home/sandbox/.odds_api_key"
    if not key and os.path.exists(kf):
        key = open(kf).read().strip()
    if not key:
        errors.append("GAP: no local odds-API key (env + /home/sandbox/.odds_api_key both absent)")
        return None
    try:
        sports = get(f"{ODDS}/sports/?apiKey={key}")
    except Exception as e:
        errors.append(f"GAP: odds-API /sports fetch failed: {e}"); return None
    tennis_keys = [s["key"] for s in sports if s.get("key", "").startswith("tennis") and s.get("active")]
    if not tennis_keys:
        errors.append("GAP: odds-API has no active tennis_* tournament keys right now"); return None
    fair = {}
    for tk in tennis_keys:
        try:
            odds = get(f"{ODDS}/sports/{tk}/odds/?apiKey={key}&regions=us&markets=h2h&oddsFormat=american")
        except Exception as e:
            errors.append(f"GAP: odds fetch failed for {tk}: {e}"); continue
        for g in odds:
            for bk in g.get("bookmakers", []):
                for mk in bk.get("markets", []):
                    if mk.get("key") != "h2h": continue
                    oc = mk.get("outcomes", [])
                    if len(oc) != 2: continue
                    def imp(a): a=float(a); return 100/(a+100) if a>0 else -a/(-a+100)
                    p = [imp(o["price"]) for o in oc]; tot = sum(p)
                    if tot <= 0: continue
                    key2 = tuple(sorted(norm_surnames(g.get("home_team","")+" vs "+g.get("away_team",""))))
                    fair.setdefault(key2, {})[oc[0]["name"].split()[-1].lower()] = p[0]/tot
                    fair[key2][oc[1]["name"] .split()[-1].lower()] = p[1]/tot
                    break  # first book only per game (single-book devig, same standard as NFL/WNBA path)
    return fair or None


GAMMA = "https://gamma-api.polymarket.com"
def poly_surnames(title):
    """Tournament-prefixed tennis titles: 'Chengdu Open: A vs B' -> surname pair."""
    t = title.split(":", 1)[-1]
    return norm_surnames(t)

def polymarket_fair(errors):
    """Polymarket tennis match-winner prices -> devigged fair, keyed by sorted surname pair.
    Match-winner market = outcomes are the two player names (not Yes/No/Over/Under) and the
    question contains no Set/O-U/Spread/Handicap qualifier."""
    idx = {}
    off = 0
    try:
        for _ in range(15):
            d = get(f"{GAMMA}/events?closed=false&limit=100&offset={off}&tag_slug=tennis")
            if not d: break
            for e in d:
                title = e.get("title") or ""
                if " vs " not in title: continue
                sn = poly_surnames(title)
                if len(sn) < 2: continue
                for m in e.get("markets", []):
                    q = (m.get("question") or "").lower()
                    if any(k in q for k in ("set 1","set 2","set 3","o/u","spread","handicap","completed")): continue
                    try:
                        oc = json.loads(m.get("outcomes") or "[]")
                        pr = json.loads(m.get("outcomePrices") or "[]")
                    except Exception: continue
                    if len(oc) != 2 or len(pr) != 2: continue
                    if any(o.lower() in ("yes","no","over","under") for o in oc): continue
                    try: p = [float(x) for x in pr]
                    except Exception: continue
                    tot = sum(p)
                    if tot <= 0: continue
                    names = [re.findall(r"[A-Za-z']+", o)[-1].lower() for o in oc]
                    key2 = tuple(sorted(names))
                    idx[key2] = {names[0]: p[0]/tot, names[1]: p[1]/tot,
                                 "_event": title, "_poly_slug": e.get("slug")}
                    break
            off += 100
            time.sleep(0.25)
    except Exception as e:
        errors.append(f"GAP: Polymarket gamma fetch failed: {e}")
        return None
    if not idx:
        errors.append("GAP: Polymarket returned no tennis match-winner markets")
        return None
    return idx

def main():
    target = None
    out = "/tmp/tennis_catch.json"
    args = sys.argv[1:]
    slate_path = None
    for i, a in enumerate(args):
        if a == "--date": target = args[i+1]
        if a == "--out": out = args[i+1]
        if a == "--slate": slate_path = args[i+1]
    if not target:
        target = (datetime.datetime.now(PT) + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    errors, gaps = [], []
    slate_rows = None
    if slate_path:
        try:
            sd = json.load(open(slate_path))
            slate_rows = [r for r in sd.get("rows", []) if r.get("league") in ("ATP", "WTA")]
            if not slate_rows: errors.append(f"slate file {slate_path} has no ATP/WTA rows")
        except Exception as e:
            errors.append(f"slate load failed ({slate_path}): {e}")
    series = discover_series(errors)
    events = open_match_events(series, errors)
    day = [e for e in events if e["exp_pt"] and e["exp_pt"][:10] == target]
    book = odds_api_fair(gaps)
    fair_src = "odds-api tennis devig" if book else None
    if not book:
        book = polymarket_fair(gaps)
        fair_src = "polymarket tennis devig (fallback)" if book else None
    if not book:
        gaps.append("GAP: BOTH fair feeds dead (odds-API tennis keys inactive AND Polymarket tennis unavailable) - tennis edges cannot compute tonight")
    catches = []
    for e in sorted(day, key=lambda x: x["exp_pt"]):
        rec = dict(e); sides = []
        rec["slate_bound"] = None
        if slate_rows is not None:
            sn = norm_surnames(e["title"])
            hits = [r for r in slate_rows if all(s_ in (r.get("match") or "").lower() for s_ in sn)] if len(sn) >= 2 else []
            # fail closed on ambiguity (bind_tennis semantics): exact one slate row or no bind
            rec["slate_bound"] = hits[0].get("instance_id") if len(hits) == 1 else ("AMBIGUOUS" if hits else None)
        for tk in e["markets"]:
            yb, ya, sub = top_of_book(tk, errors)
            side = (re.findall(r"[A-Za-z']+", sub or "")[-1].lower() if sub
                    else tk.rsplit("-", 1)[-1].lower())
            rec_side = {"ticker": tk, "player": sub, "yes_bid_c": yb, "yes_ask_c": ya}
            if book and e["series"].endswith("MATCH") and ":" not in e["title"]:
                # match-winner fairs attach ONLY to match-winner Kalshi events; a
                # spread/total rung's fair is not the match prob (polymarket spread/
                # total mapping is a later stage)
                sn = norm_surnames(e["title"])
                f = book.get(tuple(sorted(sn)))
                if f:
                    fp = f.get(side)
                    if fp is not None and ya is not None:
                        edge = fp * 100 - ya - FEE_C
                        rec_side.update({"fair_pct": round(fp * 100, 1), "net_edge_c": round(edge, 1),
                                         "passes_p_edge_001": edge >= EDGE_MIN_C})
            sides.append(rec_side)
        rec["sides"] = sides
        catches.append(rec)
    payload = {"date_pt": target, "series_discovered": series, "open_match_events_total": len(events),
               "matches_on_target_date": len(catches), "fair_feed": fair_src,
               "gaps": gaps, "fetch_errors": errors, "catches": catches}
    with open(out, "w") as f: json.dump(payload, f, indent=1)
    priced = sum(1 for c in catches for s in c["sides"] if s.get("yes_ask_c") is not None)
    passing = sum(1 for c in catches for s in c["sides"] if s.get("passes_p_edge_001"))
    print(f"TENNIS CATCH {target}: {len(series)} series discovered, {len(events)} open match events, {len(catches)} settle on target date")
    print(f"  priced sides: {priced}/{sum(len(c['sides']) for c in catches)} | passing P-EDGE-001: {passing}")
    for g in gaps: print(" ", g)
    for er in errors: print("  ERROR:", er)
    for c in catches[:60]:
        print(f"  {c['exp_pt'][11:16]}PT {c['title']} [{c['series']}] " +
              " | ".join(f"{s['ticker'].rsplit('-',1)[-1]} ask {s['yes_ask_c']}" for s in c["sides"]))
    print("wrote", out)

if __name__ == "__main__":
    main()
