import flaskr.common.config as common_config
from flask import Flask

from flaskr.route.storage import register_storage_handler
from flaskr.service.common.oss_utils import OSS_PROFILE_COURSES, OSS_PROFILE_DEFAULT
from flaskr.service.common.storage import STORAGE_PROVIDER_LOCAL, upload_to_storage
from flaskr.service.tts.tts_handler import upload_audio_to_oss


def _reset_config_cache(*keys: str) -> None:
    for key in keys:
        common_config.__ENHANCED_CONFIG__._cache.pop(key, None)  # noqa: SLF001


def _make_storage_app(monkeypatch, tmp_path, provider: str) -> Flask:
    monkeypatch.setenv("PATH_PREFIX", "/api")
    monkeypatch.setenv("STORAGE_PROVIDER", provider)
    monkeypatch.setenv("LOCAL_STORAGE_ROOT", str(tmp_path))
    _reset_config_cache("PATH_PREFIX", "STORAGE_PROVIDER", "LOCAL_STORAGE_ROOT")

    app = Flask(__name__)
    register_storage_handler(app, "/api")
    return app


def test_upload_to_storage_auto_falls_back_to_local(monkeypatch, tmp_path):
    app = _make_storage_app(monkeypatch, tmp_path, "auto")

    result = upload_to_storage(
        app,
        file_content=b"hello",
        object_key="example",
        content_type="text/plain",
        profile=OSS_PROFILE_DEFAULT,
    )

    assert result.provider == STORAGE_PROVIDER_LOCAL
    assert result.url == "/api/storage/default/example"
    assert (tmp_path / "default" / "example").read_bytes() == b"hello"


def test_storage_route_serves_nested_object_key(monkeypatch, tmp_path):
    app = _make_storage_app(monkeypatch, tmp_path, "local")
    client = app.test_client()

    mp3_bytes = b"ID3" + b"\x00" * 16
    result = upload_to_storage(
        app,
        file_content=mp3_bytes,
        object_key="tts-audio/test.mp3",
        content_type="audio/mpeg",
        profile=OSS_PROFILE_COURSES,
    )

    response = client.get(result.url)
    assert response.status_code == 200
    assert response.data == mp3_bytes
    assert response.headers["Content-Type"].startswith("audio/mpeg")


def test_storage_route_guesses_mimetype_by_magic(monkeypatch, tmp_path):
    app = _make_storage_app(monkeypatch, tmp_path, "local")
    client = app.test_client()

    jpeg_bytes = b"\xff\xd8\xff" + b"\x00" * 16
    result = upload_to_storage(
        app,
        file_content=jpeg_bytes,
        object_key="image-without-extension",
        content_type="image/jpeg",
        profile=OSS_PROFILE_COURSES,
    )

    response = client.get(result.url)
    assert response.status_code == 200
    assert response.data == jpeg_bytes
    assert response.headers["Content-Type"].startswith("image/jpeg")


def test_upload_audio_to_oss_uses_storage_layer(monkeypatch, tmp_path):
    app = _make_storage_app(monkeypatch, tmp_path, "auto")

    audio_bytes = b"ID3" + b"\x00" * 8
    url, bucket = upload_audio_to_oss(app, audio_bytes, "abc123")

    assert bucket == ""
    assert url == "/api/storage/courses/tts-audio/abc123.mp3"
    assert (
        tmp_path / "courses" / "tts-audio" / "abc123.mp3"
    ).read_bytes() == audio_bytes
