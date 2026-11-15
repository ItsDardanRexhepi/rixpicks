"""A mismatched market or missing Yes outcome must preserve the last recorded observation."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import futures_quotes as feed


def market(question, outcomes, prices):
    return {'question': question, 'outcomes': outcomes, 'outcomePrices': prices}


def refresh(markets):
    saved = {'url': 'https://example.invalid/event/example', 'verified': True,
             'market_label': 'Example City', 'cents': 20, 'quoted_at': '2025-03-01T12:10:00Z'}
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'futures.json'
        path.write_text(json.dumps([{'polymarket_com': saved}]))
        with patch.object(feed, 'get', return_value=[{'markets': markets}]), patch.object(feed.time, 'sleep'), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            feed.main(path, write=True)
        return saved, json.loads(path.read_text())[0]['polymarket_com']


question = 'Will Example City take the division?'
valid = market(question, '["No","Yes"]', '["0.35","0.65"]')
saved, result = refresh([valid])
assert result['cents'] == 65 and result['quoted_at'] != saved['quoted_at']
assert feed.matching_market([valid], question.upper(), None) is valid
assert feed.yes_price_cents(market(question, [' YES ', 'no'], ['0.09', '0.91'])) == 9
assert feed.matching_market([valid], 'Will Example City win the final?', 'Example City') is None
for cases in [
    [valid, market('Will Example City win the title?', valid['outcomes'], valid['outcomePrices'])],
    [market(question, ['Over', 'Under'], [0.7, 0.3])],
    [market(question, ['Yes', 'Yes'], [0.3, 0.7])],
    [market(question, ['No', 'Yes'], [0.3])],
    [market(question, ['No', 'Yes'], [0.3, True])],
    [market(question, ['Yes', 'No'], ['NaN', 0.4])],
    [market(question, ['Yes', 'No'], [0.999, 0.001])],
    [market(question, '[broken', '[]')],
]:
    previous, result = refresh(cases)
    assert result == previous, 'an unverified observation replaced the saved quote'
print('Verified exact, unique, reversed-order, missing, malformed and ambiguous quote observations offline')
