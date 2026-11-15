"""Content-specific checks on the artifact accepted by both Pages providers."""
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import ROOT, build, verify


def draft_cards():
    drafts = ROOT / '.github/card-drafts/2026-11-13'
    def load(file):
        source = (drafts / file).read_text()
        return json.loads(re.search(r'var DATA=(.*?);\n', source)[1])
    nba = load('nba-nov13.js')
    return [*load('nhl-picks.js')['cards'], nba['wooder'], nba['nba']]


class PagesReleaseTests(unittest.TestCase):
    def test_real_release_preserves_current_site_and_historical_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / 'release'
            build(site)
            self.assertFalse((site / '.github').exists())
            self.assertFalse((site / 'nba-nov13.js').exists())
            for name in ['index.html', 'active-day.js', 'nhl-picks.js', 'history.json', 'record_done.json', '404.html']:
                self.assertEqual((site / name).read_bytes(), (ROOT / name).read_bytes(), name)
            paths = subprocess.check_output(['git', 'ls-files', '-z', 'slates'], cwd=ROOT).decode().split('\0')
            for name in filter(None, paths):
                self.assertEqual((site/name).read_bytes(), (ROOT/name).read_bytes(), name)

    def test_renamed_or_reordered_withdrawn_cards_are_detected(self):
        for card in draft_cards():
            for fmt in ('json', 'js'):
                with self.subTest(title=card.get('title'), form=fmt), tempfile.TemporaryDirectory() as tmp:
                    site = Path(tmp)
                    legs = copy.deepcopy(card['legs'][::-1])
                    for leg in legs:
                        leg['odds'] = 'different displayed price'
                    payload = json.dumps({'cards':[{'title':'Changed title', 'legs':legs}]})
                    (site / ('unrelated-name.'+fmt)).write_text(payload if fmt=='json' else 'var DATA = '+payload+';')
                    with self.assertRaisesRegex(ValueError, 'Withdrawn card selections'):
                        verify(site)

    def test_existing_historical_cards_remain_publishable(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            for name in ['nfl_20261108_archive.json','past_tickets.json','wooder_tickets.json']:
                (site / name).write_bytes((ROOT / 'slates' / name).read_bytes())
            before = {f.name: hashlib.sha256(f.read_bytes()).digest() for f in site.iterdir()}
            verify(site)
            self.assertEqual(before, {f.name: hashlib.sha256(f.read_bytes()).digest() for f in site.iterdir()})

    def test_direct_paths_and_loader_references_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            file = site / 'nba-nov13.js'
            file.write_text('')
            with self.assertRaisesRegex(ValueError, 'withdrawn path'):
                verify(site)
            file.unlink()
            (site/'index.html').write_text('<script src="nba-nov13.js?v=6"></script>')
            with self.assertRaisesRegex(ValueError, 'Withdrawn card reference'):
                verify(site)


if __name__ == '__main__':
    unittest.main()
