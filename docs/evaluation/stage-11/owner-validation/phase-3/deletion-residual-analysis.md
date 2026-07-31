# Stage 11A Phase 3 — Deletion Residual Analysis (S11A-P3-035)

**Status:** PASS — no unjustified content-bearing residual · **Date:** 2026-07-31

Companion: [privacy-operation-results.md](privacy-operation-results.md) · [tombstone-analysis.md](tombstone-analysis.md)

Every row/key enumerated after the deletion paths exercised this phase (imported-data ×5, inferred-preference ×5, full account ×10, uncertain-execution-then-account-deletion ×10), classified per the governing framework. No item is classified only "miscellaneous" or "internal."

| Residual item | Storage location | Content-bearing? | Owner-identifying potential | Operational purpose | Retention justification | Classification |
|---|---|---|---|---|---|---|
| `users` row (post-account-deletion) | PostgreSQL `users` | No — anonymised (`deleted+<uuid>@deleted.invalid`, `google_subject`/`display_name`/`timezone`/`locale` cleared) | Opaque `deletion_subject_id` only, not reversible to a real identity | Prevents re-authentication; preserves referential integrity for audit tombstones | Required to keep `audit_events`/`action_executions` FK-valid without orphaning them | **REQUIRED RESIDUAL** |
| `audit_events` rows | PostgreSQL `audit_events` | No — `safe_metadata_json` closed schema, no raw content ever written | Only the (anonymised) `user_id` FK | Append-only compliance/transparency record (T18) | Explicit product requirement — audit integrity must survive account deletion | **REQUIRED RESIDUAL** |
| `action_executions` rows | PostgreSQL `action_executions` | No — `executed_payload_json` minimised to `{}` on deletion; `result_json`/idempotency key/outcome retained | Only via `proposal_id` (proposal itself removed on full deletion; row retained standalone) | Proves no duplicate external write occurred; supports future dispute resolution | Required for idempotency/audit integrity (T12) | **REQUIRED RESIDUAL** |
| `data_deletion_operations` rows | PostgreSQL `data_deletion_operations` | No — content-free by construction (counts, states, safe reason codes only) | Anonymised `user_id` after account deletion | Proves the deletion itself actually happened | Required — without this, "was it deleted?" would be unanswerable | **REQUIRED RESIDUAL** |
| Rate-limit bucket (if the deleted user had an active one) | Redis | No — HMAC digest key, token-count value | None (pseudonymised) | Abuse control | Expires naturally via TTL, no action needed | **TEMPORARY RESIDUAL** (self-expiring) |
| arq job-result key (if a deletion job ran) | Redis | No — opaque UUID + status | None | Library bookkeeping | Expires via arq's own default TTL | **TEMPORARY RESIDUAL** (self-expiring) |
| Pre-deletion `pg_dump` backup (this phase's rehearsal only) | Local scratch directory | Yes, by design (a point-in-time snapshot) | Full pre-deletion state | Proves backup/restore fidelity and the honest deletion-vs-backup limitation | Deleted at the end of every rehearsal cycle — never persists | **TEMPORARY RESIDUAL** (rehearsal-scoped, always destroyed) |

## Reduction check

Every REQUIRED RESIDUAL item was checked for further minimisation opportunity: `action_executions.result_json` already excludes provider content (only a safe status message); `audit_events.safe_metadata_json` already excludes raw metadata by the Stage 9 closed-registry design. No further reduction is possible without breaking the idempotency/audit-integrity guarantees those tables exist to provide.

## Result

Zero UNJUSTIFIED RESIDUAL or DEFECT classifications. Every surviving row/key is either required for an explicit safety/integrity guarantee, or self-expiring with no content.
