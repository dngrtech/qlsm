import minqlx
import time
import os
import re
import io

RECORDS_KEY = "minqlx:uberstats_records:{}"
WEAPON_RECORDS = {
                    "kill_machine": ["KILL MACHINE", "{:0.2f} frags/min"],
                    "counterstrike": ["BEST COUNTERSTRIKE PLAYER", "{:0.2f} K/D ratio"],
                    "most_damage": ["DESTRUCTICATOR", "{:,} dmg given"],
                    "longest_spree": ["RAMBO", "{} kill streak"],
                    "best_rail_accuracy": ["LASER EYES", "{:0.2f} percent rail accuracy"],
                    "most_nade_kills": ["PINEAPPLE POWER", "{} grenade frags"],
                    "most_pummels": ["PUMMEL LORD", "{} pummels"],
                    "most_dmg_taken": ["BIGGEST PINCUSHION", "{:,} dmg taken"],
                    "most_world_deaths": ["CLUMSIEST FOOL", "{:,} deaths by world"],
                    "most_dmg_per_kill": ["GOOD SAMARITAN", "{:0.2f} damage per frag"],
                    "most_lines_of_chat": ["BIGGEST CHATTERBOX", "{} lines of chat"]
                  }
FILE_PATTERN = re.compile('[\W_]+')

# Hex-colored spans for decimal color codes ^0 - ^9
_dec_spans = [
 '<span style="color: rgb(128,128,128);">',
 '<span style="color: rgb(255, 0, 0);">',
 '<span style="color: rgb(51, 255, 0);">',
 '<span style="color: rgb(255, 255, 0);">',
 '<span style="color: rgb(51,102,255);">',
 '<span style="color: rgb(51,255,255);">',
 '<span style="color: rgb(197,0,255);">',
 '<span style="color: rgb(255,255,255);">',
 '<span style="color: rgb(255,255,255);">',
 '<span style="color: rgb(255,255,255);">'
]
# Color code patterns
_dec_colors = re.compile(r'\^(\d)')
_all_colors = _dec_colors

class uberstats(minqlx.Plugin):

  def __init__(self):
    self.set_cvar_once("qlx_uberstats_sftp_hostname", "")
    self.set_cvar_once("qlx_uberstats_sftp_username", "")
    self.set_cvar_once("qlx_uberstats_sftp_password", "")
    self.set_cvar_once("qlx_uberstats_sftp_remote_path", "")

    self.sftp_hostname = self.get_cvar("qlx_uberstats_sftp_hostname")
    self.sftp_username = self.get_cvar("qlx_uberstats_sftp_username")
    self.sftp_password = self.get_cvar("qlx_uberstats_sftp_password")
    self.sftp_remote_path = self.get_cvar("qlx_uberstats_sftp_remote_path")

    self.add_command("score", self.cmd_score)
    self.add_command("highscores", self.cmd_highscores)    
    self.add_command("clearhighscores", self.cmd_clear_highscores, 5)

    self.add_hook("stats", self.handle_stats)
    self.add_hook("chat", self.handle_chat)
    self.add_hook("map", self.handle_map)
    self.add_hook("game_end", self.handle_game_end)

    self.weapons = ["PLASMA", "ROCKET", "PROXMINE", "RAILGUN", "CHAINGUN", "NAILGUN", "GRENADE", "LIGHTNING", "SHOTGUN", "MACHINEGUN", "HMG", "BFG", "GAUNTLET"]
    self.weapon_sprees = ["PLASMORGASM", "ROCKET RENEGADE", "MINE MASTER", "RAIL RANGER", "CHAIN GANG", "GNARLY NAILER", "GRENADE GOON", "LIGHTNING LASHER", "SHOTGUN SAMURAI", "MACHINEGUN PECKER", "HMG HARASSER", "BFG BOSS", "GUANTLET GOD"]
    self.kill_streak = {}
    for weapon in self.weapons:
      self.kill_streak[weapon] = {}

    self.outputted_accuracy_players = []
    self.kamikaze_stats = {}

    self.best_kpm_names = []
    self.best_kpm = 0

    self.best_kd_names = []
    self.best_kd = 0

    self.most_damage_names = []
    self.most_damage = 0

    self.longest_spree_names = []
    self.longest_spree = 0

    self.best_rail_accuracy_names = []
    self.best_rail_accuracy = 0
    self.best_rail_hits = 0
    self.best_rail_shots = 0

    self.most_nade_kills_names = []
    self.most_nade_kills = 0

    self.most_pummels_names = []
    self.most_pummels = 0

    self.most_dmg_taken_names = []
    self.most_dmg_taken = 0

    self.world_death_types = ["UNKNOWN", "WATER", "SLIME", "LAVA", "CRUSH", "FALLING", "TRIGGER_HURT", "HURT"]
    self.world_death_stats = {}
    self.most_world_deaths_names = []
    self.most_world_deaths = 0

    self.most_dmg_per_kill_names = []
    self.most_dmg_per_kill = 0

    self.most_lines_of_chat_stats = {}
    self.most_lines_of_chat_names = []
    self.most_lines_of_chat = 0

  def cmd_score(self, player, msg, channel):
    if player.team != "spectator":
      sorted_players = sorted(self.players(), key = lambda p: p.stats.score, reverse=True)
      player_index = sorted_players.index(player) + 1
      player.tell("^2{} - ^3Score: ^7{} - ^3K/D: ^7{} - ^3DMG: ^7{} - ^3TIME: ^7{} - ^3PING: ^7{}".format(
        self.ordinal(player_index),
        player.stats.score,
        str(player.stats.kills) + "/" + str(player.stats.deaths),
        player.stats.damage_dealt,
        int((player.stats.time/(1000*60))%60),
        player.stats.ping
      )
      )

  def handle_chat(self, player, msg, channel):
    if self.game is not None:
      if self.game.state == "in_progress" and channel == "chat" and str(player.steam_id)[:1] != "9":
        if player.name not in self.most_lines_of_chat_stats:
          self.most_lines_of_chat_stats[player.name] = 1
        else:
          self.most_lines_of_chat_stats[player.name] += 1

  def handle_stats(self, stats):
    if self.game is not None:
      if self.game.state == "in_progress":
        if stats['TYPE'] == "PLAYER_DEATH":
          if stats['DATA']['VICTIM']['STEAM_ID'] != "0":  # ignore bots
            victim_name = stats['DATA']['VICTIM']['NAME']

            #remove player from kill streak counters when they die
            for weapon in self.weapons:
              if self.kill_streak[weapon]:
                if victim_name in self.kill_streak[weapon]:
                  self.kill_streak[weapon][victim_name] = 0

            #count player world deaths
            if stats['DATA']['MOD'] in self.world_death_types:
              victim_name = stats['DATA']['VICTIM']['NAME']
              if victim_name not in self.world_death_stats:
                self.world_death_stats[victim_name] = 1
              else:
                self.world_death_stats[victim_name] += 1
        elif stats['TYPE'] == "PLAYER_KILL" and stats['DATA']['MOD'] in self.weapons:
          if stats['DATA']['KILLER']['STEAM_ID'] != "0":  # ignore bots
            killer_name = stats['DATA']['KILLER']['NAME']
            weapon = stats['DATA']['MOD']

            if killer_name != stats['DATA']['VICTIM']['NAME']:
              if killer_name not in self.kill_streak[weapon]:
                self.kill_streak[weapon][killer_name] = 1
              else:
                self.kill_streak[weapon][killer_name] += 1

              if self.kill_streak[weapon][killer_name] == 1:
                self.handle_kill_streak(killer_name, weapon)
        elif stats['TYPE'] == "PLAYER_KILL" and stats['DATA']['MOD'] == "KAMIKAZE":
          if stats['DATA']['KILLER']['STEAM_ID'] != "0":  # ignore bots
            killer_name = stats['DATA']['KILLER']['NAME']
            if killer_name != stats['DATA']['VICTIM']['NAME']:
              if killer_name not in self.kamikaze_stats:
                self.kamikaze_stats[killer_name] = 1
              else:
                self.kamikaze_stats[killer_name] += 1

              if self.kamikaze_stats[killer_name] == 1:
                self.handle_kamikaze_stats(killer_name)

    if stats['TYPE'] == "PLAYER_STATS":
      #these stats come at end of game after MATCH_REPORT for each player
      if stats['DATA']['QUIT'] == 0 and stats['DATA']['WARMUP'] == 0:
        if stats['DATA']['PLAY_TIME'] >= 120 and stats['DATA']['STEAM_ID'] != "0": #ignore bots:
          player_name = stats['DATA']['NAME']

          #player accuracies (sent to each player in tell)
          player = self.player(int(stats['DATA']['STEAM_ID']))
          #dont show if player is in spec, also handle multiple output bug as well
          if player.team != "spectator" and player.steam_id not in self.outputted_accuracy_players:
            accuracy_output = "^2YOUR ACCURACY:"
            for weapon in self.weapons:
              weapon_shots = stats['DATA']['WEAPONS'][weapon]["S"]
              weapon_hits = stats['DATA']['WEAPONS'][weapon]["H"]
              if weapon_shots > 0:
                if weapon_hits > 0:
                  weapon_accuracy = 100 * (weapon_hits / weapon_shots)
                else:
                  weapon_accuracy = 0.00
                accuracy_output += " - ^3{}: ^1{:0.2f}".format(weapon, weapon_accuracy)
            player.tell(accuracy_output)
            self.outputted_accuracy_players.append(player.steam_id)

          player_kpm = stats['DATA']['KILLS'] / (stats['DATA']['PLAY_TIME'] / 60)

          if stats['DATA']['DEATHS'] != 0: #we don't want to divide by 0!
            player_kd = stats['DATA']['KILLS'] / stats['DATA']['DEATHS']
          else:
            player_kd = stats['DATA']['KILLS']

          player_dmg = stats['DATA']['DAMAGE']['DEALT']
          player_longest_spree = stats['DATA']['MAX_STREAK']

          player_rail_hits = 0
          player_rail_shots = 0

          if stats['DATA']['WEAPONS']['RAILGUN']['S'] >= 15:
            player_rail_hits = stats['DATA']['WEAPONS']['RAILGUN']['H']
            player_rail_shots = stats['DATA']['WEAPONS']['RAILGUN']['S']
            player_rail_accuracy = 100 * (player_rail_hits / player_rail_shots)
          else:
            player_rail_accuracy = 0

          player_nade_kills = stats['DATA']['WEAPONS']['GRENADE']['K']
          player_pummels = stats['DATA']['WEAPONS']['GAUNTLET']['K']
          player_dmg_taken = stats['DATA']['DAMAGE']['TAKEN']

          player_dmg_per_kill = 0
          if stats['DATA']['KILLS'] > 0: #we don't want to divide by 0!
            player_dmg_per_kill = stats['DATA']['DAMAGE']['DEALT'] / stats['DATA']['KILLS']

          if not self.best_kpm_names:
            self.best_kpm_names = [player_name]
            self.best_kpm = player_kpm
          elif player_kpm > self.best_kpm:
            self.best_kpm_names = [player_name]
            self.best_kpm = player_kpm
          elif player_kpm == self.best_kpm:
            self.best_kpm_names.append(player_name)

          if not self.best_kd_names:
            self.best_kd_names = [player_name]
            self.best_kd = player_kd
          elif player_kd > self.best_kd:
            self.best_kd_names = [player_name]
            self.best_kd = player_kd
          elif player_kd == self.best_kd:
            self.best_kd_names.append(player_name)

          if not self.most_damage_names:
            self.most_damage_names = [player_name]
            self.most_damage = player_dmg
          elif player_dmg > self.most_damage:
            self.most_damage_names = [player_name]
            self.most_damage = player_dmg
          elif player_dmg == self.most_damage:
            self.most_damage_names.append(player_name)

          if not self.longest_spree:
            self.longest_spree_names = [player_name]
            self.longest_spree = player_longest_spree
          elif player_longest_spree > self.longest_spree:
            self.longest_spree_names = [player_name]
            self.longest_spree = player_longest_spree
          elif player_longest_spree == self.longest_spree:
            self.longest_spree_names.append(player_name)

          if not self.best_rail_accuracy_names:
            self.best_rail_accuracy_names = [player_name]
            self.best_rail_accuracy = player_rail_accuracy
            self.best_rail_hits = player_rail_hits
            self.best_rail_shots = player_rail_shots
          elif player_rail_accuracy > self.best_rail_accuracy:
            self.best_rail_accuracy_names = [player_name]
            self.best_rail_accuracy = player_rail_accuracy
            self.best_rail_hits = player_rail_hits
            self.best_rail_shots = player_rail_shots
          elif player_rail_accuracy == self.best_rail_accuracy:
            self.best_rail_accuracy_names.append(player_name)

          if not self.most_nade_kills_names:
            self.most_nade_kills_names = [player_name]
            self.most_nade_kills = player_nade_kills
          elif player_nade_kills > self.most_nade_kills:
            self.most_nade_kills_names = [player_name]
            self.most_nade_kills = player_nade_kills
          elif player_nade_kills == self.most_nade_kills:
            self.most_nade_kills_names.append(player_name)

          if not self.most_pummels_names:
            self.most_pummels_names = [player_name]
            self.most_pummels = player_pummels
          elif player_pummels > self.most_pummels:
            self.most_pummels_names = [player_name]
            self.most_pummels = player_pummels
          elif player_pummels == self.most_pummels:
            self.most_pummels_names.append(player_name)

          if not self.most_dmg_taken_names:
            self.most_dmg_taken_names = [player_name]
            self.most_dmg_taken = player_dmg_taken
          elif player_dmg_taken > self.most_dmg_taken:
            self.most_dmg_taken_names = [player_name]
            self.most_dmg_taken = player_dmg_taken
          elif player_dmg_taken == self.most_dmg_taken:
            self.most_dmg_taken_names.append(player_name)

          if not self.most_dmg_per_kill_names:
            self.most_dmg_per_kill_names = [player_name]
            self.most_dmg_per_kill = player_dmg_per_kill
          elif player_dmg_per_kill > self.most_dmg_per_kill:
            self.most_dmg_per_kill_names = [player_name]
            self.most_dmg_per_kill = player_dmg_per_kill
          elif player_dmg_per_kill == self.most_dmg_per_kill:
            self.most_dmg_per_kill_names.append(player_name)

  @minqlx.delay(2)
  @minqlx.thread
  def handle_game_end(self, data):
    if not data["ABORTED"] and self.best_kpm:
      self.msg("^5***UBERSTATS***")
      stats_output = "^1KILL MACHINE: "
      record_response = ""
      for i, player_name in enumerate(self.best_kpm_names):
        record_response = self.check_record("kill_machine", float(self.best_kpm), player_name)
        stats_output += "^7" + player_name
        if len(self.best_kpm_names) > 1 and len(self.best_kpm_names) - 1 != i:
          stats_output += ", "
      stats_output += "^2 - {:0.2f} frags/min".format(self.best_kpm)
      self.msg(record_response + stats_output)

      stats_output = "^1BEST COUNTERSTRIKE PLAYER: "
      record_response = ""
      for i, player_name in enumerate(self.best_kd_names):
        record_response = self.check_record("counterstrike", float(self.best_kd), player_name)
        stats_output += "^7" + player_name
        if len(self.best_kd_names) > 1 and len(self.best_kd_names) - 1 != i:
          stats_output += ", "
      stats_output += "^2 - {:0.2f} K/D ratio".format(self.best_kd)
      self.msg(record_response + stats_output)

      stats_output = "^1DESTRUCTICATOR: "
      record_response = ""
      for i, player_name in enumerate(self.most_damage_names):
        record_response = self.check_record("most_damage", float(self.most_damage), player_name)
        stats_output += "^7" + player_name
        if len(self.most_damage_names) > 1 and len(self.most_damage_names) - 1 != i:
          stats_output += ", "
      stats_output += "^2 - {:,} dmg given".format(self.most_damage)

      self.msg(record_response + stats_output)
      time.sleep(3)

      if self.longest_spree > 1:
        stats_output = "^1RAMBO: "
        record_response = ""
        for i, player_name in enumerate(self.longest_spree_names):
          record_response = self.check_record("longest_spree", float(self.longest_spree), player_name)
          stats_output += "^7" + player_name
          if len(self.longest_spree_names) > 1 and len(self.longest_spree_names) - 1 != i:
            stats_output += ", "
        stats_output += "^2 - {} kill streak".format(self.longest_spree)
        self.msg(record_response + stats_output)

      if self.best_rail_accuracy > 0:
        stats_output = "^1LASER EYES: "
        record_response = ""
        for i, player_name in enumerate(self.best_rail_accuracy_names):
          record_response = self.check_record("best_rail_accuracy", float(self.best_rail_accuracy), player_name)
          stats_output += "^7" + player_name
          if len(self.best_rail_accuracy_names) > 1 and len(self.best_rail_accuracy_names) - 1 != i:
            stats_output += ", "
        stats_output += "^2 - {:0.2f} percent rail accuracy ({} hits / {} shots)".format(self.best_rail_accuracy, self.best_rail_hits, self.best_rail_shots)
        self.msg(record_response + stats_output)

      if self.most_nade_kills > 0:
        stats_output = "^3PINEAPPLE POWER: "
        record_response = ""
        for i, player_name in enumerate(self.most_nade_kills_names):
          record_response = self.check_record("most_nade_kills", float(self.most_nade_kills), player_name)
          stats_output += "^7" + player_name
          if len(self.most_nade_kills_names) > 1 and len(self.most_nade_kills_names) - 1 != i:
            stats_output += ", "
        stats_output += "^2 - {} grenade frags".format(self.most_nade_kills)
        self.msg(record_response + stats_output)

      time.sleep(2)

      if self.most_pummels > 0:
        stats_output = "^1PUMMEL LORD: "
        record_response = ""
        for i, player_name in enumerate(self.most_pummels_names):
          record_response = self.check_record("most_pummels", float(self.most_pummels), player_name)
          stats_output += "^7" + player_name
          if len(self.most_pummels_names) > 1 and len(self.most_pummels_names) - 1 != i:
            stats_output += ", "
        stats_output += "^2 - {} pummels".format(self.most_pummels)
        self.msg(record_response + stats_output)

      stats_output = "^6BIGGEST PINCUSHION: "
      record_response = ""
      for i, player_name in enumerate(self.most_dmg_taken_names):
        record_response = self.check_record("most_dmg_taken", float(self.most_dmg_taken), player_name)
        stats_output += "^7" + player_name
        if len(self.most_dmg_taken_names) > 1 and len(self.most_dmg_taken_names) - 1 != i:
          stats_output += ", "
      stats_output += "^2 - {:,} ^6dmg taken".format(self.most_dmg_taken)
      self.msg(record_response + stats_output)

      stats_output = "^6CLUMSIEST FOOL: "
      record_response = ""
      for name, world_deaths in self.world_death_stats.items():
        if not self.most_world_deaths_names:
          self.most_world_deaths_names = [name]
          self.most_world_deaths = world_deaths
        elif world_deaths > self.most_world_deaths:
          self.most_world_deaths_names = [name]
          self.most_world_deaths = world_deaths
        elif world_deaths == self.most_world_deaths:
          self.most_world_deaths_names.append(name)

      if self.most_world_deaths > 0:
        for i, player_name in enumerate(self.most_world_deaths_names):
          record_response = self.check_record("most_world_deaths", float(self.most_world_deaths), player_name)
          stats_output += "^7" + player_name
          if len(self.most_world_deaths_names) > 1 and len(self.most_world_deaths_names) - 1 != i:
            stats_output += ", "
        stats_output += "^2 - {:,} deaths by world".format(self.most_world_deaths)
        self.msg(record_response + stats_output)

      time.sleep(2)

      if self.game.type not in ["Duel", "Instagib"]:
        stats_output = "^6GOOD SAMARITAN: "
        record_response = ""
        for i, player_name in enumerate(self.most_dmg_per_kill_names):
          record_response = self.check_record("most_dmg_per_kill", float(self.most_dmg_per_kill), player_name)
          stats_output += "^7" + player_name
          if len(self.most_dmg_per_kill_names) > 1 and len(self.most_dmg_per_kill_names) - 1 != i:
            stats_output += ", "
        stats_output += "^2 - {:0.2f} damage per frag".format(self.most_dmg_per_kill)
        self.msg(record_response + stats_output)

      stats_output = "^6BIGGEST CHATTERBOX: "
      record_response = ""
      for name, lines_of_chat in self.most_lines_of_chat_stats.items():
        if not self.most_lines_of_chat_names:
          self.most_lines_of_chat_names = [name]
          self.most_lines_of_chat = lines_of_chat
        elif lines_of_chat > self.most_lines_of_chat:
          self.most_lines_of_chat_names = [name]
          self.most_lines_of_chat = lines_of_chat
        elif lines_of_chat == self.most_lines_of_chat:
          self.most_lines_of_chat_names.append(name)

      if self.most_lines_of_chat > 0:
        for i, player_name in enumerate(self.most_lines_of_chat_names):
          record_response = self.check_record("most_lines_of_chat", float(self.most_lines_of_chat), player_name)
          stats_output += "^7" + player_name
          if len(self.most_world_deaths_names) > 1 and len(self.most_lines_of_chat_names) - 1 != i:
            stats_output += ", "
        stats_output += "^2 - {} lines of chat".format(self.most_lines_of_chat)
        self.msg(record_response + stats_output)

      if self.sftp_hostname:
        self.high_scores("endgame")

  @minqlx.delay(8)
  def handle_kill_streak(self, player_name, weapon):
    if int(self.kill_streak[weapon][player_name]) >= 4:
      self.play_sound("sound/uberstats/{}.ogg".format(weapon.lower()))
      self.center_print("{}^1 {}".format(player_name, self.weapon_sprees[self.weapons.index(weapon)]))
      self.msg("{} ^1{}: ^2({} {} frags in 8s)".format(player_name, self.weapon_sprees[self.weapons.index(weapon)], self.kill_streak[weapon][player_name], weapon))
      self.kill_streak[weapon][player_name] = 0

  @minqlx.delay(5)
  def handle_kamikaze_stats(self, player_name):
    kami_msg = "{}^7's ^3 KAMI: ^7{} ^1FRAGS".format(player_name, self.kamikaze_stats[player_name])
    self.center_print(kami_msg)
    self.msg(kami_msg)
    self.kamikaze_stats[player_name] = 0

  @minqlx.delay(10)
  def handle_map(self, mapname, factory):
    self.best_kpm_names = []
    self.best_kpm = 0

    self.best_kd_names = []
    self.best_kd = 0

    self.most_damage_names = []
    self.most_damage = 0

    self.longest_spree_names = []
    self.longest_spree = 0

    self.best_rail_accuracy_names = []
    self.best_rail_accuracy = 0
    self.best_rail_hits = 0
    self.best_rail_shots = 0

    self.most_nade_kills_names = []
    self.most_nade_kills = 0

    self.most_pummels_names = []
    self.most_pummels = 0

    self.most_dmg_taken_names = []
    self.most_dmg_taken = 0

    self.world_death_stats = {}
    self.most_world_deaths_names = []
    self.most_world_deaths = 0

    self.most_dmg_per_kill_names = []
    self.most_dmg_per_kill = 0

    self.most_lines_of_chat_stats = {}
    self.most_lines_of_chat_names = []
    self.most_lines_of_chat = 0

    self.kamikaze_stats = {}
    for weapon in self.weapons:
      self.kill_streak[weapon] = {}

    self.outputted_accuracy_players = []

    self.high_scores("triggered")

  def check_record(self, record_name, score, player_name):
    current_record = self.db.get(RECORDS_KEY.format(record_name) + ":high_score")

    if current_record is None:
      current_record = 0
    else:
      current_record = float(current_record)

    if score > current_record:
      self.db.set(RECORDS_KEY.format(record_name) + ":high_score", score)
      self.db.delete(RECORDS_KEY.format(record_name) + ":players")
      self.db.sadd(RECORDS_KEY.format(record_name) + ":players", player_name)
      self.play_sound("sound/vo_evil/new_high_score")
      return "^5NEW HIGH SCORE! - "
    elif score == current_record:
      self.db.sadd(RECORDS_KEY.format(record_name) + ":players", player_name)
      return "^5TIED HIGH SCORE! - "
    else:
      return ""

  def cmd_highscores(self, player, msg, channel):
    self.high_scores("triggered")

  @minqlx.thread
  def high_scores(self, method):
    if method == "triggered" and self.db.get(RECORDS_KEY.format("kill_machine") + ":high_score") is not None:
      self.msg("^5***UBERSTATS HIGH SCORES***")
    elif method == "endgame":
      html = "<script src='https://ajax.googleapis.com/ajax/libs/jquery/3.3.1/jquery.min.js'></script>\n" + \
           "<script>\n" + \
           "$(function(){\n"

    for key, val in WEAPON_RECORDS.items():
      high_score = self.db.get(RECORDS_KEY.format(key) + ":high_score")
      if high_score is not None:
        players = ", ".join(self.db.smembers(RECORDS_KEY.format(key) + ":players"))
        if method == "triggered":
          self.msg("^1{} - ^7{} ^2- {}".format(val[0], players, val[1].format(float(high_score))).replace(".00", "").replace(".0", ""))
        elif method == "endgame":
          players_html = []
          for player in self.db.smembers(RECORDS_KEY.format(key) + ":players"):
            players_html.append(self.html_colors(player))
          players_html_final = ", ".join(players_html)
          html += "$('.{}_record').text('{}');\n".format(key, val[1].format(float(high_score)).replace(".00", "").replace(".0", ""))
          html += "$('.{}_players').html('{}');\n\n".format(key, players_html_final)

    if method == "endgame":
      html += "});\n</script>"
      #make nice filename from hostname
      uberfilename = re.sub(' +', '_', (re.sub("[^a-zA-Z.\d\s]", "", self.game.hostname) + "-uberstats.html").lower())
      with io.open(uberfilename, 'w', encoding='utf8') as f:
        f.write(html)
      f.close()
      cnopts = pysftp.CnOpts()
      cnopts.hostkeys = None
      srv = pysftp.Connection(host = self.sftp_hostname, username = self.sftp_username, password = self.sftp_password, cnopts=cnopts)
      srv.chdir(self.sftp_remote_path)
      srv.put(uberfilename)

  def cmd_clear_highscores(self, player, msg, channel):
    for key, val in WEAPON_RECORDS.items():
      self.db.delete(RECORDS_KEY.format(key) + ":players")
      self.db.delete(RECORDS_KEY.format(key) + ":high_score")

  #UTILITY FUNCTIONS

  def ordinal(self, value):
    try:
      value = int(value)
    except ValueError:
      return value

    if value % 100//10 != 1:
      if value % 10 == 1:
        ordval = u"%d%s" % (value, "st")
      elif value % 10 == 2:
        ordval = u"%d%s" % (value, "nd")
      elif value % 10 == 3:
        ordval = u"%d%s" % (value, "rd")
      else:
        ordval = u"%d%s" % (value, "th")
    else:
      ordval = u"%d%s" % (value, "th")

    return ordval

  def html_colors(self, qstr='', limit=None):
    if not qstr or qstr == "":
      return "";
    if len(qstr) > 0:
      qstr = "^7" + qstr

    html = _dec_colors.sub(lambda match: _dec_spans[int(match.group(1))], qstr)
    return html + "</span>" * len(_all_colors.findall(qstr))