# Stage 11A Phase 6A — Configuration Truth Table

**Date:** 2026-08-05 · All scenarios verified by dedicated tests in `test_stage11a_phase6a_oauth_control_separation.py`, against local mock transports only.

| Provider configured | Sign-in enabled | Connector enabled | Sign-in initiation | Sign-in callback | Connector initiation | Connector callback | Test |
|---|---|---|---|---|---|---|---|
| true | false | false | Blocked (409) | Blocked (409) | Blocked (409) | Blocked (409) | `test_both_flows_disabled_blocks_both` |
| true | true | false | Available (302) | Available | Blocked (409) | Blocked (409) | `test_signin_enabled_connector_disabled` |
| true | false | true | **Blocked (409)** | **Blocked (409)** | Available (302) | Available | `test_signin_disabled_connector_enabled_the_exact_phase_6_incident_now_fixed` |
| true | true | true | Available | Available | Available | Available | `test_both_flows_enabled_both_available_and_still_isolated` |
| false | (unreachable — see below) | (unreachable) | Blocked (404) | — | Blocked (404) | — | `test_provider_not_configured_blocks_both_regardless_of_per_flow_flags` |

**Row 3 is the exact Phase 6 incident, reproduced and confirmed fixed**: connector consent enabled, sign-in deliberately left disabled — sign-in initiation is now blocked before any redirect or state creation, exactly the opposite of what happened during Phase 6 itself.

**Row 5 note:** `provider not configured` with a per-flow flag `true` is not merely blocked at the route — it's rejected outright at application startup (`test_malformed_configuration_fails_startup_for_each_flag`), a strictly stronger guarantee. The row above reflects the only state actually reachable at runtime: provider unconfigured with both per-flow flags at their default `false`.

## Independence, checked in both directions

| Test | Proves |
|---|---|
| `test_connector_enablement_never_enables_signin` | Connector enabled + sign-in disabled → sign-in initiation *and* callback both blocked |
| `test_signin_enablement_never_enables_connector` | Sign-in enabled + connector disabled → connector initiation *and* callback both blocked |

No redirect, state generation, code exchange, token storage, or account binding occurs on any blocked route in any scenario — verified directly: every blocked response asserts no `location` header, and the mock transport function itself raises `AssertionError` if ever invoked in a blocked scenario (`test_stage11a_phase4c_oauth_initiation_block.py`'s `transport_calls == 0` assertions).
