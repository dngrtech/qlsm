import minqlxtended
import time
import threading
import ipaddress
from datetime import datetime, timezone

DEFAULT_MU = 25.0
ELO_LIST_COOLDOWN = 10
ALIAS_COOLDOWN = 30
RANK_COOLDOWN = 10

DB_KEY_ELO_MUTE = "minqlx:players:{}:ranked:elo_muted"
DB_KEY_RANK_MUTE = "minqlx:players:{}:ranked:rank_muted"
DB_KEY_TOP10_MUTE = "minqlx:players:{}:ranked:top10_muted"

try:
    import requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False


# Tier -> Quake colour code. QL has eight colours and the ladder has eight
# tiers, but two pairs have to share: Nab and Bronze are both ^7, Silver and
# Gold are both ^3. The label is always printed beside the colour, so the
# collision costs nothing a reader can be confused by.

TIER_COLOURS = {
    "Nab": "^7",
    "Bronze": "^7",
    "Silver": "^3",
    "Gold": "^3",
    "Platinum": "^5",
    "Diamond": "^4",
    "Prism": "^6",
    "LIGHT": "^2",
}


def _rank_text(d):
    """"LIGHT" / "Diamond II" / "Nab", coloured, from any service payload.

    Every endpoint this plugin reads -- /player, /players, /leaderboard --
    carries rank_label and tier, so this works on all three. A payload with
    neither (a service still running the old engine) returns None, and the
    caller falls back to the rating number it used to print, so pointing this
    plugin at an un-migrated service degrades instead of breaking.
    """
    if not isinstance(d, dict):
        return None
    label = d.get("rank_label")
    if not label:
        return None
    colour = TIER_COLOURS.get(d.get("tier") or "Nab", "^7")
    return f"{colour}{label}"


def _points_text(d):
    """"^522,915P", or None when the payload carries no points."""
    if not isinstance(d, dict):
        return None
    points = d.get("points")
    if points is None:
        return None
    return f"^5{int(points):,}P"


def _rank_and_points(d, fallback_score):
    """The one phrase all three commands print: rank, then points.

    Falls back to the bare rating when the service reports no ranks, which is
    exactly what these commands printed before the ladder existed.
    """
    rank = _rank_text(d)
    if rank is None:
        return f"^6{int(fallback_score)}"
    points = _points_text(d)
    return f"{rank}^7 {points}" if points else rank


class ranked(minqlxtended.Plugin):

    def __init__(self):
        self.set_cvar_once("qlx_rankedPool", "ffa_auto")
        self.set_cvar_once("qlx_rankedServiceUrl", "http://localhost:5002")
        self.set_cvar_once("qlx_rankedApiKey", "change-me")
        self.set_cvar_once("qlx_rankedAutoBatchSeconds", "600")
        self.set_cvar_once("qlx_rankedAutoAfkSeconds", "10")
        self.set_cvar_once("qlx_rankedAutoMoveThreshold", "16")
        self.set_cvar_once("qlx_rankedAutoMaxBatchEvents", "2000")
        self.set_cvar_once("qlx_rankedModeCountdown", "10")
        self.set_cvar_once("qlx_rankedModeCooldown", "30")

        self.add_command("players", self.cmd_players, client_cmd_perm=0)
        self.add_command("rank", self.cmd_rank, client_cmd_perm=0, usage="[#]")
        self.add_command(("elo", "elos"), self.cmd_elos, client_cmd_perm=0)
        self.add_command("alias", self.cmd_alias, client_cmd_perm=0, usage="<#>")
        self.add_command("top10", self.cmd_top10, client_cmd_perm=0)
        self.add_command("casual", self.cmd_casual, client_cmd_perm=0)
        self.add_command("ranked", self.cmd_ranked, client_cmd_perm=0)

        self.last_elo_list_time = 0
        self.last_top10_time = 0
        self.last_alias_time = 0
        # PER PLAYER, not one clock for the whole server. !rank is a private
        # answer about yourself now, so one player asking must not lock
        # everyone else out of asking about themselves.
        self._rank_cooldowns = {}
        self._elo_muted = set()
        self._rank_muted = set()
        self._top10_muted = set()
        # Casual mode -- see the section of that name below.
        self._casual = set()
        self._mode_pending = {}
        self._mode_switched_at = {}
        self._mode_seq = 0

        pool = self.get_cvar("qlx_rankedPool") or "ffa_auto"
        self._pool = pool
        # Only present on minqlx built with ql-assets/patches/minqlx-damage-event.patch.
        self._has_damage_event = "damage" in minqlxtended.EVENT_DISPATCHERS

        # Both pools: a mode switch queued with minqlx.delay can outlive an
        # unload, and this is how it finds out.
        self._stop = threading.Event()
        self.add_hook("unload", self.handle_unload)

        self.add_hook("player_connect", self.handle_player_connect)
        self.add_hook("player_disconnect", self.handle_player_disconnect)
        self._report_connected_players()

        if pool == "ranked_duel":
            self.add_hook("game_end", self.handle_game_end)
        else:
            self._lock = threading.Lock()
            self._last_active = {}
            self._last_pos = {}
            self._kill_events = []
            self._window_started = time.time()
            self.add_hook("kill", self.handle_kill)
            self.add_hook("map", self.handle_map)
            if self._has_damage_event:
                self.add_hook("damage", self.handle_damage)
                minqlxtended.console_print(
                    "[ranked] !casual/!ranked: countdown cancels on the first hit."
                )
            else:
                minqlxtended.console_print(
                    "[ranked] !casual/!ranked: no damage event on this build; countdowns "
                    "are cancelled by frags and checked against damage stats when they end."
                )
            self._start_activity_poll()
            self._start_batch_timer()

    def handle_unload(self, plugin):
        if plugin == self.__class__.__name__:
            self._stop.set()

    # ---------------------------------------------------------------- helpers

    def _svc_url(self):
        return self.get_cvar("qlx_rankedServiceUrl")

    def _headers(self):
        return {"X-API-Key": self.get_cvar("qlx_rankedApiKey")}

    def _player_list(self):
        return [(p.id, p) for p in sorted(self.players(), key=lambda p: p.id)]

    def _player_name(self, player):
        return getattr(player, "clean_name", None) or player.name

    def _find_by_index(self, index):
        for i, p in self._player_list():
            if i == index:
                return p
        return None

    def _cvar_int(self, name, default, minimum=1):
        try:
            v = int(self.get_cvar(name))
        except (TypeError, ValueError):
            v = default
        return max(v, minimum)

    # ---------------------------------------------------------------- mute persistence

    def _load_mute_prefs(self, player):
        sid = str(player.steam_id)
        elo_val, rank_val, top10_val = self.db.mget([
            DB_KEY_ELO_MUTE.format(sid),
            DB_KEY_RANK_MUTE.format(sid),
            DB_KEY_TOP10_MUTE.format(sid),
        ])
        if elo_val:
            self._elo_muted.add(sid)
        if rank_val:
            self._rank_muted.add(sid)
        if top10_val:
            self._top10_muted.add(sid)

    def _set_mute_pref(self, key_template, sid, muted):
        key = key_template.format(sid)
        if muted:
            self.db[key] = "1"
        else:
            self.db.delete(key)



    def _player_ip(self, player):
        ip = (getattr(player, "ip", None) or "").strip()
        if not ip:
            return None
        try:
            parsed = ipaddress.ip_address(ip)
        except ValueError:
            minqlxtended.console_print(f"[ranked] Ignoring invalid player IP for {player}: {ip}")
            return None
        if parsed.is_loopback or parsed.is_unspecified or parsed.is_link_local:
            minqlxtended.console_print(f"[ranked] Ignoring non-routable player IP for {player}: {ip}")
            return None
        return str(parsed)

    def _report_player_seen(self, player):
        if not _REQUESTS_OK:
            return
        ip = self._player_ip(player)
        if not ip:
            return
        svc_url = self._svc_url()
        headers = self._headers()
        hostname = self.get_cvar("sv_hostname") or "unknown"
        payload = {
            "steam_id": str(player.steam_id),
            "name": self._player_name(player),
            "ip": ip,
            "server_id": hostname,
            "seen_at": datetime.now(timezone.utc).isoformat(),
        }

        @minqlxtended.thread
        def do_report():
            try:
                r = requests.post(
                    f"{svc_url}/player/seen",
                    headers=headers,
                    json=payload,
                    timeout=5,
                )
                if r.status_code != 200:
                    minqlxtended.console_print(f"[ranked] Player IP submit failed: HTTP {r.status_code}")
            except Exception as e:
                minqlxtended.console_print(f"[ranked] Player IP submit error: {e}")

        do_report()

    # ---------------------------------------------------------------- ranked_duel: game_end

    def handle_game_end(self, aborted):
        if aborted:
            return
        active = self.teams().get("free", [])
        if len(active) != 2:
            return
        active.sort(key=lambda p: p.score, reverse=True)
        winner, loser = active[0], active[1]
        if str(winner.steam_id) in self._casual or str(loser.steam_id) in self._casual:
            self.msg("^7Match not rated: a ^5casual^7 player was in it.")
            return
        self._report_match(
            winner_id=str(winner.steam_id),
            winner_name=self._player_name(winner),
            winner_score=winner.score,
            loser_id=str(loser.steam_id),
            loser_name=self._player_name(loser),
            loser_score=loser.score,
        )

    def _report_match(self, winner_id, winner_name, winner_score,
                      loser_id, loser_name, loser_score):
        if not _REQUESTS_OK:
            return
        svc_url = self._svc_url()
        headers = self._headers()
        hostname = self.get_cvar("sv_hostname") or "unknown"

        @minqlxtended.thread
        def do_report():
            try:
                r = requests.post(
                    f"{svc_url}/match",
                    headers=headers,
                    json={
                        "server_id": hostname,
                        "winner_steam_id": winner_id,
                        "winner_name": winner_name,
                        "winner_score": max(winner_score, 1),
                        "loser_steam_id": loser_id,
                        "loser_name": loser_name,
                        "loser_score": loser_score,
                    },
                    timeout=5,
                )
                if r.status_code == 200:
                    d = r.json()
                    sign = "+" if d["winner"]["delta"] >= 0 else ""
                    w_score = int(d["winner"].get("sort_score") or d["winner"]["mu"])
                    l_score = int(d["loser"].get("sort_score") or d["loser"]["mu"])
                    out = (
                        f"^2{winner_name} ^7{sign}{int(d['winner']['delta'])} "
                        f"^7({w_score}) ^7| "
                        f"^1{loser_name} ^7{int(d['loser']['delta'])} "
                        f"^7({l_score})"
                    )

                    @minqlxtended.next_frame
                    def send(m=out):
                        self.msg(m)
                    send()
            except Exception:
                minqlxtended.console_print("[ranked] Failed to report match")

        do_report()

    # ---------------------------------------------------------------- ffa_auto: kill + map

    def handle_kill(self, victim, killer, mod):
        if killer is None or killer == victim:
            return
        if self._mode_pending:
            self._interrupt_mode_switch(killer, "you got a frag")
            self._interrupt_mode_switch(victim, "you died")
        killer_id = str(killer.steam_id)
        victim_id = str(victim.steam_id)
        # Judged NOW, as the frag lands, never at batch time -- so going casual
        # later cannot reach back and erase a loss that is already queued.
        if killer_id in self._casual or victim_id in self._casual:
            return
        now = time.time()

        afk_threshold = self._cvar_int("qlx_rankedAutoAfkSeconds", 10)
        with self._lock:
            last_active = self._last_active.get(victim_id)
        if last_active is not None and (now - last_active) > afk_threshold:
            return

        with self._lock:
            self._kill_events.append({
                "killer_steam_id": killer_id,
                "killer_name": self._player_name(killer),
                "victim_steam_id": victim_id,
                "victim_name": self._player_name(victim),
                "timestamp": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            })

    def handle_damage(self, target, attacker, damage, dflags, mod):
        # Hot hook: fires per pellet and per splash, so it stays a single dict write.
        # World damage (fall, lava, void) arrives as attacker == -1, not None.
        if not isinstance(attacker, minqlxtended.Player):
            return
        with self._lock:
            self._last_active[str(attacker.steam_id)] = time.time()
        # Empty unless somebody is mid-switch, so this test is all it costs the
        # rest of the time. Hurting yourself is movement, not combat.
        if self._mode_pending and isinstance(target, minqlxtended.Player) and target != attacker:
            self._interrupt_mode_switch(attacker, "you dealt damage")
            self._interrupt_mode_switch(target, "you took damage")

    def handle_map(self, mapname, factory):
        @minqlxtended.thread
        def flush_and_reset():
            # _submit_batch owns the queue and _window_started: it clears both on a
            # successful POST and deliberately restores them on failure. Only the
            # per-map activity tracking is reset here.
            self._submit_batch()
            with self._lock:
                self._last_active = {}
                self._last_pos = {}
        flush_and_reset()

    # ---------------------------------------------------------------- ffa_auto: activity polling

    def _start_activity_poll(self):
        @minqlxtended.thread
        def poll():
            while not self._stop.wait(1):
                self._check_activity()
        poll()

    def _check_activity(self):
        threshold = self._cvar_int("qlx_rankedAutoMoveThreshold", 16)
        now = time.time()
        for player in self.players():
            sid = str(player.steam_id)
            try:
                # position is a property on minqlxtended, not a callable method.
                pos = player.position
                x, y, z = pos.x, pos.y, pos.z
            except Exception:
                continue
            with self._lock:
                last = self._last_pos.get(sid)
                if last is None:
                    self._last_active[sid] = now
                else:
                    dx, dy, dz = x - last[0], y - last[1], z - last[2]
                    if (dx*dx + dy*dy + dz*dz) ** 0.5 >= threshold:
                        self._last_active[sid] = now
                self._last_pos[sid] = (x, y, z)

    # ---------------------------------------------------------------- ffa_auto: batch timer

    def _start_batch_timer(self):
        @minqlxtended.thread
        def timer():
            while True:
                interval = self._cvar_int("qlx_rankedAutoBatchSeconds", 600, minimum=60)
                if self._stop.wait(interval):
                    return
                self._submit_batch()
        timer()

    def _submit_batch(self):
        if not _REQUESTS_OK:
            return

        with self._lock:
            events = self._kill_events[:]
            window_started = self._window_started
            self._kill_events = []
            self._window_started = time.time()

        if not events:
            return

        # The service rejects batches larger than its own AUTO_BATCH_MAX_EVENTS,
        # so the cap stays — but the overflow goes back on the queue for the next
        # window instead of being dropped.
        max_events = self._cvar_int("qlx_rankedAutoMaxBatchEvents", 2000)
        if len(events) > max_events:
            overflow = events[max_events:]
            events = events[:max_events]
            minqlxtended.console_print(
                f"[ranked] Batch capped at {max_events}; deferring {len(overflow)} events."
            )
            self._requeue_events(overflow, window_started)

        hostname = self.get_cvar("sv_hostname") or "unknown"
        now = datetime.now(timezone.utc)
        window_start_dt = datetime.fromtimestamp(window_started, tz=timezone.utc)
        batch_id = f"{hostname}-{window_start_dt.isoformat()}"

        payload = {
            "batch_id": batch_id,
            "server_id": hostname,
            "window_started_at": window_start_dt.isoformat(),
            "window_ended_at": now.isoformat(),
            "events": events,
        }

        try:
            r = requests.post(
                f"{self._svc_url()}/auto/batch",
                headers=self._headers(),
                json=payload,
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "accepted":
                    minqlxtended.console_print(
                        f"[ranked] Batch submitted: {data['processed_events']} events, "
                        f"{len(data['players'])} players updated."
                    )
            else:
                minqlxtended.console_print(
                    f"[ranked] Batch submit failed: HTTP {r.status_code}, retrying."
                )
                self._requeue_events(events, window_started)
        except Exception as e:
            minqlxtended.console_print(f"[ranked] Batch submit error: {e}, retrying.")
            self._requeue_events(events, window_started)

    def _requeue_events(self, events, window_started):
        with self._lock:
            self._kill_events = events + self._kill_events
            self._window_started = min(window_started, self._window_started)

    # ---------------------------------------------------------------- connection cleanup

    def handle_player_connect(self, player, is_bot):
        self._load_mute_prefs(player)
        self._report_player_seen(player)

    def _report_connected_players(self):
        for player in self.players():
            self._load_mute_prefs(player)
            self._report_player_seen(player)

    def handle_player_disconnect(self, player, reason):
        sid = str(player.steam_id)
        self._elo_muted.discard(sid)
        self._rank_muted.discard(sid)
        self._top10_muted.discard(sid)
        # Back to ranked on the way out. _mode_switched_at is deliberately
        # kept, so reconnecting does not skip the cooldown.
        self._casual.discard(sid)
        self._mode_pending.pop(sid, None)

    # ---------------------------------------------------------------- casual mode
    #
    # !casual turns a player's elo OFF and !ranked turns it back ON. Ranked is
    # the default, and the choice lasts until the player disconnects.
    #
    # A FRAG IS RATED ONLY WHEN BOTH PLAYERS ARE RANKED. The service moves both
    # sides of every frag it is sent, so there is no rating just the ranked
    # half: the event is sent or it is not. Dropping it means a casual player
    # can neither farm anybody nor be farmed.
    #
    # THE SWITCH IS A COMMITMENT, NOT A REACTION. Typing the command starts a
    # countdown, and the switch only lands if the player neither deals nor
    # takes damage before it ends -- moving and aiming are fine. Without that,
    # !casual bound to a key is a button that deletes the fight you are losing.
    #
    # A countdown AFTER the command rather than a combat tag BEFORE it, for two
    # reasons. A tag has to be written on every hit, for every player, all
    # match, to answer a question asked once in a while; this costs the damage
    # hook one empty-dict test until somebody is actually switching. And a tag
    # lets a player who has been quiet for ten seconds switch the instant they
    # see who is coming; here the decision has to be made ten seconds ahead.
    #
    # Commands, hooks and minqlx.delay all run on the game thread, so none of
    # this state needs the lock.

    def cmd_casual(self, player, msg, channel):
        self._request_mode(player, casual=True)
        return minqlxtended.Return.STOP_ALL

    def cmd_ranked(self, player, msg, channel):
        self._request_mode(player, casual=False)
        return minqlxtended.Return.STOP_ALL

    def _request_mode(self, player, casual):
        sid = str(player.steam_id)
        target = "^5casual" if casual else "^2ranked"
        now = time.time()

        pending = self._mode_pending.get(sid)
        if pending is not None:
            if pending[0] == casual:
                left = int(pending[3] - now) + 1
                player.tell(f"^7Already switching to {target}^7: ^3{left}s^7 left.")
            else:
                # The opposite command names the mode they are still in.
                del self._mode_pending[sid]
                player.tell(f"^7Switch cancelled. You're still {target}^7.")
            return

        if (sid in self._casual) == casual:
            if casual:
                player.tell("^7You're already ^5casual^7: elo is off. "
                            "^3!ranked^7 turns it back on.")
            else:
                player.tell("^7You're already ^2ranked^7: elo is on. "
                            "^3!casual^7 turns it off.")
            return

        cooldown = self._cvar_int("qlx_rankedModeCooldown", 30, minimum=0)
        remaining = cooldown - (now - self._mode_switched_at.get(sid, 0))
        if remaining > 0:
            player.tell(f"^1Mode switch on cooldown.^7 Wait {int(remaining) + 1}s.")
            return

        if self._pool == "ranked_duel":
            # A duel is rated once, at game_end, on the mode each player holds
            # then -- so the mode is fixed for the whole match. Between matches
            # nothing is being rated and there is nothing to wait out.
            game = self.game
            if game and game.state == "in_progress":
                player.tell("^1You can't change mode mid-match.^7 Switch during warmup.")
            else:
                self._apply_mode(player, casual)
            return

        seconds = self._cvar_int("qlx_rankedModeCountdown", 10)
        self._mode_seq += 1
        token = self._mode_seq
        # Without the damage event nothing can cancel on the hit, so remember
        # the engine's own damage counters and compare them when time is up.
        totals = None if self._has_damage_event else self._damage_totals(player)
        self._mode_pending[sid] = (casual, token, player.id, now + seconds, totals)
        player.center_print(f"^7Going {target} ^7in ^3{seconds}s")
        player.tell(f"^7Switching to {target}^7 in ^3{seconds}s^7. "
                    "Deal or take damage and it's cancelled.")

        @minqlxtended.delay(seconds)
        def finish():
            self._finish_mode_switch(sid, token)
        finish()

    def _finish_mode_switch(self, sid, token):
        pending = self._mode_pending.get(sid)
        if self._stop.is_set() or pending is None or pending[1] != token:
            return  # unloaded, cancelled, or replaced by a newer countdown
        del self._mode_pending[sid]
        casual, _, client_id, _, totals = pending

        # The slot can have emptied, or filled with somebody else, since the
        # command was typed.
        try:
            player = self.player(client_id)
        except minqlxtended.NonexistentPlayerError:
            return
        if player is None or str(player.steam_id) != sid:
            return

        # Any change counts, a reset by a new map included: retrying is cheap,
        # a missed fight is not.
        if totals is not None and self._damage_totals(player) != totals:
            self._tell_switch_cancelled(player, "you were in a fight")
            return

        self._apply_mode(player, casual)

    def _apply_mode(self, player, casual):
        sid = str(player.steam_id)
        now = time.time()
        cooldown = self._cvar_int("qlx_rankedModeCooldown", 30, minimum=0)
        # Survives disconnect (see handle_player_disconnect), so it is pruned
        # here, on a rare event, down to the players still inside a cooldown.
        self._mode_switched_at = {
            s: t for s, t in self._mode_switched_at.items() if now - t < cooldown
        }
        self._mode_switched_at[sid] = now

        if casual:
            self._casual.add(sid)
            player.center_print("^5CASUAL ^7- elo off")
            player.tell("^7You're now ^5casual^7: your frags and deaths don't change "
                        "anyone's rating. ^3!ranked^7 turns elo back on.")
            self._announce(sid, f"{player.name} ^7is playing ^5casual^7: "
                                "frags with them don't count for ranking.")
        else:
            self._casual.discard(sid)
            player.center_print("^2RANKED ^7- elo on")
            player.tell("^7You're ^2ranked^7 again: your frags count.")
            self._announce(sid, f"{player.name} ^7is back to ^2ranked^7.")

    def _interrupt_mode_switch(self, player, reason):
        if self._mode_pending.pop(str(player.steam_id), None) is not None:
            self._tell_switch_cancelled(player, reason)

    def _tell_switch_cancelled(self, player, reason):
        seconds = self._cvar_int("qlx_rankedModeCountdown", 10)
        player.center_print("^1Switch cancelled")
        player.tell(f"^1Mode switch cancelled^7: {reason}. "
                    f"Stay out of combat for {seconds}s.")

    def _announce(self, sid, text):
        # Same audience as the !elo list: everybody who hasn't muted it.
        for p in self.players():
            other = str(p.steam_id)
            if other != sid and other not in self._elo_muted:
                p.tell(text)

    def _damage_totals(self, player):
        try:
            stats = player.stats
            return (stats.damage_dealt, stats.damage_taken)
        except Exception as e:
            minqlxtended.console_print(f"[ranked] Could not read damage stats for {player}: {e}")
            return None

    # ---------------------------------------------------------------- info commands (both pools)

    def cmd_elos(self, player, msg, channel):
        sid = str(player.steam_id)

        if len(msg) >= 2 and msg[1].lower() == "mute":
            self._elo_muted.add(sid)
            self._set_mute_pref(DB_KEY_ELO_MUTE, sid, True)
            player.tell("^7elo announcements ^1muted^7. Use ^3!elo unmute ^7to restore.")
            return minqlxtended.Return.STOP_ALL

        if len(msg) >= 2 and msg[1].lower() == "unmute":
            self._elo_muted.discard(sid)
            self._set_mute_pref(DB_KEY_ELO_MUTE, sid, False)
            player.tell("^7elo announcements ^2unmuted^7.")
            return minqlxtended.Return.STOP_ALL

        if not _REQUESTS_OK:
            player.tell("^1Ranking service unavailable.")
            return minqlxtended.Return.STOP_ALL

        now = time.time()
        remaining = ELO_LIST_COOLDOWN - (now - self.last_elo_list_time)
        if remaining > 0:
            player.tell(f"^1rating list on cooldown. Wait {int(remaining) + 1}s.")
            return minqlxtended.Return.STOP_ALL

        self.last_elo_list_time = now
        mode = self._pool
        players = sorted(self.players(), key=lambda p: p.id)
        invoker_muted = sid in self._elo_muted
        # Copied here, on the game thread; fetch() runs off it.
        casual = set(self._casual)

        @minqlxtended.thread
        def fetch():
            names = {str(p.steam_id): self._player_name(p) for p in players}
            ids = ",".join(names.keys())
            try:
                r = requests.get(
                    f"{self._svc_url()}/players",
                    params={"ids": ids, "mode": mode},
                    timeout=5,
                )
                r.raise_for_status()
                data = r.json()
            except Exception:
                player.tell("^1rating list unavailable.")
                return

            ratings = []
            for steam_id, name in names.items():
                d = data.get(steam_id)
                tag = " ^5casual" if steam_id in casual else ""
                if d is None:
                    ratings.append({
                        "name": name, "score": 0, "shown": "^7Nab",
                        "record": "unranked", "tag": tag,
                    })
                else:
                    # SORTED BY POINTS, not by the raw rating, so the order on
                    # screen matches the order the ladder puts these players
                    # in. Nab has no points, so it sorts last on -1.
                    points = d.get("points")
                    ratings.append({
                        "name": d.get("name") or name,
                        "score": points if points is not None
                                 else (d.get("sort_score") or d["mu"]),
                        "shown": _rank_and_points(d, d.get("sort_score") or d["mu"]),
                        "record": f"{d['wins']}-{d['losses']}",
                        "tag": tag,
                    })

            ratings.sort(key=lambda r: r["score"], reverse=True)
            out = "^7ranks: " + ", ".join(
                f"{r['name']}: {r['shown']}^7 ({r['record']}){r['tag']}"
                for r in ratings
            )

            @minqlxtended.next_frame
            def send(m=out):
                if invoker_muted:
                    player.tell(m)
                else:
                    for p in self.players():
                        if str(p.steam_id) not in self._elo_muted:
                            p.tell(m)
            send()

        fetch()
        # Always swallow the raw "!elo" chat line so it never appears in public
        # chat. The rating list is delivered separately via .tell (which respects
        # mute), so non-muted players still get the output.
        return minqlxtended.Return.STOP_ALL

    def cmd_top10(self, player, msg, channel):
        sid = str(player.steam_id)

        if len(msg) >= 2 and msg[1].lower() == "mute":
            self._top10_muted.add(sid)
            self._set_mute_pref(DB_KEY_TOP10_MUTE, sid, True)
            player.tell("^7top10 announcements ^1muted^7. Use ^3!top10 unmute ^7to restore.")
            return minqlxtended.Return.STOP_ALL

        if len(msg) >= 2 and msg[1].lower() == "unmute":
            self._top10_muted.discard(sid)
            self._set_mute_pref(DB_KEY_TOP10_MUTE, sid, False)
            player.tell("^7top10 announcements ^2unmuted^7.")
            return minqlxtended.Return.STOP_ALL

        if not _REQUESTS_OK:
            player.tell("^1Ranking service unavailable.")
            return minqlxtended.Return.STOP_ALL

        now = time.time()
        remaining = ELO_LIST_COOLDOWN - (now - self.last_top10_time)
        if remaining > 0:
            player.tell(f"^1top10 on cooldown. Wait {int(remaining) + 1}s.")
            return minqlxtended.Return.STOP_ALL

        self.last_top10_time = now
        mode = self._pool
        invoker_muted = sid in self._top10_muted

        @minqlxtended.thread
        def fetch():
            try:
                r = requests.get(
                    f"{self._svc_url()}/leaderboard",
                    params={"mode": mode, "limit": 10},
                    timeout=5,
                )
                r.raise_for_status()
                data = r.json()
            except Exception:
                player.tell("^1top10 unavailable.")
                return

            if not data:
                player.tell("^7No ranked players yet.")
                return

            out = "\n".join(
                f"^5#{e.get('ladder_position') or e['rank']} ^7{e['name']} "
                f"{_rank_and_points(e, e.get('sort_score') or e.get('rating') or 0)}^7 "
                f"({e['wins']}-{e['losses']})"
                for e in data
            )

            @minqlxtended.next_frame
            def send(m=out):
                if invoker_muted:
                    player.tell(m)
                else:
                    for p in self.players():
                        if str(p.steam_id) not in self._top10_muted:
                            p.tell(m)
            send()

        fetch()
        return minqlxtended.Return.STOP_ALL

    def cmd_players(self, player, msg, channel):
        lines = ["^7Players:"]
        for i, p in self._player_list():
            lines.append(f"^7[^2{i}^7] {p.name}")
        player.tell("\n".join(lines))

    def cmd_alias(self, player, msg, channel):
        if len(msg) < 2:
            player.tell("^1Usage: !alias <#>")
            return minqlxtended.Return.STOP_ALL
        if not _REQUESTS_OK:
            player.tell("^1Ranking service unavailable.")
            return minqlxtended.Return.STOP_ALL

        now = time.time()
        remaining = ALIAS_COOLDOWN - (now - self.last_alias_time)
        if remaining > 0:
            player.tell(f"^1Alias lookup on cooldown. Wait {int(remaining) + 1}s.")
            return minqlxtended.Return.STOP_ALL

        try:
            target = self._find_by_index(int(msg[1]))
        except ValueError:
            player.tell("^1Usage: !alias <#>")
            return minqlxtended.Return.STOP_ALL

        if not target:
            player.tell("^1Invalid player number. Use !players to see the list.")
            return minqlxtended.Return.STOP_ALL

        self.last_alias_time = now
        steam_id = str(target.steam_id)
        display_name = self._player_name(target)

        @minqlxtended.thread
        def fetch():
            try:
                r = requests.get(f"{self._svc_url()}/player/{steam_id}", timeout=3)
                if r.status_code == 404:
                    reply = f"^3{display_name} ^7has no record in the ranking service."
                elif r.status_code != 200:
                    reply = "^1Could not reach ranking service."
                else:
                    names = r.json().get("name_history", [])
                    if names:
                        reply = (f"^3{display_name}^7 known as: "
                                 f"^3{'^7, ^3'.join(names)}")
                    else:
                        reply = f"^3{display_name} ^7has no name history on record."
            except Exception:
                reply = "^1Could not reach ranking service."

            @minqlxtended.next_frame
            def send(m=reply):
                self.msg(m)
            send()

        fetch()
        return minqlxtended.Return.STOP_ALL

    def cmd_rank(self, player, msg, channel):
        sid = str(player.steam_id)

        if len(msg) >= 2 and msg[1].lower() == "mute":
            self._rank_muted.add(sid)
            self._set_mute_pref(DB_KEY_RANK_MUTE, sid, True)
            player.tell("^7rank announcements ^1muted^7. Use ^3!rank unmute ^7to restore.")
            return minqlxtended.Return.STOP_ALL

        if len(msg) >= 2 and msg[1].lower() == "unmute":
            self._rank_muted.discard(sid)
            self._set_mute_pref(DB_KEY_RANK_MUTE, sid, False)
            player.tell("^7rank announcements ^2unmuted^7.")
            return minqlxtended.Return.STOP_ALL

        now = time.time()
        remaining = RANK_COOLDOWN - (now - self._rank_cooldowns.get(sid, 0))
        if remaining > 0:
            player.tell(f"^1rank lookup on cooldown. Wait {int(remaining) + 1}s.")
            return minqlxtended.Return.STOP_ALL

        # `!rank` for yourself, `!rank <#>` for whoever holds that player
        # number. The mute/unmute words are matched above, so they can never
        # reach int() and come back as "Invalid player number".
        if len(msg) >= 2:
            try:
                target = self._find_by_index(int(msg[1]))
            except ValueError:
                player.tell("^1Usage: !rank [#]")
                return minqlxtended.Return.STOP_ALL
            if not target:
                player.tell("^1Invalid player number.")
                return minqlxtended.Return.STOP_ALL
            steam_id, display_name = str(target.steam_id), target.name
        else:
            steam_id, display_name = sid, player.name

        self._rank_cooldowns[sid] = now
        mode = self._pool

        @minqlxtended.thread
        def fetch():
            if not _REQUESTS_OK:
                reply = "^1Ranking service unavailable."
            else:
                try:
                    r = requests.get(
                        f"{self._svc_url()}/player/{steam_id}?mode={mode}",
                        timeout=3,
                    )
                    if r.status_code == 404:
                        reply = f"^3{display_name} ^7has no ranked record yet."
                    elif r.status_code != 200:
                        reply = "^1Could not reach ranking service."
                    else:
                        d = r.json()
                        shown = _rank_and_points(d, d.get("sort_score") or d["mu"])
                        # THE LADDER POSITION, NOT "rank OF total". `rank`
                        # counts only placed players while `total_players`
                        # counts everyone including Nab, so printing them as a
                        # fraction put a placed player's position over an
                        # unplaced population -- two different denominators in
                        # one figure. The board's own position is the number
                        # players recognise, so that is what this prints.
                        seat = d.get("ladder_position") or d.get("rank")
                        placement = f"^7#^5{seat} ^7" if seat and not d.get("is_nab") else ""
                        reply = (
                            f"^3{d['name']} ^7— {placement}{shown} "
                            f"^7(K:^2{d['wins']} ^7D:^1{d['losses']}^7)"
                        )
                except Exception:
                    reply = "^1Could not reach ranking service."

            @minqlxtended.next_frame
            def send(m=reply):
                player.tell(m)
            send()

        fetch()
        return minqlxtended.Return.STOP_ALL
