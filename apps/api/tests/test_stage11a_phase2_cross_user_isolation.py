"""Stage 11A Phase 2 (docs/delivery/stage-11a-phase-2-plan.md), scenarios
S11A-P2-028 through 031: cross-user isolation specifically under failure
conditions — extends the existing structural isolation proof
(`test_ownership.py`) with behavioural proof for the four failure-adjacent
mechanisms this phase covers: rate-limiter bucket exhaustion, an uncertain
execution, concurrent OAuth token refresh, and the stale-deletion-operation
recovery sweep (which is deliberately cross-user *by necessity* at the query
level — `deletion.py::recover_stale_operations`'s own docstring — so what
must be proven here is that its per-row *effects* stay owner-scoped, not
that the query itself never looks across users).
"""

import asyncio
import base64
import os
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL
from tests.test_action_proposals import NOW, _approve, _proposal, _seed_google_sourced_proposals
from tests.test_deletion_engine import _account, _user
from tests.test_google_token_service import _seed_google_account, _StubOAuthClient

from lifeflow_api.accounts import GoogleTokenService
from lifeflow_api.action_executors import ExecutorOutcome
from lifeflow_api.action_proposal_service import ActionProposalService
from lifeflow_api.deletion import (
    confirm_operation,
    create_imported_data_preview,
    recover_stale_operations,
)
from lifeflow_api.deletion_ops import CONFIRM_IMPORTED_DATA
from lifeflow_api.google.oauth import GoogleTokenResponse
from lifeflow_api.google_scopes import (
    CALENDAR_EVENTS_SCOPE,
    CALENDAR_READONLY_SCOPE,
    GMAIL_COMPOSE_SCOPE,
    GMAIL_READONLY_SCOPE,
)
from lifeflow_api.models import ActionType, DataDeletionOperation, DeletionOperationState
from lifeflow_api.rate_limit_policy import RateLimitPolicy, RateLimitSubjectType
from lifeflow_api.rate_limiter import RateLimiter, bucket_key, hash_subject
from lifeflow_api.repositories import ActionExecutionRepository, AuditEventRepository
from lifeflow_api.security.token_cipher import AesGcmTokenCipher

pytestmark = pytest.mark.integration

ALL_SCOPES = [
    GMAIL_READONLY_SCOPE,
    GMAIL_COMPOSE_SCOPE,
    CALENDAR_READONLY_SCOPE,
    CALENDAR_EVENTS_SCOPE,
]
RATE_LIMIT_SECRET = (
    "test-phase2-isolation-hmac-secret-not-a-real-secret"  # pragma: allowlist secret
)
RATE_LIMIT_REDIS_URL = "redis://localhost:6380/6"


class _UncertainRegistry:
    async def execute(
        self,
        action_type: ActionType,
        *,
        proposal_id: uuid.UUID,
        payload: object,
        approved_authorization: object,
    ) -> ExecutorOutcome:
        return ExecutorOutcome(status="uncertain", result={"message": "lost confirmation"})


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as current:
        yield current
        await current.commit()
    await engine.dispose()


@pytest.fixture
def cipher() -> AesGcmTokenCipher:
    return AesGcmTokenCipher(base64.b64encode(os.urandom(32)).decode(), "test-1")


def _rate_limit_policy() -> RateLimitPolicy:
    return RateLimitPolicy(
        code="phase2_isolation_test",
        subject_type=RateLimitSubjectType.authenticated_user,
        capacity=2,
        refill_amount=2,
        refill_window_seconds=60,
    )


@pytest.mark.parametrize("_round", range(3))
async def test_rate_limit_exhaustion_for_one_user_never_blocks_another(_round: int) -> None:
    client: aioredis.Redis = aioredis.from_url(RATE_LIMIT_REDIS_URL)  # type: ignore[no-untyped-call]
    try:
        await client.flushdb()
    except Exception:
        pytest.skip("Redis is not running (docker compose up -d redis)")
    try:
        limiter = RateLimiter(client, socket_timeout_seconds=2.0)
        policy = _rate_limit_policy()
        alice_key = bucket_key(
            "ratelimit:v1",
            policy.code,
            hash_subject(RATE_LIMIT_SECRET, policy.subject_type, f"alice-{uuid.uuid4()}"),
        )
        bob_key = bucket_key(
            "ratelimit:v1",
            policy.code,
            hash_subject(RATE_LIMIT_SECRET, policy.subject_type, f"bob-{uuid.uuid4()}"),
        )

        # Exhaust Alice's bucket (capacity=2) completely.
        for _ in range(2):
            decision = await limiter.check(alice_key, policy)
            assert decision.allowed is True
        exhausted = await limiter.check(alice_key, policy)
        assert exhausted.allowed is False

        # Bob, an entirely independent subject, is unaffected.
        bob_decision = await limiter.check(bob_key, policy)
        assert bob_decision.allowed is True
    finally:
        await client.flushdb()
        await client.aclose()


@pytest.mark.parametrize("_round", range(3))
async def test_uncertain_execution_for_one_user_never_appears_in_another_users_data(
    session: AsyncSession, _round: int
) -> None:
    alice, _alice_account, alice_proposals = await _seed_google_sourced_proposals(
        session, granted_scopes=ALL_SCOPES
    )
    bob, _bob_account, _bob_proposals = await _seed_google_sourced_proposals(
        session, granted_scopes=ALL_SCOPES
    )
    proposal = _proposal(alice_proposals, ActionType.create_gmail_draft)
    service = ActionProposalService(
        session, alice.id, google_executors=_UncertainRegistry(), now_factory=lambda: NOW
    )
    approved = await _approve(service, proposal, session=session, user=alice)
    _, execution = await service.execute(approved.id)

    # Bob's own repository, scoped to his user id, must never resolve
    # Alice's uncertain execution or see it in his audit trail.
    bob_lookup = await ActionExecutionRepository(session, bob.id).get_by_proposal(proposal.id)
    assert bob_lookup is None

    bob_audit = await AuditEventRepository(session, bob.id).list(limit=100)
    assert all(str(execution.id) not in str(event.safe_metadata_json) for event in bob_audit)

    alice_lookup = await ActionExecutionRepository(session, alice.id).get_by_proposal(proposal.id)
    assert alice_lookup is not None and alice_lookup.id == execution.id


@pytest.mark.parametrize("_round", range(3))
async def test_concurrent_refresh_for_different_users_proceeds_independently(
    session: AsyncSession, cipher: AesGcmTokenCipher, _round: int
) -> None:
    alice = await _seed_google_account(
        session, cipher, expires_at=NOW + timedelta(seconds=30), refresh_token=f"alice-{_round}"
    )
    bob = await _seed_google_account(
        session, cipher, expires_at=NOW + timedelta(seconds=30), refresh_token=f"bob-{_round}"
    )
    await session.commit()

    async def refresh(user_id: uuid.UUID, label: str) -> int:
        engine = create_async_engine(TEST_DB_URL)
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as racing:
                oauth = _StubOAuthClient(
                    GoogleTokenResponse(
                        access_token=f"access-{label}",
                        refresh_token=None,
                        expires_in=3600,
                        scope="a",
                        id_token=None,
                    )
                )
                service = GoogleTokenService(
                    racing,
                    user_id,
                    cipher,
                    oauth,
                    client_id="cid",
                    client_secret="secret",  # pragma: allowlist secret
                    now_factory=lambda: NOW,
                )
                await service.get_valid_access_token("google")
                await racing.commit()
                return oauth.calls
        finally:
            await engine.dispose()

    # Two DIFFERENT users' expired-token refreshes must proceed in
    # parallel, each calling the OAuth transport exactly once — contrast
    # with the same-account case (test_stage11a_phase2_concurrent_oauth_
    # refresh.py), which serialises two concurrent callers down to one
    # real refresh call. A different account's row lock must never block.
    alice_calls, bob_calls = await asyncio.gather(
        refresh(alice.id, "alice"), refresh(bob.id, "bob")
    )
    assert alice_calls == 1
    assert bob_calls == 1


@pytest.mark.parametrize("_round", range(3))
async def test_stale_deletion_recovery_sweep_is_owner_scoped(
    session: AsyncSession, _round: int
) -> None:
    alice = await _user(
        session, email=f"phase2-alice-{uuid.uuid4()}@lifeflow-owner-validation.example"
    )
    bob = await _user(session, email=f"phase2-bob-{uuid.uuid4()}@lifeflow-owner-validation.example")
    alice_account = await _account(session, alice.id, provider="google")
    bob_account = await _account(session, bob.id, provider="google")

    alice_preview = await create_imported_data_preview(
        session, alice, source_account_id=alice_account.id, now=NOW, ttl_minutes=30
    )
    alice_op = await confirm_operation(
        session,
        alice,
        alice_preview.id,
        expected_version=alice_preview.version,
        phrase=CONFIRM_IMPORTED_DATA,
        now=NOW,
        preview_ttl_minutes=30,
    )
    bob_preview = await create_imported_data_preview(
        session, bob, source_account_id=bob_account.id, now=NOW, ttl_minutes=30
    )
    bob_op = await confirm_operation(
        session,
        bob,
        bob_preview.id,
        expected_version=bob_preview.version,
        phrase=CONFIRM_IMPORTED_DATA,
        now=NOW,
        preview_ttl_minutes=30,
    )

    # Simulate both workers crashing mid-run at the same time.
    alice_op.state = DeletionOperationState.running
    alice_op.heartbeat_at = NOW - timedelta(minutes=30)
    alice_op.attempt_count = 1
    bob_op.state = DeletionOperationState.running
    bob_op.heartbeat_at = NOW - timedelta(minutes=30)
    bob_op.attempt_count = 1
    await session.commit()

    result = await recover_stale_operations(
        session, None, now=NOW, heartbeat_timeout=timedelta(minutes=10), max_attempts=3
    )
    assert result.requeued >= 2

    reloaded_alice = await session.get(DataDeletionOperation, alice_op.id, populate_existing=True)
    reloaded_bob = await session.get(DataDeletionOperation, bob_op.id, populate_existing=True)
    assert reloaded_alice is not None and reloaded_alice.state == DeletionOperationState.pending
    assert reloaded_bob is not None and reloaded_bob.state == DeletionOperationState.pending
    assert reloaded_alice.user_id == alice.id
    assert reloaded_bob.user_id == bob.id
