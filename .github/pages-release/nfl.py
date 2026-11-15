"""Recognize Julian's withdrawn November 15 card from its described selections."""
from datetime import date, datetime
import re
import unicodedata
from zoneinfo import ZoneInfo


PACIFIC = ZoneInfo('America/Los_Angeles')


def normalized(value):
    value = unicodedata.normalize('NFKD', str(value)).casefold()
    return ''.join(char for char in value if char.isalnum())


def day(value):
    value = str(value or '').strip()
    try:
        if 'T' in value:
            stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if stamp.tzinfo:
                return stamp.astimezone(PACIFIC).date().isoformat()
        return date.fromisoformat(value).isoformat()
    except ValueError:
        pass
    for fmt in ('%b %d, %Y', '%B %d, %Y', '%a %b %d, %Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    for fmt in ('%b %d', '%B %d', '%a %b %d'):
        try:
            return datetime.strptime(value + ' 2000', fmt + ' %Y').strftime('%m-%d')
        except ValueError:
            continue
    return None


TEAM_NAMES = {
    'sanfrancisco49ers':'sf', 'dallascowboys':'dal', 'losangelesrams':'lar',
    'arizonacardinals':'ari', 'seattleseahawks':'sea', 'lasvegasraiders':'lv',
}
ONE_TD = {'anytimetd','anytimetdscorer','anytimetouchdown','anytimetouchdownscorer','1td','1tds','1touchdown','1touchdowns',
          '1ormoretds','1ormoretouchdowns','atleastonetouchdown','atleast1touchdown','toscoreatouchdown'}


def matchup(leg):
    parts = re.split(r'\s*(?:@|\bat\b|\bvs\.?\b)\s*', str(leg.get('matchup') or ''), flags=re.I)
    if len(parts) != 2:
        source = leg.get('x') if isinstance(leg.get('x'), dict) else leg
        parts = [source.get('away', ''), source.get('home', '')]
    teams = [TEAM_NAMES.get(normalized(team), normalized(team)) for team in parts]
    return '@'.join(teams) if all(teams) else None


def matches_withdrawn_nfl(card, rule):
    legs = next((card[k] for k in ('legs','picks','selections') if isinstance(card.get(k), list)), [])
    if len(legs) != 7 or not all(isinstance(leg, dict) for leg in legs):
        return False
    expected = {normalized(p): game.casefold() for game, players in rule['players_by_matchup'].items() for p in players}
    names = [normalized(leg.get('player') or leg.get('name') or '') for leg in legs]
    if set(names) != set(expected):
        return False
    for player, leg in zip(names, legs):
        league = normalized(leg.get('league') or card.get('league') or card.get('sport') or '')
        if league and league not in {'nfl','football','americanfootball'}:
            return False
        event_day = day(leg.get('commence')) or day(leg.get('date')) or day(card.get('date'))
        if event_day and event_day not in {rule['event_date'], rule['event_date'][5:]}:
            return False
        game = matchup(leg)
        if game and game != expected[player]:
            return False
        label = str(leg.get('market') or leg.get('stat') or card.get('market') or '')
        market = normalized(re.split(r'\s*[·|]\s*', label, maxsplit=1)[0])
        if market and market not in ONE_TD and market not in {'td','tds','touchdown','touchdowns'}:
            return False
        threshold = leg.get('line',leg.get('threshold'))
        if threshold is not None and not re.fullmatch(
            r'(?:1(?:\.0+)?\+?(?:\s*(?:tds?|touchdowns?))?|(?:o(?:ver)?\s*)?0?\.50*)',
            str(threshold).strip(), re.I,
        ):
            return False
    # No issuer ID exists. Incomplete labels for exactly these same seven people
    # cannot establish a different card. Other seven-leg NFL cards still pass.
    return True
