# Stage 11A Phase 6A — Defect Register

**Date:** 2026-08-05

## D-6-02 (from Phase 6): CLOSED

Phase 6's defect register recorded D-6-02 as "residue cleaned, architectural fix deferred." This phase implements that deferred fix. `GOOGLE_OAUTH_INITIATION_ENABLED` — the single flag shared by OIDC sign-in and connector consent — is removed outright and replaced with two independent, fail-closed flags. Enabling either flow's flag is now structurally incapable of enabling the other, proven by a dedicated regression test reproducing the exact original incident (`test_signin_disabled_connector_enabled_the_exact_phase_6_incident_now_fixed`). **D-6-02 is closed, not merely contained.**

## No new product defect found

No new defect in shipped product code was found during this phase. One self-caught authoring mistake in this phase's own new test suite is recorded for transparency, not because it reached any shipped state:

- `test_provider_not_configured_blocks_both_regardless_of_per_flow_flags`'s first draft attempted to construct a `Settings` object with `google_oauth_enabled=False` and a per-flow flag `True` — a combination `main.py`'s own startup guard correctly rejects (confirmed working as designed by a separate, passing test). The test was rewritten to only exercise the actually-reachable state (provider unconfigured, both per-flow flags at their default `false`) before it was ever run as part of the suite; it did not cause a failing test to be reported as passing, and no code change was made to accommodate it.
