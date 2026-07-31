# Stage 11A Phase 1 — Deletion Residual Analysis

**Status:** Complete — no unexplained residual record found · **Date:** 2026-07-31

Companion: [reset-repeatability-results.md](reset-repeatability-results.md) · [safety-invariant-results.md](safety-invariant-results.md)

## Method

After each of the 10 reset-repeatability cycles, the synthetic database (`lifeflow_test`) was inspected directly (not through the API) via `apps/api/tests/test_stage11a_phase1_reset_repeatability.py`, immediately after `run_operation` (the real account-deletion worker body) completed.

## Residual record inventory

| Record type | Expected after full account deletion | Observed (10/10 cycles) | Permitted? | Reason |
|---|---|---|---|---|
| `SourceItem` (imported emails/events) | 0 | 0 | N/A — none remain | Content-bearing, must be fully removed |
| `Signal` (extracted signals) | 0 | 0 | N/A — none remain | Content-bearing, must be fully removed |
| `ConnectedAccount` | 0 | 0 | N/A — none remain | Credentials/tokens must be fully removed |
| `Preference` | 0 | 0 | N/A — none remain | Personal product data, must be fully removed |
| `MemoryItem` | 0 | 0 | N/A — none remain | Personal product data, must be fully removed |
| `AuditEvent` | > 0 (retained) | > 0, confirmed present every cycle | **Yes** | Content-free integrity tombstone — required so a later reconciliation or dispute has a trace that *something* happened, without retaining what happened in identifiable form (`account_deletion.py:71`, `DISPOSITION_RETAINED_AUDIT`) |
| `ActionExecution` (minimised) | Retained, minimised | Retained; `executed_payload_json == {}` in the existing test this reuses (`test_account_deletion_anonymises_and_preserves_tombstones`) | **Yes** | Execution tombstone — proves an action happened (for provider-side reconciliation of an in-flight write) without retaining its content (`account_deletion.py:70`, `DISPOSITION_RETAINED_EXECUTIONS`) |
| `ActionProposal` (minimised) | Retained, minimised | Not independently re-queried by the new harness in this phase (already covered by the existing test this reuses) | **Yes** | Proposal tombstone (`account_deletion.py:69`, `DISPOSITION_MINIMISED_PROPOSALS`) |
| `User` row itself | Retained, anonymised | Retained; `account_state == deleted`, email → `@deleted.invalid`, `google_subject` cleared, `deletion_subject_id` set | **Yes** | Anonymisation, not erasure — required so re-authentication is permanently blocked and the deletion itself is auditable |

## No unexplained residual record

Every retained row type has a named, documented reason (a disposition constant in `account_deletion.py`, unchanged by this phase) and is content-free or minimised. Nothing was found retained without a stated purpose.

## Cross-user containment

Each of the 10 cycles used a distinct synthetic user; no cycle's deletion step touched another cycle's data (implicit in the per-user `WHERE model.user_id == user_id` scoping used throughout `_count`, matching the production repository pattern's ownership scoping proven separately by `test_ownership.py`).
