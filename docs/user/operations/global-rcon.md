# Global RCON

Global RCON sends one command to many instances at once and shows each
instance's reply separately.

Open it from **GLOBAL RCON** in the top navigation, or go to `/global-rcon`.

## Global RCON vs the RCON Console

| | [RCON Console](rcon-console.md) | Global RCON |
|---|---|---|
| Scope | One instance | Every instance you select |
| Opened from | Instance **Actions** menu | Top navigation |
| Live game events | Yes, optional stats stream | No — command output only |
| Output | Single stream | Grouped per target, per command |

Global RCON deliberately has no live stats stream. Use the per-instance
console when you want to watch a single server's events.

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
its own connection state, shown beside its name:

| State | Meaning |
|---|---|
| Connecting | The RCON session for this instance is being established |
| Ready | The instance can receive commands right now |
| Failed | The session dropped or was refused, with the reason shown |

The header shows `N ready / M eligible selected` so you can see at a glance
how much of your selection can actually be reached.

## Sending a command

Type the command and press **Send to N targets**. `N` is the number of
targets that are ready at the moment you press it, and the button is
disabled when that number is zero.

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
  count to expand, or use **Expand all** / **Collapse all** on the run.
- **Copy** puts a target's output on the clipboard.
- Click a target's name to switch the view to that instance's raw stream.

Per-target status labels:

| Label | Meaning |
|---|---|
| Dispatching | The command is being sent |
| Queued | The server accepted the command for delivery |
| Receiving | Output is arriving |
| Quiet | Output arrived and then stopped (after ~1.5s) |
| No response yet | Nothing arrived within ~5 seconds |
| Skipped | Not ready when you pressed Send |
| Rejected / Failed | The instance refused the command or the session dropped |

!!! warning "Queued is delivery, not success"
    **Queued**, **Quiet**, and **No response yet** only describe message
    delivery and silence. They do not mean the command did what you wanted.
    Many QLDS and minqlx commands print nothing on success — and a command
    that fails server-side can also print nothing. Always verify anything
    that changes state by reading it back.

### Verify changes by reading them back

To grant a permission level, run the mutation and then the matching read:

```text
qlx !setperm 76561190000000000 5
qlx !getperm 76561190000000000
```

The second command's output is your evidence; the first command's **Queued**
badge is not.

## Filtering output

Above the output, **All** shows every run grouped by target. Selecting a
single instance switches to that instance's raw line-by-line stream, which is
useful when one server behaves differently from the rest.

The filter list covers your current selection plus any target that appears in
retained history, so output from an instance you have since deselected stays
reachable. Longer lists move into a searchable overflow menu.

History is bounded: the newest 50 runs and the newest 1,000 raw lines per
target are kept.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Instance greyed out in Targets | Not `running` / `updated`, or no RCON port configured |
| Send button disabled | No selected target is currently ready |
| Target stuck on Connecting | Host unreachable, or the RCON service is not running |
| Everything shows Failed after a while | Browser lost its connection to QLSM; it reconnects and rejoins automatically |
| Target shows Skipped every time | It is never ready at send time — check the instance status |

## Related pages

- [RCON Console](rcon-console.md) — single-instance console and live events.
- [Instance Actions Menu](instance-actions-menu.md)
- [Deployment Troubleshooting](../help/deployment-troubleshooting.md)
