"""RankService: id validation, game-type resolution, caching, Redis guard."""
import json
from unittest.mock import MagicMock, patch

import pytest

from ui import db
from ui.models import Host, QLInstance, RankProviderConfig
from ui.rank_providers.service import RankService

VALID_A = '76561198000000001'
VALID_B = '76561198000000002'


def _seed(provider_type='slipgate', game_type=None, enabled=True,
          base_url='https://slipgate.gg/api/v1', extra=None):
    host = Host(name='host-a', ip_address='10.0.0.1', ssh_user='root',
                ssh_key_path='/keys/id', ssh_port=22, provider='vultr')
    db.session.add(host)
    db.session.flush()
    instance = QLInstance(name='inst-a', port=27960, hostname='hn', host_id=host.id)
    db.session.add(instance)
    db.session.flush()
    db.session.add(RankProviderConfig(
        instance_id=instance.id, provider_type=provider_type,
        base_url=base_url, api_key='tok', game_type=game_type,
        extra=json.dumps(extra or {}), enabled=enabled,
    ))
    db.session.commit()
    return instance.id


def _redis(status_gametype='ca', cached=None):
    client = MagicMock()
    client.get.side_effect = lambda key: (
        json.dumps({'gametype': status_gametype}) if key.startswith('server:status:')
        else cached
    )
    client.scan_iter.return_value = []
    return client


# --- steam_ids validation -------------------------------------------------

def test_invalid_ids_are_dropped_silently(app):
    with app.app_context():
        instance_id = _seed()
        service = RankService(_redis())
        with patch.object(service, '_fetch_from_provider', return_value={}) as fetch:
            service.get_ratings(instance_id, ['../../admin', '12345', VALID_A, 'abc'])
        assert fetch.call_args[0][1] == [VALID_A]


def test_ids_are_deduplicated_and_capped(app):
    with app.app_context():
        instance_id = _seed()
        service = RankService(_redis())
        many = [f'7656119{i:010d}' for i in range(100)] + [VALID_A, VALID_A]
        with patch.object(service, '_fetch_from_provider', return_value={}) as fetch:
            service.get_ratings(instance_id, many)
        sent = fetch.call_args[0][1]
        assert len(sent) == 64
        assert len(set(sent)) == 64


def test_no_valid_ids_short_circuits(app):
    with app.app_context():
        instance_id = _seed()
        service = RankService(_redis())
        with patch.object(service, '_fetch_from_provider') as fetch:
            data, configured = service.get_ratings(instance_id, ['nope', '123'])
        assert data == {}
        assert configured is True
        fetch.assert_not_called()


# --- configured flag ------------------------------------------------------

def test_unconfigured_instance_reports_not_configured(app):
    with app.app_context():
        host = Host(name='h', ip_address='1.1.1.1', ssh_user='root',
                    ssh_key_path='/k', ssh_port=22, provider='vultr')
        db.session.add(host)
        db.session.flush()
        instance = QLInstance(name='i', port=27961, hostname='hn', host_id=host.id)
        db.session.add(instance)
        db.session.commit()
        data, configured = RankService(_redis()).get_ratings(instance.id, [VALID_A])
    assert data == {}
    assert configured is False


def test_disabled_config_reports_not_configured_and_never_calls_the_adapter(app):
    with app.app_context():
        instance_id = _seed(enabled=False)
        service = RankService(_redis())
        with patch.object(service, '_fetch_from_provider') as fetch:
            data, configured = service.get_ratings(instance_id, [VALID_A])
        assert (data, configured) == ({}, False)
        fetch.assert_not_called()


def test_config_missing_base_url_reports_not_configured(app):
    with app.app_context():
        instance_id = _seed(base_url=None)
        data, configured = RankService(_redis()).get_ratings(instance_id, [VALID_A])
    assert (data, configured) == ({}, False)


def test_a_failing_provider_is_still_configured(app):
    """configured is about configuration; failure is a different axis."""
    with app.app_context():
        instance_id = _seed()
        service = RankService(_redis())
        with patch.object(service, '_fetch_from_provider', return_value={}):
            data, configured = service.get_ratings(instance_id, [VALID_A])
        assert (data, configured) == ({}, True)


# --- game type resolution -------------------------------------------------

def test_game_type_is_derived_from_live_status(app):
    with app.app_context():
        instance_id = _seed(provider_type='slipgate')
        service = RankService(_redis(status_gametype='har'))
        with patch('ui.rank_providers.slipgate.requests.post') as post:
            post.return_value = MagicMock(status_code=200,
                                          json=MagicMock(return_value={'players': []}))
            service.get_ratings(instance_id, [VALID_A])
        # 'har' must be translated to Slipgate's 'harvester'.
        assert post.call_args[1]['json']['game_type'] == 'harvester'


def test_an_explicit_game_type_overrides_derivation(app):
    with app.app_context():
        instance_id = _seed(provider_type='elo_service', game_type='ffa_auto',
                            base_url='http://elo:5002')
        service = RankService(_redis(status_gametype='ca'))
        with patch('ui.rank_providers.elo_service.requests.get') as get:
            get.return_value = MagicMock(status_code=200, json=MagicMock(return_value={}))
            service.get_ratings(instance_id, [VALID_A])
        assert get.call_args[1]['params']['mode'] == 'ffa_auto'


def test_an_unrated_mode_makes_no_http_call_at_all(app):
    with app.app_context():
        instance_id = _seed(provider_type='slipgate')
        service = RankService(_redis(status_gametype='race'))
        with patch('ui.rank_providers.slipgate.requests.post') as post:
            data, configured = service.get_ratings(instance_id, [VALID_A])
        post.assert_not_called()
        assert (data, configured) == ({}, True)


# --- caching --------------------------------------------------------------

def test_a_cache_hit_skips_the_provider(app):
    with app.app_context():
        instance_id = _seed()
        cached = json.dumps({VALID_A: {'rating': None, 'display': '1650',
                                       'provisional': False}})
        service = RankService(_redis(cached=cached))
        with patch.object(service, '_fetch_from_provider') as fetch:
            data, _ = service.get_ratings(instance_id, [VALID_A])
        fetch.assert_not_called()
        assert data[VALID_A]['display'] == '1650'


def test_a_roster_change_changes_the_cache_key(app):
    with app.app_context():
        instance_id = _seed()
        service = RankService(_redis())
        key_one = service._cache_key(instance_id, service._load_config(instance_id),
                                     'ca', [VALID_A])
        key_two = service._cache_key(instance_id, service._load_config(instance_id),
                                     'ca', [VALID_A, VALID_B])
        assert key_one != key_two


def test_the_api_key_is_not_in_the_cache_key(app):
    with app.app_context():
        instance_id = _seed()
        service = RankService(_redis())
        config = service._load_config(instance_id)
        key = service._cache_key(instance_id, config, 'ca', [VALID_A])
        assert 'tok' not in key


def test_a_successful_result_uses_the_long_ttl(app):
    with app.app_context():
        instance_id = _seed()
        client = _redis()
        service = RankService(client)
        with patch.object(service, '_fetch_from_provider',
                          return_value={VALID_A: {'rating': None, 'display': '1',
                                                  'provisional': False}}):
            service.get_ratings(instance_id, [VALID_A])
        assert client.setex.call_args[0][1] == 60


def test_an_empty_result_uses_the_short_negative_ttl(app):
    with app.app_context():
        instance_id = _seed()
        client = _redis()
        service = RankService(client)
        with patch.object(service, '_fetch_from_provider', return_value={}):
            service.get_ratings(instance_id, [VALID_A])
        assert client.setex.call_args[0][1] == 15


def test_no_redis_fetches_uncached_and_never_raises(app):
    """Degrading to 'works, just slower' beats 'silently blank'."""
    with app.app_context():
        instance_id = _seed(game_type='ffa_auto', provider_type='elo_service',
                            base_url='http://elo:5002')
        service = RankService(None)
        with patch.object(service, '_fetch_from_provider',
                          return_value={VALID_A: {'rating': 1.0, 'display': '1',
                                                  'provisional': False}}) as fetch:
            data, configured = service.get_ratings(instance_id, [VALID_A])
        fetch.assert_called_once()
        assert data[VALID_A]['display'] == '1'
        assert configured is True


def test_invalidate_deletes_every_key_for_the_instance(app):
    with app.app_context():
        client = MagicMock()
        client.scan_iter.return_value = ['rank:ratings:7:aaa:bbb',
                                         'rank:ratings:7:ccc:ddd']
        RankService(client).invalidate(7)
        client.scan_iter.assert_called_once_with(match='rank:ratings:7:*')
        assert client.delete.call_count == 2


def test_invalidate_is_a_noop_without_redis():
    RankService(None).invalidate(7)  # must not raise
