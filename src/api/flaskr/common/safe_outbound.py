"""Make bounded HTTP requests to untrusted outbound URLs."""

from __future__ import annotations

import ipaddress
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol, Self
from urllib.parse import SplitResult, urljoin, urlsplit, urlunsplit

from urllib3.exceptions import ConnectTimeoutError, NewConnectionError
from urllib3.util import Timeout

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from urllib3.response import HTTPResponse

DEFAULT_ALLOWED_PORTS = frozenset({80, 443})
DEFAULT_MAX_REDIRECTS = 3
DEFAULT_MAX_RESPONSE_BYTES = 10 * 1024 * 1024
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5.0
DEFAULT_READ_TIMEOUT_SECONDS = 15.0
DEFAULT_TOTAL_TIMEOUT_SECONDS = 30.0
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
SAFE_CROSS_ORIGIN_HEADERS = frozenset(
    {"accept", "accept-encoding", "accept-language", "user-agent"}
)
_DNS_EXECUTOR = ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="safe-outbound-dns"
)


class UnsafeOutboundUrlError(ValueError):
    """Raised when an outbound URL violates the configured network policy."""


class OutboundResponseTooLargeError(ValueError):
    """Raised when an outbound response exceeds its configured byte limit."""


class OutboundRedirectError(ValueError):
    """Raised when an outbound response has an invalid redirect chain."""


class OutboundDeadlineExceededError(TimeoutError):
    """Raised when an outbound request exceeds its wall-clock deadline."""


@dataclass(frozen=True)
class OutboundUrlPolicy:
    """Security and resource limits for an outbound request."""

    allowed_schemes: frozenset[str] = frozenset({"http", "https"})
    allowed_ports: frozenset[int] = DEFAULT_ALLOWED_PORTS
    trusted_origins: frozenset[str] = frozenset()
    max_redirects: int = DEFAULT_MAX_REDIRECTS
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS
    read_timeout_seconds: float = DEFAULT_READ_TIMEOUT_SECONDS
    total_timeout_seconds: float = DEFAULT_TOTAL_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        """Normalize and validate the immutable policy values."""
        normalized_schemes = frozenset(
            str(scheme).strip().lower() for scheme in self.allowed_schemes
        )
        normalized_origins = frozenset(
            _normalize_trusted_origin(origin) for origin in self.trusted_origins
        )
        if not normalized_schemes or not normalized_schemes <= {"http", "https"}:
            message = "allowed_schemes must contain only http and/or https"
            raise ValueError(message)
        if not self.allowed_ports or any(
            isinstance(port, bool) or not 1 <= port <= 65535
            for port in self.allowed_ports
        ):
            message = "allowed_ports must contain valid TCP ports"
            raise ValueError(message)
        if self.max_redirects < 0:
            message = "max_redirects must be nonnegative"
            raise ValueError(message)
        if self.max_response_bytes <= 0:
            message = "max_response_bytes must be positive"
            raise ValueError(message)
        if (
            self.connect_timeout_seconds <= 0
            or self.read_timeout_seconds <= 0
            or self.total_timeout_seconds <= 0
        ):
            message = "outbound timeouts must be positive"
            raise ValueError(message)
        object.__setattr__(self, "allowed_schemes", normalized_schemes)
        object.__setattr__(self, "trusted_origins", normalized_origins)


@dataclass(frozen=True)
class ValidatedOutboundUrl:
    """A normalized URL and the public addresses approved for its connection."""

    url: str
    scheme: str
    hostname: str
    port: int
    origin: str
    addresses: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]
    trusted_origin: bool = False


class Resolver(Protocol):
    """Resolve a hostname into candidate textual IP addresses."""

    def __call__(self, hostname: str, port: int) -> Iterable[str]:
        """Return every address that the hostname currently resolves to."""
        ...


class Transport(Protocol):
    """Open one request against an already validated destination address."""

    def __call__(
        self,
        method: str,
        target: ValidatedOutboundUrl,
        address: ipaddress.IPv4Address | ipaddress.IPv6Address,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout: Timeout,
        deadline: float,
    ) -> HTTPResponse:
        """Open one request without resolving the hostname again."""
        ...


@dataclass
class SafeOutboundResponse:
    """A bounded response returned by :class:`SafeOutboundClient`."""

    status: int
    headers: Mapping[str, str]
    url: str
    _raw: HTTPResponse = field(repr=False)
    _max_bytes: int = field(repr=False)
    _deadline: float = field(repr=False)
    _cached_body: bytes | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        """Reject a declared body size before a caller starts consuming it."""
        _validate_content_length(self.headers, max_bytes=self._max_bytes)

    @property
    def content(self) -> bytes:
        """Return the bounded response body."""
        if self._cached_body is None:
            self._cached_body = b"".join(self.iter_bytes())
        return self._cached_body

    def iter_bytes(self, chunk_size: int = 64 * 1024) -> Iterable[bytes]:
        """Yield response bytes while enforcing the total response limit."""
        if chunk_size <= 0:
            message = "chunk_size must be positive"
            raise ValueError(message)
        if self._cached_body is not None:
            if self._cached_body:
                yield self._cached_body
            return

        total = 0
        read = getattr(self._raw, "read1", self._raw.read)
        try:
            while True:
                _check_deadline(self._deadline)
                try:
                    chunk = read(min(chunk_size, self._max_bytes - total + 1))
                except Exception as exc:
                    if time.monotonic() >= self._deadline:
                        message = "outbound request exceeded its total timeout"
                        raise OutboundDeadlineExceededError(message) from exc
                    raise
                _check_deadline(self._deadline)
                if not chunk:
                    return
                total += len(chunk)
                if total > self._max_bytes:
                    message = "outbound response exceeds the configured byte limit"
                    raise OutboundResponseTooLargeError(message)
                yield chunk
        finally:
            self.close()

    def iter_lines(self, *, decode_unicode: bool = False) -> Iterable[bytes | str]:
        """Yield bounded response lines without buffering the complete body."""
        pending = bytearray()
        for chunk in self.iter_bytes():
            pending.extend(chunk)
            while True:
                separator_index = next(
                    (
                        index
                        for index, value in enumerate(pending)
                        if value in {0x0A, 0x0D}
                    ),
                    -1,
                )
                if separator_index < 0:
                    break
                separator = pending[separator_index]
                if separator == 0x0D and separator_index + 1 == len(pending):
                    break
                separator_size = (
                    2
                    if separator == 0x0D and pending[separator_index + 1] == 0x0A
                    else 1
                )
                line = bytes(pending[:separator_index])
                del pending[: separator_index + separator_size]
                yield line.decode("utf-8", errors="replace") if decode_unicode else line
        if pending.endswith(b"\r"):
            pending.pop()
            line = bytes(pending)
            yield line.decode("utf-8", errors="replace") if decode_unicode else line
            return
        if pending:
            line = bytes(pending)
            yield (line.decode("utf-8", errors="replace") if decode_unicode else line)

    def close(self) -> None:
        """Close the underlying connection."""
        self._raw.close()

    def __enter__(self) -> Self:
        """Return this response as a managed resource."""
        return self

    def __exit__(self, *_exc_info: object) -> None:
        """Close the response when leaving a context manager."""
        self.close()


class SafeOutboundClient:
    """Validate, pin, redirect, and bound requests to untrusted URLs."""

    def __init__(
        self,
        *,
        policy: OutboundUrlPolicy | None = None,
        resolver: Resolver | None = None,
        transport: Transport | None = None,
    ) -> None:
        """Create a client with injectable DNS and transport boundaries."""
        if transport is None:
            from flaskr.common.safe_outbound_transport import open_pinned_request

            transport = open_pinned_request
        self.policy = policy or OutboundUrlPolicy()
        self._resolver = resolver or _resolve_addresses
        self._transport = transport

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
    ) -> SafeOutboundResponse:
        """Perform one bounded request, validating every redirect target."""
        normalized_method = str(method or "").strip().upper()
        if not normalized_method:
            message = "HTTP method is required"
            raise ValueError(message)

        current_url = url
        current_method = normalized_method
        current_body = body
        request_headers = dict(headers or {})
        deadline = time.monotonic() + self.policy.total_timeout_seconds

        for redirect_count in range(self.policy.max_redirects + 1):
            target = validate_outbound_url(
                current_url,
                policy=self.policy,
                resolver=self._deadline_resolver(deadline),
            )
            _check_deadline(deadline)
            response = self._open_validated_target(
                current_method,
                target,
                headers=request_headers,
                body=current_body,
                deadline=deadline,
            )
            if response.status not in REDIRECT_STATUSES:
                try:
                    return SafeOutboundResponse(
                        status=response.status,
                        headers=MappingProxyType(dict(response.headers)),
                        url=target.url,
                        _raw=response,
                        _max_bytes=self.policy.max_response_bytes,
                        _deadline=deadline,
                    )
                except Exception:
                    response.close()
                    raise

            try:
                location = _get_header(response.headers, "location")
                if not location:
                    message = "redirect response is missing Location"
                    raise OutboundRedirectError(message)
                if redirect_count >= self.policy.max_redirects:
                    message = "outbound redirect limit exceeded"
                    raise OutboundRedirectError(message)
                next_url = urljoin(target.url, location)
                next_target = validate_outbound_url(
                    next_url,
                    policy=self.policy,
                    resolver=self._deadline_resolver(deadline),
                )
                next_method = current_method
                next_body = current_body
                if response.status == 303 or (
                    response.status in {301, 302} and current_method == "POST"
                ):
                    next_method = "GET"
                    next_body = None
                if next_target.origin != target.origin:
                    if next_method not in {"GET", "HEAD"} or next_body is not None:
                        message = (
                            "cross-origin redirects must become bodyless safe requests"
                        )
                        raise OutboundRedirectError(message)
                    request_headers = _safe_cross_origin_headers(request_headers)
                current_url = next_target.url
                if next_method != current_method or next_body is not current_body:
                    request_headers = _without_headers(
                        request_headers,
                        frozenset({"content-length", "content-type"}),
                    )
                current_method = next_method
                current_body = next_body
            finally:
                response.close()

        message = "redirect loop must return or raise"
        raise AssertionError(message)

    def _deadline_resolver(self, deadline: float) -> Resolver:
        def resolve(hostname: str, port: int) -> tuple[str, ...]:
            future = _DNS_EXECUTOR.submit(lambda: tuple(self._resolver(hostname, port)))
            try:
                return future.result(timeout=_remaining_seconds(deadline))
            except FutureTimeoutError as exc:
                future.cancel()
                message = "outbound DNS resolution exceeded the total timeout"
                raise OutboundDeadlineExceededError(message) from exc

        return resolve

    def _open_validated_target(
        self,
        method: str,
        target: ValidatedOutboundUrl,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        deadline: float,
    ) -> HTTPResponse:
        last_error: ConnectTimeoutError | NewConnectionError | None = None
        for address in target.addresses:
            remaining = _remaining_seconds(deadline)
            try:
                return self._transport(
                    method,
                    target,
                    address,
                    headers=headers,
                    body=body,
                    timeout=Timeout(
                        total=remaining,
                        connect=min(self.policy.connect_timeout_seconds, remaining),
                        read=min(self.policy.read_timeout_seconds, remaining),
                    ),
                    deadline=deadline,
                )
            except (ConnectTimeoutError, NewConnectionError) as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        message = "validated outbound target has no addresses"
        raise UnsafeOutboundUrlError(message)


def validate_outbound_url(
    url: str,
    *,
    policy: OutboundUrlPolicy | None = None,
    resolver: Resolver | None = None,
) -> ValidatedOutboundUrl:
    """Normalize a URL and reject destinations outside its outbound policy."""
    effective_policy = policy or OutboundUrlPolicy()
    effective_resolver = resolver or _resolve_addresses
    raw_url = str(url or "").strip()
    try:
        parsed = urlsplit(raw_url)
        port = parsed.port
    except ValueError as exc:
        message = "outbound URL is malformed"
        raise UnsafeOutboundUrlError(message) from exc

    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if scheme not in effective_policy.allowed_schemes or not hostname:
        message = "outbound URL must use an allowed HTTP scheme and host"
        raise UnsafeOutboundUrlError(message)
    if parsed.username is not None or parsed.password is not None:
        message = "outbound URL must not contain credentials"
        raise UnsafeOutboundUrlError(message)

    effective_port = port or (443 if scheme == "https" else 80)
    origin = _build_origin(scheme, hostname, effective_port)
    trusted_origin = origin in effective_policy.trusted_origins
    if effective_port not in effective_policy.allowed_ports and not trusted_origin:
        message = "outbound URL uses a disallowed port"
        raise UnsafeOutboundUrlError(message)

    normalized_url = _normalize_url(parsed, scheme, hostname, effective_port)
    addresses = _parse_addresses(effective_resolver(hostname, effective_port))
    if not addresses:
        message = "outbound URL host did not resolve"
        raise UnsafeOutboundUrlError(message)
    if not trusted_origin and any(not address.is_global for address in addresses):
        message = "outbound URL resolves to a non-public address"
        raise UnsafeOutboundUrlError(message)

    return ValidatedOutboundUrl(
        url=normalized_url,
        scheme=scheme,
        hostname=hostname,
        port=effective_port,
        origin=origin,
        addresses=addresses,
        trusted_origin=trusted_origin,
    )


def _normalize_trusted_origin(origin: str) -> str:
    raw_origin = str(origin or "").strip()
    try:
        parsed = urlsplit(raw_origin)
        port = parsed.port
    except ValueError as exc:
        message = "trusted origins must be valid HTTP origins"
        raise ValueError(message) from exc
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if (
        scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        message = "trusted origins must be valid HTTP origins"
        raise ValueError(message)
    effective_port = port or (443 if scheme == "https" else 80)
    return _build_origin(scheme, hostname, effective_port)


def _normalize_url(
    parsed: SplitResult,
    scheme: str,
    hostname: str,
    port: int,
) -> str:
    default_port = 443 if scheme == "https" else 80
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    netloc = display_host if port == default_port else f"{display_host}:{port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def _build_origin(scheme: str, hostname: str, port: int) -> str:
    default_port = 443 if scheme == "https" else 80
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    if port == default_port:
        return f"{scheme}://{display_host}"
    return f"{scheme}://{display_host}:{port}"


def _parse_addresses(
    addresses: Iterable[str],
) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    parsed: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    seen: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    try:
        for value in addresses:
            address = ipaddress.ip_address(str(value).split("%", 1)[0])
            if address not in seen:
                seen.add(address)
                parsed.append(address)
    except ValueError as exc:
        message = "outbound URL resolved to an invalid address"
        raise UnsafeOutboundUrlError(message) from exc
    return tuple(parsed)


def _resolve_addresses(hostname: str, port: int) -> tuple[str, ...]:
    try:
        literal = ipaddress.ip_address(hostname.split("%", 1)[0])
    except ValueError:
        try:
            results = socket.getaddrinfo(
                hostname,
                port,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            )
        except (socket.gaierror, UnicodeError) as exc:
            message = "outbound URL host could not be resolved"
            raise UnsafeOutboundUrlError(message) from exc
        return tuple(result[4][0] for result in results)
    return (str(literal),)


def _remaining_seconds(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        message = "outbound request exceeded its total timeout"
        raise OutboundDeadlineExceededError(message)
    return remaining


def _check_deadline(deadline: float) -> None:
    _remaining_seconds(deadline)


def _safe_cross_origin_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() in SAFE_CROSS_ORIGIN_HEADERS
    }


def _without_headers(
    headers: Mapping[str, str],
    denied_headers: frozenset[str],
) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in denied_headers
    }


def _validate_content_length(
    headers: Mapping[str, str],
    *,
    max_bytes: int,
) -> None:
    content_length = _get_header(headers, "content-length")
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError:
            declared_length = -1
        if declared_length > max_bytes:
            message = "outbound response exceeds the configured byte limit"
            raise OutboundResponseTooLargeError(message)


def _get_header(headers: Mapping[str, str], name: str) -> str | None:
    expected_name = name.lower()
    return next(
        (value for key, value in headers.items() if key.lower() == expected_name),
        None,
    )
