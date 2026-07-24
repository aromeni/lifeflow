# Assumptions and Decisions Log

**Status:** Stage 0 · **Date:** 2026-07-15

Per the operating protocol, no more than five genuinely architecture/scope-blocking decisions were identified. Each has a recommendation adopted as a **documented, reversible assumption** so Stage 0 could proceed without blocking on the user. Accepted outcomes are formalised in [../architecture/adr/0001-architecture.md](../architecture/adr/0001-architecture.md).

## The five blocking decisions

### BD1 — Application sign-in model

**Question:** How do users authenticate to LifeFlow itself (separate from Gmail/Calendar grants)?
**Recommendation (adopted, ADR D3):** Google Sign-In (OIDC, `openid email profile` only), with connector scopes requested incrementally later; demo mode uses a dev-seeded local session.
**Why:** target users are Gmail users; avoids operating a password store; keeps consent granular.
**Reversibility:** high — email/magic-link can be added behind the same server-side session layer.

### BD2 — Background job architecture

**Question:** Celery, Dramatiq, or arq — and when does Redis enter?
**Recommendation (adopted, ADR D2):** no queue or Redis until Stage 8; on-demand generation runs in-process first; adopt **arq** when scheduled briefs arrive.
**Why:** avoids operating infrastructure with no current requirement; arq fits the async stack and small job volumes.
**Reversibility:** high — job entry points live in `workers/` and call domain services; the runner is swappable.
**Resolved 2026-07-21:** confirmed in ADR 0004 D43, implemented in ADR 0004 D48 (Stage 8 Phase 2) — arq + Redis, optional for demo/CI, exactly as anticipated here.

### BD3 — LLM provider strategy

**Question:** Which provider first, and how hard is the abstraction boundary?
**Recommendation (adopted, ADR D4):** provider-neutral `LLMProvider` protocol; **mock provider is the default** (demo mode + all CI); Anthropic is the first real implementation.
**Why:** required by the skill's AI-layer rules; keeps every stage gate credential-free.
**Reversibility:** high by construction.

### BD4 — Hosting and data residency

**Question:** Where will production run, given a UK-based user base and GDPR constraints?
**Recommendation (adopted, ADR D8):** defer provider choice to Stage 11 (ADR 0004) with **UK/EU data residency as a binding constraint**; Docker Compose covers Stages 1–10.
**Why:** nothing before Stage 11 depends on hosting; deciding now would be speculation.
**Reversibility:** total until Stage 11.

### BD5 — Gmail ingestion window and scope set

**Question:** How much mailbox history may the MVP read, with which exact scopes?
**Recommendation (adopted, ADR D6 / threat model T20):** default window of the **last 14 days** of messages (bounded pagination, sync cursors thereafter); scopes fixed at `gmail.readonly`, `gmail.compose` (draft creation only), `calendar.readonly`, `calendar.events`.
**Why:** minimum-scope, minimum-retention principle; 14 days covers stale-follow-up detection (5+ days) with margin.
**Reversibility:** high — the window is a configuration value surfaced in the privacy screen.

## Working assumptions (reversible, not decision-blocking)

| ID | Assumption | Basis | Where recorded |
|---|---|---|---|
| A1 | Single developer + Claude Code as delivery team; GitHub for hosting/CI when a remote is created | Repo context | stage plan |
| A2 | Primary locale `en-GB`, default timezone `Europe/London`; UTC storage everywhere | Primary persona | personas, ADR |
| A3 | Repo will be initialised as a git repository at Stage 1 (it is not one today); no commit without explicit request | Skill protocol | stage plan |
| A4 | Demo dataset is authored fiction (UK-flavoured names/companies), never derived from real mail | Skill §13 | mvp-scope |
| A5 | Stale follow-up threshold defaults to 5 days; deadline-proximity boost begins at 72h | Skill §8 examples | to be tested in Stage 4 |
| A6 | Retention default: imported source items expire 30 days after last sync unless referenced by an approved action; user-configurable later | Privacy-by-design | threat model T15 |
| A7 | Proposal expiry default: 7 days after creation | Policy engine needs a bound | mvp-scope risk table |
| A8 | Priority formula starts at the skill's suggested weights (0.30 urgency, 0.25 importance, 0.20 explicit request, 0.15 deadline proximity, 0.10 relationship/context), normalised [0,1], with reason codes; tuned only via eval evidence | Skill §8 | Stage 4 |
| A9 | English-language email content is the MVP target; non-English content is surfaced but marked low confidence | Persona | Stage 4 |
| A10 | "LifeFlow Chief of Staff Suite" (directory name) is the working umbrella; product name in-app is **LifeFlow AI** | Skill mission | vision |
| A11 | Sessions are server-signed cookies (Starlette SessionMiddleware, httpOnly, SameSite=Lax, Secure in production, 8h expiry); no session table until a revocation requirement appears | Simplicity (Stage 2) | main.py, stage-02 report |
| A12 | CSRF defence is the custom-header pattern (`X-LifeFlow-CSRF: 1` required on all state-changing requests) plus SameSite=Lax — appropriate for a JSON-only API; revisit if form posts ever appear | Threat model T7 (Stage 2) | security/csrf.py |
| A13 | Tests run against a dedicated `lifeflow_test` database on the dev Postgres container, recreated each session, so development data is never touched | Testing safety (Stage 2) | tests/conftest.py |
| A14 | Demo sign-in reuses dev-login, so demo mode currently requires ENVIRONMENT=development; an anonymous demo-session path for deployed environments is deferred until a deployment exists (Stage 10/11) | Simplicity (Stage 3) | stage-03 report |
| A15 | Web↔API is cross-origin in dev (3000→8010) protected by CORS pinned to the web origin, credentialed fetch, and the custom CSRF header; demo dataset dates are day-offsets materialised against a "today" anchor in the user's timezone | Stage 3 design | main.py, connectors/synthetic.py |
| A16 | Every brief regeneration persists a new version for that briefing date; prior versions are kept indefinitely until a retention decision (revisit with T15 retention work, Stage 9) | Inspectability (Stage 5) | models.py Brief, uq_briefs_user_date_version |
| A17 | Brief "suggested actions" are advisory text derived per signal type; typed, policy-checked ActionProposals arrive in Stage 6 — nothing in a brief can execute | Safety boundary (Stage 5) | brief_composition.py |
| A18 | Optional brief prose is allow-list constrained: the model may only return exact application-authored sentences; any deviation rejects the whole output and the deterministic summary stands | Prompt-injection boundary (Stage 5) | brief_composition.py, prompts/brief_composition_v1.md |
| A19 | Proposal origin identity is the immutable `action-origin-v1` namespace + closed action type + persisted signal dedupe key; composer-version changes update only pristine proposals and never mint duplicates for the same origin | Change-aware generation (Stage 6) | proposal_composition.py, uq_action_proposals_user_origin |
| A20 | Stage 6 execution failures are final and have no retry endpoint. A future retry design must be a new explicit user action with fresh policy review; no executor retries automatically. Stage 7 extends this rule to `uncertain` outcomes, not only `failed` | Human control and duplicate prevention | action_proposal_service.py |
| A21 | Google sign-in and Google connector consent use two separate OAuth client configurations (client id/secret/redirect URI), never one client reused for both purposes | ADR 0003 D10 | google/oauth.py, config.py |
| A22 | `google_subject` (the ID token `sub` claim) is the sole identity key for Google sign-in; no automatic account linking by email. Since `users.email` is globally unique, a colliding email (e.g. a dev-login user sharing an email with a new Google sign-in) fails sign-in with a clear `email_already_registered` error rather than merging or crashing — expected not to arise in practice since dev-login is permanently environment-gated and never coexists with production sign-in | Account-takeover prevention (ADR 0003 D15) | models.py User.google_subject, auth.py |
| A23 | Calendar event creation always sends `sendUpdates=none`; no attendee is ever notified by Stage 7. The approval preview discloses this as an immutable `guest_notifications: off` field. Reversible later only via an explicit, disclosed, separately-approved decision | Undisclosed side-channel prevention (ADR 0003 D12, threat model T23) | google/calendar_client.py |
| A24 | `gmail.compose` permits sending; draft-only behaviour is enforced by the closed `ActionType` enum, a narrow allow-listed transport client, and transport-level tests — never by the scope string alone | Threat model T22 | google/gmail_client.py |
| A25 | `ActionExecution.outcome` (`pending/succeeded/failed/uncertain`) carries all Stage 7 execution-attempt complexity; `ProposalStatus` is unchanged. A `pending` row older than 120s with no `completed_at` is treated as `uncertain` on next read, not left ambiguous forever | ADR 0003 D16 | models.py, action_proposal_service.py |
| A26 | A token refresh response with no `refresh_token` field never clears the stored encrypted refresh token — only a response that actually includes a new one replaces it | ADR 0003 D18 | accounts.py |
| A27 | Execution mode/provider/account/scope is decided from the proposal's own evidence provenance (`SourceItem.source_account_id`), never from "does any capable connected account currently exist" — a synthetic-sourced proposal stays simulation permanently, a Google-sourced proposal is bound to that exact account and never substitutes a different one | ADR 0003 D29 | execution_context.py |
| A28 | `ConnectedAccount.authorisation_revision` increments on every call to `store_tokens()` (new connect, reconnect, or a materially different scope grant) and only there — never on `GoogleTokenService`'s silent access-token refresh. Since OAuth alone cannot distinguish "the same Google account re-consenting" from "a different Google account connecting" (no identity scope requested on the connector-consent flow), every reconnect is treated as a new authorisation, the safe assumption either way | ADR 0003 D30 | accounts.py |
| A29 | `GoogleSyncCursor`'s committed cursor only advances on a genuine final page; hitting a configured page bound first persists a resumable continuation instead and reports the sync as incomplete — a stale/expired continuation always falls back to a fresh bounded resync rather than skipping data | ADR 0003 D32 | google_sync_cursor.py |
| A30 | The approved account identity, `authorisation_revision`, and required scope are re-verified a second time, atomically with real-token acquisition under the account's row lock — not only once, before the durability commit that necessarily releases every lock the first check held. Every `ConnectedAccount` read (`ConnectedAccountRepository.get`/`get_by_provider`/`list`) uses `populate_existing()` so a row already loaded earlier in the same request/session can never mask a concurrent committed change, even under `expire_on_commit=False` | ADR 0003 D34 | accounts.py, repositories.py, action_executors.py |
| A31 | A Gmail draft's actual stored content is verified from an independent `drafts.get?format=raw` re-fetch, parsed via the stdlib `email` package — never from `drafts.create`'s own response, which frequently omits a parsed `payload` and produced a real false-negative `uncertain` outcome against a genuinely successful sandbox draft. Gmail's own threading decision is recorded but never compared against the requested `threadId`, since Gmail silently starts a new thread whenever Subject/References don't make the request a valid continuation | ADR 0003 D35 | google/gmail_client.py, action_executors.py |
| A32 | Proposal generation composes every eligible candidate per action type, ranked, and walks past one whose origin already maps to a terminal or dead-ended proposal (`rejected`/`executed`/`failed`/`expired`/`executing`-with-`uncertain`) rather than stopping at the first ranked signal — one *active* (`proposed`/`edited`/`approved`) proposal per action type is still the cap, but a terminal predecessor never permanently shadows a later, distinct signal | ADR 0003 D36 | proposal_composition.py, action_proposal_service.py |
| A33 | Google ID-token verification (sign-in only, never the connector-consent flow) tolerates `clock_skew_in_seconds=10`, not the `google-auth` library's default of zero — a real sign-in attempt failed every time on a 4-second clock gap between this machine and Google's token-issuance timestamp, an entirely ordinary amount of drift the library gives no tolerance for by default | ADR 0003 D37 | google/oauth.py |
| A34 | A Gmail message id returned by `history.list`/`messages.list` that 404s when fetched (a documented, expected Gmail behaviour — e.g. a draft's underlying message superseded by a later edit) is counted as `gmail_incomplete` and skipped; the sync completes normally. Any other client error resolving a message still propagates and fails the sync — the carve-out is narrow, covering only the one documented benign case, not every possible fetch failure | ADR 0003 D38 | connectors/google_email.py |
| A35 | The real-user path to a `create_calendar_event` proposal is a deterministic scheduling-intent extraction over inbound email (closed cue set + strict title/date/time/timezone/attendee parsing; nothing guessed, incomplete requests degrade to a visible low-confidence clarification signal) — a new `schedule_request` signal type, distinct from the generic `request`. Scheduling details must appear within the subject + stored preview (280 chars in demo mode; on real accounts Gmail's snippet, measured ≈200 chars — round 6b) | ADR 0003 D39 | scheduling_phrases.py, detectors.py, proposal_composition.py |
| A36 | A created Calendar event is verified from an independent `events.get` re-fetch — never from `events.insert`'s own response — comparing title, start/end **as instants** (Google normalises spellings to the calendar's offset), non-cancelled status, and attendees (only the calendar owner may appear unapproved). Any re-fetch failure or mismatch after the insert is `uncertain`, never `failed`, never retried | ADR 0003 D40 | google/calendar_client.py, action_executors.py |
| A37 | The "(proposed)"-titled calendar placeholder convention composes proposals from synthetic/demo evidence only — a real synced Google event never triggers it (it would create a near-duplicate sibling on the user's own calendar). Solo synced events excluded from "Today and upcoming" by the two-attendee meeting threshold are disclosed via the brief's `calendar_events_not_listed` notice rather than silently omitted | ADR 0003 D41 | proposal_composition.py, action_proposal_service.py, brief_composition.py |
| A38 | A message carrying the RFC 2369/8058 `List-Unsubscribe` header is bulk mail: the header name (never its value's content) is recorded at sync time and `is_bulk_email` excludes flagged mail from every detector, so promotional mail can never occupy the one active draft slot ahead of a genuine request. The one-active-proposal-per-action-type policy is deliberately unchanged | ADR 0003 D42 | google/gmail_client.py, connectors/google_email.py, normalisation.py, detectors.py |
| A39 | The scheduled brief calls the same `BriefService.generate()` the manual route uses; it never triggers a Google sync (sync stays user-triggered only, per Stage 7's `connected_accounts.py`). Due-instant calculation uses `datetime.combine(local_date, time, tzinfo=ZoneInfo(tz))` with Python's default `fold=0`, which gives the correct spring-forward/fall-back behaviour directly from PEP 495 semantics with no custom DST logic. A single per-minute arq cron dispatcher (never one cron entry per user) claims at most one `ScheduledBriefRun` per user per local date (the database `UniqueConstraint` is the final duplicate guard); a 6-hour catch-up window bounds recovery from an outage, beyond which a run is `skipped`, never backfilled | ADR 0004 D47-D50 | scheduled_briefs.py, worker_app.py, models.py, alembic/versions/0009_scheduled_briefs.py |

## Stage 6 deferred technical debt (recorded at the independent review, 2026-07-16)

| Item | Why deferred | Owner stage |
|---|---|---|
| `GET /action-proposals` (list and detail) runs the expiry sweep — a state-changing reconciliation inside GET handlers | Idempotent, time-truth only, and harmless if triggered externally; the proper home is the scheduled job runner | Stage 8 (scheduler owns expiry) |
| Unexpected (non-`FinalExecutionError`) executor exceptions roll back the whole transaction, losing the audit trail of the attempt | Acceptable while executors are simulated and side-effect-free; real external executors need a durable out-of-transaction attempt record first | Stage 7 prerequisite (before any real executor) |
| Equivalent instants expressed with different non-zero UTC offsets hash differently (UTC "Z" vs "+00:00" is normalised; "+01:00" is preserved) | Intentional: approval binds the exact representation the user was shown | Documented in `action_payloads.py`; revisit only if a real connector emits mixed offsets |
| `list_due_for_expiry` locks rows without a deterministic ORDER BY (theoretical deadlock between concurrent sweeps) | Only one sweep path exists today (request-scoped); ordering matters once a scheduler competes with requests | Stage 8 (add `ORDER BY id` with the scheduled sweep) |
| The approval UI trusts the server-supplied payload/hash pair rather than recomputing the hash of what it renders | Server-side policy re-validates the hash on approval; client-side recomputation is defence-in-depth only | Optional UI enhancement; consider with the Stage 9 trust features |

## Stage 7 deferred technical debt (recorded 2026-07-17)

| Item | Why deferred | Owner stage |
|---|---|---|
| No human-initiated reconciliation action for `uncertain` executions — they remain visible and honest, but inert | A real retry/reconciliation UX needs its own design and policy review; Stage 7 only needs to stop guessing, not resolve the guess | Stage 8/9 |
| Stale-`pending`→`uncertain` transition is computed lazily on read (mirrors the Stage 6 GET-triggered expiry sweep), not by a background scheduler | Redis/queues remain deferred to Stage 8 (ADR D2); no scheduler exists yet to own this | Stage 8 (scheduler owns it, alongside proposal expiry) |
| Connections/privacy screen is minimal (connect/disconnect/status only) | Full privacy screen, retention controls, and data deletion are already scoped to Stage 9 | Stage 9 |
| Google OAuth app verification (including the restricted-scope third-party security assessment) not started | Stage 7 develops and tests against "Testing" publishing status with named test users; verification is a pilot-readiness gate, not a Stage 7 blocker | Before general-availability pilot (see threat-model.md roadmap) |
| No browser-level (Playwright) journey through a *mocked* real-Google connect→sync→execute flow | Playwright's `webServer` starts the API as a real subprocess; intercepting its outbound Google calls would require making Google's endpoint hostnames configurable via environment overrides, a production-code change out of scope for a testability benefit `test_google_route_integration.py` already delivers by driving the identical `create_app()` composition over HTTP | Revisit only if a genuine need for browser-level coverage of this specific path emerges |
| No human-initiated reconciliation action for a proposal whose approval was invalidated by `approval_context_changed` — the user must notice the banner and re-approve manually | Same category of debt as the `uncertain`-execution reconciliation gap above; needs its own notification/reminder design | Stage 8/9 |
| A stale *continuation page token* specifically (rather than an expired historyId/syncToken) recovers via the generic `GoogleClientError` fallback, not a status code Google specifically documents for this case | Google's documented expiry contract is 404 (Gmail)/410 (Calendar) for the *whole* history/sync query, not a distinct code for an individual stale page token; the generic fallback is still safe (never skips data), just not targeted | Revisit if real sandbox testing (below) surfaces an actual distinguishing status code |

## Stage 7 independent-review remediation, round 1 (recorded 2026-07-17)

An independent review returned BLOCK on the first Stage 7 pass: `GoogleSyncService` and the Google executors existed but were never constructed by any route (every execute call silently used `SimulatedExecutorRegistry`, and no route ever called `GoogleSyncService.sync()`), `ActionProposalResponse.simulation_only` was a static default never computed from reality, and a raw transport timeout during a real Google call propagated as an unclassified exception instead of the designed `uncertain` outcome. All three blockers, plus four non-blocking findings (OIDC `nonce`, pagination-bound tests, a Calendar injection fixture, and a disconnect test that didn't actually simulate an unreachable revoke endpoint), are fixed — see ADR 0003 D25–D28 and `docs/delivery/reports/stage-07.md`'s "Independent review and remediation" section. This log entry exists so the gap and its resolution stay visible in the decision history, not just in a superseded report.

## Stage 7 independent-review remediation, round 2 (recorded 2026-07-17)

A second independent review returned BLOCK again, on the round-1 remediation itself: `resolve_execution_mode` decided the execution path from "does any capable connected account currently exist", recomputed fresh at both approval and execution time, rather than from the proposal's own evidence and a persisted approval-time snapshot — permitting a synthetic-approved proposal to silently execute as real once Google was connected, a Google-approved proposal to silently fall back to simulation once that account was disconnected, and a stale approval to survive a reconnect (including to a different Google account) undetected. Separately, `GoogleOAuthClient._parse_token_response` only classified `invalid_grant` distinctly from every other non-200 response, so a transient provider failure or a client/config rejection during a mid-execution token refresh crashed as an unhandled exception rather than the designed controlled outcome. Separately again, both connectors' page-bounded pagination loops could advance their committed cursor to a page beyond the configured bound, permanently skipping whatever lay past it.

All three are fixed — see ADR 0003 D29–D33 and `docs/delivery/reports/stage-07.md`'s "Independent review and remediation, round 2" section. A27–A29 above record the resulting assumptions. This log entry exists so the second gap and its resolution stay visible in the decision history alongside the first.

## Stage 7 focused remediation, round 3 (recorded 2026-07-17)

A focused independent review returned BLOCK on one remaining issue in the round-2 remediation: `validate_execution` re-verified the approved execution context correctly, but only *before* the durability commit (ADR 0003 D16) that deliberately releases every lock the transaction held so a slow real Gmail/Calendar call cannot block other work. The real Google token was then obtained afterwards via a bare `(user, provider)` lookup that checked only account status — never the approved `authorisation_revision` or scope — leaving a window between the commit and the real provider call in which a concurrent disconnect/reconnect or scope change went undetected and the write would proceed under a different authorisation than the one approved.

Fixed by moving the final check to be atomic with token acquisition: `GoogleTokenService.get_valid_access_token_for_execution` selects the account by both `connected_account_id` and `user_id` under `SELECT ... FOR UPDATE` and re-verifies provider/status/`authorisation_revision`/scope under that same lock, using an `ApprovedExecutionAuthorization` snapshot built only from `ActionProposal.approved_*` columns and threaded explicitly through every layer down to the token service — see ADR 0003 D34 and `docs/delivery/reports/stage-07.md`'s "Focused remediation, round 3" section. A30 above records the resulting assumption, including the `populate_existing()` correctness fix the race tests themselves surfaced as necessary (without it, this app's `expire_on_commit=False` sessions would silently mask a concurrent committed change behind a stale identity-map copy even under a genuine row lock). This log entry exists so the third gap and its resolution stay visible in the decision history alongside the first two.

## Stage 7 real sandbox-account verification, round 1 (recorded 2026-07-18)

The one item every prior round left open — real Google sandbox-account testing — was finally performed. Sign-in, Connections consent, and a real Gmail+Calendar sync all succeeded, surfacing two real defects (a Calendar all-day/timed event sort crash; a misleading combined "could not be read fully" sync count conflating by-design Gmail folder exclusion with genuine Calendar parse failures — both fixed, see `docs/delivery/reports/stage-07.md`'s "Real sandbox-account verification" section) plus one real defect in the approval-execution path itself: approving and executing a real `create_gmail_draft` proposal produced a confirmed-real draft in Gmail, but LifeFlow reported the outcome as `uncertain` rather than `succeeded` — a false negative in D17's post-create verification, not a failure of the write. `create_draft`'s own response frequently omits a parsed `message.payload`; the previous echo-check compared the approved payload against fields that were often simply absent.

Fixed by making verification independently authoritative — a dedicated `drafts.get?format=raw` re-fetch, parsed via the stdlib `email` package rather than trusted from the write's own response — see ADR 0003 D35 and `docs/delivery/reports/stage-07.md`'s "Real sandbox-account verification" section. A31 above records the resulting assumption. The provider action having genuinely succeeded, and no duplicate being created on replay, confirms the durable-execution and idempotency guarantees (D16) held correctly throughout — only LifeFlow's own verification step was wrong, and only that was fixed. A second real Gmail sandbox draft, executed end-to-end against a *fresh* proposal, remains outstanding to confirm the fix (tracked in ADR 0003's Follow-up section).

## Stage 7 real sandbox-account verification, round 2 (recorded 2026-07-18)

The attempt to close out round 1's outstanding item — a second real Gmail sandbox draft, to confirm D35's corrected verification path reports `succeeded` — surfaced a different, more fundamental defect instead: a genuinely new email appeared correctly in the latest brief, but no `create_gmail_draft` proposal was ever generated for it, while the original round-1 proposal sat untouched (correctly) in `uncertain`. Root cause: `compose_proposal_candidates` composed at most one candidate per action type per generation pass by returning the first ranked-eligible signal, full stop — the older, higher-priority email's signal always won that comparison, so the newer signal was never even composed into a candidate, regardless of the older proposal's status. This was a generation-time exclusion, not a policy, dedup, or list-endpoint defect: origin fingerprints (`sha256(action_type | signal.dedupe_key)`) were already unique per distinct signal, and `GET /action-proposals` already returned everything persisted.

Fixed by decoupling "how many candidates can exist" from "how many are considered": the composer now returns every eligible candidate per action type, ranked, and `generate_from_brief` walks that ranked list — creating or reusing the one active (`proposed`/`edited`/`approved`) proposal allowed per type, but continuing past any candidate whose origin already maps to a terminal or dead-ended proposal instead of stopping there. See ADR 0003 D36 and `docs/delivery/reports/stage-07.md`'s "Real sandbox-account verification, round 2" section. A32 above records the resulting assumption. The existing uncertain execution from round 1 was left completely unchanged and was never retried throughout — confirmed by test, not just by inspection. A live approval/execution against the newly-generated proposal, to finally confirm D35's `succeeded` path end-to-end, was attempted next (round 3, below).

## Stage 7 real sandbox-account verification, round 3 (recorded 2026-07-18)

Attempting the live confirmation round 2 left open — approving and executing the newly-generated proposal — was blocked by a third, unrelated defect: real sign-in failed on every attempt, the button appearing to flash and return to the homepage with `?auth_error=invalid_id_token`, never reaching `/connections`. Token exchange and the JWKS certs fetch both succeeded server-side; only ID-token verification failed, and its error handler logged no traceback, hiding the cause. Root cause, found after adding temporary exception logging: `google.auth.exceptions.InvalidValue: Token used too early` — a 4-second gap between the local clock and Google's token-issuance timestamp (confirmed negligible via a live Google endpoint's `Date` header), which `google.oauth2.id_token.verify_oauth2_token()`'s default zero clock-skew tolerance treated as a hard failure.

Fixed by passing `clock_skew_in_seconds=10` (a conventional tolerance) to `verify_oauth2_token()` — signature/audience/issuer verification are unaffected; only the issued-at/expiry boundary gained ±10 seconds of slack. See ADR 0003 D37. A33 above records the resulting assumption. With sign-in fixed, the proposal from round 2 was approved and executed live and reported `succeeded` (`draft_id`/`message_id`/`thread_id` all present) — finally confirming D35's corrected verification path end-to-end against the real account.

## Stage 7 real sandbox-account verification, round 4 (recorded 2026-07-18)

Confirming D35/D37 live surfaced a fourth defect: `POST /connected-accounts/google/sync` started returning `502 Bad Gateway` on every attempt. Root cause: a Gmail history entry referenced the underlying message of the very draft created during round 3's live test; fetching it 404s (Gmail's own documentation confirms a history entry can reference a message no longer retrievable — here, superseded by a later edit to the draft), and `GoogleEmailConnector._resolve_messages` had no error handling around that per-message fetch, so the 404 propagated unhandled all the way to the route, failing the entire sync over one unresolvable message.

Fixed by giving Gmail its own genuine-failure counter, parallel to Calendar's: a 404 on a single message increments a new `gmail_incomplete` count and is skipped; any other error still propagates, keeping the carve-out narrow. See ADR 0003 D38 and `docs/delivery/reports/stage-07.md`'s "Real sandbox-account verification, round 4" section. A34 above records the resulting assumption. A live "Sync now" against the real sandbox account, to confirm this fix resolves the actual failure observed, remains outstanding (tracked in ADR 0003's Follow-up section) — every other item opened by real sandbox-account testing (rounds 1–4) is closed.

## Stage 7 deep architecture and completion review (recorded 2026-07-19)

A first-principles review of the whole Stage 7 contract ("original promise → actual implementation → reachable user flow → safety guarantees → automated proof → real sandbox proof") confirmed the Gmail path end to end, but found that **real Calendar execution was unreachable by any coherent real-user flow**: the only composer route into `create_calendar_event` required an already-imported calendar event titled with "(proposed)" and carrying attendees — a demo-dataset convention (`ev-007`) that had become an accidental production dependency, and one that on a real account would have created a near-duplicate sibling of the user's own placeholder event. A controlled real scheduling email produced no signal at all, because no detector recognised scheduling prose and no code path extracted event details from email text. Sync, OAuth, the executor, and every approval/safety binding were verified sound; the gap was purely reachability — the executor existed with no road to it.

Remediated in the same session, strictly within the original Stage 7 scope (the stage-plan exit criterion explicitly includes "approves draft/**event**"): deterministic scheduling-intent detection and extraction (`schedule_request` signal, ADR 0003 D39/A35); independent `events.get` verification of created events, at parity with Gmail's D17 (D40/A36); the "(proposed)" convention gated to synthetic evidence plus a truthful brief notice for solo events excluded from "Today and upcoming" (D41/A37); a duplicate guard against events already on the synced calendar; and the demo E2E updated to D36's walk-past-terminal semantics (regeneration after executing a task proposal now legitimately surfaces the next-ranked evidenced task — the previous "exactly 3 proposals forever" assertion encoded pre-D36 behaviour and had not been re-run since). The final Stage 7 gate — a human-performed real-sandbox Calendar test from a controlled inbound scheduling email through approval, execution, and independent verification — is scripted in `stage-07-manual-checklist.md` step 6 and remains outstanding.

## Stage 7 real sandbox-account verification, round 6 (recorded 2026-07-21)

A live test of the Gmail draft path from a genuine self-sent request ("Please reply confirming …") surfaced a proposal-quality defect rather than a correctness one: the email was detected and briefed correctly, but a real Temu promotional email — whose sender local part isn't in the closed bulk list and whose "unsubscribe" text falls outside the stored 280-character preview — composed its own request signal, outranked the genuine one (frequent-sender relationship boost), and took the single active `create_gmail_draft` slot, blocking the genuine proposal until the user rejected the promo (after which the genuine proposal generated correctly, confirmed live). Fixed by marking bulk mail via the RFC-standard `List-Unsubscribe` header at sync time (ADR 0003 D42, A38 above) instead of growing blocklists or lifting the one-active-slot policy.

Verifying the fix also surfaced a latent test-rot defect: the route-level suites seeded proposals against the frozen test reference (2026-07-15) while approving/executing through the real app clock, so every seeded proposal carried a fixed absolute expiry (2026-07-22) and the suites would have begun failing wholesale the next day. Route-level (wall-clock) suites now anchor their seeding to `datetime.now(UTC)`; frozen-clock service-level suites are unchanged (the two-clock rule is documented in `tests/helpers.py`). See ADR 0003 D42 and the round-6 section of `docs/delivery/reports/stage-07.md`.

## Stage 8 Phase 1 — explicit preferences (recorded 2026-07-21)

Stage 8 opened on branch `stage-8-preferences` (from the `stage-7-complete` tag) with ADR 0004 (D43–D46): a three-phase plan (explicit preferences → scheduled brief via arq+Redis → inferred memory), a closed typed preference registry (`briefing_time`, `working_hours`, `brief_sections`; unknown keys 404, invalid values 422), the rule that `needs_attention` can never be hidden (D45), and the invariant that preferences are safety-inert — never consulted by the policy engine, executors, or approval binding (D46). Phase 1 shipped the registry API (`GET /preferences`, `PUT /preferences/{key}`, audited, explicit provenance), a Settings screen (timezone via the existing `/me`, briefing time, working hours, section choices with the D45 disclosure), and the first visible adaptation: the brief's displayed sections follow the user's choice, with `sections_disabled` recorded in brief metadata and extraction/proposal generation always running on the full composition. `User.timezone`/`locale` deliberately stay on the `User` row (already explicit and editable) — no second copy in the preference table.

## Stage 8 Phase 2 — the scheduled daily brief (recorded 2026-07-21)

Phase 2 made `briefing_time` operational (ADR 0004 D47–D50): a single per-minute arq cron dispatcher (arq+Redis, per BD2/D43) discovers explicitly opted-in users (`scheduled_briefs_enabled`, default off), resolves each one's timezone and `briefing_time` fresh every tick, and claims at most one `ScheduledBriefRun` per user per local date — the database `UniqueConstraint(user_id, local_brief_date)` is the final guard regardless of what the queue does, verified live under real concurrent races (`test_action_concurrency.py`'s pattern, applied here). The scheduled job calls the same `BriefService.generate()` the manual route uses, tagging the result `generation_trigger="scheduled"` and a real `scheduled_run_id` FK (not metadata-only) so a crashed-and-retried worker can find an already-generated brief instead of duplicating it. It never triggers Google sync — that stays user-triggered only, exactly as Stage 7 already established — and never approves or executes anything; only the ordinary brief pipeline (extraction → composition → proposal creation) runs, all landing in the same approval inbox as any other brief.

A bounded 6-hour catch-up window and a 3-attempt stale-`running` recovery policy replace indefinite hangs or silent multi-day backfills. The live end-to-end run (real Postgres, real Redis, a real `arq` worker, no mocks) is recorded in `stage-08-phase-2-manual-checklist.md`, alongside the automated coverage for everything a human can't practically wait hours to observe (the catch-up boundary, concurrent races, worker crash recovery). One genuine bug was caught by testing rather than review: the new status route initially read the process-wide `get_settings()` cache instead of the serving app's own settings, which would have made a per-instance Redis-availability check unreliable outside a single-process deployment — fixed to read `request.app.state.settings`, matching the pattern the rest of the app already uses for this exact reason.

## Credential exposure incident and repository-wide scanning gate (recorded 2026-07-21)

A real Google OAuth secret, pre-existing in `.env.example` since commit `d8a6de1` (Stage 7, unrelated to Stage 8 work), had never been caught because no scanning gate had ever actually run against that commit: the local pre-commit hook is opt-in per clone, and CI's secret-scan job triggered only on `main`/PRs, never on the direct push to `stage-7-google` that introduced it. The human user rotated/revoked both exposed secrets in Google Cloud Console, updated the local `.env`, and re-verified the full Google OIDC/connector/sync flow working end to end. The current file was redacted and that fix committed in isolation (`203f8126`). Added `scripts/check_env_example_secrets.py` (7 tests) plus a new branch-agnostic `.github/workflows/secret-scan.yml` so the same class of gap — a gate that exists but never actually runs against the ref that needed it — can't recur. The repository was made temporarily public during this remediation (for CI-log access), which revisited and superseded the original defer-the-rewrite decision: history was purged via `git filter-repo` on 2026-07-22 (`stage-7-google`, `stage-8-preferences`, `stage-8-scheduled-briefs`, and the `stage-7-complete` tag), verified clean by an independent fresh clone from `origin`. A second, unrelated false positive (`.secrets.baseline`'s own hashes tripping gitleaks' `generic-api-key` rule) was found and fixed with a `.gitleaks.toml` allowlist. Full detail, affected refs, and the executed rewrite steps are in `docs/security/threat-model.md`.

## Stage 8 Phase 2 corrections (recorded 2026-07-21)

Two issues surfaced in review before Phase 2 could be committed, both part of the scheduler contract itself (not the security fix above):

1. **DST correctness was wrong, not just under-tested.** The original claim above — that unclassified `fold=0` "lands at the first valid post-gap instant" — was checked against zoneinfo's actual 2026 transition data (Europe/London: 29 March, 25 October — this document previously and wrongly said "30 March"; the code's own tests always used the correct 29th) and found to be false: unvalidated `fold=0` on a nonexistent local time instead lands at *requested time + gap size* (02:30 BST for a configured 01:30), not the true first valid instant (02:00 BST). Replaced with `scheduled_briefs.resolve_local_schedule_instant`, which builds both PEP 495 fold candidates, round-trips each through UTC and back, and explicitly classifies the result as `valid`/`ambiguous`/`nonexistent` before resolving — verified against both a 60-minute (Europe/London) and a 30-minute (Australia/Lord_Howe) transition so the bounded gap-search never assumes a fixed offset. `compute_target_utc` is now a thin wrapper, so dispatch eligibility, catch-up, and the `next_expected_run` display all agree by construction (ADR 0004 D48, revised).
2. **Evidence freshness was implicit.** Scheduled briefs never sync Google (D47), but nothing told the user how old the evidence they're based on is. Added `GET /evidence-freshness` (per-connected-account: connected/disconnected, never-synced/synced, and a fresh/aging/stale band derived from `ConnectedAccount.last_sync_at`) and a Settings display, so "the brief uses whatever was last synced" is now a checkable fact, not just prose.

## Stage 8 Phase 3 — transparent inferred memory (recorded 2026-07-22)

Phase 3 completed Stage 8's "transparent adaptation" theme (ADR 0004 D51–D58) with one narrow, typed inferred-memory type: `preferred_email_signoff`. The original Phase 3 sketch (D43.3) named "learned priority weights" only as an example; the reconstructed, delivered contract is recorded as a requirements matrix (R1–R8) in ADR 0004. The model is strictly: *observed user-controlled behaviour → inferred candidate → visible confidence + evidence → user review → confirmed explicit preference or dismissed candidate → safe, previewed adaptation.* There is no hidden behavioural profile, no sensitive inference, and nothing is ever auto-approved or auto-executed.

- **Evidence is the user's own edited-then-approved Gmail drafts only (D53).** `memory_inference.gather_signoff_observations` reads the body of `create_gmail_draft` proposals the user deliberately edited (`user_edited_at` set) and then approved, extracts a recognised closing token via the closed-vocabulary `extract_signoff` (ignoring quoted `>` lines and contact-bearing signature lines), and stores only that short token plus a reason code — never the draft body, recipients, or subject. Nothing in inference reads `SourceItem` content, so a phrase in a *received* email can never become a preference (proven by `test_inbound_email_text_alone_creates_no_preference`).
- **Closed registry; sensitive keys fail closed (D52).** `MEMORY_REGISTRY` holds exactly one key; `PROHIBITED_MEMORY_CATEGORIES` (health, disability, race/ethnicity, religion, political opinion, sexuality, biometrics, trade-union membership, criminal matters, financial hardship, immigration status, protected characteristics, psychological diagnoses, intimate-relationship status, children — plus generic personality/mood/risk-profile) is a documented, regression-tested deny-list. There is no free-text key/value path anywhere.
- **Deterministic confidence (D54).** `confidence = evidence_strength × consistency × freshness`, each in [0,1], with a 30-day freshness half-life and `MIN_EVIDENCE = 2`; one observation can never produce a confirmable active memory. Low/Medium/High map to documented numeric bands. No LLM confidence is ever used.
- **Explicit always wins, by construction (D55/D57).** Inferred memory is *suggest-only* and is never read by the composer. Composition reads only the explicit `preferred_email_signoff` preference (default "Best"). **Confirming** a memory writes that explicit preference with normal explicit authority through the ordinary preference registry — so an inferred value literally is not in the application path until the user promotes it. Setting an explicit value supersedes any candidate; deleting the explicit preference falls back to the system default and re-surfaces the candidate, never silently re-applies the old inferred value.
- **Suggest-only adaptation, composition-only (D57).** A confirmed sign-off replaces the composer's hard-coded "Best" for *future* draft proposals; the proposal's `rationale` records "Sign-off applied from your confirmed preference." The adapted body is part of the payload and therefore of the payload hash and approval binding automatically — approval, the policy engine, execution mode, recipients, and the Gmail executor are all unchanged, and the user still previews and approves the exact draft. Existing user-edited/approved proposals are immutable; only newly composed candidates pick up the sign-off.
- **Async, recoverable inference (D56).** A qualifying approval best-effort-enqueues `recompute_user_memory(user_id)` onto the Phase 2 arq/Redis queue (user id only — never draft content). If Redis is down the approval still succeeds and the missed job self-heals, because the worker *rescans* the user's recent eligible proposals rather than trusting a single event. Recompute is idempotent (evidence deduped by `(memory_item_id, source_proposal_id)`) and cannot create duplicates under concurrency (the `(user_id, memory_key)` unique constraint is the final guard). No new scheduler or queue was introduced.
- **Deletion vs pause (D55, privacy).** `memory_inference_enabled` (default off) pauses new learning without deleting anything; `DELETE /memories[/{id}]` erases the derived item and its evidence but never touches the source proposals, Gmail, or Calendar — the Settings copy states this plainly. Account deletion cascades all memory rows.
- **`preferred_meeting_duration_minutes` deferred, not implemented (D51).** The calendar composers never present a *missing* duration for memory to fill safely — injecting one would either be inert theatre or would weaken Stage 7's fail-closed extraction, which the plan forbids. One type implemented completely demonstrates the entire lifecycle (candidate → confirm → override → dismiss → decay → delete) without a second, weaker one.

Coverage: 51 new backend tests (registry/safety, inference lifecycle, precedence, dismissal stickiness, decay, idempotency, safe sources, pause, cascade; API ownership/versions/transitions; visible adaptation with payload-hash binding; real-Redis enqueue and failure isolation) and 6 new Settings tests, all green alongside the full existing suite (529 backend / 52 frontend). The deterministic lifecycle is proven primarily by the integration suite with a controllable clock; the wired worker + API + UI path is confirmed in `stage-08-phase-3-manual-checklist.md`.

**Focused-review closure (2026-07-22).** Three lifecycle points were tightened before the Stage 8 commit. (1) **Effective expiry** — a candidate can no longer be shown as active indefinitely: `effective_confidence` continues the 30-day half-life decay from `last_evaluated_at`, `expire_stale_candidates` fires on every authenticated read (like `ActionProposalService.expire_due`) and a daily `expire_stale_memory` arq cron guarantees expiry without any user action; `memory.expired` is audited once, confirmed preferences never decay (ADR 0004 D55, effective-expiry addition). (2) **Atomic confirmation** — confirm/edit-and-confirm run in the single request transaction (ownership+version → preference write → status transition → audit; commit at the boundary, rollback on any error), proven by failure-injection, concurrency, and retry tests. (3) **Production trigger** — proven end-to-end by `test_real_approval_path_enqueues_an_identifiers_only_recompute` (edit+approve via the real routes → one identifiers-only job, nothing executed) and a full HTTP + real-worker smoke. Confidence-band cut-points (0.34 / 0.67; 0.750 → High) are now test-pinned. Total: 63 backend + 6 frontend Phase 3 tests.

**Committed-state closure (2026-07-22).** Phase 3 was committed on branch `stage-8-memory` as `466de179a7af1fe6410ee4e4f661402bec5b8925` (parent `6da388c`). Stage 8 was then reviewed as one integrated milestone against the exact committed tree — git boundary, three-phase contract, cross-phase regression, migration/database review, every verification gate, the safety-invariant matrix, documentation truthfulness, and a 16-step integrated manual smoke — and **all three phases passed the committed-state closure review with no blockers**. Stage 8 is approved for remote completion; this documentation commit records that approval, after which branch `stage-8-memory` is pushed to `origin` and, once the remote branch is green, an annotated `stage-8-complete` tag is created on this closure commit and pushed. Stage 9 (privacy, audit UX, resilience) has not begun; all remaining work belongs to Stage 9.

## Stage 9 Planning Gate — privacy & pilot-hardening architecture (recorded 2026-07-22)

The Stage 9 Planning Gate (architecture/discovery only, no code) was approved. It reconstructed the Stage 9 contract, produced a system-wide data inventory and deletion-dependency map, and ratified the policy decisions now recorded in [ADR 0005](../architecture/adr/0005-stage9-privacy-hardening.md): the five-Delivery-Phase split (Privacy Centre → deletion/retention/account-deletion → audit history → rate limiting → resilience/telemetry); **account deletion = anonymise-and-minimise** keeping only content-free tombstones (D61, resolving the `AuditEvent.user_id` CASCADE tension); **retention as validated env settings**, not a table, with provisional product defaults (D62); the derived-data deletion rules (D63); and the rate-limiting keying/trusted-proxy architecture with thresholds deferred (D64). Key facts established: `SourceItem.retention_expires_at` exists but no enforcing job yet; `AuditEvent` already emits the full `proposal.*`/`execution.*`/`account.*`/`memory.*` vocabulary (so audit history is a read projection, no new model); disconnect is already distinct from deletion.

## Stage 9 Delivery Phase 1 — Privacy & Connections Control Centre (recorded 2026-07-22)

Delivery Phase 1 shipped one consolidated, **read-only, non-destructive** surface (ADR 0005 D65). Canonical page: the existing `/connections` route expanded into the "Privacy & Connections" Control Centre (one page, reusing the existing connect/disconnect/sync routes; the Stage 7 e2e stays green because "Connections" is a substring of the new heading). One new endpoint, `GET /privacy/summary` (`lifeflow_api.privacy`), returns the per-account connection summary (status, granted scopes with human labels via `google_scopes`, last sync, freshness band reusing `evidence_freshness._freshness_band`, ever-synced, can-disconnect/can-reconnect), owner-scoped inventory counts for all twelve categories (executions counted through the proposal join, mirroring `ActionExecutionRepository`), and the retention classes with `enforced=False`. Safety by construction: the response carries no token/ciphertext, sync cursor, `authorisation_revision`, provider message/event id, proposal payload/hash, or audit metadata — proven by sentinel-leak tests; it never touches Redis (proven against an unreachable Redis) and never triggers a sync. Four data controls (disconnect / delete-imported-data / delete-learned-preferences / delete-account) are explained as distinct operations; only disconnect (existing) and the memory-controls link are actionable — imported-data and account deletion are described but have no button (they arrive in Delivery Phase 2). Retention values live in validated `config.Settings` fields (positive ints, read from app state not the cached global). 15 backend + 14 frontend tests. Enforcement, deletion, audit UI, rate limiting, and resilience remain later Delivery Phases.

## Stage 9 Delivery Phase 2 — durable deletion engine (recorded 2026-07-23)

Delivery Phase 2 ships imported-data deletion, retention enforcement, and account deletion behind **one** durable model (`DataDeletionOperation`, migration `0011`), **one** planner (`deletion_planner.apply_derived_decisions`), and **one** worker (`deletion.run_operation`), per ADR 0005 D66–D72. A previewed operation is a durable, content-free record with a snapshot cutoff (`SourceItem.created_at`, D68), captured counts, disposition (preserved/minimised/recomputed), a typed-confirmation phrase (`DELETE IMPORTED DATA` / `DELETE MY LIFEFLOW ACCOUNT`, never stored), and an expiry. Confirm requires the exact phrase (422), expected version (409 stale), and non-expired preview (409); it is idempotent, and a partial unique index guarantees at most one active operation per (user, type, scope). The worker claims atomically (conditional `UPDATE … RETURNING`), processes bounded batches committing each with a resume cursor + heartbeat, and finalises with a content-free audit tombstone; the per-minute cron drains never-enqueued pending operations (Redis-outage-safe, D70) and recovers stale ones. Derived-data rules: fully-unsupported signals/proposals deleted, mixed pruned, approved/executed minimised to tombstones, pending/uncertain executions always preserved, confirmed preferences never deleted. Account deletion keeps a terminal anonymised `users` row (`account_state='deleted'`, random `deletion_subject_id`, cleared identity — D67), preserving the content-free audit/execution tombstones `AuditEvent.user_id` CASCADE-references; `get_current_user` rejects a deleted account (session invalidation) and `require_active_account` blocks sync/brief/proposal mutations while `deletion_pending`. Retention (D72) is opt-in (`RETENTION_ENFORCEMENT_ENABLED`), bounded, uses a controllable clock, and reuses the planner. 35 backend + 6 frontend tests. At the Phase 2 boundary, audit history (Phase 3), rate limiting (Phase 4), and resilience/telemetry (Phase 5) had not begun.

**Remote completion (2026-07-23/24).** Delivery Phase 1 is remotely preserved
at `49f121a`. Delivery Phase 2 is remotely finalised at `fdb4636` on
`origin/stage-9-deletion-retention`. Delivery Phase 3 is remotely finalised at
`a50cf06` on `origin/stage-9-audit-history`. Delivery Phase 4 is implemented,
verified, and committed locally as six commits on `stage-9-rate-limiting`
from that `a50cf06` parent, awaiting remote finalisation (not pushed, not
tagged); Delivery Phase 5 has not begun. Stage 9 is not complete, has no
`stage-9-complete` tag, and has not been merged to `main`.

## Stage 9 Delivery Phase 3 — privacy-safe audit history (recorded 2026-07-24)

Delivery Phase 3 is committed locally as five commits on
`stage-9-audit-history` and awaits remote finalisation. It deliberately reuses
the existing append-only `AuditEvent` model: a closed presentation registry
(`audit_history_registry.py`, kept separate from the API module so it can be
reviewed and committed independently) maps privacy-reviewed event types to
fixed title/summary/category/tone values; unknown events remain internal and
raw actor/metadata/entity/correlation fields are never serialised. `GET
/audit-history` is owner-scoped and read-only, with closed activity/time
filters and stable `(timestamp DESC, id DESC)` keyset pagination frozen to a
first-page `as_of` boundary. Its strict, filter-bound cursor is navigation
state rather than authority. `/audit-history` is the canonical accessible
frontend and is linked from Privacy & Connections; it renders the user's
configured timezone and supports an honest empty/error state and “Load more”.
No migration, new capture model, deletion-semantic change, audit mutation
route, provider scope, rate limiter, or telemetry hardening was added.
Decisions are ratified as ADR 0005 D75–D80. Remotely finalised at `a50cf06`
on `origin/stage-9-audit-history`.

## Stage 9 Delivery Phase 4 — rate limiting (recorded 2026-07-24)

Implemented on `stage-9-rate-limiting` (base: the Phase 3 tip `a50cf06`),
enforcing the D64 architecture decided at the planning gate. A closed
registry of sixteen named token-bucket policies
(`apps/api/src/lifeflow_api/rate_limit_policy.py`) covers every
state-changing route plus the two stronger read buckets; every route not on
a short, tested exemption list (`/health`, `/ready`, `/config`, FastAPI's own
docs routes) carries exactly one policy via one reusable dependency
(`rate_limit_deps.RateLimited`). Authenticated policies key on the stable
user id; anonymous policies key on a client IP resolved via a
trusted-proxy-CIDR-gated `X-Forwarded-For` walk
(`rate_limit_ip.py`) that falls back safely on anything malformed. One atomic
Lua script (`rate_limiter.py`) performs the whole token-bucket
read-refill-consume-write cycle using Redis's own clock, so concurrent
requests can never overshoot capacity; Redis holds only an HMAC digest of the
subject, never a raw id or IP. Any Redis failure fails open (allows the
request) without touching any pre-existing database guard — execution
idempotency, approval-payload binding, deletion active-operation uniqueness,
and preview-plan fingerprint binding are all completely unmodified and stay
authoritative regardless of limiter state. The one route serving two
operation types through a single path (deletion confirmation) resolves its
policy from a side-effect-free read before charging exactly one bucket, never
two. The safe 429 contract reuses the existing `{"error": {...}}` envelope
(429 was already mapped to `"rate_limited"`) plus a bounded
`retry_after_seconds` field and a `Retry-After` header. The frontend renders
a rounded, accessible retry message on brief generation, proposal approval/
execution, and every deletion control — never as a provider failure or an
uncertain outcome, never auto-resubmitted, and never discarding typed
confirmation phrases or reviewed preview state. `RATE_LIMITING_ENABLED`
defaults to `false` (every existing test and Playwright journey is
unaffected); the new `rate-limiting.spec.ts` journeys enable it for the e2e
process with small overrides scoped to exactly the policies they exercise. No
migration was needed. Decisions are ratified as ADR 0005 D81.

**Phase 4 closure (recorded 2026-07-24).** Phase 4 is committed locally as six
commits on `stage-9-rate-limiting` from the approved parent `a50cf06` and
awaits remote finalisation — not pushed, not tagged, not merged. All 47 routes
are classified: each carries exactly one closed policy or sits on the short,
tested exemption list. Redis state is ephemeral and TTL-bounded (an abandoned
bucket always expires), holds only HMAC-pseudonymised subjects, and is
consumed through one atomic Lua token bucket; any Redis failure is an
availability-oriented fail-open, never a misleading 429, and never displaces
the database and approval guards, which remain authoritative in every case.
The immediate TCP socket peer is the sole trust anchor. Uvicorn's own
forwarded-header rewriting is explicitly disabled at every live launch site
with `--forwarded-allow-ips=""` (enforced by
`scripts/check_uvicorn_launch_safety.py` in pre-commit and CI, and regression-
tested against a real Uvicorn subprocess in
`tests/test_rate_limit_uvicorn_regression.py`), so LifeFlow's own
`TRUSTED_PROXY_CIDRS` resolver is the only place a forwarded address is ever
trusted — including in production behind a real reverse proxy. A 429 returns
only safe, bounded retry guidance. Rate-limit outcomes are operational metrics
and two safe log lines, deliberately **not** an `AuditEvent` stream, so
throttling never becomes audit noise. No migration was created and the Alembic
head remains `0011`. Final verified numbers: 716 backend tests at 92%
coverage (63 of them focused rate-limit tests), 86 frontend tests, 10
Playwright journeys passing twice consecutively, and both the deterministic
and action evaluations passing. Delivery Phase 5 has not begun, and Stage 9 is
not complete, tagged, or merged.

**Presentation completeness correction (recorded 2026-07-24, ADR 0005
D79–D80).** A follow-up review found two pure presentation-layer gaps (a
closed `action_type` and closed `reason`/`error_code` already written on every
relevant audit call but never rendered — D79) and one genuine data gap (record
counts were never written to `AuditEvent.safe_metadata_json` at all — only to
`DataDeletionOperation`'s own columns). Rendering counts required one small,
explicitly authorised, narrowly scoped addition to the already-committed
Phase 2 `deletion.py` writer — audit metadata only, no change to deletion
planning, batching, preservation, retention eligibility, account
anonymisation, or state transitions (D80). `retention.py` has never populated
`preserved_counts_json`, so `preserved_count` is correctly always absent on
retention events specifically; no writer produces a per-record `failed_count`
anywhere in the engine, so that field is always omitted. Implemented as two
further commits (`69117f7`, `b707788`), both remotely finalised in `a50cf06`.

## Open questions deliberately deferred (with owner stage)

- ~~Evaluation acceptance targets~~ — **ratified 2026-07-16 in [ADR 0002](../architecture/adr/0002-evaluation-targets.md)** after the deterministic baseline; real-model metrics still pending an Anthropic key (before the Stage 10 gate).
- Holdout + adversarial evaluation set (blind, dataset v2) — authored and run before the Stage 10 pilot gate; current golden v1 numbers are development-set results (ADR 0002, Stage 5 gate).
- Real LLM augmentation stays off by default (`LLM_EXTRACTION_ENABLED=false`) until the ADR 0002 real-provider evaluation is recorded (Stage 5 gate check).
- ~~Job runner confirmation~~ — **confirmed 2026-07-21 in ADR 0004 D43, implemented 2026-07-21 in ADR 0004 D48**: arq + Redis, live in Stage 8 Phase 2 (the scheduled brief), optional for demo/CI.
- Production hosting provider + deployment shape — a later ADR (0006) at Stage 11.
- Google OAuth app verification and security assessment — roadmap recorded in `docs/security/threat-model.md`; begins in earnest once a real pilot beyond named test users is planned.
- Entitlements/billing model — interfaces only, Stage 11; no billing implementation without explicit request.

Nothing in this log weakens the safety invariants: approval-gated side effects, prohibited high-risk actions, minimum scopes, and audit coverage are not assumptions — they are fixed requirements.
