"""Prevent local uploads from becoming active same-origin documents."""

from io import BytesIO

import flaskr.common.config as common_config
import pytest
from flask import Flask
from flaskr.route.storage import register_storage_handler
from flaskr.service.common.storage import upload_to_storage
from flaskr.service.shifu import funcs
from flaskr.service.shifu.utils import get_shifu_res_url, parse_shifu_res_bid
from PIL import Image
from werkzeug.datastructures import FileStorage


@pytest.fixture
def storage_app(monkeypatch: object, tmp_path: object) -> Flask:
    """Build a local storage app without external services."""
    monkeypatch.setenv("PATH_PREFIX", "/api")
    monkeypatch.setenv("STORAGE_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_STORAGE_ROOT", str(tmp_path))
    for key in ("PATH_PREFIX", "STORAGE_PROVIDER", "LOCAL_STORAGE_ROOT"):
        common_config.__ENHANCED_CONFIG__._cache.pop(key, None)
    app = Flask(__name__)
    register_storage_handler(app, "/api")
    return app


def _assert_sandboxed(response: object) -> None:
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    policy = response.headers["Content-Security-Policy"]
    directives = {part.strip() for part in policy.split(";")}
    assert "sandbox" in directives
    assert "default-src 'none'" in directives
    assert "allow-scripts" not in policy
    assert "allow-same-origin" not in policy


@pytest.mark.parametrize("profile", ["default", "courses"])
@pytest.mark.parametrize(
    "payload",
    [
        b"<!doctype html><script>window.storageExecuted = true</script>",
        b'<svg xmlns="http://www.w3.org/2000/svg" onload="window.storageExecuted=true"/>',
    ],
)
@pytest.mark.parametrize(
    "object_key",
    [
        "document.html",
        "document.HTM",
        "document.xhtml",
        "document.svg",
        "document.svgz",
        "document.xml",
        "document.js",
        "document.css",
        "document.pdf",
        "document.png",
        "document.mp3",
        "document.bin",
        "document",
        "nested/document.html",
    ],
)
def test_historical_active_content_downloads_without_execution(
    storage_app: Flask, tmp_path: object, profile: str, object_key: str, payload: bytes
) -> None:
    path = tmp_path / profile / object_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)

    response = storage_app.test_client().get(f"/api/storage/{profile}/{object_key}")

    assert response.status_code == 200
    assert response.data == payload
    assert response.mimetype == "application/octet-stream"
    assert response.headers["Content-Disposition"].startswith("attachment;")
    _assert_sandboxed(response)


def test_active_content_stays_sandboxed_for_partial_and_cached_requests(
    storage_app: Flask, tmp_path: object
) -> None:
    payload = b"<!doctype html><script>window.storageExecuted = true</script>"
    path = tmp_path / "courses" / "historical.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    url = "/api/storage/courses/historical.html"
    client = storage_app.test_client()
    response = client.get(url)

    for method, headers, status in (
        ("HEAD", {}, 200),
        ("GET", {"Range": "bytes=0-2"}, 206),
        ("GET", {"If-None-Match": response.headers["ETag"]}, 304),
    ):
        result = client.open(url, method=method, headers=headers)
        assert result.status_code == status
        assert result.headers["Content-Disposition"].startswith("attachment;")
        _assert_sandboxed(result)


def test_storage_rejects_paths_outside_its_root(
    storage_app: Flask, tmp_path: object
) -> None:
    (tmp_path / "outside.html").write_bytes(b"outside")
    response = storage_app.test_client().get("/api/storage/courses/../outside.html")
    assert response.status_code == 400
    assert response.data != b"outside"


@pytest.mark.parametrize(
    ("image_format", "mimetype"),
    [
        ("JPEG", "image/jpeg"),
        ("PNG", "image/png"),
        ("GIF", "image/gif"),
        ("WEBP", "image/webp"),
        ("ICO", "image/x-icon"),
    ],
)
@pytest.mark.parametrize("object_key", ["opaque-resource-id", "misleading.html"])
def test_raster_images_remain_inline_based_on_content(
    storage_app: Flask, image_format: str, mimetype: str, object_key: str
) -> None:
    image = Image.new("RGB", (16, 16), color="blue")
    stream = BytesIO()
    image.save(stream, format=image_format)
    payload = stream.getvalue()
    result = upload_to_storage(
        storage_app,
        file_content=payload,
        object_key=object_key,
        content_type=mimetype,
        profile="courses",
    )

    response = storage_app.test_client().get(result.url)

    assert response.status_code == 200
    assert response.data == payload
    assert response.mimetype == mimetype
    assert response.headers["Content-Disposition"].startswith("inline;")
    _assert_sandboxed(response)


@pytest.mark.parametrize("payload", [b"ID3" + b"\x00" * 32, b"\xff\xfb" + b"\x00" * 32])
def test_audio_keeps_range_head_and_cache_revalidation(
    storage_app: Flask, payload: bytes
) -> None:
    result = upload_to_storage(
        storage_app,
        file_content=payload,
        object_key="tts-audio/example.mp3",
        content_type="audio/mpeg",
    )
    client = storage_app.test_client()
    response = client.get(result.url)
    assert response.status_code == 200
    assert response.data == payload
    assert response.mimetype == "audio/mpeg"
    assert response.headers["Content-Disposition"].startswith("inline;")
    _assert_sandboxed(response)

    partial = client.get(result.url, headers={"Range": "bytes=0-2"})
    assert partial.status_code == 206
    assert partial.data == payload[:3]
    assert partial.headers["Content-Range"] == f"bytes 0-2/{len(payload)}"
    assert partial.mimetype == "audio/mpeg"
    _assert_sandboxed(partial)

    head = client.head(result.url)
    assert head.status_code == 200
    assert not head.data
    assert head.headers["Content-Length"] == str(len(payload))
    _assert_sandboxed(head)

    cached = client.get(result.url, headers={"If-None-Match": response.headers["ETag"]})
    assert cached.status_code == 304
    assert not cached.data
    _assert_sandboxed(cached)


@pytest.mark.parametrize("payload", [b"RIFF1234WAVEdata", b"\x00\x00\x02\x00icon"])
def test_similar_signatures_do_not_grant_inline_media(
    storage_app: Flask, payload: bytes
) -> None:
    result = upload_to_storage(
        storage_app,
        file_content=payload,
        object_key="document.webp",
        content_type="image/webp",
    )
    response = storage_app.test_client().get(result.url)
    assert response.mimetype == "application/octet-stream"
    assert response.headers["Content-Disposition"].startswith("attachment;")
    _assert_sandboxed(response)


def test_course_upload_cannot_promote_image_filename_to_html_document(
    app: Flask, storage_app: Flask
) -> None:
    payload = b"<!doctype html><script>window.storageExecuted = true</script>"
    file = FileStorage(stream=BytesIO(payload), filename="cover.png")

    url = funcs.upload_file(app, "storage-test-user", "storage-document.html", file)
    response = storage_app.test_client().get(url)

    assert response.status_code == 200
    assert response.data == payload
    assert response.mimetype == "application/octet-stream"
    assert response.headers["Content-Disposition"].startswith("attachment;")
    _assert_sandboxed(response)


def test_course_image_replacement_preserves_cover_resource_round_trip(
    app: Flask, storage_app: Flask
) -> None:
    resource_id = "storage-cover-resource"
    for color in ("blue", "red"):
        stream = BytesIO()
        Image.new("RGB", (2, 2), color=color).save(stream, format="PNG")
        payload = stream.getvalue()
        file = FileStorage(stream=BytesIO(payload), filename="cover.png")

        url = funcs.upload_file(app, "storage-test-user", resource_id, file)

        assert parse_shifu_res_bid(url) == resource_id
        with app.app_context():
            assert get_shifu_res_url(resource_id) == url
        response = storage_app.test_client().get(url)
        assert response.status_code == 200
        assert response.data == payload
        assert response.mimetype == "image/png"
        assert response.headers["Content-Disposition"].startswith("inline;")
        _assert_sandboxed(response)
