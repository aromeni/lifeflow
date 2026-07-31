"""Stage 11A Phase 1 F-002 closure (docs/evaluation/stage-11/owner-validation/
phase-1/f-002-closure-acceptance-matrix.md): proves `demo_clock_override`
(`lifeflow_api.demo_mode._resolve_now`) actually removes the real host clock
from the demo/synthetic content-generation path, without leaking a frozen
clock into anything security- or expiry-relevant.

F-002's root cause was `demo_mode.py` deriving its synthetic-dataset anchor
from `datetime.now(...)` on every `/demo/start` call — as real time passed,
which fictional email/event ranked highest drifted, periodically breaking
visual-regression baselines. These tests prove the fix at three levels: the
override branch never calls the host clock at all (even at day/month/year
boundaries), the override is inert unless explicitly enabled (mirroring the
existing `google_api_origin_override` contract), and it never affects any
other clock read in the app (action-proposal expiry keeps using real time).
"""

from datetime import UTC, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo

import pytest
from tests.conftest import CSRF_HEADERS, _make_client, _test_settings

from lifeflow_api.config import Settings
from lifeflow_api.demo_mode import _resolve_now

pytestmark = pytest.mark.integration

OVERRIDE_INSTANT = "2026-03-15T09:00:00+00:00"


class _ExplodingDatetime(datetime):
    """Stands in for the real `datetime` class inside `demo_mode`. Any call
    to `.now()` fails the test outright — the override branch must never
    reach it."""

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> datetime:
        raise AssertionError(
            "datetime.now() must not be called while demo_clock_override is active"
        )


class _FixedHostDatetime(datetime):
    """A distinguishable stand-in for the real host clock, used to prove the
    override is truly ignored when the gating flag is off."""

    STUB_UTC = datetime(2099, 8, 20, 12, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> datetime:
        return cls.STUB_UTC.astimezone(tz) if tz is not None else cls.STUB_UTC


def _settings_with_override(instant: str = OVERRIDE_INSTANT) -> Settings:
    return _test_settings("development").model_copy(
        update={"e2e_test_controls_enabled": True, "demo_clock_override": instant}
    )


def test_demo_clock_override_never_consults_the_host_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("lifeflow_api.demo_mode.datetime", _ExplodingDatetime)
    settings = _settings_with_override()

    result = _resolve_now(settings, "Europe/London")

    assert result == datetime.fromisoformat(OVERRIDE_INSTANT).astimezone(ZoneInfo("Europe/London"))


@pytest.mark.parametrize(
    "instant",
    [
        "2026-01-14T23:59:30+00:00",  # just before a midnight boundary
        "2026-02-01T00:00:30+00:00",  # just after a month boundary
        "2025-12-31T23:00:00+00:00",  # just before a year boundary
        "2026-01-01T01:00:00+00:00",  # just after a year boundary
    ],
)
def test_demo_clock_override_holds_across_boundaries_without_the_host_clock(
    monkeypatch: pytest.MonkeyPatch, instant: str
) -> None:
    monkeypatch.setattr("lifeflow_api.demo_mode.datetime", _ExplodingDatetime)
    settings = _settings_with_override(instant)

    result = _resolve_now(settings, "Europe/London")

    assert result == datetime.fromisoformat(instant).astimezone(ZoneInfo("Europe/London"))


def test_demo_clock_override_ignored_when_test_controls_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The flag is the single gate (same contract as `google_api_origin_override`,
    see test_e2e_test_controls.py) — an override left set with the flag off
    must fall through to the real clock, not silently take effect."""
    monkeypatch.setattr("lifeflow_api.demo_mode.datetime", _FixedHostDatetime)
    settings = _test_settings("development").model_copy(
        update={"e2e_test_controls_enabled": False, "demo_clock_override": OVERRIDE_INSTANT}
    )

    result = _resolve_now(settings, "Europe/London")

    assert result == _FixedHostDatetime.STUB_UTC.astimezone(ZoneInfo("Europe/London"))
    assert result != datetime.fromisoformat(OVERRIDE_INSTANT).astimezone(ZoneInfo("Europe/London"))


async def test_demo_clock_override_produces_identical_content_for_independent_users() -> None:
    """Full-stack proof: two independent synthetic users, same override,
    same imported content — the fixture-selection outcome depends only on
    the override, never on when (real time) `/demo/start` happens to run."""
    settings = _settings_with_override()

    async def _imported_items(email: str) -> list[tuple[str, str]]:
        async for client in _make_client(settings):
            login = await client.post(
                "/auth/dev-login", json={"email": email}, headers=CSRF_HEADERS
            )
            assert login.status_code == 200
            start = await client.post("/demo/start", headers=CSRF_HEADERS)
            assert start.status_code == 200
            assert start.json()["imported"] > 0
            listing = await client.get("/source-items", params={"limit": 500})
            assert listing.status_code == 200
            return sorted((item["title"], item["occurred_at"]) for item in listing.json()["items"])
        raise AssertionError("client fixture did not yield")

    first = await _imported_items("f002-clock-a@lifeflow-owner-validation.example")
    second = await _imported_items("f002-clock-b@lifeflow-owner-validation.example")

    assert first == second
    assert len(first) > 0


async def test_demo_clock_override_does_not_affect_action_proposal_expiry() -> None:
    """The override must stay scoped to the demo anchor — action-proposal
    expiry (`action_proposal_service.py`'s own `_now` factory) must keep
    using the real wall clock even while an unrelated, far-past override is
    active for demo content."""
    settings = _test_settings("development").model_copy(
        update={
            "e2e_test_controls_enabled": True,
            # Safely before any plausible real test-run date, so the
            # assertions below can never coincidentally pass by accident.
            "demo_clock_override": "1999-01-01T00:00:00+00:00",
        }
    )

    async for client in _make_client(settings):
        login = await client.post(
            "/auth/dev-login",
            json={"email": "f002-expiry@lifeflow-owner-validation.example"},
            headers=CSRF_HEADERS,
        )
        assert login.status_code == 200
        assert (await client.post("/demo/start", headers=CSRF_HEADERS)).status_code == 200
        brief = await client.post("/briefs/generate", headers=CSRF_HEADERS)
        assert brief.status_code == 200

        proposals = (await client.get("/action-proposals")).json()["proposals"]
        assert len(proposals) > 0

        real_now = datetime.now(UTC)
        for proposal in proposals:
            expires_at = datetime.fromisoformat(proposal["expires_at"])
            assert expires_at > real_now, (
                "proposal expiry must anchor to the real clock, not the demo override"
            )
            assert expires_at <= real_now + timedelta(days=7, minutes=5)
