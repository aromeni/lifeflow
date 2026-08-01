# OAuth Secret Handling Plan

**Status:** Designed and verified against current configuration handling · **Date:** 2026-08-01

Companion: [google-cloud-project-plan.md](google-cloud-project-plan.md) · [.env.example](../../../../../.env.example)

## Storage

The future Google OAuth client id/secret pairs (one pair for the OIDC sign-in client, one for the connector-consent client — `GOOGLE_OIDC_CLIENT_ID`/`GOOGLE_OIDC_CLIENT_SECRET`/`GOOGLE_CONNECTOR_CLIENT_ID`/`GOOGLE_CONNECTOR_CLIENT_SECRET`, `config.py:66-72`) are stored **only** in the developer's local, gitignored `.env` file, loaded by `Settings`' existing `env_file` mechanism (`config.py`). No approved alternative secret-injection mechanism is introduced by this phase — the existing `.env`-only pattern (already used for `TOKEN_KEY`, `SESSION_SECRET`, etc.) is sufficient for local owner-only testing and is not changed.

## Verified against current implementation

- **Never committed to Git.** `.gitignore` already excludes `.env` (confirmed present); `detect-secrets`/Gitleaks pre-commit hooks scan every commit regardless.
- **Never placed in `.env.example` as a real value.** Verified: `.env.example:44-63` contains only placeholder values (`your-oidc-client-id.apps.googleusercontent.com`, `GOCSPX-your-oidc-client-secret`) — the existing `check .env.example for live-secret-shaped values` pre-commit hook enforces this on every commit.
- **Never printed by startup.** `main.py`'s lifespan does not log `settings.google_*_client_secret` anywhere; `Settings` is a Pydantic model and its `__repr__` is never logged in full (confirmed by the existing Phase 4A acceptance row S11A-P4A-021 pattern — configuration values never appear in repr/logs/health/metrics/error responses — the same guard applies unchanged to the two new secret fields since they follow the identical `Settings` field pattern).
- **Never exposed through health or readiness.** `/health`/`/ready` routes return only bounded, non-configuration status (existing tests `test_health.py`/`test_ready.py`).
- **Never returned to the browser where not required.** The client secret is used only server-side, in `oauth_client.exchange_code(...)` calls (`auth.py:137-143`, `connected_accounts.py:121-127`) — never placed in a redirect URL or JSON response.
- **Never stored in PostgreSQL.** No table or column persists the client secret; only the *resulting* per-account access/refresh tokens are stored, and those go through Phase 4A's `TokenKeyRing` encryption — the client secret itself is a process-level configuration value, not a per-account credential.
- **Never stored in Redis.** No code path writes the client secret to Redis; the only Redis usage in this area is rate-limiting buckets keyed by IP/user, never configuration values.
- **Never recorded in Audit History.** `record_audit_event` calls in `auth.py`/`connected_accounts.py` write only `user_id`, `actor`, `event_type`, `entity_type`/`entity_id`, and a small bounded `metadata` dict (e.g. `{"method": "google_oidc"}`) — never a secret value.
- **Never copied into evidence documents.** This document and every other Phase 4B evidence file contains only placeholder client-id/secret shapes (e.g. `your-connector-client-id.apps.googleusercontent.com`), matching `.env.example`'s existing convention — never a real value, since no real project or client exists yet.

## Owner responsibility

- **Initial entry**: the project owner pastes the client id/secret from the Google Cloud Console directly into their local `.env` — never through this assistant, a chat transcript, or a shared document.
- **Validation procedure**: `build_authorization_url`/`exchange_code` calls will fail loudly (visible in local logs as a Google-side OAuth error, never a raw secret) if the id/secret pair is wrong — no separate validation step is needed beyond attempting the flow.
- **Rotation procedure**: rotate the secret in Google Cloud Console (which immediately invalidates the old one), then update the local `.env`; no code change required since the value is read from configuration at process start.
- **Revocation procedure**: same as rotation — rotating the Cloud Console secret is itself the revocation mechanism for a compromised client secret.
- **Accidental-exposure procedure**: if a client secret is ever accidentally pasted into a commit, chat, or document — rotate it immediately in the Google Cloud Console (invalidating the exposed value) and remove/redact the exposed copy from wherever it was pasted (including revoking a leaked commit's reachability where feasible); the exposure of a client secret alone does not expose any already-issued user access/refresh token, since those are separately encrypted per-account.
- **Cleanup procedure**: at programme end, delete the OAuth client entirely from the Google Cloud Console (see [google-cloud-project-plan.md](google-cloud-project-plan.md)'s shutdown procedure) rather than merely removing it from the local `.env`.
- **Production replacement requirement**: a future Stage 12+ production deployment must use a separate client id/secret pair issued on a separate, non-testing Google Cloud project — the disposable testing project's credentials must never be reused in production. Not implemented in this phase; recorded as a forward requirement only.

## `.gitignore`/`.dockerignore` review

`.gitignore` already excludes `.env` and other local secret-shaped files. This repository has no custom Docker image build (only official `postgres`/`redis` images are used per Phase 3's defect register), so `.dockerignore` review is not applicable — unchanged finding from Phase 3.
