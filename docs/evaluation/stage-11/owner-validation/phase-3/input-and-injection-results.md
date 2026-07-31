# Stage 11A Phase 3 — Input Handling and Injection Resistance Results (S11A-P3-027)

**Status:** PASS · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md)

## Structural properties (unchanged, re-confirmed)

SQLAlchemy's ORM is parameterised throughout this codebase — no string-built SQL exists anywhere (`git grep` for raw SQL string interpolation finds none in application code). React's default auto-escaping plus zero `dangerouslySetInnerHTML` usages in `apps/web/src` close classic stored/reflected XSS structurally on the frontend. The existing prompt-injection boundary (T3/T4, `docs/security/threat-model.md` §"Prompt-injection boundary") governs LLM-directed content; this phase's new coverage targets classic web-injection vectors instead, which the audit found untested end-to-end.

## New coverage this phase

`apps/api/tests/test_stage11a_phase3_injection_resistance.py` — 15 tests, all passing. 11 malicious-shaped strings (`<script>` tag, `onerror` event-handler HTML, a `javascript:` URL, a Markdown link wrapping a `javascript:` URL, two SQL-injection-shaped strings including a UNION SELECT targeting `encrypted_access_token`, a mixed template-expression string, a shell-metacharacter string, a Unicode bidi-override string, a literal embedded NUL byte, and a nested-JSON-shaped string) were sent through a real task-proposal's `title`/`notes` fields via a real HTTP `PATCH` and a real PostgreSQL database.

For every payload: the response was always 200 or 422, never 500; no `Traceback`, no `psycopg`/`asyncpg`/`sqlalchemy` string, ever appeared in the response body. Where the content was accepted (200), a subsequent `GET` confirmed it was returned **byte-identical** — never executed, never silently altered or sanitised into something different — and a direct database read confirmed the row survived with the exact content, proving the database was never confused into treating the string as SQL or losing the row.

Two additional tests confirmed oversized content (10,000 characters against a 200-character field limit) is rejected with 422 rather than silently truncated, and unexpected object types (an array where a string was expected) are rejected with 422 rather than causing a server error. A final test confirmed the Audit History projection — already a closed-vocabulary presentation registry per Stage 9 — never renders the adversarial proposal content verbatim even when the edited proposal's own content is a `<script>` tag.

## Result

Zero crashes, zero stored/reflected execution, zero SQL errors, across 11 distinct malicious payload shapes. Bounded storage is enforced (422 on oversized content), and type confusion is rejected cleanly (422, not 500).
