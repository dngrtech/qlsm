# minqlxtended - Extends Quake Live's dedicated server with extra functionality and scripting.
# Copyright (C) 2017-2026 Thomas Jones <me@thomasjones.id.au>

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

# sv_fps.py - a plugin for minqlxtended to make the sv_fps cvar modifiable.

import minqlxtended

STD_SVFPS = 40
# set_cvar(force=True) overrides sv_fps' CVAR_ROM flag, so nothing downstream catches a
# typo. Five times the stock rate is already 200 server frames a second.
MAX_SVFPS = STD_SVFPS * 5

class sv_fps(minqlxtended.Plugin):
    _qlx_svfps = minqlxtended.setting("qlx_svfps", STD_SVFPS)

    def __init__(self):
        super().__init__()
        self.set_initial_fps(self._qlx_svfps)

    @minqlxtended.command(("sv_fps", "svfps"), permission=5, usage="<integer>")
    def cmd_svfps(self, player, msg, channel):
        if len(msg) < 2:
            return minqlxtended.Return.USAGE

        try:
            sv_fps = int(msg[1])
        except ValueError:
            channel.reply(f"You must specify a positive integer greater than or equal to {STD_SVFPS}.")
            return minqlxtended.Return.STOP

        if (self.check_value(sv_fps, channel)):
            minqlxtended.set_cvar("sv_fps", str(sv_fps), force=True)
            channel.reply(f"sv_fps is now set to {sv_fps}.")

    @minqlxtended.delay(5)
    def set_initial_fps(self, cvarval):
        if (cvarval != STD_SVFPS):
            if (self.check_value(cvarval, minqlxtended.CHAT_CHANNEL)):
                minqlxtended.set_cvar("sv_fps", str(cvarval), force=True)
            else:
                self.msg("Will not set sv_fps to value of qlx_svfps as the latter contains an incompatible value.")
        else:
            pass

    def check_value(self, sv_fps, channel):
        ret = True
        if (sv_fps < 0):
            channel.reply("The integer specified must be positive.")
            ret = False
        if (sv_fps < STD_SVFPS):
            channel.reply(f"The integer specified must not be less than the preset sv_fps value ({STD_SVFPS})")
            ret = False
        if (sv_fps > MAX_SVFPS):
            channel.reply(f"The integer specified must not be greater than {MAX_SVFPS}.")
            ret = False
        if ((sv_fps % STD_SVFPS) != 0):
            channel.reply(f"The integer specified must be divisible by {STD_SVFPS}. ({STD_SVFPS*2}, {STD_SVFPS*3}, {STD_SVFPS*4}, {STD_SVFPS*5})")
            ret = False
        return ret
