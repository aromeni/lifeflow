# Stage 11A Phase 6A.1 — Existing Frontend Behaviour, Inspected Before Editing

**Date:** 2026-08-05

## Where Google sign-in visibility was determined

`apps/web/src/app/page.tsx` fetched `GET /config` once on mount and stored `config.google_oauth_enabled` in `googleOAuthEnabled` state (fail-closed default `false`). The "Sign in with Google" link rendered only when that single boolean was `true`; otherwise a static "not enabled" paragraph rendered.

## Where the Connections Google control was rendered

`apps/web/src/app/connections/page.tsx` never called `/config` at all. Its "Connect Google" link rendered unconditionally at both places a connected account could be absent or not-yet-connected — gated only on whether a `ConnectedAccount` row existed/was connected, never on whether the connector-consent flow was actually authorised.

## The safe public endpoint already in use

`GET /config` (`apps/api/src/lifeflow_api/health.py`) — public, unauthenticated, existed before this phase. Its single field, `google_oauth_enabled`, was computed via `google_wiring.google_integration_ready()`.

## Was `GOOGLE_OAUTH_ENABLED` being treated as both configuration readiness and flow authorisation?

Yes, on the landing page, confirmed by reading `google_integration_ready()`:

```python
def google_integration_ready(request: Request) -> bool:
    state = request.app.state
    return (
        state.google_oauth_client is not None
        and state.gmail_client is not None
        and state.calendar_client is not None
        and state.token_cipher is not None
    )
```

This depends only on whether `create_app()` constructed the OAuth/Gmail/Calendar clients — which happens whenever `Settings.google_oauth_enabled` and the client ID/secret/redirect fields are present — and has no dependency whatsoever on `google_oidc_signin_enabled` or `google_connector_oauth_enabled`. A deployment could have the provider fully configured with both per-flow flags safely disabled (exactly Phase 6A's own recommended safe-idle state) and this function still returns `True`.

## Could stale client state show an enabled control after the backend disables a flow?

Yes, in one direction: `/config` is fetched once on mount with no re-fetch on focus, interval, or navigation. If an operator disabled a flag on the backend while a tab was already open, that tab's rendered control would not update until the next full page load. This is a pre-existing characteristic of a static capability fetch, not something newly introduced by this phase's fix, and is not a safety gap — the backend guard is checked again, freshly, on every actual request, regardless of what the tab displays.

## Demonstrated, not just inferred

This phase's own verification (`truth-table-results.md`) reproduced the exact failure mode directly: the local development environment retained real Google client configuration from earlier phases (`GOOGLE_OAUTH_ENABLED=true`) with both per-flow flags at their safe `false` default — precisely the configuration Phase 6A recommends as the safe idle state. Under the pre-Phase-6A.1 frontend, this rendered a live, clickable "Sign in with Google" button that would 409 immediately on click. The repository's own pre-existing visual-regression baseline (`landing-darwin.png`) had captured this incorrect rendering as its recorded-correct state — independent evidence the discrepancy was real, not hypothetical, and had gone unnoticed until this phase's review.
