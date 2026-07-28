# LifeFlow AI Engineering Acceptance Contract

**Status:** binding, permanent · **Applies to:** every future LifeFlow delivery phase, regardless of which coding model performs the work · **Date:** 2026-07-27

This contract exists to eliminate repeated review-and-correction cycles between the coding agent and the human reviewer. It does not replace the phase specification, the stage-gated protocol ([stage-plan.md](stage-plan.md)), the North Star ([project-foundation.md](../project/project-foundation.md)), or any ADR — it governs how a coding agent turns a phase specification into a delivered, verified, reported phase.

Every future delivery-phase prompt should begin with the instruction in [§17](#17-future-phase-instruction).

---

## 1. Governing principle

A delivery phase is not complete merely because its main feature appears to work.

It is complete only when:

1. every requirement has been inventoried;
2. every requirement has an implementation or documented exemption;
3. every implementation has appropriate verification;
4. every required gate has actually run;
5. every discovered gap has been corrected;
6. all affected verification has been rerun;
7. the final repository boundary is clean and internally consistent;
8. the completion report is supported by current evidence.

The coding agent must iterate internally until these conditions are satisfied.

The agent must not hand ordinary engineering defects back to the user for another review cycle.

---

## 2. Authority order

When instructions overlap, use this order:

1. immutable LifeFlow safety invariants;
2. the current phase specification;
3. accepted architecture decisions and ADRs;
4. this Engineering Acceptance Contract;
5. AGENTS.md and CLAUDE.md;
6. existing repository conventions;
7. agent preference.

The agent must stop when two higher-authority requirements materially conflict and the correct resolution would require a product, privacy or architecture decision.

Do not silently choose between conflicting safety requirements.

---

## 3. Immutable LifeFlow invariants

Every phase must preserve:

- Gmail draft-only behaviour;
- Calendar create-only behaviour;
- no modification or deletion of existing Calendar events;
- exact proposal payload, version and account-context approval binding;
- durable pending execution before external provider calls;
- no automatic retry after an uncertain external outcome;
- PostgreSQL as the durable source of truth;
- Redis containing identifiers or privacy-safe ephemeral state only;
- owner scoping at the database query boundary;
- explicit preferences overriding inferred memory;
- distinct disconnect, imported-data deletion, memory deletion and account deletion semantics;
- preservation or minimisation of execution evidence required for uncertain reconciliation;
- no raw secrets, OAuth values, provider payloads or private content in logs, metrics, audit projections or Redis keys.

A phase cannot weaken an invariant merely to make a test pass.

---

## 4. Mandatory requirement inventory

Before implementation, convert the phase specification into a numbered acceptance matrix.

Use stable identifiers such as:

- P4-R001;
- P4-R002;
- P4-R003.

For each requirement record:

| Field | Meaning |
|---|---|
| Requirement ID | Stable phase-specific identifier |
| Requirement | Exact obligation |
| Category | Functional, security, privacy, test, UX, documentation or boundary |
| Implementation location | File, class, function or route |
| Verification | Test, command, query-plan proof, inspection or manual journey |
| Status | Not started, implemented, verified, exempted or blocked |
| Evidence | Exact current result |
| Notes | Constraints, historical limitations or safe fallback |

The matrix must include all:

- positive requirements;
- negative requirements;
- explicit exclusions;
- route or event inventories;
- test requirements;
- documentation obligations;
- Git-boundary requirements;
- security and privacy gates.

Do not treat exclusions as informal prose. Record and verify them.

Examples:

- "No migration 0012" must have a matrix row.
- "No raw metadata returned" must have a matrix row.
- "Delivery Phase 5 not begun" must have a matrix row.
- "No request is double-charged" must have a matrix row.

The matrix may live temporarily during implementation, but its final contents must be represented in the completion report or a committed phase report.

---

## 5. Closed-world inventory rule

Where the phase applies to a finite vocabulary, the agent must inventory the whole vocabulary rather than sample a few examples.

This includes, where applicable:

- HTTP routes;
- state-changing routes;
- AuditEvent types;
- rate-limit policies;
- execution outcomes;
- deletion-operation states;
- configuration keys;
- provider launch commands;
- frontend action surfaces;
- known error codes;
- migration heads;
- background jobs;
- external side-effect paths.

Every item must be:

1. supported;
2. intentionally hidden or exempted; or
3. classified as unreachable or deprecated with evidence.

Unknown or newly introduced items must fail closed where safety requires it.

---

## 6. Implementation loop

The coding agent must follow this loop autonomously:

### Step A — establish the boundary

Verify:

- repository path;
- current branch;
- current HEAD;
- required ancestor;
- remote references;
- working-tree status;
- staged state;
- untracked files;
- tags;
- migrations;
- generated-contract state.

Do not modify anything before the boundary is understood.

### Step B — inspect before designing

Read:

- AGENTS.md;
- CLAUDE.md;
- this contract;
- current phase prompt;
- relevant ADRs;
- prior phase reports;
- threat model;
- stage plan;
- affected implementation and tests.

Do not build a parallel abstraction when an existing repository mechanism already satisfies the need.

### Step C — implement the smallest coherent solution

Preserve existing safety architecture.

Avoid unrelated refactoring.

Do not implement later-phase features.

### Step D — run focused verification early

Run focused tests after each coherent slice.

Do not wait until the end to discover foundational defects.

### Step E — perform the requirement audit

Compare the actual implementation against every acceptance-matrix row.

Inspect the implementation itself, not only test names.

Classify each row:

- verified;
- incomplete;
- contradicted;
- untested;
- unavailable;
- intentionally omitted.

### Step F — close every ordinary gap

When a gap is found:

1. identify its root cause;
2. implement the smallest safe correction;
3. add regression coverage;
4. run focused verification;
5. rerun all affected broader gates;
6. update documentation and metrics;
7. update the matrix.

Continue until no ordinary gap remains.

Do not report back merely because the first implementation attempt finished.

---

## 7. What the agent must fix autonomously

The agent must fix these without requesting another review:

- failing tests;
- missing tests required by the phase specification;
- stale test counts;
- stale documentation;
- formatting drift;
- linting or type-checking failures;
- incomplete route or event classification;
- missing safe rendering for reachable states;
- accidental double application of middleware or dependencies;
- generated-contract drift;
- missing `.env.example` entries;
- incorrect documentation links;
- orphan test processes;
- untracked files omitted from security scans;
- flaky assertions caused by imprecise matching;
- stale metrics;
- incomplete launch-command coverage;
- an implementation that is safe but clearly fails an explicit usefulness requirement;
- verification commands that were listed but not actually run.

Do not ask the user whether these should be corrected. Correct them.

---

## 8. Legitimate stop conditions

Stop and request guidance only when at least one of these is true:

1. the current branch or required ancestor is wrong;
2. committed history appears to have been destructively rewritten;
3. credentials, private data or real user content are present;
4. the phase requires changing an immutable safety invariant;
5. two approved architecture decisions materially conflict;
6. a required migration was explicitly forbidden but evidence shows it is unavoidable;
7. implementation would require reopening a completed phase's product semantics rather than merely extending later functionality;
8. a necessary external provider, credential or infrastructure capability is unavailable and cannot be safely simulated;
9. completing the requirement would cross into a prohibited later phase;
10. the only way forward would discard or overwrite unexplained work;
11. a product-policy choice has multiple materially different, valid outcomes and the repository contains no approved decision.

A failing test is not a stop condition.

A missing test is not a stop condition.

An unexpectedly large implementation is not by itself a stop condition.

---

## 9. Evidence rules

Never report a gate as passed unless it ran successfully against the current implementation boundary.

The completion report must distinguish:

- run and passed;
- run and failed;
- not run;
- not applicable;
- blocked;
- inferred from inspection.

Do not carry old test counts forward.

Do not report "all tests pass" without exact numbers.

Do not report a remote workflow as passed when it did not trigger.

Do not claim an untracked file was covered by a staged or history scan unless the scanning method genuinely included it.

After any correction affecting implementation or tests:

- rerun focused tests;
- rerun affected integration tests;
- rerun static checks;
- rerun generated artefact checks;
- rerun the full suite when the change can affect broad behaviour.

---

## 10. Negative-control requirement

Security and boundary protections must be shown to detect the defect they are intended to prevent.

Where practical, temporarily introduce a safe, local negative control, confirm that the relevant test or validator fails, restore the correct implementation, and confirm it passes.

Examples:

- remove a required safe Uvicorn flag;
- add an unclassified route;
- add an unknown AuditEvent;
- introduce an invalid configuration override;
- modify a cursor;
- attempt owner-crossing pagination;
- insert a prohibited metadata value;
- exceed a Redis bucket concurrently;
- remove an approval-binding component;
- add an unclassified launcher.

Negative controls must:

- use synthetic data;
- be reverted immediately;
- never be committed;
- never weaken remote history;
- never involve real credentials or external side effects.

Record the result in the phase report.

---

## 11. Exact-boundary security proof

Before declaring implementation complete:

1. temporarily stage the complete intended boundary;
2. inspect the staged file list and diff;
3. confirm all intended untracked files are included;
4. run staged-diff checks and repository security hooks;
5. inspect secret allowlists;
6. remove timestamp-only baseline churn;
7. unstage everything when the phase instructions prohibit commit;
8. confirm the working tree is unchanged and the index is empty.

Security proof must cover:

- tracked modifications;
- new files;
- generated contracts;
- scripts;
- tests;
- documentation;
- configuration examples.

Never assume a full-history scan covers uncommitted files.

---

## 12. Completion conditions

The agent may issue a successful completion verdict only when all of the following are true:

### Requirements

- every acceptance-matrix row has a terminal status;
- no required row remains incomplete or untested;
- no prohibited later-phase feature is present;
- every explicit exclusion has been checked.

### Implementation

- the implementation matches the approved architecture;
- no unnecessary second source of truth exists;
- no private or secret value crosses an unsafe boundary;
- historical records degrade safely;
- unknown values fail closed where required.

### Tests

- focused tests pass;
- full regression tests pass;
- real PostgreSQL or Redis tests run where required;
- browser journeys pass the required number of times;
- concurrency tests pass;
- negative controls have been demonstrated where appropriate.

### Quality

- type checking passes;
- linting passes;
- formatting passes;
- production build passes;
- generated contracts are fresh;
- migration state is correct;
- metrics are regenerated and truthful.

### Security

- pre-commit passes;
- detect-secrets passes;
- private-key detection passes;
- `.env.example` validation passes;
- staged additions pass Gitleaks or equivalent;
- full history passes Gitleaks;
- no temporary artefacts are included.

### Git boundary

- required ancestor remains intact;
- no prohibited commit, tag, push or merge occurred;
- working tree and index have the required final state;
- no unexpected untracked file remains;
- remote claims match actual remote evidence.

A successful verdict is forbidden when any mandatory condition above remains unknown.

---

## 13. Completion report requirement

Return one comprehensive report only after the internal implementation and verification loop has converged.

The report must include:

```text
## Executive verdict
## Git boundary
## Requirement traceability summary
## Complete inventory
## Architecture and implementation
## Safety and privacy invariants
## Tests added
## Negative controls
## Full verification results
## Security proof
## Migration and contract state
## Documentation and metrics
## Known limitations
## Explicit exclusions
## Files changed
## Working-tree and index status
## Commit, push and tag status
## Next-phase status
## Recommended commit split
```

The executive verdict must be exactly one of:

- APPROVE DELIVERY PHASE FOR REVIEW
- CONDITIONAL APPROVAL
- BLOCK DELIVERY PHASE

Use APPROVE only when all mandatory acceptance conditions are satisfied.

For every limitation, classify it as:

- accepted historical limitation;
- intentional safe omission;
- future-phase work;
- blocking defect.

Do not use "conditional approval" merely because work is uncommitted when the phase explicitly required it to remain uncommitted.

---

## 14. No premature handback

Do not end the task with language such as:

- "Let me know whether you want me to fix this."
- "I found these gaps; shall I continue?"
- "The main implementation is done, but some tests remain."
- "Everything looks good except formatting."
- "The report is ready, although one required evaluation was not run."

When the issue is an ordinary engineering gap, continue working.

Report back only when:

- the phase genuinely satisfies the contract; or
- a legitimate stop condition applies.

---

## 15. Review-stage separation

There are three distinct stages:

### Implementation review

The agent implements and internally iterates until all conditions are green.

No commit, push or tag occurs unless explicitly authorised.

### Commit review

After human approval, the agent creates the approved commit structure and reruns verification against the assembled committed boundary.

### Remote finalisation

After human approval, the agent pushes the approved branch, verifies remote references and workflows honestly, and prepares the next branch without starting implementation.

Do not blend these stages.

---

## 16. Model handoff

When one coding model takes over from another:

- inspect actual repository state;
- preserve valid work;
- do not trust the previous model's unverified narrative;
- rerun required gates;
- map existing changes to the acceptance matrix;
- continue the internal correction loop;
- do not restart merely to impose a different coding style;
- do not discard untracked files before inspection.

The repository is the source of truth.

---

## 17. Future phase instruction

Every future phase prompt should begin with:

> Follow docs/delivery/engineering-acceptance-contract.md. Build a numbered acceptance matrix from this specification. Continue implementing, testing, auditing and correcting autonomously until every mandatory row is verified. Do not report ordinary gaps for another review cycle. Report only when all conditions are satisfied or a legitimate stop condition in the contract applies.
