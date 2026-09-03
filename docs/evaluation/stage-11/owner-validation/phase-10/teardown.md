# Stage 11A Phase 10 — Brief-Generation Exercise Teardown

**Date:** 2026-09-03

## Sequence

1. **Imported-data-deletion preview** — run 2026-09-01; `preview_counts`,
   `preserved_counts`, and `deleted_counts` all empty. Independently
   confirmed by direct query: Account A already had **0** `source_items`
   at that point (real Gmail/Calendar content synced during this
   exercise's Day 0–7 check-ins had already been cleared by an earlier
   phase's teardown; every item the daily briefs showed throughout Phase
   10 traced to the separate `synthetic` demo `connected_account`
   (`9cc310f6…`), never to Account A). The preview operation's window
   expired before confirmation was run — harmless, since there was nothing
   for it to delete.
2. **Disconnect** — run by the owner directly (2026-09-03, `curl` against
   the local API, per the owner's own terminal), after a Bash
   auto-classifier correctly blocked Claude from running the equivalent
   destructive call directly. `connected_accounts` row for Account A:
   `status: 'disconnected'`, `access_token_key_id`/`refresh_token_key_id`
   both null. Audit event `account.disconnected` recorded, with
   `safe_metadata_json: {"revocation_confirmed": false}` — the disconnect
   flow's Google revoke-token call returned a non-200/network-failure
   result (D20: local disconnect proceeds regardless; the two causes are
   indistinguishable from the client side by design, per
   `oauth.py::revoke_token`'s documented contract).
3. **Independent owner verification on Google's side** — the owner checked
   Google's own connected-apps page directly (not through LifeFlow) and
   was told **"You haven't linked any apps yet."** No active LifeFlow
   grant is listed.

## Residue check

- `source_items` tied to Account A: **0**.
- Stored credentials (`stored_credential_rows_zero`,
  `preconnection_readiness_check.py`): **0**.
- Non-terminal `action_proposals` referencing Account A: **1** —
  `bb0d4d00…`, an already-`executed` `create_calendar_event` write from
  Phase 6B (2026-08-05). Correctly preserved as content-free audit
  history, not new residue from this exercise; not deleted, per the
  deletion flow's own stated policy ("Actions you already approved or
  that ran are kept as content-free history").
- `preconnection_readiness_check.py`: **19/19 PASS — READY**.

## Classification

**GOOGLE REVOCATION CONFIRMED — OWNER VERIFIED OUTSIDE THE PRODUCT.**
Unlike Phase 8 (where the owner's independent check found LifeFlow still
listed with active access, requiring a manual removal), here Google's own
page already showed no linked app at all — direct, independent evidence
that access is in fact gone on Google's side, notwithstanding the local
audit trail's honest `revocation_confirmed: false` (a true reflection of
the ambiguity `revoke_token` cannot resolve from the client alone, not a
false negative in this instance). Combined with the local residue check,
this closes teardown for the brief-generation exercise with zero
outstanding items.

## Note for the record (informational, not a new open item)

This is a second observed instance (after Phase 8) of a disconnect's
Google-side revoke call not returning a confirmed success locally, while
the underlying Google-side state was in fact correct. Consistent with the
documented, intentional ambiguity of `revoke_token`'s return contract — no
new pattern or root cause is claimed beyond what was directly observed.
