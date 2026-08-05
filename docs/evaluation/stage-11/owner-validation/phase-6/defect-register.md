# Stage 11A Phase 6 — Defect Register

Two genuine defects were found during this phase's live real-account write validation; one process near-miss was caught and contained before any data exposure.

## D-6-01 — Gmail draft-verification false negative on threaded replies

- **Found during:** the first real Gmail draft write attempt (P6-GM-TEST-01), against a real Gmail account.
- **Root cause:** `GoogleGmailDraftExecutor.execute()` re-fetches the created draft and compares its subject byte-for-byte against the approved payload. Creating a draft with a `thread_id` can make Gmail canonicalise the stored subject to the thread's own subject line, silently dropping the "Re: " prefix the app adds. The code already exempted `thread_id` itself from comparison for exactly this reason (a documented, deliberate design decision) but had never been extended to the coupled subject field, since no prior test or live run had exercised this specific real Gmail behaviour.
- **Impact:** a Gmail draft that was, in fact, created correctly (right recipient, right body, in the right thread) was classified `uncertain` rather than `succeeded`, purely due to the missing "Re: " prefix.
- **Severity:** non-blocking, but real — this would misclassify a class of genuinely correct writes as uncertain indefinitely (uncertain outcomes are never auto-retried by design), understating real success and needlessly leaving a dead-ended execution record.
- **Disposition: FIXED.** `_subject_matches()` (`action_executors.py`) tolerates exactly one narrow difference — a missing reply prefix on an actual threaded reply — and nothing else; any other subject difference, or a missing prefix on a non-threaded draft, still counts as a genuine mismatch. 3 new tests (26 total in `test_google_executors.py`). Merged via PR #17 (`0eb94c4`), verified working end-to-end on a second, real, fresh trigger message (`succeeded`, not `uncertain`).
- **The original uncertain execution record was never touched or retried** — it remains a permanent, immutable record, exactly as this project's core safety design requires.

## D-6-02 — Enabling connector-consent initiation also re-arms OIDC sign-in

- **Found during:** post-disconnect residue verification (`preconnection_readiness_check.py` unexpectedly reported `google_identity_bindings=1`).
- **Root cause:** `GOOGLE_OAUTH_INITIATION_ENABLED` is a single flag shared by both the connector-consent flow and the Google OIDC sign-in flow (a deliberate Phase 4C design decision, not a bug in itself). Because real days passed between Phase 5 and Phase 6, the owner's prior LifeFlow session had expired; when reconnecting, they used "Sign in with Google" (OIDC) rather than "Try demo" to get back into a LifeFlow session, authenticating with Account A. This created a new LifeFlow user bound to a real Google identity (`google_subject`) — the OIDC sign-in flow this and every prior phase's boundary explicitly prohibited — as a side effect of the flag being armed for an unrelated, authorised purpose.
- **Impact:** contained. Confirmed directly with the owner that Account A (an already-disposable, fictional test identity) was used, not a real personal or institutional account — this is a genuine process/scope-boundary crossing, not a real-content exposure incident under `real-provider-data-boundary.md`.
- **Severity:** non-blocking, contained, but real. Recorded honestly rather than omitted.
- **Disposition: RESIDUE CLEANED, not code-fixed this phase.** The stray `google_subject` binding was cleared via a targeted, single-column database update (`UPDATE users SET google_subject = NULL WHERE id = ...`) — not the full account-deletion flow, which would have also erased the content-free execution/audit history Phase 6 deliberately preserved. `preconnection_readiness_check.py` re-run clean afterward (16/16 PASS).
- **Recommendation for a future phase (not implemented here):** split `GOOGLE_OAUTH_INITIATION_ENABLED` into two independent flags (e.g. `GOOGLE_OIDC_INITIATION_ENABLED` / `GOOGLE_CONNECTOR_INITIATION_ENABLED`) so arming one flow for a narrow, authorised purpose can never inadvertently arm the other. This is a real architectural change to a Phase 4C design decision, not a bug fix, and is deliberately left for the owner's explicit future authorisation rather than made unilaterally in this phase.

## Process near-miss — real Outlook email sent into Account A (no exposure)

- **Found during:** checkpoint 1, reported proactively by the owner before any sync.
- **What happened:** the owner sent a test message from a real university Outlook account into Account A's inbox, alongside a legitimate Account-B trigger message.
- **Immediate action:** flagged as falling under `real-provider-data-boundary.md`'s standing prohibition on personal correspondence; the owner deleted it from Account A's inbox before any sync occurred.
- **Impact: none.** Confirmed independently — no sync had run between the message being sent and being deleted, so it was never imported into LifeFlow's database. No LifeFlow-side cleanup was required.
- **Disposition:** recorded for completeness per this project's standing practice of logging every boundary-adjacent event, even ones caught before any real consequence.
