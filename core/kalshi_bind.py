"""Real Kalshi binding lookup for Stage 0 pipeline: searches the captured open-markets feed
for a market matching this game (team tokens) + market class, builds the binding from the
feed record via KalshiBinding.from_feed_record (fields from the record, freshness = feed mtime).
Returns None when nothing binds - fail closed, never fabricated."""
import json, os, re
def _toks(name):
    return [t for t in re.findall(r'[A-Za-z]+', (name or '').upper()) if len(t) >= 3]
def bind_from_feed(feed_path, away, home, event_id, market_class, side):
    """feed_path: captured Kalshi open-markets JSON {league: [market records]}.
    Matches when BOTH teams' tokens appear in the ticker+event_ticker+title, and the
    market class token matches (SPREAD/TOTAL/GAME for ml)."""
    try:
        mkts = json.load(open(feed_path))
        mtime = os.path.getmtime(feed_path)
    except Exception:
        return None
    cls_tok = {'ml': 'GAME', 'spread': 'SPREAD', 'total': 'TOTAL'}.get(market_class, market_class.upper())
    from core.binding import KalshiBinding
    def team_hit(name, hay):
        # a team matches when any >=4-letter name word appears in the market text
        # (tickers carry abbrs, titles carry names - word-level hit covers both)
        return any(w in hay for w in _toks(name) if len(w) >= 4)
    for lg, lst in mkts.items():
        if not isinstance(lst, list): continue
        for m in lst:
            hay = (m.get('ticker', '') + ' ' + m.get('event_ticker', '') + ' ' + (m.get('title') or '')).upper()
            if cls_tok not in hay: continue
            if not (team_hit(away, hay) and team_hit(home, hay)): continue
            try:
                return KalshiBinding.from_feed_record(m, event_id, market_class, side, mtime)
            except ValueError:
                continue
    return None
