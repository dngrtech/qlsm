import minqlx
import re
import os
import datetime

_re_remove_excessive_colors = re.compile(r"(?:\^.)+(\^.)")
_name_key = "minqlx:players:{}:colored_name"
LOG_FILE = os.path.join(os.path.dirname(__file__), "namesplus.log")

VERSION = "1.6.0"

class namesplus(minqlx.Plugin):
    def __init__(self):
        self.add_hook("player_connect", self.handle_player_connect)
        self.add_hook("player_loaded", self.handle_player_loaded)
        self.add_hook("player_disconnect", self.handle_player_disconnect)
        self.add_hook("userinfo", self.handle_userinfo)
        self.add_command("name", self.cmd_name, usage="<name>")
        self.add_command("setname", self.cmd_setname_admin, usage="<player id> <name>", permission=4)
        self.add_command("clear", self.cmd_clear_name, usage="<player id>", permission=4)
        self.add_command("npv", self.cmd_version)
        self.add_command("listnames", self.cmd_list_names, permission=3)
        self.add_command("enforce", self.cmd_enforce, permission=4)
        
        self.set_cvar_once("qlx_enforceSteamName", "0")
        self.steam_names = {}
        self.name_set = False
        
        self.set_cvar_once("qlx_enforceAdminName", "1")

    def handle_player_connect(self, player):
        self.steam_names[player.steam_id] = player.clean_name

    def handle_player_loaded(self, player):
        name_key = _name_key.format(player.steam_id)
        if name_key in self.db:
            db_name = self.db[name_key]
            if not self.get_cvar("qlx_enforceSteamName", bool) or self.clean_text(db_name).lower() == player.clean_name.lower():
                self.name_set = True
                player.name = db_name
                self.log_debug(f"Set loaded name for {player.id} ({player.clean_name}) to: {db_name}")

    def handle_player_disconnect(self, player, reason):
        self.steam_names.pop(player.steam_id, None)

    def handle_game_start(self, data):
        if not self.get_cvar("qlx_enforceAdminName", bool):
            return

        enforced_count = 0
        for p in self.players():
            name_key = _name_key.format(p.steam_id)
            if name_key in self.db:
                stored_name = self.db[name_key]
                if p.name != stored_name:
                    self.name_set = True
                    p.name = stored_name
                    p.tell(f"^3Your name has been updated to: {stored_name}")
                    enforced_count += 1

        self.log_debug(f"Automatically enforced {enforced_count} player names on game start.")

    def handle_userinfo(self, player, changed):
        if self.name_set:
            self.name_set = False
            return

        name_key = _name_key.format(player.steam_id)

        # Enforce admin-set names if qlx_enforceAdminName is enabled
        if self.get_cvar("qlx_enforceAdminName", bool) and name_key in self.db:
            changed["name"] = self.db[name_key]  # Restore admin-set name
            player.name = stored_name  # Force name update immediately
            player.tell(f"^3Your name has been updated to: {self.db[name_key]}")  # Notify player
            return changed

        # Regular name handling
        if "name" in changed:
            if name_key not in self.db:
                self.steam_names[player.steam_id] = self.clean_text(changed["name"])
            elif self.steam_names.get(player.steam_id) == self.clean_text(changed["name"]):
                changed["name"] = self.db[name_key]
                player.name = stored_name  # Force name update immediately
                player.tell(f"^3Your name has been updated to: {self.db[name_key]}")  # Notify player
                return changed
            else:
                del self.db[name_key]
                player.tell("Your registered name has been reset.")

    def cmd_name(self, player, msg, channel):
        name_key = _name_key.format(player.steam_id)

        if len(msg) < 2:
            if name_key in self.db:
                del self.db[name_key]
                player.tell("Your registered name has been removed.")
                return minqlx.RET_STOP_ALL
            return minqlx.RET_USAGE

        name = self.clean_excessive_colors(" ".join(msg[1:])).strip()
        if not self.validate_name(player, name):
            return minqlx.RET_STOP_ALL

        name = "^7" + name
        self.name_set = True
        player.name = name
        self.db[name_key] = name
        player.tell("The name has been registered. To remove it, use ^6!name^7 with no arguments.")
        self.log_debug(f"Player {player.id} set their name to: {name}")
        return minqlx.RET_STOP_ALL

    def cmd_setname_admin(self, player, msg, channel):
        if len(msg) < 3:
            return minqlx.RET_USAGE

        target_id = msg[1]
    
        try:
            if target_id.isdigit():
                target = self.player(int(target_id))  # Try fetching player by Player ID
                steam_id = target.steam_id if target else int(target_id)  # Use Steam ID if offline
            else:
                player.tell("Invalid ID format. Use a Player ID or Steam ID.")
                return minqlx.RET_STOP_ALL
        except Exception:
            player.tell("Player not found or invalid ID.")
            return minqlx.RET_STOP_ALL

        name = self.clean_excessive_colors(" ".join(msg[2:])).strip()
        if not self.validate_name(player, name, admin_override=True):
            return minqlx.RET_STOP_ALL

        name = "^7" + name
        self.db[_name_key.format(steam_id)] = name  # Store name in Redis using Steam ID

        if target:
            self.name_set = True
            target.name = name
            target.tell(f"^3An admin has set your name to: {name}")

        player.tell(f"Set name for Steam ID {steam_id} to: {name}")
        self.log_debug(f"Admin {player.id} set name for Steam ID {steam_id} to: {name}")

        return minqlx.RET_STOP_ALL

    def cmd_clear_name(self, player, msg, channel):
        if len(msg) != 2:
            return minqlx.RET_USAGE

        target_id = msg[1]

        try:
            if target_id.isdigit():
                target = self.player(int(target_id))  # Try fetching player by Player ID
                steam_id = target.steam_id if target else int(target_id)  # Use Steam ID if offline
            else:
                player.tell("Invalid ID format. Use a Player ID or Steam ID.")
                return minqlx.RET_STOP_ALL
        except Exception:
            player.tell("Player not found or invalid ID.")
            return minqlx.RET_STOP_ALL

        name_key = _name_key.format(steam_id)

        if name_key in self.db:
            del self.db[name_key]
            player.tell(f"Cleared name override for Steam ID {steam_id}.")
            if target:
                target.tell("An admin has cleared your custom name.")
            self.log_debug(f"Admin {player.id} cleared name for Steam ID {steam_id}")
        else:
            player.tell("No custom name to clear.")

        return minqlx.RET_STOP_ALL

    def cmd_version(self, player, msg, channel):
        player.tell(f"^3Namesplus version: ^7{VERSION}")

    def cmd_enforce(self, player, msg, channel):
        """Enforces stored names for currently connected players."""
        enforced_count = 0

        for p in self.players():  # Loop through all connected players
            name_key = _name_key.format(p.steam_id)  # Get stored name key

            if name_key in self.db:  # Check if the player has a stored name
                stored_name = self.db[name_key]

                if p.name != stored_name:  # If current name is different, update it
                    self.name_set = True
                    p.name = stored_name
                    p.tell(f"^3Your name has been updated to: {stored_name}")
                    enforced_count += 1

        player.tell(f"^3Enforced names for {enforced_count} players.")
        self.log_debug(f"Admin {player.id} enforced {enforced_count} player names.")

        return minqlx.RET_STOP_ALL
    
    def cmd_list_names(self, player, msg, channel):
        admin_names = []
    
        for key in self.db.keys("minqlx:players:*:colored_name"):  # Get all stored names
            steam_id = key.split(":")[2]  # Extract Steam ID from key format
            name = self.db[key]
            
            # Ensure Steam ID is always displayed in white, separate from colored names
            admin_names.append(f"^7Steam ID {steam_id}: {name}")

        if not admin_names:
            player.tell("^3No admin-set names found.")
        else:
            player.tell("^3Admin-set names:^7\n" + "\n".join(admin_names))

        return minqlx.RET_STOP_ALL

    def clean_excessive_colors(self, name):
        def sub_func(match):
            return match.group(1)
        return _re_remove_excessive_colors.sub(sub_func, name)

    def clean_text(self, text):
        return re.sub(r"\^.", "", text)

    def validate_name(self, player, name, admin_override=False):
        if len(name.encode()) > 36:
            player.tell("Name is too long. Try fewer colors or characters.")
            return False
        if "\\" in name:
            player.tell("Name cannot contain the '^6\\^7' character.")
            return False
        if not self.clean_text(name).strip():
            player.tell("Blank names are not allowed.")
            return False
        if not admin_override and self.get_cvar("qlx_enforceSteamName", bool):
            if self.clean_text(name).lower() != player.clean_name.lower():
                player.tell("Name must match your Steam name.")
                return False
        return True

    def log_debug(self, message):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        try:
            with open(LOG_FILE, "a") as f:
                f.write(log_entry)
        except Exception as e:
            self.logger.warning(f"Failed to write to log file: {e}")

