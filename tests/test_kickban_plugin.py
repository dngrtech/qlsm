"""Unit tests for qlsm_plugins/kickban.py helper methods."""

import os
import sys
import time
import types
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

# ── Minimal minqlx mock ──────────────────────────────────────────────────────

minqlx_mock = types.ModuleType("minqlx")
minqlx_mock.RET_USAGE = "ret_usage"
minqlx_mock.PRI_HIGH = 0


class _FakePlugin:
    def __init__(self):
        self.db = MagicMock()
        self._cvars = {
            "qlx_kickbanThreshold": "3",
            "qlx_kickbanWindow": "15",
            "qlx_kickbanDuration": "60",
            "qlx_kickbanImmunityLevel": "2",
        }

    def set_cvar_once(self, key, value):
        pass

    def add_hook(self, *args, **kwargs):
        pass

    def add_command(self, *args, **kwargs):
        pass

    def get_cvar(self, key, type_=None):
        val = self._cvars.get(key, "")
        if type_ is int:
            return int(val)
        return val

    def msg(self, text):
        pass


minqlx_mock.Plugin = _FakePlugin
minqlx_mock.NonexistentPlayerError = Exception


def _noop_delay(seconds):
    def decorator(fn):
        return fn
    return decorator


minqlx_mock.delay = _noop_delay
sys.modules["minqlx"] = minqlx_mock

# ── Import plugin after mock is in place ────────────────────────────────────

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "qlsm_plugins"))
from kickban import kickban, PLAYER_KEY, TIME_FORMAT  # noqa: E402


class TestKickbanKeys(unittest.TestCase):
    def setUp(self):
        self.plugin = kickban()

    def test_kicks_key(self):
        self.assertEqual(
            self.plugin._kicks_key(12345),
            "minqlx:players:12345:kicks"
        )

    def test_bans_key(self):
        self.assertEqual(
            self.plugin._bans_key(12345),
            "minqlx:players:12345:bans"
        )


class TestPruneAndCount(unittest.TestCase):
    def setUp(self):
        self.plugin = kickban()

    def test_prune_removes_old_entries_and_returns_count(self):
        self.plugin.db.zcard.return_value = 2
        count = self.plugin._prune_and_count(12345)
        window_seconds = 15 * 60
        self.plugin.db.zremrangebyscore.assert_called_once()
        args = self.plugin.db.zremrangebyscore.call_args[0]
        self.assertEqual(args[0], "minqlx:players:12345:kicks")
        self.assertEqual(args[1], 0)
        self.assertAlmostEqual(args[2], time.time() - window_seconds, delta=2)
        self.assertEqual(count, 2)


class TestHandleDisconnectDetection(unittest.TestCase):
    def setUp(self):
        self.plugin = kickban()
        self.player = MagicMock()
        self.player.steam_id = 99999
        self.player.clean_name = "TestPlayer"
        self.plugin.db.get_permission.return_value = 0
        self.plugin.db.zcard.return_value = 0

    def test_non_kick_reason_ignored(self):
        self.plugin.handle_player_disconnect(self.player, "disconnected")
        self.plugin.db.zadd.assert_not_called()

    def test_kick_reason_records_entry(self):
        self.plugin.db.zcard.return_value = 1
        self.plugin.handle_player_disconnect(self.player, "was kicked")
        self.plugin.db.zadd.assert_called_once()
        key, mapping = self.plugin.db.zadd.call_args[0]
        self.assertEqual(key, "minqlx:players:99999:kicks")
        self.assertEqual(len(mapping), 1)
        member = list(mapping.keys())[0]
        score = list(mapping.values())[0]
        self.assertIsInstance(member, str)
        self.assertNotEqual(member, str(score))

    def test_immune_player_ignored(self):
        self.plugin.db.get_permission.return_value = 5
        self.plugin.handle_player_disconnect(self.player, "was kicked")
        self.plugin.db.zadd.assert_not_called()

    def test_nonexistent_player_error_on_disconnect_returns_early(self):
        bad_player = MagicMock()
        type(bad_player).steam_id = PropertyMock(side_effect=minqlx_mock.NonexistentPlayerError)
        self.plugin.handle_player_disconnect(bad_player, "was kicked")
        self.plugin.db.zadd.assert_not_called()

    def test_vote_kick_reason_records_entry(self):
        self.plugin.db.zcard.return_value = 1
        self.plugin.handle_player_disconnect(self.player, "kicked by vote")
        self.plugin.db.zadd.assert_called_once()


class TestIssueBan(unittest.TestCase):
    def setUp(self):
        self.plugin = kickban()
        self.plugin.db.zcard.return_value = 0
        self.pipeline = MagicMock()
        self.plugin.db.pipeline.return_value = self.pipeline

    def test_ban_written_to_redis(self):
        with patch.object(self.plugin, "msg"):
            self.plugin._issue_ban(12345, "TestPlayer", 3)

        self.plugin.db.pipeline.assert_called_once()
        self.pipeline.zadd.assert_called_once()
        bans_key, mapping = self.pipeline.zadd.call_args[0]
        self.assertEqual(bans_key, "minqlx:players:12345:bans")
        score = list(mapping.values())[0]
        self.assertAlmostEqual(score, time.time() + 60 * 60, delta=5)

    def test_ban_hash_has_correct_fields(self):
        with patch.object(self.plugin, "msg"):
            self.plugin._issue_ban(12345, "TestPlayer", 3)

        self.pipeline.hmset.assert_called_once()
        key, data = self.pipeline.hmset.call_args[0]
        self.assertEqual(key, "minqlx:players:12345:bans:0")
        self.assertIn("expires", data)
        self.assertIn("reason", data)
        self.assertIn("issued", data)
        self.assertEqual(data["issued_by"], "0")
        self.assertIn("3", data["reason"])
        self.assertIn("15", data["reason"])

    def test_kick_history_cleared_after_ban(self):
        with patch.object(self.plugin, "msg"):
            self.plugin._issue_ban(12345, "TestPlayer", 3)
        self.plugin.db.delete.assert_called_with("minqlx:players:12345:kicks")

    def test_server_broadcast_sent(self):
        with patch.object(self.plugin, "msg") as mock_msg:
            self.plugin._issue_ban(12345, "TestPlayer", 3)
        mock_msg.assert_called_once()
        broadcast = mock_msg.call_args[0][0]
        self.assertIn("TestPlayer", broadcast)
        self.assertIn("60", broadcast)

    def test_ban_triggered_at_threshold(self):
        self.plugin.db.get_permission.return_value = 0
        self.plugin.db.zcard.return_value = 2

        with patch.object(self.plugin, "_issue_ban") as mock_ban:
            player = MagicMock()
            player.steam_id = 12345
            player.clean_name = "TestPlayer"
            self.plugin.handle_player_disconnect(player, "was kicked")
            mock_ban.assert_called_once_with(12345, "TestPlayer", 3)

    def test_ban_not_triggered_below_threshold(self):
        self.plugin.db.get_permission.return_value = 0
        self.plugin.db.zcard.return_value = 1

        with patch.object(self.plugin, "_issue_ban") as mock_ban:
            player = MagicMock()
            player.steam_id = 12345
            self.plugin.handle_player_disconnect(player, "was kicked")
            mock_ban.assert_not_called()


class TestPlayerLoadedWarning(unittest.TestCase):
    def setUp(self):
        self.plugin = kickban()
        self.player = MagicMock()
        self.player.steam_id = 12345
        self.player.clean_name = "TestPlayer"

    def test_no_broadcast_when_no_kicks(self):
        self.plugin.db.zcard.return_value = 0
        with patch.object(self.plugin, "msg") as mock_msg:
            self.plugin.handle_player_loaded(self.player)
        mock_msg.assert_not_called()

    def test_broadcast_when_kicks_exist(self):
        self.plugin.db.zcard.return_value = 1
        with patch.object(self.plugin, "msg") as mock_msg:
            self.plugin.handle_player_loaded(self.player)
        mock_msg.assert_called_once()
        text = mock_msg.call_args[0][0]
        self.assertIn("TestPlayer", text)
        self.assertIn("1", text)
        self.assertIn("2", text)
        self.assertIn("15", text)
        self.assertIn("60", text)

    def test_nonexistent_player_handled(self):
        self.player.update = MagicMock(side_effect=minqlx_mock.NonexistentPlayerError)
        self.plugin.handle_player_loaded(self.player)


class TestAdminCommands(unittest.TestCase):
    def setUp(self):
        self.plugin = kickban()
        self.admin = MagicMock()
        self.admin.steam_id = 1
        self.channel = MagicMock()

        self.target = MagicMock()
        self.target.steam_id = 99999
        self.target.clean_name = "Target"
        self.plugin.player = MagicMock(return_value=self.target)

    def test_kickhistory_usage_when_no_arg(self):
        result = self.plugin.cmd_kickhistory(self.admin, ["!kickhistory"], self.channel)
        self.assertEqual(result, minqlx_mock.RET_USAGE)

    def test_kickhistory_no_kicks(self):
        self.plugin.db.zcard.return_value = 0
        self.plugin.cmd_kickhistory(self.admin, ["!kickhistory", "5"], self.channel)
        self.channel.reply.assert_called_once()
        self.assertIn("no kicks", self.channel.reply.call_args[0][0].lower())

    def test_kickhistory_with_kicks(self):
        self.plugin.db.zcard.return_value = 2
        ts = time.time()
        self.plugin.db.zrangebyscore.return_value = [("ts1", ts), ("ts2", ts + 1)]
        self.plugin.cmd_kickhistory(self.admin, ["!kickhistory", "5"], self.channel)
        self.channel.reply.assert_called_once()
        reply = self.channel.reply.call_args[0][0]
        self.assertIn("Target", reply)
        self.assertIn("2", reply)

    def test_kickclear_usage_when_no_arg(self):
        result = self.plugin.cmd_kickclear(self.admin, ["!kickclear"], self.channel)
        self.assertEqual(result, minqlx_mock.RET_USAGE)

    def test_kickclear_deletes_key(self):
        self.plugin.cmd_kickclear(self.admin, ["!kickclear", "5"], self.channel)
        self.plugin.db.delete.assert_called_with("minqlx:players:99999:kicks")
        self.channel.reply.assert_called_once()
        self.assertIn("Target", self.channel.reply.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
