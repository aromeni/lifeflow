# Stage 11A Phase 1 — Safety-Invariant Results

**Status:** All invariants hold · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md) · [../../owner-validation-success-criteria.md](../../owner-validation-success-criteria.md)

Each invariant below is the specific, checkable claim Stage 11A's success criteria require before any participant evaluation can be considered. Every one is backed by a re-run automated test on this branch, not an assumption carried from a prior stage.

| Invariant | Threshold | Result | Evidence |
|---|---|---|---|
| Zero Gmail send capability | 0 | **0** — no send code path exists anywhere in the executor/client layer; `GmailDraftClient` only implements `create_draft`, allowlisted to `{"drafts"}` | `gmail_client.py:33-34,253-266`; `action_executors.py:191-298`; grep confirms no live `send` call, only disclaiming comments |
| Zero Calendar edit/delete capability | 0 | **0** — `CalendarEventClient` defines only `list_events`/`insert_event`/`get_event`; no update/patch/delete method, no generic request passthrough | `calendar_client.py:4-11,115-249`; `action_executors.py:316-324` |
| Zero duplicate provider writes under repeated failure/repeat-call tests | 0 | **0** across every re-run, including 10 new reset-repeatability cycles | `test_execution_durability.py::test_replay_never_calls_executor_twice...`; `test_stage11a_phase1_reset_repeatability.py` (double-execute assertion, 10/10) |
| Zero automatic uncertain-write retries | 0 | **0** — status deliberately held at `executing`, comment states "Never retried automatically" | `action_proposal_service.py:824-838`; `test_execution_durability.py::test_uncertain_outcome_leaves_proposal_executing_and_is_never_retried`; `stage10-uncertain-execution-fixture.spec.ts` (re-run, passing) |
| 100% synthetic reset reliability across repeated runs | 100% | **100%** — 10/10 cycles, zero residual data, zero duplicate executions | `test_stage11a_phase1_reset_repeatability.py` |
| Successful recovery after every defined service interruption exercised this phase | 100% of exercised cases | Journeys A–D of the resilience suite (provider read outage, uncertain write across API restart, worker-outage durable completion, dependency-health under real Postgres/Redis restart) all pass | `./scripts/e2e-resilience.sh` — 6/6 passed this session |
| No cross-user data exposure | 0 | **0** — isolation proven with locally-created synthetic user pairs, no real accounts needed | `test_ownership.py` (4 tests), `test_google_policy_and_isolation.py`, `test_privacy_deletion_api.py::test_cross_user_operation_is_404` |
| Successful imported-data deletion | Verified | Verified via existing dedicated tests; Phase 1's demo-mode walkthrough correctly shows this control as scoped to real-provider accounts (not a gap — see F-001 discussion in defect-register.md) | `test_privacy_deletion_api.py::test_preview_and_confirm_imported_data` |
| Successful inferred-memory deletion | Verified | Verified; delete-one and delete-all both isolated per user | `test_memory_api.py::test_delete_one_removes_item_and_records_key_only`, `::test_delete_all_removes_every_memory`, `::test_memories_are_isolated_per_user` |
| Successful account anonymisation | Verified | Verified — email → `@deleted.invalid`, `google_subject` cleared, `deletion_subject_id` set, re-run stable (idempotent) | `test_deletion_engine.py::test_account_deletion_anonymises_and_preserves_tombstones`, `::test_account_deletion_is_idempotent`; 10/10 new cycles |
| No raw private content in logs, metrics, or Redis keys | 0 | Rate-limiter keys are HMAC-SHA256 pseudonymised, never a raw user id/IP; audit metadata proven content-free by existing dedicated tests | `rate_limiter.py::hash_subject`; `test_action_proposals.py::test_audit_metadata_never_contains_payload_content`; `test_deletion_engine.py` (audit tombstone content-free assertions) |
| No secrets detected | 0 | **0** — full-history and staged Gitleaks, detect-secrets both clean | See [Exact-boundary security proof] in the final report |
| Stable daily brief generation | Deterministic | "Deterministic under repeat composition: True" | `./scripts/run-evals.sh brief`, `brief+mock` |
| All participant-facing P0/P1 risks resolved before recruitment consideration | 0 unresolved | 0 — no P0/P1 exists in this phase's own defect register, and no new participant-facing risk was found beyond the pre-existing, already-resolved Round-1 desk-rehearsal findings | [defect-register.md](defect-register.md) |

## Addendum: new invariant from the F-002 closure (2026-07-31)

| Invariant | Threshold | Result | Evidence |
|---|---|---|---|
| The test-only demo-clock override never affects any security- or expiry-relevant clock | 0 leakage | **0** — action-proposal expiry keeps anchoring to the real wall clock even with a far-past override active; the override is inert unless the pre-existing production-guarded `e2e_test_controls_enabled` flag is also on | `test_stage11a_demo_clock_determinism.py::test_demo_clock_override_does_not_affect_action_proposal_expiry`; `test_e2e_test_controls.py::test_e2e_test_controls_enabled_refuses_to_start_in_production_with_demo_clock_override`, `::test_demo_clock_override_alone_is_safe_in_production` |

## Verdict

Every safety invariant Stage 11A Phase 1 exists to check holds, confirmed by re-running the actual tests rather than citing memory of a prior stage's results. All 14 original invariants were reconfirmed fresh during the F-002 root-cause closure (2026-07-31), and the invariant above is newly established by that closure.
