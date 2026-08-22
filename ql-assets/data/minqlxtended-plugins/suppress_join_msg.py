# suppress_join_msg.py
# Suppresses the "X joined the battle/spectators" center-print shown to all players on connect.
# The message is hardcoded in qagamex64.so and broadcast as a `cp` server command.

import minqlxtended


class suppress_join_msg(minqlxtended.Plugin):

    def __init__(self):
        self.add_hook("server_command", self.handle_server_command)

    def handle_server_command(self, player, cmd):
        if cmd.startswith('cp "') and "joined the " in cmd:
            return minqlxtended.Return.STOP_ALL
