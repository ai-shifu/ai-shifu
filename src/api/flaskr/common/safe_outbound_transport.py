"""Pinned HTTP transport for validated outbound destinations."""

from __future__ import annotations

import contextlib
import socket
import ssl
import threading
import time
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import urllib3
from urllib3.connection import HTTPConnection, HTTPSConnection

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
    deadline: float,
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
    if hasattr(pool, "conn_kw"):
        pool.ConnectionCls = (
            _DeadlineHTTPSConnection
            if target.scheme == "https"
            else _DeadlineHTTPConnection
        )
        pool.conn_kw["absolute_deadline"] = deadline
    try:
        response = pool.urlopen(
            method,
            request_target,
            body=body,
            headers=request_headers,
            redirect=False,
            preload_content=False,
            retries=False,
            timeout=timeout,
        )
    except Exception as exc:
        if time.monotonic() >= deadline:
            _raise_deadline_exceeded(exc)
        raise
    if time.monotonic() >= deadline:
        response.close()
        _raise_deadline_exceeded()
    return response


class _AbsoluteDeadlineConnection:
    """Close an active socket when its request's wall-clock budget expires."""

    def __init__(
        self,
        *args: object,
        absolute_deadline: float,
        **kwargs: object,
    ) -> None:
        self._absolute_deadline = absolute_deadline
        self._deadline_timer: threading.Timer | None = None
        super().__init__(*args, **kwargs)

    def connect(self) -> None:
        self._arm_deadline()
        try:
            super().connect()
        except Exception:
            self._cancel_deadline()
            raise

    def close(self) -> None:
        self._cancel_deadline()
        super().close()

    def _arm_deadline(self) -> None:
        delay = max(0.0, self._absolute_deadline - time.monotonic())
        timer = threading.Timer(delay, self._interrupt_socket)
        timer.daemon = True
        self._deadline_timer = timer
        timer.start()

    def _cancel_deadline(self) -> None:
        timer = self._deadline_timer
        self._deadline_timer = None
        if timer is not None:
            timer.cancel()

    def _interrupt_socket(self) -> None:
        active_socket = self.sock
        if active_socket is None:
            return
        with contextlib.suppress(OSError):
            active_socket.shutdown(socket.SHUT_RDWR)
        with contextlib.suppress(OSError):
            active_socket.close()


class _DeadlineHTTPConnection(_AbsoluteDeadlineConnection, HTTPConnection):
    """HTTP connection interrupted at an absolute monotonic deadline."""


class _DeadlineHTTPSConnection(_AbsoluteDeadlineConnection, HTTPSConnection):
    """HTTPS connection interrupted at an absolute monotonic deadline."""


def _raise_deadline_exceeded(exc: Exception | None = None) -> None:
    from flaskr.common.safe_outbound import OutboundDeadlineExceededError

    message = "outbound request exceeded its total timeout"
    if exc is None:
        raise OutboundDeadlineExceededError(message)
    raise OutboundDeadlineExceededError(message) from exc


def _host_header(hostname: str, port: int, scheme: str) -> str:
    default_port = 443 if scheme == "https" else 80
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    return display_host if port == default_port else f"{display_host}:{port}"
