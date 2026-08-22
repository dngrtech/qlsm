# Created by Thomas Jones on 16/05/2016 - thomas@tomtecsolutions.com
# onjoin.py, a plugin for minqlx to automatically display a set message when a player who has set their onjoin message connects.
# This plugin is released to everyone, for any purpose. It comes with no warranty, no guarantee it works, it's released AS IS.
# You can modify everything, except for lines 1-4 and the !tomtec_versions code. They're there to indicate I whacked this together originally. Please make it better :D

# Concepts and code borrowed from names.py by Mino. Thanks a lot!

import minqlxtended

_onjoin_key = "minqlx:players:{}:onjoin_message"

class onjoin(minqlxtended.Plugin):
    def __init__(self):
        self.add_hook("player_loaded", self.handle_player_loaded, priority=minqlxtended.Priority.LOWEST)

        self.add_command(("onjoin", "oj"), self.cmd_onjoin, usage="<message>", client_cmd_perm=0)
        
        self.add_command("tomtec_versions", self.cmd_showversion)
        self.plugin_version = "1.1"


    def cmd_onjoin(self, player, msg, channel):
        onjoin_key = _onjoin_key.format(player.steam_id)   
        if len(msg) < 2:
            if onjoin_key not in self.db:
                return minqlxtended.Return.USAGE
            else:
                del self.db[onjoin_key]
                player.tell("Your onjoin message has been removed.")
                return minqlxtended.Return.STOP_ALL
        message = str(" ".join(msg[1:]))
        
        if len(message.encode()) > 150:
            player.tell("That message is too long. Character Limit: 150.")
            return minqlxtended.Return.STOP_ALL

        self.db[onjoin_key] = message
        player.tell("That message has been saved. To make me forget about it, a simple ^4{}onjoin^7 will do it.".format(self.get_cvar("qlx_commandPrefix")))
        return minqlxtended.Return.STOP_ALL
    
    def handle_player_loaded(self, player):
        onjoin_key = _onjoin_key.format(player.steam_id)
        if onjoin_key in self.db:
            onjoin_message = self.db[onjoin_key]
            self.msg("{}^7: ^2{}^7".format(player.name, onjoin_message))
            self.talk_beep()

    def talk_beep(self, player=None):
        if not player:
            self.play_sound("sound/player/talk.ogg")
        else:
            self.play_sound("sound/player/talk.ogg", player)
                     
    def cmd_showversion(self, player, msg, channel):
        channel.reply("^4onjoin.py^7 - version {}, created by Thomas Jones on 16/05/2016.".format(self.plugin_version))
