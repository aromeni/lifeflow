# ADR 0006 — Stage 10: product design system and UX completion

**Status:** implemented on `stage-10-product-design`, branched from the merged/tagged Stage 9 boundary (`main` @ `e347b75e27399eb353a6d57aa87fe4c2282a803a`, tag `stage-9-complete`). Not yet merged to `main`.

**Context:** by the end of Stage 9 the product was functionally complete
end-to-end (Gmail/Calendar evidence → brief → proposal → approval →
execution → audit) but visually was unstyled Next.js boilerplate: default
system colours, no shared component vocabulary, ad hoc Tailwind colour
literals scattered per page, and no consistent navigation shell. A working
prototype was being asked to double as something a pilot user or reviewer
would trust on sight. Stage 10's brief was a visual/interaction-design pass
that could not touch any safety-relevant behaviour: draft-only Gmail,
insert-only Calendar, exact-payload approval, deletion confirmation,
evidence/confidence explanations, and rate-limit/outage messaging all had to
survive unchanged underneath the new surface.

## D96 — Token-based design system, not a component library dependency

All colour, spacing-adjacent, radius, shadow and typography decisions are
centralised as CSS custom properties in `apps/web/src/app/globals.css`, then
re-exported to Tailwind v4 utilities via `@theme inline` (e.g. `--color-danger-text`
becomes usable as `text-danger-text`). No third-party component library
(e.g. shadcn, MUI) was introduced — the acceptance spec asked for a system
that doesn't read as "a generic component-library demo," and the app's
actual component surface (badges, notices, buttons, a nav shell, a handful
of form primitives) is small enough that hand-rolling it on top of Tailwind
keeps every visual decision inspectable in one file rather than inherited
from an external dependency's defaults.

Palette: a cool-neutral surface scale (not pure grey), a three-step text
hierarchy (`text-primary`/`text-secondary`/`text-tertiary`, each verified
≥4.5:1 against both `bg` and `surface`), one restrained brand accent
(`#4338ca` indigo light / `#8b7ff5` dark) used only for the single primary
action per view and for focus rings, and four semantic tone families
(`success`/`warning`/`danger`/`info`), each with `bg`/`border`/`text`/`icon`
sub-tokens. Both a light and a dark palette are defined
(`@media (prefers-color-scheme: dark)`); the app has no manual theme toggle,
so this follows the OS preference only.

## D97 — Priority and risk reuse the semantic tone scale; no separate palette

`PriorityBadge` (Today) and `RiskBadge` (Approvals) both map their three
bands (high/medium/low) onto the existing danger/warning/info tones rather
than a dedicated "priority" palette. Both answer the same underlying
question — "how much attention does this deserve" — and every badge keeps
its text label regardless (e.g. "HIGH PRIORITY", "Risk: medium"), so colour
is reinforcement, never the only signal (WCAG 1.4.1). This was a deliberate
reduction, not an oversight: an earlier draft of `globals.css` had separate
`--color-priority-*` tokens, removed once it was clear they'd always be
value-identical to the semantic tones.

## D98 — Shared primitives over per-page markup

Five components in `apps/web/src/components/ui/` carry every visual
decision that used to be repeated per page:

- **`Badge`** — closed `BadgeTone` vocabulary (`neutral`/`info`/`success`/`warning`/`danger`), a small non-colour-dependent dot cue, `PriorityBadge` and `RiskBadge` built on top.
- **`Notice`** — the one shared way to surface a non-default state (outage, degraded dependency, uncertain outcome, rate limiting, validation problem). Callers pass `role="status"` or `role="alert"` explicitly; the component never guesses, because that distinction is safety-relevant (see D100).
- **`Button`** — three variants only: `primary` (the one accent-filled action per view — approve/execute/save, never reject/cancel), `secondary`, and `danger` (reserved for genuinely irreversible actions, never a normal decision like reject or disconnect).
- **`AppShell`** / `PageHeader` — the persistent top navigation and per-page header, described in D99.
- **`Form`** — `Field`, `TextInput`, `TimeInput`, `Checkbox` (native `<input>` + `accent-color`, not a custom widget — see D101), `FormSection`.

## D99 — Persistent top nav, not a permanent sidebar

The app has exactly four top-level authenticated destinations (Today,
Approvals, Connections, Audit history) plus Settings. A permanent sidebar
would cost real content width on Today's already-long priority list for no
navigational benefit at this scale, and the spec explicitly warned against
an "admin console" feel, which a wide fixed sidebar tends to produce. `AppShell`
is a slim sticky top bar wrapped per-page (not the Next.js root layout), so
the landing and onboarding screens — each a focused, single-purpose flow —
never show it.

## D100 — `aria-live="polite"` regions stay persistently mounted; `role="alert"` may mount fresh

Status text that changes over a page's lifetime (brief generation progress,
deletion operation status, approval status) is rendered into one span that
is always present in the DOM, with only its text/class varying — screen
readers reliably announce a *content change* inside an existing live region,
but do not reliably announce a live region that is inserted alongside its
first content. `role="alert"` carries an implicit `aria-live="assertive"`
and is reliably announced even when freshly mounted, so genuinely new error
conditions (e.g. `ActionProposalPanel`'s final execution error) are
conditionally rendered rather than always-mounted-but-empty. This is a
deliberate distinction, not an inconsistency — applying "always mount"
uniformly would mean rendering empty alert boxes on every screen.

## D101 — Native controls stay native

Checkboxes and time inputs use the platform `<input>` element styled via the
`accent-color` CSS property (for checkboxes) rather than custom-built
widgets. This keeps keyboard behaviour, screen-reader announcement, and
platform conventions (e.g. the native time picker) intact for free, per the
acceptance spec's explicit instruction not to replace accessible native
controls with brittle custom widgets.

## D102 — Automated accessibility coverage is a floor, not a certification

`apps/web/e2e-design/accessibility.spec.ts` runs `@axe-core/playwright`'s
`AxeBuilder` (tags `wcag2a`/`wcag2aa`/`wcag21a`/`wcag21aa`) against all seven
principal screens plus a keyboard-reachability check and a
`prefers-reduced-motion` check, filtered to `serious`/`critical` impact
violations. This is the repository's chosen lightweight approach: no new CI
infrastructure, no bespoke rule engine. It is explicitly documented (in the
spec file itself and here) as catching a meaningful subset of failures
(missing labels, contrast, landmark/heading structure, focus-visible
regressions) while **not** verifying genuine screen-reader usability, true
keyboard-only task completion, or zoom behaviour — those remain manual
checks, recorded in `docs/delivery/reports/stage-10.md`.

## D103 — A small, masked set of pixel baselines; not a screenshot per state

`apps/web/e2e-design/visual-regression.spec.ts` snapshots eight of the
highest-value screens/states at one viewport (1440×900), not every
permutation of every screen — the acceptance spec explicitly warned against
"excessive pixel-snapshot overhead." Server-rendered timestamps are masked
via their own `data-testid` (added specifically for this: `brief-item-due`,
`proposal-expires`) or the semantic `<time>` element, rather than masking
whole sections, so the pixel diff still covers the actual design (badges,
buttons, layout, colour). The full Approvals list is deliberately **not**
screenshotted: demo proposals are seeded in one batch and can tie on
`created_at`, so `ActionProposal` repository ordering (`created_at desc, id`
— a fair and stable order for real usage, where proposals arrive at
different times) is not guaranteed run-to-run for same-instant seed data. A
single, deterministically-selected card (`proposal-create_gmail_draft`) is
screenshotted instead, which still exercises every element that matters:
risk/status badges, notices, and the Approve/Edit/Reject button hierarchy.
The Today baseline is viewport-only, not full-page (D107 explains why).
Responsive/no-overflow coverage (`apps/web/e2e-design/responsive.spec.ts`)
is a separate, cheaper suite: it asserts zero horizontal overflow at
1440/1024/768/390/320px across all principal screens plus the
account-deletion confirmation state, without pixel comparison.

## D104 — Superseded: degraded-provider and uncertain-execution now have direct fixtures

*Original decision (Stage 10 first pass):* two states named in the
acceptance spec — a retryable Google sync failure and an uncertain
execution outcome — were not given their own responsive or pixel-baseline
fixture, on the reasoning that both render through the same shared `Notice`
component already exercised elsewhere, and both require the dedicated
dependency-outage infrastructure.

**This was judged insufficient at final closure review.** Proxy coverage
through another screen's `Notice` instance proves the component renders
correctly somewhere; it does not prove *this specific state* — reached via
the real backend classification path — renders the right message, the
right tone, no raw provider detail, and no unsafe retry control. Two new
specs were added to the existing Stage 9 resilience infrastructure instead
of building a new one: `apps/web/e2e-resilience/stage10-outage-notice-fixture.spec.ts`
sets the fake Google server's `gmail_list_messages` scenario to
`transient_then_recover` with `fail_count=5` (exceeding `retry_read`'s
3-attempt budget), which reaches the real `GoogleTransientError` →
`sync-degraded-notice` path with the real backend safe-message copy
("Google was temporarily unavailable."). `stage10-uncertain-execution-fixture.spec.ts`
reuses Journey B's exact `hang_on_write` mechanism to reach a real
`execution-uncertain-warning`. Both assert the correct `Notice` tone/role,
absence of raw provider detail (fake tokens, stack traces, HTTP codes), and
zero horizontal overflow at all five required breakpoints, and both capture
a screenshot. Neither introduces a new test-only bypass — both run through
the same `scripts/e2e-resilience.sh` stack Journeys A–D already use.

## D105 — Three independent E2E discovery boundaries, not one inflated suite

The first Stage 10 pass placed `accessibility.spec.ts`, `responsive.spec.ts`,
and `visual-regression.spec.ts` inside the original `apps/web/e2e/`
directory — the same boundary as the 10 pre-existing functional journeys.
This silently changed what "the original suite" meant: a reported "37
passed" conflated 10 functional journeys with 26 unrelated design-verification
tests, and nothing would have caught a future edit quietly growing one
count at the expense of the other's traceability. Final closure review
split this into three independent, separately-scripted boundaries:
`apps/web/e2e` (original 10 journeys, `scripts/e2e.sh`, unchanged),
`apps/web/e2e-resilience` (4 outage journeys plus the two D104 fixtures,
`scripts/e2e-resilience.sh`), and the new `apps/web/e2e-design` (26
design/accessibility/responsive/visual-regression tests,
`scripts/e2e-design.sh`, `playwright.design.config.ts`). `e2e-design` needs
neither the ARQ worker nor `GOOGLE_OAUTH_ENABLED` — it runs against the same
plain demo stack `e2e` uses (port 8010/3000) — so the two must not run
concurrently (both would start/reuse the same dev-server pair), exactly the
existing constraint between `e2e` and `e2e-resilience`. `scripts/check_ci_e2e_coverage.py`
and the CI workflow were both extended to require all three as real `run:`
steps, the same guard pattern Stage 9 used to prevent the resilience suite
from silently disappearing from CI again.

## D106 — Two intermittent screenshot races found and fixed, not tolerated

Stress-running the design suite repeatedly (5+ consecutive runs) surfaced
two genuine, intermittent — not merely flaky — pixel-baseline failures,
both fixed at the root cause rather than papered over with a wider
tolerance: (1) the landing page's Google sign-in button depends on an async
`GET /config` call that fails closed by default (ADR 0003 D23); screenshotting
before it resolved sometimes captured the fail-closed default and sometimes
the settled state, changing the CTA row's layout — fixed by awaiting the
`/config` response before capturing. (2) The Connections page's privacy
summary loads asynchronously behind a "Loading your privacy summary…"
transient state; screenshotting before it resolved sometimes captured a
near-empty page — fixed by waiting for that text to disappear and the
inventory section to be visible first. Neither was a design defect; both
were test-timing bugs that would have made the baseline unreliable in CI.
Separately, a third, permanent (not intermittent) noise source was found
and masked: Next.js's own dev-mode overlay button, present on every page
under `pnpm dev`, whose badge state isn't fully deterministic — now masked
on every baseline via a shared `devtoolsMask()` helper.

## D107 — Today's pixel baseline is viewport-only, not full-page

The original full-page Today baseline was ~5500px tall, produced a 719KB
PNG — over the repository's 500KB `check-added-large-files` pre-commit
limit — and was also the one baseline sensitive to real wall-clock time
passing during a long local session (a same-day meeting starting moves it
out of the "Today and upcoming" section, changing the page's total height
by more than a pixel-ratio tolerance could reasonably absorb). Capturing
only the viewport (header, summary strip, and the top of "Needs attention")
resolves both problems at once and still exercises the elements that matter
for a design regression: priority badges, the summary strip, and card
layout/tokens.

## D108 — Investigation note: demo mode's synthetic connected account is not a leak

While fixing D106's Connections race, the diff briefly showed a fresh
demo user's Connections page reporting "Connected accounts: 1" and
"Imported emails & events: 36" under a "Not connected" heading — shaped
like a cross-user data leak. Verified via a direct, unmediated
`GET /privacy/summary` call (bypassing the browser and the UI entirely) for
a brand-new dev-login user before and after calling `POST /demo/start`:
before, every count is genuinely zero; after, `POST /demo/start` itself
creates a real `ConnectedAccount` row with `provider="synthetic"` to
represent the fictional demo dataset, correctly scoped to that one user.
The "Connected accounts" card at the top of the page filters to
`provider="google"` specifically, so it correctly reads "Not connected" for
a demo user with no real Google account, while the inventory panel
correctly counts the synthetic account's data below it. Both are correct
and consistent; nothing is leaked between users. The test was renamed from
"Connections (not connected)" to "Connections (no real Google connected)"
to stop implying an empty-inventory state that demo mode never actually
has.
