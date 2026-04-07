# Work in progress plugin for mitigating ddos attacks targetting a Quake Live server's gameport.
# Offloads heavy traffic being blocked by configuring all currently connected players' source ips as allowed on the upstream hosting platform firewall.
# Curernt plugin built as an example for Linode.

import requests
import ipaddress
import minqlx

class linodefw(minqlx.Plugin):
    def __init__(self):
        super().__init__()
        # self.add_command("ips", self.cmd_get_ips, 3)
        self.add_command("current", self.get_currently_allowed, 3)
        self.add_command(("iplock", "ipclose", "ipl", "ipc"), self.lock_server, 3)
        self.add_command(("ipunlock", "ipopen", "ipu", "ipo"), self.unlock_server, 3)
        self.add_command(("ipadd", "ipa"), self.cmd_add_ip, 3)
        # self.add_hook("player_disconnect", self.handle_player_disconnect)
        self.fwaccesstoken = self.get_cvar("qlx_fwaccesstoken")
        self.fwname = self.get_cvar("qlx_fwname")
        self.fwid = 0
        self.gameport = self.get_cvar("net_port")
        self.uribase = "https://api.linode.com/v4/networking/firewalls"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.fwaccesstoken}"
        }

    # def handle_player_disconnect(self, *args, **kwargs):
    #    if len(self.players()) <= 1:
    #        self.unlock_server()
    
    def get_ips(self):
        players = self.players()
        if not len(players):
            return minqlx.RET_STOP_ALL
        res = []
        for p in players:
            res.append(p.ip + "/32")
        return res
    
    def get_linode_firewalls(self):
        try:
            response = requests.get(self.uribase, headers=self.headers)
        except:
            return minqlx.RET_STOP_ALL
        if response.status_code == 200:
            firewall_list = response.json()
            return firewall_list
        else:
            return minqlx.RET_STOP_ALL
        
    def get_firewall_rules(self):
        fwdata = self.get_linode_firewalls()
        if fwdata:
            for firewall in fwdata["data"]:
                if firewall["label"] == self.fwname:
                    if self.fwid == 0:
                        self.fwid = firewall["id"]
                    return firewall["rules"]
        return minqlx.RET_STOP_ALL

    def get_current_rule(self):
        rules = self.get_firewall_rules()
        if rules:
            for rule in rules["inbound"]:
                if rule["protocol"] == "UDP" and rule["ports"] == self.gameport:
                    return rule
        return minqlx.RET_STOP_ALL
    
    def update_ipv4_addressses(self, rules, addresses):
        for rule in rules["inbound"]:
            if rule["ports"] == str(self.gameport) and rule["protocol"] == "UDP":
                rule["addresses"]["ipv4"] = addresses
        return rules

    def update_linode_firewall(self, rules):
        uri = f"{self.uribase}/{self.fwid}/rules"
        try:
            response = requests.put(uri, headers=self.headers, json=rules)
        except:
            return minqlx.RET_STOP_ALL
        if response.status_code == 200:
            return response.json()
        else:
            return minqlx.RET_STOP_ALL
    
    @minqlx.thread
    def get_currently_allowed(self, player, msg, channel):
        current_rule = self.get_current_rule()
        if current_rule:
            label = current_rule["label"]
            ips_str = ", ".join(current_rule["addresses"]["ipv4"])
            player.tell(f"Rule Name: {label}")
            player.tell("Allowed IPs:")
            for ip in current_rule["addresses"]["ipv4"]:
                player.tell(str(ip))
        else:
            player.tell("No rule found.")
        return minqlx.RET_STOP_ALL
    
    @minqlx.thread
    def lock_server(self, player, msg, channel):
        ips = self.get_ips()
        rules = self.get_firewall_rules()
        newRules = self.update_ipv4_addressses(rules, ips)
        if newRules:
            confirmation = self.update_linode_firewall(newRules)
            if confirmation:
                player.tell("Rules Updated")
            else:
                player.tell("Error updating rules")
        return minqlx.RET_STOP_ALL
    
    @minqlx.thread
    def unlock_server(self, player, msg, channel):
        ips = ["0.0.0.0/0"]
        rules = self.get_firewall_rules()
        newRules = self.update_ipv4_addressses(rules, ips)
        if newRules:
            confirmation = self.update_linode_firewall(newRules)
            if confirmation:
                player.tell("Server unlocked")
            else:
                player.tell("Error unlocking server - LOL")
        return minqlx.RET_STOP_ALL    

    @minqlx.thread
    def cmd_add_ip(self, player, msg, channel):
        ip = msg[1]
        if not ip:
            player.tell("Usage: !ipadd <ip>")
            return minqlx.RET_STOP_ALL
        else:
            try:
                ipaddress.ip_address(ip)
            except ValueError:
                player.tell(f"Invalid IP Address: {ip}")
                return minqlx.RET_STOP_ALL
            # Use existing IPs from the current rule
            current_rule = self.get_current_rule()
            ips = current_rule["addresses"]["ipv4"]
            if ip in ips:
                player.tell(f"IP Address: {ip}, already exists")
                return minqlx.RET_STOP_ALL
            else:
                ips.append(f"{ip}/32")
                rules = self.get_firewall_rules()
                newRules = self.update_ipv4_addressses(rules, ips)
                if newRules:
                    confirmation = self.update_linode_firewall(newRules)
                    if confirmation:
                        player.tell("IP Address Added")
                    else:
                        player.tell("Error adding IP")
                return minqlx.RET_STOP_ALL