"""Vendor edge for Google integration (ADR 0003).

Only this package and the adapters/executors that sit directly on top of it
(`connectors/google_email.py`, `connectors/google_calendar.py`,
`action_executors.py`'s Google executors) may import from here. Domain
services (`action_proposal_service.py`, `extraction.py`,
`brief_composition.py`) never do — the same boundary the synthetic adapters
already respect (ADR 0001 D6).
"""
