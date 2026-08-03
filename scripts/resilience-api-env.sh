#!/usr/bin/env bash
# Stage 9 Delivery Phase 5 (§20): the exact environment the dedicated
# resilience-journey API instance (port 8011) runs with. Single source of
# truth, `source`d by both `scripts/e2e-resilience.sh` (the initial start)
# and `journey-b-uncertain-write.spec.ts` (which kills and respawns this
# exact process mid-test to prove an API restart never retries an uncertain
# provider write) — duplicating these values in two places would risk them
# drifting apart and silently changing what the journey actually proves.
#
# Never real credentials: GOOGLE_OIDC_*/GOOGLE_CONNECTOR_* only need to be
# non-empty to satisfy `create_app`'s GOOGLE_OAUTH_ENABLED=true startup
# validation — sign-in uses dev-login, never the real Google OAuth flow.
# TOKEN_KEY must byte-for-byte match `_FAKE_TOKEN_KEY` in
# apps/api/scripts/e2e_google_support.py.
export WEB_ORIGIN=http://localhost:3001
# Fixed (never a real secret): without this, a restart generates a fresh
# ephemeral session secret (main.py's documented dev/test convenience),
# invalidating every existing session cookie — exactly the real-world
# reason a production deployment always sets this explicitly, and exactly
# what Journey B's API-restart step needs to NOT happen.
export SESSION_SECRET=e2e-resilience-fixed-session-secret-not-a-real-secret-32c  # pragma: allowlist secret
export GOOGLE_OAUTH_ENABLED=true
# These journeys seed fake credentials directly and never exercise browser
# OAuth consent. Keep the independent Phase 4C initiation/callback gate shut.
export GOOGLE_OAUTH_INITIATION_ENABLED=false
export GOOGLE_OIDC_CLIENT_ID=resilience-e2e-oidc-id
export GOOGLE_OIDC_CLIENT_SECRET=resilience-e2e-oidc-secret  # pragma: allowlist secret
export GOOGLE_OIDC_REDIRECT_URI=http://localhost:8011/auth/google/callback
export GOOGLE_CONNECTOR_CLIENT_ID=resilience-e2e-connector-id
export GOOGLE_CONNECTOR_CLIENT_SECRET=resilience-e2e-connector-secret  # pragma: allowlist secret
export GOOGLE_CONNECTOR_REDIRECT_URI=http://localhost:8011/connected-accounts/google/callback
export TOKEN_KEY=ZTJlLXJlc2lsaWVuY2UtZmFrZS10b2tlbi1rZXktMzI=  # pragma: allowlist secret
export TOKEN_KEY_ID=e2e-resilience-1
export E2E_TEST_CONTROLS_ENABLED=true
export GOOGLE_API_ORIGIN_OVERRIDE=http://127.0.0.1:8098
# Short write budget so Journey B's hang-on-write scenario (the fake server
# withholds its response for 8s) is observed as an uncertain outcome
# quickly rather than the test waiting 8+ seconds per case.
export GOOGLE_WRITE_TIMEOUT_SECONDS=2
