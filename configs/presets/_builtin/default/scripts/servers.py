# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# If you have any suggestions or issues/problems with this plugin you can contact me(kanzo) on irc at #minqlbot
# or alternatively you can open an issue at https://github.com/cstewart90/minqlx-plugins/issues

"""
Adds !servers command which shows status of servers.
This plugin uses a2s api I made at a2s.c16t.uk/info

!servers - Show status of servers.

Cvars and their default values:
qlx_servers ""            - List of servers to be shown. Example: "108.61.190.53:27960, il.qlrace.com:27961"
qlx_serversShowInChat "0" - Whether to output to chat. If it is 0 it only tells the player who used !servers.
"""

import minqlx
import time
import requests


class servers(minqlx.Plugin):
    def __init__(self):
        super().__init__()
        self.add_command("servers", self.cmd_servers)

        # Example value "108.61.190.53:27960, 108.61.190.53:27961, il.qlrace.com:27960"
        self.set_cvar_once("qlx_serversShowInChat", "0")

    def cmd_servers(self, player, _msg, channel):
        """If `qlx_servers` is set then it outputs status of servers.
        Outputs to chat if `qlx_serversShowInChat` is 1, otherwise it will
        output to the player who called the command only."""
        servers_list = self.get_cvar("qlx_servers", list)
        if len(servers_list) == 1 and servers_list[0] == "":
            self.logger.warning("qlx_servers is not set")
            player.tell("qlx_servers is not set")
            return minqlx.RET_STOP_ALL
        elif any(s == '' for s in servers_list):
            self.logger.warning("qlx_servers has an invalid server(empty string). Most likely due to trailing comma.")
            player.tell("qlx_servers has an invalid server(empty string). Most likely due to trailing comma.")
            return minqlx.RET_STOP_ALL

        irc = isinstance(player, minqlx.AbstractDummyPlayer)
        if not self.get_cvar("qlx_serversShowInChat", bool) and not irc:
            self.get_servers(servers_list, minqlx.TellChannel(player))
            return minqlx.RET_STOP_ALL

        self.get_servers(servers_list, channel, irc=irc)

    @minqlx.thread
    def get_servers(self, servers_list, channel, irc=False):
        """Gets and outputs info for all servers in `qlx_servers`."""
        info = self.get_server_info(servers_list)
        if info["error"]:
            channel.reply("Error: {}".format(info["error"]))
            return

        output = ["^3{:^20} | {:^37} | {:^22}  | {}".format("IP", "Server Name", "Map", "Players")]

        for server in info["servers"]:
            if server["max_players"] == 0:
                players = "^1..."
            elif server["players"] >= server["max_players"]:
                players = "^3{players}/{max_players}".format(**server)
            else:
                players = "^2{players}/{max_players}".format(**server)

            if server["error"]:
                server["name"] = "^1Error when trying to query^7"
            else:
                server["name"] = server["name"][:36]

            output.append("^7{:20} | {:37} | {:23} | {}".format(
                server["server"], server["name"], server["map"], players))

        if irc:
            reply_large_output(channel, output, max_amount=1, delay=2)
        else:
            reply_large_output(channel, output)

    def get_server_info(self, servers_list):
        """Gets server info for all servers using a2s.c16t.uk/info"""
        query = {"servers": ",".join(servers_list)}
        try:
            r = requests.get("https://a2s.c16t.uk/info", params=query)
            return r.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(e)
            return {"error": e, "servers": []}


def reply_large_output(channel, output, max_amount=26, delay=0.4):
    """Replies with large output in small portions, as not to disconnected the player.
    :param channel: Channel to reply to.
    :param output: Output to send to channel.
    :param max_amount: Max amount of lines to send at once.
    :param delay: Time to sleep between large inputs.
    """
    for count, line in enumerate(output, start=1):
        if count % max_amount == 0:
            time.sleep(delay)
        channel.reply(line)