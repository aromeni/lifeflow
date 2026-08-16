# Stage 11A Phase 7 — Decision

**Date:** 2026-08-16

## Summary

The 10-day (240-hour minimum) owner-only soak ran for 257.9 hours (10.75
days) from a recorded Google consent timestamp, with daily or near-daily
owner-triggered check-ins driving a single controlled read-only sync plus
resource/queue/database/Redis stability measurements and duplicate checks
each time. The soak observed the previously-undecided Google Testing-status
7-day refresh-token boundary directly — the token expired, was detected as
a single non-retried `409`, and Account A was reconnected under a
controlled, independently-verified procedure without resetting the soak
clock. Zero duplicate `SourceItem`/`Signal`/proposal rows and zero new
`ActionExecution`s occurred at any point (`GOOGLE_PROVIDER_WRITES_ENABLED`
stayed `false` throughout — no proposal was ever approved or executed).
Several genuine local-environment gaps (Docker/DB/Redis outages, most
likely host sleep or reboot) occurred and self-recovered cleanly every
time, with no flag drift and no data loss. Full teardown — imported-data
deletion, access revocation, disconnection, and flag restoration —
completed at soak end, independently re-verified against the database.

## Requirements met

- Soak duration ≥ 240 hours from the recorded consent timestamp — **met**
  (257.9 hours).
- One controlled, owner-triggered, read-only sync per day — **met**, every
  check-in.
- Resource/queue/database/Redis stability measurements each check-in —
  **met**.
- Duplicate `SourceItem`/`Signal`/proposal checks each check-in — **met**,
  zero every time.
- Observation of the Google Testing-status 7-day token boundary — **met**,
  directly observed and correctly handled (single non-retried `409`,
  truthful audit trail, no background retry possible by construction).
- Controlled reconnection and recovery after expiry — **met**,
  independently verified (`authorisation_revision` 3→4, same four scopes,
  no duplicate account row, Account B untouched, OIDC bindings still zero).
- Bounded authentication-failure and retry behaviour — **met**.
- Final data deletion, revocation, disconnection, zero-residue
  verification — **met for deletion/disconnection/residue**;
  **revocation itself came back uncertain, not confirmed** (see below).
- `GOOGLE_PROVIDER_WRITES_ENABLED` stayed `false` throughout — **met**.
- Account B remained disconnected throughout — **met**.
- No participant or Stage 12 activity — **met**.

## Open items (why this is a conditional pass, not an unqualified one)

1. **GM-12 stale-follow-up evaluation was not achieved.** Neither Gmail's
   history cursor nor Calendar's sync token ever expired into a full resync
   during the soak, so GM-12 — whose local copy this project's own Phase 6B
   cleanup had already deleted before this soak began — never became
   visible to a fresh import. Every way to force this (an out-of-band
   database write, or a full account deletion) would have been materially
   worse than leaving it undone, and the project owner did not ask for it
   to be forced when this was raised directly. **Recommended closure**: a
   small, separate, future check using a *fresh* trigger message aged
   naturally past 5 days — not a reason to repeat or extend this soak.
2. **Google-side access revocation is not objectively confirmed for this
   soak's teardown.** `revoke_token` returned `false` (non-200 or network
   failure, indistinguishable from the client side); the local disconnect
   proceeded regardless per the product's own by-design guarantee, and
   local credentials are verifiably, completely cleared either way.
   **Recommended closure**: the owner independently checks
   `myaccount.google.com/permissions` and revokes LifeFlow's access there
   directly if it is still listed.

Neither open item reflects a code defect, a duplicate, an unauthorised
write, or a residual credential — both are honestly-reported gaps in what
this specific run happened to observe or confirm, not correctness failures.

## Automated verification

Readiness command: **19/19 PASS**, `READY`, re-run after teardown. No
application code changed during this phase — only documentation/evidence
files were added (see the PR diff). `git diff --check` clean; evidence pack
scanned for prohibited content (account addresses, tokens, provider item
IDs, raw email/event content, absolute local paths) — clean.

## Decision

**CONDITIONAL PASS — 10-DAY SOAK COMPLETE, TWO NAMED OPEN ITEMS, NO
BLOCKING DEFECTS.**

This does not authorise GM-12's evaluation being retried in isolation
without a fresh trigger, participant recruitment, or Stage 12 — each
remains a separate, explicit owner decision.

**Next owner decision — one of:**

- `AUTHORISE RECONNECTION FOR GM-12'S DEFERRED READ-ONLY EVALUATION`
- `PROCEED TO STAGE 11A NEXT-PHASE PLANNING`
