"""Build a Pages artifact from one checked-out commit, keeping editorial drafts private."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
POLICY = HERE / 'withdrawn.json'
TEXT = {'.html', '.htm', '.js', '.mjs', '.json', '.jsonl', '.css', '.txt', '.csv', '.md', '.xml'}


def selection(leg):
    # Game, player, market, side and line identify each selection. Display price and order can change.
    if leg.get('game_id') and leg.get('player_id'):
        fields = ('game_id', 'player_id', 'market', 'line', 'dir')
        return {key: leg[key] for key in fields if key in leg}
    if isinstance(leg.get('x'), dict):
        fields = ('event', 'league', 'athlete', 'team', 'keys', 'doubleDouble', 'spreadTeam', 'spreadLine', 'totalPoints')
        return {'event_selection': {key: leg['x'][key] for key in fields if key in leg['x']},
                'market': leg.get('market'), 'line': leg.get('line'), 'dir': leg.get('dir')}
    return leg


def legs_hash(legs):
    if not isinstance(legs, list) or not legs or not all(isinstance(v, dict) for v in legs):
        return None
    values = sorted(json.dumps(selection(v), sort_keys=True, separators=(',', ':')) for v in legs)
    return hashlib.sha256(json.dumps(values, separators=(',', ':')).encode()).hexdigest()


def check_cards(value, blocked, name):
    if isinstance(value, dict):
        if legs_hash(value.get('legs')) in blocked:
            raise ValueError(f'Withdrawn card selections found in {name}')
        for entry in value.values():
            check_cards(entry, blocked, name)
    elif isinstance(value, list):
        for entry in value:
            check_cards(entry, blocked, name)


def verify(directory):
    rules = json.loads(POLICY.read_text())
    markers = [v.casefold().encode() for v in rules['markers']]
    blocked = set(rules['selection_hashes'])
    for file in directory.rglob('*'):
        if file.is_symlink():
            raise ValueError(f'Unexpected symlink in Pages artifact: {file.relative_to(directory)}')
        name = file.relative_to(directory).as_posix()
        if file.name.casefold() in rules['filenames'] or name.split('/')[0] in {'.github', '.git'}:
            raise ValueError(f'Private or withdrawn path in Pages artifact: {name}')
        if not file.is_file() or file.suffix.casefold() not in TEXT:
            continue
        raw = file.read_bytes()
        lower = raw.lower()
        if any(marker in lower for marker in markers):
            raise ValueError(f'Withdrawn card reference in {name}')
        if b'"legs"' not in lower:
            continue
        if file.suffix.lower() in {'.json', '.jsonl'}:
            entries = raw.splitlines() if file.suffix.lower() == '.jsonl' else [raw]
            for entry in entries:
                if entry.strip():
                    check_cards(json.loads(entry), blocked, name)
        elif file.suffix.lower() in {'.js', '.mjs', '.html', '.htm'}:
            # Existing NBA/NHL loaders assign a JSON data object to DATA.
            source = raw.decode('utf-8', errors='replace')
            for match in re.finditer(r'\bDATA\s*=\s*(?=[{\[])', source):
                try:
                    value, _ = json.JSONDecoder().raw_decode(source, match.end())
                except ValueError:
                    continue
                check_cards(value, blocked, name)


def build(output):
    output = output.resolve()
    if output.exists():
        raise ValueError(f'Choose a new artifact directory: {output}')
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='rixpicks-package-') as temp:
        archive = Path(temp) / 'source.tar'
        staged = Path(temp) / 'site'
        staged.mkdir()
        subprocess.run(['git', 'archive', '--format=tar', '--output', str(archive), 'HEAD', '--', '.',
                        ':(exclude).github'], cwd=ROOT, check=True)
        with tarfile.open(archive) as tar:
            tar.extractall(staged, filter='data')
        verify(staged)
        staged.rename(output)


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('directory', type=Path)
    cli.add_argument('--verify', action='store_true', help='check a materialized deploy directory')
    args = cli.parse_args()
    if args.verify:
        if not (args.directory / 'index.html').is_file():
            cli.error('expected a site directory containing index.html')
        verify(args.directory)
    else:
        build(args.directory)
