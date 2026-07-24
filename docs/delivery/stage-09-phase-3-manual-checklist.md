# Stage 9 Delivery Phase 3 — Audit History Manual Checklist

Use a fresh development/demo user. No Google or Anthropic credentials are
required, and no provider side effect is exercised.

## Setup

1. Start the local stack with `./scripts/demo.sh`, or start PostgreSQL, the API,
   and the web app using the README commands.
2. Sign in as a fresh demo user, start the demo, and generate one brief.
3. Open the Approval inbox and reject one proposed action. If entering a
   reason, use a distinctive private value so its absence can be checked.

## Canonical route and integration

4. Open `/connections`; confirm the heading is **Privacy & Connections** and
   the **View audit history** link is visible.
5. Follow that link; confirm the URL is exactly `/audit-history`, the heading is
   **Audit history**, and links back to Today and Privacy & Connections work.

## Privacy-safe presentation

6. Confirm **Brief generated** and **Action rejected** appear as plain-language
   entries with a timestamp, actor, category, and outcome label.
7. Confirm the entered rejection reason, email/calendar content, recipients,
   provider identifiers, UUID entity/correlation details, error internals, and
   words such as `safe_metadata` are absent.
8. Confirm no edit, delete, retry, or other audit mutation control exists.
9. Confirm the **Action rejected** entry shows a small safe action-type badge
   (**Task**, **Gmail draft**, or **Calendar event**) — never the raw
   `create_task`/`create_gmail_draft`/`create_calendar_event` value. If any
   entry represents a partially failed or failed deletion, retention, or
   execution, confirm it shows a plain-language **Reason:** line drawn from a
   fixed, closed set — never a raw error code, exception message, or provider
   response. For a completed (or partially failed) imported-data, retention, or
   account-deletion entry, confirm it shows plain-language count sentences
   ("N records deleted", "N record(s) preserved for reconciliation") with
   correct singular/plural wording, no zero-value counts, and never a raw
   per-category breakdown, operation id, or scope descriptor (ADR 0005 D80).
   Retention entries never show a preserved-records line (retention never
   tracks that figure — a pre-existing characteristic, not a bug).

## Closed filters and pagination

10. Select **Actions**; confirm action entries remain and the brief entry is no
    longer visible.
11. Exercise **Last 7 days**, **Last 30 days**, **Last 90 days**, and **All
    time**; confirm each produces a fresh, coherent result window.
12. If more than 20 registered events exist, use **Load more**; confirm existing
    entries remain, older entries append once, and no duplicate appears.
13. Select a combination with no matching events; confirm the page shows an
    honest empty state rather than an error.

## Accessibility and failure states

14. Navigate the filters, links, history list, and Load more button by keyboard;
    confirm focus and labels are understandable without relying on colour.
15. Sign out and open `/audit-history`; confirm the signed-out guidance appears.
16. Stop the API and retry; confirm the load failure is announced and **Try
    again** is available. Restart the API and confirm retry recovers.

## Automated equivalent

`./scripts/e2e.sh audit-history.spec.ts` automates the principal journey
(steps 2–11) against the real API, a real ARQ worker, and real PostgreSQL,
including the safe action-type badge assertion and a genuine completed
imported-data deletion whose audit entry shows the exact seeded count
("3 records deleted"). Backend tests additionally prove owner isolation,
unknown-event exclusion, raw-field sentinel privacy, closed-filter validation,
stable equal-timestamp keysets, a frozen `as_of` window, malformed/
filter-mismatched cursor rejection, read-only behaviour, and — from the
presentation completeness correction — safe action-type/reason rendering,
safe aggregate counts for imported-data/retention/account-deletion completion
and partial failure, rejection of negative/boolean/string/float/excessive
counts, omission of unknown metadata keys and unregistered values, and
historical rows without the optional detail still rendering safely.
