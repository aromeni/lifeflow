# Stage 11A Phase 10 — Daily Brief Generation Under Real Elapsed Time

Bounded exercise (not a repeat of the Phase 7 soak): reconnect Account A,
generate one brief per day for at least several real days, confirm stable,
consistent, error-free output each time. Same operating model as Phase 7
(owner-triggered check-ins, best-effort local uptime). Teardown at the end.

Each entry: date, elapsed day count, brief generation result (success/
error, section counts, any anomaly), connection/stability status.

---

## Day 0 — 2026-08-24T19:20:47Z (T0)

- Connection: Account A reconnected, verified (`authorisation_revision`
  6→7, same four scopes, Account B untouched, 0 OIDC bindings).
  `GOOGLE_CONNECTOR_OAUTH_ENABLED` restored to `false` immediately after.
- Sync: `imported=0 updated=0 unchanged=0`, both cursors `"incremental"`.
- Brief generation: `HTTP 200`, `status: "complete"`, version `1`.
  Section counts: needs_attention 7, today_upcoming 4, waiting_for 2,
  suggested_actions 6, low_confidence_review 1. Extraction: 19
  deterministic signals, 0 LLM used, 0 failed.
- Duplicates: 0/0 (SourceItem/Signal group-by checks empty).
- Writes: confirmed 0 `action_executions` against the real account with
  `started_at` after T0.
- No anomalies.

## Day 3 — 2026-08-27T15:17Z (first check-in since Day 0; ~2.8 real days elapsed)

- No gap: API/web processes are the same PIDs as Day 0 (running
  continuously since); `db`/`redis` up 2 weeks straight. Flags confirmed
  `false`.
- Connection status: `active`, `authorisation_revision: 7` — unchanged.
- Sync: `imported=0 updated=0 unchanged=0`, both cursors still
  `"incremental"`.
- Brief generation: `HTTP 200`, `status: "complete"`, version `1` (a new
  briefing date — versions are scoped per calendar day, so `1` here is
  correct, not a stall). Section counts identical in shape to Day 0
  (needs_attention 7, today_upcoming 4, waiting_for 2, suggested_actions 6,
  low_confidence_review 1); extraction counts shifted slightly
  (17 deterministic, 10 updated, 7 unchanged vs Day 0's 19/8/11) — expected
  variation as demo-dataset due-dates/ages move relative to the reference
  clock across real days, not an error.
- Duplicates: 0/0. Writes: confirmed 0 new `action_executions`.
- `preconnection_readiness_check.py` correctly reports `stored_credential_rows=1`
  / `NOT READY` right now — expected and not a defect, since that check
  specifically gates *new* connections and Account A is deliberately still
  connected mid-exercise; every other row still passes.
- No anomalies.

## Day 7 — 2026-08-31T19:09:20Z (second check-in since Day 3; ~6.99 real days elapsed since T0)

- No gap: API process is the same PID as Day 0/Day 3 (running continuously
  since, started the prior Monday evening); `db`/`redis` up 2 weeks
  straight, healthy. `/health` and `/ready` both clean (`degraded_dependencies: []`).
  Flags confirmed `false`/`false`/`false`.
- Connection status: `active`, `authorisation_revision: 7` — unchanged since
  Day 0's reconnection, `has_access`/`has_refresh` both true.
- Sync: `imported=0 updated=0 unchanged=0`, both `gmail_cursor_status` and
  `calendar_cursor_status` still `"incremental"` (no full resync triggered
  yet).
- Brief generation: `HTTP 200`, `status: "complete"`, version `1` for the
  new briefing date (2026-08-30T23:00Z, i.e. 2026-08-31 Europe/London) —
  correct, not a stall. Section counts: needs_attention 7, today_upcoming 4,
  waiting_for **3** (up from 2 on Day 0/Day 3 — a third stale-follow-up
  crossed its threshold as real days advanced: `no_reply_8d` on the
  Northgate contract-terms reply, alongside the existing 13-day and 20-day
  items), suggested_actions 6, low_confidence_review 1. Extraction: 17
  deterministic signals, 0 LLM used, 0 failed; `persisted_new: 1`,
  `persisted_updated: 7`, `persisted_unchanged: 9`.
- Proposal generation: `created: 2` — investigated, not assumed benign.
  Both new proposals (`60122480…` a `create_task` traced to `em-019`,
  `62ccde42…` a `create_gmail_draft` traced to `em-009`) are freshly
  created because their underlying deadlines (`before the end of the
  month`, `by the 30th`) became due/overdue exactly as real calendar days
  advanced — deterministic, date-driven proposal generation working
  correctly, not duplication. Confirmed distinct `source_refs` from every
  prior proposal on this account.
- Duplicates: all three checks (`source_items` by external_id,
  `signals` by dedupe_key, `action_proposals` by origin_fingerprint) return
  0 rows.
- Writes: confirmed 0 `action_executions` against this connected account
  with `started_at` after T0.
- `preconnection_readiness_check.py` again correctly reports `NOT READY`
  (`stored_credential_rows=1`) — same expected, explained condition as
  Day 3; every other check passes.
- No anomalies.

**Assessment:** three check-ins (Day 0, Day 3, Day 7) spanning just under 7
real days, each independently verified end-to-end (sync → brief generation
→ duplicate checks → write checks), all clean with no unexplained failures
and only expected, explainable variation (per-day version numbering,
date-relative extraction counts, newly-due proposals as calendar time
advances). This satisfies the exit template's condition 2 wording ("across
at least several real days... stable, consistent output with no unexplained
failures"). **Condition 2 is closed** — see
[phase-10-decision.md](phase-10-decision.md).

## Teardown — 2026-09-03

Full teardown completed and independently verified as zero-residue:
imported-data-deletion preview (no-op — 0 real source items on this
account already), disconnect (owner-run, `revocation_confirmed: false`
locally but independently confirmed on Google's own side — "You haven't
linked any apps yet"), and `preconnection_readiness_check.py` 19/19 PASS.
See [teardown.md](teardown.md) for the full record.
