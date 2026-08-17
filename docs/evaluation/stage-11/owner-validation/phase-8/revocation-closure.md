# Stage 11A Phase 8 — Revocation Closure

**Date:** 2026-08-17

## Background

Phase 7's teardown (`soak-completion-and-teardown.md`) recorded
`revocation_confirmed: false` for the disconnect's revoke-token call — a
non-200/network-failure result, indistinguishable from the client side, and
classified `REVOCATION ATTEMPT RECORDED — PROVIDER RESULT UNCERTAIN`. Local
credentials were verifiably fully cleared regardless, but Google-side
revocation itself was not confirmed.

## Independent owner verification

The owner checked Google's own connected-apps permissions page directly
(not through LifeFlow) and confirmed: **LifeFlow AI (Owner Testing) still
had active access**, listing four services — consistent with the four
granted scopes (`calendar.events`, `calendar.readonly`, `gmail.compose`,
`gmail.readonly`). This is concrete, independent confirmation that Phase
7's `revocation_confirmed: false` reflected a genuine failure, not merely
an ambiguous network hiccup masking a real success.

The owner then removed LifeFlow's access directly via Google's own
interface and confirmed: `ACCESS REVOKED VIA GOOGLE`.

## Revised classification

**`GOOGLE REVOCATION CONFIRMED — OWNER VERIFIED OUTSIDE THE PRODUCT`.**
Access is now confirmed removed on Google's side, verified independently of
LifeFlow's own audit trail (which could not confirm it at teardown). This
closes Phase 7's open revocation item.

## Note for the record (not a new open item — informational)

This is the first time in this project's history that a revoke-token call
has been directly observed to fail objectively on the Google side (Phase
6B's equivalent call succeeded, `revocation_confirmed: true`). No pattern
or root cause is claimed here beyond what was observed — a single instance
of `revoke_token` returning `false`, with no application-level logging
distinguishing the cause (by design, per `oauth.py::revoke_token`'s
documented contract, so as not to fabricate false confidence about which
of the two possible causes occurred). The product's own behaviour was
correct throughout: local disconnect proceeded regardless (D20), local
credentials were fully cleared either way, and the audit trail truthfully
recorded `false` rather than assuming success.
