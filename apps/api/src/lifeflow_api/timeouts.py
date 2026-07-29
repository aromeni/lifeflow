"""Stage 9 Delivery Phase 5 — the central timeout policy.

Every network call the app makes (Google, PostgreSQL, Redis-adjacent health
pings) must use a finite, validated, centrally-configured timeout — never a
magic number hand-rolled at the call site. `config.py` owns the validated
settings (all `Field(gt=0)`, so a misconfigured non-positive value fails
startup, never silently disables a timeout); this module turns them into
the shapes each client library actually wants.

A local timeout on a *write* (Gmail draft creation, Calendar event
insertion) never means "the write didn't happen" — Google may still be
processing the request when the local socket gives up. Callers must treat a
write-path timeout as `GoogleTransientError` (uncertain), exactly like a
connection error, never as `GoogleClientError` (final) and never by
retrying the write automatically (see `retry.py`).
"""

from __future__ import annotations

import httpx

from lifeflow_api.config import Settings


def google_httpx_timeout(settings: Settings) -> httpx.Timeout:
    """A read-optimised timeout for GET-heavy Google clients (Gmail/Calendar
    list+get, OAuth token exchange/refresh). Write call sites that need the
    longer write budget pass `google_httpx_write_timeout` instead when
    constructing their own request (see `google/gmail_client.py::create_draft`
    and `google/calendar_client.py::insert_event`)."""
    return httpx.Timeout(
        connect=settings.google_connect_timeout_seconds,
        read=settings.google_read_timeout_seconds,
        write=settings.google_read_timeout_seconds,
        pool=settings.google_connect_timeout_seconds,
    )


def google_httpx_write_timeout(settings: Settings) -> httpx.Timeout:
    return httpx.Timeout(
        connect=settings.google_connect_timeout_seconds,
        read=settings.google_write_timeout_seconds,
        write=settings.google_write_timeout_seconds,
        pool=settings.google_connect_timeout_seconds,
    )


def database_statement_timeout_ms(settings: Settings) -> str:
    """A PostgreSQL `statement_timeout` value in milliseconds, as a string
    (the format `asyncpg`/`server_settings` expects)."""
    return str(int(settings.database_statement_timeout_seconds * 1000))


__all__ = ["database_statement_timeout_ms", "google_httpx_timeout", "google_httpx_write_timeout"]
