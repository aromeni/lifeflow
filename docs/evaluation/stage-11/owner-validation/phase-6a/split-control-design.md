# Stage 11A Phase 6A — Split-Control Design

**Date:** 2026-08-05

## Design

```
provider configured (GOOGLE_OAUTH_ENABLED + complete client config)
        │
        ├── GOOGLE_OIDC_SIGNIN_ENABLED=true      → OIDC sign-in available
        ├── GOOGLE_CONNECTOR_OAUTH_ENABLED=true  → connector consent available
        └── neither / provider not configured    → neither flow available
```

Effective logic, matching the governing instruction's §4 exactly:

- provider configured + sign-in enabled → OIDC sign-in available.
- provider configured + connector enabled → connector consent available.
- provider configured + both disabled → neither flow available.
- provider not configured → neither flow available, regardless of either per-flow flag (and unreachable in practice — see below).

## Master flag retained, never sole authorisation

`GOOGLE_OAUTH_ENABLED` is unchanged: it remains the "Google integration configured" prerequisite (client IDs/secrets/redirect URIs present and validated, `TOKEN_KEY` set), checked once at startup (`main.py`). It was never itself an authorisation to initiate either flow, and still isn't. Both new guards require it in addition to their own flag — identical shape to the guard they replace.

## New controls

```python
# config.py
google_oidc_signin_enabled: bool = False
google_connector_oauth_enabled: bool = False
```

```python
# oauth_initiation.py
def require_google_oidc_signin(request: Request) -> None: ...
def require_google_connector_oauth(request: Request) -> None: ...
```

Both are environment-only (`pydantic-settings`), exactly like every existing flag in this project — never settable by an HTTP request. Both default `false`. Neither function references the other's flag.

## Startup validation

```python
if settings.google_oidc_signin_enabled and not settings.google_oauth_enabled:
    raise RuntimeError("GOOGLE_OIDC_SIGNIN_ENABLED=true requires GOOGLE_OAUTH_ENABLED=true.")
if settings.google_connector_oauth_enabled and not settings.google_oauth_enabled:
    raise RuntimeError("GOOGLE_CONNECTOR_OAUTH_ENABLED=true requires GOOGLE_OAUTH_ENABLED=true.")
```

This makes "provider not configured but a per-flow flag enabled" an unreachable runtime state — the app refuses to start, which is a stronger guarantee than a route-level 404 would be. Confirmed with a dedicated test for each flag.

## No backward-compatible fallback

`google_oauth_initiation_enabled` and `require_google_oauth_initiation` are removed outright — not deprecated, not aliased, not silently mapped to "enable both." Every call site and every test that referenced them was updated in the same change, not left to fail later.

## What was deliberately not built

- **No new frontend capability-exposure API.** The "Sign in with Google" and "Connect Google" links remain static, as they were before this phase. The route itself is, and remains, the sole enforcement point. Building a dynamic capability endpoint would be new scope beyond "separate the two controls," and the original incident was never caused by the UI misrepresenting availability — it was caused by the route itself permitting the flow.
- **No weakening of PKCE, state, owner binding, or redirect matching.** `oauth_state.py` and `google/oauth.py` are untouched by this phase.
