# MVP Scope

**Status:** Stage 0 draft · **Date:** 2026-07-15

Companion documents: [vision.md](vision.md) · [user-journeys.md](user-journeys.md) · [../architecture/system-context.md](../architecture/system-context.md) · [../delivery/stage-plan.md](../delivery/stage-plan.md)

## In scope for the MVP

- Google OAuth authentication.
- Gmail read access for a constrained recent window (default assumption: last 14 days, bounded pagination — tunable, recorded in [../delivery/assumptions-and-decisions.md](../delivery/assumptions-and-decisions.md)).
- Gmail **draft creation** after approval (never sending).
- Google Calendar read access.
- Google Calendar **event creation** after approval.
- Internal tasks created by the agent or user.
- Daily brief generation on demand; optional scheduled daily brief job once on-demand is stable.
- Signal extraction: direct requests; promises/commitments; dates and deadlines; meetings; unanswered follow-ups; possible scheduling conflicts; high-priority messages based on transparent rules.
- Explainable hybrid priority scoring with reason codes.
- Approval queue with edit / approve / reject and payload previews.
- Deterministic action policy engine and risk levels.
- Append-only audit/event log.
- User preferences and lightweight memory (explicit first; inferred only with provenance, confidence, and user control).
- Demo mode with a wholly fictional synthetic dataset, runnable without Google or Anthropic credentials.
- Automated tests (unit, integration, contract, E2E), evaluation golden dataset, and developer documentation.

## Explicitly out of scope for the MVP (roadmap items, not hidden features)

- WhatsApp, Slack, Microsoft 365, banking, health, travel booking, shopping, or social-media connectors.
- Automatic sending of email or any side effect without user review.
- Autonomous purchases or financial transactions.
- Medical, legal, or financial decision-making.
- Voice interfaces; native mobile apps.
- Multi-user family or team workspaces.
- Browser automation against arbitrary websites; browsing links or opening attachments from ingested content.
- Vector databases unless a measured requirement justifies one.
- Multi-agent orchestration where ordinary functions and services suffice.
- Fine-tuning.
- Continuous surveillance or unrestricted mailbox ingestion.
- Full billing (entitlement interfaces only, defined in Stage 12 — renumbered 2026-07-30, originally Stage 11; see `docs/delivery/stage-plan.md`).

## Prohibited in the MVP (hard safety boundary)

| Risk | Example | MVP behaviour |
|---|---|---|
| Low | Create internal task | Approval required |
| Medium | Create calendar event | Approval required + payload preview |
| Medium | Create Gmail draft | Approval required + recipient/body preview |
| High | Send email, delete event, purchase | **Prohibited — no code path exists** |

## Measurable success criteria

Safety and integrity criteria are absolute; quality targets are initial and will be confirmed in a dedicated ADR after the deterministic baseline exists (Stage 4), per the evaluation framework.

### Safety and integrity (must be 100%/zero — verified by tests)

| ID | Criterion | Verified by |
|---|---|---|
| S1 | 0 prohibited actions executed, ever | Policy engine tests, E2E, eval suite |
| S2 | 100% of side-effecting actions require explicit approval of the exact payload | State-machine + policy tests, E2E (J4) |
| S3 | 0 duplicate external actions under retry tests | Idempotency integration tests (J4) |
| S4 | 100% source attribution for surfaced actionable items | Brief generation tests (J3) |
| S5 | Prompt-injection fixtures never trigger tools or alter policy | Adversarial fixtures + E2E (J7) |
| S6 | Cross-user data access attempts fail | Ownership/isolation tests |
| S7 | No tokens, email bodies, or private event descriptions in logs | Redaction tests + log review |
| S8 | Disconnect and deletion controls work | Integration tests (J6) |

### Quality (initial targets, ratified in Stage 4 ADR)

| ID | Criterion | Initial target |
|---|---|---|
| Q1 | Precision on actionable signals | ≥ 0.85 |
| Q2 | Recall on explicit requests and deadlines | ≥ 0.80 |
| Q3 | Deadline extraction accuracy | Reported; target set with baseline |
| Q4 | Duplicate signal rate | Reported; target set with baseline |
| Q5 | Priority-band agreement with golden labels | Reported; target set with baseline |
| Q6 | Brief usefulness (small human rubric on demo dataset) | "Understandable in < 2 minutes" (J3) |
| Q7 | Demo user completes brief → approval → audit loop unaided | E2E demo path passes |

### Engineering health

| ID | Criterion |
|---|---|
| E1 | A new developer can run the stack from a clean clone using documented commands |
| E2 | Demo mode works with no external credentials |
| E3 | Formatter, linter, type checks, tests, and build pass in CI at every stage gate |
| E4 | Every stage ends with the completion report and explicit human approval |

## Feature → journey → acceptance criterion traceability

Journey IDs and AC IDs are defined in [user-journeys.md](user-journeys.md).

| MVP feature | Journey(s) | Acceptance criteria | Stage |
|---|---|---|---|
| Demo mode + synthetic dataset | J1 | AC-J1.1–J1.3 | 3 |
| Google OAuth connect | J2 | AC-J2.1–J2.3 | 7 |
| Gmail read (recent window) | J2, J3 | AC-J2.1, AC-J3.1 | 7 |
| Calendar read | J2, J3 | AC-J2.1, AC-J3.1 | 7 |
| Source normalisation | J1, J3 | AC-J3.1, AC-J3.3 | 3 |
| Signal extraction (requests, commitments, deadlines, meetings, follow-ups, conflicts) | J3 | AC-J3.1–J3.3, Q1–Q5 | 4 |
| Priority scoring + reason codes | J3, J8 | AC-J3.3, AC-J8.1–J8.2 | 4 |
| Daily brief (on demand) | J3 | AC-J3.1–J3.4, Q6 | 5 |
| Scheduled brief | J8 | AC-J8.4 | 8 |
| Action proposals (task, Gmail draft, calendar event) | J4, J5 | AC-J4.1–J4.4, AC-J5.1–J5.3 | 6 |
| Approval inbox with edit | J4, J5 | AC-J4.1–J4.2, S2 | 6 |
| Policy engine + risk levels | J4, J5, J7 | S1–S3, AC-J7.1–J7.2 | 6 |
| Gmail draft creation (real) | J4 | AC-J4.3–J4.4 | 7 |
| Calendar event creation (real) | J4, J5 | S1–S3 | 7 |
| Internal tasks | J4 | S2 | 6 |
| Audit log + history UI | J4–J7 | AC-J5.3, AC-J6.3, S7 | 2, 9 |
| Preferences + lightweight memory | J8 | AC-J8.1–J8.3 | 8 |
| Connections & privacy screen | J2, J6 | AC-J6.1–J6.3, S8 | 7, 9 |
| Disconnect + data deletion | J6 | AC-J6.1–J6.2, S8 | 9 |
| Prompt-injection resistance | J7 | AC-J7.1–J7.3, S5 | 4, 6 |
| Token encryption at rest | J2, J6 | S7, threat model T1 | 2 |
| Evaluation golden dataset | — (quality harness) | Q1–Q6 | 4, 10 |

Every MVP feature above maps to at least one user journey and at least one acceptance criterion, satisfying the Stage 0 check.
