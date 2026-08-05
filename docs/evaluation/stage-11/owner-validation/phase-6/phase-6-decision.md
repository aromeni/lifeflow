# Stage 11A Phase 6 — Decision

**Date:** 2026-08-05

## Summary

This phase performed LifeFlow's first-ever real ingestion of provider content through its normal product pipeline (sync → extraction → proposal → approval → execution) and validated Decision 2 (the first real provider write) using two dedicated, purpose-built trigger messages rather than the original, ambiguous GM-18/CAL-12 scenarios. The Gmail-draft write path was fully validated, including finding and fixing a genuine defect along the way. The Calendar-write path was honestly recorded as not validated this pass, per the plan's own explicit rule against forcing an unqualified proposal. A second, unrelated real finding (an OIDC sign-in boundary crossing, contained to the disposable test account) was caught, contained, and its residue cleaned, with an architectural recommendation deferred rather than unilaterally implemented.

## What passed

- Real sync imported 49 items (later 3 more) as genuine `SourceItem`s; extraction and proposal composition ran unmodified against real content for the first time.
- Gmail draft write validated end-to-end: real write → real independent re-verification → (after a found-and-fixed defect) a clean `succeeded` outcome, owner-verified directly in Gmail, then deleted.
- The "uncertain, never auto-retried" safety mechanism was proven against a genuine real-world edge case, not just a mock — the first attempt's uncertain outcome was correctly never retried or touched again.
- Exactly one Gmail write occurred per attempt (metric-verified); zero Calendar writes occurred; zero automatic retries.
- Full cleanup: imported data and signals deleted (content-free execution/audit history correctly preserved), Account A revoked and disconnected with a truthful, objectively-confirmed revocation result, all flags restored, full residual-data sweep at zero.

## What did not pass / was not validated

- **Calendar write: not validated this pass.** P6-CAL-TEST-01 did not produce a `create_calendar_event` proposal — the deterministic scheduling parser requires an unambiguous date/time/duration the trigger message evidently didn't provide. Per the plan's explicit rule, no proposal was approved to force completion. This requires a separately authorised, corrected trigger message in a future attempt.
- **A precise per-scenario extraction-accuracy comparison against Phase 4B's table could not be performed** — the original population wasn't tagged with scenario IDs. Aggregate, content-free evidence was recorded instead (`extraction-accuracy-results.md`).

## Defects found

- **D-6-01 (Gmail subject-verification false negative on threaded replies): FIXED.** Code + 3 new tests, merged (PR #17, `0eb94c4`), verified working end-to-end on a real second attempt.
- **D-6-02 (enabling connector-consent initiation also re-arms OIDC sign-in, leading to a real but contained sign-in with the disposable Account A): residue cleaned, architectural fix deferred.** No real/personal data was exposed — confirmed directly with the owner. A recommendation to split the shared initiation flag is recorded for future owner consideration, not implemented unilaterally in this phase.
- One process near-miss (a real Outlook email sent into Account A) was caught and removed before any sync — zero impact, recorded for completeness.

## Decision

**CONDITIONAL PASS.**

Following this project's own established governance precedent (the Phase 3 decision correction: an unqualified PASS requires every finding to be either absent or fully fixed), this is a conditional, not unqualified, PASS specifically because D-6-02's underlying architectural condition (the shared initiation flag) remains open by deliberate deferral, not because anything was left broken or unsafe — its immediate residue was fully cleaned and independently verified at zero. The Calendar non-validation is explicitly **not** a qualifying condition for this classification — the plan itself defines "not validated this pass" as an accepted, non-failing outcome, not a defect.

This decision does not authorise: a corrected Calendar-write retry, the soak period, recruitment, or Stage 12. It does confirm that LifeFlow's real provider-write pipeline — the single most safety-critical capability this entire testing programme exists to validate — works correctly against a real account, including correctly refusing to claim false success.

**Next owner decision — one of:**

- `AUTHORISE A CORRECTED CALENDAR-WRITE TRIGGER ATTEMPT` (a new, more concrete P6-CAL-TEST-02 message)
- `AUTHORISE THE SHARED-INITIATION-FLAG ARCHITECTURAL FIX` (split OIDC/connector initiation into independent flags, per D-6-02's recommendation)
- `AUTHORISE RECONNECTION FOR GM-12'S DEFERRED EVALUATION` (once it is genuinely 5+ days old)
- `PROCEED TO STAGE 11A SOAK-PERIOD PLANNING` (treating the above as follow-ups, not blockers)
