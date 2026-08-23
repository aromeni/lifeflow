# Stage 11A Phase 10 — Low-Disk-Space Exercise Results

**Date:** 2026-08-24

## Method

Isolated, throwaway infrastructure only — never the real dev database or
host disk:

1. A standalone `postgres:16-alpine` container (`lifeflow-disk-test`) with
   its data directory mounted on a **48MB `tmpfs`**, on a separate port
   (5499), no relation to the real dev `db` container.
2. Alembic migrations applied to it (all 12 migrations, clean).
3. A temporary `uvicorn` instance on a separate port (8099) pointed at this
   isolated database via a `DATABASE_URL` override — `.env` never touched.
4. Seeded via `/demo/start` and a few `/briefs/generate` calls, then forced
   to true exhaustion with direct, incompressible-data SQL inserts
   (`md5(random())`-derived text — plain repeated characters were found to
   compress via TOAST and didn't actually consume space, corrected for).

## Result: exhaustion behaviour

At `100%` used / `0` available, Postgres itself correctly rejected the
insert with `ERROR: could not extend file ... No space left on device` —
the expected, standard Postgres safety behaviour, not something this
exercise needed to prove on its own.

The interesting result is the **application's** behaviour on top of that:

| Check | Result |
|---|---|
| `GET /health` during exhaustion | `200 {"status":"ok"}` — unaffected (liveness only) |
| `GET /ready` during exhaustion | `200 {"status":"ok","degraded_dependencies":[]}` — unaffected (connectivity check, not a write-capacity check) |
| `POST /briefs/generate` (a real write) during exhaustion | Clean `500`, `{"error":{"code":"internal_error","message":"An internal error occurred.",...}}` — **no raw exception, stack trace, or file path leaked**; a single well-formed JSON error, not a hang or a crash |
| API process | Stayed alive and responsive throughout — no crash, no restart needed |
| Partial/corrupted rows | **Zero** — `select count(*) from briefs where status not in ('complete','degraded')` returned `0`; the brief count was exactly the number of *successful* prior generations, confirming the failed attempt left no partial row (Postgres's own transactional guarantee held, and the app didn't paper over the failure with fabricated partial state) |

## Result: recovery

Freeing space (dropping the filler table) and immediately retrying
`POST /briefs/generate` succeeded cleanly on the very next call — version
6, `status: "complete"`, full normal output, **no API restart required**.
This mirrors the same self-recovery pattern already observed for Redis/DB
connectivity outages in Phase 2 and the real Docker sleep/reboot gaps
observed live during Phase 7's soak.

## Observation for the record (not a defect)

`/health` and `/ready` do not detect write-capacity exhaustion — only
connectivity. This is reasonable design (a readiness probe answering "can
this instance serve traffic" is a different question from "can every
possible write succeed right now," and the latter is generally
undecidable in advance for a shared database), but it means an operator
watching only `/ready` would not see this specific failure mode coming;
they would see it exactly at the point a write is attempted, via that
write's own error response — which is what actually happened here.

## Verdict

**Safe, ungraceful-failure-free degradation confirmed.** No corruption, no
crash, no leaked internals, clean automatic recovery once space returned.
Closes §D's low-disk-space exercise, the one item in Phase 2's original
scope that had never actually been run.
