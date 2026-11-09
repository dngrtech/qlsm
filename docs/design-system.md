# Design System

Reference for QLSM's frontend visual language: color tokens, typography, the
reusable component inventory, and the Headless UI patterns used to build new
UI. Keep this in sync whenever colors, shared components, or interaction
patterns change (see `CLAUDE.md` → Documentation).

## Visual identity

Dark, industrial/tech aesthetic — neon accent color, glow/scan-line motifs,
monospace touches for a "server console" feel. Light mode exists and is a
softer/desaturated variant of the same token set, not a separate design.

## Color tokens

Source of truth: CSS custom properties in `frontend-react/src/index.css`
(`:root` = light theme, `.dark` = dark theme override). Reference these via
the theme-aware utility classes below — not raw Tailwind color utilities —
so components adapt correctly between light and dark.

> **Known drift:** `frontend-react/tailwind.config.js` also defines an
> `accent`/`surface` color palette, but those values are hardcoded to the
> **dark-mode** hex codes only (see comment at `tailwind.config.js:11-17`).
> Utilities like `bg-accent-primary` will therefore render the dark-mode
> green in light mode too. Until that's fixed, prefer the CSS-variable-backed
> classes (`.bg-theme-*`, `.text-theme-*`, `.border-theme*`, or
> `var(--accent-*)` inline) for anything that must theme-swap correctly.

| Token | Light | Dark | Usage |
|---|---|---|---|
| `--accent-primary` | `#0D9668` | `#00FF9D` | primary action / brand accent |
| `--accent-primary-dim` | `#087A53` | `#00CC7D` | primary, muted state |
| `--accent-danger` | `#DC2626` | `#FF3366` | destructive actions, errors |
| `--accent-danger-dim` | `#B91C1C` | `#CC2952` | danger, muted state |
| `--accent-warning` | `#D97706` | `#FFB800` | caution / warning states |
| `--accent-info` | `#0891B2` | `#00D4FF` | informational accents |
| `--surface-base` | `#F0F2F5` | `#0A0E14` | page background |
| `--surface-raised` | `#FAFBFC` | `#111820` | cards, panels |
| `--surface-overlay` | `#FFFFFF` | `#141B22` | modals, dropdowns |
| `--surface-elevated` | `#E8ECF1` | `#1C2530` | nested/elevated surfaces |
| `--surface-border` | `#D0D7E0` | `#2A3441` | default borders |
| `--surface-border-strong` | `#B0BAC6` | `#3D4A5C` | emphasized borders |
| `--text-primary` | `#0F172A` | `#F1F5F9` | primary text |
| `--text-secondary` | `#3E4C5E` | `#94A3B8` | secondary text |
| `--text-muted` | `#7E8D9F` | `#64748B` | muted/disabled text |

Utility classes wrapping these tokens (`frontend-react/src/index.css:181-217`):
`.bg-theme-base`, `.bg-theme-raised`, `.bg-theme-overlay`, `.bg-theme-elevated`,
`.border-theme`, `.border-theme-strong`, `.text-theme-primary`,
`.text-theme-secondary`, `.text-theme-muted`, `.text-theme-danger`.

Glow effects (dark-mode-flavored, defined directly in `tailwind.config.js`
`boxShadow`): `shadow-glow-sm/md/lg`, `shadow-glow-danger`, `shadow-inner-glow`.

Diff views tint removed lines with `--accent-danger` and added lines with
`--accent-primary` (alpha 0.10–0.35), see `utils/codemirrorSetup.js`.

## Typography

Defined in `tailwind.config.js:36-40`:

| Family | Fonts | Tailwind class | Usage |
|---|---|---|---|
| Display | Rajdhani → system-ui | `font-display` | headings, emphasis |
| Mono | Share Tech Mono → Consolas | `font-mono` | console/log output, technical data |
| Sans | Exo 2 → system-ui | `font-sans` (default) | body text |

## Component inventory

### CSS-class components (native elements + Tailwind `@apply`)

Most primitives (buttons, cards, inputs, alerts, tabs, tables) are **not**
React components — they're CSS classes in `frontend-react/src/index.css`
applied directly to native `<button>`/`<div>`/`<table>` elements.

| Class | Location | Purpose |
|---|---|---|
| `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger`, `.btn-caution`, `.btn-ghost` | `index.css:251-386` | button variants, each with `:hover`/`:focus-visible`/`:disabled` states |
| `.input-base`, `.input-error`, `.input-caution` | `index.css:388-431` | text inputs with validation states |
| `.select-base` | `index.css:433-455` | native `<select>` styling |
| `.card`, `.card-elevated` | `index.css:457-476` | container surfaces |
| `.modal-backdrop`, `.modal-panel` | `index.css:478-530` | modal chrome (paired with Headless UI `Dialog`, see below) |
| `.alert-error`, `.alert-warning`, `.alert-success` | `index.css:584-615` | inline alert banners |
| `.tab-item`, `.tab-item-active` | `index.css:564-582` | tab navigation |
| `.table-tech` | `index.css:726-752` | data table styling |
| `.status-pulse`, `.status-pulse-active/-error/-warning` | `index.css:532-562` | animated status dot |
| `.loader-tech` | `index.css:617-634` | loading spinner |

When building new UI, reuse these classes rather than writing new button/card/
input styles — check `index.css` for the full variant before adding a new one.

### React components (`frontend-react/src/components/`)

| Component | Path | Notes |
|---|---|---|
| `ConfirmationModal` | `ConfirmationModal.jsx` | Headless UI `Dialog`; `confirmButtonVariant` prop: `danger`/`red`/`primary`/`amber`/`warning`/`orange` (default → secondary styling); `confirmButtonText`, `cancelButtonText` |
| `Notification` / `NotificationProvider` | `Notification.jsx`, `NotificationProvider.jsx` | Toast + queue provider; `variant`: `success`/`error`/`info`; `autoClose`, `autoCloseDelay` (ms) |
| `StatusIndicator` | `StatusIndicator.jsx` | Colored status pill; `status` prop drives color/animation (running/active/updated/pollable/stopped/error/idle) |
| `ThemeToggleButton` | `ThemeToggleButton.jsx` | Light/dark switch, reads `ThemeContext` |
| `FileUploadButton` | `FileUploadButton.jsx` | Generic file-upload trigger |
| `HostActionsMenu` / `InstanceActionsMenu` | `HostActionsMenu.jsx`, `InstanceActionsMenu.jsx` | Headless UI `Menu` action dropdowns, floating-ui positioned |
| `RconConsoleModal` | `RconConsoleModal.jsx` | Modal wrapper around the RCON console UI |
| `CodeMirrorEditor` | `CodeMirrorEditor.jsx` | Shared code editor used by file manager / config editors; theme and highlight styles live in `utils/codemirrorSetup.js` (`themeExtensions`, `mergeThemeExtensions`) |
| `FloatingListbox` | `components/common/FloatingListbox.jsx` | Headless UI `Listbox`-based custom select with floating-ui positioning; supports option badges (`OptionBadge`) and perf chips |
| `InfoTooltip` | `components/common/InfoTooltip.jsx` | Hover tooltip; props: `size`, `placement` (top/bottom/left/right), `variant` (info/cyan/warning/danger), `testId` (data-testid for the hover target) |
| `CompatibilityRow` | `components/presetManager/CompatibilityRow.jsx` | One plugin row of a cross-runtime compatibility report (checkbox for replaceable plugins, none for dropped ones); props: `entry`, `sourceRuntime`, `targetRuntime`, `checked`, `onToggle`, `sourceNoun` (`'preset'` default, `'instance'` for the upgrade dialog), `showEnablement` (upgrade dialog only: tags and mutes rows whose `originally_checked` is false; off for presets, where a legacy preset reports every row unchecked). Shared by `PresetCompatibilityDialog` and `hosts/RuntimeUpgradeDialog` |
| `QlColorString` | `components/common/QlColorString.jsx` | Renders Quake Live `^`-color-coded strings as styled spans |
| `SubfolderPluginNotice` | `components/fileManager/SubfolderPluginNotice.jsx` | Dismissible `.alert-warning` banner; props: `count` (0 renders nothing), `onDismiss`. Parent owns dismissal state |
| `SidebarResizeHandle` | `components/fileManager/SidebarResizeHandle.jsx` | Drag handle between the file list and the editor pane; doubles as the 1px divider. Pointer-capture drag, double-click or `Home` resets, arrow keys nudge 16px. Width lives in the `useSidebarWidth` store (module-level + `localStorage`, clamped 200-560, default 320) so all three mounted FileManager tabs resize together |
| `OverwritePluginsModal` | `pluginRepositories/OverwritePluginsModal.jsx` | Per-file overwrite prompt (checkbox + Diff per file); `files: [{filename, runtime}]`, `onConfirm(filenames)` |
| `PluginDiffModal` | `pluginRepositories/PluginDiffModal.jsx` | 95vw×95vh read-only `@codemirror/merge` two-pane diff; z-[80] so it stacks above other modals |
| `PluginManifestEditorModal` | `pluginRepositories/PluginManifestEditorModal.jsx` | max-w-5xl × 85vh two-pane `qlsm-plugins.json` authoring modal (list ⟷ selected plugin). Owns the draft; the panes are `PluginManifestPluginList` (@dnd-kit reorder + Sort A–Z), `PluginManifestCvarRows`, `PluginManifestCommandRows` and `PluginManifestIssues`. Local only — nothing is saved back to the repository row |
| `PluginManifestIssues` | `pluginRepositories/PluginManifestIssues.jsx` | Scrolling validator-message list under an editor pane; errors first, a message carrying an `index` is a button that selects that row |

Feature-scoped directories (`components/hosts`, `instances`, `presetManager`,
`fileManager`, `addInstance`, `users`, `rcon`) contain additional modals and
dropdowns that follow the same patterns below but are page-specific, not
generic/shared — check there first before assuming a new component is needed.

## Headless UI patterns

All from `@headlessui/react`, generally paired with `@floating-ui/react-dom`
for positioning and `lucide-react` for icons. Use the matching primitive
rather than hand-rolling behavior:

| Need | Primitive | Reference file |
|---|---|---|
| Modal / confirmation dialog | `Dialog` + `DialogBackdrop`, styled with `.modal-backdrop`/`.modal-panel` | `ConfirmationModal.jsx` |
| Custom select / dropdown | `Listbox` + `Portal` + `useFloating` | `components/common/FloatingListbox.jsx` |
| Autocomplete / searchable select | `Combobox` + `Portal` + `Transition` | `PresetNameCombobox.jsx` |
| Action dropdown menu | `Menu` + `Portal` + `useFloating` | `HostActionsMenu.jsx`, `InstanceActionsMenu.jsx` |
| Enter/exit animation | `Transition` with `data-[enter]`/`data-[closed]` Tailwind state selectors | any of the above |

Positioning consistently uses floating-ui's `useFloating` with
`offset`/`flip`/`shift`/`autoUpdate` — reuse that combination for new
dropdowns/tooltips instead of manual absolute positioning.

## States & accessibility

- Validation states: `.input-error` / `.input-caution` (see `index.css:409-431`)
- Interactive states: every `.btn-*` variant defines `:hover`, `:focus-visible`,
  and `:disabled` — new buttons should reuse these classes to inherit them
  rather than redefining state styles.
- No formal accessibility audit or contrast-ratio documentation exists yet —
  treat this as a gap; when adding new color combinations, check contrast
  manually against both theme token tables above.

## File size note

There is no hard line cap (see `File Size Guideline` in
`development_guidelines.md`). `frontend-react/src/index.css` (4,300+ lines) is
the single global stylesheet. Put styles for new components in their own files
rather than growing it further.
