# Soak-Period Decision — Required Before Phase 4C

**Status:** Decision required, not yet made · **Date:** 2026-08-01

Companion: [google-platform-requirements.md](google-platform-requirements.md) · [defect-register.md](defect-register.md) · [phase-4b-decision.md](phase-4b-decision.md)

## The constraint

Verified against Google Cloud Console Help — Manage App Audience (`support.google.com/cloud/answer/15549945`), re-checked 2026-08-01: *"Authorizations by a test user will expire seven days from the time of consent. If your OAuth client requests an `offline` access type and receives a refresh token, that token will also expire."* Testing-status publishing is also capped at 100 listed test users (the same source).

LifeFlow's disposable two-account test-account model (Account A, Account B — see [test-account-specification.md](test-account-specification.md)) is trivially within the 100-user cap. The 7-day refresh-token/authorization expiry is not: the future 14–30 day owner soak period (Phase 4C, out of scope for this task) cannot run on a single Testing-status consent for its full duration.

## This phase's position

Phase 4B is readiness and planning only. It does not begin the soak period, does not choose between the two options below, and does not change any publishing status — none exists to change, since no Google Cloud project or OAuth consent screen has been created. The first controlled connection under [first-connection-runbook.md](first-connection-runbook.md) and the two authorisations in [provider-write-authorisation-gate.md](provider-write-authorisation-gate.md) do **not** require this decision — they are short, single-session activities that complete well inside any 7-day window. This decision is a precondition for Phase 4C (the soak period) alone.

## Option A — Testing-status re-authorisation cadence

- Remain in Testing publishing status for the entire soak period.
- Re-authorise (re-consent) the disposable test account roughly every 7 days, treating each expiry as an expected, planned interruption rather than a failure.
- LifeFlow's existing `InvalidGrantError` handling (`accounts.py:327-343` — marks the account `revoked`, requires re-authorisation) is the already-implemented, already-tested mechanism this option relies on; no product change is required to support it.
- Never claim, during or after the soak period, that OAuth authorization was continuous and uninterrupted — the record must show each re-consent as a distinct, dated event.
- Trade-off: operational overhead (a manual or scheduled re-consent step roughly every 7 days) in exchange for making no publishing-status change and triggering no verification requirement.

## Option B — reviewed publishing-status change

- Separately review the implications of changing the OAuth consent screen's publishing status from Testing to In production before the soak period begins.
- Reconfirm, at that time, the restricted-scope verification requirement for the two Gmail scopes (`gmail.readonly`, `gmail.compose` — classified **RESTRICTED**, requiring OAuth app verification plus an annual third-party security assessment for production use) and the standard verification requirement for the two Calendar scopes (classified **SENSITIVE**).
- Do not change the publishing status automatically or as a side effect of any other decision — it requires its own explicit, separate review.
- Do not claim production approval, verification completion, or compliance certification has occurred merely by considering or selecting this option — verification is a distinct, unstarted process with its own timeline and Google-side review.
- Trade-off: no recurring re-consent interruption during the soak period, in exchange for a verification process (timeline outside LifeFlow's control) and an annual recurring security-assessment obligation for the two Gmail scopes.

## What this document does not do

It does not choose Option A or Option B — that choice belongs to the project owner and is out of scope for Phase 4B and for this correction task. It does not start the soak period. It does not create a Google Cloud project, change a publishing status, or request verification. It exists so the decision is visible and unavoidable before Phase 4C begins, rather than discovered mid-soak when a token silently stops refreshing.

## Decided by

Not yet decided. Authority rests with the project owner, to be exercised before Phase 4C (the soak period) is planned or begins.
