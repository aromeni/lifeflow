# Stage 3 Completion Report

**Date:** 2026-07-15 · **Approved:** pending

## Outcome

Demo mode delivers the first vertical slice with zero external credentials: a wholly fictional UK dataset (24 emails, 12 calendar events, all `.example` domains) flows through the real connector interfaces, deterministic normalisation, and idempotent ingestion into PostgreSQL, and surfaces on a Today dashboard shell with onboarding — started with one command (`./scripts/demo.sh`). The exact same pipeline will carry real Google data at Stage 7 by swapping adapters. No signal extraction, priority scoring, or brief intelligence was built (explicitly out of this stage's scope).

## Implemented

- **Connector contracts** (`connectors/interfaces.py`): `EmailConnector`/`CalendarConnector`/`TaskConnector` protocols with vendor-neutral frozen DTOs; all datetimes timezone-aware; deterministic ordering; content marked untrusted (T3).
- **Synthetic adapters** (`connectors/synthetic.py`) over the dataset (`demo/data/*.json`), materialising day-offsets against a "today" anchor in Europe/London. Dataset covers every skill §13 scenario: explicit requests, near deadline, overdue follow-up (sent, unanswered 6 days), workshop/dentist calendar conflict, newsletter, prompt-injection email, ambiguous request, and material for the later draft/event proposals.
- **Normalisation** (`normalisation.py`): pure functions DTO→SourceItem, UTC storage, sorted canonical metadata, SHA-256 content fingerprints.
- **Ingestion** (`ingestion.py` + `SourceItemRepository`): upsert on (user, type, external_id) — new→imported, unchanged→skipped, changed→updated in place; never deletes; sets 30-day retention (A6); updates `last_sync_at`; audits `sync.completed` with counts.
- **API**: `POST /demo/start` (creates the synthetic ConnectedAccount, imports the 14-day-past/30-day-future window), `GET /source-items` with type/time filters; CORS pinned to the web origin with credentials + CSRF header.
- **Contracts package**: `packages/contracts` now real — `scripts/generate-contracts.sh` exports the OpenAPI schema and generates `index.d.ts` (openapi-typescript); web consumes only these types.
- **Web**: landing page with Try-demo path and privacy summary; `/onboarding` (timezone + brief sections, marks onboarding complete); `/today` shell (Today & upcoming, Recent messages, refresh, status line, honest "intelligence arrives later" notice); `/debug/source-items` raw developer table; `lib/api.ts` client (credentials, CSRF header, shared error shape).
- **Pre-stage hardening** (user request): ownership tests now parametrised over all 7 user-owned tables (structural FK checks), executions-owned-via-proposal check, and a meta-test forcing every future repository to bind `user_id`.

## Architecture decisions

No new ADRs; D6 implemented as designed. New reversible assumptions: A14 (demo sign-in reuses dev-login → demo requires development environment until a deployed demo-session path exists), A15 (cross-origin dev topology with pinned CORS; day-offset dataset anchoring).

## Tests and evidence

| Check | Result | Evidence |
|---|---|---|
| Backend tests | PASS | `uv run pytest` — **75 passed** (was 42): connector contracts, dataset scenario coverage, determinism, DST boundary, ingestion idempotency, demo API, strengthened ownership |
| Synthetic connectors satisfy contracts | PASS | `isinstance` against runtime-checkable protocols + behaviour tests |
| Normalisation deterministic | PASS | repeated runs byte-identical; fingerprints stable; changed content changes fingerprint |
| Duplicate imports don't duplicate records | PASS | re-import: 0 imported / 36 skipped, row count unchanged (test + live curl) |
| Timezones correct around DST | PASS | 2026-03-28/29 Europe/London boundary test: same wall clock, UTC+0 vs UTC+1 |
| Demo starts with one command | PASS | `./scripts/demo.sh` (db + migrations + API + web) |
| Frontend tests | PASS | 8 passing (api client, SourceItemList incl. BST rendering, landing page) |
| Type checking / lint / format | PASS | mypy strict 28 files; ruff; ESLint; Prettier — all clean |
| Build | PASS | `pnpm web:build` compiled |
| Pre-commit + secret scan | PASS | all 9 hooks; detect-secrets baseline 0 findings |
| Coverage | 93% backend | metrics dashboard |

## Manual verification

Live end-to-end with curl and the dev servers: dev-login → `POST /demo/start` → `{imported: 36}` → second run `{skipped: 36}` → 24 emails + 12 events listed with filters → all five web routes (/,` /onboarding`, `/today`, `/debug/source-items`, `/health`) serving 200 with the Try-demo button present. Audit trail shows `demo.started` and `sync.completed`.

## Known limitations

Demo requires the development environment (A14); the Today page is deliberately a shell — no prioritisation or "needs attention" logic yet (Stage 4–5); Playwright E2E deferred to Stage 5 when the brief flow exists; contracts freshness isn't CI-enforced yet (regeneration is scripted + documented); the web app renders only titles/snippets, never full bodies.

## Recommended commit message

`feat(demo): synthetic connectors, deterministic ingestion, fictional UK dataset, demo onboarding and Today shell`

## Gate

Stage 3 is complete. Stop here and wait for explicit approval to begin Stage 4.
