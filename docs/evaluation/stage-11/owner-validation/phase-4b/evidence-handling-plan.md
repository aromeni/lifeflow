# Evidence-Handling Plan

**Status:** Defined · **Date:** 2026-08-01

Companion: [real-provider-data-boundary.md](real-provider-data-boundary.md) · [manual-walkthrough.md](manual-walkthrough.md)

## Permitted evidence

- Account-purpose identifiers that do not reveal credentials (e.g. "Account A", never the actual email address in a shared/committed document).
- Google Cloud configuration screenshots with project numbers and secrets redacted.
- The scope list (already public in [oauth-scope-matrix.md](oauth-scope-matrix.md)).
- The redirect URI (already a documented placeholder-shaped, non-secret value).
- Connection-gate results (bounded counts only).
- Content-free credential metadata (key id, envelope version — never ciphertext or plaintext).
- Synthetic inbox and event screenshots (fictional content only, per [real-provider-data-boundary.md](real-provider-data-boundary.md)).
- Provider-call counts (per [provider-call-budget.md](provider-call-budget.md)).
- Cleanup results (confirmation that residue checks passed).
- Owner observations (per [manual-walkthrough.md](manual-walkthrough.md)'s template).
- Defect records (per [defect-register.md](defect-register.md)).

## Prohibited evidence

- Passwords.
- Recovery codes.
- OAuth client secrets.
- Access tokens.
- Refresh tokens.
- Authorisation codes.
- Session cookies.
- Raw callback URLs containing sensitive parameters (`code`/`state` values).
- Unredacted Google Cloud credentials.
- Personal account identifiers (the owner's real email, phone number, or other real-account identifiers).
- Raw database dumps.
- Redis dumps.
- HAR files.
- Browser traces.
- Raw logs (unredacted).
- Screenshots containing real information.
- Absolute local filesystem paths (e.g. `/Users/<real-name>/...` — use relative repository paths in any evidence document instead).

## Secure out-of-repository storage

Any temporary operational evidence that would otherwise fall into the prohibited category above (e.g. a screenshot taken during a real future connection attempt, before it has been redacted) must be stored only in the owner's own local, non-synced, non-repository location until redacted or discarded — never pasted into a chat transcript, an issue tracker, or committed to Git even temporarily. Once redacted to contain only permitted evidence, it may be added to the evidence pack under `docs/evaluation/stage-11/owner-validation/phase-4b/` (or a future Phase 4C directory) following this document's categories.

## This document's own compliance

Every Phase 4B evidence document in this pack has been checked against this list before being written: no account credential, token, real project identifier, or absolute local path appears anywhere in `docs/evaluation/stage-11/owner-validation/phase-4b/`. This is re-verified mechanically as part of this phase's exact-boundary security proof, recorded in the final Phase 4B report rather than duplicated here.
