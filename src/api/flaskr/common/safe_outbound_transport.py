"""Pinned HTTP transport for validated outbound destinations."""

from __future__ import annotations

import contextlib
import socket
import ssl
import threading
import time
from typing import TYPE_CHECKING, Protocol
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
    deadline_guard = _AbsoluteDeadlineGuard(deadline)
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
        pool.conn_kw["deadline_guard"] = deadline_guard
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
        deadline_guard.cancel()
        if time.monotonic() >= deadline:
            _raise_deadline_exceeded(exc)
        raise
    if time.monotonic() >= deadline:
        response.close()
        deadline_guard.cancel()
        _raise_deadline_exceeded()
    _cancel_guard_when_response_closes(response, deadline_guard)
    return response


class _SocketOwner(Protocol):
    sock: socket.socket | ssl.SSLSocket | None


class _AbsoluteDeadlineGuard:
    """Interrupt every socket retained by one response at its deadline."""

    def __init__(self, absolute_deadline: float) -> None:
        self._owner: _SocketOwner | None = None
        self._retained_sockets: set[socket.socket | ssl.SSLSocket] = set()
        self._state_lock = threading.Lock()
        delay = max(0.0, absolute_deadline - time.monotonic())
        self._timer = threading.Timer(delay, self._interrupt_sockets)
        self._timer.daemon = True
        self._timer.start()

    def bind_owner(self, owner: _SocketOwner) -> None:
        with self._state_lock:
            self._owner = owner

    def retain_socket(
        self,
        active_socket: socket.socket | ssl.SSLSocket | None,
    ) -> None:
        if active_socket is None:
            return
        with self._state_lock:
            self._retained_sockets.add(active_socket)

    def cancel(self) -> None:
        self._timer.cancel()
        with self._state_lock:
            self._owner = None
            self._retained_sockets.clear()

    def _interrupt_sockets(self) -> None:
        with self._state_lock:
            owner_socket = self._owner.sock if self._owner is not None else None
            sockets = set(self._retained_sockets)
            if owner_socket is not None:
                sockets.add(owner_socket)
            self._owner = None
            self._retained_sockets.clear()
        for active_socket in sockets:
            with contextlib.suppress(OSError):
                active_socket.shutdown(socket.SHUT_RDWR)
            with contextlib.suppress(OSError):
                active_socket.close()


class _AbsoluteDeadlineConnection:
    """Keep the response's deadline guard attached across connection close."""

    def __init__(
        self,
        *args: object,
        deadline_guard: _AbsoluteDeadlineGuard,
        **kwargs: object,
    ) -> None:
        self._deadline_guard = deadline_guard
        super().__init__(*args, **kwargs)
        self._deadline_guard.bind_owner(self)

    def close(self) -> None:
        self._deadline_guard.retain_socket(self.sock)
        super().close()


class _DeadlineHTTPConnection(_AbsoluteDeadlineConnection, HTTPConnection):
    """HTTP connection interrupted at an absolute monotonic deadline."""


class _DeadlineHTTPSConnection(_AbsoluteDeadlineConnection, HTTPSConnection):
    """HTTPS connection interrupted at an absolute monotonic deadline."""


def _cancel_guard_when_response_closes(
    response: HTTPResponse,
    deadline_guard: _AbsoluteDeadlineGuard,
) -> None:
    original_close = response.close

    def close_with_deadline_cleanup() -> None:
        try:
            original_close()
        finally:
            deadline_guard.cancel()

    response.close = close_with_deadline_cleanup


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
