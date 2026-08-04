"""Stage 7: OAuth flow primitives — PKCE/state, token exchange/refresh,
ID-token verification (ADR 0003 D10/D14/D18). All against `httpx.MockTransport`
or an injected verifier — no real network call is possible from this suite.
"""

import time

import httpx
import pytest
from starlette.requests import Request

from lifeflow_api.google.errors import (
    GoogleAuthError,
    GoogleClientError,
    GoogleTransientError,
    IdTokenVerificationError,
    InvalidGrantError,
)
from lifeflow_api.google.oauth import (
    GoogleOAuthClient,
    build_authorization_url,
    generate_nonce,
    generate_pkce_pair,
    generate_state,
    verify_id_token,
)
from lifeflow_api.metrics import REGISTRY
from lifeflow_api.oauth_state import OAuthStateError, begin_oauth_flow, consume_oauth_flow


def test_pkce_pair_challenge_is_derived_from_verifier_via_s256() -> None:
    import base64
    import hashlib

    pair = generate_pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(pair.verifier.encode()).digest())
    assert pair.challenge == expected.rstrip(b"=").decode("ascii")


def test_state_and_pkce_are_unique_per_call() -> None:
    assert generate_state() != generate_state()
    assert generate_pkce_pair().verifier != generate_pkce_pair().verifier


def test_authorization_url_carries_pkce_and_exact_scope() -> None:
    url = build_authorization_url(
        client_id="client-123",
        redirect_uri="https://app.example/callback",
        scope="scope-a scope-b",
        state="state-xyz",
        code_challenge="challenge-abc",
        access_type="offline",
        prompt="consent",
    )
    assert "client_id=client-123" in url
    assert "code_challenge=challenge-abc" in url
    assert "code_challenge_method=S256" in url
    assert "state=state-xyz" in url
    assert "scope=scope-a+scope-b" in url
    assert "access_type=offline" in url
    assert "prompt=consent" in url


def _mock_client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


async def test_exchange_code_parses_token_response() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/token"
        body = request.read().decode()
        assert "grant_type=authorization_code" in body
        assert "code_verifier=verifier-1" in body
        return httpx.Response(
            200,
            json={
                "access_token": "access-1",
                "refresh_token": "refresh-1",
                "expires_in": 3600,
                "scope": "a b",
                "id_token": "idtok-1",
            },
        )

    client = GoogleOAuthClient(_mock_client(httpx.MockTransport(handle)))
    result = await client.exchange_code(
        client_id="cid",
        client_secret="csecret",
        redirect_uri="https://app.example/callback",
        code="auth-code",
        code_verifier="verifier-1",
    )
    assert result.access_token == "access-1"
    assert result.refresh_token == "refresh-1"
    assert result.expires_in == 3600
    assert result.id_token == "idtok-1"


async def test_refresh_response_without_refresh_token_is_none_not_empty() -> None:
    """D18: Google's ordinary refresh response omits refresh_token — the
    dataclass must carry None, distinguishable from an empty string, so
    callers know to leave the stored value untouched."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"access_token": "access-2", "expires_in": 3600, "scope": "a"}
        )

    client = GoogleOAuthClient(_mock_client(httpx.MockTransport(handle)))
    result = await client.refresh_access_token(
        client_id="cid", client_secret="csecret", refresh_token="refresh-1"
    )
    assert result.access_token == "access-2"
    assert result.refresh_token is None


async def test_refresh_invalid_grant_raises_typed_error() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    client = GoogleOAuthClient(_mock_client(httpx.MockTransport(handle)))
    with pytest.raises(InvalidGrantError):
        await client.refresh_access_token(
            client_id="cid", client_secret="csecret", refresh_token="revoked"
        )


@pytest.mark.parametrize(
    "error_code", ["invalid_request", "unsupported_grant_type", "invalid_scope"]
)
async def test_definite_client_error_codes_raise_google_client_error(error_code: str) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": error_code})

    client = GoogleOAuthClient(_mock_client(httpx.MockTransport(handle)))
    with pytest.raises(GoogleClientError) as exc:
        await client.refresh_access_token(
            client_id="cid", client_secret="csecret", refresh_token="whatever"
        )
    assert exc.value.status_code == 400


@pytest.mark.parametrize("error_code", ["invalid_client", "unauthorized_client"])
async def test_client_rejected_error_codes_raise_google_auth_error(error_code: str) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": error_code})

    client = GoogleOAuthClient(_mock_client(httpx.MockTransport(handle)))
    with pytest.raises(GoogleAuthError):
        await client.refresh_access_token(
            client_id="cid", client_secret="csecret", refresh_token="whatever"
        )


@pytest.mark.parametrize("error_code", ["server_error", "temporarily_unavailable"])
async def test_transient_oauth_error_codes_raise_google_transient_error(error_code: str) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": error_code})

    client = GoogleOAuthClient(_mock_client(httpx.MockTransport(handle)))
    with pytest.raises(GoogleTransientError):
        await client.refresh_access_token(
            client_id="cid", client_secret="csecret", refresh_token="whatever"
        )


@pytest.mark.parametrize("status_code", [429, 500, 502, 503])
async def test_transient_http_statuses_raise_google_transient_error(status_code: int) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": "unexpected"})

    client = GoogleOAuthClient(_mock_client(httpx.MockTransport(handle)))
    with pytest.raises(GoogleTransientError):
        await client.refresh_access_token(
            client_id="cid", client_secret="csecret", refresh_token="whatever"
        )


async def test_refresh_connection_timeout_raises_google_transient_error() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    client = GoogleOAuthClient(_mock_client(httpx.MockTransport(handle)))
    with pytest.raises(GoogleTransientError):
        await client.refresh_access_token(
            client_id="cid", client_secret="csecret", refresh_token="whatever"
        )


async def test_other_definitive_4xx_without_error_code_raises_google_client_error() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={})

    client = GoogleOAuthClient(_mock_client(httpx.MockTransport(handle)))
    with pytest.raises(GoogleClientError) as exc:
        await client.refresh_access_token(
            client_id="cid", client_secret="csecret", refresh_token="whatever"
        )
    assert exc.value.status_code == 400


def _oauth_requests_value(outcome: str) -> float:
    return (
        REGISTRY.get_sample_value(
            "lifeflow_provider_requests_total",
            {
                "provider": "google_oauth",
                "operation": "refresh_access_token",
                "outcome": outcome,
            },
        )
        or 0.0
    )


async def test_successful_refresh_emits_a_success_request_metric() -> None:
    """Stage 9 Delivery Phase 5 (§14/§18 item 36): token refresh is the one
    OAuth call classified as a provider operation for metrics purposes."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "a", "expires_in": 3600, "scope": "s"})

    client = GoogleOAuthClient(_mock_client(httpx.MockTransport(handle)))
    before = _oauth_requests_value("success")

    await client.refresh_access_token(client_id="cid", client_secret="csecret", refresh_token="r")

    assert _oauth_requests_value("success") == before + 1


async def test_revoked_grant_is_a_distinct_metric_outcome_not_unknown_error() -> None:
    """A revoked refresh token is an expected, well-understood condition —
    it must not be lumped into the catch-all `unknown_error` bucket."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    client = GoogleOAuthClient(_mock_client(httpx.MockTransport(handle)))
    before = _oauth_requests_value("grant_invalid")

    with pytest.raises(InvalidGrantError):
        await client.refresh_access_token(
            client_id="cid", client_secret="csecret", refresh_token="revoked"
        )

    assert _oauth_requests_value("grant_invalid") == before + 1


async def test_revoke_is_best_effort_and_never_raises() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    client = GoogleOAuthClient(_mock_client(httpx.MockTransport(handle)))
    confirmed = await client.revoke_token(token="whatever")  # must not raise
    assert confirmed is False


async def test_revoke_reports_true_only_on_an_objective_200() -> None:
    """Stage 11A Phase 4D: the caller needs to know whether Google actually
    confirmed revocation, to decide between recording
    `GOOGLE_ACCESS_REVOCATION=CONFIRMED` and asking the owner to check
    manually."""

    def ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client = GoogleOAuthClient(_mock_client(httpx.MockTransport(ok)))
    assert await client.revoke_token(token="whatever") is True

    def rejected(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_token"})

    client = GoogleOAuthClient(_mock_client(httpx.MockTransport(rejected)))
    assert await client.revoke_token(token="whatever") is False


async def test_verify_id_token_rejects_unverified_email() -> None:
    def stub_verifier(token: str, client_id: str) -> dict:
        return {"sub": "user-1", "email": "user@example.com", "email_verified": False}

    with pytest.raises(IdTokenVerificationError):
        await verify_id_token("token", client_id="cid", verifier=stub_verifier)


async def test_verify_id_token_accepts_verified_email() -> None:
    def stub_verifier(token: str, client_id: str) -> dict:
        assert client_id == "cid"
        return {"sub": "user-1", "email": "user@example.com", "email_verified": True}

    identity = await verify_id_token("token", client_id="cid", verifier=stub_verifier)
    assert identity.subject == "user-1"
    assert identity.email == "user@example.com"
    assert identity.email_verified is True


async def test_verify_id_token_wraps_verifier_exceptions() -> None:
    def stub_verifier(token: str, client_id: str) -> dict:
        raise ValueError("bad signature")

    with pytest.raises(IdTokenVerificationError):
        await verify_id_token("token", client_id="cid", verifier=stub_verifier)


async def test_verify_id_token_accepts_matching_nonce() -> None:
    def stub_verifier(token: str, client_id: str) -> dict:
        return {
            "sub": "user-1",
            "email": "user@example.com",
            "email_verified": True,
            "nonce": "expected-nonce",
        }

    identity = await verify_id_token(
        "token", client_id="cid", expected_nonce="expected-nonce", verifier=stub_verifier
    )
    assert identity.subject == "user-1"


async def test_verify_id_token_rejects_nonce_mismatch() -> None:
    def stub_verifier(token: str, client_id: str) -> dict:
        return {
            "sub": "user-1",
            "email": "user@example.com",
            "email_verified": True,
            "nonce": "wrong-nonce",
        }

    with pytest.raises(IdTokenVerificationError):
        await verify_id_token(
            "token", client_id="cid", expected_nonce="expected-nonce", verifier=stub_verifier
        )


async def test_verify_id_token_rejects_missing_nonce_when_one_was_expected() -> None:
    def stub_verifier(token: str, client_id: str) -> dict:
        return {"sub": "user-1", "email": "user@example.com", "email_verified": True}

    with pytest.raises(IdTokenVerificationError):
        await verify_id_token(
            "token", client_id="cid", expected_nonce="expected-nonce", verifier=stub_verifier
        )


def test_generate_nonce_is_unique_per_call() -> None:
    assert generate_nonce() != generate_nonce()


def _fake_request(session_data: dict | None = None) -> Request:
    scope = {
        "type": "http",
        "session": dict(session_data or {}),
        "headers": [],
        "method": "GET",
        "path": "/",
    }
    return Request(scope)


def test_oauth_state_round_trip_succeeds() -> None:
    request = _fake_request()
    state, pkce, _nonce = begin_oauth_flow(request, purpose="signin")
    flow = consume_oauth_flow(request, purpose="signin", state=state)
    assert flow.code_verifier == pkce.verifier


def test_oauth_state_is_single_use() -> None:
    request = _fake_request()
    state, _pkce, _nonce = begin_oauth_flow(request, purpose="signin")
    consume_oauth_flow(request, purpose="signin", state=state)
    with pytest.raises(OAuthStateError):
        consume_oauth_flow(request, purpose="signin", state=state)


def test_oauth_state_rejects_wrong_state_value() -> None:
    request = _fake_request()
    begin_oauth_flow(request, purpose="signin")
    with pytest.raises(OAuthStateError):
        consume_oauth_flow(request, purpose="signin", state="not-the-real-state")


def test_oauth_state_rejects_purpose_mismatch() -> None:
    request = _fake_request()
    state, _pkce, _nonce = begin_oauth_flow(request, purpose="connect")
    with pytest.raises(OAuthStateError):
        consume_oauth_flow(request, purpose="signin", state=state)


def test_oauth_state_rejects_stale_flow() -> None:
    request = _fake_request()
    state, _pkce, _nonce = begin_oauth_flow(request, purpose="signin")
    request.session["google_oauth_pending"]["created_at"] = time.time() - 10_000
    with pytest.raises(OAuthStateError):
        consume_oauth_flow(request, purpose="signin", state=state)


def test_oauth_state_connect_flow_binds_to_current_session_user() -> None:
    request = _fake_request({"user_id": "user-a"})
    state, _pkce, _nonce = begin_oauth_flow(request, purpose="connect", bind_user_id="user-a")
    # Simulate the session now belonging to a different user (session swap).
    request.session["user_id"] = "user-b"
    with pytest.raises(OAuthStateError):
        consume_oauth_flow(request, purpose="connect", state=state)


def test_oauth_state_signin_flow_carries_a_nonce_when_requested() -> None:
    request = _fake_request()
    state, _pkce, nonce = begin_oauth_flow(request, purpose="signin", include_nonce=True)
    assert nonce is not None
    flow = consume_oauth_flow(request, purpose="signin", state=state)
    assert flow.nonce == nonce


def test_oauth_state_connect_flow_never_carries_a_nonce() -> None:
    """The connector-consent flow never exchanges an ID token, so it has
    nothing to bind a nonce to."""
    request = _fake_request({"user_id": "user-a"})
    state, _pkce, nonce = begin_oauth_flow(request, purpose="connect", bind_user_id="user-a")
    assert nonce is None
    flow = consume_oauth_flow(request, purpose="connect", state=state)
    assert flow.nonce is None
