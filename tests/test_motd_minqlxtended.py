"""QLSM's additions to minqlxtended's motd.py: qlx_motd1..10 seeding, !reloadmotd, and
adopting the MOTD minqlx's motd.py stored under the full fs_homepath.

Without these, a server moved from minqlx to minqlxtended comes back with no MOTD: the
stock plugin keys on the basename of fs_homepath and never reads the qlx_motdN cvars.
"""
import importlib.util
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from stubs.minqlxtended_stub import install_stub  # noqa: E402

PLUGIN_PATH = os.path.join('ql-assets', 'data', 'minqlxtended-plugins', 'motd.py')
HOMEPATH = '/home/ql/qlds/28'
NEW_KEY = 'minqlx:motd:28'
LEGACY_KEY = f'minqlx:motd:{HOMEPATH}'


@pytest.fixture(scope='module')
def module():
    install_stub()
    spec = importlib.util.spec_from_file_location('mxt_motd', PLUGIN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeDb:
    """The slice of minqlxtended.database.Redis motd.py touches."""

    def __init__(self, data=None, members=None):
        self.data = dict(data or {})
        self.sets = {'minqlx:motd': set(members or ())}

    def __contains__(self, key):
        return key in self.data

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def __delitem__(self, key):
        del self.data[key]

    def get(self, key):
        return self.data.get(key)

    def sadd(self, key, member):
        self.sets.setdefault(key, set()).add(member)

    def srem(self, key, member):
        self.sets.setdefault(key, set()).discard(member)


class FakePlayer:
    def __init__(self):
        self.told = []

    def tell(self, msg):
        self.told.append(msg)


@pytest.fixture
def make(module, monkeypatch):
    def build(db, cvars=None):
        values = {'fs_homepath': HOMEPATH, **(cvars or {})}
        monkeypatch.setattr(module.motd, 'db', db, raising=False)
        monkeypatch.setattr(module.motd, 'get_cvar',
                            lambda self, name, return_type=str, default=None: values.get(name, default))
        return module.motd()
    return build


def test_adopts_the_minqlx_full_path_motd(make):
    db = FakeDb({LEGACY_KEY: 'old^7 line'}, members={HOMEPATH})
    make(db)
    assert db.data[NEW_KEY] == 'old^7 line'
    assert db.data[LEGACY_KEY] == 'old^7 line', 'left for minqlx servers sharing the Redis'
    assert db.sets['minqlx:motd'] == {'28'}


def test_an_existing_minqlxtended_motd_is_not_overwritten_by_the_legacy_one(make):
    db = FakeDb({LEGACY_KEY: 'old', NEW_KEY: 'current'})
    make(db)
    assert db.data[NEW_KEY] == 'current'


def test_cvars_seed_the_motd_when_none_is_stored(make):
    db = FakeDb()
    make(db, {'qlx_motd1': 'first', 'qlx_motd3': 'third'})
    assert db.data[NEW_KEY] == 'first\\nthird'


def test_a_stored_motd_wins_over_the_cvars(make):
    db = FakeDb({LEGACY_KEY: 'stored'})
    make(db, {'qlx_motd1': 'from config'})
    assert db.data[NEW_KEY] == 'stored'


def test_reloadmotd_rebuilds_from_the_cvars(make, module):
    db = FakeDb({NEW_KEY: 'stale'})
    plugin = make(db, {'qlx_motd1': 'a', 'qlx_motd2': 'b'})
    player = FakePlayer()
    assert plugin.cmd_reloadmotd(player, ['!reloadmotd'], None) is module.minqlxtended.Return.STOP_EVENT
    assert db.data[NEW_KEY] == 'a\\nb'
    assert player.told == ['The MOTD has been reloaded from config.']


def test_reloadmotd_without_cvars_leaves_the_motd_alone(make):
    db = FakeDb({NEW_KEY: 'keep'})
    plugin = make(db)
    player = FakePlayer()
    plugin.cmd_reloadmotd(player, ['!reloadmotd'], None)
    assert db.data[NEW_KEY] == 'keep'
    assert 'left as it is' in player.told[0]
