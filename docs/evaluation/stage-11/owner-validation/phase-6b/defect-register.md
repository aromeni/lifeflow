# Stage 11A Phase 6B — Defect Register

**Date:** 2026-08-05

No P0 or P1 found. Three P3 process/environmental findings, none affecting payload correctness, account binding, duplication, or final residue — all resolved within the phase.

## D-6B-01 (P3, process) — Owner checkpoint confirmations arrived retroactively

Sequencing intent: the owner would report `CONSENT SCREEN VERIFIED — ACCOUNT A — APPROVED FOUR-SCOPE SET` *before* proceeding past the OAuth consent step. In practice, the owner completed the consent screen, callback, and an initial sync in the live browser before this was requested back, without an intervening report. Closed by independently verifying, directly against the database, everything the checkpoint exists to catch — exactly one real credentialed account, the exact four scopes, single-account binding, zero OIDC identity bindings — *before* asking the owner for retroactive confirmation, rather than trusting the state uncritically. The owner then explicitly confirmed. No incorrect scope, wrong account, or unexpected state was found.

## D-6B-02 (P3, environmental, not a product defect) — Session invalidated by an API restart

Restarting the local API process to apply a configuration-flag change logged the owner out, because the local `.env` had no fixed `SESSION_SECRET` — documented, intentional development-only behaviour (a fresh ephemeral signing key per process start). Closed by setting a local-only `SESSION_SECRET` for the remainder of the session; no application code changed, no committed file changed (`.env` is gitignored).

## D-6B-03 (P3, process) — Disconnecting before deleting imported data hid the deletion control

The cleanup sequence disconnected Account A before deleting its imported data, and the Connections page's "Delete imported provider data" control is gated on the account still showing as *connected* — so after disconnecting, no UI control existed to run the deletion. The underlying backend route/service imposes no such requirement (only account ownership), so the deletion was carried out by calling the same API path directly, produced the exact same preview counts, typed-confirmation gate, and audited outcome the UI flow would have. A future phase could reorder its own instructions to delete imported data before disconnecting, or the product could relax the frontend gate to allow deletion for a disconnected-but-still-owned account; neither was in scope to change here.

## Unrelated environmental noise, not a defect

An earlier, unrelated task had used a Linux Docker container bind-mounting this repository, which left path references inside the frontend's local Turbopack dev cache pointing at the container's internal filesystem layout. Reusing that cache from the host caused repeated dev-server errors during this phase's live browser session. Not a product defect — cleared by deleting the local cache directories (`apps/web/.next-dev`, `apps/web/.next`), which are already gitignored and rebuild automatically.
