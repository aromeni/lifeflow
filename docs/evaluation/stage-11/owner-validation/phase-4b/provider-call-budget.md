# Provider-Call Budget

**Status:** Defined · **Date:** 2026-08-01

Companion: [provider-write-authorisation-gate.md](provider-write-authorisation-gate.md) · [first-connection-runbook.md](first-connection-runbook.md)

Conservative budgets for the first connection and the first-write test. These are the maximum counts a future authorised task may perform; they are not targets to reach, and no count here is created by this task.

| Call type | Connection-only (Decision 1) budget | After Decision 2 |
|---|---|---|
| OAuth attempts (authorization + token exchange) | ≤ 3 (allowing for one or two consent-screen mistakes before success) | no additional budget — connection is one-time |
| Gmail list/read requests | ≤ 20 (one `sync` call plus manual re-checks) | ≤ 20 more, for verification |
| Calendar list/read requests | ≤ 20 | ≤ 20 more, for verification |
| Token refresh attempts | ≤ 5 | ≤ 5 more |
| Gmail draft writes | **0** | **≤ 1** |
| Calendar insertion writes | **0** | **≤ 1** |
| Reconciliation reads (confirming what was written) | 0 (nothing written yet) | ≤ 5 |
| Revocation attempts | ≤ 3 (allowing for a retry if the first attempt fails) | ≤ 3 |

## Write-budget rule

**Gmail drafts created by LifeFlow: 0 during connection-only validation. Calendar events inserted by LifeFlow: 0 during connection-only validation.** Only after separate, explicit Decision 2 authorisation: **Gmail drafts: maximum 1. Calendar insertions: maximum 1.**

## No retries of uncertain writes

If a write's outcome is uncertain (e.g. a timeout after the request was sent but before a response was received), the write is **not** automatically or manually retried. The owner must first check Gmail/Calendar directly to determine the actual outcome before deciding whether a single, deliberate retry is warranted — consistent with LifeFlow's existing uncertain-write handling for the synthetic connectors (Stage 2/Phase 2 resilience testing).

## Counters and evidence

A future connection/write task must record, in a dated addendum to this document or a successor evidence file: the actual count of each call type performed, compared against the budgets above, and an explanation for any count that reaches its budget (rather than silently exceeding it). This document does not itself record any counts, since no call of any kind has been made.
