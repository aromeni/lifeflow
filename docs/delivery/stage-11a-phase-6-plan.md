# Stage 11A Phase 6 — Real Ingestion, Extraction, and First Provider-Write Validation

**Status:** Approved by the project owner 2026-08-04, amended twice (five initial amendments, then a further amendment replacing the write triggers) — all incorporated below · **Date:** 2026-08-04

Governed by [engineering-acceptance-contract.md](engineering-acceptance-contract.md). Follows Phase 5 (`PASS — DATASET POPULATED, READY FOR OWNER DECISION ON NEXT STEP`) and the project owner's authorisation: **AUTHORISE DECISION 2 — FIRST REAL PROVIDER-WRITE**.

Nothing has been executed yet. No branch has been created, no `.env` flag has been changed, and Account A remains disconnected. Checkpoint 1 (below) is entirely owner-performed and must complete before I do anything else.

## Supersession note — dedicated write-validation triggers replace GM-18/CAL-12

The original plan relied on GM-18 (a dataset-plan scenario) to trigger the Gmail draft, and on whichever of GM-01/05/10/17 happened to trigger a Calendar proposal organically — a genuine ambiguity for the Calendar side, and a dependency on GM-12 reaching five days old before the phase could start at all. The owner has now replaced both triggers with two dedicated, purpose-built messages:

- **P6-GM-TEST-01** — an unambiguous B→A request, worded as a single, explicit, standalone ask (e.g. "could you send over the latest version of the document") with no scheduling language mixed in, so it should produce exactly one clean `create_gmail_draft` candidate and nothing else.
- **P6-CAL-TEST-01** — an unambiguous B→A scheduling request, worded as a single, explicit meeting/call request with a time reference (e.g. "could we grab a call sometime in the next few days to go over X") and no document-request language mixed in, so it should produce exactly one clean `create_calendar_event` candidate and nothing else.

**GM-18 and CAL-12 (the original Phase 4B dataset-plan scenario IDs) stay permanently uncreated, superseded by these two.** This also decouples the write test from GM-12's five-day timer entirely — **the write test may proceed today.**

## Why this is still bundled with GM-01–17/CAL-01–11 ingestion

`POST /connected-accounts/google/sync` uses a fixed, non-configurable 14-day-past / 30-day-future window (`SYNC_WINDOW_PAST_DAYS`/`SYNC_WINDOW_FUTURE_DAYS`, `connected_accounts.py`) — there is no way to sync only the two P6 trigger messages without adding new code for a one-off test, which this plan avoids. Any real sync still imports the entire previously-populated dataset alongside the two new triggers. The extraction-accuracy comparison against that dataset therefore still happens as part of this phase (see below) — but it is now explicitly a *separate* piece of evidence from the write-trigger validation, per the owner's requirement 3.

## Objective

1. Immediately before reconnecting: refresh the eight time-relative Calendar fixtures (table below, unchanged from the prior amendment) and send both P6-GM-TEST-01 and P6-CAL-TEST-01, for real, between Account A and Account B.
2. Reconnect Account A and run exactly one real sync, importing the full previously-populated dataset plus the two new trigger messages as real `SourceItem`s.
3. Before approving anything: record content-free extraction-accuracy evidence for GM-01–17 (excluding GM-12, deferred — see below) and CAL-01–11 against Phase 4B's expected-outcome table. This is a separate evidence set from write-trigger validation and does not include P6-GM-TEST-01/P6-CAL-TEST-01 in its denominator.
4. Separately, confirm each P6 trigger message produced the intended proposal shape (exactly one `create_gmail_draft` candidate traceable to P6-GM-TEST-01; at most one `create_calendar_event` candidate traceable to P6-CAL-TEST-01).
5. Approve and execute **at most one** `create_gmail_draft` proposal, and only if it is derived from P6-GM-TEST-01.
6. Approve and execute **at most one** `create_calendar_event` proposal, and only if it is derived from P6-CAL-TEST-01 *and* meets the controlled acceptance envelope (unchanged from the prior amendment) — otherwise the Calendar write is not performed this pass.
7. Manually verify the resulting draft in Gmail (and the event in Calendar, if one was created).
8. Delete LifeFlow's own imported copies (`SourceItem`s, signals, brief) — but leave every message/event in Account A and Account B untouched, including GM-12 and both P6 triggers, so a later phase can re-sync without repopulating.
9. Revoke and disconnect Account A, and restore every flag to its safe default.

## GM-12's deferred evaluation

GM-12 (the "5+ days old, no reply" stale-follow-up scenario) is real-content-populated already but will not yet be old enough at the time this phase runs. It is **excluded from this phase's extraction-accuracy denominator** rather than evaluated prematurely and marked a false mismatch. Its accuracy check happens as a separate, later, lightweight follow-up (a fresh reconnect+sync once it is genuinely 5+ days old, since this phase deletes LifeFlow's local copies at the end) — it does not gate this phase's PASS/FAIL.

## Authorised boundary

- Immediately before reconnecting: refreshing CAL-01, CAL-02, CAL-03, CAL-04, CAL-05, CAL-06, CAL-07, and CAL-10 to fresh relative dates (table below), and sending P6-GM-TEST-01 and P6-CAL-TEST-01 for real, via Gmail's own interface.
- Reconnecting Account A via the connector-consent flow (same mechanics as Phase 4D).
- Temporarily setting `GOOGLE_PROVIDER_WRITES_ENABLED=true` (in addition to the initiation flag), for this window only.
- One real, on-demand sync (`POST /connected-accounts/google/sync`), accepting that it imports the entire populated dataset plus both new triggers as `SourceItem`s.
- Normal, unmodified operation of the extraction pipeline and brief generation against this real content.
- Recording extraction-accuracy evidence for GM-01–17 (excluding GM-12) and CAL-01–11 — a dataset-accuracy record, separate from write-trigger validation.
- Recording, separately, whether each P6 trigger produced its intended proposal shape.
- Approving **at most one** `create_gmail_draft` proposal, only if traceable to P6-GM-TEST-01.
- Approving **at most one** `create_calendar_event` proposal, only if traceable to P6-CAL-TEST-01 *and* it satisfies every condition in the controlled acceptance envelope.
- Explicitly rejecting or leaving untouched every other proposal the pipeline generates, including any candidate derived from GM-01–17 rather than the P6 triggers.
- At most one real Gmail draft creation, and (only if both the trigger-linkage and envelope conditions hold) at most one real Calendar event insertion, through the existing, already-tested real executors — no new application code is expected for this phase.
- Owner verification of both results directly in Gmail/Calendar (not merely LifeFlow's own confirmation).
- Manual deletion of the draft (Gmail) and, if created, the event (Calendar or the approved cleanup procedure).
- Preserving content-free extraction-accuracy and trigger-validation evidence, then running the existing imported-data and inferred-preference deletion operations against everything this sync created.
- Revoking access and disconnecting Account A afterward; restoring `GOOGLE_OAUTH_INITIATION_ENABLED=false` and `GOOGLE_PROVIDER_WRITES_ENABLED=false`.
- Leaving every message/event in Account A/Account B untouched, including GM-12 and both P6 triggers.

## Calendar fixture refresh (unchanged, performed immediately before reconnecting)

| Scenario | New timing, relative to the day of reconnection |
|---|---|
| CAL-02 | Today |
| CAL-03 | Tomorrow |
| CAL-06 | Tomorrow |
| CAL-01 | 2 days ahead |
| CAL-10 | 2 days ahead |
| CAL-04 | 3 days ahead |
| CAL-05 | 4 days ahead |
| CAL-07 | 5 days ahead |

CAL-08 (overlapping same-day pair), CAL-09 (cancelled), and CAL-11 (recurring) are not refreshed.

## Controlled Calendar-proposal acceptance envelope (unchanged, now also gated on trigger linkage)

A `create_calendar_event` proposal may be approved **only if it is derived from P6-CAL-TEST-01 and**:

- a new-event insertion (never anything resembling an update to an existing event);
- entirely fictional content;
- future-dated;
- exact-payload and exact-account bound;
- explicit about timezone and attendees (nothing silently inferred);
- limited to Account B as its only possible external attendee;
- notification-disabled (`sendUpdates=none`);
- structurally incapable of modifying or deleting CAL-01 through CAL-11.

**If no proposal traceable to P6-CAL-TEST-01 meets every condition, the Calendar write is not performed.** Recorded as "Calendar write not validated this pass," not a phase failure, requiring a separately authorised trigger correction (e.g. a reworded P6-CAL-TEST-01 in a future attempt) before it is attempted again. No proposal is ever approved merely to complete the phase.

## Prohibited boundary

- More than one Gmail draft, or any Gmail draft not traceable to P6-GM-TEST-01.
- Any Calendar event that doesn't meet the acceptance envelope, or isn't traceable to P6-CAL-TEST-01.
- Gmail send, Calendar update, or Calendar delete through LifeFlow (structurally impossible, per the existing proofs — restated as a policy boundary too).
- Connecting Account B to LifeFlow — Account B remains disconnected throughout.
- Any personal/business account.
- Automatically retrying an uncertain write.
- Starting the soak period.
- Participant recruitment activity.
- Stage 12 work.
- Creating a Stage 11/11A tag.
- Any new application code beyond what Phase 4D already built and tested.
- Deleting any message or event from Account A or Account B themselves.

## Owner-operated checkpoints (eight, updated)

1. **Trigger creation and dataset freshness** — refresh the eight Calendar fixtures per the table above, send P6-GM-TEST-01, send P6-CAL-TEST-01. Confirmation: `TRIGGERS SENT — DATASET FRESH`.
2. **Account A reconnection** — same consent-screen review as Phase 4D: `CONSENT SCREEN VERIFIED — ACCOUNT A — APPROVED FOUR-SCOPE SET`, then `OAUTH CALLBACK COMPLETED — RETURNED TO LIFEFLOW`.
3. **One manual sync** — owner triggers the sync from the Connections screen; confirmation: `SYNC COMPLETE`.
4. **Extraction/evaluation review** — owner (and I) review the dataset-accuracy comparison (GM-01–17 excl. GM-12, CAL-01–11) and, separately, whether each P6 trigger produced its intended proposal shape, before any approval; confirmation: `EVALUATION REVIEWED — READY FOR APPROVALS`.
5. **Gmail draft: approval, execution, verification, deletion** — approve at most one `create_gmail_draft` proposal traceable to P6-GM-TEST-01, confirm execution, verify the exact draft in Gmail, delete it: `GMAIL DRAFT VERIFIED AND DELETED`, or `GMAIL DRAFT NOT VALIDATED — NO QUALIFYING PROPOSAL` if P6-GM-TEST-01 didn't produce one.
6. **Calendar event: approval, execution, verification, deletion** — only if a proposal traceable to P6-CAL-TEST-01 meets the envelope: approve it, confirm execution, verify the exact event in Calendar, delete it: `CALENDAR EVENT VERIFIED AND DELETED`, or `CALENDAR WRITE NOT VALIDATED — NO QUALIFYING PROPOSAL`.
7. **Imported-data and inferred-data deletion** — after all evidence is recorded, run both deletion operations: `IMPORTED AND INFERRED DATA DELETED`.
8. **Revocation, disconnection, flag restoration, zero-residue verification** — as in Phase 4D: `DISCONNECTED — ACCOUNT A — GOOGLE ACCESS REVOKED CONFIRMED`.

`EMERGENCY STOP — <reason>` is always available in place of any of the above.

## Two separate evidence records (per the owner's requirement 3)

1. **Dataset extraction-accuracy evidence** — GM-01–17 (excluding GM-12, deferred) and CAL-01–11 against Phase 4B's expected-outcome table. First real-world measurement of extraction accuracy; a mismatch is a finding, not a phase failure, unless it reveals a genuine defect.
2. **Trigger-validation evidence** — for each of P6-GM-TEST-01 and P6-CAL-TEST-01: did it produce exactly one candidate proposal of the intended type, cleanly traceable to that specific trigger message (checked directly against the proposal's evidence/source reference in the Approvals UI, not assumed from category alone)? This record is kept separate from record 1 and is not counted into the GM-01–17/CAL-01–11 denominator.

Both are preserved before checkpoint 7's deletion runs.

## Safeguards

- Reuse Phase 4D's credential-storage and connection-gate checks unchanged.
- Before any approval, independently confirm from Audit History / provider-call metrics that zero writes have occurred yet.
- Before approving either proposal, independently verify its evidence/source reference in the Approvals UI actually points to the correct P6 trigger message — not merely that a proposal of the right *type* exists.
- After execution, independently confirm exactly one `lifeflow_provider_requests_total{provider="gmail",operation="create_draft"}` increment, and (only if a Calendar write happened) exactly one `{provider="calendar",operation="insert_event"}` increment.
- Re-run the existing write-block and idempotency regression tests fresh, as in the Phase 4D merge-integrity review.

## Evidence rules

Content-free throughout: scenario IDs, match/mismatch verdicts, and counts — never message bodies, event details, or account identifiers.

## Emergency stops

Reuses [real-provider-data-boundary.md](../evaluation/stage-11/owner-validation/phase-4b/real-provider-data-boundary.md)'s incident procedure for any real/personal content, and Phase 4D's emergency-stop table for connection-related failures, extended with: a second draft appearing unexpectedly; a proposal being approved despite failing trigger-linkage or the envelope; the approved payload not matching what's shown before approval; an uncertain write being retried; cleanup failing to remove the draft/event.

## Exit decision

Exactly one of:

- **PASS — FIRST PROVIDER WRITE AND REAL-INGESTION VALIDATION COMPLETE** (Gmail draft validated against P6-GM-TEST-01; Calendar event either validated against P6-CAL-TEST-01 or honestly recorded as not-validated-this-pass).
- **CONDITIONAL PASS** (a non-safety gap recorded, e.g. a dataset extraction-accuracy mismatch that isn't a defect).
- **FAIL — REAL PROVIDER WRITE REMAINS UNVALIDATED** (the Gmail draft itself could not be validated, or any emergency stop fired).

A PASS does not authorise the soak period or recruitment, and does not itself close out GM-12's deferred evaluation.

## Immediate next step

Checkpoint 1 is entirely yours, and can happen today: refresh the eight Calendar fixtures per the table above, then send P6-GM-TEST-01 and P6-CAL-TEST-01. Reply `TRIGGERS SENT — DATASET FRESH` when done, and I'll walk you through checkpoint 2 (reconnection).
