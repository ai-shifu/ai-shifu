"""Verify resource persistence and provider failures without external requests."""

from unittest.mock import Mock

import pytest
import requests
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.shifu import funcs


@pytest.mark.parametrize(
    ("url", "status", "payload", "error_name"),
    [
        (
            "https://bilibili.com/not-a-video",
            200,
            {},
            "server.file.videoInvalidBilibiliLink",
        ),
        (
            "https://bilibili.com.evil.example/video/BV12345",
            200,
            {},
            "server.file.videoUnsupportedVideoSite",
        ),
        (
            "https://bilibili.com/video/BV12345",
            200,
            {"code": 1},
            "server.file.videoBilibiliApiError",
        ),
        (
            "https://bilibili.com/video/BV12345",
            503,
            {},
            "server.file.videoBilibiliApiRequestFailed",
        ),
    ],
)
def test_video_lookup_preserves_actionable_provider_error_codes(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    status: int,
    payload: dict,
    error_name: str,
) -> None:
    response = Mock(status_code=status)
    response.json.return_value = payload
    monkeypatch.setattr(funcs.requests, "get", Mock(return_value=response))
    with pytest.raises(AppError) as error:
        funcs.get_video_info(app, "user", url)
    assert error.value.code == ERROR_CODE[error_name]


@pytest.mark.parametrize(
    "failure",
    [requests.Timeout("timeout"), KeyError("data"), ValueError("invalid json")],
)
def test_video_lookup_maps_network_parse_and_unexpected_failures_to_application_errors(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    monkeypatch.setattr(funcs.requests, "get", Mock(side_effect=failure))
    with pytest.raises(AppError):
        funcs.get_video_info(app, "user", "https://www.bilibili.com/video/BV12345")
