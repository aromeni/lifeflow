# @lifeflow/web

LifeFlow AI frontend — Next.js (App Router, TypeScript, Tailwind).

All commands run from the repository root (see the root [README](../../README.md) for full setup):

```bash
pnpm web:dev          # dev server on http://localhost:3000
pnpm web:test         # Vitest + React Testing Library
pnpm web:lint         # ESLint
pnpm web:typecheck    # tsc --noEmit
pnpm web:format       # Prettier
pnpm web:build        # production build
```

`/health` is the app's liveness endpoint. Playwright E2E tests arrive with the first real user flows (Stage 3).
