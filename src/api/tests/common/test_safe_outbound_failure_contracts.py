"""Exercise outbound policy validation, bounded reads and connection failures."""

import socket
from unittest.mock import Mock

import pytest
from flaskr.common import safe_outbound as outbound
from urllib3.exceptions import ConnectTimeoutError, NewConnectionError

from tests.common.test_safe_outbound import _FakeTransport, _Reply, _resolver


@pytest.mark.parametrize(
    "changes",
    [
        {"allowed_schemes": frozenset()},
        {"allowed_schemes": frozenset({"file"})},
        {"allowed_ports": frozenset()},
        {"allowed_ports": frozenset({True})},
        {"allowed_ports": frozenset({0})},
        {"allowed_ports": frozenset({65536})},
        {"max_redirects": -1},
        {"max_response_bytes": 0},
        {"connect_timeout_seconds": 0},
        {"read_timeout_seconds": -1},
        {"total_timeout_seconds": 0},
    ],
)
def test_invalid_outbound_policy_cannot_be_constructed(changes: dict) -> None:
    key = next(iter(changes))
    message = "outbound timeouts" if "timeout" in key else key
    with pytest.raises(ValueError, match=message):
        outbound.OutboundUrlPolicy(**changes)


@pytest.mark.parametrize(
    "origin",
    [
        "ftp://example.test",
        "https://user:secret@example.test",
        "https://example.test/path",
        "https://example.test?query=1",
        "https://example.test#fragment",
        "https://example.test:invalid",
        "https://[invalid",
        "",
    ],
)
def test_trusted_origin_cannot_silently_expand_to_url_prefix_or_credentials(
    origin: str,
) -> None:
    with pytest.raises(ValueError, match="valid HTTP origins"):
        outbound.OutboundUrlPolicy(trusted_origins=frozenset({origin}))


@pytest.mark.parametrize("addresses", [(), ("invalid-ip",)])
def test_failed_or_invalid_dns_result_never_reaches_transport(addresses: tuple) -> None:
    transport = Mock()
    client = outbound.SafeOutboundClient(
        resolver=_resolver(*addresses), transport=transport
    )
    with pytest.raises(
        outbound.UnsafeOutboundUrlError, match=r"did not resolve|invalid address"
    ):
        client.request("GET", "https://example.test/path")
    transport.assert_not_called()


def test_blank_method_rejected_before_dns_lookup() -> None:
    resolver = Mock()
    client = outbound.SafeOutboundClient(resolver=resolver, transport=Mock())
    with pytest.raises(ValueError, match="HTTP method is required"):
        client.request(" ", "https://example.test")
    resolver.assert_not_called()


def test_all_pinned_connection_failures_surface_last_error_without_new_dns() -> None:
    resolver = Mock(return_value=("93.184.216.34", "93.184.216.35"))
    final_error = NewConnectionError(None, "connection refused")
    transport = Mock(side_effect=[ConnectTimeoutError("timeout"), final_error])
    client = outbound.SafeOutboundClient(resolver=resolver, transport=transport)
    with pytest.raises(NewConnectionError) as error:
        client.request("GET", "https://example.test")
    assert error.value is final_error
    resolver.assert_called_once_with("example.test", 443)
    assert [str(call.args[2]) for call in transport.call_args_list] == [
        "93.184.216.34",
        "93.184.216.35",
    ]


@pytest.mark.parametrize("payload", [b"", b"hello"])
def test_cached_body_is_repeatable_after_connection_close(payload: bytes) -> None:
    raw = Mock()
    raw.read1.side_effect = [payload, b""] if payload else [b""]
    response = outbound.SafeOutboundResponse(
        200, {}, "https://example.test/", raw, 100, float("inf")
    )
    assert response.content == payload
    read_count = raw.read1.call_count
    assert response.content == payload
    assert list(response.iter_bytes()) == ([payload] if payload else [])
    assert raw.read1.call_count == read_count
    raw.close.assert_called_once()
    with pytest.raises(ValueError, match="chunk_size must be positive"):
        list(response.iter_bytes(chunk_size=0))


@pytest.mark.parametrize("expired", [False, True])
def test_read_failure_closes_response_and_maps_only_expired_deadline(
    monkeypatch: pytest.MonkeyPatch,
    expired: bool,
) -> None:
    clock = [0.0]
    monkeypatch.setattr(outbound.time, "monotonic", lambda: clock[0])
    raw = Mock()
    original = OSError("socket read failed")

    def fail(_size: int) -> None:
        clock[0] = 2.0 if expired else 0.5
        raise original

    raw.read1.side_effect = fail
    response = outbound.SafeOutboundResponse(
        200, {}, "https://example.test/", raw, 100, 1.0
    )
    with pytest.raises(
        outbound.OutboundDeadlineExceededError if expired else OSError
    ) as error:
        _ = response.content
    if expired:
        assert error.value.__cause__ is original
    else:
        assert error.value is original
    raw.close.assert_called_once()


@pytest.mark.parametrize("decode", [False, True])
def test_trailing_carriage_return_yields_one_final_line(decode: bool) -> None:
    client = outbound.SafeOutboundClient(
        resolver=_resolver("93.184.216.34"),
        transport=_FakeTransport([_Reply(200, {}, b"last\r")]),
    )
    with client.request("GET", "https://example.test") as response:
        assert list(response.iter_lines(decode_unicode=decode)) == (
            ["last"] if decode else [b"last"]
        )


def test_invalid_content_length_cannot_bypass_actual_stream_limit() -> None:
    client = outbound.SafeOutboundClient(
        policy=outbound.OutboundUrlPolicy(max_response_bytes=3),
        resolver=_resolver("93.184.216.34"),
        transport=_FakeTransport([_Reply(200, {"Content-Length": "invalid"}, b"four")]),
    )
    with (
        client.request("GET", "https://example.test") as response,
        pytest.raises(outbound.OutboundResponseTooLargeError),
    ):
        _ = response.content


def test_literal_resolution_bypasses_dns_and_dns_failures_are_policy_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = Mock(side_effect=socket.gaierror("host not found"))
    monkeypatch.setattr(outbound.socket, "getaddrinfo", resolver)
    assert outbound._resolve_addresses("2001:4860:4860::8888", 443) == (
        "2001:4860:4860::8888",
    )
    resolver.assert_not_called()
    with pytest.raises(outbound.UnsafeOutboundUrlError, match="could not be resolved"):
        outbound._resolve_addresses("missing.example.test", 443)
