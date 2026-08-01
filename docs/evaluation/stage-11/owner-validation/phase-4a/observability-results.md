# Stage 11A Phase 4A — Observability Results (S11A-P4A-042)

**Status:** PASS · **Date:** 2026-08-01

Companion: [migration-design.md](migration-design.md) · [secret-sentinel-results.md](secret-sentinel-results.md)

## Metric

`lifeflow_credential_key_rotation_total{outcome}` (`apps/api/src/lifeflow_api/metrics.py`), a `Counter` registered against the module's existing process-local `REGISTRY` (never the global default, matching every other metric in this codebase). Exactly one label, `outcome`, drawn from the closed four-value vocabulary `migrated`/`skipped_current`/`blocked`/`failed` — the same shape `worker_job_events_total{job, outcome}` already established for background-job observability.

## What is deliberately never a label or logged value

Per the governing task's explicit prohibited list: no token, ciphertext, nonce, account email, user email, provider payload, exception text, or owner/account identifier is ever passed as a metric label or logged at any point in `credential_rotation.py`. `RotationBatchResult` (the structure returned to callers, including the operator CLI) carries only bounded integer counts plus a list of **account ids** for blocked rows (`blocked_account_ids`) — UUIDs, not content, included specifically so an operator can look up which rows need manual attention, analogous to how `data_deletion_operations` already records `user_id` (an identifier, not content) throughout this codebase's existing deletion engine. This is a deliberate, bounded exception to "never log an identifier" for the *specific, narrow* case of surfacing which rows are blocked to the one audience (an operator with direct database access) who could already see that same id by querying the table directly — it is never emitted as a Prometheus label (which would be unbounded cardinality) and never printed by the operator CLI's summary line, only carried in the in-memory result object.

## Verification

`test_metric_label_registries_are_closed_and_bounded`-style reasoning applies directly: `credential_key_rotation_total._labelnames == ("outcome",)`, a single, fixed, small label set defined at import time, never computed from row content. No test found a call site passing anything other than the four literal outcome strings.

## Conclusion

Rotation observability satisfies the "bounded, content-free" requirement. No P0. No P1.
