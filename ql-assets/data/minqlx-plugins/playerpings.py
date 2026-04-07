#Plugin requires TC wrapper named TCConfig - https://tcconfig.readthedocs.io/en/latest/pages/introduction/index.html
#sudo pip install tcconfig
#add user to sudoers file and allow the tcdel,tcset commands
#steam ALL=NOPASSWD:/usr/local/bin/tcset*,/usr/local/bin/tcdel*
#Modify the qlx_nic cvar below to the correct interface ID for tcconfig to work properly

#Following does not work properly but is in the documentation for tcconfig. Must use sudo for tcset command instead.
#sudo setcap cap_net_admin+ep /sbin/tc
#sudo setcap cap_net_raw,cap_net_admin+ep /usr/bin/ip
#version 1.3

from time import sleep
from statistics import mean
from collections import deque
import minqlx
import subprocess

class playerpings(minqlx.Plugin):
    def __init__(self):

        self.add_command("addping", self.cmd_addping, 3, usage="<id> <latency>")
        self.add_command("delping", self.cmd_delping, 3, usage="<id>")
        self.add_command("clearpings", self.cmd_clearpings, 3)
        self.set_cvar_once("qlx_nic", "eth0")
        self.set_cvar_once("qlx_minping", "40")
        self.set_cvar_once("qlx_pingsamples", "60")
        self.set_cvar_once("qlx_autobalanceping", "1")
        self.set_cvar_once("qlx_closeenoughping", "3")
        self.add_hook("player_connect", self.handle_player_connect, priority=minqlx.PRI_LOWEST)
        self.add_hook("player_disconnect", self.handle_player_disconnect)
        
        self.recent_dcs = deque(maxlen=10)

    def handle_player_disconnect(self, player, reason):
        if self.get_cvar("qlx_autobalanceping", int):
            self.recent_dcs.appendleft(player)

    def handle_player_connect(self, player):
        if self.get_cvar("qlx_autobalanceping", int):
            self.ping_adjust_player_connect(player)

    @minqlx.thread
    def ping_adjust_player_connect(self, player):
        minping = int(self.get_cvar("qlx_minping"))
        pingsamples = int(self.get_cvar("qlx_pingsamples"))
        closeenoughping = int(self.get_cvar("qlx_closeenoughping"))
        pinglist = []
        try:
            for _ in range(pingsamples):
                if player in self.recent_dcs:
                    self.recent_dcs.remove(player)
                    raise Exception
                else: 
                    sleep(1)
                    currentplayerping = player.ping
                    if (currentplayerping < minping) and (currentplayerping > 0):
                        pinglist.append(currentplayerping)
            if not pinglist:
                return
            else:
                player.update()
                pingaverage = mean(pinglist)
                latency = minping - int(pingaverage)
                if (latency > closeenoughping):
                    self.setping(player, 0, minqlx.CHAT_CHANNEL, latency)
                else:
                    return
        except:
            return minqlx.RET_STOP_ALL


    def cmd_addping(self, player, msg, channel):
        if len(msg) < 2:
            return minqlx.RET_USAGE
        try:
            i = int(msg[1])
            target_player = self.player(i)
            if not (0 <= i < 64) or not target_player:
                raise ValueError
        except ValueError:
            channel.reply("Invalid ID.")
            return
        try:
            if not len(target_player.ip) > 1:
                raise ValueError
        except ValueError:
            channel.reply("Player IP not found.")
            return
        try:
            latency = int(msg[2])
            if not (0 < latency <= 200):
                raise ValueError
            self.setping(target_player, msg, channel, latency)
        except ValueError:
            channel.reply("Latency value invalid. 200 is the maximum.")
            return
        except Exception as e:
            channel.reply("{} {}".format(e.message,e.args))
            return

    def cmd_delping(self, player, msg, channel):
        if len(msg) < 2:
            return minqlx.RET_USAGE
        try:
            i = int(msg[1])
            target_player = self.player(i)
            if not (0 <= i < 64) or not target_player:
                raise ValueError
        except ValueError:
            channel.reply("Invalid ID.")
            return
        try:
            if not len(target_player.ip) > 1:
                raise ValueError
        except ValueError:
            channel.reply("Player IP not found.")
            return
        try:
            self.setpingdel(target_player, msg, channel)
        except Exception as e:
            channel.reply("{} {}".format(e.message,e.args))
            return

    @minqlx.thread
    def setping(self, player, msg, channel, latency):
        try:
            interface = self.get_cvar("qlx_nic")
            incommand = "sudo tcset {} --delay {}ms --direction incoming --src-network {} --change".format(interface,latency/2,player.ip)
            outcommand = "sudo tcset {} --delay {}ms --direction outgoing --network {} --change".format(interface,latency/2,player.ip)
            subprocess.call(incommand,shell=True)
            subprocess.call(outcommand,shell=True)
            channel.reply("Player {} - ping increased by {}ms".format(player.name,latency))
        except Exception as e:
            channel.reply("{} {}".format(e.message,e.args))

    @minqlx.thread
    def setpingdel(self, player, msg, channel):
        try:
            interface = self.get_cvar("qlx_nic")
            incommand = "sudo tcdel {} --direction incoming --src-network {}".format(interface,player.ip)
            outcommand = "sudo tcdel {} --direction outgoing --network {}".format(interface,player.ip)
            subprocess.call(incommand,shell=True)
            subprocess.call(outcommand,shell=True)
            channel.reply("Player {} - ping reset to default".format(player.name))
        except Exception as e:
            channel.reply("{} {}".format(e.message,e.args))

    @minqlx.thread
    def cmd_clearpings(self, player, msg, channel):
        try:
            interface = self.get_cvar("qlx_nic")
            command = "sudo tcdel {} --all".format(interface)
            subprocess.call(command,shell=True)
            channel.reply("All player pings reset to default")
        except Exception as e:
            channel.reply("{} {}".format(e.message,e.args))
