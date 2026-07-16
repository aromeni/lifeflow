"""Cross-user isolation (threat model T2, success criterion S6).

Three layers of guarantee:
1. Structural (parametrised over every user-owned table): a non-nullable
   cascading `user_id` foreign key exists, so no future entity can be
   created without an owner.
2. Contractual: every repository class must bind an owning user_id at
   construction — a new repository that forgets this fails the meta-test.
3. Behavioural (per existing repository): cross-user retrieval, listing,
   and mutation paths all fail. Entities without repositories yet
   (Signal, Brief, ActionProposal) gain their behavioural tests in the
   stage that introduces their repositories; layers 1-2 already bind them.
"""

import inspect
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.conftest import TEST_DB_URL

import lifeflow_api.repositories as repositories_module
from lifeflow_api.db import Base
from lifeflow_api.models import Brief, ConnectedAccount, Preference, User
from lifeflow_api.repositories import (
    AuditEventRepository,
    BriefRepository,
    ConnectedAccountRepository,
    PreferenceRepository,
)

# Structural and contractual tests below need no database; only the
# behavioural tests are marked integration.

# Owned via user_id directly; action_executions is owned via its proposal.
USER_OWNED_TABLES = sorted(
    t.name for t in Base.metadata.sorted_tables if t.name not in {"users", "action_executions"}
)


@pytest.mark.parametrize("table_name", USER_OWNED_TABLES)
def test_every_user_owned_table_has_cascading_user_fk(table_name: str) -> None:
    table = Base.metadata.tables[table_name]
    assert "user_id" in table.c, f"{table_name} lacks user_id"
    column = table.c.user_id
    assert not column.nullable, f"{table_name}.user_id must be non-nullable"
    fks = list(column.foreign_keys)
    assert fks, f"{table_name}.user_id must reference users"
    assert fks[0].column.table.name == "users"
    assert fks[0].ondelete == "CASCADE", f"{table_name}.user_id must cascade on user deletion"


def test_action_executions_are_owned_via_their_proposal() -> None:
    column = Base.metadata.tables["action_executions"].c.proposal_id
    assert not column.nullable
    fks = list(column.foreign_keys)
    assert fks and fks[0].column.table.name == "action_proposals"
    assert fks[0].ondelete == "CASCADE"


def test_every_repository_binds_an_owner() -> None:
    """Any *Repository over user-owned data must take user_id at construction.

    UserRepository is the identity boundary itself and is exempt."""
    for name, cls in inspect.getmembers(repositories_module, inspect.isclass):
        if not name.endswith("Repository") or name == "UserRepository":
            continue
        params = inspect.signature(cls.__init__).parameters
        assert "user_id" in params, f"{name} does not bind an owning user_id"


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.commit()
    await engine.dispose()


@pytest.fixture
async def two_users(session: AsyncSession) -> tuple[User, User]:
    alice = User(email="alice@example.test", display_name="Alice")
    bob = User(email="bob@example.test", display_name="Bob")
    session.add_all([alice, bob])
    await session.flush()
    return alice, bob


@pytest.mark.integration
async def test_connected_accounts_are_isolated(
    session: AsyncSession, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    bob_account = ConnectedAccount(user_id=bob.id, provider="google")
    session.add(bob_account)
    await session.flush()

    alice_repo = ConnectedAccountRepository(session, alice.id)
    assert await alice_repo.get(bob_account.id) is None
    assert await alice_repo.get_by_provider("google") is None
    assert await alice_repo.list() == []

    with pytest.raises(ValueError, match="does not belong"):
        alice_repo.add(ConnectedAccount(user_id=bob.id, provider="synthetic"))


@pytest.mark.integration
async def test_preferences_are_isolated(
    session: AsyncSession, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    session.add(Preference(user_id=bob.id, key="briefing_time", value_json="08:00"))
    await session.flush()

    alice_repo = PreferenceRepository(session, alice.id)
    assert await alice_repo.get("briefing_time") is None
    assert await alice_repo.list() == []

    with pytest.raises(ValueError, match="does not belong"):
        alice_repo.add(Preference(user_id=bob.id, key="k", value_json=1))


@pytest.mark.integration
async def test_audit_events_are_isolated(
    session: AsyncSession, two_users: tuple[User, User]
) -> None:
    from lifeflow_api.audit import record_audit_event

    alice, bob = two_users
    record_audit_event(
        session,
        user_id=bob.id,
        actor=f"user:{bob.id}",
        event_type="test.event",
        entity_type="user",
        entity_id=str(bob.id),
    )
    await session.flush()

    assert await AuditEventRepository(session, alice.id).list() == []
    assert len(await AuditEventRepository(session, bob.id).list()) == 1


@pytest.mark.integration
async def test_briefs_are_isolated(session: AsyncSession, two_users: tuple[User, User]) -> None:
    from datetime import UTC, datetime

    alice, bob = two_users
    bob_brief = Brief(
        user_id=bob.id,
        briefing_date=datetime(2026, 7, 15, tzinfo=UTC),
        version=1,
        status="complete",
        summary="Bob's private summary",
        sections_json={"sections": [], "notices": []},
        source_window="test",
        model_metadata={},
    )
    session.add(bob_brief)
    await session.flush()

    alice_repo = BriefRepository(session, alice.id)
    assert await alice_repo.get(bob_brief.id) is None
    assert await alice_repo.latest() is None
    assert await alice_repo.list_recent() == []
    with pytest.raises(ValueError, match="does not belong"):
        alice_repo.add(
            Brief(
                user_id=bob.id,
                briefing_date=datetime(2026, 7, 16, tzinfo=UTC),
                summary="not allowed",
                sections_json={"sections": [], "notices": []},
                source_window="test",
                model_metadata={},
            )
        )
