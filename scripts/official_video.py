#!/usr/bin/env python3
"""Official-video detector (owner directive 9:48: official YouTube embeds on Home, games show up right away).
Contract (main 9:53 accepted): publish slates/official_video.json with event IDs, verified official
rights-holder source, embed URL, embeddability, validity/status, freshness. FAIL-CLOSED: only validated
entries tied to current/upcoming games; no video shown for unverified streams. FREE sources only:
  1. resolve official channel handle -> channelId from the channel page itself (identity self-verified)
  2. channel RSS feed (no key) for recent uploads
  3. oEmbed probe (no key): 200 = embed allowed; 401/403/400 = not embeddable -> excluded
  4. optional YT_API_KEY upgrade path: videos.list part=status for the authoritative embeddable flag.
Channel allowlist is curated in official_video_channels.json (handle -> leagues); a video only counts
if its title matches a current/upcoming game from slates/live_games.json (both matchup sides).
"""
import json, os, re, sys, time, urllib.request, urllib.parse, datetime, xml.etree.ElementTree as ET

LIVE_GAMES = 'slates/live_games.json'
CHANNELS = 'slates/official_video_channels.json'
OUT = 'slates/official_video.json'
GAME_WINDOW_H = 36
UA = {'User-Agent': 'rixpicks-official-video/1.0'}
YT_KEY = os.environ.get('YT_API_KEY', '')

def get(url, timeout=20):
    r = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.status, resp.read()

def resolve_channel_id(handle):
    """Handle page HTML carries the canonical channelId + verified handle - identity from source."""
    try:
        status, body = get(f'https://www.youtube.com/@{handle}')
        html = body.decode('utf-8', 'replace')
        m = re.search(r'"externalId":"(UC[^"]+)"', html) or re.search(r'channel_id=(UC[^"&]+)', html)
        title = re.search(r'<title>([^<]+)</title>', html)
        return (m.group(1) if m else None, (title.group(1).strip() if title else ''))
    except Exception as e:
        print(f'resolve FAIL @{handle}: {e}')
        return None, ''

def channel_uploads(cid):
    try:
        status, body = get(f'https://www.youtube.com/feeds/videos.xml?channel_id={cid}')
        root = ET.fromstring(body)
        ns = {'a': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}
        out = []
        for e in root.findall('a:entry', ns):
            out.append({'video_id': e.find('yt:videoId', ns).text,
                        'title': e.find('a:title', ns).text,
                        'published': e.find('a:published', ns).text,
                        'channel_title': (root.find('a:title', ns).text if root.find('a:title', ns) is not None else '')})
        return out
    except Exception as e:
        print(f'rss FAIL {cid}: {e}')
        return []

def oembed_ok(vid):
    try:
        url = 'https://www.youtube.com/oembed?' + urllib.parse.urlencode({'url': f'https://www.youtube.com/watch?v={vid}', 'format': 'json'})
        status, _ = get(url)
        return status == 200
    except urllib.error.HTTPError:
        return False
    except Exception:
        return False

def api_embeddable(vids):
    """Authoritative batch check when YT_API_KEY exists (1 unit per 50 ids)."""
    if not YT_KEY or not vids:
        return {}
    try:
        url = 'https://www.googleapis.com/youtube/v3/videos?' + urllib.parse.urlencode({
            'part': 'status', 'id': ','.join(vids[:50]), 'key': YT_KEY})
        status, body = get(url)
        data = json.loads(body)
        return {it['id']: bool(it.get('status', {}).get('embeddable')) for it in data.get('items', [])}
    except Exception as e:
        print(f'yt api FAIL: {e}')
        return {}


# stream-vs-clip gate (fail-closed): a candidate only counts as a WATCHABLE GAME STREAM when the
# title asserts live/full-game AND carries no clip marker. Highlights/recaps are NOT streams.
NEG = ('highlight', 'recap', 'best plays', 'top plays', 'condensed', 'mic\'d', 'micd',
       'every play', 'best of', 'week in review', 'preview', 'prediction', 'reaction')
POS = ('live', 'full game', 'full match', 'watch along', 'watchalong', 'game day live', 'gameday live')
def is_stream_title(title):
    t = str(title).lower()
    if any(n in t for n in NEG):
        return False
    return any(p in t for p in POS)

def nrm(s):
    return re.sub(r'[^a-z0-9]+', '', str(s).lower())

def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    games = []
    try:
        lg = json.load(open(LIVE_GAMES))
        for league in lg.get('leagues', []):
            for g in league.get('games', []):
                try:
                    ct = datetime.datetime.strptime(g.get('commence', ''), '%Y-%m-%dT%H:%MZ').replace(tzinfo=datetime.timezone.utc)
                except Exception:
                    continue
                if abs((ct - now).total_seconds()) > GAME_WINDOW_H * 3600 or g.get('status') not in ('pre', 'in'):
                    continue
                sides = [p.strip() for p in str(g.get('matchup', '')).split(' @ ') if p.strip()]
                if len(sides) == 2:
                    games.append({'event_id': g.get('espn_event_id'), 'league': league.get('league'),
                                  'matchup': g.get('matchup'), 'sides': sides, 'commence': g.get('commence')})
    except Exception as e:
        print(f'{LIVE_GAMES} unreadable: {e}')
    try:
        chan_cfg = json.load(open(CHANNELS)).get('channels', [])
    except Exception as e:
        print(f'{CHANNELS} unreadable: {e} - fail closed, empty feed')
        chan_cfg = []
    candidates = []
    for ch in chan_cfg:
        cid, ctitle = resolve_channel_id(ch.get('handle', ''))
        if not cid:
            continue
        for v in channel_uploads(cid)[:10]:
            v['channel_id'] = cid
            v['handle'] = ch.get('handle')
            v['leagues'] = ch.get('leagues', [])
            candidates.append(v)
        time.sleep(0.3)
    # authoritative embeddable pass when key exists
    flags = api_embeddable([v['video_id'] for v in candidates])
    items = []
    for v in candidates:
        t = nrm(v['title'])
        for g in games:
            if g['league'] not in v['leagues']:
                continue
            if not is_stream_title(v['title']):
                continue
            if not all(nrm(s) in t for s in g['sides']):
                continue
            ok = flags.get(v['video_id']) if flags else oembed_ok(v['video_id'])
            if not ok:
                print(f"not embeddable, excluded: {v['video_id']} {v['title'][:60]}")
                continue
            items.append({'event_id': g['event_id'], 'league': g['league'], 'matchup': g['matchup'],
                          'video_id': v['video_id'], 'title': v['title'],
                          'channel_handle': v['handle'], 'channel_id': v['channel_id'],
                          'channel_title': v.get('channel_title', ''),
                          'embed_url': f"https://www.youtube.com/embed/{v['video_id']}",
                          'watch_url': f"https://www.youtube.com/watch?v={v['video_id']}",
                          'published': v['published'], 'status': 'embeddable-official',
                          'checked_at': now.isoformat(timespec='seconds')})
    out = {'version': 1, 'generated_at': now.isoformat(timespec='seconds'),
           'source': 'youtube-official-channels', 'fail_closed': True, 'items': items}
    json.dump(out, open(OUT, 'w'), indent=1)
    print(f'official_video: {len(games)} live/upcoming games, {len(candidates)} uploads scanned, {len(items)} validated embeds -> {OUT}')

if __name__ == '__main__':
    main()
