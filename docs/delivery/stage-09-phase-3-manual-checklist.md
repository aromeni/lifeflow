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

## Closed filters and pagination

9. Select **Actions**; confirm action entries remain and the brief entry is no
   longer visible.
10. Exercise **Last 7 days**, **Last 30 days**, **Last 90 days**, and **All
    time**; confirm each produces a fresh, coherent result window.
11. If more than 20 registered events exist, use **Load more**; confirm existing
    entries remain, older entries append once, and no duplicate appears.
12. Select a combination with no matching events; confirm the page shows an
    honest empty state rather than an error.

## Accessibility and failure states

13. Navigate the filters, links, history list, and Load more button by keyboard;
    confirm focus and labels are understandable without relying on colour.
14. Sign out and open `/audit-history`; confirm the signed-out guidance appears.
15. Stop the API and retry; confirm the load failure is announced and **Try
    again** is available. Restart the API and confirm retry recovers.

## Automated equivalent

`./scripts/e2e.sh audit-history.spec.ts` automates the principal journey
(steps 2–10) against the real API and PostgreSQL. Backend tests additionally
prove owner isolation, unknown-event exclusion, raw-field sentinel privacy,
closed-filter validation, stable equal-timestamp keysets, a frozen `as_of`
window, malformed/filter-mismatched cursor rejection, and read-only behaviour.
