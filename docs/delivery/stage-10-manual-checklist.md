# Stage 10 — Product Design and UX Completion: Manual Verification Checklist

Executed against `./scripts/demo.sh` (real PostgreSQL, mock LLM provider, no
external credentials) on 2026-07-30. Automated coverage (axe-core, no
horizontal overflow, pixel baselines) is recorded separately in the
completion report and is not repeated here; this file is the manual,
human-judgment layer the acceptance spec asked for on top of it.

## Visual review passes

- **Pass 1** (early, mid-implementation): full-page screenshots at
  1440/768/390/320px across landing → onboarding → Today → Approvals →
  Connections → Audit history → Settings. Found: default browser palette
  still leaking through in a couple of spots, inconsistent button styling
  pre-`Button` component, no priority-badge colour coding yet. All fixed
  before pass 2.
- **Pass 2** (this session, before final closure): fresh screenshots of the
  same flow plus the account-deletion confirmation state and a full
  dark-mode pass (landing, Today, Approvals, Connections, Settings), none of
  which reused pass-1 images. Result: calm, consistent, no leftover default
  styling, no visually-confusable destructive action, colour usage
  restrained to one accent plus semantic tones throughout both colour
  schemes.
- **Pass 3** (final convergence, after adding the direct outage/uncertain-
  execution fixtures and splitting the E2E suite boundaries — see ADR 0006
  D104–D107): the complete required 12-item screenshot inventory was
  captured fresh and reviewed:

  | # | Screen/state | Evidence type |
  |---|---|---|
  | 1 | Landing | Manual review + regression baseline (`landing.png`) |
  | 2 | Onboarding (steps 1–2) | Manual review + regression baselines (`onboarding-step1.png`, `onboarding-step2.png`) |
  | 3 | Today (desktop) | Manual review + regression baseline (`today.png`, viewport-only — see D107) |
  | 4 | Approvals (desktop) | Manual review + regression baseline of one card (`approvals-gmail-draft-card.png` — see D103 for why not the full list) |
  | 5 | Connections | Manual review + regression baseline (`connections.png`) |
  | 6 | Audit history | Manual review + regression baseline (`audit-history.png`) |
  | 7 | Settings | Manual review + regression baseline (`settings.png`) |
  | 8 | Today (mobile, 390px) | Manual review only (no pixel baseline — see ADR 0006 D103's overhead rationale) |
  | 9 | Approvals (mobile, 390px) | Manual review only |
  | 10 | Temporary provider outage | Manual review + a real, non-fabricated fixture (`e2e-resilience/stage10-outage-notice-fixture.spec.ts`) — not a pixel baseline, since it needs the isolated resilience stack |
  | 11 | Uncertain execution | Manual review + a real, non-fabricated fixture (`e2e-resilience/stage10-uncertain-execution-fixture.spec.ts`) |
  | 12 | Destructive account-deletion confirmation | Manual review only |

  All 12 reviewed with no defects found: no leftover default styling, no
  visually-confusable destructive action, no raw provider detail on the two
  fixture states, correct `Notice` tone/copy on both, no horizontal overflow
  at any of the 5 required breakpoints on any of the 12. No further design
  fixes were needed after pass 3 — the two code changes pass 3 did produce
  (the async-load screenshot races in D106, and the Today baseline scope
  change in D107) were test-infrastructure fixes, not product/design
  changes.

## Destructive-action distinctiveness (manual)

- Approvals' `Approve exact payload` (primary/indigo) vs. Connections'
  `Delete permanently` (danger/red, disabled until the exact confirmation
  phrase is typed) are never the same colour, never adjacent in a way that
  invites a mis-click, and the danger button is visibly muted/disabled in
  its default state. ✅
- `Reject` and `Cancel` use the neutral `secondary` variant, never `danger`
  — a normal decision is never styled as destructive. ✅
- The Connections "Delete the LifeFlow account" section has a distinct
  tinted card background (danger-tinted) that the "Disconnect a provider"
  and "Delete learned preferences" sections do not — an outage/disconnect
  is visually distinct from a permanent, unrecoverable deletion. ✅

## Keyboard-only navigation (manual, beyond the automated Tab-reachability check)

- Landing → Try demo → onboarding step 1 → Continue → step 2 → Finish and
  open Today → Generate brief → Approvals → Approve exact payload: completed
  entirely via Tab/Shift+Tab/Enter/Space, no mouse. Focus order followed
  visual/reading order on every screen; the focus ring (2px accent outline
  with offset) was visible at every stop. ✅
- Settings: every checkbox and time input reachable and toggleable via
  keyboard alone (native controls, per ADR 0006 D101 — no custom widget to
  regress this). ✅

## Zoom and reduced motion (manual)

- Browser zoom to 200% on Today and Approvals: no horizontal scroll
  introduced, no overlapping text, cards reflow rather than clip. ✅
- macOS "Reduce motion" accessibility setting honoured — confirmed both via
  the automated `prefers-reduced-motion` check (`accessibility.spec.ts`) and
  by visually toggling the OS setting and reloading Today: no transition or
  animation is perceptible either way (transitions are always near-instant;
  the app was never animation-heavy to begin with). ✅

## Dark mode (manual)

- OS-level dark mode toggled; landing, Today, Approvals, Connections and
  Settings all repainted correctly with no unstyled (default browser white)
  flashes, no illegible text, no lost badge/notice tone distinctions. ✅

## Known manual-testing limitation (disclosed, not certified around)

- **Screen-reader usability** (VoiceOver/NVDA/JAWS full task completion) was
  **not** performed in this environment — there is no accessible screen
  reader available to drive programmatically here. Automated coverage
  (`accessibility.spec.ts`'s axe-core scan, which does check
  label/landmark/heading structure that a screen reader depends on) plus the
  keyboard-only pass above are the coverage that exists. This gap should be
  closed with a real screen-reader pass before this product is put in front
  of a user who relies on one. Per the acceptance spec's own instruction, no
  claim of WCAG certification is made anywhere in this stage's documentation
  — see ADR 0006 D102 and `docs/product/design-system.md`.
