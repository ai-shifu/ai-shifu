"""Security contract tests for untrusted outbound HTTP requests."""

from __future__ import annotations

import ipaddress
import threading
from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING

import pytest
from flaskr.common.safe_outbound import (
    OutboundDeadlineExceededError,
    OutboundRedirectError,
    OutboundResponseTooLargeError,
    OutboundUrlPolicy,
    Resolver,
    SafeOutboundClient,
    SafeOutboundResponse,
    UnsafeOutboundUrlError,
    ValidatedOutboundUrl,
    validate_outbound_url,
)
from urllib3.response import HTTPResponse

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from urllib3.util import Timeout


def _resolver(*addresses: str) -> Resolver:
    def resolve(_hostname: str, _port: int) -> Iterable[str]:
        return addresses

    return resolve


@pytest.mark.parametrize(
    ("url", "address"),
    [
        ("http://localhost/image.png", "127.0.0.1"),
        ("http://127.0.0.1/image.png", "127.0.0.1"),
        ("http://[::1]/image.png", "::1"),
        ("http://service.internal/image.png", "10.0.0.8"),
        ("http://metadata/image.png", "169.254.169.254"),
        ("http://reserved/image.png", "192.0.2.10"),
    ],
)
def test_validation_rejects_non_public_destinations(url: str, address: str) -> None:
    with pytest.raises(UnsafeOutboundUrlError, match="non-public"):
        validate_outbound_url(url, resolver=_resolver(address))


def test_validation_rejects_mixed_public_and_private_dns_results() -> None:
    with pytest.raises(UnsafeOutboundUrlError, match="non-public"):
        validate_outbound_url(
            "https://mixed.example/image.png",
            resolver=_resolver("93.184.216.34", "10.0.0.8"),
        )


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "https://user:secret@example.com/file",
        "https://example.com:8080/file",
        "https:///missing-host",
    ],
)
def test_validation_rejects_malformed_or_disallowed_urls(url: str) -> None:
    with pytest.raises(UnsafeOutboundUrlError):
        validate_outbound_url(url, resolver=_resolver("93.184.216.34"))


def test_validation_rejects_invalid_dns_label_as_unsafe_url() -> None:
    invalid_host = "a" * 64 + ".example"

    with pytest.raises(UnsafeOutboundUrlError, match="could not be resolved"):
        validate_outbound_url(f"https://{invalid_host}/resource")


def test_validation_normalizes_public_url_and_addresses() -> None:
    result = validate_outbound_url(
        "HTTPS://Example.COM./asset?q=1#fragment",
        resolver=_resolver("93.184.216.34", "93.184.216.34"),
    )

    assert result.url == "https://example.com/asset?q=1"
    assert result.origin == "https://example.com"
    assert result.addresses == (ipaddress.ip_address("93.184.216.34"),)
    assert result.trusted_origin is False


def test_exact_trusted_origin_allows_local_self_hosted_service() -> None:
    policy = OutboundUrlPolicy(trusted_origins=frozenset({"http://localhost:5001"}))

    result = validate_outbound_url(
        "http://LOCALHOST:5001/v1/chat",
        policy=policy,
        resolver=_resolver("127.0.0.1"),
    )

    assert result.trusted_origin is True
    assert result.origin == "http://localhost:5001"


def test_trusted_origin_does_not_allow_other_local_ports() -> None:
    policy = OutboundUrlPolicy(trusted_origins=frozenset({"http://localhost:5001"}))

    with pytest.raises(UnsafeOutboundUrlError, match="disallowed port"):
        validate_outbound_url(
            "http://localhost:5002/v1/chat",
            policy=policy,
            resolver=_resolver("127.0.0.1"),
        )


@dataclass(frozen=True)
class _Reply:
    status: int
    headers: Mapping[str, str]
    body: bytes = b""


class _FakeTransport:
    def __init__(self, replies: list[_Reply]) -> None:
        self.replies = list(replies)
        self.calls: list[
            tuple[
                str,
                ValidatedOutboundUrl,
                ipaddress.IPv4Address | ipaddress.IPv6Address,
                Mapping[str, str],
                bytes | None,
            ]
        ] = []

    def __call__(
        self,
        method: str,
        target: ValidatedOutboundUrl,
        address: ipaddress.IPv4Address | ipaddress.IPv6Address,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout: Timeout,
    ) -> HTTPResponse:
        del timeout
        self.calls.append((method, target, address, dict(headers), body))
        reply = self.replies.pop(0)
        return HTTPResponse(
            body=BytesIO(reply.body),
            status=reply.status,
            headers=dict(reply.headers),
            preload_content=False,
        )


def test_client_pins_transport_to_validated_address() -> None:
    transport = _FakeTransport([_Reply(200, {}, b"image")])
    client = SafeOutboundClient(
        resolver=_resolver("93.184.216.34"),
        transport=transport,
    )

    response = client.request("GET", "https://example.com/image.png")

    assert response.content == b"image"
    assert transport.calls[0][2] == ipaddress.ip_address("93.184.216.34")
    assert transport.calls[0][1].hostname == "example.com"


def test_response_iter_lines_decodes_utf8_and_normalizes_crlf() -> None:
    transport = _FakeTransport(
        [_Reply(200, {}, "data: 你好\r\ndata: world\n".encode())]
    )
    client = SafeOutboundClient(
        resolver=_resolver("93.184.216.34"),
        transport=transport,
    )
    response = client.request("GET", "https://example.com/events")

    assert list(response.iter_lines(decode_unicode=True)) == [
        "data: 你好",
        "data: world",
    ]


def test_response_iter_lines_handles_bare_cr_and_split_crlf() -> None:
    class ChunkedRawResponse:
        def __init__(self) -> None:
            self.chunks = [
                b"data: one\rdata: two\r",
                b"\ndata: three\r",
            ]

        def read1(self, _size: int) -> bytes:
            return self.chunks.pop(0) if self.chunks else b""

        def read(self, size: int) -> bytes:
            return self.read1(size)

        def close(self) -> None:
            pass

    response = SafeOutboundResponse(
        status=200,
        headers={},
        url="https://example.com/events",
        _raw=ChunkedRawResponse(),
        _max_bytes=1024,
        _deadline=float("inf"),
    )

    assert list(response.iter_lines(decode_unicode=True)) == [
        "data: one",
        "data: two",
        "data: three",
    ]


def test_default_https_transport_uses_pinned_ip_with_original_tls_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakePool:
        def __init__(self, host: str, **kwargs: object) -> None:
            captured["pool_host"] = host
            captured["pool_kwargs"] = kwargs

        def urlopen(self, method: str, path: str, **kwargs: object) -> HTTPResponse:
            captured["method"] = method
            captured["path"] = path
            captured["request_kwargs"] = kwargs
            return HTTPResponse(
                body=BytesIO(b"ok"),
                status=200,
                headers={},
                preload_content=False,
            )

    monkeypatch.setattr(
        "flaskr.common.safe_outbound_transport.urllib3.HTTPSConnectionPool",
        FakePool,
    )
    client = SafeOutboundClient(resolver=_resolver("93.184.216.34"))

    response = client.request("GET", "https://example.com/resource?q=1")

    assert response.content == b"ok"
    assert captured["pool_host"] == "93.184.216.34"
    pool_kwargs = captured["pool_kwargs"]
    assert isinstance(pool_kwargs, dict)
    assert pool_kwargs["assert_hostname"] == "example.com"
    assert pool_kwargs["server_hostname"] == "example.com"
    request_kwargs = captured["request_kwargs"]
    assert isinstance(request_kwargs, dict)
    assert request_kwargs["headers"]["Host"] == "example.com"
    assert "host" not in request_kwargs["headers"]
    assert captured["path"] == "/resource?q=1"


def test_default_transport_replaces_caller_host_case_insensitively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakePool:
        def __init__(self, _host: str, **_kwargs: object) -> None:
            pass

        def urlopen(self, _method: str, _path: str, **kwargs: object) -> HTTPResponse:
            captured["headers"] = kwargs["headers"]
            return HTTPResponse(body=BytesIO(b"ok"), status=200, preload_content=False)

    monkeypatch.setattr(
        "flaskr.common.safe_outbound_transport.urllib3.HTTPSConnectionPool",
        FakePool,
    )
    client = SafeOutboundClient(resolver=_resolver("93.184.216.34"))

    response = client.request(
        "GET",
        "https://example.com/resource",
        headers={"host": "attacker.example"},
    )

    assert response.content == b"ok"
    assert captured["headers"] == {"Host": "example.com"}


def test_client_tries_later_validated_address_after_connection_failure() -> None:
    transport = _FakeTransport([_Reply(200, {}, b"ok")])
    attempted: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []

    def fail_first(
        method: str,
        target: ValidatedOutboundUrl,
        address: ipaddress.IPv4Address | ipaddress.IPv6Address,
        **kwargs: object,
    ) -> HTTPResponse:
        attempted.append(address)
        if len(attempted) == 1:
            message = "unreachable"
            raise OSError(message)
        return transport(method, target, address, **kwargs)

    client = SafeOutboundClient(
        resolver=_resolver("2001:4860:4860::8888", "93.184.216.34"),
        transport=fail_first,
    )

    assert client.request("GET", "https://example.com/resource").content == b"ok"
    assert attempted == [
        ipaddress.ip_address("2001:4860:4860::8888"),
        ipaddress.ip_address("93.184.216.34"),
    ]


def test_client_revalidates_and_rejects_private_redirect() -> None:
    transport = _FakeTransport([_Reply(302, {"Location": "http://metadata/latest"})])

    def resolve(hostname: str, _port: int) -> Iterable[str]:
        if hostname == "metadata":
            return ("169.254.169.254",)
        return ("93.184.216.34",)

    client = SafeOutboundClient(resolver=resolve, transport=transport)

    with pytest.raises(UnsafeOutboundUrlError, match="non-public"):
        client.request("GET", "https://example.com/start")


def test_client_follows_safe_relative_redirect() -> None:
    transport = _FakeTransport(
        [
            _Reply(302, {"Location": "/final"}),
            _Reply(200, {}, b"done"),
        ]
    )
    client = SafeOutboundClient(
        resolver=_resolver("93.184.216.34"),
        transport=transport,
    )

    response = client.request("GET", "https://example.com/start")

    assert response.url == "https://example.com/final"
    assert response.content == b"done"
    assert len(transport.calls) == 2


def test_client_strips_secrets_from_cross_origin_redirect() -> None:
    transport = _FakeTransport(
        [
            _Reply(302, {"Location": "https://cdn.example.net/final"}),
            _Reply(200, {}, b"done"),
        ]
    )
    client = SafeOutboundClient(
        resolver=_resolver("93.184.216.34"),
        transport=transport,
    )

    response = client.request(
        "GET",
        "https://example.com/start",
        headers={
            "Authorization": "Bearer secret",
            "X-Api-Key": "also-secret",
            "Accept": "image/*",
        },
    )
    assert response.content == b"done"

    assert transport.calls[0][3]["Authorization"] == "Bearer secret"
    assert "Authorization" not in transport.calls[1][3]
    assert "X-Api-Key" not in transport.calls[1][3]
    assert transport.calls[1][3]["Accept"] == "image/*"


def test_client_rejects_cross_origin_redirect_for_request_with_body() -> None:
    client = SafeOutboundClient(
        resolver=_resolver("93.184.216.34"),
        transport=_FakeTransport(
            [_Reply(307, {"Location": "https://other.example/final"})]
        ),
    )

    with pytest.raises(OutboundRedirectError, match="bodyless safe requests"):
        client.request(
            "POST",
            "https://example.com/start",
            headers={"Authorization": "Bearer secret"},
            body=b"payload",
        )


def test_client_rejects_cross_origin_get_redirect_with_body() -> None:
    client = SafeOutboundClient(
        resolver=_resolver("93.184.216.34"),
        transport=_FakeTransport(
            [_Reply(307, {"Location": "https://other.example/final"})]
        ),
    )

    with pytest.raises(OutboundRedirectError, match="bodyless safe requests"):
        client.request("GET", "https://example.com/start", body=b"payload")


def test_client_keeps_authorization_on_same_origin_redirect() -> None:
    transport = _FakeTransport(
        [
            _Reply(307, {"Location": "/final"}),
            _Reply(200, {}, b"done"),
        ]
    )
    client = SafeOutboundClient(
        resolver=_resolver("93.184.216.34"),
        transport=transport,
    )

    response = client.request(
        "POST",
        "https://example.com/start",
        headers={"Authorization": "Bearer secret"},
        body=b"payload",
    )
    assert response.content == b"done"

    assert transport.calls[1][3]["Authorization"] == "Bearer secret"
    assert transport.calls[1][4] == b"payload"


def test_client_rejects_redirect_without_location() -> None:
    client = SafeOutboundClient(
        resolver=_resolver("93.184.216.34"),
        transport=_FakeTransport([_Reply(302, {})]),
    )

    with pytest.raises(OutboundRedirectError, match="missing Location"):
        client.request("GET", "https://example.com/start")


def test_client_rejects_redirects_past_limit() -> None:
    policy = OutboundUrlPolicy(max_redirects=1)
    client = SafeOutboundClient(
        policy=policy,
        resolver=_resolver("93.184.216.34"),
        transport=_FakeTransport(
            [
                _Reply(302, {"Location": "/second"}),
                _Reply(302, {"Location": "/third"}),
            ]
        ),
    )

    with pytest.raises(OutboundRedirectError, match="limit exceeded"):
        client.request("GET", "https://example.com/start")


@pytest.mark.parametrize(
    "reply",
    [
        _Reply(200, {"Content-Length": "5"}, b"12345"),
        _Reply(200, {}, b"12345"),
    ],
)
def test_client_rejects_declared_and_streamed_oversized_responses(
    reply: _Reply,
) -> None:
    policy = OutboundUrlPolicy(max_response_bytes=4)
    client = SafeOutboundClient(
        policy=policy,
        resolver=_resolver("93.184.216.34"),
        transport=_FakeTransport([reply]),
    )

    with pytest.raises(OutboundResponseTooLargeError, match="byte limit"):
        _ = client.request("GET", "https://example.com/image.png").content


def test_post_redirect_303_becomes_get_without_body() -> None:
    transport = _FakeTransport(
        [
            _Reply(303, {"Location": "/result"}),
            _Reply(200, {}, b"ok"),
        ]
    )
    client = SafeOutboundClient(
        resolver=_resolver("93.184.216.34"),
        transport=transport,
    )

    client.request("POST", "https://example.com/start", body=b"payload")

    assert (transport.calls[0][0], transport.calls[0][4]) == ("POST", b"payload")
    assert (transport.calls[1][0], transport.calls[1][4]) == ("GET", None)


def test_cross_origin_post_redirect_303_becomes_safe_get() -> None:
    transport = _FakeTransport(
        [
            _Reply(303, {"Location": "https://results.example/final"}),
            _Reply(200, {}, b"ok"),
        ]
    )
    client = SafeOutboundClient(
        resolver=_resolver("93.184.216.34"),
        transport=transport,
    )

    response = client.request(
        "POST",
        "https://example.com/start",
        headers={"Authorization": "Bearer secret", "Content-Type": "text/plain"},
        body=b"payload",
    )

    assert response.content == b"ok"
    assert (transport.calls[1][0], transport.calls[1][4]) == ("GET", None)
    assert "Authorization" not in transport.calls[1][3]
    assert "Content-Type" not in transport.calls[1][3]


def test_response_can_be_consumed_as_bounded_stream() -> None:
    client = SafeOutboundClient(
        resolver=_resolver("93.184.216.34"),
        transport=_FakeTransport([_Reply(200, {}, b"abcdef")]),
    )

    response = client.request("GET", "https://example.com/stream")

    assert list(response.iter_bytes(chunk_size=2)) == [b"ab", b"cd", b"ef"]


def test_response_stream_enforces_wall_clock_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    monkeypatch.setattr("flaskr.common.safe_outbound.time.monotonic", lambda: clock[0])
    client = SafeOutboundClient(
        policy=OutboundUrlPolicy(total_timeout_seconds=1),
        resolver=_resolver("93.184.216.34"),
        transport=_FakeTransport([_Reply(200, {}, b"abcdef")]),
    )
    response = client.request("GET", "https://example.com/stream")
    clock[0] = 2.0

    with pytest.raises(OutboundDeadlineExceededError, match="total timeout"):
        list(response.iter_bytes(chunk_size=2))


def test_client_enforces_deadline_during_dns_resolution() -> None:
    release_resolver = threading.Event()

    def stalled_resolver(_hostname: str, _port: int) -> tuple[str, ...]:
        release_resolver.wait(timeout=1)
        return ("93.184.216.34",)

    client = SafeOutboundClient(
        policy=OutboundUrlPolicy(total_timeout_seconds=0.01),
        resolver=stalled_resolver,
        transport=_FakeTransport([_Reply(200, {}, b"ok")]),
    )

    try:
        with pytest.raises(OutboundDeadlineExceededError, match="DNS resolution"):
            client.request("GET", "https://example.com/resource")
    finally:
        release_resolver.set()
