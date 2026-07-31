# Stage 11A Phase 3 — Dependency Security Results (S11A-P3-039)

**Status:** PASS (with one documented, bounded, dev-tooling-only exception) · **Date:** 2026-07-31

Companion: [acceptance-matrix.md](acceptance-matrix.md) · [defect-register.md](defect-register.md)

No dependency-vulnerability scanning existed anywhere in this project before this phase — confirmed absent during the Phase 3 audit (no `pip-audit`, `safety`, `npm audit`, `trivy`, or `snyk` configured in any CI workflow, pre-commit hook, or `pyproject.toml`/`package.json` script). This is the first run in this project's history.

## Python (`pip-audit --local`, apps/api's `.venv`)

**Result: no known vulnerabilities found.** Classification: **confirmed not applicable** — the installed dependency set is clean.

## JavaScript (`pnpm audit`, full workspace)

**Initial run: 17 vulnerabilities (11 high, 6 moderate).** All 15 Next.js-specific findings (SSRF in Server Actions and rewrites, middleware/proxy bypass in App Router, denial of service in App Router and Image Optimization, cache confusion, unauthenticated disclosure of internal Server Function endpoints) plus bundled `postcss` (arbitrary file read, path traversal, XSS) and `sharp` (libvips CVEs) were traced to a single root cause: `next` was pinned at `16.2.10`, one patch release behind the `16.2.11` fix threshold.

**Classification: confirmed exploitable in principle, fixed this phase.** `next` was bumped to `16.2.12` (the latest available 16.2.x patch, `apps/web/package.json`), `eslint-config-next` bumped to match. `postcss`/`sharp`/`js-yaml` were additionally pinned via `pnpm.overrides` in the root `package.json` (`postcss >=8.5.18`, `sharp >=0.35.0`, `js-yaml >=4.3.0`) to force their remaining separately-resolved copies (used by `@tailwindcss/postcss`/`vite`/`@redocly/openapi-core`, none of them the Next.js-bundled copy the version bump already fixed) to patched versions.

**Verification after the fix**: `pnpm audit` dropped to 2 findings (both `brace-expansion`, below); full re-run of `pnpm web:typecheck`, `pnpm web:lint`, `pnpm web:test` (90/90 passing), `pnpm web:build` (production build succeeds on Next.js 16.2.12/Turbopack), and `./scripts/generate-contracts.sh` (byte-identical output) confirmed zero regressions from the dependency bump.

## Remaining finding: `brace-expansion` (2 paths, both dev-tooling-only)

**Classification: requires upstream fix, currently unresolvable locally without breaking a dev tool — recorded as P2, not blocking.**

An identical override attempt (`brace-expansion >=5.0.8`) was tried and **reverted** after it broke `pnpm web:lint` (`TypeError: expand is not a function` inside `minimatch@3.1.5`, a transitive dependency of `@eslint/config-array` that this project does not control). Root cause: the GHSA advisory's vulnerable range (`<=5.0.7`) spans every major line of `brace-expansion` (1.x, 2.x, 5.x) with a patch only ever released in the 5.x line — `minimatch@3.1.5` hard-depends on the incompatible 1.x major and cannot consume a 5.x replacement without a code change upstream in `minimatch`/`eslint`/`@eslint/config-array` itself.

**Real-world exposure is bounded to zero in this project's actual usage**: both vulnerable paths are exercised only by `eslint` (processing this repository's own source tree during `pnpm web:lint`) and `@redocly/openapi-core`/`openapi-typescript` (processing this repository's own OpenAPI schema during contract generation) — neither ever processes attacker-supplied input, and neither ever runs as part of the deployed production API or web server. The vulnerability (a DoS via an attacker-crafted glob pattern) has no attacker-reachable surface in this project's actual usage pattern.

**Closure condition**: this is fully resolved once `eslint`'s own dependency chain bumps its `minimatch`/`brace-expansion` usage past the vulnerable range upstream — tracked here rather than left silently unaddressed. No fabricated "zero vulnerabilities" claim is made.
