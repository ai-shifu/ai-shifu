"""Pinned HTTP transport for validated outbound destinations."""

from __future__ import annotations

import ssl
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import urllib3

if TYPE_CHECKING:
    import ipaddress
    from collections.abc import Mapping

    from urllib3.response import HTTPResponse
    from urllib3.util import Timeout

    from flaskr.common.safe_outbound import ValidatedOutboundUrl


def open_pinned_request(
    method: str,
    target: ValidatedOutboundUrl,
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    headers: Mapping[str, str],
    body: bytes | None,
    timeout: Timeout,
) -> HTTPResponse:
    """Connect to a validated IP while preserving HTTP Host and HTTPS SNI."""
    request_headers = {
        key: value for key, value in headers.items() if key.lower() != "host"
    }
    request_headers["Host"] = _host_header(target.hostname, target.port, target.scheme)
    parsed_url = urlsplit(target.url)
    path = parsed_url.path or "/"
    request_target = f"{path}?{parsed_url.query}" if parsed_url.query else path
    address_text = str(address)

    if target.scheme == "https":
        pool: urllib3.HTTPConnectionPool = urllib3.HTTPSConnectionPool(
            address_text,
            port=target.port,
            assert_hostname=target.hostname,
            server_hostname=target.hostname,
            ssl_context=ssl.create_default_context(),
            maxsize=1,
            block=True,
        )
    else:
        pool = urllib3.HTTPConnectionPool(
            address_text,
            port=target.port,
            maxsize=1,
            block=True,
        )
    return pool.urlopen(
        method,
        request_target,
        body=body,
        headers=request_headers,
        redirect=False,
        preload_content=False,
        retries=False,
        timeout=timeout,
    )


def _host_header(hostname: str, port: int, scheme: str) -> str:
    default_port = 443 if scheme == "https" else 80
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    return display_host if port == default_port else f"{display_host}:{port}"
