"""Verify remote image imports cannot reach internal network targets."""

from __future__ import annotations

import contextlib
from io import BytesIO
from types import SimpleNamespace
from typing import TYPE_CHECKING, Self

import pytest
from flask import Flask
from flaskr.common.safe_outbound import (
    OutboundResponseTooLargeError,
    SafeOutboundClient,
)
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.shifu import funcs
from urllib3.response import HTTPResponse

if TYPE_CHECKING:
    import ipaddress
    from collections.abc import Iterator, Mapping

    from urllib3.util import Timeout


class _Response:
    def __init__(
        self,
        *,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
        content: bytes = b"image",
        url: str = "https://images.example/photo.png",
    ) -> None:
        self.status = status
        self.headers = dict(headers or {"Content-Type": "image/png"})
        self.content = content
        self.url = url

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        return None


class _Client:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.calls: list[tuple[str, str, Mapping[str, str]]] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
    ) -> _Response:
        self.calls.append((method, url, dict(headers)))
        return self.response


class _FailingClient:
    def request(self, *_args: object, **_kwargs: object) -> object:
        message = "outbound response exceeds the configured byte limit"
        raise OutboundResponseTooLargeError(message)


@pytest.fixture
def service_app() -> Flask:
    return Flask(__name__)


@pytest.fixture
def capture_resource_write(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    resources: list[object] = []
    monkeypatch.setattr(
        funcs,
        "db",
        SimpleNamespace(session=SimpleNamespace(add=resources.append)),
    )

    @contextlib.contextmanager
    def fake_unit_of_work() -> Iterator[None]:
        yield

    monkeypatch.setattr(funcs, "unit_of_work", fake_unit_of_work)
    return resources


def _mock_storage(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def upload_to_storage(_app: object, **kwargs: object) -> object:
        calls.append(kwargs)
        return SimpleNamespace(
            bucket="course-assets",
            object_key=str(kwargs["object_key"]),
            url="https://cdn.example/imported.png",
        )

    monkeypatch.setattr(funcs, "upload_to_storage", upload_to_storage)
    return calls


def _assert_error_code(error: AppError, key: str) -> None:
    assert error.code == ERROR_CODE.get(key, ERROR_CODE["server.common.unknownError"])


def test_remote_image_import_preserves_signed_query_without_referer(
    monkeypatch: pytest.MonkeyPatch,
    service_app: Flask,
    capture_resource_write: list[object],
) -> None:
    client = _Client(
        _Response(
            content=b"png-content",
            url="https://images.example/photo.png?signature=secret",
        )
    )
    captured_policies: list[object] = []

    def client_factory(*, policy: object) -> _Client:
        captured_policies.append(policy)
        return client

    monkeypatch.setattr(funcs, "SafeOutboundClient", client_factory)
    storage_calls = _mock_storage(monkeypatch)

    result = funcs.upload_url(
        service_app,
        "teacher-1",
        "https://images.example/photo.png?signature=secret",
    )

    assert result == "https://cdn.example/imported.png"
    assert client.calls[0][1].endswith("?signature=secret")
    assert "Referer" not in client.calls[0][2]
    assert captured_policies[0].trusted_origins == frozenset()
    assert captured_policies[0].max_response_bytes == 10 * 1024 * 1024
    assert storage_calls[0]["file_content"].read() == b"png-content"
    assert len(capture_resource_write) == 1
    resource = capture_resource_write[0]
    assert resource.name == "photo.png"
    assert resource.created_by == "teacher-1"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/private.png",
        "http://[::1]/private.png",
        "http://169.254.169.254/latest/meta-data/iam.png",
    ],
)
def test_remote_image_import_rejects_literal_internal_targets_before_storage(
    monkeypatch: pytest.MonkeyPatch,
    service_app: Flask,
    capture_resource_write: list[object],
    url: str,
) -> None:
    storage_calls = _mock_storage(monkeypatch)

    with pytest.raises(AppError) as error:
        funcs.upload_url(service_app, "teacher-1", url)

    _assert_error_code(error.value, "server.file.fileDownloadFailed")
    assert storage_calls == []
    assert capture_resource_write == []


def test_remote_image_import_revalidates_private_redirect_before_storage(
    monkeypatch: pytest.MonkeyPatch,
    service_app: Flask,
    capture_resource_write: list[object],
) -> None:
    storage_calls = _mock_storage(monkeypatch)

    def resolve(hostname: str, _port: int) -> tuple[str, ...]:
        if hostname == "metadata.internal":
            return ("169.254.169.254",)
        return ("93.184.216.34",)

    def transport(
        _method: str,
        _target: object,
        _address: ipaddress.IPv4Address | ipaddress.IPv6Address,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout: Timeout,
    ) -> HTTPResponse:
        del headers, body, timeout
        return HTTPResponse(
            body=BytesIO(),
            status=302,
            headers={"Location": "http://metadata.internal/latest"},
            preload_content=False,
        )

    def client_factory(*, policy: object) -> SafeOutboundClient:
        return SafeOutboundClient(
            policy=policy,
            resolver=resolve,
            transport=transport,
        )

    monkeypatch.setattr(funcs, "SafeOutboundClient", client_factory)

    with pytest.raises(AppError) as error:
        funcs.upload_url(
            service_app,
            "teacher-1",
            "https://images.example/start.png",
        )

    _assert_error_code(error.value, "server.file.fileDownloadFailed")
    assert storage_calls == []
    assert capture_resource_write == []


def test_remote_image_import_preserves_unsupported_type_error(
    monkeypatch: pytest.MonkeyPatch,
    service_app: Flask,
    capture_resource_write: list[object],
) -> None:
    client = _Client(
        _Response(
            headers={"Content-Type": "text/html"},
            content=b"not-an-image",
        )
    )
    monkeypatch.setattr(funcs, "SafeOutboundClient", lambda **_kwargs: client)
    storage_calls = _mock_storage(monkeypatch)

    with pytest.raises(AppError) as error:
        funcs.upload_url(
            service_app,
            "teacher-1",
            "https://images.example/photo.png",
        )

    _assert_error_code(error.value, "server.file.fileTypeNotSupport")
    assert storage_calls == []
    assert capture_resource_write == []


def test_remote_image_import_rejects_oversized_response_before_storage(
    monkeypatch: pytest.MonkeyPatch,
    service_app: Flask,
    capture_resource_write: list[object],
) -> None:
    monkeypatch.setattr(
        funcs,
        "SafeOutboundClient",
        lambda **_kwargs: _FailingClient(),
    )
    storage_calls = _mock_storage(monkeypatch)

    with pytest.raises(AppError) as error:
        funcs.upload_url(
            service_app,
            "teacher-1",
            "https://images.example/large.png",
        )

    _assert_error_code(error.value, "server.file.fileDownloadFailed")
    assert storage_calls == []
    assert capture_resource_write == []


@pytest.mark.parametrize("status", [301, 404, 500])
def test_remote_image_import_rejects_unsuccessful_final_response(
    monkeypatch: pytest.MonkeyPatch,
    service_app: Flask,
    capture_resource_write: list[object],
    status: int,
) -> None:
    client = _Client(_Response(status=status))
    monkeypatch.setattr(funcs, "SafeOutboundClient", lambda **_kwargs: client)
    storage_calls = _mock_storage(monkeypatch)

    with pytest.raises(AppError) as error:
        funcs.upload_url(
            service_app,
            "teacher-1",
            "https://images.example/photo.png",
        )

    _assert_error_code(error.value, "server.file.fileDownloadFailed")
    assert storage_calls == []
    assert capture_resource_write == []


def test_remote_image_import_does_not_log_sensitive_url_on_download_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    service_app: Flask,
    capture_resource_write: list[object],
) -> None:
    storage_calls = _mock_storage(monkeypatch)
    sensitive_url = "http://127.0.0.1/private.png?token=do-not-log"

    with pytest.raises(AppError) as error:
        funcs.upload_url(service_app, "teacher-1", sensitive_url)

    _assert_error_code(error.value, "server.file.fileDownloadFailed")
    assert "do-not-log" not in caplog.text
    assert sensitive_url not in caplog.text
    assert storage_calls == []
    assert capture_resource_write == []


@pytest.mark.parametrize("body", ["null", '{"url": 123}', '{"url": "  "}'])
def test_url_upload_route_rejects_missing_or_non_string_url(
    monkeypatch: pytest.MonkeyPatch,
    test_client: object,
    body: str,
) -> None:
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: SimpleNamespace(
            user_id="teacher-http",
            language="en-US",
            is_creator=True,
        ),
    )

    response = test_client.post(
        "/api/shifu/url-upfile",
        headers={"Token": "test-token", "Content-Type": "application/json"},
        data=body,
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] != 0
    assert "url is required" in payload["message"]
