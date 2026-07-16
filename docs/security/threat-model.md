# Threat Model

**Status:** Stage 0 draft (v1) · **Date:** 2026-07-15 · **Review before:** Stage 7 (real OAuth) and Stage 11 (deployment)

Scope: the MVP described in [../product/mvp-scope.md](../product/mvp-scope.md), with components and trust boundaries from [../architecture/system-context.md](../architecture/system-context.md). This document exists **before** any OAuth implementation, as required.

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
| T11 | Insecure OAuth redirects / state forgery | B2 | Exact-match registered redirect URIs; `state` validation; PKCE; tests for tampered state and redirect | Google OAuth flow | 7 |
| T12 | Replay / duplicate execution (double-click, retries, job re-runs) | B4 | Idempotency key per execution; unique constraint; duplicate-execution integration tests; executed payload must hash-match approved payload | ActionExecution, policy engine | 6 |
| T13 | Approval bypass via payload mutation after approval | B4 | Approval binds to payload hash; any edit invalidates approval; policy engine re-verifies at execution time | Proposal state machine | 6 |
| T14 | Dependency compromise | build | Lockfiles (uv, pnpm); CI dependency audit + secret scanning; minimal dependency policy (ADR D9) | CI pipeline | 1 |
| T15 | Excessive data retention | data | Constrained ingestion window; `retention_expires_at` on SourceItem; retention jobs (idempotent); documented policy in privacy screen | Retention jobs, privacy UI | 3, 9 |
| T16 | Missing disconnect/deletion | data | Disconnect stops syncs and attempts token revocation; delete removes/anonymises imported + derived data; verified by integration tests | Connections service | 9 |
| T17 | Model-provider data exposure | B2 | Redact/minimise before LLM calls; only necessary fields sent; provider-neutral layer allows policy per provider; demo/CI never call real providers; document provider data-use terms before pilot | LLM layer | 4, 10 |
| T18 | Audit log tampering or secret leakage into audit | integrity | Append-only writes (no update/delete paths); `safe_metadata_json` schema excludes secrets; redaction tests | AuditEvent | 2 |
| T19 | Session hijack / weak app auth | B1 | Google Sign-In (OIDC) with server-side sessions; secure, httpOnly, same-site cookies; session expiry; auth security tests | Session layer | 2 |
| T20 | Scope creep / silent broadening of Google scopes | B2 | Scopes declared in one config constant; UI shows granted scopes; incremental consent; test asserts requested scopes match documented set | Google adapter, Connections UI | 7 |
| T21 | Rate-limit abuse / cost exhaustion (LLM or Google quota) | B2 | Bounded pagination, bounded retries, request timeouts; per-user rate limiting (Stage 9); cost capture per LLM call | LLM layer, API middleware | 4, 9 |

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

## Out-of-scope threats (recorded, revisit at Stage 11)

Multi-region availability, DDoS at scale, malicious insiders with database access, and formal GDPR DPIA sign-off (draft privacy notice arrives in Stage 10 for professional review).
