# Threat Model

**Status:** Stage 7 reviewed (v5, focused remediation round 3) · **Date:** 2026-07-17 · **Review before:** Stage 11 (deployment)

Scope: the MVP described in [../product/mvp-scope.md](../product/mvp-scope.md), with components and trust boundaries from [../architecture/system-context.md](../architecture/system-context.md). T11/T19/T20/T22/T23 were mitigated in design **before** the Stage 7 OAuth implementation began, as required; this revision (v3) records how each mitigation was actually built.

## Assets

1. OAuth access/refresh tokens (Google).
2. Email metadata and constrained message content; calendar event data.
3. Derived signals, briefs, and proposals (still personal data).
4. Application session credentials.
5. Audit log integrity.
6. Anthropic API key and LLM prompt contents.

## Trust boundaries

- **B1** Browser ↔ API (authenticated session).
- **B2** API ↔ Google / Anthropic (outbound, credentialed).
- **B3** Ingested content ↔ reasoning (untrusted data vs system policy) — the prompt-injection boundary.
- **B4** Proposal ↔ execution (policy engine gate).

## Threats and planned mitigations

Every mitigation maps to a planned component and delivery stage (Stage 0 check: "threat model maps mitigations to planned components").

| ID | Threat | Boundary | Mitigations | Component | Stage |
|---|---|---|---|---|---|
| T1 | OAuth token theft (DB dump, backup leak, log leak) | B2 | Application-level AES-GCM encryption via `TokenCipher` before storage; env-managed dev key, KMS-ready interface; documented rotation; tokens never logged; minimal scopes limit blast radius | Token cipher, ConnectedAccount repo, log redaction | 2, 7 |
| T2 | Cross-user data access (IDOR, missing ownership filter) | B1 | `user_id` on all user-owned records; ownership enforced in every repository query and route; isolation tests that actively attempt cross-user access | Repositories, auth middleware, test suite | 2 |
| T3 | Prompt injection inside emails / event descriptions | B3 | Content treated as untrusted data; clear delimiting; instructions inside content ignored by design; extraction output limited to typed schemas; tool eligibility decided by application code + policy engine, never by model prose; adversarial fixtures in demo dataset and eval suite | Ingestion sanitiser, LLM layer, policy engine, evals | 3, 4, 6 |
| T4 | Indirect instructions attempting tool invocation ("forward all mail to…") | B3, B4 | High-risk actions unrepresentable as action types; proposals schema-validated; policy engine + human approval gate every execution; injection E2E test must show zero triggered actions | ActionProposal schema, policy engine | 4, 6 |
| T5 | Malicious links and attachments | B3 | MVP never browses links or opens attachments; links rendered non-clickable in evidence views or clearly marked external | Ingestion, UI evidence drawer | 3, 5 |
| T6 | Sensitive data in logs (tokens, bodies, headers, cookies, prompts) | all | Structured logging with correlation IDs; redaction layer for credentials, cookies, auth headers, email bodies, private event descriptions, personal-data prompts; redaction unit tests; periodic log review (Stage 9) | Logging module | 1, 2, 9 |
| T7 | CSRF | B1 | Same-site session cookies, CSRF tokens on state-changing routes; framework protections verified by tests | Web/API session layer | 2 |
| T8 | XSS (including hostile email content rendered in UI) | B1 | React auto-escaping; no `dangerouslySetInnerHTML` for ingested content; email content rendered as plain text in MVP; CSP headers | Web app | 3, 5 |
| T9 | SSRF | B2 | No user-supplied URLs fetched in MVP (no link browsing); outbound calls restricted to Google/Anthropic endpoints | API egress discipline | 4, 7 |
| T10 | SQL injection | B1 | SQLAlchemy parameterised queries only; no string-built SQL; lint/review gate | Repositories | 2 |
| T11 | Insecure OAuth redirects / state forgery | B2 | Exact-match registered redirect URIs; `state` validation; PKCE; tests for tampered state and redirect; separate OIDC and connector-consent client configurations (redirect URIs cannot be confused between the two flows) | Google OAuth flow (`google/oauth.py`) | 7 |
| T12 | Replay / duplicate execution (double-click, retries, job re-runs) | B4 | Idempotency key per execution; unique constraint; duplicate-execution integration tests; executed payload must hash-match approved payload | ActionExecution, policy engine | 6 |
| T13 | Approval bypass via payload mutation after approval | B4 | Approval binds to payload hash; any edit invalidates approval; policy engine re-verifies at execution time | Proposal state machine | 6 |
| T14 | Dependency compromise | build | Lockfiles (uv, pnpm); CI dependency audit + secret scanning; minimal dependency policy (ADR D9) | CI pipeline | 1 |
| T15 | Excessive data retention | data | Constrained ingestion window; `retention_expires_at` on SourceItem; retention jobs (idempotent); documented policy in privacy screen | Retention jobs, privacy UI | 3, 9 |
| T16 | Missing disconnect/deletion | data | Disconnect stops syncs and attempts token revocation; delete removes/anonymises imported + derived data; verified by integration tests | Connections service | 9 |
| T17 | Model-provider data exposure | B2 | Redact/minimise before LLM calls; only necessary fields sent; provider-neutral layer allows policy per provider; demo/CI never call real providers; document provider data-use terms before pilot | LLM layer | 4, 10 |
| T18 | Audit log tampering or secret leakage into audit | integrity | Append-only writes (no update/delete paths); `safe_metadata_json` schema excludes secrets; redaction tests | AuditEvent | 2 |
| T19 | Session hijack / weak app auth | B1 | Google Sign-In (OIDC) with server-side sessions; secure, httpOnly, same-site cookies; session expiry; auth security tests | Session layer | 2 |
| T20 | Scope creep / silent broadening of Google scopes | B2 | Connector scopes declared in one constant; UI shows exactly the scopes Google actually granted (never the requested set); no automatic re-request of dropped scopes; test asserts the authorization-URL scope string matches the documented set | Google adapter, Connections UI | 7 |
| T21 | Rate-limit abuse / cost exhaustion (LLM or Google quota) | B2 | Bounded pagination, bounded retries, request timeouts; per-user rate limiting (Stage 9); cost capture per LLM call | LLM layer, API middleware | 4, 9 |
| T22 | `gmail.compose` scope permits sending, not just drafting — a compromised or buggy code path could send mail even though the product never intends to | B2 | Defense in depth, not scope reliance (ADR 0003 D11/D33): closed `ActionType` enum has no send member; `GmailDraftClient` exposes only `create_draft()` against one fixed, allow-listed path; no generic request method exists; transport-level tests assert the only HTTP call ever made is `POST /gmail/v1/users/me/drafts`. The literal allow-list assertion inside the client is a cheap self-check, not itself the boundary — see D33 | `google/gmail_client.py`, `action_executors.py` | 7 |
| T23 | Undisclosed guest notification on calendar-event creation (Google's default `sendUpdates` behaviour would email attendees without the user ever approving a "send") | B4 | `CalendarEventClient.insert_event()` hard-codes `sendUpdates=none` (not caller-overridable); the approval preview carries an immutable `guest_notifications: off` field bound into the same payload hash | `google/calendar_client.py`, approval preview | 7 |
| T24 | Execution context substitution — a proposal approved under one execution path (simulation, or a specific Google account/scope) silently executing under a different one because the decision was recomputed from live "is anything connected" state instead of what the user actually approved | B4 | `execution_context.py` binds execution mode/provider/account/scope to the proposal's own evidence provenance, never to "any capable account"; the approved snapshot (`ActionProposal.approved_execution_*`, migration `0008`) is persisted at approval and re-verified twice: once pre-commit (`validate_execution`) and, atomically with token acquisition — under the same account row lock, after the durability commit (D16) that necessarily releases the pre-commit check's locks — via `GoogleTokenService.get_valid_access_token_for_execution` (ADR 0003 D34); any difference (disconnect, reconnect, scope change, a different source account) raises `approval_context_changed` before any provider call and is classified `failed`, not `uncertain` | `execution_context.py`, `action_policy.py`, `action_proposal_service.py`, `accounts.py`, `action_executors.py` | 7 |
| T25 | Silent pagination data loss — a connector's committed sync cursor advancing past pages it never actually fetched because a configured page bound was reached first, permanently skipping the unseen data on every future sync | B2 | `GoogleSyncCursor` separates the committed cursor from mid-pagination continuation state; the committed cursor only advances on a genuine final page; an incomplete attempt persists a resumable continuation and reports `incomplete`/`sync_complete=False` instead of silently succeeding; a later sync resumes from the continuation rather than skipping ahead (ADR 0003 D32) | `google_sync_cursor.py`, `connectors/google_email.py`, `connectors/google_calendar.py` | 7 |
| T26 | OAuth token-endpoint failures misclassified as an unhandled exception (generic 500) instead of the designed controlled outcome, because only `invalid_grant` was distinguished from every other non-200 response | B2 | `GoogleOAuthClient._classify_token_error` maps every non-200 response (429/5xx, `server_error`/`temporarily_unavailable`, `invalid_client`/`unauthorized_client`, `invalid_request`/`unsupported_grant_type`/`invalid_scope`, any other 4xx) to an existing typed error the executors already handle as `uncertain` or a controlled final failure — never a generic 500, never treated as final merely because the response was non-200 (ADR 0003 D31) | `google/oauth.py` | 7 |
| T30 | A real credential committed to example/template configuration (`.env.example`) going undetected because no scanning gate actually ran against the commit that introduced it | build | `scripts/check_env_example_secrets.py` — a narrow, branch-agnostic, current-tree check specifically for this file, wired into pre-commit and into `secret-scan.yml`, which (unlike `ci.yml`) triggers on every branch push, not only `main`/PRs; see "Credential exposure incident" below for the incident this closes | `scripts/check_env_example_secrets.py`, `.pre-commit-config.yaml`, `.github/workflows/secret-scan.yml` | 8 |

## Prompt-injection boundary (expanded)

All connector content is untrusted. Concretely:

1. Source content is wrapped in explicit delimiters and role-tagged as data before any LLM call; the system prompt states that instructions inside data must be ignored.
2. The LLM can only return instances of registered output schemas; anything else is rejected and retried within a fixed limit.
3. The set of possible action types is a closed enum owned by application code. "Send email", "forward", "delete" do not exist in the enum — a hijacked model cannot propose them.
4. No ingested link is fetched; no attachment is parsed.
5. Adversarial fixtures (including the demo dataset's injection email) run in CI; the unsafe-action rate on them must be zero (criterion S5 in [../product/mvp-scope.md](../product/mvp-scope.md)).

## Encryption and key management assumptions

- Dev: single symmetric key from environment (`TOKEN_KEY`, with `TOKEN_KEY_ID` naming it), never committed; `.env.example` documents it without a value.
- Interface: `TokenCipher.encrypt/decrypt` with key-id in the ciphertext envelope, enabling rotation (re-encrypt on read) and a KMS-backed implementation in production.
- Rotation: documented manual procedure in MVP; automated rotation is post-MVP.

## Stage 6 verification notes

- T3/T4: deterministic composition produced no proposal from injection fixture `em-004`; the action golden suite and Playwright journey verify no injection evidence or text crosses the proposal boundary.
- T12: `action_executions.proposal_id` and idempotency keys are unique; a replay returns the original success or final failure record without invoking an executor again.
- T13: approval binds the closed action type, canonical typed payload, payload hash and proposal version. An approved edit clears the snapshot, increments the version and appends `approval.invalidated` in the same transaction.
- Expiry and ownership are checked while the owner-scoped proposal row is locked immediately before approval or first execution. Denied execution attempts are audited without recording payload content.
- No Stage 6 module imports a Google client or performs an external side effect; task, Gmail-draft and calendar-event executors return deterministic simulated results only.

## Stage 7 verification notes

- T1/T7: OAuth tokens remain encrypted via `TokenCipher` before storage; a refresh response omitting `refresh_token` (Google's normal behaviour outside the initial grant) never clears the stored value — proven by a test that a refresh with no `refresh_token` field leaves the encrypted envelope byte-identical (ADR 0003 D18).
- T11: `state` and a PKCE `code_verifier`/`code_challenge` (S256) are generated per-flow and stored in the existing signed session cookie with a short server-checked TTL, cleared on first use; the connector-consent flow additionally binds `state` to the signed-in `user_id`. Redirect URIs are exact-match against configured settings, never derived from the request `Host` header. Sign-in and connector-consent use separate client configurations (D10), so a redirect-URI or state value from one flow is meaningless in the other.
- T19 (ID token trust): verified via `google-auth`'s maintained `verify_oauth2_token` (JWKS fetch/cache, signature, issuer, audience, expiry) through a thin injectable wrapper — no hand-rolled JWT cryptography (D14). `email_verified` must be `true` or sign-in is rejected. Account linking is by `google_subject` (`sub`) only; a pre-existing user with a matching email is never automatically merged (D15), closing an account-takeover vector.
- T20: the connector-consent callback persists exactly the scopes Google's response reports as granted, never the requested set; a partial grant (user deselects a scope on Google's consent screen) is recorded honestly and the policy engine denies the actions that scope would have covered.
- T22 (new): `gmail.compose` is a broad scope that permits sending; Stage 7 does not rely on the scope to prevent it. See the closed action-type enum, the narrow `GmailDraftClient`, and the transport-level test asserting the only Gmail write call ever made is `POST /gmail/v1/users/me/drafts`.
- T23 (new): calendar event creation hard-codes `sendUpdates=none`; no guest is ever notified and no other calendar is modified by Stage 7. The approval preview discloses this as an immutable field rather than leaving it implicit.
- Durable execution attempts (extends T12): an `ActionExecution` row (`outcome=pending`) is committed *before* any real Google call, independent of the request's main transaction, so a crash or network failure during the call cannot erase the fact that an attempt was made. A stale `pending` row transitions to `uncertain` on next read; `uncertain` is never automatically retried (extends assumption A20 from "final failure" to "any non-confirmed outcome").
- Ingestion minimises content at the source (Gmail `format=metadata` with an explicit header allow-list, no raw body) — less untrusted content is ingested per message, narrowing T3's practical surface without changing the boundary itself.
- Scheduling-intent extraction (ADR 0003 D39) stays inside the T3 boundary: email text is matched against a closed cue/pattern set only (`scheduling_phrases.py`), never interpreted as instructions; extracted values can only ever populate the typed `CalendarEventCreatePayload` a human must review before anything is created; bulk/newsletter senders are excluded before extraction runs; and the extractor cannot select tools, change action types, or widen policy — action eligibility remains decided by application code and the policy engine.

## Stage 7 remediation round 2 verification notes

- T24: `resolve_execution_context` is unit- and integration-tested against all nine required approval-context scenarios (`test_execution_context_binding.py`) — synthetic-sourced approval surviving a later Google connect with zero Google HTTP calls made; a real approval blocked (not downgraded to simulation) once its exact source account disconnects; a reconnect (`authorisation_revision` bump) blocking a stale approval; a routine token refresh (no revision change) leaving the approval valid; a scope removal blocking execution; a stale preview producing a controlled `stale_execution_context` 409 rather than approving against reality; and a concurrent account-state change racing `execute()` never producing an undisclosed provider call or a `simulation` outcome for a real-approved proposal.
- T24 (frontend): `ActionProposalPanel.tsx` sends the exact execution-context hash it displayed on approve; the API independently re-verifies it server-side (never trusts the client's claim); a changed context surfaces as a visible, non-dismissable-by-approving banner with Execute disabled, never a silent proceed.
- T25: `test_google_connectors.py` and `test_google_sync_service.py` cover every page-bound scenario in the remediation brief — more pages than the bound, exactly at the bound, resuming a persisted continuation (same base cursor, continuing page token), a windowed continuation resuming with its exact original query window, an expired/invalid continuation falling back to a fresh bounded resync, and a failed import leaving both the committed cursor and any continuation untouched. No page token or provider error detail appears in the sync route's response or audit metadata (asserted directly in `test_sync_route_reports_incomplete_sync_truthfully`).
- T26: `test_google_oauth.py` exercises the complete classification matrix through the real `GoogleOAuthClient`; `test_execution_context_binding.py`/`test_google_route_integration.py` prove the classification is actually reachable through the real action-execution route (a token refresh failure mid-execution resolves to `uncertain`/a controlled final failure, never a generic 500), and that a replay after an `uncertain` outcome never makes a second Google call.
- T13 (extended): the approval-binding hash (`approval_binding_hash`) now includes the execution-context hash alongside action type, canonical payload, and proposal version — an approval cannot be replayed against a different execution mode, provider, or account than the one actually displayed.

## Stage 7 focused remediation round 3 verification notes

- T24 (extended — post-commit TOCTOU closed, ADR 0003 D34): `test_google_token_execution_race.py` drives the real `ActionProposalService` -> `GoogleExecutorRegistry` -> `GoogleGmailDraftExecutor`/`GoogleCalendarEventExecutor` -> `GoogleTokenService` path (never the `CountingExecutor` stub) against a mocked transport that raises on any Gmail/Calendar write call. A deterministic `post_commit_hook` seam pauses `execute()` immediately after the durability commit; a genuinely independent second PostgreSQL session then reconnects (bumping `authorisation_revision`) or removes the required scope, commits, and only then does `execute()` resume — proving the executor never reaches the provider once the row-locked check (atomic with token acquisition) detects the mismatch, that the failure is classified `failed`/`approval_context_changed` (never `uncertain`, never a silent `simulation` result), and that a replay makes no further provider call. Covered for both Gmail and Calendar, at the shared token-acquisition layer directly (`test_google_token_service.py`), and through one full HTTP route-level path (`create_app()` -> `/execute` -> the real object graph).
- T24 (identity-map correctness): the fix depends on every consent-relevant `ConnectedAccount` read (`ConnectedAccountRepository.get`/`get_by_provider`/`list`, and the new exact-account query) using `populate_existing()` — without it, this app's `expire_on_commit=False` session configuration would let a row already read once in a request (e.g. `execute()`'s own pre-commit `accounts.list()`) silently mask a concurrent committed change even under a real `SELECT ... FOR UPDATE` lock. Caught by the round-3 race tests themselves; a naive first implementation of the fix passed every test except the ones using a genuinely independent second session.
- T13/T24 (UI): `ActionProposalPanel.tsx` now distinguishes an `approval_context_changed` execution failure from an ordinary one — "Not executed — approval context changed", explicit "no external action was attempted" copy, and disables Approve entirely (not merely Execute) whenever `execution_mode` is `unavailable`.

## Credential exposure incident (2026-07-21) and remediation

A real Google OAuth client secret (both the OIDC and connector client secrets) was found committed in plaintext in `.env.example` at commit `d8a6de1` ("feat(stage-7): complete approval-bound Google integration"), pre-existing and unrelated to Stage 8 Phase 2 work. Confirmed real by the human user. **Rotation confirmed complete** (2026-07-21): both exposed secrets were rotated/revoked in Google Cloud Console directly (outside this repository's control — this assistant had no access to do that, and did not request or view either the old or replacement value); the ignored local `.env` was updated to the new credential and the stack restarted; fresh Google OIDC sign-in, the connector consent/callback flow, and Google sync were all re-verified working; no replacement credential was added to any tracked file.

**Risk-acceptance decision** (repository is private, single-contributor): the revoked credentials may remain in private Git history; no history rewrite or force-push will be performed at this time; the repository must not be made public or shared externally until the affected history (see refs below) has been purged. This is a live constraint on future work, not just a historical note — revisit before any visibility change.

**Affected refs** (everywhere the leaking commit `d8a6de1` is reachable):

- Local branches: `stage-7-google`, `stage-8-preferences`, `stage-8-scheduled-briefs`.
- Remote branches: `origin/stage-7-google`, `origin/stage-8-preferences`.
- Tags: `stage-7-complete`.
- **Not** reachable from `main` or `origin/main` — no PR was ever opened merging the leaking branch into `main`.
- The redaction fix (commit `203f8126afa0dbc2dbd22e5f7d753a0ce77d4878`, `.env.example` only) exists solely on the local `stage-8-scheduled-briefs` branch; it has not been pushed and is not on any tag.
- A later commit, `07c568e1` (the Stage 8 Phase 1 base, present on `stage-8-preferences` and `stage-8-scheduled-briefs`, local and `origin/stage-8-preferences`), carried the same leaked file forward unchanged before the redaction.

**Why the existing scanning gates did not block this**: both scanners are technically capable of catching this value — verified directly against the original historical file content: `detect-secrets scan` flags both lines (`Base64HighEntropyString` and `Secret Keyword`), and `gitleaks git` flags both as `generic-api-key`. The gap was not detection capability but that neither gate ever actually ran against the commit:

1. The local pre-commit hook is opt-in per clone (`uvx pre-commit install`, documented as a one-time manual step in CLAUDE.md) — there is no server-side enforcement, so a commit made before that step is run locally is never checked.
2. The CI "Secret scanning" job existed (added in `94cfb41`) but its trigger was `push: branches: [main]` plus `pull_request` — identical to every other job in `ci.yml`. `d8a6de1` was pushed directly to `origin/stage-7-google` with no PR ever opened against `main`, so the workflow's checkout never included that ref, and the job simply never executed against this content. Confirmed by running `gitleaks git` locally scoped to `main`'s history alone (8 commits, no leaks) versus the branch containing the leak (12 commits, 2 real findings) — the difference is entirely which ref is scanned, not scanner behavior.
3. `.secrets.baseline` did not allow-list or otherwise suppress this secret — at commit `d8a6de1` the baseline contained no entry at all for `.env.example`, ruling out an allow-list failure.

**Regression protection added**:

- `scripts/check_env_example_secrets.py` — a narrow, dedicated, branch-agnostic check: every secret/token/password/key-shaped variable in `.env.example` must hold one of a small explicit set of known-safe placeholder values (never a heuristic like "contains the word placeholder"), plus a defense-in-depth check for known vendor secret-format prefixes (`GOCSPX-`, `AIza`, `sk-`, `ghp_`, `AKIA`, etc.) against every value regardless of variable name. Covered by 7 tests in `apps/api/tests/test_env_example_placeholders.py`, including one that asserts the real, current `.env.example` has zero findings.
- Wired into `.pre-commit-config.yaml` (new local hook, `files: ^\.env\.example$`) — current-tree scanning, runs on every commit once installed.
- Wired into a new `.github/workflows/secret-scan.yml`, split out of `ci.yml` specifically so it triggers on **every branch push**, not only `main`/PRs — this is what closes the actual gap above. It also carries forward the existing gitleaks (full-history-for-this-ref) and `detect-secrets-hook` (current-tree, against the committed baseline) steps, unchanged in behavior, merely relocated and re-triggered.
- **Current-tree vs. history scanning, explicitly**: `detect-secrets` (pre-commit and CI) and `check_env_example_secrets.py` scan the file content as it exists right now on whatever ref is checked out — they say nothing about older commits. `gitleaks git` scans every commit reachable from the checked-out ref, back to the root — this is what would have caught `d8a6de1` if the workflow had ever run against a ref containing it. Neither mechanism inspects refs it is never pointed at, which is precisely how this leak survived: `main` was always clean, and nothing ever scanned the branch that was not clean.

**Full-history scan after remediation** (`gitleaks git --no-banner --redact` against the full local repository, all commits reachable from `HEAD` on `stage-8-scheduled-briefs`, run 2026-07-21): 2 genuine findings, both the original `d8a6de1` commit (`GOOGLE_OIDC_CLIENT_SECRET`, `GOOGLE_CONNECTOR_CLIENT_SECRET`); the remaining 7 reported matches are `.secrets.baseline`'s own stored SHA-256 hashes (expected noise from scanning a secrets-baseline file itself, not a live secret). No other commit, file, or branch surfaced a finding.

**History-rewrite plan (documented, not executed — the risk-acceptance decision above defers it)**:

Because the leaking commit is not reachable from `main`, a full rewrite need not touch the repository's primary line of history. Recorded here so it can be executed later without re-deriving it, should the risk-acceptance decision above ever be revisited (e.g. before making the repository public or adding a collaborator):

1. Rotation is already confirmed complete (see above) — a rewrite at that point is pure history hygiene, not an active leak response.
2. Rewrite only the three affected refs — `stage-7-google`, `stage-8-preferences`, and the tag `stage-7-complete` — using `git filter-repo` (preferred over `git filter-branch`, which is slower and easier to misuse) with a path+content rule scoped to `.env.example`, replacing the two known secret values with the current placeholder text. Do this in a fresh clone, not the working copy in use, to avoid disturbing work on `stage-8-scheduled-briefs`.
3. The annotated tag `stage-7-complete` cannot be edited in place; it must be deleted and recreated pointing at the new, rewritten commit that replaces the one it currently references, with the same tag message and a note in its message recording that it was recreated for this reason.
4. Force-push (`--force-with-lease`, never bare `--force`) each rewritten ref to `origin`, in this order: `stage-7-google`, `stage-8-preferences`, then the recreated tag — `--force-with-lease` will reject any push if the remote has moved since the last fetch, which is the correct behavior here since it is a shared ref.
5. `stage-8-scheduled-briefs` (this branch) would need to be rebased onto the rewritten `stage-8-preferences` afterwards, since its history currently includes the original, non-rewritten commits — it has not been pushed, so this is a local-only rebase with no shared-ref risk.
6. **Collaborator impact**: anyone with a local clone of `stage-7-google` or `stage-8-preferences` (or a fork) must discard and re-fetch those branches after the force-push — their local history will diverge irreconcilably otherwise (any local commits made on top would need to be manually replayed onto the new base). Currently a single-contributor, private repository, so this is a documented risk rather than an active coordination problem — but must be checked again if that ever changes.
7. `main` is never touched by this plan, since it never contained the leaked commit.

**Not executed, by explicit decision**: the repository is private and single-contributor; the revoked credentials remaining in private history is an accepted risk for now. This decision is conditional — it must be revisited, and this plan executed, before the repository is made public or shared with anyone external.

## Google API verification and security-assessment roadmap (tracked, not a Stage 7 blocker)

`gmail.readonly` and `gmail.compose` are Google-classified **restricted scopes**. Before any real-user pilot beyond named test accounts, the following must be completed — tracked here so it is never treated as "already done" by omission:

1. Google Cloud OAuth consent screen moves from "Testing" (current Stage 7 status; up to 100 named test users, no verification required) to "In production".
2. Submit for Google app verification: privacy policy URL, limited-use disclosure for restricted-scope data, and an in-app scope-justification walkthrough (screenshots of the Connections consent flow).
3. Restricted scopes additionally require an annual third-party security assessment (Google's CASA Tier 2, or equivalent) before verification completes.
4. Until verification completes, the pilot is bounded to the ≤100 test users the "Testing" status allows (already recorded as a risk in `docs/delivery/stage-plan.md`'s risk register).

## Out-of-scope threats (recorded, revisit at Stage 11)

Multi-region availability, DDoS at scale, malicious insiders with database access, and formal GDPR DPIA sign-off (draft privacy notice arrives in Stage 10 for professional review).
