# Stage 11A Phase 6 — Real Ingestion, Extraction, and First Provider-Write Validation

**Status:** Approved by the project owner 2026-08-04, subject to five amendments (all incorporated below) · **Date:** 2026-08-04

Governed by [engineering-acceptance-contract.md](engineering-acceptance-contract.md). Follows Phase 5 (`PASS — DATASET POPULATED, READY FOR OWNER DECISION ON NEXT STEP`) and the project owner's authorisation: **AUTHORISE DECISION 2 — FIRST REAL PROVIDER-WRITE (GM-18 GMAIL DRAFT, CAL-12 CALENDAR EVENT)**.

Nothing has been executed yet. No branch has been created, no `.env` flag has been changed, and Account A remains disconnected. Checkpoint 1 (below) is entirely owner-performed and must complete before I do anything else.

## Why this is bundled with real-ingestion validation, not narrowly scoped

`provider-write-authorisation-gate.md`'s Decision 2 describes GM-18/CAL-12 as coming from LifeFlow's *real* pipeline (a real email arrives, LifeFlow syncs it, extraction proposes the draft, the owner approves in the UI) — not a synthetic shortcut. Checked directly against the code: `POST /connected-accounts/google/sync` uses a **fixed, non-configurable 14-day-past / 30-day-future window** (`SYNC_WINDOW_PAST_DAYS`/`SYNC_WINDOW_FUTURE_DAYS`, `connected_accounts.py`), not a caller-controlled range. Since Phase 5's population happened well inside that window, any real sync run for this phase will import the *entire* populated dataset, not just GM-18. There is no product-code path to sync "only GM-18" without adding new code for a one-off test, which this plan deliberately avoids.

**A second, genuine uncertainty, stated honestly rather than assumed away:** `proposal_composition.py` derives `create_calendar_event` proposals from an *email* signal expressing scheduling intent, not directly from calendar content. The dataset plan does not name which specific message is expected to produce the CAL-12-shaped proposal. **This plan does not assume in advance which proposal(s) the real extraction pipeline will generate.** Amendment 3 below (the controlled acceptance envelope) governs which one, if any, may be approved.

## Objective

1. Once GM-12 is genuinely 5+ days old, refresh the time-relative Calendar fixtures and send GM-18, so both the "stale follow-up" and the "current" scenarios are genuinely fresh at ingestion time.
2. Reconnect Account A and run exactly one real sync, importing the full previously-populated dataset as real `SourceItem`s.
3. Let the real extraction/priority pipeline process this real content unmodified, and record how its output compares to Phase 4B's pre-specified expected outcomes for GM-01–17/CAL-01–11 (content-free: category/priority/signal-type match or mismatch only), before approving anything.
4. Approve and execute **exactly one** `create_gmail_draft` proposal.
5. Approve and execute a `create_calendar_event` proposal **only if one meets the controlled acceptance envelope** (Amendment 3) — otherwise the Calendar write is not performed this pass.
6. Manually verify the resulting draft in Gmail (and the event in Calendar, if one was created).
7. Delete LifeFlow's own imported copies (`SourceItem`s, signals, brief) — but leave the actual messages/events in Account A and Account B untouched, so a later phase can re-sync against the same fictional source dataset without repopulating it.
8. Revoke and disconnect Account A, and restore every flag to its safe default.

## Authorised boundary

- Waiting for GM-12 to be objectively 5+ days old before starting anything else in this phase (Amendment 1).
- Immediately before reconnecting: refreshing CAL-01, CAL-02, CAL-03, CAL-04, CAL-05, CAL-06, CAL-07, and CAL-10 to fresh relative dates (Amendment 2, exact mapping below), and sending the GM-18 email for real, between Account A and Account B, via Gmail's own interface.
- Reconnecting Account A via the connector-consent flow (same mechanics as Phase 4D).
- Temporarily setting `GOOGLE_PROVIDER_WRITES_ENABLED=true` (in addition to the initiation flag), for this window only.
- One real, on-demand sync (`POST /connected-accounts/google/sync`), accepting that it imports the entire populated dataset as `SourceItem`s.
- Normal, unmodified operation of the extraction pipeline and brief generation against this real content.
- Reviewing the extraction/evaluation comparison (Objective 3) before touching any approval.
- Approving **exactly one** `create_gmail_draft` proposal.
- Approving **at most one** `create_calendar_event` proposal, and only one that satisfies every condition in the controlled acceptance envelope (Amendment 3).
- Explicitly rejecting or leaving untouched every other proposal the pipeline generates.
- Exactly one real Gmail draft creation, and (if the envelope is met) exactly one real Calendar event insertion, through the existing, already-tested real executors — no new application code is expected for this phase.
- Owner verification of both results directly in Gmail/Calendar (not merely LifeFlow's own confirmation).
- Manual deletion of the draft (Gmail) and, if created, the event (Calendar or the approved cleanup procedure).
- Preserving content-free extraction-accuracy evidence, then running the existing imported-data and inferred-preference deletion operations against everything this sync created.
- Revoking access and disconnecting Account A afterward; restoring `GOOGLE_OAUTH_INITIATION_ENABLED=false` and `GOOGLE_PROVIDER_WRITES_ENABLED=false`.
- Leaving the fictional source content in Account A/Account B itself untouched (Amendment 5) — this phase deletes only LifeFlow's own local copies.

## Amendment 2 — exact Calendar fixture refresh (performed immediately before reconnecting)

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

CAL-08 (overlapping same-day pair), CAL-09 (cancelled), and CAL-11 (recurring) are not date-sensitive in the same way and are not refreshed.

## Amendment 3 — controlled Calendar-proposal acceptance envelope

A `create_calendar_event` proposal may be approved **only if it is**:

- a new-event insertion (never anything resembling an update to an existing event);
- entirely fictional content;
- future-dated;
- exact-payload and exact-account bound (the existing approval-binding behaviour, reconfirmed for this specific approval);
- explicit about timezone and attendees (nothing silently inferred);
- limited to Account B as its only possible external attendee;
- notification-disabled (`sendUpdates=none`);
- structurally incapable of modifying or deleting CAL-01 through CAL-11 (already guaranteed — no update/delete action type exists — reconfirmed as an explicit gate here too).

**If no proposal in the Approvals inbox meets every condition, the Calendar write is not performed.** This is recorded as "Calendar write not validated this pass," not as a phase failure, and requires a separately authorised trigger correction (e.g. a more explicit future scheduling request) before it is attempted again. No proposal is ever approved merely to complete the phase.

## Prohibited boundary

- More than one Gmail draft, or any Calendar event that doesn't meet the Amendment 3 envelope, regardless of how many proposals the pipeline generates.
- Gmail send, Calendar update, or Calendar delete through LifeFlow (structurally impossible, per the existing proofs — restated as a policy boundary too).
- Connecting Account B to LifeFlow — Account B remains disconnected throughout.
- Any personal/business account.
- Automatically retrying an uncertain write.
- Starting the soak period.
- Participant recruitment activity.
- Stage 12 work.
- Creating a Stage 11/11A tag.
- Any new application code beyond what Phase 4D already built and tested — if a real gap is found during this phase, it will be fixed and reported, not silently worked around.
- Deleting the fictional source messages/events from Account A or Account B themselves.

## Owner-operated checkpoints (Amendment 4 — exact set of eight)

1. **Dataset freshness and GM-18 creation** — confirm GM-12 is 5+ days old, refresh the eight Calendar fixtures per the Amendment 2 table, send GM-18. Confirmation: `DATASET FRESH — GM-18 SENT`.
2. **Account A reconnection** — same consent-screen review as Phase 4D: `CONSENT SCREEN VERIFIED — ACCOUNT A — APPROVED FOUR-SCOPE SET`, then `OAUTH CALLBACK COMPLETED — RETURNED TO LIFEFLOW`.
3. **One manual sync** — owner triggers the sync from the Connections screen; confirmation: `SYNC COMPLETE`.
4. **Extraction/evaluation review** — owner (and I) review the real extraction results against Phase 4B's expected-outcome table before any approval; confirmation: `EVALUATION REVIEWED — READY FOR APPROVALS`.
5. **Gmail draft: approval, execution, verification, deletion** — approve exactly one `create_gmail_draft` proposal, confirm execution, verify the exact draft in Gmail, delete it: `GMAIL DRAFT VERIFIED AND DELETED`.
6. **Calendar event: approval, execution, verification, deletion** — only if a proposal meets the Amendment 3 envelope: approve it, confirm execution, verify the exact event in Calendar, delete it: `CALENDAR EVENT VERIFIED AND DELETED`, or, if nothing qualified: `CALENDAR WRITE NOT VALIDATED — NO QUALIFYING PROPOSAL`.
7. **Imported-data and inferred-data deletion** — after extraction-accuracy evidence is recorded, run both deletion operations: `IMPORTED AND INFERRED DATA DELETED`.
8. **Revocation, disconnection, flag restoration, zero-residue verification** — as in Phase 4D: `DISCONNECTED — ACCOUNT A — GOOGLE ACCESS REVOKED CONFIRMED`.

`EMERGENCY STOP — <reason>` is always available in place of any of the above.

## Extraction-accuracy evidence (new to this phase, preserved before deletion — Amendment 5)

For each of GM-01–17 and CAL-01–11, record — content-free — whether the real pipeline's detected signal type, Today category, and priority band matched Phase 4B's expected-outcome table, **before** running the deletion in checkpoint 7. This is the project's first real-world (not demo-fixture) measurement of extraction accuracy, and is recorded honestly even where it doesn't match expectations — a mismatch here is a finding, not a phase failure, unless it reveals a genuine defect.

## Safeguards

- Reuse Phase 4D's credential-storage and connection-gate checks unchanged.
- Before any approval, independently confirm from Audit History / provider-call metrics that zero writes have occurred yet.
- After execution, independently confirm exactly one `lifeflow_provider_requests_total{provider="gmail",operation="create_draft"}` increment, and (only if a Calendar write happened) exactly one `{provider="calendar",operation="insert_event"}` increment — not merely trusting the UI's own success message.
- Re-run the existing write-block and idempotency regression tests fresh, as in the Phase 4D merge-integrity review.
- Independently verify the Amendment 3 envelope against the actual proposal payload shown in the Approvals UI before approval — not merely trust that it looks reasonable.

## Evidence rules

Content-free throughout, as in every prior phase: scenario IDs, match/mismatch verdicts, and counts — never message bodies, event details, or account identifiers.

## Emergency stops

Reuses [real-provider-data-boundary.md](../evaluation/stage-11/owner-validation/phase-4b/real-provider-data-boundary.md)'s incident procedure for any real/personal content, and Phase 4D's emergency-stop table for connection-related failures, extended with: a second draft appearing unexpectedly; a Calendar proposal being approved despite failing the envelope; the approved payload not matching what's shown before approval; an uncertain write being retried; cleanup failing to remove the draft/event.

## Exit decision

Exactly one of:

- **PASS — FIRST PROVIDER WRITE AND REAL-INGESTION VALIDATION COMPLETE** (Gmail draft validated; Calendar event either validated or honestly recorded as not-validated-this-pass with no envelope-qualifying proposal).
- **CONDITIONAL PASS** (a non-safety gap recorded, e.g. an extraction-accuracy mismatch that isn't a defect).
- **FAIL — REAL PROVIDER WRITE REMAINS UNVALIDATED** (the Gmail draft itself could not be validated, or any emergency stop fired).

A PASS does not authorise the soak period or recruitment — those remain separately gated.

## Immediate next step

Checkpoint 1 is entirely yours to perform, at your own pace: wait until GM-12 is 5+ days old, then immediately before you're ready to reconnect, refresh the eight Calendar fixtures per the table above and send GM-18. Reply `DATASET FRESH — GM-18 SENT` when that's done, and I'll walk you through checkpoint 2 (reconnection).
