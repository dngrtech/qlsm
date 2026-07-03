# Release Notes

QLSM uses `v<major>.<minor>.<patch>` tags. Every merged pull request is listed as an individual release entry.

| Version | Date | PR | Changes |
| --- | --- | --- | --- |
| `v1.13.5` | 2026-07-03 | [#135](https://github.com/dngrtech/qlsm/pull/135) | Fix preset ZIP import rejecting `.so` plugin scripts, and surface `.so` scripts correctly in the preset API instead of silently dropping them. |
| `v1.13.4` | 2026-07-02 | — | Bug fixes and improvements. |
| `v1.13.3` | 2026-07-02 | [#133](https://github.com/dngrtech/qlsm/pull/133) | Add preset ZIP import: upload a previously exported preset archive from the Preset Manager Load tab. Archives are validated before anything is written, and name conflicts offer overwrite or rename. Built-in presets can no longer be downloaded. |
| `v1.13.2` | 2026-06-29 | [#131](https://github.com/dngrtech/qlsm/pull/131) | Replace the separate Load, Save, and Update preset dialogs with a unified two-tab Preset Manager. |
| `v1.13.1` | 2026-06-27 | [#130](https://github.com/dngrtech/qlsm/pull/130) | Add preset ZIP export. Download Preset is available both after saving a preset (Preset Manager Save tab) and for any selected preset in the Preset Manager Load tab; the archive includes the full preset directory, including custom config files, factories, scripts, user hooks, checked selections, and export metadata. |
| `v1.12.13` | 2026-06-26 | [#129](https://github.com/dngrtech/qlsm/pull/129) | Keep `STOPPED` instances stopped across host reboots: stopping an instance now disables its systemd unit (and starting/restarting re-enables it), so the auto-restart reboot no longer brings stopped servers back up and leaves the panel showing the wrong status. Adds `flask reconcile-service-enablement` to backfill already-stopped instances. |
| `v1.12.12` | 2026-06-24 | [#128](https://github.com/dngrtech/qlsm/pull/128) | Add retry handling to `force_rate.so` so the LD_PRELOAD hook waits briefly for qzeroded's target text page before giving up on the LAN-rate patch. |
| `v1.12.11` | 2026-06-23 | [#127](https://github.com/dngrtech/qlsm/pull/127) | Apply static network hardening to all hosts, not just non-standalone hosts. |
| `v1.12.10` | 2026-06-23 | [#126](https://github.com/dngrtech/qlsm/pull/126) | Auto-recover hosts after reboot timeouts: failed restart playbooks now probe for post-reboot reachability before marking ERROR, and the status poller can restore stale ERROR hosts to ACTIVE when live instance status is available. |
| `v1.12.9` | 2026-06-22 | [#125](https://github.com/dngrtech/qlsm/pull/125) | Fix the Test Connection button staying disabled for standalone hosts in the Add Host modal. |
| `v1.12.8` | 2026-06-21 | [#123](https://github.com/dngrtech/qlsm/pull/123) | Hide the `user-hooks/` directory from the Configuration Files tab. |
| `v1.12.7` | 2026-06-20 | [#122](https://github.com/dngrtech/qlsm/pull/122) | Add `qlx_brandingMapCredit` cvar to `branding.py` (default `0`). When `0`, the map's baked-in author credit is dropped from the loading screen and only the configured `qlx_serverBrandTopField` / `qlx_serverBrandBottomField` brand text is shown; set to `1` to restore the original behaviour of prepending the map credit. |
| `v1.12.6` | 2026-06-19 | — | Fix factory file upload in Edit Instance Config failing with "Failed to read file". |
| `v1.12.5` | 2026-06-18 | — | Fix `commlink.py` calling `minqlx.unload_plugin("commlink")` from `__init__` — this raised `PluginUnloadError` (plugin not yet registered), cascading into a Python runtime `SystemError` that broke all plugin commands including `!ban`. |
| `v1.12.4` | 2026-06-18 | — | Fix `zadd_compat` in ban.py catching only `TypeError` — redis-py 2.x raises `RedisError` when a dict is passed as positional args, so `!ban` always threw instead of falling back to the old API. |
| `v1.12.3` | 2026-06-14 | [#119](https://github.com/dngrtech/qlsm/pull/119) | Fix `zadd_compat` in ban.py (both trees) catching `Exception` instead of `TypeError`, which could silently mask unrelated runtime errors in the argument expressions. |
| `v1.12.2` | 2026-06-14 | [#118](https://github.com/dngrtech/qlsm/pull/118) | Fix three Hooks tab UX bugs: uploading a hook no longer blanks the tab (silent reload); replacing an existing hook now enables "Apply & Restart" since the server must reload the binary; description save button was invisible (undefined CSS variable `--accent-success`) and is now correctly styled with the accent colour. |
| `v1.12.0` | 2026-06-14 | [#117](https://github.com/dngrtech/qlsm/pull/117) | Expanded user documentation: new LD_PRELOAD Hooks page, Hooks tab coverage in Edit Configs, plugin requirements.txt auto-install docs, Re-run Host Setup availability and downtime behavior corrected, legacy 99k LAN Rate migration notes removed, nav index expanded. |
| `v1.11.9` | 2026-06-14 | [#116](https://github.com/dngrtech/qlsm/pull/116) | Fix standalone host IP address field pre-filling with the self-host IP when switching providers in the Add Host modal. |
| `v1.11.8` | 2026-06-13 | [#115](https://github.com/dngrtech/qlsm/pull/115) | Removed "99k LAN rate is not compatible with Ubuntu" warning from the add-host form and connection test response — Ubuntu hosts have supported 99k LAN rate via the LD_PRELOAD hook since v1.10.0. |
| `v1.11.7` | 2026-06-13 | [#113](https://github.com/dngrtech/qlsm/pull/113) | Fix 7 critical specqueue plugin bugs: thread leak on plugin reload (AFK poll thread had no stop condition), TOCTOU race on ELO fetch flag, `!afk <id>` crash on unknown player, self-crashing exception handler in `add_spectators` (malformed format string), unconditional `traceback` import, missing `ENABLE_LOG` guard in `queue_message`, and dead `elo_dict` code. Applied to both `configs/presets/` and `ql-assets/` copies. |
| `v1.11.6` | 2026-06-13 | [#112](https://github.com/dngrtech/qlsm/pull/112) | Create `user-hooks/` directory on instance creation so the Ansible deploy playbook rsync has a valid source and does not fail with "No such file or directory". |
| `v1.11.5` | 2026-06-11 | [#111](https://github.com/dngrtech/qlsm/pull/111) | Fix `qlsm-rcon` container crash-loop caused by redis-py 8.0.0 changing the default `socket_timeout` from `None` to 5 seconds. Pubsub `listen()` now raises `TimeoutError` after 5 idle seconds and exits. Explicitly set `socket_timeout=None` to restore the previous behaviour for pubsub listeners. |
| `v1.11.4` | 2026-06-11 | [#110](https://github.com/dngrtech/qlsm/pull/110) | Prevent `needrestart` from restarting `systemd-networkd` and `systemd-udevd` after package upgrades. On OVH VPS hosts, restarting these services disrupts the /32 DHCP routing setup and causes the VM to become unreachable for incoming connections until rebooted. |
| `v1.11.3` | 2026-06-11 | [#109](https://github.com/dngrtech/qlsm/pull/109) | Added `reset_acc` minqlx plugin with `!resetstats` (resets accuracy, K/D, and score) and `!resetacc` (resets accuracy only, K/D unchanged). Both commands are silent — not broadcast to other players. Requires a minqlx C patch that adds `reset_player_stats()` and `reset_player_accuracy()` bindings; patch is applied automatically on re-run host setup. Fixed `sync_instance_configs_and_restart.yml` to copy the rebuilt minqlx binary from the shared location to each instance directory, so re-runs now actually deploy the new binary. Removed `spec_switch_guard` plugin (replaced by a hook). |
| `v1.11.2` | 2026-06-10 | [#107](https://github.com/dngrtech/qlsm/pull/107) | Ensure `ssh.service` is enabled on boot during host setup. On Ubuntu 24.04, `unattended-upgrades` can upgrade systemd packages and trigger `daemon-reexec`, which drops the `ssh.socket` listener and leaves the host unreachable. Enabling `ssh.service` makes sshd run as a persistent daemon that owns its own socket, immune to socket-activation cycling. |
| `v1.11.1` | 2026-06-05 | [#105](https://github.com/dngrtech/qlsm/pull/105) | Pinned host-level minqlx Python deps to `ql-assets/data/minqlx-plugins/requirements.txt` (was an unpinned `pip install redis, pyzmq, discord.py`, drifting to redis-py 5.x on fresh hosts and breaking the serverchecker Unix-socket connection). Added `discord.py` to the common requirements so bundled `mydiscordbot` / `discord_extensions/*` plugins work without a manual `pip install`. |
| `v1.11.0` | 2026-06-05 | [#93](https://github.com/dngrtech/qlsm/pull/93) | Hook manager: dedicated `user-hooks/` directory with full CRUD — upload, download, replace, rename, delete, and per-file descriptions — plus inline editing and a delete confirmation modal in the Hooks tab. |
| `v1.10.12` | 2026-06-04 | [#104](https://github.com/dngrtech/qlsm/pull/104) | Auto-install minqlx plugin Python dependencies from `requirements.txt` on every deploy, apply-config, and restart. pip failures are non-blocking and logged to the instance log. |
| `v1.10.11` | 2026-06-02 | [#103](https://github.com/dngrtech/qlsm/pull/103) | Allow re-running host setup when host is in ERROR status, not just ACTIVE. |
| `v1.10.10` | 2026-06-02 | [#102](https://github.com/dngrtech/qlsm/pull/102) | Reverted redundant QLSM-LANRATE chain cleanup task from `setup_host.yml` — `iptables-restore` already removes custom chains not present in the rules file. |
| `v1.10.9` | 2026-06-02 | [#101](https://github.com/dngrtech/qlsm/pull/101) | Fixed 127.0.0.1 showing as client IP on hosts with stale `QLSM-LANRATE-*` iptables chains from a pre-release version. Instance restart or hook sync now removes the chains automatically. |
| `v1.10.8` | 2026-06-02 | [#100](https://github.com/dngrtech/qlsm/pull/100) | Removed `sv_serverType` from qlds startup args — the `force_rate.so` hook makes it unnecessary and keeping the default (`2`) shows real client IPs in `rcon status`. |
| `v1.10.7` | 2026-06-01 | [#98](https://github.com/dngrtech/qlsm/pull/98) | Fixed DHCP lease expiry on systemd-networkd hosts (OVH/standalone) by allowing DHCP responses in the iptables firewall template. |
| `v1.10.6` | 2026-05-27 | [#97](https://github.com/dngrtech/qlsm/pull/97) | Auto-transitions REBOOTING hosts to ACTIVE on web container startup, fixing the self-hosted reboot recovery bug. |
| `v1.10.5` | 2026-05-26 | [#94](https://github.com/dngrtech/qlsm/pull/94) | Normalized local SSH key ownership during standalone and self-host setup so reruns do not fail on root-owned private keys. |
| `v1.10.4` | 2026-05-26 | [#92](https://github.com/dngrtech/qlsm/pull/92) | Hooks tab now shows registered hooks whose binary is missing on disk, with a warning and the ability to remove them. |
| `v1.10.3` | 2026-05-26 | [#91](https://github.com/dngrtech/qlsm/pull/91) | Config apply now self-heals root-owned files in minqlx-plugins before rsync, enabling UI-only recovery from permission-related ERROR states. |
| `v1.10.2` | 2026-05-26 | [#90](https://github.com/dngrtech/qlsm/pull/90) | Fixed system hooks rsync running as root, preventing permission errors on subsequent config apply. |
| `v1.10.1` | 2026-05-26 | [#89](https://github.com/dngrtech/qlsm/pull/89) | Re-run Host Setup action now available from ERROR state, enabling recovery without a full host restart. |
| `v1.10.0` | 2026-05-25 | [#88](https://github.com/dngrtech/qlsm/pull/88) | Migrated 99k LAN Rate to LD_PRELOAD hook path, eliminating iptables NAT dependency. |
| `v1.9.0` | 2026-05-24 | [#87](https://github.com/dngrtech/qlsm/pull/87) | Added the app version footer, update-available link, latest-version manifest, and full release notes history. |
| `v1.8.5` | 2026-05-24 | [#86](https://github.com/dngrtech/qlsm/pull/86) | Bug fixes and performance improvements. |
| `v1.8.4` | 2026-05-24 | [#85](https://github.com/dngrtech/qlsm/pull/85) | Added per-instance LD_PRELOAD hook management with UI, API, and apply flow. |
| `v1.8.3` | 2026-05-23 | [#84](https://github.com/dngrtech/qlsm/pull/84) | Added Redis Unix socket support and a re-run host setup action. |
| `v1.8.2` | 2026-05-22 | [#83](https://github.com/dngrtech/qlsm/pull/83) | Restored operator control of `qlx_serverBrandName`. |
| `v1.8.1` | 2026-05-21 | [#82](https://github.com/dngrtech/qlsm/pull/82) | Bug fixes and performance improvements. |
| `v1.8.0` | 2026-05-17 | [#81](https://github.com/dngrtech/qlsm/pull/81) | Added secured CommLink plugin hardening and player command cooldowns. |
| `v1.7.7` | 2026-05-17 | [#79](https://github.com/dngrtech/qlsm/pull/79) | Added `qlsm-uninstall.sh` for clean uninstall and optional purge. |
| `v1.7.6` | 2026-05-17 | [#78](https://github.com/dngrtech/qlsm/pull/78) | Added the first-party `kickban` minqlx plugin. |
| `v1.7.5` | 2026-05-16 | [#77](https://github.com/dngrtech/qlsm/pull/77) | Added QLSM self-host detection during standalone host setup. |
| `v1.7.4` | 2026-05-15 | [#76](https://github.com/dngrtech/qlsm/pull/76) | Added performance and QL capacity chips to plan selection and host details. |
| `v1.7.3` | 2026-05-14 | [#75](https://github.com/dngrtech/qlsm/pull/75) | Bug fixes and performance improvements. |
| `v1.7.2` | 2026-05-14 | [#74](https://github.com/dngrtech/qlsm/pull/74) | Added `WORKER_REPLICAS` for configurable background worker count. |
| `v1.7.1` | 2026-05-14 | [#73](https://github.com/dngrtech/qlsm/pull/73) | Added self-host IP autofill from the browser hostname. |
| `v1.7.0` | 2026-05-14 | [#72](https://github.com/dngrtech/qlsm/pull/72) | Improved host setup recovery for slow SteamCMD/CDN downloads. |
| `v1.6.6` | 2026-05-14 | [#71](https://github.com/dngrtech/qlsm/pull/71) | Added the LG-ANTILAG built-in preset. |
| `v1.6.5` | 2026-05-12 | [#70](https://github.com/dngrtech/qlsm/pull/70) | Bug fixes and performance improvements. |
| `v1.6.4` | 2026-05-11 | [#69](https://github.com/dngrtech/qlsm/pull/69) | Bug fixes and performance improvements. |
| `v1.6.3` | 2026-05-10 | [#68](https://github.com/dngrtech/qlsm/pull/68) | Added CodeMirror highlighting and diagnostics for `.ent` files. |
| `v1.6.2` | 2026-05-10 | [#67](https://github.com/dngrtech/qlsm/pull/67) | Bug fixes and performance improvements. |
| `v1.6.1` | 2026-05-09 | [#66](https://github.com/dngrtech/qlsm/pull/66) | Bug fixes and performance improvements. |
| `v1.6.0` | 2026-05-10 | [#65](https://github.com/dngrtech/qlsm/pull/65) | Added config folders, nested `.ent` files, folder CRUD, and row actions. |
| `v1.5.19` | 2026-05-08 | [#64](https://github.com/dngrtech/qlsm/pull/64) | Bug fixes and performance improvements. |
| `v1.5.18` | 2026-05-08 | [#63](https://github.com/dngrtech/qlsm/pull/63) | Bug fixes and performance improvements. |
| `v1.5.17` | 2026-05-08 | [#62](https://github.com/dngrtech/qlsm/pull/62) | Bug fixes and performance improvements. |
| `v1.5.16` | 2026-05-07 | [#61](https://github.com/dngrtech/qlsm/pull/61) | Bug fixes and performance improvements. |
| `v1.5.15` | 2026-05-07 | [#60](https://github.com/dngrtech/qlsm/pull/60) | Deployment and maintenance improvements. |
| `v1.5.14` | 2026-05-07 | [#59](https://github.com/dngrtech/qlsm/pull/59) | Bug fixes and performance improvements. |
| `v1.5.13` | 2026-05-07 | [#58](https://github.com/dngrtech/qlsm/pull/58) | Bug fixes and performance improvements. |
| `v1.5.12` | 2026-05-07 | [#57](https://github.com/dngrtech/qlsm/pull/57) | Bug fixes and performance improvements. |
| `v1.5.11` | 2026-05-07 | [#56](https://github.com/dngrtech/qlsm/pull/56) | Added a unified file manager for configs, plugins, and factories. |
| `v1.5.10` | 2026-05-03 | [#55](https://github.com/dngrtech/qlsm/pull/55) | Bug fixes and performance improvements. |
| `v1.5.9` | 2026-05-01 | [#54](https://github.com/dngrtech/qlsm/pull/54) | Bug fixes and performance improvements. |
| `v1.5.8` | 2026-05-01 | [#53](https://github.com/dngrtech/qlsm/pull/53) | Added automatic CPU affinity assignment for QLDS instances. |
| `v1.5.7` | 2026-04-30 | [#52](https://github.com/dngrtech/qlsm/pull/52) | Added a recommended plan badge for Vultr host creation. |
| `v1.5.6` | 2026-04-30 | [#51](https://github.com/dngrtech/qlsm/pull/51) | Added Vultr host plan resizing. |
| `v1.5.5` | 2026-04-29 | [#50](https://github.com/dngrtech/qlsm/pull/50) | Improved binary description editing. |
| `v1.5.4` | 2026-04-29 | [#49](https://github.com/dngrtech/qlsm/pull/49) | Added an All option to the server logs filter. |
| `v1.5.3` | 2026-04-29 | [#48](https://github.com/dngrtech/qlsm/pull/48) | Added built-in preset seeding for binary plugin descriptions. |
| `v1.5.2` | 2026-04-29 | [#47](https://github.com/dngrtech/qlsm/pull/47) | Added expanded server log viewing. |
| `v1.5.1` | 2026-04-29 | [#46](https://github.com/dngrtech/qlsm/pull/46) | Bug fixes and performance improvements. |
| `v1.5.0` | 2026-04-28 | [#45](https://github.com/dngrtech/qlsm/pull/45) | Added editable descriptions for `.so` plugin binaries. |
| `v1.4.13` | 2026-04-28 | [#44](https://github.com/dngrtech/qlsm/pull/44) | Deployment and maintenance improvements. |
| `v1.4.12` | 2026-04-28 | [#43](https://github.com/dngrtech/qlsm/pull/43) | Bug fixes and performance improvements. |
| `v1.4.11` | 2026-04-28 | [#42](https://github.com/dngrtech/qlsm/pull/42) | Bug fixes and performance improvements. |
| `v1.4.10` | 2026-04-27 | [#41](https://github.com/dngrtech/qlsm/pull/41) | Added confirmation before QLFilter uninstall. |
| `v1.4.9` | 2026-04-27 | [#40](https://github.com/dngrtech/qlsm/pull/40) | Bug fixes and performance improvements. |
| `v1.4.8` | 2026-04-27 | [#39](https://github.com/dngrtech/qlsm/pull/39) | Bug fixes and performance improvements. |
| `v1.4.7` | 2026-04-27 | [#38](https://github.com/dngrtech/qlsm/pull/38) | Bug fixes and performance improvements. |
| `v1.4.6` | 2026-04-27 | [#37](https://github.com/dngrtech/qlsm/pull/37) | Bug fixes and performance improvements. |
| `v1.4.5` | 2026-04-27 | [#36](https://github.com/dngrtech/qlsm/pull/36) | Added a downtime warning before QLFilter install. |
| `v1.4.4` | 2026-04-27 | [#35](https://github.com/dngrtech/qlsm/pull/35) | Bug fixes and performance improvements. |
| `v1.4.3` | 2026-04-27 | [#34](https://github.com/dngrtech/qlsm/pull/34) | Added QLFilter status indicators to host lists. |
| `v1.4.2` | 2026-04-27 | [#33](https://github.com/dngrtech/qlsm/pull/33) | Bug fixes and performance improvements. |
| `v1.4.1` | 2026-04-27 | [#32](https://github.com/dngrtech/qlsm/pull/32) | Bug fixes and performance improvements. |
| `v1.4.0` | 2026-04-27 | [#31](https://github.com/dngrtech/qlsm/pull/31) | Bug fixes and performance improvements. |
| `v1.3.8` | 2026-04-25 | [#30](https://github.com/dngrtech/qlsm/pull/30) | Added immutable built-in default config presets. |
| `v1.3.7` | 2026-04-23 | [#29](https://github.com/dngrtech/qlsm/pull/29) | Improved GitHub Pages docs design and content. |
| `v1.3.6` | 2026-04-23 | [#28](https://github.com/dngrtech/qlsm/pull/28) | Published user documentation through GitHub Pages. |
| `v1.3.5` | 2026-04-21 | [#26](https://github.com/dngrtech/qlsm/pull/26) | Bug fixes and performance improvements. |
| `v1.3.4` | 2026-04-21 | [#25](https://github.com/dngrtech/qlsm/pull/25) | Bug fixes and performance improvements. |
| `v1.3.3` | 2026-04-22 | [#24](https://github.com/dngrtech/qlsm/pull/24) | Added the in-app documentation viewer. |
| `v1.3.2` | 2026-04-19 | [#23](https://github.com/dngrtech/qlsm/pull/23) | Bug fixes and performance improvements. |
| `v1.3.1` | 2026-04-19 | [#22](https://github.com/dngrtech/qlsm/pull/22) | Added self-host OS auto-detection with Ubuntu LAN-rate warnings. |
| `v1.3.0` | 2026-04-19 | [#21](https://github.com/dngrtech/qlsm/pull/21) | Bug fixes and performance improvements. |
| `v1.2.9` | 2026-04-19 | [#20](https://github.com/dngrtech/qlsm/pull/20) | Development and maintenance improvements. |
| `v1.2.8` | 2026-04-17 | [#19](https://github.com/dngrtech/qlsm/pull/19) | Bug fixes and performance improvements. |
| `v1.2.7` | 2026-04-17 | [#18](https://github.com/dngrtech/qlsm/pull/18) | Bug fixes and performance improvements. |
| `v1.2.6` | 2026-04-17 | [#17](https://github.com/dngrtech/qlsm/pull/17) | Bug fixes and performance improvements. |
| `v1.2.5` | 2026-04-17 | [#16](https://github.com/dngrtech/qlsm/pull/16) | Bug fixes and performance improvements. |
| `v1.2.4` | 2026-04-17 | [#15](https://github.com/dngrtech/qlsm/pull/15) | Documented cron-based auto-update setup. |
| `v1.2.3` | 2026-04-17 | [#14](https://github.com/dngrtech/qlsm/pull/14) | Bug fixes and performance improvements. |
| `v1.2.2` | 2026-04-17 | [#13](https://github.com/dngrtech/qlsm/pull/13) | Bug fixes and performance improvements. |
| `v1.2.1` | 2026-04-17 | [#12](https://github.com/dngrtech/qlsm/pull/12) | Bug fixes and performance improvements. |
| `v1.2.0` | 2026-04-17 | [#11](https://github.com/dngrtech/qlsm/pull/11) | Added expanded editor support for plugin files and fixed editor theme consistency. |
| `v1.1.8` | 2026-04-16 | [#10](https://github.com/dngrtech/qlsm/pull/10) | Bug fixes and performance improvements. |
| `v1.1.7` | 2026-04-14 | [#9](https://github.com/dngrtech/qlsm/pull/9) | Synced the GitHub Pages landing page with README content. |
| `v1.1.6` | 2026-04-12 | [#8](https://github.com/dngrtech/qlsm/pull/8) | Auto-opens Add Host after the first password change. |
| `v1.1.5` | 2026-04-14 | [#7](https://github.com/dngrtech/qlsm/pull/7) | Added the self-host deployment provider. |
| `v1.1.4` | 2026-04-08 | [#5](https://github.com/dngrtech/qlsm/pull/5) | Bug fixes and performance improvements. |
| `v1.1.3` | 2026-04-07 | [#4](https://github.com/dngrtech/qlsm/pull/4) | Bug fixes and performance improvements. |
| `v1.1.2` | 2026-04-07 | [#3](https://github.com/dngrtech/qlsm/pull/3) | Added bundled QL assets, minqlx plugins, and QLFilter sources to version control. |
| `v1.1.1` | 2026-04-07 | [#2](https://github.com/dngrtech/qlsm/pull/2) | Bug fixes and performance improvements. |
| `v1.1.0` | 2026-04-07 | [#1](https://github.com/dngrtech/qlsm/pull/1) | Bug fixes and performance improvements. |
| `v1.0.0` | Before 2026-04-07 | — | Initial QLSM baseline before tracked pull request history. |
