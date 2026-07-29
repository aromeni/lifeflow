# Provider (Google) Failure Runbook

Stage 9 Delivery Phase 5. What each Google-related failure code means, and
what — if anything — an operator should do.

## Closed failure codes (`failure_taxonomy.FailureCode`)

| Code | Meaning | Auto-recovery | Operator action |
|---|---|---|---|
| `authentication_expired` | The access token was rejected; the app refreshes and retries once internally | Yes, transparently, per request | None, unless it recurs for the same account — see `authorisation_revoked` |
| `authorisation_revoked` | The refresh token itself was rejected (`InvalidGrantError`) — the user revoked access, or Google expired it | No — the account is moved to `AccountStatus.revoked` | None from an operator; the user must reconnect via the Connections screen |
| `provider_transient_error` | Timeout, connection error, 429, or 5xx from Gmail/Calendar | Reads: yes, bounded retry with backoff (`retry.py`, max 3 attempts, ~20s budget). Writes: no — becomes a durable `uncertain` execution | None if isolated; if sustained (rising `lifeflow_provider_requests_total{outcome="transient_error"}`), check Google's own status page |
| `provider_permanent_error` | A 4xx (other than 401/403) — a genuinely bad request | No, and never retried | Usually a bug (payload construction) or a scope issue — check application logs for the specific route, never the raw Google response body (not logged, by design) |
| `uncertain_external_outcome` | A write (`create_draft`/`insert_event`) could not be confirmed to have succeeded or failed | No — permanently uncertain until a human checks directly with the provider | Never auto-retry. The UI already tells the user this; an operator does not need to intervene unless asked to help the user verify manually |

## Where to look

```bash
curl -s http://localhost:8010/metrics | grep lifeflow_provider
```

- `lifeflow_provider_requests_total{provider="gmail"|"calendar", operation=..., outcome=...}`
  — request counts by outcome. `operation` is currently populated for
  `create_draft`, `get_draft`, `insert_event`, `get_event` only (the bulk
  Gmail/Calendar ingestion read path is not yet instrumented — a known,
  documented Phase 5 scope limitation, see the Phase 5 completion report).
- `lifeflow_provider_request_duration_seconds{provider=..., operation=...}`
  — latency histogram for the same instrumented operations.
- `lifeflow_uncertain_outcomes_total` — defined but not yet wired at every
  uncertain-outcome site in this pass; do not treat its absence as proof no
  uncertain outcomes occurred — check `ActionExecution.outcome = 'uncertain'`
  rows directly if you need an authoritative count.

## Manual verification when a user reports "my email/event never showed up"

1. Ask for (or find via correlation id) the proposal id.
2. Check its execution outcome:
   - `succeeded` → it happened; the payload is on record (`executed_payload_json`).
   - `failed` → it did not happen; safe to tell the user so.
   - `uncertain` → **check directly in Gmail/Calendar** (search by subject/
     time for a draft, or the calendar for an event at the approved time).
     Only after that manual check should anyone tell the user what actually
     happened — the product's own state is honestly "don't know," not
     "probably fine."
3. Never re-approve or re-execute the same proposal to "try again" — this
   product has no mechanism to safely retry a write with an unknown outcome,
   by design (duplicate side effects are the exact risk this avoids).

## Timeout tuning (if genuinely needed)

Central, validated settings (`apps/api/src/lifeflow_api/timeouts.py`,
`config.py`) — never edit a call site directly:

- `GOOGLE_CONNECT_TIMEOUT_SECONDS` (default 5.0)
- `GOOGLE_READ_TIMEOUT_SECONDS` (default 10.0)
- `GOOGLE_WRITE_TIMEOUT_SECONDS` (default 20.0 — deliberately longer; see
  `timeouts.py`'s module docstring for why a write's timeout must never be
  shortened to "fail faster")

Raising these trades user-visible latency for fewer `uncertain` outcomes
under a slow-but-eventually-successful Google response; lowering them does
the reverse. Change only with evidence (e.g. `lifeflow_provider_request_duration_seconds`
showing genuine call latency close to the current timeout), not
speculatively.
