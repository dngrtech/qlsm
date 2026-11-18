# Styling an addon UI

An addon can look like it belongs in QLSM - matching colors, surfaces and
shadows in both light and dark theme - **without Tailwind and without a
build step**. QLSM's `index.css` defines a set of CSS custom properties
(`var(--...)`) on `:root` (light theme) and `.dark` (dark theme). These are
already global: any element on the page, including your addon's markup, can
read them. Just write a plain `.css` file next to your component and
reference the variables - no compiler, no PostCSS, no Tailwind config.

```css
/* ui/Panel.css - a plain, hand-written stylesheet, no build step */
.my-addon-panel {
  background: var(--surface-raised);
  border: 1px solid var(--surface-border);
  color: var(--text-primary);
  border-radius: 8px;
  padding: 16px;
  box-shadow: var(--shadow-card);
}

.my-addon-panel .title {
  color: var(--accent-primary);
}
```

QLSM auto-loads `Panel.css` when it loads `Panel.js` for a tier-2 component
(same base filename, next to it in `ui/`) - see `README.md` in this
directory for the loading contract and `_examples/css-test-addon` for a
minimal working proof. The stylesheet is imported into the `qlsm-addons`
cascade layer, which ranks below every QLSM style: it styles your own markup
but cannot override the panel's, so page-wide rules (such as a bundled
Tailwind build) can't break QLSM layouts. Scope your selectors to your
component's root class anyway.

Because the variables already flip between light and dark theme at the
`:root` / `.dark` level, your addon gets both themes for free - you never
need to write your own `.dark .my-addon-panel { ... }` override for these
values.

## Stability contract

The variables listed below are a **stable contract**: QLSM will not rename,
remove, or repurpose them without a version bump and a migration note in the
changelog. Anything in `index.css` that is *not* in this list (e.g.
`--footer-height`, a core layout constant) is internal to QLSM's own UI and
may change without notice - do not depend on it from addon code.

### Accent colors

| Variable | Purpose |
|---|---|
| `--accent-primary` | Primary brand/action accent - main call-to-action color, active states |
| `--accent-primary-dim` | Muted/hover variant of the primary accent |
| `--accent-danger` | Destructive actions, errors |
| `--accent-danger-dim` | Muted/hover variant of danger |
| `--accent-warning` | Warnings, caution states |
| `--accent-info` | Informational highlights, links |

```css
.my-addon-button { background: var(--accent-primary); }
.my-addon-button:hover { background: var(--accent-primary-dim); }
.my-addon-error { color: var(--accent-danger); }
```

### Surfaces

| Variable | Purpose |
|---|---|
| `--surface-base` | Page background |
| `--surface-raised` | Cards, panels sitting above the page background |
| `--surface-overlay` | Modals, dropdowns, popovers |
| `--surface-elevated` | Elements raised above raised surfaces (e.g. nested cards) |
| `--surface-border` | Default border color for surfaces |
| `--surface-border-strong` | Emphasized border, e.g. on focus or selection |

```css
.my-addon-card {
  background: var(--surface-raised);
  border: 1px solid var(--surface-border);
}
```

### Text

| Variable | Purpose |
|---|---|
| `--text-primary` | Primary body/heading text |
| `--text-secondary` | Secondary text, labels |
| `--text-muted` | De-emphasized text, placeholders, hints |

```css
.my-addon-panel h3 { color: var(--text-primary); }
.my-addon-panel .hint { color: var(--text-muted); }
```

### Shadows

| Variable | Purpose |
|---|---|
| `--shadow-card` | Default resting shadow for a raised surface |
| `--shadow-card-hover` | Shadow on hover for an interactive card |
| `--shadow-elevated` | Shadow for overlays/modals |

```css
.my-addon-card { box-shadow: var(--shadow-card); }
.my-addon-card:hover { box-shadow: var(--shadow-card-hover); }
```

## What addons should not do

- Don't hardcode hex colors for anything that should track the active theme
  (backgrounds, borders, text, shadows) - use the variables above instead,
  so your addon stays legible when the operator switches theme.
- Don't read or depend on any `index.css` custom property not listed in this
  guide. Those are free to change between QLSM releases.
- Don't assume Tailwind utility classes are available - QLSM's Tailwind
  build is not exposed to addon code. Plain CSS only.
