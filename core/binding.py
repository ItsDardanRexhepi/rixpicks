"""Kalshi market binding for the J-122 card gate. A binding is only real when it proves
same event + same market class + same side, wagerable status, a live ask, and quote
freshness in BOTH directions (stale OR future-dated beyond skew rejects).
from_feed_record builds bindings ONLY from captured feed data - never caller-asserted."""
from dataclasses import dataclass
from datetime import datetime, timezone
WAGERABLE = ('open', 'active')   # Kalshi live state = 'active'
@dataclass
class KalshiBinding:
    ticker: str
    event_id: str
    market_class: str
    side: str
    status: str
    ask_c: float
    quote_ts: str
    @classmethod
    def from_feed_record(cls, record, event_id, market_class, side, feed_mtime):
        """Build from a real Kalshi feed record. Missing fields raise (fail closed)."""
        t = record.get('ticker')
        if not t: raise ValueError('feed record missing ticker')
        st = record.get('status')
        if not st: raise ValueError('feed record missing status')
        ask = record.get('yes_ask')
        if ask is None:
            d = record.get('yes_ask_dollars')
            ask = float(d) * 100 if d is not None else None
        if ask is None: raise ValueError('feed record missing ask')
        qts = datetime.fromtimestamp(feed_mtime, timezone.utc).isoformat()
        return cls(t, event_id, market_class, side, st, ask, qts)
    def validate(self, expected_event, expected_class, expected_side, now=None,
                 max_age_s=300, max_future_skew_s=300):
        now = now or datetime.now(timezone.utc)
        if not self.ticker: return False, 'no ticker'
        if self.event_id != expected_event: return False, f'cross-event binding ({self.event_id} != {expected_event})'
        if self.market_class != expected_class: return False, f'class mismatch ({self.market_class} != {expected_class})'
        if self.side != expected_side: return False, f'side mismatch ({self.side} != {expected_side})'
        if self.status not in WAGERABLE: return False, f'market not wagerable (status {self.status})'
        if not (0 < self.ask_c < 100): return False, f'ask {self.ask_c} not a live price'
        try: age = (now - datetime.fromisoformat(self.quote_ts.replace('Z', '+00:00'))).total_seconds()
        except Exception: return False, 'unparseable quote_ts'
        if age > max_age_s: return False, f'stale quote ({age:.0f}s > {max_age_s}s)'
        if age < -max_future_skew_s: return False, f'future-dated quote ({-age:.0f}s ahead > {max_future_skew_s}s skew)'
        return True, 'bound+live'
