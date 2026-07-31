# Stage 11A Phase 3 — Storage-Surface Inventory

**Status:** Complete · **Date:** 2026-07-31

Companion: [data-flow-inventory.md](data-flow-inventory.md) · [../../../../delivery/stage-11a-phase-3-plan.md](../../../../delivery/stage-11a-phase-3-plan.md)

## PostgreSQL

Every user-owned table (`users`, `connected_accounts`, `source_items`, `signals`, `briefs`, `scheduled_brief_runs`, `action_proposals`, `action_executions`, `preferences`, `memory_items`, `memory_evidence`, `audit_events`, `data_deletion_operations`) carries a non-nullable `user_id` foreign key with `ondelete="CASCADE"` (`_user_fk()` helper, `models.py`), proven exhaustively by `test_ownership.py::test_every_user_owned_table_has_cascading_user_fk`. `action_executions` is owned transitively via `proposal_id` CASCADE.

- **Content-bearing columns**: `source_items.title/sender_or_organiser/metadata_json`, `action_proposals.payload_json/approved_payload_json/rationale`, `action_executions.executed_payload_json/result_json`, `briefs.summary/sections_json`, `memory_items.value_json`, `preferences.value_json`.
- **Identifier columns**: every table's `id` (UUID PK), `source_items.external_id`, `action_executions.idempotency_key`, `users.deletion_subject_id`/`google_subject`.
- **Encrypted fields**: `connected_accounts.encrypted_access_token/encrypted_refresh_token` (AES-256-GCM envelope, `v1:<key_id>:<nonce>:<ciphertext>`).
- **Hash columns**: `source_items.content_fingerprint`, `signals.dedupe_key`, `action_proposals.payload_hash/approved_payload_hash/approved_binding_hash/approved_execution_context_hash`, `action_executions.executed_payload_hash/approval_binding_hash` — all opaque SHA-256, never reversible to content.
- **Timestamps**: `created_at`/`updated_at` (server-default `func.now()`) on every mutable table; `occurred_at`, `expires_at`, `approved_at`, `first_observed_at`/`last_observed_at`/`last_evaluated_at` domain-specific timestamps.
- **Uniqueness constraints**: `(user_id, origin_fingerprint)` on `action_proposals`; `(user_id, memory_key)` on `memory_items`; `(user_id, provider)` on `connected_accounts`; a partial unique index guaranteeing at most one active deletion operation per `(user, type, scope)`.
- **Deletion behaviour**: imported-data deletion removes `source_items`/dependent `signals`/unapproved `action_proposals` for one account within the snapshot boundary; inferred-preference deletion removes `memory_items`/`memory_evidence`; full account deletion anonymises `users` (tombstone), removes `connected_accounts`/`source_items`/`signals`/`preferences`/`memory_items`, and minimises `action_executions.executed_payload_json` to `{}` while retaining the row for idempotency/audit integrity.
- **Anonymisation behaviour**: `account_deletion.py`'s phased `run_account_deletion_step` sets `deletion_subject_id=uuid4()`, `email=f"deleted+{id}@deleted.invalid"`, clears `google_subject`/`display_name`/`timezone`/`locale`, sets `account_state=deleted` — proven content-free by `test_account_deletion_anonymises_and_preserves_tombstones` and this phase's `tombstone-analysis.md`.
- **Tombstone behaviour**: `audit_events` (append-only, never deleted, `safe_metadata_json` closed schema) and `action_executions` (payload minimised, outcome/idempotency key retained) are the two REQUIRED RESIDUAL categories — see `deletion-residual-analysis.md`.

## Redis

- **Key namespaces**: `ratelimit:v1:<policy_code>:<hmac_digest>` (rate limiter, `rate_limiter.py::bucket_key`); `arq:result:*`/`arq:job:cron:*` (library-owned job bookkeeping for the deletion-drain and scheduled-brief cron).
- **Value shapes**: rate-limit buckets are a Lua-script-managed token count + refill timestamp (no content); arq result records are `{"f": function_name, "a": [opaque_uuid], "s": bool, ...}` — confirmed by direct `redis-cli --scan`/`GET` inspection in Phase 2 and re-confirmed this phase (`redis-residual-analysis.md`).
- **TTLs**: rate-limit buckets expire via the token-bucket window itself; arq result keys carry arq's own default result TTL.
- **Queue payloads**: job arguments are `run_id`/`operation_id` (opaque UUIDs) only — never content — enforced by a custom JSON (de)serializer overriding arq's default pickle (T28), verified against a real Redis instance.
- **Rate-limit identifiers**: HMAC-SHA256 digests of `subject_type:normalised_subject`, keyed by `RATE_LIMIT_KEY_SECRET` — never a raw user id or IP (T21).
- **Lock identifiers**: none — OAuth refresh concurrency is serialized via a PostgreSQL row lock (`SELECT ... FOR UPDATE`), not a Redis lock.
- **Job identifiers**: arq's own `arq:in-progress:<job_id>` TTL-based keys (library-internal, not application-owned; independently re-verified against the installed `arq==0.28.0` source in Phase 2).
- **Failure behaviour**: the rate limiter fails open on any Redis error (ADR 0005 D64) — the one approved fail-open path; every database-level guard (idempotency, approval binding, deletion uniqueness) stays authoritative regardless.
- **Cleanup behaviour**: bucket keys expire naturally; arq result keys expire per arq's own TTL; no LifeFlow-owned Redis key requires manual cleanup.

## Browser

- **Cookies**: exactly one — `lifeflow_session` (httpOnly, `SameSite=Lax`, `Secure` in production, 8h max-age, itsdangerous-signed). No other cookie is ever set.
- **localStorage / sessionStorage / IndexedDB / Cache Storage**: confirmed by repository-wide grep — zero usages anywhere in `apps/web/src`. No client-side persistence exists beyond the one backend-issued session cookie.
- **Browser cache**: standard HTTP caching only, governed by Next.js's default static-asset caching; no page response is user-content-cacheable across sessions (all data routes are dynamic/authenticated).
- **URL query strings**: never carry a token, payload, or personal content — routes are path/id-based, bodies carry mutation data.
- **Route state**: React Router/Next.js App Router state is in-memory only, cleared on navigation/reload.
- **Hydration payloads**: server-rendered page data is scoped to the authenticated user's own resources (proven by the owner-scoping test suite); no cross-session hydration cache exists.
- **Error overlays**: development-only Next.js error overlay is never enabled in production (`NODE_ENV=production` disables it structurally).
- **Downloadable artefacts**: LifeFlow has no user-facing export/download feature (confirmed in `generated-artefact-results.md`) — nothing to inventory here.

## Process and filesystem

- **Environment variables**: all secret-shaped vars (`SESSION_SECRET`, `TOKEN_KEY`, `GOOGLE_OIDC_CLIENT_SECRET`, `GOOGLE_CONNECTOR_CLIENT_SECRET`, `RATE_LIMIT_KEY_SECRET`, `ANTHROPIC_API_KEY`) are loaded via `pydantic-settings` from `.env` (untracked) and never logged; `.env.example` is validated to hold only known-safe placeholder values (`scripts/check_env_example_secrets.py`).
- **Temporary files**: this phase's new backup/deletion rehearsal script uses a `tempfile.TemporaryDirectory` removed at the end of every run regardless of outcome; no dump file is ever written outside that directory.
- **Logs**: structured JSON via `logging_setup.py::JsonFormatter`, redaction backstop applied to every message and exception field; never written to a committed path.
- **Screenshots**: owner-validation Playwright walkthroughs capture synthetic-data-only screenshots, individually viewed and never committed (Phase 1/2/3 convention).
- **Playwright output / caches / build output**: `.gitignore`d (`test-results/`, `playwright-report/`, `.next/`, `node_modules/`).
- **Docker volumes**: `db_data`/`redis_data` named volumes, local-only, never backed up outside this rehearsal's explicit local `pg_dump` scripts.
- **Backup files**: never committed; this phase's and Phase 2's rehearsal scripts delete every dump file at the end of every cycle.
- **Crash files**: none produced by this stack (no core dumps configured; Python/Node exceptions are caught and logged, not crash-dumped).
- **Shell history risk**: no script in this repository ever passes a secret as a bare CLI argument (`.env` is loaded via file, not `--flag=value`), so shell-history exposure risk is structurally low.
