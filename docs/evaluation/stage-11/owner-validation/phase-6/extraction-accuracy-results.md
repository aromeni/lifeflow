# Stage 11A Phase 6 — Extraction-Accuracy Evidence

**Date:** 2026-08-05

## A real limitation, stated honestly

The plan called for comparing each of GM-01–17 (excluding GM-12, deferred) and CAL-01–11 against Phase 4B's expected-outcome table. In practice, the original population checklist did not ask the owner to tag each message/event with its scenario ID the way the dedicated P6 trigger messages were tagged — so individual signals cannot be mapped back to individual scenario IDs without asking the owner to describe content, which would break the content-free evidence principle this entire programme has held throughout. **A precise per-scenario match against Phase 4B's table could not be performed this phase.** This is recorded as a genuine process gap, not glossed over: a future phase needing this precision should ask the owner to include a scenario-ID tag when composing dataset content, exactly as done for the P6 triggers.

## What could be measured: aggregate, content-free signal distribution

| Signal type | Count | Avg. priority | Avg. confidence |
|---|---|---|---|
| `request` | 11 | 0.63 | 0.85 |
| `deadline` | 2 | 0.53 | 0.70 |
| `conflict` | 1 | 0.65 | 1.00 |
| `schedule_request` | 1 | 0.49 | 0.45 |

Source items: 37 emails, 15 calendar events (49 imported total; recurring CAL-11 evidently expands to multiple occurrence rows within the sync window).

Directionally consistent with the dataset's design:
- The single `conflict` signal corresponds to the overlapping-events scenario (CAL-08/GM-10) — correctly detected.
- The single `schedule_request` signal is P6-CAL-TEST-01 itself (confirmed by direct cross-reference in `trigger-and-write-validation-results.md`) — no other message in the dataset was classified this way, despite several (GM-01, GM-05, GM-10, GM-17) carrying scheduling-adjacent content; this indicates the deterministic scheduling-signal detector is narrow/strict, consistent with its "nothing is guessed" design philosophy.
- 11 `request`-type signals is plausible given the dataset's design includes roughly a dozen distinct request-shaped scenarios (GM-01, 03, 05, 09, 10, 11, 17, plus both P6 triggers, plus additional signals from the multi-message GM-08/GM-15 threads).

## GM-12 (deferred)

GM-12 was excluded from this evaluation, as planned — it will not be genuinely 5+ days old until after this phase's live window. Its accuracy check is deferred to a separate, later, lightweight follow-up (a fresh reconnect+sync once it qualifies), since this phase's own cleanup deletes LifeFlow's local copies at its end. It does not gate this phase's decision.
