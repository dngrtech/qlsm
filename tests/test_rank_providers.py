"""Adapter contract tests. Fixtures are transcribed from each provider's real
client, not guessed — see the spec's 'Provider API shapes'."""
from unittest.mock import MagicMock, patch

import pytest
import requests as requests_lib

from ui.rank_providers.elo_service import ThunderdomeEloProvider
from ui.rank_providers.qlstats import QlstatsProvider
from ui.rank_providers.slipgate import SlipgateProvider

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


# Transcribed from slipgate.py v1.10.1 fetch_ratings/:2496-2507 and
# rating_entry/:2542-2547. Both unranked shapes are represented.
SLIPGATE_BODY = {
    'players': [
        {'steam_id': '76561198000000001', 'display': '1650',
         'tier_name': 'Gold', 'provisional': False, 'found': True},
        {'steam_id': '76561198000000002', 'display': '1200 (Silver)',
         'tier_name': 'Silver', 'provisional': True, 'found': True},
        {'steam_id': '76561198000000003', 'display': None,
         'tier_name': None, 'provisional': False, 'found': True},
        {'steam_id': '76561198000000004', 'display': None,
         'tier_name': None, 'provisional': False, 'found': False},
    ],
}


def test_slipgate_parses_the_bulk_response():
    provider = SlipgateProvider('https://slipgate.gg/api/v1', 'sgs_tok', {})
    with patch('ui.rank_providers.slipgate.requests.post',
               return_value=_response(body=SLIPGATE_BODY)) as post:
        result = provider.fetch_ratings(
            ['76561198000000001', '76561198000000002',
             '76561198000000003', '76561198000000004'], 'ca')
    assert post.call_args[0][0] == 'https://slipgate.gg/api/v1/ratings/bulk'
    assert post.call_args[1]['json'] == {
        'steam_ids': ['76561198000000001', '76561198000000002',
                      '76561198000000003', '76561198000000004'],
        'game_type': 'ca',
    }
    # Both unranked shapes drop out: found=False AND found=True/display=None.
    assert set(result) == {'76561198000000001', '76561198000000002'}


def test_slipgate_returns_display_verbatim_and_never_parses_it():
    """display may be a label, not a number. Printing it whole is the contract."""
    provider = SlipgateProvider('https://slipgate.gg/api/v1', 'sgs_tok', {})
    with patch('ui.rank_providers.slipgate.requests.post',
               return_value=_response(body=SLIPGATE_BODY)):
        result = provider.fetch_ratings(['76561198000000002'], 'ca')
    assert result['76561198000000002']['display'] == '1200 (Silver)'
    assert result['76561198000000002']['rating'] is None
    assert result['76561198000000002']['provisional'] is True


def test_slipgate_sends_the_bearer_token():
    provider = SlipgateProvider('https://slipgate.gg/api/v1', 'sgs_tok', {})
    with patch('ui.rank_providers.slipgate.requests.post',
               return_value=_response(body={'players': []})) as post:
        provider.fetch_ratings(['76561198000000001'], 'ca')
    assert post.call_args[1]['headers']['Authorization'] == 'Bearer sgs_tok'


def test_slipgate_omits_the_header_when_there_is_no_token():
    provider = SlipgateProvider('https://slipgate.gg/api/v1', None, {})
    with patch('ui.rank_providers.slipgate.requests.post',
               return_value=_response(body={'players': []})) as post:
        provider.fetch_ratings(['76561198000000001'], 'ca')
    assert 'Authorization' not in post.call_args[1]['headers']


def test_slipgate_404_is_not_an_error():
    provider = SlipgateProvider('https://slipgate.gg/api/v1', 'sgs_tok', {})
    with patch('ui.rank_providers.slipgate.requests.post', return_value=_response(status=404)):
        assert provider.fetch_ratings(['76561198000000001'], 'ca') == {}


def test_slipgate_keys_are_strings():
    provider = SlipgateProvider('https://slipgate.gg/api/v1', 'sgs_tok', {})
    body = {'players': [{'steam_id': 76561198000000001, 'display': '1650',
                         'provisional': False, 'found': True}]}
    with patch('ui.rank_providers.slipgate.requests.post', return_value=_response(body=body)):
        result = provider.fetch_ratings(['76561198000000001'], 'ca')
    assert list(result) == ['76561198000000001']


@pytest.mark.parametrize('qlsm,expected', [
    # The four that differ. har->harvester and 1f->1flag are THE regression
    # guards for the silent-empty-column failure this feature exists to avoid.
    ('har', 'harvester'), ('dom', 'domination'), ('rr', 'redrover'),
    ('1f', '1flag'),
    # The seven that pass through unchanged.
    ('ca', 'ca'), ('ctf', 'ctf'), ('tdm', 'tdm'), ('ft', 'ft'),
    ('ffa', 'ffa'), ('duel', 'duel'), ('ad', 'ad'),
    # Unrated here. '1fctf' and 'ictf' are frontend guesses that no plugin
    # emits, so they are deliberately unmapped rather than aliased to 1flag.
    ('race', None), ('ob', None), ('1fctf', None), ('ictf', None), ('', None),
])
def test_slipgate_game_type_mapping(qlsm, expected):
    provider = SlipgateProvider('https://slipgate.gg/api/v1', 'sgs_tok', {})
    assert provider.map_game_type(qlsm) == expected


ELO_SERVICE_BODY = {
    '76561198000000001': {'name': 'a', 'mu': 25.1, 'sort_score': 1802.5,
                          'wins': 10, 'losses': 3},
    '76561198000000002': {'name': 'b', 'mu': 18.0, 'sort_score': None,
                          'wins': 0, 'losses': 0},
    '76561198000000003': None,
    # The `or` guard: 0 is falsy, so the plugin falls through to mu here.
    '76561198000000004': {'name': 'd', 'mu': 22.5, 'sort_score': 0,
                          'wins': 0, 'losses': 0},
}


def test_elo_service_prefers_sort_score_and_falls_back_to_mu():
    """There is NO 'rating' key on this endpoint. Reading one returns nothing
    for every player against a healthy service."""
    provider = ThunderdomeEloProvider('http://elo:5002', 'k', {})
    with patch('ui.rank_providers.elo_service.requests.get',
               return_value=_response(body=ELO_SERVICE_BODY)) as get:
        result = provider.fetch_ratings(
            ['76561198000000001', '76561198000000002', '76561198000000003'],
            'ffa_auto')
    assert get.call_args[1]['params'] == {
        'ids': '76561198000000001,76561198000000002,76561198000000003',
        'mode': 'ffa_auto',
    }
    assert result['76561198000000001']['rating'] == 1802.5
    assert result['76561198000000001']['display'] == '1802.5'
    # sort_score None -> falls back to mu
    assert result['76561198000000002']['rating'] == 18.0
    # a null entry yields no result at all
    assert '76561198000000003' not in result


def test_elo_service_treats_a_zero_sort_score_as_absent():
    """ranked.py:466 and :672 both read `int(d.get("sort_score") or d["mu"])`.
    Python's `or`, literally: 0 is falsy and mu wins. An `is None` check
    diverges exactly here and shows 0 for a player whose !rating shows 22."""
    provider = ThunderdomeEloProvider('http://elo:5002', 'k', {})
    with patch('ui.rank_providers.elo_service.requests.get',
               return_value=_response(body=ELO_SERVICE_BODY)):
        result = provider.fetch_ratings(['76561198000000004'], 'ffa_auto')
    assert result['76561198000000004']['rating'] == 22.5


def test_elo_service_sends_the_api_key():
    provider = ThunderdomeEloProvider('http://elo:5002', 'k', {})
    with patch('ui.rank_providers.elo_service.requests.get',
               return_value=_response(body={})) as get:
        provider.fetch_ratings(['76561198000000001'], 'ffa_auto')
    assert get.call_args[1]['headers']['X-API-Key'] == 'k'


def test_elo_service_404_is_not_an_error():
    provider = ThunderdomeEloProvider('http://elo:5002', 'k', {})
    with patch('ui.rank_providers.elo_service.requests.get', return_value=_response(status=404)):
        assert provider.fetch_ratings(['76561198000000001'], 'ffa_auto') == {}


def test_elo_service_network_error_is_an_empty_dict():
    provider = ThunderdomeEloProvider('http://elo:5002', 'k', {})
    with patch('ui.rank_providers.elo_service.requests.get',
               side_effect=requests_lib.RequestException('boom')):
        assert provider.fetch_ratings(['76561198000000001'], 'ffa_auto') == {}


def test_elo_service_keys_are_strings():
    provider = ThunderdomeEloProvider('http://elo:5002', 'k', {})
    body = {76561198000000001: {'mu': 25.0, 'sort_score': 1800}}
    with patch('ui.rank_providers.elo_service.requests.get', return_value=_response(body=body)):
        result = provider.fetch_ratings(['76561198000000001'], 'ffa_auto')
    assert list(result) == ['76561198000000001']


def test_elo_service_has_no_derivable_game_type():
    """mode is a service-specific pool name; it can only come from the override."""
    provider = ThunderdomeEloProvider('http://elo:5002', 'k', {})
    for code in ('ca', 'ffa', 'duel', 'har', ''):
        assert provider.map_game_type(code) is None
