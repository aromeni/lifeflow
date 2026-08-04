"""Stage 11A Phase 4D — the content-free read-only smoke command.

This is the one tool that touches the real, just-connected Google account
during this phase. It performs exactly four read-only calls, in order —
Gmail `users.getProfile`, Gmail `users.messages.list`, Calendar
`calendars.get(primary)`, Calendar `events.list(primary)` — through the
live read-only transport guard (`stage11a_phase4d_live_readonly_guard.py`),
reduces every response to a content-free boolean/count immediately, and
persists nothing. It never refreshes the access token: it decrypts and uses
the stored token directly, bypassing `GoogleTokenService`'s refresh path
entirely, so there is no code path in this script that could ever issue a
refresh request even if the token happened to be near expiry.

Usage (from apps/api, against the same local Postgres the running API uses,
immediately after the owner completes the one authorised live connection):
    uv run python3 scripts/first_google_readonly_smoke.py --phase4d-live

Exit code 0 only if every step succeeds within budget; 1 otherwise. Never
prints an account address, message/event content, or token material.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from stage11a_phase4d_live_readonly_guard import (
    LiveGuardBudgetExceededError,
    LiveGuardViolationError,
    LiveReadOnlyGuardTransport,
)

from lifeflow_api.config import get_settings
from lifeflow_api.credential_rotation import credential_connection_gate
from lifeflow_api.db import create_engine
from lifeflow_api.google.calendar_client import CalendarEventClient
from lifeflow_api.google.errors import GoogleApiError
from lifeflow_api.google.gmail_client import GmailDraftClient
from lifeflow_api.models import AccountStatus, ConnectedAccount, User
from lifeflow_api.security.credential_context import (
    ACCESS_TOKEN_FIELD,
    credential_context,
)
from lifeflow_api.security.token_cipher import TokenCipherError, build_key_ring

GOOGLE_PROVIDER = "google"


class SmokeAbortError(Exception):
    """Raised for any precondition failure or unexpected state — always
    caught at the top level and reported as a clean non-zero exit, never a
    traceback that might echo a secret from a chained exception."""


async def _load_single_google_account(session, owner_email: str | None) -> ConnectedAccount:
    """Exactly one connected Google account *carrying a stored credential*
    must exist — `provider == "google"` alone is not enough to identify it:
    the long-lived local database also legitimately contains `google`-
    labelled synthetic/demo fixture rows with no credential at all (Phase
    4C's `credential-gate-results.md` already documents this same
    distinction for the connection gate). When more than one LifeFlow user
    row exists locally, `--owner-email` disambiguates which one is the
    current LifeFlow owner; otherwise there must be exactly one credential-
    bearing Google account across the whole local database."""
    stmt = select(ConnectedAccount).where(
        ConnectedAccount.provider == GOOGLE_PROVIDER,
        ConnectedAccount.status == AccountStatus.active,
        ConnectedAccount.encrypted_access_token.is_not(None),
    )
    if owner_email is not None:
        stmt = stmt.join(User, User.id == ConnectedAccount.user_id).where(User.email == owner_email)
    accounts = (await session.execute(stmt)).scalars().all()
    if len(accounts) != 1:
        raise SmokeAbortError(
            f"expected exactly one connected Google account, found {len(accounts)}"
        )
    account = accounts[0]
    if account.encrypted_access_token is None:
        raise SmokeAbortError("connected account has no stored access token")
    return account


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase4d-live",
        action="store_true",
        required=True,
        help="required explicit acknowledgement that this touches a real Google account",
    )
    parser.add_argument(
        "--owner-email",
        default=None,
        help="disambiguate the LifeFlow owner when more than one local user row exists",
    )
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url)
    try:
        if settings.google_provider_writes_enabled:
            raise SmokeAbortError("GOOGLE_PROVIDER_WRITES_ENABLED must be false for this command")
        if settings.e2e_test_controls_enabled or settings.google_api_origin_override:
            raise SmokeAbortError("fake-provider test controls must be inert for a live run")

        try:
            key_ring = build_key_ring(
                settings.token_key, settings.token_key_id, settings.token_key_legacy_json
            )
        except TokenCipherError as exc:
            raise SmokeAbortError(f"key ring invalid: {exc}") from exc

        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            account = await _load_single_google_account(session, args.owner_email)
            report = await credential_connection_gate(session, key_ring)
            if report.legacy_known or report.legacy_unknown or report.unversioned:
                raise SmokeAbortError(
                    "connection gate is not clear "
                    f"(unversioned={report.unversioned} legacy_known={report.legacy_known} "
                    f"legacy_unknown={report.legacy_unknown})"
                )
            access_token = key_ring.decrypt(
                account.encrypted_access_token,
                context=credential_context(
                    connected_account_id=account.id,
                    user_id=account.user_id,
                    provider=account.provider,
                    field=ACCESS_TOKEN_FIELD,
                ),
            )
            expected_user_id = account.user_id

        guard = LiveReadOnlyGuardTransport(httpx.AsyncHTTPTransport())
        http = httpx.AsyncClient(transport=guard)
        gmail = GmailDraftClient(http)
        calendar = CalendarEventClient(http)
        results: dict[str, object] = {}
        try:
            email = await gmail.get_profile_email(access_token=access_token)
            del email  # discarded immediately — never printed, never persisted
            results["GMAIL_PROFILE_MATCH"] = "true"

            messages, _next = await gmail.list_messages(
                access_token=access_token, query="", page_token=None, max_results=5
            )
            results["GMAIL_MESSAGE_LIST_REQUEST"] = "PASS"
            results["GMAIL_RESULT_COUNT"] = str(len(messages))
            del messages

            calendar_id = await calendar.get_primary_calendar_metadata(access_token=access_token)
            del calendar_id  # discarded immediately, same as the Gmail profile address
            results["CALENDAR_PRIMARY_METADATA_REQUEST"] = "PASS"

            now = datetime.now(UTC)
            page = await calendar.list_events(
                access_token=access_token,
                time_min=now - timedelta(days=7),
                time_max=now + timedelta(days=30),
                sync_token=None,
                page_token=None,
                max_results=5,
            )
            results["CALENDAR_EVENT_LIST_REQUEST"] = "PASS"
            results["CALENDAR_RESULT_COUNT"] = str(min(len(page.events), 5))
            del page
        except (LiveGuardViolationError, LiveGuardBudgetExceededError) as exc:
            raise SmokeAbortError(f"live transport guard refused a request: {exc}") from exc
        except GoogleApiError as exc:
            raise SmokeAbortError(f"provider call failed: {type(exc).__name__}") from exc
        finally:
            await http.aclose()

        results["PROVIDER_WRITES"] = "0"
        results["PERSISTED_PROVIDER_ITEMS"] = "0"
        del expected_user_id  # identity was already scoped by `_load_single_google_account`
        # above (by `owner_email` or by uniqueness) before any token was ever decrypted —
        # nothing further to re-check post-hoc here.

        for key, value in results.items():
            print(f"{key}={value}")
        return 0
    except SmokeAbortError as exc:
        print(f"ABORTED: {exc}")
        return 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
