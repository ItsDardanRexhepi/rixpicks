#!/usr/bin/env python3
"""bridge_worker_news.py - Lane 3 Option A (main 9/30 4:04 PM PT).
Copy the Cloudflare worker's news feed into slates/news.json so the X/NIM chain and the live
page (which still reads slates/) stay generation-matched while GH news-refresh is off.
Fail-safe: any fetch/validation problem keeps the existing file and exits 0 (chain continues on
the last good news, exactly as when news-refresh skipped a cycle)."""
import json, sys, time, urllib.request
from datetime import datetime, timezone

URL = 'https://rixpicks-feeds.itsdardanr.workers.dev/feeds/news.json'
DST = 'slates/news.json'
MAX_AGE_MIN = 25          # worker cron is */5; older than this = worker lane is stuck, do not publish
MIN_VOLUME_FRAC = 0.6     # vs existing file (outage guard)

def ts(s):
    try:
        d = datetime.fromisoformat(str(s).replace('Z', '+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def count(d):
    return sum(len(v) for v in (d.get('leagues') or {}).values() if isinstance(v, list))

def main():
    raw = None
    for i in range(3):
        try:
            req = urllib.request.Request(URL + '?cb=%d' % time.time(), headers={'User-Agent': 'RixPicks-bridge/1.0'})
            raw = urllib.request.urlopen(req, timeout=20).read()
            break
        except Exception as e:
            print('WARN fetch try %d: %s' % (i + 1, str(e)[:100]))
            time.sleep(3)
    if raw is None:
        print('BRIDGE skip: worker unreachable, keeping existing news.json'); return 0
    try:
        new = json.loads(raw)
    except Exception:
        print('BRIDGE skip: worker body not JSON'); return 0
    try:
        old = json.load(open(DST))
    except Exception:
        old = None
    g = ts(new.get('generated_at')) if isinstance(new, dict) else None
    if not g or not isinstance(new.get('leagues'), dict) or 'latest' not in new:
        print('BRIDGE skip: schema check failed'); return 0
    age = (datetime.now(timezone.utc) - g).total_seconds() / 60
    if age > MAX_AGE_MIN:
        print('BRIDGE skip: worker news %.1f min old (> %d)' % (age, MAX_AGE_MIN)); return 0
    if new.get('degraded_sources'):
        print('BRIDGE skip: worker degraded_sources=%s' % new['degraded_sources']); return 0
    if old:
        og = ts(old.get('generated_at'))
        if og and g <= og:
            print('BRIDGE noop: worker generated_at %s not newer than %s' % (new['generated_at'], old['generated_at'])); return 0
        if count(old) and count(new) < MIN_VOLUME_FRAC * count(old):
            print('BRIDGE skip: volume %d < %.0f%% of existing %d' % (count(new), MIN_VOLUME_FRAC * 100, count(old))); return 0
    with open(DST, 'w') as f:
        json.dump(new, f, indent=1)
    print('BRIDGE wrote %s (generated_at=%s, %d items, age %.1f min)' % (DST, new['generated_at'], count(new), age))
    return 0

sys.exit(main())
