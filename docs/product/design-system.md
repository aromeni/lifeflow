# LifeFlow design system (Stage 10)

Companion to [ADR 0006](../architecture/adr/0006-stage10-product-design-system.md), which records *why* each decision below was made. This document is the practical reference: what tokens exist, what each shared component does, and how to use them correctly in a new screen.

## Principles

1. **Calm, not clinical, not decorative.** One accent colour, used sparingly. No gradients, no illustration, no "AI" iconography (robots, sparkles, neural-net art).
2. **Colour is reinforcement, never the only signal.** Every badge and notice carries a text label. Priority and risk are always spelled out ("HIGH PRIORITY", "Risk: medium"), not just colour-coded.
3. **Never make a destructive action easy or attractive.** `Button variant="danger"` exists only for genuinely irreversible operations (permanent deletion) and is never the default/first button in a group.
4. **Approve and Execute are never visually confused.** They use the same `primary` button variant only because they're never the same button on screen at the same time in a way that could be mis-clicked; see `ActionProposalPanel` for the actual state machine that decides which one (if either) renders.
5. **Prefer native controls.** Style `<input>`/`<select>`/`<fieldset>` rather than building custom widgets.

## Tokens

All tokens live in `apps/web/src/app/globals.css` as CSS custom properties, then re-exported to Tailwind utilities via `@theme inline`. **Never hardcode a colour literal in a component** — add or reuse a token instead.

### Surfaces and text

| Token | Light | Dark | Use |
|---|---|---|---|
| `--color-bg` | `#f7f8fa` | `#10131a` | Page background |
| `--color-surface` | `#ffffff` | `#171b24` | Cards, panels |
| `--color-surface-raised` | `#ffffff` | `#1d222c` | Hover/raised state |
| `--color-border` | `#e2e5ea` | `#2b3140` | Default dividers/borders |
| `--color-border-strong` | `#838d9c` | `#606b80` | Input borders, secondary-button outlines — verified ≥3:1 (WCAG 1.4.11) |
| `--color-text-primary` | `#14181f` | `#edf0f5` | Headings, primary copy |
| `--color-text-secondary` | `#4c5563` | `#b6bccc` | Supporting copy |
| `--color-text-tertiary` | `#646c7b` | `#838ba0` | Metadata, timestamps — verified ≥4.5:1 |

### Accent

One restrained indigo, used for exactly one primary action per view and for focus rings — never a large decorative fill.

| Token | Light | Dark |
|---|---|---|
| `--color-accent` | `#4338ca` | `#8b7ff5` |
| `--color-accent-hover` | `#372da3` | `#a49af7` |
| `--color-accent-subtle` | `#eeecfd` | `#262247` |
| `--color-accent-subtle-text` | `#372da3` | `#c3bbfa` |

### Semantic tones

Four families — `success`, `warning`, `danger`, `info` — each with `bg`/`border`/`text`/`icon` sub-tokens (e.g. `--color-danger-bg`, `--color-danger-text`). `danger` additionally has `-solid`/`-solid-hover` variants for filled destructive buttons. Every text/background pairing is verified ≥4.5:1; every border pairing ≥3:1 (`scripts/check_design_token_contrast.py`).

**Priority (Today) and risk (Approvals) reuse these same tones** rather than a separate palette — see ADR 0006 D97. High → danger, medium → warning, low → info.

### Structure

- **Radii:** `--radius-sm` (0.375rem, inputs/focus), `--radius-md` (0.625rem, buttons), `--radius-lg` (0.875rem, cards), `--radius-full` (badges/pills).
- **Shadows:** `--shadow-xs`/`sm`/`md` — subtle depth only, never a decorative drop shadow.
- **Focus:** `--focus-ring-color`/`-width`/`-offset`, applied globally via a single `:focus-visible` rule. Never colour-only — always a 2px outline with offset, visible under Windows High Contrast Mode.
- **Motion:** a global `@media (prefers-reduced-motion: reduce)` rule forces near-zero animation/transition duration everywhere; no per-component opt-out needed.

## Shared components (`apps/web/src/components/ui/`)

### `Badge` / `PriorityBadge` / `RiskBadge`

```tsx
<Badge tone="warning">Needs review</Badge>
<PriorityBadge band={item.priority_band} />   // "high" | "medium" | "low" | anything else → neutral
<RiskBadge level={proposal.risk_level} />
```

`BadgeTone` is `neutral | info | success | warning | danger`. Unrecognised priority/risk values fail safe to `neutral` rather than throwing or silently dropping the badge.

### `Notice`

The one shared way to surface a non-default state: outages, degraded dependencies, uncertain execution outcomes, rate limiting, validation errors.

```tsx
<Notice tone="warning" role="status" title="Optional heading">
  Body text.
</Notice>
```

**You must choose `role` explicitly** — `Notice` never guesses:
- `role="status"` (→ `aria-live="polite"`) for a non-urgent update. Render the `Notice` (or its containing element) unconditionally, and vary only its content, so the live region is already mounted when the text changes — screen readers do not reliably announce a live region that appears at the same moment as its first content.
- `role="alert"` (→ `aria-live="assertive"`) for a genuinely new problem. Safe to mount conditionally (only when the error exists), since `role="alert"` is reliably announced even on first insertion.

### `Button`

```tsx
<Button variant="primary">Approve exact payload</Button>
<Button variant="secondary">Edit exact payload</Button>
<Button variant="danger">Delete permanently</Button>
```

- `primary` — the one accent-filled action per view (approve, execute, save, continue). Never used for reject/cancel.
- `secondary` — everything else by default (edit, reject, cancel, disconnect).
- `danger` — reserved for genuinely irreversible actions (permanent account/data deletion). Never used for a normal decision like reject.

### `AppShell` / `PageHeader`

Wrap every authenticated screen (not the landing page or onboarding, which have their own focused flow):

```tsx
<AppShell>
  <PageHeader title="Today" description={<span aria-live="polite">{statusText}</span>} actions={<Button ...>Generate brief</Button>} />
  {/* page content */}
</AppShell>
```

`AppShell` renders a skip-to-content link, the sticky top nav (Today/Approvals/Connections/Audit history + a separate Settings link), and a `<main id="main-content">` landmark. It's a slim top bar, not a permanent sidebar — see ADR 0006 D99 for why.

### `Form` primitives

`Field`, `TextInput`, `TimeInput`, `Checkbox`, `FormSection` — all thin wrappers around native elements, styled consistently. `Checkbox` uses the native `<input type="checkbox">` recoloured via `accent-color`, not a custom widget, so keyboard behaviour and screen-reader announcement stay exactly what the platform already provides for free.

```tsx
<FormSection legend="Time" description="..." testId="settings-time">
  <Field label="Timezone (IANA name)" htmlFor="tz">
    <TextInput id="tz" ... />
  </Field>
  <Checkbox label="..." description="..." checked={...} onChange={...} />
</FormSection>
```

## Adding a new screen or state

1. Reach for an existing token/component first. If you need a colour that isn't one of the tokens above, that's a sign the new state should map onto an existing semantic tone (success/warning/danger/info), not a new one-off value.
2. Wrap authenticated screens in `AppShell` + `PageHeader`.
3. Any status text that changes over the page's lifetime goes in a persistently-mounted element (see `Notice`'s `role="status"` guidance above) — check `apps/web/src/app/today/page.tsx`'s `briefStatusText` pattern for a worked example.
4. Run `scripts/check_design_token_contrast.py` if you add or change a token colour pairing, and record the result before merging.
5. Check the new screen against `apps/web/e2e-design/accessibility.spec.ts` (axe-core), `apps/web/e2e-design/responsive.spec.ts` (1440/1024/768/390/320px, zero horizontal overflow), and consider whether it's high-value enough to add to `apps/web/e2e-design/visual-regression.spec.ts`'s deliberately small baseline set (see ADR 0006 D103 before adding one — mask any server-rendered timestamp via its own `data-testid` rather than hiding a whole section). Run this suite via `./scripts/e2e-design.sh`, never concurrently with `./scripts/e2e.sh` (both share the same demo stack, ADR 0006 D105).
