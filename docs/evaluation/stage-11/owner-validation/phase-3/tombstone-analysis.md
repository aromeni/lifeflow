# Stage 11A Phase 3 — Account-Deletion Tombstone Analysis (S11A-P3-037)

**Status:** PASS · **Date:** 2026-07-31

Companion: [deletion-residual-analysis.md](deletion-residual-analysis.md) · [privacy-operation-results.md](privacy-operation-results.md)

## Mechanism

`account_deletion.py::run_account_deletion_step`'s final phase (`_PHASE_FINALISE`) sets: `deletion_subject_id=uuid4()` (a fresh, unlinkable random identifier), `email=f"deleted+{deletion_subject_id}@deleted.invalid"`, clears `google_subject`/`display_name`/`timezone`/`locale` to `None`, and sets `account_state=deleted`.

## Direct inspection (re-run this phase)

`test_deletion_engine.py::test_account_deletion_anonymises_and_preserves_tombstones` (re-run, passing) directly inspects the reloaded `User` row and asserts: `account_state == deleted`, `deletion_subject_id is not None`, `email != original_email` and contains `@deleted.invalid`, `google_subject is None`. It further confirms zero remaining rows in `SourceItem`, `Signal`, `ConnectedAccount`, `Preference`, `MemoryItem` for that user, a positive count of retained `AuditEvent` rows (content-free tombstones), and a minimised `ActionExecution` tombstone.

This phase's own `test_stage11a_phase3_deletion_repeatability.py::test_full_account_deletion_ten_cycles` (10 cycles, passing) and `test_uncertain_execution_then_account_deletion_ten_cycles` (10 cycles, passing) independently re-confirm the same tombstone shape, and additionally confirm the sentinel draft-body content from an uncertain execution never survives in `executed_payload_json`/`result_json`.

## Verified against every governing-task requirement

- No email subject or body — structurally never stored (T15 ingestion minimisation).
- No calendar title or description — removed with the `ActionProposal`/`SourceItem` rows; only an opaque `approval_binding_hash` survives inside the minimised `ActionExecution` tombstone, never the calendar content itself.
- No recipient or attendee — same as above.
- No OAuth data — `ConnectedAccount` rows are fully removed, not merely marked disconnected.
- No proposal payload — `ActionProposal` rows are removed; the only surviving trace is the minimised `ActionExecution.executed_payload_json = {}`.
- No user email or provider account email — anonymised to the opaque `@deleted.invalid` form.
- No direct personal identifier — `deletion_subject_id` is a fresh random UUID, not derived from any personal value.
- No reversible encryption of deleted content — there is no encrypted content left to reverse; `encrypted_access_token`/`encrypted_refresh_token` columns are gone with the removed `ConnectedAccount` row.
- Identifiers are opaque — `deletion_subject_id`, retained `AuditEvent`/`ActionExecution` ids.
- Retention purpose is explicit — documented above and in [deletion-residual-analysis.md](deletion-residual-analysis.md).
- Access is restricted — the anonymised `User` row can never authenticate again (`get_current_user` blocks `deleted` accounts); tombstone rows are only ever read through the same owner-scoped repositories as any other data.
- Records cannot be used to reconstruct private content — every surviving field is either a count, a state, a safe reason code, or an opaque id.

## Result

The tombstone is content-free by construction and this phase's direct inspection confirms it holds true in practice, across 20 total fresh cycles (10 plain + 10 uncertain-execution-preceded).
