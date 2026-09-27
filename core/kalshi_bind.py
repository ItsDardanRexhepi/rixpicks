"""Canonical Kalshi binding for Stage 0: binds on KALSHI'S OWN identifiers with full
verification - class token, event_ticker game code (exact abbr concat), DATE TOKEN vs the
game's commence (user-local day), outcome side suffix vs requested side, and line value
vs the flagged band. Multiple distinct candidates = fail closed, never first-match."""
import json, os, re
from datetime import datetime
from zoneinfo import ZoneInfo
ALIAS = {'CHW': 'CWS', 'ARI': 'AZ'}
def _canon(a): return ALIAS.get(a.upper(), a.upper())
def game_code(event_ticker):
    seg = event_ticker.split('-')[-1]
    seg = re.sub(r'^\d{2}[A-Z]{3}\d{2}', '', seg)
    return re.sub(r'^\d{4}', '', seg)
def date_token(event_ticker):
    seg = event_ticker.split('-')[-1]
    m = re.match(r'^(\d{2}[A-Z]{3}\d{2})', seg)
    return m.group(1) if m else None
def daycode(commence_utc):
    dt = datetime.fromisoformat(commence_utc.replace('Z', '+00:00')).astimezone(ZoneInfo('America/Los_Angeles'))
    return dt.strftime('%y%b%d').upper()
def outcome_suffix(ticker):
    """'...-MSST55' -> ('MSST', 5.5); '...-MSST' -> ('MSST', None); '...-O555' -> ('O', 55.5)."""
    suf = ticker.rsplit('-', 1)[-1].upper()
    m = re.match(r'^([A-Z]+?)(\d+)?$', suf)
    if not m: return suf, None
    team, digits = m.group(1), m.group(2)
    return team, (int(digits) / 10 if digits else None)
CLASS_TOKEN = {'ml': 'GAME', 'spread': 'SPREAD', 'total': 'TOTAL'}
def bind_event(feed_path, event_id, away_abbr, home_abbr, market_class, side,
               commence_utc=None, line_hint=None, line_tol=1.5, out_reason=None):
    """Fully verified canonical binding or None. Every check fails closed.
    side: home|away (ml/spread) or over|under (total). commence_utc required (date verify).
    line_hint: expected line magnitude (e.g. 5.5 for a -5.5 home spread, 55.5 total)."""
    why = out_reason if out_reason is not None else []
    if not event_id or not away_abbr or not home_abbr:
        why.append('missing event_id/abbrs'); return None
    if not commence_utc:
        why.append('no commence - cannot verify date token'); return None
    if market_class in ('spread', 'total') and line_hint is None:
        why.append(f'no line_hint for {market_class} - cannot verify line value, fail closed'); return None
    try:
        mkts = json.load(open(feed_path)); mtime = os.path.getmtime(feed_path)
    except Exception as e:
        why.append(f'feed unreadable: {e}'); return None
    want_day = daycode(commence_utc)
    ok_codes = {_canon(away_abbr) + _canon(home_abbr), _canon(home_abbr) + _canon(away_abbr)}
    cls_tok = CLASS_TOKEN.get(market_class, market_class.upper())
    cands = []
    for lg, lst in mkts.items():
        if not isinstance(lst, list): continue
        for m in lst:
            tk = m.get('ticker', ''); et = m.get('event_ticker', '')
            if cls_tok not in tk.upper() and cls_tok not in et.upper(): continue
            if game_code(et) not in ok_codes: continue
            if date_token(et) != want_day: continue                     # wrong-day market rejected
            team, line = outcome_suffix(tk)
            if market_class in ('ml', 'spread'):
                want_abbr = _canon(home_abbr if side == 'home' else away_abbr)
                if team != want_abbr: continue                          # wrong-side outcome rejected
            else:
                want = 'O' if side == 'over' else 'U'
                if not team.startswith(want): continue                  # over/under marker required
            if market_class in ('spread', 'total'):
                if line is None: continue                               # no numeric line in ticker = unverifiable, fail closed
                if abs(line - abs(line_hint)) > line_tol: continue      # wrong handicap/total rejected
            cands.append(m)
    if len(cands) != 1:
        why.append(f'{len(cands)} verified candidates - need exactly 1, fail closed'); return None
    from core.binding import KalshiBinding
    try:
        return KalshiBinding.from_feed_record(cands[0], event_id, market_class, side, mtime)
    except ValueError as e:
        why.append(str(e)); return None
