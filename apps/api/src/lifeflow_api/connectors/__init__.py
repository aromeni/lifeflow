"""Connector interfaces and adapters.

Domain services depend on the protocols in `interfaces.py`, never on vendor
SDKs (ADR 0001 D6). Synthetic adapters (Stage 3) and Google adapters
(Stage 7) implement the same contracts.
"""
