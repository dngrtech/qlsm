# Global RCON

Global RCON sends one command to many instances at once and shows each
instance's reply separately.

Open it from **GLOBAL RCON** in the top navigation, or go to `/global-rcon`.

## Global RCON vs the RCON Console

| | [RCON Console](rcon-console.md) | Global RCON |
|---|---|---|
| Scope | One instance | Every instance you select |
| Opened from | Instance **Actions** menu | Top navigation |
| Live game events | Yes, optional structured stats overlay | Raw console output only (no structured overlay) |
| Output | Single stream | Grouped per target, per command |

Every ready target keeps an open RCON connection, so console output the
server prints on its own — chat, connects, admin messages — arrives live in
Global RCON too, not just the reply to a command you sent. What Global RCON
doesn't have is the per-instance console's optional **structured stats
overlay** (a separate parsed kill-feed/event view). Use the per-instance
console when you want that overlay for a single server.

## Selecting targets

The **Targets** pane lists your hosts and their instances.

- Tick an instance to include it. Ticking a host selects all of its
  selectable instances; partial selections show the host as indeterminate.
- **Select All** ticks every selectable instance, **Select None** clears
  everything.
- An instance is selectable only when it is `running` or `updated` **and**
  has an RCON port configured. Anything else is shown greyed out with the
  reason, and cannot be ticked.
- Selections are saved per user in your browser and restored on your next
  visit. An instance that is temporarily unavailable stays remembered, so it
  comes back selected once it is running again.

On narrow screens the pane collapses behind a **Hide targets** /
**Show targets** toggle.

### Readiness

Selection is not the same as readiness. Each selected instance moves through
its own connection state, shown as a colored dot beside its name — hover it
for the exact state and, if failed, the reason:

| Dot | State | Meaning |
|---|---|---|
| 🟢 Green | Ready | The instance can receive commands right now |
| 🟡 Amber | Connecting | The RCON session for this instance is being established |
| 🔴 Red | Failed | The session dropped or was refused, with the reason shown |

The header shows `N ready / M eligible selected` so you can see at a glance
how much of your selection can actually be reached.

## Sending a command

**The active output tab controls where the command goes:**

- **ALL** selected — the button reads **Send to N targets** and dispatches
  to every ready instance in your current selection.
- **A specific instance's tab** selected — the button reads **Send to
  \<instance name\>** and dispatches to **that instance only**, even if
  other instances are also ticked in the Targets pane. This lets you send a
  one-off command to a single server without changing your selection.

The button is disabled whenever the instance(s) it would send to are not
ready — for a single-instance tab, that means that one instance specifically,
regardless of whether other selected instances are ready.

Dispatch is **not atomic**. The command is delivered to each ready instance
individually, so some can succeed while others fail. The recipient list is a
snapshot taken when you press Send:

- Ready targets receive the command.
- Selected-but-not-ready targets are recorded as **Skipped**, with the
  reason, and are **never retried later**. If you want them included, wait
  until they are ready and send again.

Use Up/Down in the input to cycle through your recent commands.

## Reading the output

Each send produces one run, newest first, showing the command, the time, and
one block per target.

- Short replies are shown in full.
- Replies longer than five lines collapse to their first line; click the line
  count to expand, or use the **Expand All** / **Collapse All** toggle on the
  run to do it for every target at once.
- **Copy** puts a target's output on the clipboard.
- Click a target's name to switch the view to that instance's raw stream.

Per-target status labels:

| Label | Meaning |
|---|---|
| Dispatching | The command is being sent |
| Queued | The server accepted the command for delivery |
| Receiving | Output is arriving |
| No response yet | Nothing arrived within ~5 seconds |
| Skipped | Not ready when you pressed Send |
| Rejected / Failed | The instance refused the command or the session dropped |

!!! warning "Queued is delivery, not success"
    **Queued** and **No response yet** only describe message delivery and
    silence. They do not mean the command did what you wanted. Many QLDS and
    minqlx commands print nothing on success — and a command that fails
    server-side can also print nothing. Always verify anything that changes
    state by reading it back.

A target's block can keep showing **Receiving** and growing well past your
command's actual reply — the connection stays open, so any chat, connect, or
admin-plugin lines the server prints in the meantime land in the same block.
It settles once the target has been quiet for about 1.5 seconds, and starts
fresh the next time you send that target a command.

### Verify changes by reading them back

To grant a permission level, run the mutation and then the matching read:

```text
qlx !setperm 76561190000000000 5
qlx !getperm 76561190000000000
```

The second command's output is your evidence; the first command's **Queued**
badge is not.

## Filtering output

Above the output, **ALL** shows every run grouped by target. Selecting a
single instance's tab switches to that instance's raw line-by-line stream,
which is useful when one server behaves differently from the rest — **and
also scopes Send to that one instance**, see [Sending a command](#sending-a-command)
above.

The tab list always mirrors your current tree selection: tick or untick an
instance in the Targets pane and its tab appears or disappears immediately.
Unticking an instance you were viewing drops its tab, but its output already
shown under **ALL** is unaffected.

History is bounded: the newest 50 runs and the newest 1,000 raw lines per
target are kept.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Instance greyed out in Targets | Not `running` / `updated`, or no RCON port configured |
| Send button disabled | Nothing the active tab would send to is ready — on **ALL** that means no selected target is ready; on a single instance's tab, that instance specifically isn't ready |
| Target stuck on Connecting | Host unreachable, or the RCON service is not running |
| Everything shows Failed after a while | Browser lost its connection to QLSM; it reconnects and rejoins automatically |
| Target shows Skipped every time | It is never ready at send time — check the instance status |

## Related pages

- [RCON Console](rcon-console.md) — single-instance console and live events.
- [Instance Actions Menu](instance-actions-menu.md)
- [Deployment Troubleshooting](../help/deployment-troubleshooting.md)
