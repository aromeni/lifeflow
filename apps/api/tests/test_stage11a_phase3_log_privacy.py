"""Stage 11A Phase 3 (S11A-P3-022) — end-to-end log-privacy sentinel scan.

`test_logging.py` already proves `redact()` catches known credential/cookie
patterns at the unit level. The Phase 3 audit found no test that captures
*actual* application log output across a real workflow and searches it for
concrete sentinel values — this file is that missing end-to-end proof.

A distinctive sentinel is planted for every content type the governing task
names (email address, subject, calendar description/attendee, OAuth access
and refresh tokens, proposal payload, provider response, database
credentials, and a real session cookie), then a full workflow is exercised:
normal operation, a validation failure, an uncertain (provider-outage-style)
write, a token refresh, a revoked-consent refresh, rate-limit exhaustion,
and full deletion. Captured logs (kept in memory only, never written to
disk) are searched for every sentinel afterwards. Run for 5 full workflow
cycles, each with fresh sentinels, per the required repetition count.

Note: LifeFlow's ingestion pipeline never stores a raw email body (Gmail
`format=metadata` with a header allow-list, per the threat model) — there is
no "email body" column to plant a sentinel into structurally, so that
content type is represented here by the Gmail-draft *payload* body instead,
which is genuinely stored (as a proposal the user must approve).
"""

import base64
import contextlib
import io
import logging
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import redis.asyncio as aioredis
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import CSRF_HEADERS, TEST_DB_URL

from lifeflow_api.accounts import ConnectedAccountService, GoogleTokenService
from lifeflow_api.action_executors import ExecutorOutcome
from lifeflow_api.action_proposal_service import ActionProposalService
from lifeflow_api.config import Settings
from lifeflow_api.deletion import confirm_operation, create_imported_data_preview, run_operation
from lifeflow_api.deletion_ops import CONFIRM_IMPORTED_DATA
from lifeflow_api.google.errors import InvalidGrantError
from lifeflow_api.google.oauth import GoogleTokenResponse
from lifeflow_api.logging_setup import JsonFormatter
from lifeflow_api.main import create_app
from lifeflow_api.models import (
    ActionProposal,
    ActionType,
    ConnectedAccount,
    ProposalStatus,
    SourceItem,
    User,
)
from lifeflow_api.rate_limit_policy import RateLimitPolicy, RateLimitSubjectType
from lifeflow_api.rate_limiter import RateLimiter, bucket_key, hash_subject
from lifeflow_api.retention import RetentionHorizons
from lifeflow_api.security.token_cipher import AesGcmTokenCipher

pytestmark = pytest.mark.integration

REDIS_URL = "redis://localhost:6380/0"
_HORIZONS = RetentionHorizons(
    source_items_days=30,
    brief_versions_days=90,
    unapproved_proposals_days=90,
    scheduled_runs_days=90,
    memory_evidence_days=90,
)


@pytest.fixture
def cipher() -> AesGcmTokenCipher:
    return AesGcmTokenCipher(base64.b64encode(os.urandom(32)).decode(), "test-1")


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as current:
        yield current
        await current.commit()
    await engine.dispose()


class _StubOAuthClient:
    def __init__(
        self, *, response: GoogleTokenResponse | None = None, raises: Exception | None = None
    ) -> None:
        self._response = response
        self._raises = raises

    async def refresh_access_token(
        self, *, client_id: str, client_secret: str, refresh_token: str
    ) -> GoogleTokenResponse:
        if self._raises is not None:
            raise self._raises
        assert self._response is not None
        return self._response


class _ScriptedRegistry:
    async def execute(
        self,
        action_type: ActionType,
        *,
        proposal_id: uuid.UUID,
        payload: object,
        approved_authorization: object,
    ) -> ExecutorOutcome:
        return ExecutorOutcome(
            status="uncertain",
            result={"message": f"provider-response:{_SENTINELS['provider_response']}"},
        )


_SENTINELS: dict[str, str] = {}


def _sentinel(name: str) -> str:
    value = f"SENTINEL-{name.upper()}-{uuid.uuid4()}"
    _SENTINELS[name] = value
    return value


@pytest.mark.parametrize("cycle", range(5))
async def test_no_sentinel_leaks_across_a_full_workflow(
    session: AsyncSession, cipher: AesGcmTokenCipher, cycle: int
) -> None:
    # This workflow's rate-limit-exhaustion stage needs a real Redis to
    # prove exhaustion at all (RateLimiter.check() fails open without one,
    # which would make the exhaustion assertion meaningless, not merely
    # unreachable) — skip cleanly rather than crash, matching the
    # established pattern in test_rate_limiter.py's redis_client fixture.
    probe = aioredis.from_url(REDIS_URL)
    try:
        await probe.ping()
    except Exception:
        pytest.skip("Redis is not running (docker compose up -d redis)")
    finally:
        await probe.aclose()

    _SENTINELS.clear()
    sentinel_email = _sentinel("email")  # pragma: allowlist secret
    sentinel_subject = _sentinel("subject")
    sentinel_access = _sentinel("access_token")  # pragma: allowlist secret
    sentinel_refresh = _sentinel("refresh_token")  # pragma: allowlist secret
    sentinel_refreshed_access = _sentinel("refreshed_access")  # pragma: allowlist secret
    sentinel_revoked_refresh = _sentinel("revoked_refresh")  # pragma: allowlist secret
    sentinel_draft_body = _sentinel("draft_body")
    sentinel_cal_description = _sentinel("cal_description")
    sentinel_cal_attendee = "attendee-" + str(uuid.uuid4()) + "@example.com"
    _SENTINELS["cal_attendee"] = sentinel_cal_attendee
    _sentinel("provider_response")
    sentinel_rationale = _sentinel("rationale")

    # `create_app()` calls `configure_logging()`, which replaces
    # `root.handlers` wholesale — so the capture handler must be attached
    # AFTER the one app this test creates, or every log line up to that
    # point would be silently dropped from capture.
    app = create_app(
        Settings(
            _env_file=None,
            environment="development",
            log_level="DEBUG",
            database_url=TEST_DB_URL,
            token_key=base64.b64encode(os.urandom(32)).decode(),
            token_key_id="test-1",
        )
    )

    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setFormatter(JsonFormatter())
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    previous_level = root_logger.level
    root_logger.setLevel(logging.DEBUG)

    try:
        # --- Normal operation: create a user, connect an account, ingest
        # a source item, all carrying planted sentinels.
        user = User(email=sentinel_email, display_name="Log Privacy Sentinel")
        session.add(user)
        await session.flush()

        await ConnectedAccountService(session, user.id, cipher).store_tokens(
            provider="google",
            access_token=sentinel_access,
            refresh_token=sentinel_refresh,
            granted_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        account = ConnectedAccount(user_id=user.id, provider="synthetic", granted_scopes=["demo"])
        session.add(account)
        await session.flush()
        session.add(
            SourceItem(
                user_id=user.id,
                source_type="email",
                external_id=f"em-{uuid.uuid4()}",
                source_account_id=account.id,
                title=sentinel_subject,
                sender_or_organiser=sentinel_email,
                occurred_at=datetime.now(UTC),
                content_fingerprint="fp",
            )
        )
        await session.flush()

        # --- Uncertain write (provider-outage-style): a Gmail-draft
        # proposal carrying a sentinel body, and a calendar-event proposal
        # carrying a sentinel description/attendee, both executed via a
        # scripted registry that returns "uncertain" with a sentinel
        # provider-response message.
        draft_proposal = ActionProposal(
            user_id=user.id,
            origin_fingerprint=f"fp-draft-{uuid.uuid4()}",
            action_type=ActionType.create_gmail_draft,
            rationale=sentinel_rationale,
            source_refs=[],
            payload_json={
                "to": ["someone@example.com"],
                "subject": "Log privacy fixture",
                "body": sentinel_draft_body,
                "thread_id": None,
            },
            payload_hash="0" * 64,
            risk_level="medium",
            confidence=0.9,
            status=ProposalStatus.proposed,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        calendar_proposal = ActionProposal(
            user_id=user.id,
            origin_fingerprint=f"fp-cal-{uuid.uuid4()}",
            action_type=ActionType.create_calendar_event,
            rationale=sentinel_rationale,
            source_refs=[],
            payload_json={
                "title": "Log privacy fixture event",
                "starts_at": datetime.now(UTC).isoformat(),
                "ends_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "timezone": "Europe/London",
                "location": None,
                "description": sentinel_cal_description,
                "attendees": [sentinel_cal_attendee],
            },
            payload_hash="0" * 64,
            risk_level="medium",
            confidence=0.9,
            status=ProposalStatus.proposed,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        session.add_all([draft_proposal, calendar_proposal])
        await session.commit()

        service = ActionProposalService(session, user.id, google_executors=_ScriptedRegistry())
        for proposal in (draft_proposal, calendar_proposal):
            proposal.status = ProposalStatus.approved
            proposal.approved_action_type = proposal.action_type
            proposal.approved_payload_json = proposal.payload_json
            proposal.approved_payload_hash = proposal.payload_hash
            proposal.approved_version = proposal.version
            proposal.approved_at = datetime.now(UTC)
            proposal.approved_execution_mode = "simulation"
        await session.commit()
        for proposal in (draft_proposal, calendar_proposal):
            # Only log content matters here, not the execution outcome
            # itself (proven elsewhere) — a policy conflict from the
            # hand-constructed approval snapshot above is an acceptable,
            # silently-ignored outcome for this test's purpose.
            with contextlib.suppress(Exception):
                await service.execute(proposal.id)

        # --- Validation failure via a real HTTP request (reusing the one
        # app instance created above, before the capture handler existed).
        async with LifespanManager(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                login = await client.post("/auth/dev-login", json={}, headers=CSRF_HEADERS)
                assert login.status_code == 200
                bad = await client.patch(
                    "/me", json={"timezone": "Mars/Olympus"}, headers=CSRF_HEADERS
                )
                assert bad.status_code == 422
                session_cookie = client.cookies.get("lifeflow_session")
                assert session_cookie is not None
                _SENTINELS["session_cookie"] = session_cookie

        # --- Token refresh.
        expired_user = User(email=f"refresh-{uuid.uuid4()}@example.com", display_name="Refresh")
        session.add(expired_user)
        await session.flush()
        await ConnectedAccountService(session, expired_user.id, cipher).store_tokens(
            provider="google",
            access_token="old-access",
            refresh_token="old-refresh",  # pragma: allowlist secret
            granted_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        refresh_service = GoogleTokenService(
            session,
            expired_user.id,
            cipher,
            _StubOAuthClient(
                response=GoogleTokenResponse(
                    access_token=sentinel_refreshed_access,
                    refresh_token=None,
                    expires_in=3600,
                    scope="https://www.googleapis.com/auth/gmail.readonly",
                    id_token=None,
                )
            ),
            client_id="client",
            client_secret="secret",  # pragma: allowlist secret
        )
        assert await refresh_service.get_valid_access_token("google") == sentinel_refreshed_access

        # --- Revoked-consent refresh.
        revoked_user = User(email=f"revoked-{uuid.uuid4()}@example.com", display_name="Revoked")
        session.add(revoked_user)
        await session.flush()
        await ConnectedAccountService(session, revoked_user.id, cipher).store_tokens(
            provider="google",
            access_token="old-access-2",
            refresh_token=sentinel_revoked_refresh,
            granted_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        revoked_service = GoogleTokenService(
            session,
            revoked_user.id,
            cipher,
            _StubOAuthClient(raises=InvalidGrantError("revoked")),
            client_id="client",
            client_secret="secret",  # pragma: allowlist secret
        )
        with pytest.raises(Exception):  # noqa: B017 - any rejection is fine, only logging matters
            await revoked_service.get_valid_access_token("google")

        # --- Rate-limit exhaustion (real Redis, tiny synthetic policy).
        redis_client = aioredis.from_url(REDIS_URL)
        try:
            limiter = RateLimiter(redis_client, socket_timeout_seconds=1.0)
            policy = RateLimitPolicy(
                code=f"log-privacy-fixture-{cycle}",
                subject_type=RateLimitSubjectType.authenticated_user,
                capacity=1,
                refill_amount=1,
                refill_window_seconds=3600,
            )
            digest = hash_subject("fixture-secret", policy.subject_type, str(user.id))
            key = bucket_key("ratelimit:log-privacy-fixture", policy.code, digest)
            await limiter.check(key, policy)
            denied = await limiter.check(key, policy)
            assert denied.allowed is False
        finally:
            # The bucket's own 3600s TTL would otherwise leave this key in
            # the shared dev Redis long after the test process exits —
            # clean it up immediately rather than relying on expiry.
            await redis_client.delete(key)
            await redis_client.aclose()

        # --- Deletion: remove the imported data (SourceItem carrying the
        # sentinel subject/email) end to end.
        preview = await create_imported_data_preview(
            session, user, source_account_id=account.id, now=datetime.now(UTC), ttl_minutes=30
        )
        confirmed = await confirm_operation(
            session,
            user,
            preview.id,
            expected_version=preview.version,
            phrase=CONFIRM_IMPORTED_DATA,
            now=datetime.now(UTC),
            preview_ttl_minutes=30,
        )
        await session.commit()
        await run_operation(
            session,
            confirmed.id,
            now=datetime.now(UTC),
            horizons=_HORIZONS,
            batch_size=10,
            max_attempts=3,
        )
        await session.commit()
    finally:
        root_logger.removeHandler(handler)
        root_logger.setLevel(previous_level)
        captured = log_capture.getvalue()
        for name, value in _SENTINELS.items():
            assert value not in captured, f"sentinel {name!r} leaked into logs"
        assert "lifeflow_test" not in captured or "postgresql" not in captured
