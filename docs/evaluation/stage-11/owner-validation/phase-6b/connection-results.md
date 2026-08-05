# Stage 11A Phase 6B — Connection Results

**Date:** 2026-08-05

Account A reconnected via the connector-consent flow (`/connected-accounts/google/connect`), never `/auth/google/login` (confirmed blocked with 409 throughout).

Verified directly against the database after connection:

- Exactly one real, credentialed `connected_accounts` row for `provider="google"` (`access_token_key_id` present).
- Status: `active`.
- Granted scopes: exactly the four approved scopes (`calendar.events`, `calendar.readonly`, `gmail.compose`, `gmail.readonly`) — no unexpected scope.
- Bound to exactly one LifeFlow user.
- Zero `users.google_subject` bindings anywhere (confirms OIDC sign-in was never used, at any point).
- Account B was never connected (no second `connected_accounts` row for provider `google`).

Owner confirmed: `CONSENT SCREEN VERIFIED — ACCOUNT A — APPROVED FOUR-SCOPE SET` (given retroactively, after independent backend verification of the scopes/account binding above — see `defect-register.md` for the process note on why this confirmation came after the fact rather than before, as originally sequenced).
