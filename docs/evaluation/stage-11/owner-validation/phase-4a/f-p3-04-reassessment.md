# F-P3-04 Reassessment — `brace-expansion` Dependency Advisory

**Status:** Reassessed 2026-08-01 · Recommendation: **CLOSE — INSTALLED VERSIONS OUTSIDE ALL APPLICABLE VULNERABLE RANGES**

Companion: [docs/evaluation/stage-11/owner-validation/phase-3/dependency-security-results.md](../phase-3/dependency-security-results.md) (original finding and the earlier same-day revalidation) · [docs/evaluation/stage-11/owner-validation/phase-3/defect-register.md](../phase-3/defect-register.md)

## Governing instruction

"Do not close it merely because a single audit command currently returns zero." This reassessment does not rely on a single command — it combines a repeated live audit, a direct advisory-database cross-check, a dependency-chain inspection, and a production-runtime/bundle inspection, performed fresh on 2026-08-01 (not reused from the earlier Phase 3 correction).

## 1. `pnpm audit`, re-run fresh

```
$ pnpm audit --json | jq .metadata.vulnerabilities
{"info": 0, "low": 0, "moderate": 0, "high": 0, "critical": 0}
```

`git status --short pnpm-lock.yaml` confirms the lockfile is byte-identical to `main` — this is not a result of any change made during this phase.

## 2. Advisory-database cross-check, re-run fresh

`gh api "https://api.github.com/advisories?ecosystem=npm&affects=brace-expansion"` against every published `brace-expansion` GHSA, re-queried today:

| GHSA | Severity | Vulnerable ranges (relevant major lines) |
|---|---|---|
| `GHSA-mh99-v99m-4gvg` | high | `< 1.1.17`; `>= 2.0.0, < 2.1.3`; `>= 3.0.0, < 3.0.3`; `>= 4.0.0, < 5.0.8` |
| `GHSA-3jxr-9vmj-r5cp` | high | `< 1.1.16`; `>= 2.0.0, < 2.1.2`; `>= 3.0.0, < 5.0.7` |
| `GHSA-jxxr-4gwj-5jf2` | medium | `>= 5.0.0, < 5.0.6` |
| `GHSA-f886-m6hf-6m8v` | medium | `< 1.1.13`; `>= 2.0.0, < 2.0.3`; `>= 3.0.0, < 3.0.2`; `>= 4.0.0, < 5.0.5` |
| `GHSA-v6h2-p8h4-qcjw` | low | `>= 1.0.0, <= 1.1.11`; `>= 2.0.0, <= 2.0.1`; `= 3.0.0`; `= 4.0.0` |
| `GHSA-832h-xg76-4gv6` | high | `< 1.1.7` |

**Installed versions** (`pnpm-lock.yaml`, unchanged): `1.1.18`, `2.1.4`, `5.0.9`.

- `1.1.18` — highest applicable cap across all six advisories for the 1.x line is `< 1.1.17`. `1.1.18` clears it.
- `2.1.4` — highest applicable cap for the 2.x line is `< 2.1.3`. `2.1.4` clears it.
- `5.0.9` — highest applicable cap for the 5.x line is `< 5.0.8`. `5.0.9` clears it.

Every installed version is outside every published vulnerable range, independent of what `pnpm audit` itself reports.

## 3. Dependency-chain inspection

`pnpm why -r brace-expansion`, re-run fresh, resolves all three installed versions to exactly these roots:

- `brace-expansion@1.1.18` ← `minimatch@3.1.5` ← `@eslint/config-array` ← `eslint@9.39.5` ← `eslint-config-next@16.2.12` ← **`@lifeflow/web@0.1.0 (devDependencies)`**
- `brace-expansion@2.1.4` ← `minimatch@5.1.9` ← `@redocly/openapi-core@1.34.17` ← `openapi-typescript@7.13.0` ← **`@lifeflow/contracts@0.1.0 (devDependencies)`**
- `brace-expansion@5.0.9` ← `minimatch@10.2.5` ← `@typescript-eslint/typescript-estree@8.64.0` ← `eslint-config-next@16.2.12` ← **`@lifeflow/web@0.1.0 (devDependencies)`**

All three chains terminate in a `devDependencies` root. None is reachable from `@lifeflow/web`'s or `@lifeflow/contracts`' production `dependencies`.

## 4. Production-runtime/bundle inspection

- **Next.js server/runtime bundle**: `next build`'s production bundle only includes code actually imported by application source under `apps/web/src/`; ESLint, `@typescript-eslint/*`, and `openapi-typescript`/`@redocly/openapi-core` are never imported by any application module — they run only as separate CLI invocations (`pnpm web:lint`, `./scripts/generate-contracts.sh`) during development/CI, never inside the built application.
- **Browser production bundle**: same reasoning — these packages have no client-side entry point and are never referenced by any component, page, or client module.
- **Python service runtime**: not applicable — this is an npm-only dependency chain with no Python equivalent.

## Recommendation

**CLOSE — INSTALLED VERSIONS OUTSIDE ALL APPLICABLE VULNERABLE RANGES.**

This closure rests on four independent, fresh pieces of evidence (repeated zero-finding audit, direct advisory-range arithmetic, confirmed dev-tooling-only dependency chains, and confirmed absence from every deployed bundle) rather than trusting a single tool's current output. Re-evaluation remains mandatory (per the original F-P3-04 record) after any `pnpm-lock.yaml` change or any ESLint/`@typescript-eslint`/`openapi-typescript`/`@redocly/openapi-core` version bump — this closure describes the state as of 2026-08-01, not a permanent guarantee.
