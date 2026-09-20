"""Resolve client addresses across explicitly trusted proxy hops."""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from typing import TYPE_CHECKING

from flask import current_app, has_app_context, request

if TYPE_CHECKING:
    from collections.abc import Iterable

    from flask import Request

_MAX_FORWARDED_HOPS = 32
IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


def _config_items(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    if value is None:
        return ()
    return (str(value).strip(),)


@lru_cache(maxsize=64)
def _parse_networks(items: tuple[str, ...]) -> tuple[IPNetwork, ...]:
    return tuple(ipaddress.ip_network(item, strict=False) for item in items)


def validate_trusted_proxy_cidrs(value: object) -> bool:
    """Return whether a configuration value contains only valid IP networks."""
    try:
        _parse_networks(_config_items(value))
    except ValueError:
        return False
    return True


def _normalized_address(value: object) -> IPAddress | None:
    candidate = str(value or "").strip()
    if not candidate or "%" in candidate:
        return None
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


def _is_trusted(
    address: IPAddress,
    networks: Iterable[IPNetwork],
) -> bool:
    return any(
        address.version == network.version and address in network
        for network in networks
    )


def resolve_client_ip(
    request_value: Request | None = None,
    *,
    trusted_proxy_cidrs: object | None = None,
) -> str:
    """Return the first untrusted address in a validated forwarding chain.

    Forwarding headers are ignored unless the TCP peer is explicitly trusted.
    Malformed or excessively long chains fail closed to that peer.
    """
    current_request = request_value or request
    remote_address = _normalized_address(current_request.remote_addr)
    if remote_address is None:
        return "unknown"
    remote_ip = remote_address.compressed

    configured_cidrs = trusted_proxy_cidrs
    if configured_cidrs is None and has_app_context():
        configured_cidrs = current_app.config.get("TRUSTED_PROXY_CIDRS", ())
    try:
        trusted_networks = _parse_networks(_config_items(configured_cidrs))
    except ValueError:
        return remote_ip
    if not trusted_networks or not _is_trusted(remote_address, trusted_networks):
        return remote_ip

    forwarded = str(current_request.headers.get("X-Forwarded-For") or "").strip()
    if not forwarded:
        return remote_ip
    raw_hops = forwarded.split(",")
    if len(raw_hops) > _MAX_FORWARDED_HOPS:
        return remote_ip
    parsed_hops = [_normalized_address(hop) for hop in raw_hops]
    if any(hop is None for hop in parsed_hops):
        return remote_ip

    chain = [*parsed_hops, remote_address]
    for hop in reversed(chain):
        if hop is not None and not _is_trusted(hop, trusted_networks):
            return hop.compressed
    return remote_ip
