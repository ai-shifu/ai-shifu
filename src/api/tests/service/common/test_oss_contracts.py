"""Verify OSS profile isolation and bounded, best-effort CDN warming."""

import json
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from flask import Flask
from flaskr.service.common import oss_utils as oss
from flaskr.service.common.models import AppError


@pytest.fixture
def config() -> oss.OSSConfig:
    return oss.OSSConfig(
        "oss-cn-test.aliyuncs.com",
        "test-id",
        "test-secret",
        "https://cdn.invalid/",
        "assets",
    )


@pytest.mark.parametrize("profile", ["default", "courses"])
def test_profile_selects_its_own_credentials_and_storage_location(
    monkeypatch: pytest.MonkeyPatch, profile: str
) -> None:
    prefix = "ALIBABA_CLOUD_OSS_" + ("COURSES_" if profile == "courses" else "")
    values = {
        prefix + "ENDPOINT": "endpoint",
        prefix + "ACCESS_KEY_ID": "id",
        prefix + "ACCESS_KEY_SECRET": "secret",
        prefix + "BUCKET": "bucket",
        prefix + ("URL" if profile == "courses" else "BASE_URL"): "url",
    }
    monkeypatch.setattr(oss, "get_config", values.get)
    assert oss.get_oss_config(" " + profile.upper() + " ") == oss.OSSConfig(
        "endpoint", "id", "secret", "url", "bucket"
    )
    assert oss.is_oss_profile_configured(profile)
    assert not oss.is_oss_profile_configured(
        "courses" if profile == "default" else "default"
    )


@pytest.mark.parametrize("missing", ["ACCESS_KEY_ID", "ACCESS_KEY_SECRET", "BUCKET"])
def test_profile_configuration_requires_credentials_and_bucket(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    values = {
        "ALIBABA_CLOUD_OSS_ACCESS_KEY_ID": "id",
        "ALIBABA_CLOUD_OSS_ACCESS_KEY_SECRET": "secret",
        "ALIBABA_CLOUD_OSS_BUCKET": "bucket",
    }
    values["ALIBABA_CLOUD_OSS_" + missing] = " "
    monkeypatch.setattr(oss, "get_config", values.get)
    assert not oss.is_oss_profile_configured("")


@pytest.mark.parametrize("missing", ["ACCESS_KEY_ID", "ACCESS_KEY_SECRET"])
def test_missing_credentials_raise_before_bucket_creation(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    values = {
        "ALIBABA_CLOUD_OSS_ACCESS_KEY_ID": "id",
        "ALIBABA_CLOUD_OSS_ACCESS_KEY_SECRET": "secret",
    }
    values.pop("ALIBABA_CLOUD_OSS_" + missing)
    monkeypatch.setattr(oss, "get_config", values.get)
    with pytest.raises(AppError):
        oss.get_oss_config()


def test_unknown_profile_cannot_fall_back_to_another_bucket() -> None:
    assert not oss.is_oss_profile_configured("unknown")
    with pytest.raises(ValueError, match="Unknown OSS profile"):
        oss.get_oss_config("unknown")


def test_bucket_receives_exact_profile_credentials(
    monkeypatch: pytest.MonkeyPatch, config: oss.OSSConfig
) -> None:
    auth = Mock(return_value=object())
    bucket = Mock(return_value=object())
    monkeypatch.setattr(oss.oss2, "Auth", auth)
    monkeypatch.setattr(oss.oss2, "Bucket", bucket)
    assert oss.create_oss_bucket(config) is bucket.return_value
    auth.assert_called_once_with("test-id", "test-secret")
    bucket.assert_called_once_with(
        auth.return_value, "oss-cn-test.aliyuncs.com", "assets"
    )


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("photo.JPG", "image/jpeg"),
        ("photo.jpeg", "image/jpeg"),
        ("photo.png", "image/png"),
        ("photo.GIF", "image/gif"),
    ],
)
def test_supported_image_extensions_map_to_content_types(
    filename: str, expected: str
) -> None:
    assert oss.get_image_content_type(filename) == expected


def test_unsupported_image_type_is_rejected() -> None:
    with pytest.raises(AppError):
        oss.get_image_content_type("image.exe")


@pytest.fixture
def cdn(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    import aliyunsdkcore.client as sdk

    client = Mock()
    factory = Mock(return_value=client)
    head = Mock(return_value=SimpleNamespace(status_code=200))
    sleep = Mock()
    monkeypatch.setattr(sdk, "AcsClient", factory)
    monkeypatch.setattr(oss.requests, "head", head)
    monkeypatch.setattr(oss, "time", SimpleNamespace(sleep=sleep))
    return SimpleNamespace(client=client, factory=factory, head=head, sleep=sleep)


def _task(status: str) -> str:
    return json.dumps(
        {"Tasks": {"CDNTask": [{"Status": status, "Description": "task outcome"}]}}
    )


def test_cdn_polling_waits_for_completion_then_verifies_public_url(
    cdn: SimpleNamespace, config: oss.OSSConfig
) -> None:
    cdn.client.do_action_with_exception.side_effect = [
        json.dumps({"PushTaskId": "task-id"}),
        _task("Processing"),
        _task("Complete"),
    ]
    cdn.head.side_effect = [
        OSError("temporarily offline"),
        SimpleNamespace(status_code=503),
        SimpleNamespace(status_code=200),
    ]
    assert oss.warm_up_cdn(Flask(__name__), "https://cdn.invalid/image.png", config)
    cdn.factory.assert_called_once_with("test-id", "test-secret", region_id="cn-test")
    requests = [
        entry.args[0] for entry in cdn.client.do_action_with_exception.call_args_list
    ]
    assert requests[0].get_ObjectPath() == "https://cdn.invalid/image.png\n"
    assert [request.TaskId for request in requests[1:]] == ["task-id", "task-id"]
    assert cdn.sleep.call_args_list == [call(1), call(2), call(2)]
    assert (
        cdn.head.call_args_list
        == [call("https://cdn.invalid/image.png", timeout=5)] * 3
    )


@pytest.mark.parametrize("status", ["Failed", "Processing", "missing"])
def test_cdn_failure_or_timeout_is_bounded_without_url_probe(
    cdn: SimpleNamespace, config: oss.OSSConfig, status: str
) -> None:
    response = "{}" if status == "missing" else _task(status)
    cdn.client.do_action_with_exception.side_effect = ["{}"] + [response] * 10
    assert not oss.warm_up_cdn(Flask(__name__), "https://cdn.invalid/image.png", config)
    expected_polls = 1 if status == "Failed" else 10
    assert cdn.client.do_action_with_exception.call_count == 1 + expected_polls
    assert cdn.sleep.call_count == expected_polls - 1
    cdn.head.assert_not_called()


def test_completed_cdn_task_with_unavailable_url_stops_after_ten_probes(
    cdn: SimpleNamespace, config: oss.OSSConfig
) -> None:
    cdn.client.do_action_with_exception.side_effect = ["{}", _task("Complete")]
    cdn.head.return_value.status_code = 404
    assert not oss.warm_up_cdn(Flask(__name__), "https://cdn.invalid/image.png", config)
    assert cdn.head.call_count == 10
    assert cdn.sleep.call_args_list == [call(2)] * 9


@pytest.mark.parametrize("stage", ["construct", "request", "invalid_json"])
def test_cdn_sdk_failures_are_best_effort(
    cdn: SimpleNamespace, config: oss.OSSConfig, stage: str
) -> None:
    if stage == "construct":
        cdn.factory.side_effect = RuntimeError("SDK unavailable")
    elif stage == "request":
        cdn.client.do_action_with_exception.side_effect = RuntimeError(
            "API unavailable"
        )
    else:
        cdn.client.do_action_with_exception.return_value = "invalid JSON"
    assert not oss.warm_up_cdn(Flask(__name__), "https://cdn.invalid/image.png", config)
    cdn.head.assert_not_called()
    cdn.sleep.assert_not_called()


@pytest.mark.parametrize("warm_up", [True, False])
def test_upload_succeeds_even_if_optional_cdn_warming_fails(
    monkeypatch: pytest.MonkeyPatch, config: oss.OSSConfig, warm_up: bool
) -> None:
    bucket = Mock()
    warm = Mock(return_value=False)
    monkeypatch.setattr(oss, "warm_up_cdn", warm)
    monkeypatch.setattr(
        oss, "get_oss_config", lambda profile: config if profile == "courses" else None
    )
    monkeypatch.setattr(oss, "create_oss_bucket", lambda _: bucket)
    app = Flask(__name__)
    result = oss.upload_to_oss(
        app,
        file_content=b"audio",
        file_id="clips/audio.mp3",
        content_type="audio/mpeg",
        profile="courses",
        warm_up=warm_up,
    )
    assert result == ("https://cdn.invalid/clips/audio.mp3", "assets")
    bucket.put_object.assert_called_once_with(
        "clips/audio.mp3", b"audio", headers={"Content-Type": "audio/mpeg"}
    )
    assert warm.call_count == int(warm_up)
    if warm_up:
        warm.assert_called_once_with(app, result[0], config)


def test_failed_upload_does_not_start_cdn_warming(
    monkeypatch: pytest.MonkeyPatch, config: oss.OSSConfig
) -> None:
    bucket = Mock()
    bucket.put_object.side_effect = OSError("upload failed")
    warm = Mock()
    monkeypatch.setattr(oss, "warm_up_cdn", warm)
    with pytest.raises(OSError, match="upload failed"):
        oss.upload_to_oss(
            Flask(__name__),
            file_content=b"audio",
            file_id="clip",
            content_type="audio/mpeg",
            config=config,
            bucket=bucket,
        )
    warm.assert_not_called()
