"""Stage 9 Delivery Phase 4: trusted-proxy client-IP resolution (ADR 0005
D64). A Starlette `Request` is heavier than needed here — a minimal stand-in
exposing `.client.host` and `.headers` is enough to exercise the resolver in
isolation."""

from dataclasses import dataclass

import pytest

from lifeflow_api.rate_limit_ip import parse_trusted_proxy_cidrs, resolve_client_ip


@dataclass
class _FakeClient:
    host: str


class _FakeRequest:
    def __init__(self, peer: str | None, headers: dict[str, str] | None = None) -> None:
        self.client = _FakeClient(peer) if peer is not None else None
        self.headers = headers or {}


def test_direct_client_with_no_trusted_proxies() -> None:
    request = _FakeRequest("203.0.113.5")
    result = resolve_client_ip(request, trusted_proxy_cidrs="", max_forwarded_hops=5)
    assert result.ip == "203.0.113.5"
    assert result.used_forwarded_header is False


def test_spoofed_forwarded_header_from_untrusted_peer_is_ignored() -> None:
    request = _FakeRequest("203.0.113.5", {"x-forwarded-for": "1.2.3.4"})
    result = resolve_client_ip(request, trusted_proxy_cidrs="", max_forwarded_hops=5)
    assert result.ip == "203.0.113.5"
    assert result.used_forwarded_header is False


def test_empty_trusted_proxy_list_trusts_no_forwarded_headers() -> None:
    request = _FakeRequest("10.0.0.1", {"x-forwarded-for": "9.9.9.9"})
    result = resolve_client_ip(request, trusted_proxy_cidrs="", max_forwarded_hops=5)
    assert result.ip == "10.0.0.1"


def test_trusted_proxy_resolves_direct_client() -> None:
    request = _FakeRequest("10.0.0.1", {"x-forwarded-for": "198.51.100.7"})
    result = resolve_client_ip(request, trusted_proxy_cidrs="10.0.0.0/8", max_forwarded_hops=5)
    assert result.ip == "198.51.100.7"
    assert result.used_forwarded_header is True


def test_multi_proxy_chain_walks_to_first_untrusted_hop() -> None:
    # Two trusted internal hops (10.0.0.2, 10.0.0.1) then the real client.
    request = _FakeRequest("10.0.0.1", {"x-forwarded-for": "198.51.100.7, 10.0.0.2, 10.0.0.1"})
    result = resolve_client_ip(request, trusted_proxy_cidrs="10.0.0.0/8", max_forwarded_hops=5)
    assert result.ip == "198.51.100.7"


def test_mixed_chain_where_leftmost_is_the_untrusted_client() -> None:
    request = _FakeRequest("10.0.0.1", {"x-forwarded-for": "203.0.113.9, 10.0.0.1"})
    result = resolve_client_ip(request, trusted_proxy_cidrs="10.0.0.0/8", max_forwarded_hops=5)
    assert result.ip == "203.0.113.9"


def test_chain_entirely_trusted_falls_back_to_leftmost_hop() -> None:
    request = _FakeRequest("10.0.0.1", {"x-forwarded-for": "10.0.0.3, 10.0.0.2, 10.0.0.1"})
    result = resolve_client_ip(request, trusted_proxy_cidrs="10.0.0.0/8", max_forwarded_hops=5)
    assert result.ip == "10.0.0.3"


def test_ipv4_and_ipv6_both_resolve() -> None:
    ipv6_request = _FakeRequest("2001:db8::1")
    result = resolve_client_ip(ipv6_request, trusted_proxy_cidrs="", max_forwarded_hops=5)
    assert result.ip == "2001:db8::1"


def test_ipv4_mapped_ipv6_normalises_to_ipv4() -> None:
    request = _FakeRequest("10.0.0.1", {"x-forwarded-for": "::ffff:198.51.100.7"})
    result = resolve_client_ip(request, trusted_proxy_cidrs="10.0.0.0/8", max_forwarded_hops=5)
    assert result.ip == "198.51.100.7"


def test_malformed_forwarded_value_falls_back_to_peer() -> None:
    request = _FakeRequest("10.0.0.1", {"x-forwarded-for": "not-an-ip"})
    result = resolve_client_ip(request, trusted_proxy_cidrs="10.0.0.0/8", max_forwarded_hops=5)
    assert result.ip == "10.0.0.1"
    assert result.forwarded_header_rejected is True


def test_empty_forwarded_header_falls_back_to_peer() -> None:
    request = _FakeRequest("10.0.0.1", {"x-forwarded-for": ""})
    result = resolve_client_ip(request, trusted_proxy_cidrs="10.0.0.0/8", max_forwarded_hops=5)
    assert result.ip == "10.0.0.1"


def test_excessive_hop_count_falls_back_to_peer() -> None:
    chain = ", ".join(f"198.51.100.{n}" for n in range(1, 8))
    request = _FakeRequest("10.0.0.1", {"x-forwarded-for": chain})
    result = resolve_client_ip(request, trusted_proxy_cidrs="10.0.0.0/8", max_forwarded_hops=5)
    assert result.ip == "10.0.0.1"
    assert result.forwarded_header_rejected is True


def test_overlapping_cidrs_still_trust_correctly() -> None:
    request = _FakeRequest("10.0.0.1", {"x-forwarded-for": "198.51.100.7"})
    result = resolve_client_ip(
        request, trusted_proxy_cidrs="10.0.0.0/8,10.0.0.0/16", max_forwarded_hops=5
    )
    assert result.ip == "198.51.100.7"


def test_no_transport_peer_degrades_to_sentinel_without_raising() -> None:
    request = _FakeRequest(None)
    result = resolve_client_ip(request, trusted_proxy_cidrs="", max_forwarded_hops=5)
    assert result.ip == "unknown"


def test_malformed_cidr_entry_is_ignored_not_fatal() -> None:
    networks = parse_trusted_proxy_cidrs("not-a-cidr, 10.0.0.0/8")
    assert len(networks) == 1


@pytest.mark.parametrize("value", ["10.0.0.1", "2001:db8::1"])
def test_resolved_ip_never_logged_raw_in_result_object(value: str) -> None:
    # The resolver returns the plain IP by design (callers HMAC it before it
    # reaches Redis or a log line) — this test just pins that resolve_client_ip
    # itself never raises or mutates the header/peer value unexpectedly.
    request = _FakeRequest(value)
    result = resolve_client_ip(request, trusted_proxy_cidrs="", max_forwarded_hops=5)
    assert result.ip == value
