# This file is part of the Quake Live server implementation by TomTec Solutions. Do not copy or redistribute or link to this file without the emailed consent of Thomas Jones (thomas@tomtecsolutions.com).
# custom_votes.py - a minqlx plugin to enable the ability to have custom vote functionality in-game.
# This plugin is released to everyone, for any purpose. It comes with no warranty, no guarantee it works, it's released AS IS.
# You can modify everything, except for lines 1-4 and the !tomtec_versions code. They're there to indicate I whacked this together originally. Please make it better :D

"""
The following cvars are used on this plugin:
    qlx_rulesetLocked: Is used to prevent '/cv ruleset' votes. Default: 0
    qlx_disablePlayerRemoval: Prevents non-privileged players from using '/cv kick' or '/cv tempban'. Default: 0
    qlx_disableCvarVoting: Prevents anyone from calling a CVAR vote. Default: 0
    qlx_cvarVotePermissionRequired: Required permission level to call a CVAR vote. Default: 3
"""

#
#    List of custom votes this plugin provides: http://tomtecsolutions.com.au/thepurgery/index.php?title=Special_votes
#

import minqlx

class custom_votes(minqlx.Plugin):
    def __init__(self):
        self.add_hook("vote_called", self.handle_vote_called)
        self.add_command("tomtec_versions", self.cmd_showversion)
        
        self.plugin_version = "2.3"

    def handle_vote_called(self, caller, vote, args):
        if not (self.get_cvar("g_allowSpecVote", bool)) and caller.team == "spectator":
            if caller.privileges == None:
                caller.tell("You are not allowed to call a vote as spectator.")
                return minqlx.RET_STOP_ALL

        if vote.lower() == "alltalk":
            # enables the '/cv alltalk [on/off]' command
            if args.lower() == "off":
                self.callvote("set g_allTalk 0", "voice comm between teams: off")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            elif args.lower() == "on":
                self.callvote("set g_allTalk 1", "voice comm between teams: on")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            else:
                caller.tell("^2/cv alltalk [on/off]^7 is the usage for this callvote command.")
                return minqlx.RET_STOP_ALL

        if vote.lower() == "autoshuffle":
            # enables the '/cv autoshuffle [on/off]' command
            if args.lower() == "off":
                self.callvote("set qlx_bdmBalanceAtGameStart 0", "autoshuffle: off")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            elif args.lower() == "on":
                self.callvote("set qlx_bdmBalanceAtGameStart 1", "autoshuffle: on")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            else:
                caller.tell("^2/cv autoshuffle [on/off]^7 is the usage for this callvote command.")
                return minqlx.RET_STOP_ALL


        if vote.lower() == "abort":
            # enables the '/cv abort' command
            if self.game.state != "warmup":
                self.callvote("abort", "abort the game", 30)
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            else:
                caller.tell("You can't vote to abort the game when the game isn't in progress.")
                return minqlx.RET_STOP_ALL

        if vote.lower() in ("silence", "mute"):
            # enables the '/cv silence <id>' command
            try:
                player_name = self.player(int(args)).clean_name
                player_id = self.player(int(args)).id
            except:
                caller.tell("^1Invalid ID.^7 Use a client ID from the ^2/players^7 command.")
                return minqlx.RET_STOP_ALL

            if self.get_cvar("qlx_serverExemptFromModeration") == "1":
                caller.tell("This server has the serverExemptFromModeration flag set, and therefore, silencing is disabled.")
                return minqlx.RET_STOP_ALL
            
            self.callvote("qlx !silence {} 10 minutes You were call-voted silent for 10 minutes.; mute {}".format(player_id, player_id), "silence {} for 10 minutes".format(player_name))
            self.msg("{}^7 called a vote.".format(caller.name))
            return minqlx.RET_STOP_ALL

        if vote.lower() == "spec":
            # enables the '/cv spec <id>' command
            try:
                player_name = self.player(int(args)).clean_name
                player_id = self.player(int(args)).id
            except:
                caller.tell("^1Invalid ID.^7 Use a client ID from the ^2/players^7 command.")
                return minqlx.RET_STOP_ALL

            if self.player(int(args)).team == "spectator":
                caller.tell("That player is already in the spectators.")
                return minqlx.RET_STOP_ALL
            
            self.callvote("put {} spec".format(player_id), "move {} to the spectators".format(player_name))
            self.msg("{}^7 called a vote.".format(caller.name))
            return minqlx.RET_STOP_ALL

        if vote.lower() == "do":
            if "balance" in self.plugins:
                if self.plugins["balance"].suggested_pair:
                    self.callvote("qlx !do", "force the suggested switch")
                    self.msg("{}^7 called a vote.".format(caller.name))
                else:
                    caller.tell("A switch hasn't been suggested yet by ^4!teams^7, you cannot vote to apply a suggestion that doesn't exist.")
            else:
                caller.tell("The ^4balance^7 system isn't currently loaded. This vote cannot function.")
                
            return minqlx.RET_STOP_ALL
                
    def cmd_showversion(self, player, msg, channel):
        channel.reply("^4custom_votes.py^7 - version {}, created by Thomas Jones on 01/01/2016.".format(self.plugin_version))

