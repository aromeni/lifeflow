"""Trusted client-IP resolution for anonymous rate-limit subjects (ADR 0005
D64).

The immediate socket peer (`request.client.host`) is the only trust anchor.
`X-Forwarded-For` is consulted only when that immediate peer itself belongs to
an explicit `TRUSTED_PROXY_CIDRS` allowlist; an empty allowlist (the default)
trusts no forwarded header under any circumstance. A malformed or overlong
chain never grants a fresh identity — it falls back to the immediate peer.
"""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass

from fastapi import Request

logger = logging.getLogger(__name__)

_IpNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
_IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def parse_trusted_proxy_cidrs(raw: str) -> tuple[_IpNetwork, ...]:
    """Parse the comma-separated `TRUSTED_PROXY_CIDRS` setting. A malformed
    entry is dropped with a warning (never crashes a request) rather than
    silently trusting everything — but an operator error here should be
    caught by the config validation tests, not discovered at request time."""
    networks: list[_IpNetwork] = []
    for raw_entry in raw.split(","):
        entry = raw_entry.strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            logger.warning("rate_limit.trusted_proxy_cidrs_malformed_entry_ignored")
    return tuple(networks)


def _normalise(address: _IpAddress) -> _IpAddress:
    if isinstance(address, ipaddress.IPv6Address):
        mapped = address.ipv4_mapped
        if mapped is not None:
            return mapped
    return address


def _is_trusted(address: _IpAddress, trusted_networks: tuple[_IpNetwork, ...]) -> bool:
    return any(
        address in network for network in trusted_networks if address.version == network.version
    )


def _parse_address(raw: str) -> _IpAddress | None:
    try:
        return _normalise(ipaddress.ip_address(raw.strip()))
    except ValueError:
        return None


@dataclass(frozen=True)
class ClientIpResolution:
    ip: str
    used_forwarded_header: bool
    forwarded_header_rejected: bool


def resolve_client_ip(
    request: Request,
    *,
    trusted_proxy_cidrs: str,
    max_forwarded_hops: int,
) -> ClientIpResolution:
    """Resolve the address a client-IP-keyed rate-limit policy should charge.
    Never raises — every failure mode degrades to the immediate peer."""
    peer = request.client.host if request.client is not None else None
    if peer is None:
        # No transport-level peer at all (e.g. a unix socket in some test
        # harnesses) — nothing safe to key on; degrade to a fixed sentinel
        # rather than raising and breaking the route entirely.
        return ClientIpResolution(
            "unknown", used_forwarded_header=False, forwarded_header_rejected=False
        )

    peer_address = _parse_address(peer)
    if peer_address is None:
        return ClientIpResolution(
            peer, used_forwarded_header=False, forwarded_header_rejected=False
        )

    trusted_networks = parse_trusted_proxy_cidrs(trusted_proxy_cidrs)
    if not trusted_networks or not _is_trusted(peer_address, trusted_networks):
        return ClientIpResolution(
            str(peer_address), used_forwarded_header=False, forwarded_header_rejected=False
        )

    raw_header = request.headers.get("x-forwarded-for")
    if not raw_header:
        return ClientIpResolution(
            str(peer_address), used_forwarded_header=False, forwarded_header_rejected=False
        )

    raw_hops = [hop.strip() for hop in raw_header.split(",") if hop.strip()]
    if not raw_hops or len(raw_hops) > max_forwarded_hops:
        logger.warning("rate_limit.forwarded_header_rejected reason=hop_count_or_empty")
        return ClientIpResolution(
            str(peer_address), used_forwarded_header=False, forwarded_header_rejected=True
        )

    parsed_hops: list[_IpAddress] = []
    for hop in raw_hops:
        address = _parse_address(hop)
        if address is None:
            logger.warning("rate_limit.forwarded_header_rejected reason=malformed_hop")
            return ClientIpResolution(
                str(peer_address), used_forwarded_header=False, forwarded_header_rejected=True
            )
        parsed_hops.append(address)

    # Walk from the trusted edge (the end nearest this server, which the
    # nearest trusted proxy itself appended) leftward, skipping any hop that
    # is itself a trusted proxy; the first non-trusted hop is the originating
    # client. If every hop is trusted (an internal chain with no visible
    # client), fall back to the leftmost hop as a best-effort identity rather
    # than granting no identity at all.
    for address in reversed(parsed_hops):
        if not _is_trusted(address, trusted_networks):
            return ClientIpResolution(
                str(address), used_forwarded_header=True, forwarded_header_rejected=False
            )
    return ClientIpResolution(
        str(parsed_hops[0]), used_forwarded_header=True, forwarded_header_rejected=False
    )


__all__ = ["ClientIpResolution", "parse_trusted_proxy_cidrs", "resolve_client_ip"]
