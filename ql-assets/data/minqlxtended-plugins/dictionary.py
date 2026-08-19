# minqlxtended - Extends Quake Live's dedicated server with extra functionality and scripting.
# Copyright (C) 2024-2026 Thomas Jones <me@thomasjones.id.au>

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

# dictionary.py - a plugin for minqlxtended to enable players to call up Urban Dictionary definitions in-game.

import minqlxtended
import requests
import urllib.parse
import re
from textwrap import shorten

# api docs: https://github.com/zdict/zdict/wiki/Urban-dictionary-API-documentation
DICT_API_URL = "https://api.urbandictionary.com/v0/define?term={}"

class dictionary(minqlxtended.Plugin):
    @minqlxtended.command("define", usage="<term>")
    def cmd_define_term(self, player, msg, channel):
        """ Provides the Urban Dictionary definition for the term provided. """
        # Validate here rather than in the worker. @minqlxtended.thread returns the
        # Thread, so a Return.USAGE computed inside one is thrown away.
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        self._lookup_term(" ".join(msg[1:]), channel)

    @minqlxtended.thread
    def _lookup_term(self, term, channel):
        """The HTTP round-trip, off the game thread."""
        try:
            r = requests.get(DICT_API_URL.format(urllib.parse.quote(term)), timeout=5)
            r.raise_for_status()
            data = r.json()["list"][0]
            channel.reply(f"^6Definition^7: {shorten(self.strip_brackets(data['definition']), width=150, placeholder='...')}^7")
            if data["example"] != "":
                channel.reply(f"^6Example^7: {shorten(self.strip_brackets(data['example']), width=250, placeholder='...')}^7")
        except (IndexError, KeyError):
            channel.reply("^6Definition^7: ^3no definitions found^7")
        except Exception:
            # permission=0, so the whole server sees whatever goes to the channel.
            # Keep the detail in the log.
            self.logger.exception("Urban Dictionary lookup failed for %s", term)
            channel.reply("^6Definition^7: ^1lookup failed^7")

    def strip_brackets(self, string):
        return re.sub(r"\[|\]", "", string)
