# Stage 11 — Issue Register Template

**Status:** Planning document · **Date:** 2026-07-30

Companion: [stage-11-plan.md](../../delivery/stage-11-plan.md) §7 · [findings-template.md](findings-template.md)

## Severity definitions

### P0 — Safety or privacy blocker

Examples: user believes LifeFlow sends emails automatically; user believes it can edit or delete existing Calendar events; unsafe uncertain-outcome retry behaviour; cross-user data exposure; destructive-deletion misunderstanding.

**Required response:** evaluation pauses; root cause fixed; regression coverage added; affected journeys re-evaluated. No unresolved P0 is permitted at Stage 11 exit.

### P1 — Core task blocker

Examples: onboarding cannot be completed; user cannot interpret Today; user cannot approve or reject correctly; Audit History cannot be understood.

**Required response:** fix before Stage 11 closure; repeat affected tasks. No unresolved P1 is permitted at Stage 11 exit.

### P2 — Material confusion or friction

Examples: excessive assistance required; unclear labels; difficulty finding evidence; inconsistent navigation.

**Required response:** prioritised remediation; any accepted remainder must be explicitly justified in the findings report.

### P3 — Minor issue

Examples: cosmetic preference; non-blocking wording refinement; minor spacing concern.

**Required response:** document and schedule where worthwhile; no blocking effect on Stage 11 exit.

## Register

| ID | Round | Participant ID | Task | Severity | Description | Root cause (once known) | Fix status | Regression coverage added | Re-evaluated? |
|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | |

## Rules

- Every row's Severity must be one of P0/P1/P2/P3 — no ad hoc labels.
- A P0 or P1 row cannot be marked "Fix status: closed" without a linked regression test and a re-evaluation record.
- This register is the single source counted in the "unresolved P0/P1" check at Stage 11 exit (see [go-no-go-template.md](go-no-go-template.md)).
