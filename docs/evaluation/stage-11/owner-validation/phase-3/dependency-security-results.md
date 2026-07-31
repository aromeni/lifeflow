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

**Classification at the time this phase's own testing was performed: requires upstream fix, currently unresolvable locally without breaking a dev tool — recorded as P2, not blocking.**

An identical override attempt (`brace-expansion >=5.0.8`) was tried and **reverted** after it broke `pnpm web:lint` (`TypeError: expand is not a function` inside `minimatch@3.1.5`, a transitive dependency of `@eslint/config-array` that this project does not control). At the time, `pnpm audit` flagged two `brace-expansion` findings alongside the Next.js/postcss/sharp set, and the override was believed necessary to close them; `minimatch@3.1.5` hard-depends on the incompatible 1.x major and cannot consume a 5.x replacement without a code change upstream in `minimatch`/`eslint`/`@eslint/config-array` itself.

**Real-world exposure was bounded to zero in this project's actual usage regardless**: both vulnerable paths are exercised only by `eslint` (processing this repository's own source tree during `pnpm web:lint`) and `@redocly/openapi-core`/`openapi-typescript` (processing this repository's own OpenAPI schema during contract generation) — neither ever processes attacker-supplied input, and neither ever runs as part of the deployed production API or web server. The vulnerability class (a DoS via an attacker-crafted glob pattern) has no attacker-reachable surface in this project's actual usage pattern.

### Revalidation performed for this correction task (2026-07-31, same day, later)

This correction task required confirming the exact dependency chain rather than trusting the earlier record as-is. Re-running the exact same command against the exact same lockfile (no drift — `git diff --stat HEAD -- pnpm-lock.yaml` is empty) produced a different result:

- **Exact command**: `pnpm audit` (also confirmed with `pnpm audit --json` and `pnpm audit --audit-level=low`), run three times.
- **Current result**: `No known vulnerabilities found` — 0 findings at every severity, across all three runs.
- **Independent cross-check, not relying on `pnpm audit` alone**: `gh api "https://api.github.com/advisories?ecosystem=npm&affects=brace-expansion"` was queried directly against GitHub's advisory database for every known `brace-expansion` GHSA and its exact `vulnerable_version_range`. The lockfile (`pnpm-lock.yaml`) contains exactly three `brace-expansion` versions: `1.1.18`, `2.1.4`, and `5.0.9` (the last still reached via `minimatch@3.1.5 → brace-expansion: 1.1.18` for the 1.x line, confirmed present and unchanged in the lockfile snapshot). Checked against all six published advisories (`GHSA-mh99-v99m-4gvg`, `GHSA-3jxr-9vmj-r5cp`, `GHSA-jxxr-4gwj-5jf2`, `GHSA-f886-m6hf-6m8v`, `GHSA-v6h2-p8h4-qcjw`, `GHSA-832h-xg76-4gv6`), every one of the three installed versions falls **outside** every published vulnerable range (e.g. the 1.x-line advisories cap at `< 1.1.17`, and `1.1.18` clears all of them; the 2.x-line advisories cap at `< 2.1.3`, and `2.1.4` clears all of them; the 5.x-line advisories cap at `< 5.0.8`, and `5.0.9` clears all of them).
- **Package/upstream chain responsible**: `minimatch@3.1.5` (a transitive dependency of `@eslint/config-array`, itself a dependency of this project's ESLint flat-config tooling) resolves `brace-expansion@1.1.18` for its own internal use; `@redocly/openapi-core`/`openapi-typescript`'s chain resolves `2.1.4`; the workspace's own top-level/other tooling resolves `5.0.9`. None of these three resolutions were changed by this correction task.
- **Mandatory re-evaluation trigger**: re-run `pnpm audit` after any `pnpm-lock.yaml` change, any ESLint/`@eslint/config-array`/`openapi-typescript`/`@redocly/openapi-core` version bump, or before any release — advisory databases and transitive resolutions can both change independently of this project's own commits.

**Honest conclusion**: the live re-run and the independent GHSA range cross-check both indicate this specific finding no longer reproduces today. This does not mean the earlier record was fabricated — it was an accurate report of what `pnpm audit` returned at the time it was run, and the revert-after-break decision was the correct call given what was known then. **This correction task does not unilaterally reclassify F-P3-04 as closed** (per this task's explicit governing instruction); the owner should treat this section as new evidence to weigh when next reviewing the defect register, rather than as a closure declaration made on their behalf. No fabricated "zero vulnerabilities" claim is made at any point in this document — every number above is the direct, reproducible output of a named command, run and shown.
