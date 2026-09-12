# Operators

QLSM keeps a directory of named operators — the people who run or moderate
your servers, each with their SteamID64. Add someone once, then assign them as
a server's **Owner** or **Admin** by picking their name, instead of looking up
and retyping their SteamID in `server.cfg` and `access.txt`.

Operators are managed in **Settings → Operators** and assigned from the
**Owner & Admins** tab wherever server configs are edited.

![Operators page](../images/operators-page.png)

## Add An Operator

1. Go to **Settings → Operators**.
2. Click **Add Operator**.
3. Enter a display name and the operator's SteamID64 (17 digits, starting
   with `7656119`).
4. Choose a **Default admin level** (0-5). This is the level filled in when
   you pick the operator to add as an Admin in the Owner & Admins tab.
5. Click **Add Operator**.

![Add Operator dialog](../images/operators-add-modal.png)

Each SteamID64 can only be in the directory once.

## Delete An Operator

1. Go to **Settings → Operators**.
2. Click the delete icon on the operator's row and confirm.

Deleting an operator only removes them from the directory. It does **not**
remove them from any server: an existing `qlx_owner` line or stored Admin
row with their SteamID64 stays in place, and so does their in-game
permission. To take someone's access away, remove them in the Owner &
Admins tab and save.

## Assign Owner Or Admin

In the instance **Edit Config** window and the **Add Instance** form, the
**Owner & Admins** controls have their own tab, to the right of **Hooks**. On
the preset add and edit pages they appear as a panel above the config fields.

![Owner & Admins panel](../images/owner-admins-panel.png)

- **Owner** — pick an operator. This writes their SteamID64 to the
  `qlx_owner` line of `server.cfg`. The owner always has level 5. The change
  takes effect when the server restarts, so leave **Restart after saving** on.
- **Admins** — pick an operator, choose a level from **1 to 5**, and click
  **Add**. Admins are picked from the operator directory above, so granting a
  raw SteamID means adding that person there first.

Higher levels unlock more minqlx admin commands. Level **5** is the highest
and includes `!setperm`, which lets that admin grant permissions to other
players, so only give 5 to people you trust with that.

Redis — minqlx's own permission database on the running server — is the
source of truth for who is an admin and at what level. QLSM keeps its own
list per instance and reapplies it after every deploy or config save, so a
rebuilt host or a wiped Redis database gets its admins back.

The **Manage operators** link opens **Settings → Operators** in a new tab.

An admin whose SteamID is not in the operator directory shows as a bare
SteamID with an **Add to operators** button. It opens the same Add Operator
dialog as the Operators page, on top of the configuration window, with the
SteamID and current level already filled in. Enter a name and click **Add
Operator**; the row then shows that name. Your unsaved configuration edits
are not affected.

## Row States

Each row in the Admins list carries a badge that says how QLSM's stored list
compares to what the server actually has:

- **Managed** — stored in QLSM and matching the level on the server.
- **Not applied yet** — stored in QLSM, but the server has a different level
  (or none yet). Clears to **Managed** after the next save.
- **Set in-game** — a level on the server with no matching QLSM row: someone
  ran `!setperm` in-game, or this is an admin from another instance that
  shares the same Redis database.
- **Will be revoked on save** — a level on the server that *is* in QLSM's
  managed set but has lost its stored row, so the next save will reset it to
  0. Click **Adopt** to keep the grant instead.
- **No badge at all** — QLSM could not read the server (unreachable host,
  nothing deployed yet, or no instance, as on the Add Instance form). A
  banner above the list explains why. Managed rows always carry a badge, so a
  bare row unambiguously means "unknown," never "definitely not an admin."

**Set in-game** and **Will be revoked on save** rows have no **Remove**
button — there is no stored row to delete. Click **Adopt** first to give the
grant a stored row, then remove it normally if you want it gone.

There is no inline level editor in this first cut: to change someone's level,
remove them and add them back at the new level.

## What Happens In-Game

Levels apply on **Save Configuration** (and after a fresh deploy) without a
server restart, though minqlx's own permission cache can take up to about 30
seconds to pick up the change.

- **Adding** an admin gives them that level in-game.
- **Removing** an admin sets their in-game level back to 0 on the next save.
- **Players promoted in-game** with `!setperm`, and never added through
  QLSM, are left alone (shown as **Set in-game**).

Instances that share a Redis database also share in-game admins: an admin
added on one instance is an admin on the other. If both instances list the
same SteamID, **the last instance saved wins** — QLSM does not detect or warn
about the conflict.

Presets store an `admins.json` file. Nothing is applied in-game until an
instance using the preset is saved.

### If The Push Fails

If QLSM can't reach the server (for example, SSH or Redis is down), the
config is still saved, but the instance log shows a warning and the Owner &
Admins tab shows no per-row badges with a banner explaining the server
couldn't be read. In-game permissions stay as they were until the next
successful save. Check the instance log, and save again once the server is
reachable.

## access.txt

`access.txt` is Quake Live's own file — it only holds Quake Live's native
`admin`, `mod` and `ban` role lines. It no longer holds QLSM admin levels:
those live in QLSM's database and in minqlx's Redis permissions, not on disk.
Any numeric `steamid|level` line left over from an older QLSM version is
stripped out automatically the next time the file is saved, whether from an
instance or a preset.

## Related Pages

- [Edit Configs, Plugins, Factories, And Hooks](../operations/edit-configs.md)
- [User Management & API Keys](user-management.md)
