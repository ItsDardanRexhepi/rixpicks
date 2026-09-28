"""ESPN injuries feeds (core level, 9/27 - his 4:40 PM ask 'If ESPN offers an API, connect to it').
ESPN has no official PUBLIC/self-service API (parent wording correction 9/27 7:07 PM PT: keyed
syndication feeds exist for licensed vendors - not pursued). The site.api + sports.core.api v2
JSON endpoints are the practical de facto feed (grounded live 9/27 7:00 PM PT). What this adds beyond the scoreboard/summary
chain: the league-wide injuries feed (site.api) and the per-team core injuries endpoint
(sports.core.api v2) as structured second sources for injury double-sourcing (J-115 lane).
Mozilla UA 403s from this IP - python-urllib passes (learning #9). Fail-loud: fetch errors
raise, never return partial silence."""
import json, urllib.request
UA = {'User-Agent': 'python-urllib/3.10'}

def _get(url, timeout=30):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read())

def league_injuries(league_path):
    """League-wide feed (site.api). league_path e.g. 'football/nfl'.
    Returns {team_displayName: [{name, status, comment}]} - big payload (NFL ~9MB), callers filter."""
    d = _get(f'https://site.api.espn.com/apis/site/v2/sports/{league_path}/injuries')
    out = {}
    for team in d.get('injuries', []):
        rows = []
        for inj in team.get('injuries', []):
            a = inj.get('athlete') or {}
            nm = a.get('displayName')
            if nm:
                rows.append({'name': nm, 'status': inj.get('status'),
                             'comment': inj.get('shortComment') or ''})
        if team.get('displayName'):
            out[team['displayName']] = rows
    return out

def team_injuries(league, team_id):
    """Per-team core feed (sports.core.api v2). league e.g. 'nfl'; team_id = ESPN numeric id.
    Returns [{name, status, comment}]. Raises on fetch failure (fail-loud)."""
    sport = {'nfl': 'football', 'mlb': 'baseball', 'nba': 'basketball',
             'wnba': 'basketball', 'nhl': 'hockey', 'mls': 'soccer'}.get(league, league)
    d = _get(f'https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/teams/{team_id}/injuries')
    out = []
    for item in d.get('items', []):
        # items are refs; the feed inlines athlete/status when available
        a = item.get('athlete') or {}
        out.append({'name': a.get('displayName') or item.get('displayName'),
                    'status': item.get('status'), 'comment': item.get('shortComment') or ''})
    return out
