# minqlxtended - Extends Quake Live's dedicated server with extra functionality and scripting.
# Copyright (C) 2015 Mino <mino@minomino.org>
# Copyright (C) 2016-2026 Thomas Jones <me@thomasjones.id.au>

# This file is part of minqlxtended.

# minqlxtended is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# minqlxtended is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with minqlxtended. If not, see <http://www.gnu.org/licenses/>.

# This plugin owns the `cn`/`xcn` keys in every player's configstring: exactly one writer
# and exactly one pair. Other plugins contribute a prefix through
# set_prefix()/clear_prefix() and this plugin composes the result.

import re

import minqlxtended

NO_CLANTAG_FLAG_NAME = "no_clantag"

_re_remove_excessive_colors = re.compile(r"(?:\^.)+(\^.)")
_tag_key = "minqlx:players:{}:clantag"

# The infostring format can't carry any of these, so format_infostring raises on them.
# A tag holding one would make every configstring change for that slot throw.
_FORBIDDEN_TAG_CHARS = "\\;\""

MAX_TAG_LENGTH = 5

class clan(minqlxtended.Plugin):
    def __init__(self):
        super().__init__()

        # client_id -> {"steam_id": int, "tag": str|None, "no_clantag": bool}. Keyed on
        # client id so the set_configstring handler, which only knows an index, doesn't
        # have to build a Player. Cleared on connect and disconnect so a new occupant
        # can't inherit the previous tag.
        self._by_client = {}
        # client_id -> str, contributed by other plugins (queue positions, AFK, ...).
        self._prefixes = {}

        for player in self.players():
            self._load_cache(player)

    # API FOR OTHER PLUGINS

    def set_prefix(self, client_id, prefix):
        """Prepend *prefix* to this player's clan tag, e.g. a queue position.

        Dirty-checked. Returns True if the displayed tag changed and a
        configstring write was issued.
        """
        prefix = prefix or ""
        if self._prefixes.get(client_id, "") == prefix:
            return False
        if prefix:
            self._prefixes[client_id] = prefix
        else:
            self._prefixes.pop(client_id, None)
        return self.refresh(client_id)

    def clear_prefix(self, client_id):
        """Remove any prefix contributed for this player."""
        return self.set_prefix(client_id, "")

    def clan_tag(self, client_id):
        """The composed tag this plugin would show for a player, or ""."""
        entry = self._by_client.get(client_id)
        if entry is None or entry["no_clantag"]:
            return ""
        return self._compose(client_id, entry)

    def refresh(self, client_id):
        """Rewrite this player's configstring so the composed tag is applied.

        Player.clan's setter is dirty-checked, so assigning the same value back is a
        no-op and never reaches the dispatchers. Writing the configstring does.
        """
        index = minqlxtended.CS_PLAYERS + client_id
        current = minqlxtended.configstring(index)
        if not current:
            return False
        minqlxtended.set_configstring(index, current)
        return True

    # HOOKS

    @minqlxtended.hook("player_connect")
    def handle_player_connect(self, player, is_bot):
        # Client ids are reused. Drop whatever the previous occupant left behind
        # before any configstring for this slot can be composed against it.
        self._by_client.pop(player.id, None)
        self._prefixes.pop(player.id, None)

        # Seeded immediately: handle_set_configstring does nothing without an entry, and
        # player_loaded, the only other populator, never fires for bots.
        try:
            self._load_cache(player)
        except Exception:
            self.logger.exception("Couldn't cache the clan tag for client %d.", player.id)

        # PlayerConnectDispatcher reads a returned string as a ban message, and
        # _load_cache hands back the entry dict.
        return None

    @minqlxtended.hook("player_loaded")
    def handle_player_loaded(self, player):
        # player_connect already seeded the slot, so this reads the database only when that
        # threw or when the cached entry belongs to a previous occupant.
        entry = self._by_client.get(player.id)
        if entry is None or entry["steam_id"] != player.steam_id:
            self._load_cache(player)
        # The configstrings written during connect had no cache entry to work from,
        # so apply the tag now. One write per connect.
        if self.clan_tag(player.id):
            self.refresh(player.id)

    @minqlxtended.hook("player_disconnect")
    def handle_player_disconnect(self, player, reason):
        self._by_client.pop(player.id, None)
        self._prefixes.pop(player.id, None)

    @minqlxtended.hook("set_configstring")
    def handle_set_configstring(self, index, value):
        if not value: # Player disconnected?
            return
        if not (minqlxtended.CS_PLAYERS <= index < minqlxtended.CS_PLAYERS + minqlxtended.MAX_CLIENTS):
            return

        client_id = index - minqlxtended.CS_PLAYERS
        entry = self._by_client.get(client_id)
        if entry is None:
            # Between player_connect and player_loaded the identity is unknown, and this
            # runs on the game thread for every player configstring change, so no database
            # I/O here. handle_player_loaded applies the tag.
            return
        if entry["no_clantag"]:
            return # Player is not allowed to use clan tags.

        tag = self._compose(client_id, entry)

        variables = minqlxtended.parse_infostring(value)
        # "" rather than None, since a player with no tag and a configstring with no cn key
        # is already correct and comparing the two would rewrite it on every change.
        if variables.get("cn", "") == tag and variables.get("xcn", "") == tag:
            return # Nothing to change; don't make the engine rewrite it.

        if tag:
            variables["cn"] = tag
            variables["xcn"] = tag
        else:
            variables.pop("cn", None)
            variables.pop("xcn", None)

        return minqlxtended.format_infostring(variables)

    # COMMANDS

    @minqlxtended.command("clan", client_cmd_perm=0, usage="<clan_tag>")
    def cmd_clan(self, player, msg, channel):
        """ Sets the player's clan tag to the string specified, or clears it if nothing specified. """
        entry = self._by_client.get(player.id)
        if entry is None:
            entry = self._load_cache(player)

        if entry["no_clantag"]:
            player.tell("You cannot modify your clan tag.")
            return minqlxtended.Return.STOP_EVENT

        tag_key = _tag_key.format(player.steam_id)

        if len(msg) < 2:
            if entry["tag"] is None:
                player.tell(f"Usage to set a clan tag: ^6{msg[0]} <clan_tag>")
                return minqlxtended.Return.STOP_EVENT

            try:
                del self.db[tag_key]
            except KeyError:
                pass # Already gone; the cache was ahead of the database.
            entry["tag"] = None
            self.refresh(player.id)
            player.tell("The clan tag has been cleared.")
            return minqlxtended.Return.STOP_EVENT

        if len(self.clean_text(msg[1])) > MAX_TAG_LENGTH:
            player.tell(f"The clan tag can only be at most {MAX_TAG_LENGTH} characters long, excluding colors.")
            return minqlxtended.Return.STOP_EVENT

        if any(character in msg[1] for character in _FORBIDDEN_TAG_CHARS):
            player.tell("The clan tag cannot contain a backslash, a semicolon or a quote.")
            return minqlxtended.Return.STOP_EVENT

        silence = self.plugin("silence")
        if silence is not None and player.steam_id in silence.silenced:
            # prevent a silenced player from changing their clan tag, but let them remove it
            return minqlxtended.Return.STOP_EVENT

        tag = self.clean_tag(msg[1])
        self.db[tag_key] = tag
        entry["tag"] = tag
        self.refresh(player.id)
        self.msg(f"{player}^7 changed clan tag to {tag}")
        return minqlxtended.Return.STOP_EVENT

    @minqlxtended.command("setnoclan", permission=4, client_cmd_perm=4, usage="<id>")
    def cmd_setnoclan(self, player, msg, channel):
        """ Prevents the specified player from using clan tags. """
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        resolved = self.resolve_identifier(msg[1], channel)
        if resolved is None:
            return
        ident, name, target_player = resolved

        flag = self.db.get_flag(ident, NO_CLANTAG_FLAG_NAME)
        self.db.set_flag(ident, NO_CLANTAG_FLAG_NAME, not flag)

        # Keep the in-memory cache consistent if this player is currently connected.
        if target_player is not None:
            cached = self._by_client.get(target_player.id)
            if cached is not None:
                cached["no_clantag"] = not flag
            self.refresh(target_player.id)

        if not flag:
            channel.reply(f"{name}^7 is no longer allowed to use clan tags.")
        else:
            channel.reply(f"{name}^7 is allowed to use clan tags.")

    # HELPERS

    def _compose(self, client_id, entry):
        """The full tag: any contributed prefix, then the player's own clan tag."""
        parts = []
        prefix = self._prefixes.get(client_id)
        if prefix:
            parts.append(prefix)
        if entry["tag"]:
            parts.append(entry["tag"])
        return " ".join(parts)

    def _load_cache(self, player):
        """Read a player's clan tag and no-clantag flag from the DB once and cache them."""
        tag_key = _tag_key.format(player.steam_id)
        try:
            tag = self.db[tag_key]
        except KeyError:
            tag = None
        if tag and any(character in tag for character in _FORBIDDEN_TAG_CHARS):
            # Composing this would raise on every configstring change for the slot, so the
            # stored value is dropped on the way in.
            self.logger.warning("Dropping the unusable clan tag stored for %d.", player.steam_id)
            tag = None
        entry = {
            "steam_id": player.steam_id,
            "no_clantag": self.db.get_flag(player, NO_CLANTAG_FLAG_NAME),
            "tag": tag,
        }
        self._by_client[player.id] = entry
        return entry

    def clean_tag(self, tag):
        """Removes excessive colors and only keeps the one that matters."""
        def sub_func(match):
            return match.group(1)

        return _re_remove_excessive_colors.sub(sub_func, tag)
