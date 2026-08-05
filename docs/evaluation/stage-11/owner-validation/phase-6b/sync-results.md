# Stage 11A Phase 6B — Sync Results

**Date:** 2026-08-05

Exactly one manual sync was performed (`POST /connected-accounts/google/sync`), triggered on demand from the Connections page. No automatic or second sync occurred (`last_sync_at` recorded a single timestamp).

- Imported: 53, updated: 0, unchanged: 0 (content-free counts only).
- No provider write occurred during sync — the sync path only ever reads.
- No Gmail draft and no Calendar write occurred during extraction.
- P6-CAL-TEST-02 was present among the imported items and was traced through to its resulting proposal (see `proposal-traceability.md`).
- No real or personal content was knowingly encountered; the fixed synthetic dataset (GM-01–17, CAL-01–11) and the two dedicated trigger messages are the only expected content in Account A's mailbox/calendar for this environment.
- GM-12's stale-age expectation was not counted towards this phase's result — this phase evaluates only the Calendar-write path.
