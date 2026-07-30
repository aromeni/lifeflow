# Threat Model

**Status:** Stage 7 reviewed (v5, focused remediation round 3) · **Date:** 2026-07-17 · **Review before:** Stage 12 (packaging/deployment; renumbered 2026-07-30 — originally Stage 11, see `docs/delivery/stage-plan.md`)

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
| T21 | Rate-limit abuse / cost exhaustion (LLM or Google quota) | B2 | Bounded pagination, bounded retries, request timeouts; per-user/per-IP Redis-backed rate limiting (Stage 9 Delivery Phase 4, ADR 0005 D64/D81 — see below); cost capture per LLM call | LLM layer, `rate_limit_*` modules | 4, 9 |
| T22 | `gmail.compose` scope permits sending, not just drafting — a compromised or buggy code path could send mail even though the product never intends to | B2 | Defense in depth, not scope reliance (ADR 0003 D11/D33): closed `ActionType` enum has no send member; `GmailDraftClient` exposes only `create_draft()` against one fixed, allow-listed path; no generic request method exists; transport-level tests assert the only HTTP call ever made is `POST /gmail/v1/users/me/drafts`. The literal allow-list assertion inside the client is a cheap self-check, not itself the boundary — see D33 | `google/gmail_client.py`, `action_executors.py` | 7 |
| T23 | Undisclosed guest notification on calendar-event creation (Google's default `sendUpdates` behaviour would email attendees without the user ever approving a "send") | B4 | `CalendarEventClient.insert_event()` hard-codes `sendUpdates=none` (not caller-overridable); the approval preview carries an immutable `guest_notifications: off` field bound into the same payload hash | `google/calendar_client.py`, approval preview | 7 |
| T24 | Execution context substitution — a proposal approved under one execution path (simulation, or a specific Google account/scope) silently executing under a different one because the decision was recomputed from live "is anything connected" state instead of what the user actually approved | B4 | `execution_context.py` binds execution mode/provider/account/scope to the proposal's own evidence provenance, never to "any capable account"; the approved snapshot (`ActionProposal.approved_execution_*`, migration `0008`) is persisted at approval and re-verified twice: once pre-commit (`validate_execution`) and, atomically with token acquisition — under the same account row lock, after the durability commit (D16) that necessarily releases the pre-commit check's locks — via `GoogleTokenService.get_valid_access_token_for_execution` (ADR 0003 D34); any difference (disconnect, reconnect, scope change, a different source account) raises `approval_context_changed` before any provider call and is classified `failed`, not `uncertain` | `execution_context.py`, `action_policy.py`, `action_proposal_service.py`, `accounts.py`, `action_executors.py` | 7 |
| T25 | Silent pagination data loss — a connector's committed sync cursor advancing past pages it never actually fetched because a configured page bound was reached first, permanently skipping the unseen data on every future sync | B2 | `GoogleSyncCursor` separates the committed cursor from mid-pagination continuation state; the committed cursor only advances on a genuine final page; an incomplete attempt persists a resumable continuation and reports `incomplete`/`sync_complete=False` instead of silently succeeding; a later sync resumes from the continuation rather than skipping ahead (ADR 0003 D32) | `google_sync_cursor.py`, `connectors/google_email.py`, `connectors/google_calendar.py` | 7 |
| T26 | OAuth token-endpoint failures misclassified as an unhandled exception (generic 500) instead of the designed controlled outcome, because only `invalid_grant` was distinguished from every other non-200 response | B2 | `GoogleOAuthClient._classify_token_error` maps every non-200 response (429/5xx, `server_error`/`temporarily_unavailable`, `invalid_client`/`unauthorized_client`, `invalid_request`/`unsupported_grant_type`/`invalid_scope`, any other 4xx) to an existing typed error the executors already handle as `uncertain` or a controlled final failure — never a generic 500, never treated as final merely because the response was non-200 (ADR 0003 D31) | `google/oauth.py` | 7 |
| T27 | Scheduled generation silently widening what the product does without a human present — approving or executing a proposal, or syncing Google, on a timer | B4 | The scheduled job calls the exact same `BriefService.generate()` the manual route uses; nothing in that pipeline approves or executes anything (proposals only ever land as `proposed`, in the ordinary approval inbox). Scheduled generation never triggers Google sync — sync remains user-triggered only, per Stage 7's `connected_accounts.py` (ADR 0004 D47); a scheduled brief uses only already-synced evidence. `scheduled_briefs_enabled` is opt-in, default off (D50), and — like every other preference (D46) — is never consulted by the policy engine, executors, or approval binding | `scheduled_briefs.py`, `worker_app.py`, `brief_composition.py` | 8 |
| T28 | Untrusted deserialization via the job queue — a compromised or misconfigured Redis instance feeding a worker process pickled data (arq's default job serializer) | B2 | Job payloads carry only `run_id` (an internal UUID string, never user content); the worker overrides arq's default pickle (de)serializer with JSON (`scheduled_briefs.job_serializer`/`job_deserializer`) so no job payload is ever pickle-deserialized, verified directly against a real Redis instance (`test_scheduled_briefs_queue.py`) | `scheduled_briefs.py`, `worker_app.py` | 8 |
| T29 | Scheduler/queue outage cascading into the rest of the product (manual briefs, Google connections, approvals, execution all becoming unavailable because Redis is down) | B2 | The web API never requires Redis for any route except the scheduled-brief status read, which uses a short-timeout best-effort ping and degrades to `scheduler_available: false` rather than failing (`scheduled_brief_status.py`); manual brief generation, sync, and approval/execution have no dependency on Redis or the worker process at all | `scheduled_brief_status.py`, `main.py` | 8 |
| T30 | A real credential committed to example/template configuration (`.env.example`) going undetected because no scanning gate actually ran against the commit that introduced it | build | `scripts/check_env_example_secrets.py` — a narrow, branch-agnostic, current-tree check specifically for this file, wired into pre-commit and into `secret-scan.yml`, which (unlike `ci.yml`) triggers on every branch push, not only `main`/PRs; see "Credential exposure incident" below for the incident this closes | `scripts/check_env_example_secrets.py`, `.pre-commit-config.yaml`, `.github/workflows/secret-scan.yml` | 8 |
| T31 | Operational telemetry (structured logs, metrics) added for resilience/observability purposes becoming a second, uncontrolled channel for private data — an email address, calendar content, token, provider payload, or unbounded-cardinality identifier ending up in a log line or a metric label | B2 | Closed, hand-reviewed vocabularies only: `failure_taxonomy.py`'s `FailureCode` enum for every safe error code/message; `metrics.py`'s label sets are fixed at definition time (provider name, operation name, failure code, registered rate-limit policy code, job name) — never a user id, email, proposal id, exception message, or IP address; a full audit of every `logger.*` call site in `apps/api/src/lifeflow_api/` (Stage 9 Delivery Phase 5) found the pre-existing pattern already held everywhere — no raw content, only safe internal identifiers/codes, with `exc_info` (never an interpolated exception message) carrying traceback detail through the existing `redact()` regex backstop | `failure_taxonomy.py`, `metrics.py`, `logging_setup.py`, `correlation.py` | 9 |

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

## Stage 8 Phase 2 verification notes

- T27: `test_scheduled_generation_respects_sections_never_hides_needs_attention_and_never_executes` (`test_scheduled_briefs.py`) asserts every resulting proposal is `status=proposed` and zero `ActionExecution` rows exist after a scheduled generation; `test_status_reports_the_latest_run_and_its_linked_brief` and the live end-to-end run (`stage-08-phase-2-manual-checklist.md`) confirm the same. `test_disabled_user_is_never_dispatched` and the D47 decision in ADR 0004 cover the default-off/no-sync guarantees.
- T28: `test_job_payload_is_json_not_pickle_and_contains_only_the_run_id` (`test_scheduled_briefs_queue.py`) reads the raw bytes back from a real Redis instance, decodes them with `json.loads` (which would raise on a pickled payload), and asserts the sole argument is a bare UUID string.
- T29: `test_status_reports_scheduler_unavailable_without_breaking_the_route` constructs a real app pointed at an unreachable Redis address and asserts both that the status route still returns 200 (`scheduler_available: false`) and that an unrelated route (`/me`) is entirely unaffected.
- Troubleshooting a stuck or unresponsive scheduled brief: check `GET /scheduled-briefs/status` first (`scheduler_available`, `latest_run_status`, `latest_run_error_code`); a run stuck `running` for more than 10 minutes is recovered automatically by the next dispatcher tick (`scheduled_briefs.recover_stale_running`, bounded to 3 attempts); a `skipped` run with `error_code=missed_grace_window` means the worker was down for more than 6 hours past the configured time — generate manually in the meantime, no backfill will occur.

## Credential exposure incident (2026-07-21) and remediation

A real Google OAuth client secret (both the OIDC and connector client secrets) was found committed in plaintext in `.env.example` at commit `d8a6de1` ("feat(stage-7): complete approval-bound Google integration"), pre-existing and unrelated to Stage 8 Phase 2 work. Confirmed real by the human user. **Rotation confirmed complete** (2026-07-21): both exposed secrets were rotated/revoked in Google Cloud Console directly (outside this repository's control — this assistant had no access to do that, and did not request or view either the old or replacement value); the ignored local `.env` was updated to the new credential and the stack restarted; fresh Google OIDC sign-in, the connector consent/callback flow, and Google sync were all re-verified working; no replacement credential was added to any tracked file.

**Risk-acceptance decision (superseded 2026-07-22 — see "History purged" below)**: originally, the revoked credentials would remain in private Git history with no rewrite performed while the repository stayed private and single-contributor. That decision was explicitly revisited once the repository was made temporarily public for unrelated CI-verification purposes during this remediation, at which point the original reason to defer no longer held — the history was purged instead (below), rather than leaving a real (if revoked) credential visible in a now-public repository.

**Affected refs, pre-purge** (everywhere the leaking commit `d8a6de1` was reachable — historical record, now rewritten, see below):

- Local branches: `stage-7-google`, `stage-8-preferences`, `stage-8-scheduled-briefs`.
- Remote branches: `origin/stage-7-google`, `origin/stage-8-preferences`.
- Tags: `stage-7-complete`.
- **Not** reachable from `main` or `origin/main` — no PR was ever opened merging the leaking branch into `main`.
- The redaction fix (commit `203f8126afa0dbc2dbd22e5f7d753a0ce77d4878`, `.env.example` only) existed solely on the local `stage-8-scheduled-briefs` branch.
- A later commit, `07c568e1` (the Stage 8 Phase 1 base, present on `stage-8-preferences` and `stage-8-scheduled-briefs`), carried the same leaked file forward unchanged before the redaction.

**Why the existing scanning gates did not block this**: both scanners are technically capable of catching this value — verified directly against the original historical file content: `detect-secrets scan` flags both lines (`Base64HighEntropyString` and `Secret Keyword`), and `gitleaks git` flags both as `generic-api-key`. The gap was not detection capability but that neither gate ever actually ran against the commit:

1. The local pre-commit hook is opt-in per clone (`uvx pre-commit install`, documented as a one-time manual step in CLAUDE.md) — there is no server-side enforcement, so a commit made before that step is run locally is never checked.
2. The CI "Secret scanning" job existed (added in `94cfb41`) but its trigger was `push: branches: [main]` plus `pull_request` — identical to every other job in `ci.yml`. `d8a6de1` was pushed directly to `origin/stage-7-google` with no PR ever opened against `main`, so the workflow's checkout never included that ref, and the job simply never executed against this content. Confirmed by running `gitleaks git` locally scoped to `main`'s history alone (8 commits, no leaks) versus the branch containing the leak (12 commits, 2 real findings) — the difference is entirely which ref is scanned, not scanner behavior.
3. `.secrets.baseline` did not allow-list or otherwise suppress this secret — at commit `d8a6de1` the baseline contained no entry at all for `.env.example`, ruling out an allow-list failure.

**Regression protection added**:

- `scripts/check_env_example_secrets.py` — a narrow, dedicated, branch-agnostic check: every secret/token/password/key-shaped variable in `.env.example` must hold one of a small explicit set of known-safe placeholder values (never a heuristic like "contains the word placeholder"), plus a defense-in-depth check for known vendor secret-format prefixes (`GOCSPX-`, `AIza`, `sk-`, `ghp_`, `AKIA`, etc.) against every value regardless of variable name. Covered by 7 tests in `apps/api/tests/test_env_example_placeholders.py`, including one that asserts the real, current `.env.example` has zero findings.
- Wired into `.pre-commit-config.yaml` (new local hook, `files: ^\.env\.example$`) — current-tree scanning, runs on every commit once installed.
- Wired into a new `.github/workflows/secret-scan.yml`, split out of `ci.yml` specifically so it triggers on **every branch push**, not only `main`/PRs — this is what closes the actual gap above. It also carries forward the existing gitleaks (full-history-for-this-ref) and `detect-secrets-hook` (current-tree, against the committed baseline) steps, unchanged in behavior, merely relocated and re-triggered.
- **Current-tree vs. history scanning, explicitly**: `detect-secrets` (pre-commit and CI) and `check_env_example_secrets.py` scan the file content as it exists right now on whatever ref is checked out — they say nothing about older commits. `gitleaks git` with no `--log-opts` scans every ref present in the repository it's pointed at (verified directly: it is **not** scoped to HEAD or the checked-out branch alone — a bare `gitleaks git .` in a local clone with several branches present picks up a secret that exists only on another, uncheckedout branch). In `secret-scan.yml` this still ends up correctly scoped in practice, because `actions/checkout`'s `fetch-depth: 0` only unshallows the *one* ref that triggered the run — it does not fetch other branches as remote-tracking refs, so there's nothing else in that clone for gitleaks to find. This distinction is why the original leak survived: the CI job never even ran against a ref containing it (the trigger gap, not a scanning-scope gap).

**Full-history scan after remediation** (`gitleaks git --no-banner --redact` against the full local repository, all commits reachable from `HEAD` on `stage-8-scheduled-briefs`, run 2026-07-21): 2 genuine findings, both the original `d8a6de1` commit (`GOOGLE_OIDC_CLIENT_SECRET`, `GOOGLE_CONNECTOR_CLIENT_SECRET`); the remaining 7 reported matches are `.secrets.baseline`'s own stored SHA-256 hashes (expected noise from scanning a secrets-baseline file itself, not a live secret).

**History purged (2026-07-22)**: after confirming credential rotation and functional verification (fresh OIDC sign-in, connector consent, sync — all re-tested against the new client), and given the risk-acceptance decision above was explicitly revisited once the repository was made temporarily public, the documented rewrite plan below was executed. `git filter-repo --replace-text` ran against a fresh scratch clone, replacing both secret values (verified: only those two lines changed anywhere, confirmed by diffing the old and new commit content directly; `main` was untouched, byte-identical hash, since it never contained the leak). All three affected branches and the `stage-7-complete` tag were force-pushed with `--force-with-lease` against their exact known prior values. A completely independent fresh clone from `origin` afterward confirmed zero real findings.

**A second, unrelated false-positive was found and fixed at the same time**: even after the purge, `gitleaks` kept failing — not on the real secret, but on `.secrets.baseline`'s own SHA-256 hashes, which its `generic-api-key` rule flags as high-entropy strings regardless of the file's known-safe purpose. This would have failed the job indefinitely, independent of the leak. Fixed with a `.gitleaks.toml` allowlist (`paths = ['''\.secrets\.baseline$''']`), auto-discovered by gitleaks with no workflow change needed. Verified this doesn't weaken detection: a genuinely planted high-entropy fake secret in an unrelated file was still caught with the exclusion in place (8 findings without it, 1 — the canary — with it; 0 once the canary was removed).

**History-rewrite plan — executed 2026-07-22**:

The plan below was drafted, then actually run (superseding the original "not executed, private+single-contributor" deferral once the risk-acceptance decision was explicitly revisited — the repository was made temporarily public during this remediation, which removed the reason to defer):

1. Rotation was already confirmed complete before this ran — a pure history-hygiene operation, not an active leak response.
2. Ran in a fresh scratch clone (not the working copy), via `git filter-repo --replace-text` with a literal-match rule for each of the two known secret values, replacing them with a fixed marker string. `git filter-repo` (not `git filter-branch`) rewrote every ref present in that clone consistently in one pass — including the parts of `stage-8-scheduled-briefs` unique to it, so no separate rebase step was needed as originally anticipated.
3. `git filter-repo` automatically rewrote the annotated tag `stage-7-complete` to point at the new commit, preserving its message — no manual delete/recreate was needed.
4. Force-pushed with `--force-with-lease` (an exact expected-old-value check per ref, not bare `--force`) in order: `stage-7-google` (`d8a6de1` → `07bb328`), `stage-8-preferences` (`07c568e` → `2a14a3c`), `stage-8-scheduled-briefs` (`5cffd4c` → `ed0318c`), then the `stage-7-complete` tag. `main` was untouched (byte-identical hash before and after), since it never contained the leaked commit.
5. Verified precisely before pushing: diffed the rewritten leak-commit's `.env.example` against the original — only the two secret lines differed, everything else (comments, client IDs, structure) byte-identical; diffed the entire current working tree of `stage-8-scheduled-briefs` against the pre-rewrite working copy — identical in every tracked file. Verified again after pushing, via a completely independent fresh clone from `origin`: zero real findings.
6. **Collaborator impact**: none realised — single-contributor repository throughout. The local working copy's other branches (`stage-7-google`, `stage-8-preferences`) needed a manual `git branch -f <name> origin/<name>` afterward to match, since only the checked-out branch was auto-updated by the fetch+reset; this is exactly the same category of step a collaborator's clone would need, confirming the plan's collaborator-impact note was accurate.

## Google API verification and security-assessment roadmap (tracked, not a Stage 7 blocker)

`gmail.readonly` and `gmail.compose` are Google-classified **restricted scopes**. Before any real-user pilot beyond named test accounts, the following must be completed — tracked here so it is never treated as "already done" by omission:

1. Google Cloud OAuth consent screen moves from "Testing" (current Stage 7 status; up to 100 named test users, no verification required) to "In production".
2. Submit for Google app verification: privacy policy URL, limited-use disclosure for restricted-scope data, and an in-app scope-justification walkthrough (screenshots of the Connections consent flow).
3. Restricted scopes additionally require an annual third-party security assessment (Google's CASA Tier 2, or equivalent) before verification completes.
4. Until verification completes, the pilot is bounded to the ≤100 test users the "Testing" status allows (already recorded as a risk in `docs/delivery/stage-plan.md`'s risk register).

## Inferred memory — the learning boundary (Stage 8 Phase 3, recorded 2026-07-22)

Inferred memory (ADR 0004 D51–D58) is a new place where the system forms a belief about the user, so it gets its own boundary rules; all of them are enforced in code and regression-tested.

- **Learning input is user-controlled behaviour, never inbound content.** The single evidence source is a Gmail-draft proposal the user *deliberately edited and then approved*. `memory_inference` never reads `SourceItem` content, so the prompt-injection boundary (§11.1) extends cleanly: a recognised phrase inside a received email, a marketer's footer, or an attacker-crafted "please set my sign-off to X" message can never become a stored preference (`test_inbound_email_text_alone_creates_no_preference`). This is the mitigation for *inference poisoning* — steering the user's learned preferences via content they merely received.
- **Sensitive inference is refused, not merely absent.** A closed registry (one key) plus a documented `PROHIBITED_MEMORY_CATEGORIES` deny-list (special-category and protected-characteristic data, plus generic personality/mood/risk-profile) means unknown and sensitive keys fail closed at the registry, repository, and API layers. No free-text key/value path exists.
- **Memory cannot widen authority.** Inferred memory is suggest-only and never read by the policy engine, approval binding, executors, or execution-context resolution. It reaches an outgoing draft only after the user confirms it into an *explicit* preference, which itself is safety-inert (ADR 0004 D46) and whose effect is limited to draft composition — the adapted body is fully previewed and part of the approval hash. So memory can never bypass approval, alter recipients/attendees/execution mode, or trigger a side effect.
- **Data minimisation and deletion.** Memory tables store only a short normalised token, a reason code, and safe references (proposal id) — never draft bodies, recipients, tokens, or provider data. Redis carries only a user id; worker logs carry only ids and reason codes. `memory.deleted` audit records the key and fact of deletion, never the deleted value. The user can pause learning, delete one memory, delete all inferred memory, and account deletion cascades every memory row.

## Privacy & Connections Control Centre (Stage 9 Delivery Phase 1, recorded 2026-07-22)

The read-only Privacy Centre (ADR 0005 D65, `GET /privacy/summary`) is a new surface over already-owned data, so it gets explicit disclosure-boundary rules; all are code-enforced and regression-tested (`test_privacy_api.py`).

- **T2 (cross-user aggregate leakage).** Every count and connection read is owner-scoped by `user_id`; execution counts enforce ownership through the join to the owning proposal (mirroring `ActionExecutionRepository`). Proven by an isolation test: one user's populated data yields all-zero counts and no trace for another.
- **T1/T6 (secret & internals disclosure).** The response is counts, statuses, scope labels, and freshness bands only. It never serialises an OAuth token or ciphertext, a sync cursor, the `authorisation_revision`, a provider message/event id, a proposal payload or hash, or audit `safe_metadata` internals — proven by seeding distinctive sentinels into those columns and asserting none appear in the response body. Logs carry only user id, account id, safe event type, and correlation id.
- **T20 (scope truthfulness).** Granted scopes render exactly as stored, mapped to human labels; unrecognised scopes become a neutral "Other access"; requested-but-not-granted scopes never appear as active. Partial grants render truthfully.
- **T29 (scheduler/queue outage isolation).** The endpoint depends only on PostgreSQL and is proven to work against an unreachable Redis. Opening or refreshing the page never triggers a Google sync (ADR 0003 boundary preserved).
- **T15/T16 (retention & deletion honesty).** Delivery Phase 1 is non-destructive. Retention horizons are surfaced read-only with `enforced=False` and explicit "not switched on yet" copy, so the UI can never imply enforcement that does not exist. Actual deletion, retention enforcement, and account deletion (anonymise-and-minimise, ADR 0005 D61–D63) arrive in Delivery Phase 2; rate limiting (D64) in Delivery Phase 4.

## Durable deletion engine (Stage 9 Delivery Phase 2, recorded 2026-07-23)

The destructive engine (ADR 0005 D66–D72) introduces a new class of privileged, irreversible operations, so it gets explicit safety rules; all are code-enforced and regression-tested (`test_deletion_engine.py`, `test_privacy_deletion_api.py`, `test_deletion_queue.py`).

- **T2 (cross-user destruction).** Every preview/confirm/cancel/status is owner-scoped; a cross-user operation returns 404 without ownership leakage. The worker's cross-user recovery/scan create only owner-scoped operations. Anonymisation preserves ownership isolation for retained tombstones.
- **T12 (duplicate/concurrent destruction).** A partial unique index guarantees at most one active operation per (user, type, scope); the worker claim is an atomic conditional `UPDATE … RETURNING` (only one worker wins); re-running a completed operation is a no-op. Idempotent across crash-resume (durable cursor + fresh DB query authoritative; re-minimising yields the identical tombstone).
- **T15 (retention honesty & preservation).** Enforcement is opt-in (`RETENTION_ENFORCEMENT_ENABLED`), bounded (per-day scope key, per-tick cap), and reuses the one planner; it never deletes pending/uncertain executions or confirmed explicit preferences. The Privacy Centre flips to "enforced" only when it genuinely is.
- **T16 (deletion correctness & scope).** Imported-data deletion removes only LifeFlow's copy for one account within the snapshot boundary (`SourceItem.created_at`); it never calls a provider content API (the engine imports no Gmail/Calendar client — proven). Gmail draft-only / Calendar create-only invariants are untouched; uncertain outcomes are never auto-retried.
- **T1/T6 (content-free by construction).** Operation responses, audit metadata, worker logs, and the Redis payload (operation id only) carry no token, payload, recipient, subject, provider id, or confirmation phrase — only ids, counts, states, and safe reason codes. Retained proposal/execution/audit tombstones are minimised (payloads cleared).
- **Authorisation & session invalidation.** A typed confirmation phrase gates each user-requested operation; a `deletion_pending`/`deleted` account is blocked from sync/brief/proposal mutations (`require_active_account`), and a `deleted` account can never authenticate again (`get_current_user`), invalidating existing sessions. The same Google identity may create a genuinely new account without reviving the anonymised one.
- **T29 (queue outage).** Preview/confirm never touch Redis; a confirmed operation persists as `pending` and is drained by the per-minute cron when Redis returns — ordinary API routes stay available throughout.

## Public audit history (Stage 9 Delivery Phase 3, recorded 2026-07-23, extended 2026-07-24)

The audit-history surface is a new disclosure boundary over internal safety
records (ADR 0005 D75–D80), covered by `test_audit_history_registry.py`,
`test_audit_history.py`, `test_deletion_engine.py`'s safe-aggregate-counts
tests, the frontend component suite, and `audit-history.spec.ts`.

- **T2 (cross-user history leakage).** `GET /audit-history` authenticates with
  `CurrentUser`; every repository query filters by that exact `user_id`.
  Cursors are never authority and cannot override the owner predicate.
- **T1/T6 (private content and internals disclosure).** A closed presentation
  registry produces fixed text. The API schema has no raw event type, raw
  actor, entity id, correlation id, provider id, payload, or value field.
  Three narrow, independently re-validated typed details were added on top of
  the fixed text (D79–D80): a closed 3-value `action_type`, a closed
  `reason` drawn only from hand-written safe code vocabularies, and two flat
  bounded non-negative `deleted_count`/`preserved_count` integers aggregated
  from durable per-category totals — never the raw metadata value, the raw
  per-category JSON, an id, or a scope descriptor. Each closed lookup function
  omits (never guesses or echoes) anything absent, wrong-typed, or
  unregistered. Unknown event types are excluded at query time. Sentinel tests
  cover raw metadata, malformed/excessive/negative/boolean/string/float
  counts, unknown metadata keys, and another owner's records.
- **T18 (audit integrity).** Phase 3 adds one read method and no mutation or
  deletion method/route. The append-only capture path and deletion tombstone
  rules are unchanged; a repository surface test pins that contract.
- **Pagination abuse and consistency.** `limit` is closed to 1–50; cursor input
  is non-empty and at most 1024 characters; strict version/filter/type
  validation returns 422. `(timestamp DESC, id DESC)` keysets plus a frozen
  `as_of` window prevent duplicate/shifted pages under concurrent inserts.
- **Deferred controls remain deferred.** Phase 3 introduces no rate limiter,
  trusted-proxy behaviour, telemetry, log expansion, or provider scope. The
  rate limiter and trusted-proxy behaviour ship in Delivery Phase 4 below;
  telemetry/log expansion remain Delivery Phase 5.

## Rate limiting (Stage 9 Delivery Phase 4, recorded 2026-07-24)

Closes T21 (see the updated table row above). Covered by
`test_rate_limit_policy.py`, `test_rate_limit_ip.py`, `test_rate_limiter.py`
(real Redis), `test_rate_limiting_api.py` (real Postgres + Redis, full route
table), `test_rate_limit_uvicorn_regression.py` (a real Uvicorn subprocess,
not `ASGITransport`), the frontend component/page suites, and
`e2e/rate-limiting.spec.ts` (real API, worker, PostgreSQL, and Redis).

- **T21 (abuse/cost exhaustion).** Every state-changing route carries a
  closed rate-limit policy or an explicit, tested exemption
  (`/health`, `/ready`, `/config`, FastAPI's own docs routes). Authenticated
  policies key on the stable internal user id; anonymous policies key on a
  securely resolved client IP that never trusts a forwarded header unless the
  immediate peer is itself an explicitly configured trusted proxy. A single
  atomic Lua script performs the whole token-bucket read-refill-consume-write
  cycle, so concurrent requests against one bucket can never overshoot
  capacity.
- **T1/T6 (secret and subject disclosure).** Redis holds only a versioned
  namespace, a registered policy code, and an HMAC digest of the subject —
  never a raw user id, IP address, or path parameter. The 429 response and
  server logs carry only the policy code, allow/block result, and a bounded
  retry-after value — never the digest, the raw subject, the forwarded
  header, or request body content.
- **T2 (cross-user/hidden-parameter bypass).** A subject is derived solely
  from the authenticated user id or resolved IP, never from a path parameter
  — proven by a test that two different proposal/account/operation ids for
  the same user share one bucket, so a hidden identifier can never grant a
  fresh budget.
- **Fail-open, and why that is safe.** Redis unavailability, a timeout, or an
  unexpected reply allows the request rather than returning a misleading 429
  — a rate limiter is defence-in-depth, not the source of truth for
  correctness. Every database-level guard that existed before this phase
  (execution idempotency, approval-payload binding, deletion active-operation
  uniqueness, preview-plan fingerprint binding) is completely unmodified and
  stays authoritative regardless of the limiter's state; tests prove Redis
  failure creates no duplicate execution or deletion operation.
- **Layered without double-charging.** Each route declares exactly one
  policy via one reusable dependency, evaluated once at route-declaration
  time against a closed registry (an unregistered code fails at import time).
  The sole exception, the shared deletion-confirmation route, resolves which
  of two policies applies from a side-effect-free read of the operation's
  type before charging exactly one of them — never both, and never zero.
- **Idempotency is unaffected.** Rate limiting only gates whether a request
  proceeds to the unchanged database logic; a blocked replay attempt cannot
  duplicate a record because nothing runs, and an allowed replay still hits
  the pre-existing idempotency guard, which returns the original result
  unchanged.
- **No migration.** Rate-limit state lives entirely in Redis plus validated
  environment configuration (`RATE_LIMITING_ENABLED`, `RATE_LIMIT_KEY_SECRET`,
  `RATE_LIMIT_POLICY_OVERRIDES_JSON`, `TRUSTED_PROXY_CIDRS`, reused from
  Delivery Phase 1) — no new table, and no per-user configurable limits.
- **Deferred controls remain deferred.** Phase 4 introduces no CAPTCHA,
  account suspension, IP deny lists, or telemetry/log expansion beyond the
  limiter's own safe policy-code/allow-block instrumentation. Those, and any
  broader outage-resilience hardening, remain Delivery Phase 5.
- **Uvicorn's own header trust is not the security boundary (found via
  manual smoke test, fixed, regression-tested).** Uvicorn's
  `--proxy-headers`/`--forwarded-allow-ips` machinery runs ahead of this
  application and, by default, trusts `X-Forwarded-For` from any loopback
  peer — rewriting `request.client` before `rate_limit_ip.py`'s own
  `TRUSTED_PROXY_CIDRS` check ever runs, which let a spoofed header bypass an
  empty (default-deny) allowlist during the required manual smoke test. No
  automated test caught this before the smoke test, because
  `httpx.ASGITransport` (used everywhere else in this suite) never runs
  Uvicorn's header middleware at all. Fixed at every launch site with
  `--forwarded-allow-ips=""` (ADR 0005 D81); enforced going forward by
  `scripts/check_uvicorn_launch_safety.py` (pre-commit and `secret-scan.yml`)
  and proven end-to-end by `test_rate_limit_uvicorn_regression.py`, which
  drives a real Uvicorn subprocess over a real socket. A production
  deployment behind a real reverse proxy must keep `--forwarded-allow-ips=""`
  and configure `TRUSTED_PROXY_CIDRS` to the proxy's real address instead —
  Uvicorn's independent forwarded-header trust must never be relied on as
  the application's security boundary.

## Outage resilience and privacy-safe telemetry (Stage 9 Delivery Phase 5, recorded 2026-07-28, converged 2026-07-29)

Closes T31 (see the updated table row above) and extends T29's Redis-outage
posture to a documented, closed-taxonomy failure model across Google,
Redis, and PostgreSQL. Covered by `test_failure_taxonomy.py`, `test_timeouts.py`,
`test_retry.py`, `test_execution_recovery_sweep.py`,
`test_scheduled_briefs_enqueue_resilience.py`,
`test_deletion_engine_enqueue_resilience.py`, `test_ready.py`,
`test_correlation.py`, `test_metrics.py`, `test_e2e_test_controls.py`,
updated `test_google_executors.py`/`test_google_route_integration.py`/
`test_google_gmail_client.py`/`test_google_calendar_client.py`/
`test_google_oauth.py`/`test_worker_app.py`, the frontend `connections` page
suite, four real-stack Playwright journeys
(`apps/web/e2e-resilience/`, run twice consecutively), and a live manual
smoke test against the real Docker stack (see the Phase 5 completion
report).

- **T31 (telemetry privacy leak).** Every new operational-observability
  surface (`failure_taxonomy.py`, `metrics.py`, `correlation.py`'s worker
  extension) uses a small, fixed, hand-reviewed vocabulary — never
  user-supplied or provider-supplied content. `test_metrics.py` asserts each
  metric's label-name set directly, as a regression guard against a future
  change accidentally widening a label to something unbounded.
- **Write safety is unchanged by retries.** `retry.py::retry_read` is
  structurally incapable of retrying a write: it is applied only at Gmail/
  Calendar read call sites and the OAuth refresh call, never at
  `create_draft`/`insert_event`. Two dedicated tests count actual transport
  calls (not just observed outcomes) to prove a write is attempted exactly
  once regardless of the failure classification.
- **A local timeout is never mistaken for "no request was sent."** Every
  Google timeout — connect, read, or the write path's longer budget — is
  classified identically to a raw connection error (`GoogleTransientError`
  → `uncertain`), never surfaced as a final failure and never silently
  treated as success.
- **T29 extended: Redis outage reporting is now explicit and non-blocking.**
  `GET /ready` best-effort pings Redis and reports `degraded_dependencies:
  ["redis"]` without ever returning `503` for it — proven live (Redis
  stopped/started against the real Docker Compose service, `/ready` observed
  at each step) and by `test_ready.py`'s equivalent automated case.
  PostgreSQL unavailability, by contrast, does return `503` (also proven
  live) — the API genuinely cannot serve its core functions without it,
  unlike Redis.
- **No new AuditEvent stream.** Every mechanism in this phase (stale-
  execution recovery, enqueue-failure handling, metrics, correlation ids)
  writes only to existing safe channels (structured logs, Prometheus
  counters, or — for the execution-recovery sweep — the same
  `execution.uncertain` audit event `execute()`'s own re-entry guard already
  produces). No new audit event type was introduced.
- **No new database guard was touched.** The stale-pending-execution sweep,
  the Redis-enqueue hardening, and the timeout/retry changes are additive
  observability and recovery around existing durable-state transitions —
  `ActionExecution`'s pending→uncertain transition, `DataDeletionOperation`'s
  state machine, and `ScheduledBriefRun`'s status column are exercised
  through their pre-existing, unmodified write paths.
- **Circuit breaker: evaluated, not built (see ADR 0005 D85).** Recorded
  here because a circuit breaker is itself a common source of new privacy/
  availability risk (shared state that could leak across users, or fail
  closed for everyone on one user's account-specific problem) — the decision
  not to add one avoids that risk entirely rather than mitigating it.
- **Test-only fake-provider infrastructure cannot reach production (ADR 0005
  D92).** `lifeflow_api/testing/fake_google_server.py` is a separate ASGI
  app, never imported by `main.py`, that refuses to start without
  `LIFEFLOW_E2E_FAKE_GOOGLE=1`. The real API only ever talks to it via
  `google_api_origin_override`, itself inert unless
  `e2e_test_controls_enabled=true` — and `create_app` refuses to start
  (`RuntimeError`) if that flag is ever `true` with
  `environment=production`, proven by
  `test_e2e_test_controls_enabled_refuses_to_start_in_production`. The fake
  server never accepts or validates a real bearer token and never makes an
  outbound call to a real Google host — it is a pure in-memory stub. Its own
  `/__control__/*` routes accept only a closed `Scenario` enum and a closed
  operation-name set (422 on anything else), and expose only synthetic
  object/call counts, never content.

## Out-of-scope threats (recorded, revisit at Stage 12)

Multi-region availability, DDoS at scale, malicious insiders with database access, and formal GDPR DPIA sign-off (draft privacy notice arrives in Stage 11 for professional review). (Renumbered 2026-07-30 — originally Stage 11/Stage 10 respectively; see `docs/delivery/stage-plan.md`.)
