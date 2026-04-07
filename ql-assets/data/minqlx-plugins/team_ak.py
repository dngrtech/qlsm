import minqlx
import random

class team_ak(minqlx.Plugin):
    def __init__(self):
        self.add_hook("game_countdown", self.on_game_countdown)
        self.add_hook("round_end", self.on_round_end)
        self.add_hook("player_spawn", self.on_spawn)
        self.add_hook("map", self.on_map_load)
        self.add_command("arenatele", self.cmd_arenatele, 3)
        self.add_command("arenashuffle", self.cmd_arenashuffle, 1)

        self.ARENAMODE_ACTIVE = False
        self.CURRENT_ARENA_SPAWN = {}
        self.ARENA_SPAWN_POINTS = {}
        self.PLAYER_OFFSETS = [
        (0, 0),
        (60, 60),
        (-60, -60),
        (60, -60),
        (60, 0),
        (-60, 0),
        (0, 60),
        (0, -60),
        (-60, 60),
        ]

        # define all supported maps and their spawns here
        self.ARENA_MAP_SPAWNS = {
            "gridlock": {
                1: {"team_red": (640, 376, 128), "team_blue": (640, 776, 128)},
                2: {"team_red": (2048, 376, 128), "team_blue": (2048, 776, 128)},
            },
            "4charon": {
                1: {"team_red": (2224, 2224, 448),  "team_blue": (1856, 752, 288)},
                2: {"team_red": (2080, -404, 240), "team_blue": (1232, -432, 256)},
                3: {"team_red": (160, -368, 224), "team_blue": (-17, 222, 210)},
                4: {"team_red": (512, 3712, 496), "team_blue": (512, 4432, 432)},
            },
            "4ak": {
                1: {"team_red": (-1824, -160, 128), "team_blue": (-1812, -115, 344)},
                2: {"team_red": (32, 320, -128), "team_blue": (-271, -25, -135)},
                3: {"team_red": (-1824, -1716, -34), "team_blue": (-1479, -1329, -100)},
                4: {"team_red": (-864, -1313, -205), "team_blue": (-864, -887, -205)},
            },
            "akclassics": {
                1: {"team_red": (-1248, -2432, 800), "team_blue": (-1280, -1616, 208)},
                2: {"team_red": (-1536, 240, 1088), "team_blue": (-1536, -448, 1088)},
                3: {"team_red": (0, 320, 544), "team_blue": (368, -64, 544)},
                4: {"team_red": (1520, 688, -304), "team_blue": (2624, 352, 32)},
                5: {"team_red": (2192, -704, 32), "team_blue": (1712, -1296, 96)},
                6: {"team_red": (864, -2720, 528), "team_blue": (128, -2720, 544)},
            },
            "techtowerak": {
                1: {"team_red": (312, -217, 216), "team_blue": (78, -215, 216)},
                2: {"team_red": (446, 786, 88), "team_blue": (-60, 501, 152)},
                3: {"team_red": (-695, -392, 24), "team_blue": (-339, -390, 248)},
                4: {"team_red": (985, -217, 312), "team_blue": (1377, -213, 312)},
                5: {"team_red": (-705, 559, 280), "team_blue": (-1180, 559, 280)},
                6: {"team_red": (-71, 524, -87), "team_blue": (-6, 78, -71)},
            },
            "arcticak": {
                1: {"team_red": (264, 263, 360), "team_blue": (134, -122, 360)},
                2: {"team_red": (1245, 115, 312), "team_blue": (1618, 42, 312)},
                3: {"team_red": (714, -722, 184), "team_blue": (718, -920, 184)},
                4: {"team_red": (-1002, -1016, 280), "team_blue": (-214, -1027, 280)},
                5: {"team_red": (-317, 1855, 440), "team_blue": (-994, 1195, 440)},
                6: {"team_red": (424, 891, 568), "team_blue": (371, 1249, 568)},
            },
            "tdak1": {
                1: {"team_red": (736, -144, 608), "team_blue": (-160, 448, 608)},
                2: {"team_red": (-672, -1552, -160), "team_blue": (272, -1840, 96)},
                3: {"team_red": (1648, -1296, 448), "team_blue": (1904, 48, 512)},
                4: {"team_red": (1584, 976, 592), "team_blue": (2848, 2032, 48)},
            },
            "tdak2": {
                1: {"team_red": (480, 2000, -16), "team_blue": (80, 1568, -16)},
                2: {"team_red": (80, 464, 16), "team_blue": (-480, -512, 16)},
                3: {"team_red": (-1232, -288, -336), "team_blue": (-2464, -160, -320)},
                4: {"team_red": (-1680, 1440, -96), "team_blue": (-2640, 3312, 192)},
            },
            "tdak3": {
                1: {"team_red": (-80, 1184, -496), "team_blue": (-368, 2272, -240)},
                2: {"team_red": (3152, 1920, 112), "team_blue": (1296, 1584, -144)},
                3: {"team_red": (-16, 48, 64), "team_blue": (960, -800, 112)},
                4: {"team_red": (2016, -656, -32), "team_blue": (3232, 288, -16)},
            },
        }

    def on_map_load(self, data, mapdata):
        arena_spawns = self.ARENA_MAP_SPAWNS.get(self.game.map.lower())
        if arena_spawns:
            self.ARENAMODE_ACTIVE = True
            self.ARENA_SPAWN_POINTS = arena_spawns
            self.shuffle_arena_spawn()
        else:
            self.ARENAMODE_ACTIVE = False
            self.CURRENT_ARENA_SPAWN = {}

    def on_game_countdown(self):
        if self.ARENAMODE_ACTIVE:
            self.shuffle_arena_spawn()

    def on_round_end(self, data):
        if self.ARENAMODE_ACTIVE:
            self.shuffle_arena_spawn()

    @minqlx.next_frame
    def on_spawn(self, player):
        if not self.ARENAMODE_ACTIVE:
            return

        team_players = self.teams()[player.team]
        try:
            index = team_players.index(player)
        except ValueError:
            index = 0

        offset = self.PLAYER_OFFSETS[index % len(self.PLAYER_OFFSETS)]
        x_off, y_off = offset

        if player.team == "red":
            x, y, z = self.CURRENT_ARENA_SPAWN['team_red']
        else:
            x, y, z = self.CURRENT_ARENA_SPAWN['team_blue']

        player.position(x=x + x_off, y=y + y_off, z=z + 96)


    def shuffle_arena_spawn(self):
        # randomly change arenas
        spawn_id, spawn_data = random.choice(list(self.ARENA_SPAWN_POINTS.items()))

        #make sure same arena isn't played twice in a row
        while (spawn_id == self.CURRENT_ARENA_SPAWN.get("spawn_id")):
            spawn_id, spawn_data = random.choice(list(self.ARENA_SPAWN_POINTS.items()))

        # randomly change red/blue spawns
        if random.choice([True, False]):
            red_pos = spawn_data["team_red"]
            blue_pos = spawn_data["team_blue"]
        else:
            red_pos = spawn_data["team_blue"]
            blue_pos = spawn_data["team_red"]

        self.CURRENT_ARENA_SPAWN = {
            "spawn_id": spawn_id,
            "team_red": red_pos,
            "team_blue": blue_pos,
        }

    def cmd_arenashuffle(self, player, msg, channel):
        if self.ARENAMODE_ACTIVE:
            self.shuffle_arena_spawn()
            channel.reply(f"Arena shuffled to spawn {self.CURRENT_ARENA_SPAWN['spawn_id']}.")
        else:
            channel.reply("Arena mode is not active.")

    def cmd_arenatele(self, player, msg, channel):
        if not self.ARENAMODE_ACTIVE:
            channel.reply("Arena mode is not active.")
            return
        if len(msg) < 3:
            return minqlx.RET_USAGE
        try:
            player_id = int(msg[1])
            target_player = self.player(player_id)
            if not target_player:
                channel.reply("No player with that ID.")
                return
        except ValueError:
            channel.reply("Invalid player ID.")
            return

        try:
            arenaid = int(msg[2])
            coords = self.ARENA_SPAWN_POINTS.get(arenaid)
            if not coords:
                channel.reply("Invalid arena ID.")
                return

            if target_player.team == "red":
                x, y, z = coords["team_red"]
            else:
                x, y, z = coords["team_blue"]
            target_player.position(x=x, y=y, z=z)
        except Exception as e:
            channel.reply(f"{type(e).__name__}: {e}")


