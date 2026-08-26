"""The ported suppress_join_msg must register on this runtime and still swallow the
"joined the battle" center-print.

server_command's arity is unchanged (_events.py:486), so the only real risk is the
constant rename — minqlx.RET_STOP_ALL does not exist on minqlxtended (_enums.py:591).
"""
import importlib.util
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from stubs.minqlxtended_stub import install_stub  # noqa: E402

PLUGIN_PATH = os.path.join(
    'ql-assets', 'data', 'minqlxtended-plugins', 'suppress_join_msg.py'
)


@pytest.fixture(scope='module')
def module():
    install_stub()
    spec = importlib.util.spec_from_file_location('mxt_suppress_join_msg', PLUGIN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def plugin(module):
    return module.suppress_join_msg()


@pytest.fixture
def handler(plugin):
    _event, callback, _priority = plugin.hooks[0]
    return callback


def test_it_registers_its_hook(plugin):
    assert [event for event, _handler, _priority in plugin.hooks] == ['server_command']


@pytest.mark.parametrize('cmd', [
    'cp "sarge^7 joined the battle.\n"',
    'cp "sarge^7 joined the spectators.\n"',
])
def test_it_stops_the_join_message(handler, cmd):
    import minqlxtended
    assert handler(None, cmd) is minqlxtended.Return.STOP_ALL


@pytest.mark.parametrize('cmd', [
    'cp "sarge^7 was kicked.\n"',            # a cp that is not a join
    'print "sarge^7 joined the battle.\n"',  # a join phrase on the wrong command
])
def test_it_leaves_other_server_commands_alone(handler, cmd):
    assert handler(None, cmd) is None
