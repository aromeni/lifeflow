# Stage 7 Manual Sandbox-Account Checklist

**Status:** partially executed against a real sandbox Google account (2026-07-18 → 2026-07-21). **The core Stage 7 loop is confirmed live**: sign-in (1), connector consent (2), real sync + brief (4), real Gmail draft (5, rounds 3–4), real Calendar event from an inbound scheduling email (6, round 6b) including replay protection and the no-invitation check, and safe degradation of incomplete requests (6b). Items 3 and 7–15 remain open — they gate pilot-readiness (consent-screen promotion), not Stage 7 completion, per the note at the end of this document.

**Every step below now maps to a real, reachable UI control or API route** (updated after the 2026-07-17 independent-review remediation, round 1: ADR 0003 D25–D26; round 2: D29/D32, items 13–15). Before round 1, step 4 referenced "brief generation" as if it triggered a real sync — it did not; no route existed to pull real Gmail/Calendar data into the app at all, and every execution silently used the simulated path regardless of what was connected. That gap is now closed: `POST /connected-accounts/google/sync` (a "Sync now" button on the Connections screen) is the real sync trigger, and the approval preview/execution result now say plainly whether an action is real or simulated (`execution_mode`). Round 2 additionally bound execution to an approval-time snapshot of that account/scope, so items 13–14 exist to prove that binding against a *real* Google account/reconnect, not just against mocks.

## Prerequisites

1. A Google Cloud project with the Gmail API and Calendar API enabled.
2. OAuth consent screen configured as **External**, publishing status **Testing**, with your sandbox Google account added as a test user. **Never use a primary/production mailbox for this checklist.**
3. Two OAuth 2.0 Client IDs (Web application), per [ADR 0003](../architecture/adr/0003-stage7-google-integration.md) D10:
   - **OIDC client** — authorized redirect URI `http://localhost:8010/auth/google/callback`.
   - **Connector client** — authorized redirect URI `http://localhost:8010/connected-accounts/google/callback`.
4. `.env` populated (never commit real values):
   ```
   GOOGLE_OAUTH_ENABLED=true
   GOOGLE_OIDC_CLIENT_ID=...
   GOOGLE_OIDC_CLIENT_SECRET=...
   GOOGLE_OIDC_REDIRECT_URI=http://localhost:8010/auth/google/callback
   GOOGLE_CONNECTOR_CLIENT_ID=...
   GOOGLE_CONNECTOR_CLIENT_SECRET=...
   GOOGLE_CONNECTOR_REDIRECT_URI=http://localhost:8010/connected-accounts/google/callback
   TOKEN_KEY=<generated per .env.example>
   ```
5. The sandbox mailbox seeded with a handful of real (but non-sensitive, throwaway) emails and calendar events so ingestion has something to find.

## Checklist

- [x] **1. Sign in with Google.** **PASS — confirmed live (see sign-off table).** Visit `http://localhost:8010/auth/google/login` directly (or via a frontend button pointing at it). Confirm the Google consent screen requests only `email`, `profile`, and `openid` — no Gmail/Calendar permission. Complete sign-in; confirm you land back on the web app signed in.
- [x] **2. Connect Google separately.** **PASS — confirmed live (see sign-off table).** From the Connections screen, click "Connect Google". Confirm the Google consent screen this time lists exactly: read your email messages and settings, compose/send drafts (compose only), read your calendars, create/manage events you create. Confirm no other permission is listed.
- [ ] **3. Partial grant.** Repeat step 2 but deselect the Calendar permission on Google's consent screen if the UI allows it. Confirm the Connections screen shows only the scopes actually granted. Click "Sync now": confirm it syncs Gmail only (`calendar_synced: false`, `calendar_cursor_status: "not_granted"` in the response) and does not fail the whole sync. Confirm a subsequent calendar-event proposal is denied by the policy engine (not silently allowed), and that its approval preview reads "This action cannot be executed yet" (`execution_mode: "unavailable"`).
- [x] **4. Sync and generate a brief from real data.** **PASS — confirmed live (see sign-off table).** On the Connections screen, click **"Sync now"** (`POST /connected-accounts/google/sync`). Confirm the on-screen summary shows imported/updated counts and cursor status for both Gmail and Calendar. Go to Today and click "Generate brief". Confirm real emails and calendar events appear as source items and evidenced signals — inspect the evidence drawer and confirm it shows real (but redacted/minimal) content, not raw full bodies.
- [x] **5. Approve a Gmail draft.** **PASS — confirmed live (see sign-off table).** Before approving, confirm the proposal's approval preview reads **"This will create a real draft in your connected Gmail account. It will not send the email."** (`execution_mode: "real"`) — not "This action will be simulated". Approve and execute the `create_gmail_draft` proposal. Confirm the result reads **"Gmail draft created"**, not "Simulation result". Confirm in the actual Gmail account (via gmail.com) that a **draft** now exists with the exact approved recipient/subject/body — and confirm **no email was sent**.
- [x] **6. Approve a calendar event from a controlled inbound scheduling email (D39/D40 — the final Stage 7 gate). PASS — confirmed live 2026-07-21.** Proposal composed exactly from the email (23 Jul 2026 16:00–16:30 Europe/London, sender as sole attendee); approved (real Google context); executed once; `succeeded` via independent `events.get` verification; **replay protection PASS** (human-confirmed: exactly one event named "LifeFlow Calendar sandbox test-Z" in the real calendar, no duplicate, proposal terminal); **no-invitation check PASS** (human-confirmed: the controlled attendee mailbox received no Google Calendar invitation email); audit trail complete. The target event must **not** already exist in the calendar. Pick a start time at least 24 hours in the future and write the full date out (weekday, day, month, year).
  1. **Send the controlled email** to the sandbox inbox (from any account you control), following this template exactly — every field below is required by the deterministic extractor. **Two hard constraints measured live (round 6b):** (a) real-account sync stores only Gmail's own snippet, ≈200 characters — keep the body to this single compact sentence, nothing before it; (b) the weekday must genuinely match the date — a contradiction ("Thursday" on a Friday date) is rejected, never silently corrected:
     > Subject: `Please schedule LifeFlow Calendar sandbox test`
     >
     > Please schedule a 30-minute calendar event called 'LifeFlow Calendar sandbox test' for `<Weekday> <D> <Month> <YYYY>`, from `<H:MM>` PM to `<H:MM>` PM Europe/London. Please add me as the attendee.
  2. **Sync**: Connections → "Sync now". Confirm the email imported.
  3. **Generate a fresh brief** on Today. Confirm a "Scheduling request from …" item appears (Needs attention) with the email as its evidence.
  4. **Open the Approval inbox.** Confirm a `create_calendar_event` proposal exists whose payload shows exactly the title, date, start, end, `Europe/London`, and the sender address as the single attendee — nothing invented, nothing missing.
  5. Confirm the preview reads **"This will create a real event in your connected Google Calendar. Guest notifications are off."** (`execution_mode: "real"`) and shows the connected sandbox account context.
  6. **Approve, then execute once.** Confirm the result reads **"Calendar event created"** with `guest_notifications: "off"` and a real `event_id`.
  7. **Verify in Google Calendar** (calendar.google.com): exactly **one** new event with the exact title/date/start/end/timezone/attendee; **no existing event changed**; the attendee received **no** email invitation (check that mailbox).
  8. **Replay**: click execute again (or `POST .../execute`). Confirm the same execution record is returned and **no second event** appears in the calendar.
  9. Confirm the audit trail shows the approval and `execution.succeeded` events with the event id and no token material.

  **Stop rules:** if the outcome reads **uncertain**, stop — do not retry, do not delete anything; record the proposal id and check the calendar manually (the event may or may not exist; LifeFlow will not act again on it). If the created event's details **mismatch** the approved payload, stop and record both — that is a defect, not something to fix by editing the event. If **two** events appear after a replay, stop immediately and report — that is a replay-protection failure.
- [x] **6b. Incomplete scheduling request degrades safely. PASS — live-confirmed 2026-07-21** (not by a deliberate omission, but by three real controlled emails whose details were genuinely incomplete after Gmail's ≈200-char snippet truncation, plus one weekday/date contradiction): all three appeared only as low-confidence clarification signals with per-field reason codes, no `create_calendar_event` proposal was created, and nothing appeared in the calendar.
- [ ] **6c. Duplicate protection (optional — not required by the original Stage 7 acceptance criteria).** Covered by automated evidence: `test_existing_synced_event_suppresses_a_duplicate_candidate` (composition-level duplicate guard) and the route-level replay-protection test; additionally the live replay check in step 6 confirmed no duplicate event. May still be run live at any time: re-send the step-6 email unchanged, sync, regenerate — no second proposal should appear.
- [ ] **7. Audit trail.** Confirm the audit history for both approved actions shows the expected `execution.succeeded` events with a real Google resource id (draft id / event id) in the safe result — and no token material anywhere.
- [ ] **8. Incremental sync.** Click "Sync now" a second time shortly after the first. Confirm the response shows `gmail_cursor_status`/`calendar_cursor_status` as `"incremental"` (using the Gmail historyId / Calendar syncToken cursor) rather than `"initial"`, and that no source items are duplicated.
- [ ] **9. Token refresh.** Wait for the access token to near expiry (or manually adjust `expires_at` in the database to force it), then trigger another action. Confirm it refreshes transparently with no user-visible failure, and that the stored refresh token is unchanged in the database (still decrypts to the same value) if Google's response omits a new one.
- [ ] **10. Revoke from Google's side.** Go to [Google Account → Third-party access](https://myaccount.google.com/permissions) and revoke LifeFlow's access directly from Google. Then trigger a sync or action in LifeFlow. Confirm the account moves to a clear "reconnect required" state — not a raw error — and that re-connecting restores normal operation.
- [ ] **11. Disconnect.** Click "Disconnect Google" in LifeFlow. Confirm: the connection status updates immediately, no further syncs occur, and (if Google's revoke endpoint is reachable) the app no longer appears under Google's third-party access list.
- [ ] **12. Uncertain outcome (optional, harder to force deliberately).** If feasible, simulate a network interruption during an execute call (e.g., disconnect Wi-Fi briefly at the right moment, or throttle the connection). Confirm the result reads **"Outcome uncertain — not retried automatically"** immediately (not a generic error, and not after waiting ~2 minutes for the staleness sweep — a raw connection failure is now classified `uncertain` as soon as it happens), with the no-automatic-retry warning, rather than silently appearing as succeeded or failed.
- [ ] **13. Execution context changes after approval (round 2).** Approve a `create_gmail_draft` or `create_calendar_event` proposal while Google is connected (`execution_mode: "real"`), but do **not** execute it yet. Disconnect Google from the Connections screen. Reload the proposal: confirm it shows **"Execution context changed since approval"** and the Execute button is disabled. Attempt `POST .../execute` directly against the API anyway: confirm it returns a controlled `approval_context_changed` 409, not a raw error and not a silent simulated execution. Reconnect Google, re-approve, and confirm execution now proceeds normally.
- [ ] **14. Reconnect invalidates a stale approval (round 2).** Approve a real proposal, then disconnect and reconnect the **same** Google account (or, if you have a second sandbox Google account available, connect that one instead) without executing the first approval. Confirm execution is blocked with `approval_context_changed` exactly as in step 13 — a reconnect must invalidate a stale approval even though `ConnectedAccount`'s row/id does not change.
- [ ] **15. Incomplete sync and resume (round 2, optional — requires a mailbox with enough history to exceed the page bound, or a temporarily reduced page-bound constant for this test only).** Seed enough Gmail/Calendar history that a sync would need more than the configured page bound (`_MAX_HISTORY_PAGES`/`_MAX_PAGES`) to complete. Trigger "Sync now": confirm the response reports `gmail_sync_complete`/`calendar_sync_complete` as `false` and a truthful "incomplete" notice, and that no page token or provider error text appears in the response. Trigger "Sync now" again: confirm it resumes (no duplicated source items, no gap) rather than restarting from scratch or skipping ahead, and eventually reports `sync_complete: true` once genuinely caught up.

## Sign-off

| Item | Result | Date | Notes |
|---|---|---|---|
| 1. Sign in with Google | ✅ Pass | 2026-07-18 | After D37 clock-skew fix |
| 2. Connect Google separately | ✅ Pass | 2026-07-18 | |
| 3. Partial grant | ☐ Open | | Pilot-readiness item |
| 4. Sync + brief from real data | ✅ Pass | 2026-07-18/21 | Incl. D38 404-resilience live |
| 5. Real Gmail draft | ✅ Pass | 2026-07-18 | Two verified drafts, `succeeded`; nothing sent; historical round-1 `uncertain` preserved |
| 6. Real Calendar event from inbound email | ✅ Pass | 2026-07-21 | Incl. replay-protection + no-invitation checks (human-confirmed) |
| 6b. Incomplete request degrades safely | ✅ Pass | 2026-07-21 | Live: 3 truncated/contradictory emails → clarification signals only |
| 6c. Duplicate protection | ◇ Optional | | Automated evidence; may be run live any time |
| 7–15 | ☐ Open | | Pilot-readiness items (consent-screen promotion gate) |

This checklist gates the move from "Testing" to "In production" consent-screen status (see the verification roadmap in [docs/security/threat-model.md](../security/threat-model.md)) — not Stage 7 development itself, which is unblocked by the automated test suite alone.
