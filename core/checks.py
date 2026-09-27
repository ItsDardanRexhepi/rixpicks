"""J-119/J-120 2-full-check bar as EVIDENCE OBJECTS with a real schema:
- kind: book_convergence | availability (both required, distinct)
- sources: >=2 entries, each {id, artifact_path, snapshot_ts} - artifact is a captured,
  non-empty file from that source; snapshot_ts within MAX_SNAPSHOT_AGE_S and not future-dated
- event_id + market_class bind the check to this exact game+market
- the two checks' source ids must be DISJOINT (no label reuse across checks)
Stale snapshots, missing artifacts, future timestamps, and source-label reuse all reject."""
import json, os
from dataclasses import dataclass, field
from datetime import datetime, timezone
REQUIRED = ('book_convergence', 'availability')
MAX_SNAPSHOT_AGE_S = 3600
MAX_FUTURE_SKEW_S = 300
def _ts(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00'))
@dataclass
class CheckEvidence:
    kind: str
    sources: list          # [{'id','artifact_path','snapshot_ts'}, ...]
    detail: str
    event_id: str
    market_class: str
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    def validate(self, now=None):
        now = now or datetime.now(timezone.utc)
        if self.kind not in REQUIRED: return False, f'unknown check kind {self.kind}'
        if not self.event_id or not self.market_class:
            return False, 'check not bound to an event+market'
        ids = [s.get('id') for s in self.sources]
        if len(set(ids)) < 2: return False, f'{self.kind}: need >=2 distinct source ids, got {ids}'
        for s in self.sources:
            p = s.get('artifact_path')
            if not p or not os.path.isfile(p) or os.path.getsize(p) == 0:
                return False, f"{self.kind}: source {s.get('id')} has no captured artifact"
            try: snap = _ts(s['snapshot_ts'])
            except Exception: return False, f"{self.kind}: source {s.get('id')} bad snapshot_ts"
            age = (now - snap).total_seconds()
            if age > MAX_SNAPSHOT_AGE_S:
                return False, f"{self.kind}: source {s.get('id')} snapshot stale ({age:.0f}s > {MAX_SNAPSHOT_AGE_S}s)"
            if age < -MAX_FUTURE_SKEW_S:
                return False, f"{self.kind}: source {s.get('id')} snapshot future-dated"
        if not self.detail or len(self.detail) < 10:
            return False, f'{self.kind}: detail is not substantive'
        return True, 'ok'
def two_checks(c1, c2, now=None):
    for c in (c1, c2):
        ok, why = c.validate(now)
        if not ok: return False, why
    if {c1.kind, c2.kind} != set(REQUIRED):
        return False, f'need exactly {REQUIRED}, got ({c1.kind}, {c2.kind})'
    if c1.event_id != c2.event_id or c1.market_class != c2.market_class:
        return False, 'checks bound to different events/markets (conflicting identity)'
    ids1 = {s['id'] for s in c1.sources}; ids2 = {s['id'] for s in c2.sources}
    if ids1 & ids2:
        return False, f'source-label reuse across checks: {ids1 & ids2}'
    return True, 'ok'
