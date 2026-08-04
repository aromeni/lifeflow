# Stage 11A Phase 5 — Synthetic Dataset Population

**Status:** Approved by the project owner 2026-08-04; population checklist issued, execution (manual, owner-performed) in progress · **Date:** 2026-08-04

Governed by [engineering-acceptance-contract.md](engineering-acceptance-contract.md). Follows Phase 4D (`PASS — READY FOR OWNER DECISION ON SYNTHETIC DATASET POPULATION`, merged to `main` at `5266c4dd04c2c67ab416d34bd134c3811f5bd8cb`) and the project owner's authorisation: **AUTHORISE POPULATION OF ACCOUNTS A AND B WITH THE APPROVED SYNTHETIC GMAIL AND CALENDAR DATASET**.

The project owner reviewed this plan and approved it as drafted, without changes. No branch or code work is created by this phase — see "Authorised boundary" below. The companion [population-checklist.md](../evaluation/stage-11/owner-validation/phase-5/population-checklist.md) is the exact, self-contained document the owner follows to perform the 28 manual actions this phase authorises.

## What "the approved dataset" actually is

Phase 4B already designed and got structural sign-off on two dataset plans — this phase does not invent new content, it executes an existing design:

- [synthetic-gmail-dataset-plan.md](../evaluation/stage-11/owner-validation/phase-4b/synthetic-gmail-dataset-plan.md) — 18 email scenarios, GM-01 through GM-18.
- [synthetic-calendar-dataset-plan.md](../evaluation/stage-11/owner-validation/phase-4b/synthetic-calendar-dataset-plan.md) — 12 calendar scenarios, CAL-01 through CAL-12.

**Critical scope boundary, already decided by Phase 4B, not by this plan:** GM-18 (the Gmail-draft scenario) and CAL-12 (the Calendar-insertion scenario) are explicitly reserved in [provider-write-authorisation-gate.md](../evaluation/stage-11/owner-validation/phase-4b/provider-write-authorisation-gate.md) for a separate, not-yet-made **Decision 2 — first real provider-write authorisation**. They exist to prove LifeFlow's *own* write path (one Gmail draft, one Calendar insertion, through the app itself, under the write kill switch Phase 4D built). Populating them any other way — manually, or by any tool other than LifeFlow's real executor — would consume the one write-validation opportunity Decision 2 is designed to test cleanly and would misrepresent what Decision 2 later proves.

**This phase therefore populates GM-01–GM-17 (17 messages) and CAL-01–CAL-11 (11 events) only.** GM-18 and CAL-12 stay uncreated until Decision 2 is separately authorised.

## Objective

Get realistic, pre-approved, entirely fictional content into the real Account A / Account B Gmail and Calendar, using Google's own web interfaces — never LifeFlow's API — so a future phase can validate LifeFlow's real ingestion/sync path against real provider data instead of only the local demo/fake-provider fixtures.

## Authorised boundary

- The owner manually signs into Account A and Account B directly at gmail.com / calendar.google.com — never through LifeFlow, never via a LifeFlow-initiated OAuth flow.
- The owner manually sends/receives the 17 email scenarios (GM-01–GM-17) between Account A and Account B, matching each scenario's sender/recipient/subject/body intent as described in the dataset plan (paraphrasing the illustrative subject/body is fine — the *scenario category* is what must match, not exact wording).
- The owner manually creates the 11 calendar events (CAL-01–CAL-11) on Account A's primary calendar, inviting Account B as attendee only where the plan specifies it.
- Repository/tooling work I do autonomously: produce a single self-contained, step-by-step population checklist (derived verbatim from the two existing dataset plans) for the owner to follow at their own pace; no code changes are needed for this phase since it touches nothing in `apps/api` or `apps/web`.
- One consolidated, content-free owner confirmation once population is complete (see Owner checkpoint below) — not a checkpoint per item; with 28 pre-approved, non-sensitive fictional items and no LifeFlow code or credential involved, per-item gating would be disproportionate to the risk.

## Prohibited boundary

- Any LifeFlow API write of any kind — no Gmail draft creation, no Calendar event insertion through LifeFlow. GM-18 and CAL-12 remain uncreated.
- Reconnecting Account A to LifeFlow. This phase is deliberately independent of LifeFlow's OAuth/credential/read path entirely — Account A stays disconnected throughout, keeping this phase's blast radius to "manual actions in Google's own products," fully separate from any LifeFlow code path.
- Any real, personal, or confidential content of any kind — [real-provider-data-boundary.md](../evaluation/stage-11/owner-validation/phase-4b/real-provider-data-boundary.md)'s prohibited list applies unchanged and is still binding for the lifetime of these two accounts.
- Decision 2 (the single controlled Gmail draft / Calendar insertion) — remains separately gated, not implied by this authorisation.
- Starting the soak period, participant recruitment, Stage 12 work, or creating a Stage 11/11A tag.

## Owner checkpoint

Because this entire phase is manual action in Google's own products with no LifeFlow code involved, it is one consolidated checkpoint rather than several small ones:

1. I hand the owner a single checklist (28 rows: GM-01–GM-17, CAL-01–CAL-11), each row showing only the scenario ID and category (e.g. "GM-03 — unanswered request, B → A, no reply") — never the illustrative subject/body text repeated back verbatim, to keep the habit of not round-tripping account content through chat even when it's pre-approved fiction.
2. The owner performs all 28 items at their own pace, directly in Gmail/Calendar.
3. The owner reports completion with exactly: **`POPULATION COMPLETE — 17/17 MESSAGES — 11/11 EVENTS`**, or, if something couldn't be completed as specified, **`POPULATION PARTIAL — <what's missing>`**, or **`EMERGENCY STOP — REAL CONTENT INTRODUCED`** if real/personal content is accidentally entered into either account (see Emergency stop below).
4. Never requested: the accounts' passwords, recovery details, MFA/backup codes, or the literal message/event content — counts and scenario IDs are sufficient.

## Emergency stop — real content accidentally introduced

Reuses [real-provider-data-boundary.md](../evaluation/stage-11/owner-validation/phase-4b/real-provider-data-boundary.md)'s existing incident procedure unchanged: stop immediately, remove the content at the source (delete in Gmail/Calendar directly), check whether any evidence document captured it (unlikely here since no screenshot/content is requested), record as a P0 defect, and do not proceed to Decision 2 or any later phase until root-caused.

## Evidence rules

Content-free throughout, matching every prior phase: the evidence pack records scenario IDs and counts (e.g. "17/17 sent, 11/11 created"), never subject lines, bodies, real timestamps, attendee addresses, or screenshots of the accounts' actual inboxes/calendars.

## Exit decision

Exactly one of:

- **PASS — DATASET POPULATED, READY FOR OWNER DECISION ON NEXT STEP** (28/28 items confirmed by the owner, no real content introduced).
- **CONDITIONAL PASS** (population substantially complete with an explicitly recorded, non-safety gap — e.g. a scenario category the owner substituted for a practical reason).
- **FAIL — POPULATION INCOMPLETE OR COMPROMISED** (real content introduced, or population abandoned).

A PASS here does **not** itself authorise Decision 2, reconnecting Account A, real-ingestion validation, or the soak period — each remains a separate, explicit future owner decision. The natural next owner decisions this unlocks (not decided by this plan) are most likely one of:

- **AUTHORISE DECISION 2 — FIRST REAL PROVIDER-WRITE (GM-18 GMAIL DRAFT, CAL-12 CALENDAR EVENT)**
- **AUTHORISE RECONNECTION OF ACCOUNT A FOR REAL-INGESTION VALIDATION AGAINST THE POPULATED DATASET**

## Next steps

1. ~~Produce the 28-row population checklist as a companion evidence document.~~ Done — [population-checklist.md](../evaluation/stage-11/owner-validation/phase-5/population-checklist.md).
2. No branch or code work is needed for this phase — confirmed: it touches nothing in `apps/api` or `apps/web`.
3. Awaiting the owner's `POPULATION COMPLETE` confirmation (or `POPULATION PARTIAL`/`EMERGENCY STOP`), after which the Phase 5 evidence pack and decision record will be written.
