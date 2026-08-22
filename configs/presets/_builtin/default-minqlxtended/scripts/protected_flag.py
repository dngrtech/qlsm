"""Protect Quake Live country flags behind per-flag SteamID64 whitelists."""

import minqlxtended


PROTECTED_CODES_CVAR = "qlx_protectedFlags"
LEGACY_PROTECTED_CODE_CVAR = "qlx_protectedFlagCode"
ADMIN_PERMISSION_CVAR = "qlx_protectedFlagAdmin"
KEY_TEMPLATE = "minqlx:protected_flag:{}:steamids"
STEAMID64_INDIVIDUAL_BASE = 76561197960265728
STEAMID64_INDIVIDUAL_MAX = STEAMID64_INDIVIDUAL_BASE + 0xFFFFFFFF
FLAGLIST_PAGE_SIZE = 20


def normalize_country(value):
    """Return a normalized Quake Live country code."""
    return str(value or "").strip().lower()


def parse_protected_codes(value):
    """Parse a comma/whitespace-separated list while preserving order."""
    codes = []
    for token in str(value or "").replace(",", " ").split():
        code = normalize_country(token)
        is_valid = (
            1 <= len(code) <= 32
            and code.isascii()
            and code[0].isalnum()
            and all(character.isalnum() or character in "_-" for character in code)
        )
        if is_valid and code not in codes:
            codes.append(code)
    return tuple(codes)


class protected_flag(minqlxtended.Plugin):
    """Restrict configured country codes to per-flag Redis whitelists."""

    def __init__(self):
        super().__init__()
        self.set_cvar_once(ADMIN_PERMISSION_CVAR, "5")

        configured_value = self.get_cvar(PROTECTED_CODES_CVAR)
        if configured_value is None:
            configured_value = self.get_cvar(LEGACY_PROTECTED_CODE_CVAR)
        if configured_value is None:
            self.set_cvar_once(PROTECTED_CODES_CVAR, "x76")
            configured_value = self.get_cvar(PROTECTED_CODES_CVAR)

        configured_codes = parse_protected_codes(configured_value)
        if not configured_codes:
            configured_codes = ("x76",)
        self.protected_codes = frozenset(configured_codes)
        self.protected_code = configured_codes[0]
        self.whitelist_key = self.whitelist_key_for(self.protected_code)

        self.add_hook("userinfo", self.handle_userinfo, priority=minqlxtended.Priority.LOWEST)
        self.add_hook("player_loaded", self.handle_player_loaded)
        admin_permission = self.get_cvar(ADMIN_PERMISSION_CVAR, int)
        self.add_command(
            "flagadd",
            self.cmd_flagadd,
            admin_permission,
            usage="<player> | <flag> <player>",
        )
        self.add_command(
            "flagdel",
            self.cmd_flagdel,
            admin_permission,
            usage="<player> | <flag> <player>",
        )
        self.add_command(
            "flaglist",
            self.cmd_flaglist,
            admin_permission,
            usage="[flag] [cursor]",
        )

    @staticmethod
    def _member_to_text(member):
        if isinstance(member, bytes):
            return member.decode("ascii")
        return str(member)

    @staticmethod
    def whitelist_key_for(code):
        return KEY_TEMPLATE.format(normalize_country(code))

    def is_authorized(self, code, steam_id=None):
        if steam_id is None:
            steam_id = code
            code = self.protected_code
        try:
            return bool(self.db.sismember(self.whitelist_key_for(code), str(steam_id)))
        except Exception:
            self.logger.exception("Failed to read protected flag whitelist")
            return False

    @staticmethod
    def is_valid_steam_id(steam_id):
        value = str(steam_id)
        if len(value) != 17 or not value.isascii() or not value.isdecimal():
            return False
        numeric_value = int(value)
        return STEAMID64_INDIVIDUAL_BASE < numeric_value <= STEAMID64_INDIVIDUAL_MAX

    def reply_storage_error(self, channel, code=None, action="update"):
        channel.reply(
            "^1Could not {} the {} flag whitelist.".format(
                action, code or self.protected_code
            )
        )

    def handle_userinfo(self, player, changed, infostring):
        country = normalize_country(changed.get("country"))
        if country not in self.protected_codes:
            return None
        if self.is_authorized(country, player.steam_id):
            return None
        changed["country"] = ""
        return changed

    def handle_player_loaded(self, player):
        self.check_loaded_player(player.id, player.steam_id)

    @minqlxtended.delay(1)
    def check_loaded_player(self, client_id, expected_steam_id):
        try:
            player = self.player(client_id)
            if player.steam_id != expected_steam_id:
                return
            country = normalize_country(player.country)
            if country not in self.protected_codes:
                return
            if self.is_authorized(country, player.steam_id):
                return
            player.country = ""
        except minqlxtended.NonexistentPlayerError:
            return

    def parse_flag_and_steam_id(self, msg):
        if len(msg) == 2:
            code, identifier = self.protected_code, msg[1]
        elif len(msg) == 3:
            code, identifier = normalize_country(msg[1]), msg[2]
        else:
            return None
        if code not in self.protected_codes:
            return None

        identifier = str(identifier)
        if (
            len(identifier) <= 17
            and identifier.isascii()
            and identifier.isdecimal()
            and int(identifier) < 64
        ):
            try:
                return code, str(self.player(int(identifier)).steam_id)
            except minqlxtended.NonexistentPlayerError:
                return code, None
        if not self.is_valid_steam_id(identifier):
            return None
        return code, identifier

    def cmd_flagadd(self, _player, msg, channel):
        parsed = self.parse_flag_and_steam_id(msg)
        if parsed is None:
            return minqlxtended.Return.USAGE
        code, steam_id = parsed
        if steam_id is None:
            channel.reply("^1Invalid client ID. Use either a client ID or a SteamID64.")
            return
        whitelist_key = self.whitelist_key_for(code)
        try:
            added = self.db.sadd(whitelist_key, steam_id)
        except Exception:
            self.logger.exception("Failed to add protected flag whitelist member")
            self.reply_storage_error(channel, code=code)
            return
        if not added:
            channel.reply(
                "^3{} is already allowed to use the {} flag.".format(steam_id, code)
            )
            return
        channel.reply("^2Added ^7{}^2 to the {} flag whitelist.".format(steam_id, code))

    def cmd_flagdel(self, _player, msg, channel):
        parsed = self.parse_flag_and_steam_id(msg)
        if parsed is None:
            return minqlxtended.Return.USAGE
        code, steam_id = parsed
        if steam_id is None:
            channel.reply("^1Invalid client ID. Use either a client ID or a SteamID64.")
            return
        whitelist_key = self.whitelist_key_for(code)
        try:
            removed = self.db.srem(whitelist_key, steam_id)
        except Exception:
            self.logger.exception("Failed to remove protected flag whitelist member")
            self.reply_storage_error(channel, code=code)
            return
        if not removed:
            channel.reply(
                "^3{} is not in the {} flag whitelist.".format(steam_id, code)
            )
            return
        channel.reply(
            "^2Removed ^7{}^2 from the {} flag whitelist.".format(steam_id, code)
        )

    def cmd_flaglist(self, _player, msg, channel):
        if len(msg) == 1 and len(self.protected_codes) > 1:
            channel.reply(
                "^2Protected flags:^7 {}".format(
                    ", ".join(sorted(self.protected_codes))
                )
            )
            return

        cursor = 0
        offset = 0
        if len(msg) == 1:
            code = self.protected_code
        elif len(msg) in (2, 3):
            code = normalize_country(msg[1])
            if len(msg) == 3:
                cursor_parts = str(msg[2]).split(":")
                if len(cursor_parts) not in (1, 2) or any(
                    not part.isascii() or not part.isdecimal() or len(part) > 20
                    for part in cursor_parts
                ):
                    return minqlxtended.Return.USAGE
                cursor = int(cursor_parts[0])
                if len(cursor_parts) == 2:
                    offset = int(cursor_parts[1])
        else:
            return minqlxtended.Return.USAGE
        if code not in self.protected_codes:
            return minqlxtended.Return.USAGE

        whitelist_key = self.whitelist_key_for(code)
        try:
            next_cursor, raw_members = self.db.sscan(
                whitelist_key, cursor=cursor, count=FLAGLIST_PAGE_SIZE
            )
        except Exception:
            self.logger.exception("Failed to scan protected flag whitelist members")
            self.reply_storage_error(channel, code=code, action="read")
            return

        raw_members = list(raw_members)
        page_end = offset + FLAGLIST_PAGE_SIZE
        members = []
        for raw_member in raw_members[offset:page_end]:
            try:
                member = self._member_to_text(raw_member)
            except (UnicodeDecodeError, UnicodeEncodeError):
                continue
            if self.is_valid_steam_id(member):
                members.append(member)
        members.sort(key=int)

        if members:
            reply = "^2{} flag whitelist:^7 {}".format(code, ", ".join(members))
        else:
            reply = "^3The {} flag whitelist is empty.".format(code)
        if page_end < len(raw_members):
            reply += "^3 [next cursor: {}:{}]".format(cursor, page_end)
        elif int(next_cursor):
            reply += "^3 [next cursor: {}]".format(next_cursor)
        channel.reply(reply)
