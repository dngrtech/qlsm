# This file is part of the Quake Live server implementation by TomTec Solutions. Do not copy or redistribute or link to this file without the emailed consent of Thomas Jones (thomas@tomtecsolutions.com).
# custom_votes.py - a minqlx plugin to enable the ability to have custom vote functionality in-game.
# This plugin is released to everyone, for any purpose. It comes with no warranty, no guarantee it works, it's released AS IS.
# You can modify everything, except for lines 1-4 and the !tomtec_versions code. They're there to indicate I whacked this together originally. Please make it better :D
# Updated February 2026 by Doomsday

"""
The following cvars are used on this plugin:
    qlx_rulesetLocked: Is used to prevent '/cv ruleset' votes. Default: 0
    qlx_disablePlayerRemoval: Prevents non-privileged players from using '/cv kick' or '/cv tempban'. Default: 0
    qlx_disableCvarVoting: Prevents anyone from calling a CVAR vote. Default: 3
    qlx_cvarVotePermissionRequired: Required permission level to call a CVAR vote. Default: 3
    
    qlx_cvflags: Bitwise flags to control which custom votes are enabled. Default: 0
        0 = All flags disabled (use original behavior - all votes allowed)
        Set to -1 to enable all vote restrictions
        Or add flag values together to enable specific vote types:
        
        1 = infiniteammo
        2 = freecam
        4 = floordamage
        8 = alltalk
        16 = allready
        32 = abort
        64 = chatsounds
        128 = mute (new - with configurable timeout)
        256 = silence (new - with custom duration)
        512 = tempban
        1024 = spec
        2048 = excessive
        4096 = kick/clientkick
        8192 = lock
        16384 = unlock
        32768 = balancing
        65536 = roundtimelimit
        131072 = balance
        262144 = lgammo
        524288 = glammo
        1048576 = lgdamage
        2097152 = rgdamage
        4194304 = runes
        
        Examples:
          qlx_cvflags 0      # All votes allowed (default)
          qlx_cvflags 132    # Only mute (128) + floordamage (4)
          qlx_cvflags -1     # All vote restrictions enabled
    
    qlx_mutevotetimeout: Default timeout in seconds for mute votes. Default: 300 (5 minutes)
        Does not affect admin !silence commands which have their own time parameters.
    
    qlx_mutevotelevel: Required permission level to call a mute/silence vote. Default: 0 (anyone can vote)
"""

#
#    List of custom votes this plugin provides: https://web.archive.org/web/20160203093751/http://tomtecsolutions.com.au/thepurgery/index.php?title=Special_votes
#

import minqlx

# Vote type flags - use these with qlx_cvflags
CV_FLAG_INFINITEAMMO = 1
CV_FLAG_FREECAM = 2
CV_FLAG_FLOORDAMAGE = 4
CV_FLAG_ALLTALK = 8
CV_FLAG_ALLREADY = 16
CV_FLAG_ABORT = 32
CV_FLAG_CHATSOUNDS = 64
CV_FLAG_MUTE = 128
CV_FLAG_SILENCE = 256
CV_FLAG_TEMPBAN = 512
CV_FLAG_SPEC = 1024
CV_FLAG_EXCESSIVE = 2048
CV_FLAG_KICK = 4096
CV_FLAG_LOCK = 8192
CV_FLAG_UNLOCK = 16384
CV_FLAG_BALANCING = 32768
CV_FLAG_ROUNDTIMELIMIT = 65536
CV_FLAG_BALANCE = 131072
CV_FLAG_LGAMMO = 262144
CV_FLAG_GLAMMO = 524288
CV_FLAG_LGDAMAGE = 1048576
CV_FLAG_RGDAMAGE = 2097152
CV_FLAG_RUNES = 4194304

class custom_votesplus(minqlx.Plugin):
    def __init__(self):
        self.add_hook("vote_called", self.handle_vote_called)
        self.add_hook("player_loaded", self.player_loaded)
        self.add_hook("vote_ended", self.handle_vote_ended)

        self.add_command("tomtec_versions", self.cmd_showversion)
        self.add_command("excessiveweaps", self.cmd_excessive_weaps, 5, usage="on/off")
        self.add_command("ruleset", self.cmd_ruleset, 5, usage="pql/vql")

        self.set_cvar_once("qlx_rulesetLocked", "0")
        self.set_cvar_once("qlx_excessive", "0")
        self.set_cvar_once("qlx_disablePlayerRemoval", "0")
        self.set_cvar_once("qlx_disableCvarVoting", "0")
        self.set_cvar_once("qlx_cvarVotePermissionRequired", "3")
        
        self.plugin_version = "2.4"

    def player_loaded(self, player):
        if (self.get_cvar("qlx_excessive", bool)):
            player.tell("Excessive weapons are ^2enabled^7. To disable them, ^2/cv excessive off^7.")
    
    def check_cv_flag(self, flag):
        """Check if a specific custom vote flag is enabled.
        
        Returns True if the vote type is allowed, False if disabled.
        qlx_cvflags = 0 means all votes allowed (default behavior).
        qlx_cvflags = -1 means use all restrictions.
        Otherwise, check if the specific flag bit is set.
        """
        cv_flags = self.get_cvar("qlx_cvflags", int)
        if cv_flags == 0:
            # Default behavior - all votes allowed
            return True
        if cv_flags == -1:
            # All restrictions enabled
            return True
        return (cv_flags & flag) != 0
    
    def handle_vote_ended(self, votes, vote, args, passed):
        """Handle vote results for mute/silence votes."""
        if not passed:
            # Clear pending votes if they failed
            self.pending_mute = None
            self.pending_silence = None
            return
            
        # Handle mute vote
        if self.pending_mute:
            target_player, timeout = self.pending_mute
            if target_player and target_player in self.players():
                # Use essentials mute
                if "essentials" in self.plugins:
                    self.plugins["essentials"].mute(target_player.steam_id)
                    
                    # Schedule unmute after timeout
                    @minqlx.next_frame
                    def schedule_unmute():
                        @minqlx.delay(timeout)
                        def unmute_player():
                            if "essentials" in self.plugins and target_player in self.players():
                                self.plugins["essentials"].unmute(target_player.steam_id)
                                self.msg("^3{}^7's mute has expired.".format(target_player.name))
                        unmute_player()
                    schedule_unmute()
                    
                    self.msg("^3{}^7 has been muted for ^3{}^7 seconds.".format(
                        target_player.name, timeout))
            self.pending_mute = None
        
        # Handle silence vote  
        elif self.pending_silence:
            target_player, duration, unit = self.pending_silence
            if target_player and target_player in self.players() and "essentials" in self.plugins:
                # Call the silence command
                minqlx.console_command("qlx !silence {} {} {}".format(
                    target_player.id, duration, unit))
            self.pending_silence = None
            
    def cmd_ruleset(self, player, msg, channel):
        if len(msg) < 2:
            return minqlx.RET_USAGE
        
        if msg[1].lower() == "pql":
            minqlx.set_cvar("pmove_airControl", "1")
            minqlx.set_cvar("pmove_rampJump", "1")
            minqlx.set_cvar("weapon_reload_rg", "1200")
            minqlx.set_cvar("pmove_weaponRaiseTime", "10")
            minqlx.set_cvar("pmove_weaponDropTime", "10")
            minqlx.set_cvar("g_damage_lg", "7")
            minqlx.set_cvar("dmflags", "60")
            if self.game.type_short == "ca":
                minqlx.set_cvar("g_startingHealth", "200")
                minqlx.set_cvar("g_startingArmor", "200")
            minqlx.console_command("map_restart")
            self.msg("PQL ruleset is now set.")

        if msg[1].lower() == "vql":
            minqlx.set_cvar("pmove_airControl", "0")
            minqlx.set_cvar("pmove_rampJump", "0")
            minqlx.set_cvar("weapon_reload_rg", "1500")
            minqlx.set_cvar("pmove_weaponRaiseTime", "200")
            minqlx.set_cvar("pmove_weaponDropTime", "200")
            minqlx.set_cvar("g_damage_lg", "6")
            if self.game.type_short == "ca":
                minqlx.set_cvar("dmflags", "28")
            else:
                minqlx.console_command("reset dmflags")
            minqlx.console_command("reset g_startingHealth")
            minqlx.console_command("reset g_startingArmor")
            minqlx.console_command("map_restart")
            self.msg("VQL ruleset is now set.")

    def cmd_excessive_weaps(self, player, msg, channel):
        if len(msg) < 2:
            return minqlx.RET_USAGE
        
        if msg[1] == "on":
            minqlx.set_cvar("weapon_reload_sg", "200")
            minqlx.set_cvar("weapon_reload_rl", "200")
            minqlx.set_cvar("weapon_reload_rg", "50")
            minqlx.set_cvar("weapon_reload_prox", "200")
            minqlx.set_cvar("weapon_reload_pg", "40")
            minqlx.set_cvar("weapon_reload_ng", "800")
            minqlx.set_cvar("weapon_reload_mg", "40")
            minqlx.set_cvar("weapon_reload_hmg", "40")
            minqlx.set_cvar("weapon_reload_gl", "200")
            minqlx.set_cvar("weapon_reload_gauntlet", "100")
            minqlx.set_cvar("weapon_reload_cg", "30")
            minqlx.set_cvar("weapon_reload_bfg", "75")
            minqlx.set_cvar("qlx_excessive", "1")
            self.msg("Excessive weapons are enabled.")
        if msg[1] == "off":
            minqlx.console_command("reset weapon_reload_sg")
            minqlx.console_command("reset weapon_reload_rl")
            if (minqlx.get_cvar("pmove_airControl")) == "1":
                minqlx.set_cvar("weapon_reload_rg", "1200")
            else:
                minqlx.console_command("reset weapon_reload_rg")
            minqlx.console_command("reset weapon_reload_prox")
            minqlx.console_command("reset weapon_reload_pg")
            minqlx.console_command("reset weapon_reload_ng")
            minqlx.console_command("reset weapon_reload_mg")
            minqlx.console_command("reset weapon_reload_hmg")
            minqlx.console_command("reset weapon_reload_gl")
            minqlx.console_command("reset weapon_reload_gauntlet")
            minqlx.console_command("reset weapon_reload_cg")
            minqlx.console_command("reset weapon_reload_bfg")
            minqlx.set_cvar("qlx_excessive", "0")
            self.msg("Excessive weapons are disabled.")
            
    def handle_vote_called(self, caller, vote, args):
        if not (self.get_cvar("g_allowSpecVote", bool)) and caller.team == "spectator":
            if caller.privileges == None:
                caller.tell("You are not allowed to call a vote as spectator.")
                return minqlx.RET_STOP_ALL

        # Handle new mute vote (with timeout)
        if vote.lower() == "mute":
            if not self.check_cv_flag(CV_FLAG_MUTE):
                caller.tell("Mute voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
            # Check permission level
            required_level = self.get_cvar("qlx_mutevotelevel", int)
            if not self.db.has_permission(caller.steam_id, required_level):
                caller.tell("^1Insufficient privileges to call a mute vote.^7 Permission Level required: ^4{}^7.".format(required_level))
                return minqlx.RET_STOP_ALL
            
            # Parse target player
            try:
                target = self.player(args)
                if not target:
                    caller.tell("^2/cv mute <player id/name>^7 is the usage for this callvote command.")
                    return minqlx.RET_STOP_ALL
                
                # Don't allow muting admins
                if target.privileges:
                    caller.tell("You cannot vote to mute a privileged player.")
                    return minqlx.RET_STOP_ALL
                
                timeout = self.get_cvar("qlx_mutevotetimeout", int)
                self.pending_mute = (target, timeout)
                
                self.callvote("qlx custom_mute_vote", "mute player ^3{}^7 for ^3{}^7 seconds".format(
                    target.name, timeout))
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
                
            except (ValueError, minqlx.NonexistentPlayerError):
                caller.tell("^2/cv mute <player id/name>^7 is the usage for this callvote command.")
                return minqlx.RET_STOP_ALL

        # Handle new silence vote (with custom duration)
        if vote.lower() == "silence":
            if not self.check_cv_flag(CV_FLAG_SILENCE):
                caller.tell("Silence voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
            # Check permission level
            required_level = self.get_cvar("qlx_mutevotelevel", int)
            if not self.db.has_permission(caller.steam_id, required_level):
                caller.tell("^1Insufficient privileges to call a silence vote.^7 Permission Level required: ^4{}^7.".format(required_level))
                return minqlx.RET_STOP_ALL
            
            # Parse arguments: player id/name, duration, unit
            args_split = args.split()
            if len(args_split) < 3:
                caller.tell("^2/cv silence <player id/name> <duration> <seconds|minutes|hours|days>^7 is the usage for this callvote command.")
                return minqlx.RET_STOP_ALL
            
            try:
                target = self.player(args_split[0])
                duration = int(args_split[1])
                unit = args_split[2].lower()
                
                if not target:
                    caller.tell("Player not found.")
                    return minqlx.RET_STOP_ALL
                
                # Don't allow silencing admins
                if target.privileges:
                    caller.tell("You cannot vote to silence a privileged player.")
                    return minqlx.RET_STOP_ALL
                
                # Validate unit
                valid_units = ["seconds", "minutes", "hours", "days", "second", "minute", "hour", "day"]
                if unit not in valid_units:
                    caller.tell("^2/cv silence <player id/name> <duration> <seconds|minutes|hours|days>^7 is the usage for this callvote command.")
                    return minqlx.RET_STOP_ALL
                
                self.pending_silence = (target, duration, unit)
                
                self.callvote("qlx custom_silence_vote", "silence player ^3{}^7 for ^3{} {}^7".format(
                    target.name, duration, unit))
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
                
            except (ValueError, minqlx.NonexistentPlayerError):
                caller.tell("^2/cv silence <player id/name> <duration> <seconds|minutes|hours|days>^7 is the usage for this callvote command.")
                return minqlx.RET_STOP_ALL

        if vote.lower() == "infiniteammo":
            if not self.check_cv_flag(CV_FLAG_INFINITEAMMO):
                caller.tell("Infinite ammo voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
            # enables the '/cv infiniteammo [on/off]' command
            if args.lower() == "off":
                self.callvote("set g_infiniteAmmo 0", "infinite ammo: off")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            elif args.lower() == "on":
                self.callvote("set g_infiniteAmmo 1", "infinite ammo: on")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            else:
                caller.tell("^2/cv infiniteammo [on/off]^7 is the usage for this callvote command.")
                return minqlx.RET_STOP_ALL

        if vote.lower() == "freecam":
            if not self.check_cv_flag(CV_FLAG_FREECAM):
                caller.tell("Freecam voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
            # enables the '/cv freecam [on/off]' command
            if args.lower() == "off":
                self.callvote("set g_teamSpecFreeCam 0", "team spectator free-cam: off")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            elif args.lower() == "on":
                self.callvote("set g_teamSpecFreeCam 1", "team spectator free-cam: on")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            else:
                caller.tell("^2/cv freecam [on/off]^7 is the usage for this callvote command.")
                return minqlx.RET_STOP_ALL

        if vote.lower() == "floordamage":
            if not self.check_cv_flag(CV_FLAG_FLOORDAMAGE):
                caller.tell("Floor damage voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
            # enables the '/cv floordamage [on/off]' command
            if args.lower() == "off":
                self.callvote("set g_forceDmgThroughSurface 0", "damage through floor: off")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            elif args.lower() == "on":
                self.callvote("set g_forceDmgThroughSurface 1", "damage through floor: on")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            else:
                caller.tell("^2/cv floordamage [on/off]^7 is the usage for this callvote command.")
                return minqlx.RET_STOP_ALL

        if vote.lower() == "alltalk":
            if not self.check_cv_flag(CV_FLAG_ALLTALK):
                caller.tell("Alltalk voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
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

        if vote.lower() == "allready":
            if not self.check_cv_flag(CV_FLAG_ALLREADY):
                caller.tell("Allready voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
            # enables the '/cv allready' command
            if self.game.state == "warmup":
                self.callvote("allready", "begin game immediately")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            else:
                caller.tell("You can't vote to begin the game when the game is already on.")
                return minqlx.RET_STOP_ALL

        if vote.lower() == "ruleset":
            # enables the '/cv ruleset [pql/vql]' command
            if (minqlx.get_cvar("qlx_rulesetLocked")) == "1":
                caller.tell("Voting to change the ruleset is disabled on ruleset-locked servers.")
                return minqlx.RET_STOP_ALL

            if args.lower() == "pql":
                self.callvote("qlx !ruleset pql", "ruleset: pql")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            elif args.lower() == "vql":
                self.callvote("qlx !ruleset vql", "ruleset: vql")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            else:
                caller.tell("^2/cv ruleset [pql/vql]^7 is the usage for this callvote command.")
                return minqlx.RET_STOP_ALL
            
        if vote.lower() == "abort":
            if not self.check_cv_flag(CV_FLAG_ABORT):
                caller.tell("Abort voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
            # enables the '/cv abort' command
            if self.game.state != "warmup":
                self.callvote("abort", "abort the game", 30)
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            else:
                caller.tell("You can't vote to abort the game when the game isn't in progress.")
                return minqlx.RET_STOP_ALL

        if vote.lower() == "chatsounds":
            if not self.check_cv_flag(CV_FLAG_CHATSOUNDS):
                caller.tell("Chatsounds voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
            # enables the '/cv chatsounds [on/off]' command
            if args.lower() == "off":
                self.callvote("qlx !unload fun", "chat-activated sounds: off")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            elif args.lower() == "on":
                self.callvote("qlx !load fun", "chat-activated sounds: on")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            else:
                caller.tell("^2/cv chatsounds [on/off]^7 is the usage for this callvote command.")
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

        if vote.lower() == "tempban":
            if not self.check_cv_flag(CV_FLAG_TEMPBAN):
                caller.tell("Tempban voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
            # enables the '/cv tempban <id>' command
            if self.get_cvar("qlx_disablePlayerRemoval", bool):
                # if player removal cvar is set, do not permit '/cv tempban'
                if caller.privileges == None:
                    caller.tell("Voting to tempban is disabled in this server.")
                    caller.tell("^2/cv spec <id>^7 and ^2/cv silence <id>^7 exist as substitutes to kicking/tempbanning.")
                    return minqlx.RET_STOP_ALL
            try:
                player_name = self.player(int(args)).clean_name
                player_id = self.player(int(args)).id
            except:
                caller.tell("^1Invalid ID.^7 Use a client ID from the ^2/players^7 command.")
                return minqlx.RET_STOP_ALL

            if self.player(int(args)).privileges != None:
                caller.tell("The player specified is an admin, a mod or banned, and cannot be tempbanned.")
                return minqlx.RET_STOP_ALL
            
            self.callvote("tempban {}".format(player_id), "^1ban {} until the map changes^3".format(player_name))
            self.msg("{}^7 called a vote.".format(caller.name))
            return minqlx.RET_STOP_ALL

        if vote.lower() == "spec":
            if not self.check_cv_flag(CV_FLAG_SPEC):
                caller.tell("Spec voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
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

        if vote.lower() == "excessive":
            if not self.check_cv_flag(CV_FLAG_EXCESSIVE):
                caller.tell("Excessive voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
            # enables the '/cv excessive [on/off]' command
            if args.lower() == "off":
                self.callvote("qlx !excessiveweaps off", "excessive weapons: off")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            elif args.lower() == "on":
                self.callvote("qlx !excessiveweaps on", "excessive weapons: on")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            else:
                caller.tell("^2/cv excessive [on/off]^7 is the usage for this callvote command.")
                return minqlx.RET_STOP_ALL

        if vote.lower() in ("kick", "clientkick"):
            if not self.check_cv_flag(CV_FLAG_KICK):
                caller.tell("Kick voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
            # if player removal cvar is set, do not permit '/cv kick' or '/cv clientkick'
            if self.get_cvar("qlx_disablePlayerRemoval", bool):
                if caller.privileges == None:
                    caller.tell("Voting to kick/clientkick is disabled in this server.")
                    caller.tell("^2/cv spec <id>^7 and ^2/cv silence <id>^7 exist as substitutes to kicking.")
                    return minqlx.RET_STOP_ALL

        if vote.lower() == "lock":
            if not self.check_cv_flag(CV_FLAG_LOCK):
                caller.tell("Lock voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
            # enables the '/cv lock <team>' command
            if len(args) <= 1:
                self.callvote("lock", "lock all teams")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            else:
                if args.lower() == "blue":
                    self.callvote("lock blue", "lock the ^4blue^3 team")
                    self.msg("{}^7 called a vote.".format(caller.name))
                    return minqlx.RET_STOP_ALL
                elif args.lower() == "red":
                    self.callvote("lock red", "lock the ^1red^3 team")
                    self.msg("{}^7 called a vote.".format(caller.name))
                    return minqlx.RET_STOP_ALL
                else:
                    caller.tell("^2/cv lock^7 or ^2/cv lock <blue/red>^7 is the usage for this callvote command.")
                    return minqlx.RET_STOP_ALL

        if vote.lower() == "unlock":
            if not self.check_cv_flag(CV_FLAG_UNLOCK):
                caller.tell("Unlock voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
            # enables the '/cv unlock <team>' command
            if len(args) <= 1:
                self.callvote("unlock", "unlock all teams")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            else:
                if args.lower() == "blue":
                    self.callvote("unlock blue", "unlock the ^4blue^3 team")
                    self.msg("{}^7 called a vote.".format(caller.name))
                    return minqlx.RET_STOP_ALL
                elif args.lower() == "red":
                    self.callvote("unlock red", "unlock the ^1red^3 team")
                    self.msg("{}^7 called a vote.".format(caller.name))
                    return minqlx.RET_STOP_ALL
                else:
                    caller.tell("^2/cv unlock^7 or ^2/cv unlock <blue/red>^7 is the usage for this callvote command.")
                    return minqlx.RET_STOP_ALL

        if vote.lower() == "balancing":
            if not self.check_cv_flag(CV_FLAG_BALANCING):
                caller.tell("Balancing voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
            # enables the '/cv balancing on/off' command
            if args.lower() == "off":
                self.callvote("qlx !unload balance", "glicko-based team balancing: off")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            elif args.lower() == "on":
                self.callvote("qlx !load balance", "glicko-based team balancing: on")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            else:
                caller.tell("^2/cv balancing [on/off]^7 is the usage for this callvote command.")
                return minqlx.RET_STOP_ALL

        if vote.lower() == "roundtimelimit":
            if not self.check_cv_flag(CV_FLAG_ROUNDTIMELIMIT):
                caller.tell("Round time limit voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
            # enables the '/cv roundtimelimit [90/120/180]' command
            if args.lower() == "180":
                self.callvote("set roundtimelimit 180", "round time limit: 180")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            if args.lower() == "120":
                self.callvote("set roundtimelimit 120", "round time limit: 120")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            if args.lower() == "90":
                self.callvote("set roundtimelimit 90", "round time limit: 90")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            else:
                caller.tell("^2/cv roundtimelimit [90/120/180]^7 is the usage for this callvote command.")
                return minqlx.RET_STOP_ALL

        if vote.lower() == "balance":
            if not self.check_cv_flag(CV_FLAG_BALANCE):
                caller.tell("Balance voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
            # enables the '/cv balance' command
            self.callvote("qlx !balance", "balance the teams")
            self.msg("{}^7 called a vote.".format(caller.name))
            return minqlx.RET_STOP_ALL

        if vote.lower() == "lgammo":
            if not self.check_cv_flag(CV_FLAG_LGAMMO):
                caller.tell("LG ammo voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
            # enables the '/cv lgammo [150/200]' command
            if args.lower() == "150":
                self.callvote("set g_startingAmmo_lg 150", "Lightning gun ammo: 150")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            if args.lower() == "200":
                self.callvote("set g_startingAmmo_lg 200", "Lightning gun ammo: 200")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            else:
                caller.tell("^2/cv lgammo [150/200]^7 is the usage for this callvote command.")
                return minqlx.RET_STOP_ALL

        if vote.lower() == "glammo":
            if not self.check_cv_flag(CV_FLAG_GLAMMO):
                caller.tell("GL ammo voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
            # enables the '/cv glammo [25/10/6]' command
            if args.lower() == "25":
                self.callvote("set g_startingAmmo_gl 25", "Grenade launcher ammo: 25")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            if args.lower() == "10":
                self.callvote("set g_startingAmmo_gl 10", "Grenade launcher ammo: 10")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            if args.lower() == "6":
                self.callvote("set g_startingAmmo_gl 6", "Grenade launcher ammo: 6")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            else:
                caller.tell("^2/cv glammo [25/10/6]^7 is the usage for this callvote command.")
                return minqlx.RET_STOP_ALL

        if vote.lower() == "lgdamage":
            if not self.check_cv_flag(CV_FLAG_LGDAMAGE):
                caller.tell("LG damage voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
            # enables the '/cv lgdamage [6/7]' command
            if args.lower() == "6":
                self.callvote("set g_damage_lg 6; set g_knockback_lg 1.75", "^7Lightning gun damage: 6")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            if args.lower() == "7":
                self.callvote("set g_damage_lg 7; set g_knockback_lg 1.50", "^7Lightning gun damage: 7 (with appropriate knockback)")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            else:
                caller.tell("^2/cv lgdamage [6/7]^7 is the usage for this callvote command.")
                return minqlx.RET_STOP_ALL

        if vote.lower() == "rgdamage":
            if not self.check_cv_flag(CV_FLAG_RGDAMAGE):
                caller.tell("RG damage voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
            # enables the '/cv rgdamage [80/100]' command
            if args.lower() == "80":
                self.callvote("set g_damage_rg 80", "^2Railgun^3 damage: 80")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            if args.lower() == "100":
                self.callvote("set g_damage_rg 100", "^2Railgun^3 damage: 100")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            else:
                caller.tell("^2/cv rgdamage [80/100]^7 is the usage for this callvote command.")
                return minqlx.RET_STOP_ALL

        if vote.lower() == "runes":
            if not self.check_cv_flag(CV_FLAG_RUNES):
                caller.tell("Runes voting is disabled on this server.")
                return minqlx.RET_STOP_ALL
            
            # enables the '/cv runes on/off' command
            if self.game.state != "warmup":
                caller.tell("Voting to alter runes is only allowed during the warm-up period.")
                return minqlx.RET_STOP_ALL
            
            if args.lower() == "off":
                self.callvote("set g_runes 0; map_restart", "runes: off")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            elif args.lower() == "on":
                self.callvote("set g_runes 1; map_restart", "runes: on")
                self.msg("{}^7 called a vote.".format(caller.name))
                return minqlx.RET_STOP_ALL
            else:
                caller.tell("^2/cv runes [on/off]^7 is the usage for this callvote command.")
                return minqlx.RET_STOP_ALL

        if vote.lower() == "cvar":
            if not self.get_cvar("qlx_disableCvarVoting", bool):
                if not len(args) <= 1:
                    # enables the '/cv cvar <variable> <value>' command
                    if self.db.has_permission(caller.steam_id, self.get_cvar("qlx_cvarVotePermissionRequired", int)):
                        self.callvote("set {}".format(args), "Server CVAR change: {}^3".format(args))
                        self.msg("{}^7 called a server vote.".format(caller.name))
                        return minqlx.RET_STOP_ALL
                    else:
                        caller.tell("^1Insufficient privileges to change a server cvar.^7 Permission Level required: ^43^7.")
                        return minqlx.RET_STOP_ALL
                else:
                    caller.tell("^2/cv cvar <variable> <value>^7 is the usage for this callvote command.")
                    return minqlx.RET_STOP_ALL
            else:
                caller.tell("Voting to change server CVARs is disabled on this server.")
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

