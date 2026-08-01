# Preconnection Readiness Automation — Results

**Status:** Built and verified · **Date:** 2026-08-01

Companion: [credential-preconnection-results.md](credential-preconnection-results.md) · [first-connection-runbook.md](first-connection-runbook.md)

## Command

`apps/api/scripts/preconnection_readiness_check.py` — new this phase.

```
uv run python3 scripts/preconnection_readiness_check.py [--json]
```

## Checks performed

| Check | What it verifies | Displays |
|---|---|---|
| `environment_not_production` | `ENVIRONMENT != production` | environment name only |
| `e2e_test_controls_disabled` | `E2E_TEST_CONTROLS_ENABLED=false` | boolean only |
| `fake_provider_override_unset` | `GOOGLE_API_ORIGIN_OVERRIDE` empty | "unset" or "is set" (never the value) |
| `single_alembic_head` | exactly one Alembic head reported | head count |
| `migration_0012_applied` | the head is (or includes) `0012` | head revision id (non-secret) |
| `active_key_configured` | `TOKEN_KEY` is set | active key **id** only (never key material) |
| `dev_key_id_rejected_in_production` | would `main.py`'s production guard reject the current key id | "safe" / a description, never the key itself |
| `database_reachable` | PostgreSQL reachable (reuses `check_database`) | boolean + exception class name only, never a connection string |
| `connection_gate_clear` | Phase 4A `credential_connection_gate` reports `clear_to_connect=true` | bounded counts only (reuses the existing gate, never decrypts) |
| `redis_reachable` | Redis reachable (reuses `health.py`'s `check_redis`) | boolean only |
| `callback_configuration_present` | both redirect URIs are configured when `GOOGLE_OAUTH_ENABLED=true` | the connector redirect URI (already a documented non-secret placeholder-shaped value) |

## Output

Human-readable (default) or `--json` (machine-readable), always exit 0 only when every check passes, 1 otherwise. Verified: no secret, token, key material, or private content appears in either output mode — every field is a boolean, a count, an environment name, a non-secret key id, or a redirect URI that is already documented in `.env.example` as a placeholder-shaped, non-secret configuration value.

## Result against current local state (2026-08-01)

```
[PASS] environment_not_production: environment=development
[PASS] e2e_test_controls_disabled: e2e_test_controls_enabled=False
[PASS] fake_provider_override_unset: unset
[PASS] single_alembic_head: 1 head(s) reported
[PASS] migration_0012_applied: 0012 (head)
[PASS] active_key_configured: active key id=dev-1
[PASS] dev_key_id_rejected_in_production: safe
[PASS] database_reachable: PostgreSQL reachable
[PASS] connection_gate_clear: unversioned=0 legacy_known=0 legacy_unknown=0
[PASS] redis_reachable: reachable
[PASS] callback_configuration_present: http://localhost:8010/connected-accounts/google/callback

READY
```

Exit code 0.

## Relationship to `--connection-gate`

This command is a superset of `rotate_credential_keys.py --connection-gate` — it calls the same `credential_connection_gate()` function as one of its 11 checks, plus the broader environment/service/configuration prerequisites the governing instruction's §22 requires beyond credential state alone. Both commands remain available; a future connection task should run this broader command, not the narrower one, as its final gate before step 17 of [first-connection-runbook.md](first-connection-runbook.md).

## What it does not do

It does not create accounts, OAuth clients, or connections. It does not decrypt any credential. It does not accept any argument beyond `--json`.
