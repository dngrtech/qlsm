"""Adapter contract tests. Fixtures are transcribed from each provider's real
client, not guessed — see the spec's 'Provider API shapes'."""
from unittest.mock import MagicMock, patch

import pytest
import requests as requests_lib

from ui.rank_providers.qlstats import QlstatsProvider

QLSTATS_BODY = {
    'players': [
        {'steamid': '76561198000000001', 'ca': {'elo': 1650, 'games': 120}},
        {'steamid': '76561198000000002', 'ca': {'elo': 1200, 'games': 4}},
        {'steamid': '76561198000000003', 'ctf': {'elo': 1400, 'games': 9}},
        # balance.py:326-327's "the API has nothing" shape.
        {'steamid': '76561198000000004', 'ca': {'elo': 0, 'games': 0}},
    ],
    'untracked': ['76561198000000002'],
}


def _response(status=200, body=None):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = body if body is not None else {}
    return response


def test_qlstats_reads_elo_for_the_requested_game_type():
    provider = QlstatsProvider('http://qlstats.net', None, {'rating_system': 'elo'})
    with patch('ui.rank_providers.qlstats.requests.get',
               return_value=_response(body=QLSTATS_BODY)) as get:
        result = provider.fetch_ratings(
            ['76561198000000001', '76561198000000002', '76561198000000003',
             '76561198000000004'], 'ca')
    url = get.call_args[0][0]
    assert url == ('http://qlstats.net/elo/'
                   '76561198000000001+76561198000000002+76561198000000003'
                   '+76561198000000004')
    # Only the first: the second is untracked, the third has no 'ca' key, the
    # fourth is the zero/zero "nothing known" bucket.
    assert list(result) == ['76561198000000001']
    assert result['76561198000000001']['display'] == '1650'
    assert result['76561198000000001']['rating'] == 1650.0


def test_qlstats_omits_a_zero_elo_zero_games_bucket():
    """balance.py:326-327 reads elo==0 and games==0 as 'the API has nothing'
    and substitutes DEFAULT_RATING. QLSM does not invent 1500 for a read-only
    display — it omits the player so the cell shows a dash. Without this guard
    the cell renders a literal 0, which looks like a real rating."""
    provider = QlstatsProvider('http://qlstats.net', None, {})
    with patch('ui.rank_providers.qlstats.requests.get',
               return_value=_response(body=QLSTATS_BODY)):
        result = provider.fetch_ratings(['76561198000000004'], 'ca')
    assert '76561198000000004' not in result


def test_qlstats_honours_the_elo_b_rating_system():
    provider = QlstatsProvider('http://qlstats.net', None, {'rating_system': 'elo_b'})
    with patch('ui.rank_providers.qlstats.requests.get',
               return_value=_response(body={'players': []})) as get:
        provider.fetch_ratings(['76561198000000001'], 'ca')
    assert get.call_args[0][0].startswith('http://qlstats.net/elo_b/')


def test_qlstats_keys_are_strings():
    provider = QlstatsProvider('http://qlstats.net', None, {})
    with patch('ui.rank_providers.qlstats.requests.get',
               return_value=_response(body=QLSTATS_BODY)):
        result = provider.fetch_ratings(['76561198000000001'], 'ca')
    assert all(isinstance(k, str) for k in result)


def test_qlstats_network_error_is_an_empty_dict():
    provider = QlstatsProvider('http://qlstats.net', None, {})
    with patch('ui.rank_providers.qlstats.requests.get',
               side_effect=requests_lib.RequestException('boom')):
        assert provider.fetch_ratings(['76561198000000001'], 'ca') == {}


def test_qlstats_non_200_is_an_empty_dict():
    provider = QlstatsProvider('http://qlstats.net', None, {})
    with patch('ui.rank_providers.qlstats.requests.get', return_value=_response(status=503)):
        assert provider.fetch_ratings(['76561198000000001'], 'ca') == {}


@pytest.mark.parametrize('qlsm,expected', [
    ('ca', 'ca'), ('ctf', 'ctf'), ('tdm', 'tdm'), ('ft', 'ft'),
    ('ad', 'ad'), ('dom', 'dom'), ('duel', 'duel'), ('ffa', 'ffa'),
    ('har', None), ('rr', None), ('ob', None), ('race', None), ('', None),
])
def test_qlstats_game_type_mapping(qlsm, expected):
    provider = QlstatsProvider('http://qlstats.net', None, {})
    assert provider.map_game_type(qlsm) == expected
