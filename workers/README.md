# workers

Background job entry points (scheduled briefs, retention). Populated at Stage 8 per ADR 0001 (D2). Jobs call domain services in `apps/api`; no business logic lives here.
