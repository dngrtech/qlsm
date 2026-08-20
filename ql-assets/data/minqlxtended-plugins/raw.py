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

# Used mostly for debug. A potential security issue, since it allows
# level 5 people to execute arbitrary Python code on your server.

import minqlxtended

class raw(minqlxtended.Plugin):
    @minqlxtended.command(("exec", "pyexec"), permission=5, client_cmd_pass=False, usage="<python_code>")
    def cmd_exec(self, player, msg, channel):
        """ 'exec' arbitrary Python code. """
        if len(msg) < 2:
            return minqlxtended.Return.USAGE
        else:
            try:
                exec(" ".join(msg[1:]))
            except Exception as e:
                channel.reply(f"^1{e.__class__.__name__}^7: {e}")
                raise

    @minqlxtended.command(("eval", "pyeval"), permission=5, client_cmd_pass=False, usage="<python_code>")
    def cmd_eval(self, player, msg, channel):
        """ 'eval' arbitrary Python code. """
        if len(msg) < 2:
            return minqlxtended.Return.USAGE
        else:
            try:
                channel.reply(str(eval(" ".join(msg[1:]))))
            except Exception as e:
                channel.reply(f"^1{e.__class__.__name__}^7: {e}")
                raise

    @minqlxtended.command(("db", "database"), permission=5, usage="<key> [value]")
    def cmd_db(self, player, msg, channel):
        """ Prints the value of a key in the database. """
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        try:
            if msg[1] not in self.db:
                channel.reply("The key is not present in the database.")
            else:
                t = self.db.type(msg[1])
                if t == "string":
                    out = self.db[msg[1]]
                elif t == "list":
                    out = str(self.db.lrange(msg[1], 0, -1))
                elif t == "set":
                    out = str(self.db.smembers(msg[1]))
                elif t == "zset":
                    out = str(self.db.zrange(msg[1], 0, -1, withscores=True))
                else:
                    out = str(self.db.hgetall(msg[1]))

                channel.reply(out)
        except Exception as e:
            channel.reply(f"^1{e.__class__.__name__}^7: {e}")
            raise
