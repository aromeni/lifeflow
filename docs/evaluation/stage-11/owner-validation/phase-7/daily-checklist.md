# Stage 11A Phase 7 — Daily Checklist

This is the exact, repeatable protocol to run at every owner check-in for the
duration of the soak (see [stage-11a-phase-7-plan.md](../../../delivery/stage-11a-phase-7-plan.md)
for scope and the operating model). Written once, in full, so it can be
followed identically on day 1 and day 10, including after a context reset —
do not re-derive commands from memory.

All commands assume the repo root as the working directory, the demo stack
up (`docker compose up -d db redis`, API on `127.0.0.1:8010`), and use a
throwaway cookie jar so no session token is ever printed. Never print token,
credential, or raw provider content values to any evidence file or terminal
output that gets committed.

## 0. Pre-flight (every check-in)

```bash
grep -E "^GOOGLE_OIDC_SIGNIN_ENABLED|^GOOGLE_CONNECTOR_OAUTH_ENABLED|^GOOGLE_PROVIDER_WRITES_ENABLED" .env
```

Expect all three `false`, *except* during the brief Day-0-connection or
reconnection-after-expiry windows (§2/§5), where
`GOOGLE_CONNECTOR_OAUTH_ENABLED` is briefly `true`. Any other deviation is an
anomaly — stop and investigate before continuing.

## 1. Stability snapshot

```bash
curl -s http://127.0.0.1:8010/health
curl -s http://127.0.0.1:8010/ready
curl -s http://127.0.0.1:8010/metrics | grep -E "provider_requests_total|provider_timeouts_total|stale_pending_recovered_total|database_readiness_failures_total|redis_degraded_total|rate_limited_requests_total"
docker compose ps
```

Record: `/ready` status (200 vs 503 + `degraded_dependencies`), and the
Prometheus counter deltas since the previous check-in (a monotonically
increasing counter is expected; note the delta, not just the absolute
value). If the stack was down between check-ins, log it as an observed gap
(see plan's "Operating model") rather than a failure, then continue.

## 2. Authenticate and check connection status

```bash
COOKIE_JAR=$(mktemp)
curl -s -c "$COOKIE_JAR" -X POST http://127.0.0.1:8010/auth/dev-login -H "Content-Type: application/json" -d '{}' > /dev/null
```

```sql
-- via: docker compose exec -T db psql -U lifeflow -d lifeflow -c "..."
select id, status, authorisation_revision, access_token_key_id is not null as has_access,
       refresh_token_key_id is not null as has_refresh
from connected_accounts
where user_id = (select id from users where email = 'dev@lifeflow.local') and provider = 'google';
```

- `status = 'active'` → proceed to §3 (normal day).
- `status = 'revoked'` → this is the expected 7-day-boundary event (or an
  earlier-than-expected one) — skip to §5 (reconnection), then continue with
  §3 once reconnected.

## 3. One controlled read-only sync

```bash
curl -s -c "$COOKIE_JAR" -b "$COOKIE_JAR" -X POST http://127.0.0.1:8010/connected-accounts/google/sync
```

Record the response body's `imported`/`updated`/`unchanged` counts (content-free — counts only, never item titles or IDs). A `409 reauthorisation_required` response means the token was rejected — treat exactly as the `status = 'revoked'` case above (§5), and note in the log that the *sync attempt itself*, not a separate status poll, is what surfaced the expiry (this satisfies "bounded authentication-failure and retry behaviour" — confirm the response is a single, non-retried 409, never a hang or repeated automatic attempt: no cron job in this codebase touches Google, so no background retry can occur).

## 4. Duplicate checks

```sql
select source_type, external_id, count(*) from source_items
where source_account_id = (select id from connected_accounts where user_id = (select id from users where email='dev@lifeflow.local') and provider='google')
group by 1,2 having count(*) > 1;

select dedupe_key, count(*) from signals
where user_id = (select id from users where email='dev@lifeflow.local')
group by 1 having count(*) > 1;

select origin_fingerprint, count(*) from action_proposals
where user_id = (select id from users where email='dev@lifeflow.local')
group by 1 having count(*) > 1;
```

All three must return zero rows (the `UniqueConstraint`s on these columns
make a non-empty result structurally impossible unless something is
seriously wrong — treat any row here as a P0). Also check the sync
response's own counts: after day 0, `imported` should stay `0` on every
subsequent day (nothing new is being sent to Account A), with repeats
absorbed as `unchanged`.

## 5. Reconnection after expiry (only when §2/§3 showed `revoked`/409)

1. Set `GOOGLE_CONNECTOR_OAUTH_ENABLED=true` in `.env`; restart the API
   process (`--forwarded-allow-ips=""` flag required, per CLAUDE.md).
2. Ask the owner to perform the live reconnect for **Account A only**,
   approving the same four scopes (`calendar.events`, `calendar.readonly`,
   `gmail.compose`, `gmail.readonly`) — never Account B.
3. Verify via the database immediately (same query as §2): `status='active'`,
   `authorisation_revision` incremented by exactly 1 from its pre-expiry
   value, scopes still exactly the four approved ones, exactly one
   `connected_accounts` row for this user+provider (the `UniqueConstraint`
   guarantees this — a reconnect updates the existing row, it cannot create
   a second one).
4. Set `GOOGLE_CONNECTOR_OAUTH_ENABLED=false` again immediately.
5. Record the reconnection event: query
   `select event_type, timestamp from audit_events where entity_id = '<account id>' order by timestamp desc limit 1;`
   — expect `event_type = 'account.tokens_refreshed'` (not
   `account.connected` — the account row already exists from Phase 6B
   onward, so `accounts.py`'s `store_tokens` takes the existing-row branch,
   which is labelled `tokens_refreshed` even though this is a full
   re-consent, not a silent refresh; this is a pre-existing audit-vocabulary
   quirk, not a defect introduced by this phase). Record this timestamp as
   the reconnection time, distinct from T0 — the soak clock does not reset.
6. Log the elapsed hours since T0 at the moment of expiry, and resume the
   daily protocol from §3.

## 6. GM-12 eligibility and evaluation (once, the first day it qualifies)

```sql
select id, occurred_at, now() - occurred_at as age
from source_items
where source_account_id = (select id from connected_accounts where user_id=(select id from users where email='dev@lifeflow.local') and provider='google')
  and metadata_json->>'subject' ilike '%checking in%'
order by occurred_at asc;
```

(Adjust the subject filter if needed — GM-12 is the synthetic "Checking in
on the invoice" stale-follow-up fixture, sent 5+ days before Phase 6-era
testing began; see
[synthetic-gmail-dataset-plan.md](../phase-4b/synthetic-gmail-dataset-plan.md).)
Once `age >= 5 days`, check whether a stale-follow-up `Signal` exists
referencing this item and whether a corresponding proposal (if any) was
composed — record what was found, but do **not** approve or execute
anything. This is a read-only observation of extraction correctness under
real elapsed time, not an action-taking step.

## 7. Log the day

Append one entry to
[soak-daily-log.md](soak-daily-log.md) with: date/time, elapsed hours since
T0, `/ready` result, counter deltas, sync counts, duplicate-check result,
connection status, any reconnection event, GM-12 status, and any observed
gap. Commit the log update on this branch (small, frequent commits — do not
batch multiple days into one commit).

## 8. Check the clock

```bash
python3 -c "
from datetime import datetime, timezone
t0 = datetime.fromisoformat('<T0 ISO8601>')
elapsed = datetime.now(timezone.utc) - t0
print(elapsed, elapsed.total_seconds()/3600, 'hours')
"
```

Once elapsed hours >= 240, this was the final daily check-in — proceed to
the soak-completion teardown instead of scheduling another day (see
[stage-11a-phase-7-plan.md](../../../delivery/stage-11a-phase-7-plan.md)).
