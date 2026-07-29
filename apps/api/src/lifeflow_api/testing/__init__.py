"""Test-only support code (Stage 9 Delivery Phase 5, §20). Nothing under
this package is imported by the production application (`main.py`) — it
exists purely for Playwright's resilience journeys and refuses to run
outside that context (see `fake_google_server.py`'s own startup guard)."""
