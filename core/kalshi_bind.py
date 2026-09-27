"""Canonical Kalshi binding for Stage 0: binds on KALSHI'S OWN identifiers - the series
ticker's class token (GAME/SPREAD/TOTAL) and the event_ticker's exact date+team-abbr game code
(both orders, same rule as hunt_v2 bind_standard). Name substrings never bind. Fail closed."""
import json, os, re
def game_code(event_ticker):
    """'KXNCAAFGAME-26SEP27MIZZMSST' -> 'MIZZMSST' (date token + optional HHMM stripped)."""
    seg = event_ticker.split('-')[-1]
    seg = re.sub(r'^\d{2}[A-Z]{3}\d{2}', '', seg)
    return re.sub(r'^\d{4}', '', seg)
CLASS_TOKEN = {'ml': 'GAME', 'spread': 'SPREAD', 'total': 'TOTAL'}
def bind_event(feed_path, event_id, away_abbr, home_abbr, market_class, side):
    """Returns KalshiBinding built from the feed record, or None. Requires non-empty
    event_id and BOTH abbrs; the event_ticker game code must equal an exact abbr concat."""
    if not event_id or not away_abbr or not home_abbr:
        return None
    try:
        mkts = json.load(open(feed_path)); mtime = os.path.getmtime(feed_path)
    except Exception:
        return None
    ok_codes = {away_abbr.upper() + home_abbr.upper(), home_abbr.upper() + away_abbr.upper()}
    cls_tok = CLASS_TOKEN.get(market_class, market_class.upper())
    from core.binding import KalshiBinding
    for lg, lst in mkts.items():
        if not isinstance(lst, list): continue
        for m in lst:
            et = m.get('event_ticker', '')
            if cls_tok not in m.get('ticker', '').upper() and cls_tok not in et.upper(): continue
            if game_code(et) not in ok_codes: continue
            try:
                return KalshiBinding.from_feed_record(m, event_id, market_class, side, mtime)
            except ValueError:
                continue
    return None
