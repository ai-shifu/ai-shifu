"""Verify resource persistence and provider failures without external requests."""

import json
import uuid
from collections.abc import Iterator
from contextlib import nullcontext
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from flaskr.dao import db
from flaskr.i18n import _
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.resource.models import Resource
from flaskr.service.shifu import funcs
from flaskr.service.shifu.models import AiCourseAuth, FavoriteScenario
from werkzeug.datastructures import FileStorage


@pytest.fixture
def resource_owner(app: object) -> Iterator[str]:
    owner = uuid.uuid4().hex
    yield owner
    with app.app_context():
        Resource.query.filter_by(created_by=owner).delete()
        AiCourseAuth.query.filter_by(user_id=owner).delete()
        FavoriteScenario.query.filter_by(user_id=owner).delete()
        db.session.commit()


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> Mock:
    def upload(_app: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            bucket="course-bucket",
            object_key=kwargs["object_key"],
            url="https://storage.example/resource",
        )

    handler = Mock(side_effect=upload)
    monkeypatch.setattr(funcs, "upload_to_storage", handler)
    return handler


def _outbound_response(monkeypatch: pytest.MonkeyPatch, **overrides: object) -> Mock:
    response = SimpleNamespace(
        **{
            "status": 200,
            "url": "https://images.example/image.png",
            "headers": {"Content-Type": "image/png"},
            "content": b"image-bytes",
            **overrides,
        }
    )
    client = Mock()
    client.request.return_value = nullcontext(response)
    monkeypatch.setattr(funcs, "SafeOutboundClient", Mock(return_value=client))
    return client.request


def test_upload_creates_resource_then_updates_metadata_without_changing_creator(
    app: object,
    resource_owner: str,
    storage: Mock,
) -> None:
    first_file = FileStorage(stream=BytesIO(b"image"), filename="first.png")
    assert (
        funcs.upload_file(app, resource_owner, "", first_file)
        == "https://storage.example/resource"
    )
    with app.app_context():
        row = Resource.query.filter_by(created_by=resource_owner).one()
        resource_id = row.resource_id
        assert len(resource_id) == 32
        assert row.name == "first.png"
        assert row.oss_bucket == "course-bucket"
    updater = uuid.uuid4().hex
    second_file = FileStorage(stream=BytesIO(b"updated"), filename="replacement.jpg")
    funcs.upload_file(app, updater, resource_id, second_file)
    with app.app_context():
        row = Resource.query.filter_by(resource_id=resource_id).one()
        assert row.name == "replacement.jpg"
        assert row.created_by == resource_owner
        assert row.updated_by == updater
        assert row.oss_name == resource_id
        assert Resource.query.filter_by(resource_id=resource_id).count() == 1
    assert storage.call_count == 2
    assert storage.call_args.kwargs["object_key"] == resource_id


@pytest.mark.parametrize(
    ("url", "content_type", "filename"),
    [
        (
            "https://images.example/cover?token=example#fragment",
            "image/png",
            "cover.png",
        ),
        ("https://images.example/cover", "image/webp", "cover.jpg"),
        ("https://images.example/photo.jpeg", "image/jpeg", "photo.jpeg"),
    ],
)
def test_remote_image_upload_persists_normalized_file_metadata(
    app: object,
    resource_owner: str,
    storage: Mock,
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    content_type: str,
    filename: str,
) -> None:
    request = _outbound_response(
        monkeypatch, headers={"Content-Type": content_type}, url=url
    )
    assert (
        funcs.upload_url(app, resource_owner, url) == "https://storage.example/resource"
    )
    assert request.call_args.args == ("GET", url)
    assert "Referer" not in request.call_args.kwargs["headers"]
    assert storage.call_args.kwargs["file_content"].getvalue() == b"image-bytes"
    with app.app_context():
        row = Resource.query.filter_by(created_by=resource_owner).one()
        assert row.name == filename
        assert row.created_by == row.updated_by == resource_owner


@pytest.mark.parametrize("url", ["", "  "])
def test_remote_image_upload_rejects_invalid_urls_before_network_access(
    app: object,
    resource_owner: str,
    monkeypatch: pytest.MonkeyPatch,
    storage: Mock,
    url: str,
) -> None:
    request = Mock()
    monkeypatch.setattr(funcs, "SafeOutboundClient", request)
    with pytest.raises(AppError):
        funcs.upload_url(app, resource_owner, url)
    request.assert_not_called()
    storage.assert_not_called()


def test_remote_image_upload_keeps_content_type_rejection_distinct_from_storage_failure(
    app: object,
    resource_owner: str,
    monkeypatch: pytest.MonkeyPatch,
    storage: Mock,
) -> None:
    _outbound_response(
        monkeypatch, headers={"Content-Type": "text/html"}, content=b"html"
    )
    with pytest.raises(AppError) as error:
        funcs.upload_url(app, resource_owner, "https://images.example/page")
    assert error.value.code == ERROR_CODE["server.file.fileTypeNotSupport"]
    storage.assert_not_called()


@pytest.mark.parametrize(
    "failure",
    [
        OSError("timeout"),
        RuntimeError("storage failed"),
        funcs.OutboundRedirectError("too many redirects"),
        funcs.OutboundResponseTooLargeError("too large"),
        funcs.UnsafeOutboundUrlError("private target"),
    ],
)
def test_image_transfer_failures_do_not_persist_a_resource(
    app: object,
    resource_owner: str,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    request = _outbound_response(monkeypatch)
    upload = Mock(side_effect=failure)
    if not isinstance(failure, RuntimeError):
        request.side_effect = failure
    monkeypatch.setattr(funcs, "upload_to_storage", upload)
    with pytest.raises(AppError):
        funcs.upload_url(app, resource_owner, "https://images.example/image.png")
    with app.app_context():
        assert Resource.query.filter_by(created_by=resource_owner).count() == 0


@pytest.mark.parametrize("host", ["bilibili.com", "www.bilibili.com"])
def test_video_lookup_uses_supported_domain_and_maps_provider_metadata(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    host: str,
) -> None:
    response = Mock(status_code=200)
    response.json.return_value = {
        "code": 0,
        "data": {
            "title": "Lesson",
            "pic": "cover",
            "owner": {"name": "Teacher"},
            "duration": 60,
        },
    }
    request = Mock(return_value=response)
    monkeypatch.setattr(funcs.requests, "get", request)
    assert funcs.get_video_info(app, "user", f"https://{host}/video/BV12345?p=2") == {
        "success": True,
        "title": "Lesson",
        "cover": "cover",
        "bvid": "BV12345",
        "author": "Teacher",
        "duration": 60,
    }
    assert (
        request.call_args.args[0]
        == "https://api.bilibili.com/x/web-interface/view?bvid=BV12345"
    )
    assert request.call_args.kwargs["timeout"] == 10


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
    ("failure", "error_name", "expected_code"),
    [
        # Network/parse errors currently retain the manifest's generic code.
        (requests.Timeout("timeout"), "server.file.videoNetworkError", 9999),
        (KeyError("data"), "server.file.videoParseError", 9999),
        (ValueError("invalid json"), "server.file.videoGetInfoError", 6008),
    ],
)
def test_video_lookup_maps_network_parse_and_unexpected_failures_to_application_errors(
    app: object,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    error_name: str,
    expected_code: int,
) -> None:
    monkeypatch.setattr(funcs.requests, "get", Mock(side_effect=failure))
    with pytest.raises(AppError) as error:
        funcs.get_video_info(app, "user", "https://www.bilibili.com/video/BV12345")
    assert error.value.code == expected_code
    assert error.value.message == _(error_name)


@pytest.mark.parametrize(
    ("stored_auth", "permission", "expected"),
    [
        ('"publish"', "publish", True),
        ('["4"]', "publish", True),
        ('["edit"]', "view", True),
        ("{broken", "edit", False),
    ],
)
def test_permission_lookup_recovers_from_corrupt_cache_and_normalizes_legacy_grants(
    app: object,
    resource_owner: str,
    monkeypatch: pytest.MonkeyPatch,
    stored_auth: str,
    permission: str,
    expected: bool,
) -> None:
    bid = uuid.uuid4().hex
    with app.app_context():
        db.session.add(
            AiCourseAuth(
                course_id=bid, user_id=resource_owner, status=1, auth_type=stored_auth
            )
        )
        db.session.commit()
    cache = Mock()
    cache.get.return_value = b"{broken-cache"
    monkeypatch.setattr(funcs, "redis", cache)
    monkeypatch.setattr(funcs, "get_shifu_creator_bid", lambda _app, _bid: "other")
    assert (
        funcs.shifu_permission_verification(app, resource_owner, bid, permission)
        is expected
    )
    cache.delete.assert_called_once_with(cache.get.call_args.args[0])
    if expected:
        assert permission in json.loads(cache.set.call_args.args[1])


def test_unmarking_missing_favorite_does_not_create_a_row(app: object) -> None:
    assert funcs.unmark_favorite_shifu(app, uuid.uuid4().hex, uuid.uuid4().hex) is False


def test_favorite_lifecycle_reuses_one_row_and_is_scoped_to_course(
    app: object, resource_owner: str
) -> None:
    bid = uuid.uuid4().hex
    other_bid = uuid.uuid4().hex
    assert funcs.mark_or_unmark_favorite_shifu(
        app, resource_owner, bid, is_favorite=True
    )
    assert funcs.mark_favorite_shifu(app, resource_owner, other_bid)
    assert funcs.mark_or_unmark_favorite_shifu(
        app, resource_owner, bid, is_favorite=False
    )
    with app.app_context():
        row = FavoriteScenario.query.filter_by(
            user_id=resource_owner, scenario_id=bid
        ).one()
        first_id = row.id
        assert row.status == 0
        assert (
            FavoriteScenario.query.filter_by(
                user_id=resource_owner, scenario_id=other_bid
            )
            .one()
            .status
            == 1
        )
    assert funcs.mark_favorite_shifu(app, resource_owner, bid)
    with app.app_context():
        row = FavoriteScenario.query.filter_by(
            user_id=resource_owner, scenario_id=bid
        ).one()
        assert row.id == first_id
        assert row.status == 1


def test_upload_with_unknown_resource_id_persists_requested_identity(
    app: object, resource_owner: str, storage: Mock
) -> None:
    resource_id = uuid.uuid4().hex
    file = FileStorage(stream=BytesIO(b"image"), filename="new.png")
    funcs.upload_file(app, resource_owner, resource_id, file)
    with app.app_context():
        row = Resource.query.filter_by(resource_id=resource_id).one()
        assert row.created_by == resource_owner
        assert row.name == "new.png"
    assert storage.call_args.kwargs["object_key"] == resource_id
