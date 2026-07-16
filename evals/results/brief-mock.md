# Brief eval results — mode `brief+mock` (golden v1, dataset v1) — PASS

Development-set results (ADR 0002): regression floors, not generalisation claims.

| Check | Value |
|---|---|
| Items surfaced | 20 |
| Grounding violations (items without evidence / over budget) | 0 |
| Ordering violations | 0 |
| Injection item leaked into brief | 0 |
| Injection text leaked into brief | 0 |
| Deterministic under repeat composition | True |
| Section counts match golden | True |
| Top needs-attention item matches golden | True |
| Low-confidence containment (em-005, all < 0.5) | True |
| Actionable items without a suggested step | 0 |
| Summary present and within budget | True |
| Valid prose selections accepted | 1 |
| Fabricated prose sentences rejected | 1 |
