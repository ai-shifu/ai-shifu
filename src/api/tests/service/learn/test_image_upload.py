"""Exercise raster validation, input limits and local image transport offline."""

import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Request
from flask.testing import FlaskClient
from flaskr.api.llm import learner_images
from flaskr.common.cache_provider import InMemoryCacheProvider
from flaskr.service.common.models import AppError
from flaskr.service.learn import image_upload
from PIL import Image
from werkzeug.datastructures import FileStorage
from werkzeug.test import EnvironBuilder


def raster(image_format: str = "PNG", size: tuple[int, int] = (8, 8)) -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", size, "red").save(stream, format=image_format)
    return stream.getvalue()


@pytest.mark.parametrize(
    ("image_format", "extension", "mime"),
    [
        ("PNG", "png", "image/png"),
        ("JPEG", "jpg", "image/jpeg"),
        ("WEBP", "webp", "image/webp"),
    ],
)
def test_upload_uses_verified_content_not_filename(
    monkeypatch: pytest.MonkeyPatch, image_format: str, extension: str, mime: str
) -> None:
    stored = {}

    def upload(_app: object, **kwargs: object) -> SimpleNamespace:
        stored.update(kwargs)
        return SimpleNamespace(url="stored-url")

    monkeypatch.setattr(image_upload, "upload_to_storage", upload)
    data = raster(image_format)
    result = image_upload.upload_learner_image(
        None,
        FileStorage(
            stream=io.BytesIO(data), filename="fake.svg", content_type="text/html"
        ),
    )
    assert result == "stored-url"
    assert stored["file_content"] == data
    assert stored["content_type"] == mime
    assert stored["object_key"].startswith("learner-images/")
    assert stored["object_key"].endswith("." + extension)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"<svg></svg>",
        b"not an image",
        b"x" * (5 * 1024 * 1024 + 1),
        raster("GIF"),
        raster(size=(4500, 4500)),
        raster()[:24],
    ],
)
def test_invalid_upload_never_reaches_storage(
    monkeypatch: pytest.MonkeyPatch, data: bytes
) -> None:
    def unexpected(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Invalid content reached storage")

    monkeypatch.setattr(image_upload, "upload_to_storage", unexpected)
    with pytest.raises(AppError):
        image_upload.upload_learner_image(
            None, FileStorage(stream=io.BytesIO(data), filename="photo.png")
        )


def test_attachment_limit_covers_every_input_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        learner_images, "get_config", lambda _: "https://images.example"
    )
    marker = (
        "![learner-image](https://images.example/learner-images/" + "a" * 32 + ".png)"
    )
    image_upload.validate_learner_images({"answer": [marker] * 4})
    with pytest.raises(AppError):
        image_upload.validate_learner_images({"answer": [marker] * 4, "other": marker})
    with pytest.raises(AppError):
        image_upload.validate_learner_images(
            {"answer": ["![learner-image](file:///etc/passwd)"]}
        )
    with pytest.raises(AppError):
        image_upload.validate_learner_images(
            {"answer": marker.replace("images.example", "other.example")}
        )


def test_local_images_are_inlined_without_network_or_mutating_history(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key = "learner-images/" + "a" * 32 + ".png"
    url = "/api/storage/courses/" + key
    older_url = "/api/storage/courses/learner-images/" + "b" * 32 + ".png"
    path = tmp_path / "image.png"
    path.write_bytes(raster())
    monkeypatch.setattr(
        learner_images,
        "get_local_storage_path",
        lambda profile, object_key: (
            path
            if profile == "courses" and object_key == key
            else pytest.fail("Unexpected path")
        ),
    )
    monkeypatch.setattr(
        learner_images,
        "build_local_storage_url",
        lambda profile, object_key: f"/api/storage/{profile}/{object_key}",
    )
    messages = [
        {
            "role": "user",
            "content": learner_images.learner_content(
                f"Earlier question\n![learner-image]({older_url})"
            ),
        },
        {
            "role": "user",
            "content": learner_images.learner_content(
                "What color?\n" + f"![learner-image]({url})\n" * 4
            ),
        },
    ]
    result = learner_images.materialize_local_images(messages)
    assert result[0]["content"] == [
        {"type": "text", "text": "Earlier question"},
        {"type": "text", "text": "[Earlier image attachment omitted]"},
    ]
    assert result[1]["content"][0] == {"type": "text", "text": "What color?"}
    assert len(result[1]["content"][1:]) == 4
    assert all(
        part["image_url"]["url"].startswith("data:image/png;base64,iVBOR")
        for part in result[1]["content"][1:]
    )
    assert messages[0]["content"][1]["image_url"]["url"] == older_url
    assert messages[1]["content"][1]["image_url"]["url"] == url


@pytest.mark.parametrize("failure_mode", ["deleted", "unreadable", "rejected_path"])
def test_unavailable_historical_images_preserve_the_next_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_mode: str
) -> None:
    old_url = "https://old.example/learner-images/" + "a" * 32 + ".png"
    missing_url = "/api/storage/courses/learner-images/" + "b" * 32 + ".png"
    new_url = "https://images.example/learner-images/" + "c" * 32 + ".png"
    monkeypatch.setattr(
        learner_images, "get_config", lambda _: "https://images.example"
    )
    monkeypatch.setattr(
        learner_images,
        "build_local_storage_url",
        lambda profile, key: f"/api/storage/{profile}/{key}",
    )

    def local_path(*_args: object) -> Path:
        if failure_mode == "rejected_path":
            message = "Invalid storage path"
            raise ValueError(message)
        return tmp_path if failure_mode == "unreadable" else tmp_path / "deleted.png"

    monkeypatch.setattr(learner_images, "get_local_storage_path", local_path)
    messages = learner_images.map_learner_messages(
        [
            {
                "role": "user",
                "content": (
                    f"Earlier question\n![learner-image]({old_url})"
                    f"\n![learner-image]({missing_url})"
                ),
            },
            {"role": "assistant", "content": "Earlier reply"},
            {"role": "user", "content": f"New question\n![learner-image]({new_url})"},
        ]
    )
    result = learner_images.materialize_local_images(messages)
    assert result[0]["content"] == [
        {"type": "text", "text": "Earlier question"},
        {"type": "text", "text": "[Image attachment unavailable]"},
        {"type": "text", "text": "[Image attachment unavailable]"},
    ]
    assert result[1:] == messages[1:]


def test_ordinary_markdown_and_assistant_images_are_not_promoted() -> None:
    text = "![example](https://images.example/image.png)"
    assert learner_images.learner_content(text) == text
    marker = (
        "![learner-image](https://images.example/learner-images/" + "a" * 32 + ".png)"
    )
    messages = [
        {"role": "assistant", "content": marker},
        {"role": "user", "content": marker},
    ]
    result = learner_images.map_learner_messages(messages)
    assert result[0] == messages[0]
    assert result[1]["content"][1]["type"] == "image_url"


def test_upload_route_uses_response_envelope_and_rejects_invalid_bytes(
    test_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise multipart transport and business errors through the real learner route."""
    user = SimpleNamespace(
        user_id="image-learner", is_creator=False, is_operator=False, language="en-US"
    )
    monkeypatch.setattr("flaskr.route.user.validate_user", lambda *_: user)
    stored = []

    def upload(_app: object, **kwargs: object) -> SimpleNamespace:
        stored.append(kwargs)
        return SimpleNamespace(
            url="/api/storage/courses/learner-images/" + "a" * 32 + ".png"
        )

    monkeypatch.setattr(image_upload, "upload_to_storage", upload)
    response = test_client.post(
        "/api/learn/images",
        headers={"Token": "test-token"},
        data={"file": (io.BytesIO(raster()), "photo.png")},
    ).get_json()
    assert response["code"] == 0
    assert response["data"].endswith(".png")
    assert len(stored) == 1
    invalid = test_client.post(
        "/api/learn/images",
        headers={"Token": "test-token"},
        data={"file": (io.BytesIO(b"<svg></svg>"), "photo.png")},
    ).get_json()
    assert invalid["code"] != 0
    assert len(stored) == 1


def test_upload_route_caps_attempts_per_learner_before_storage(
    test_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Apply the upload budget per authenticated learner and hour."""
    user = SimpleNamespace(
        user_id="quota-learner", is_creator=False, is_operator=False, language="en-US"
    )
    monkeypatch.setattr("flaskr.route.user.validate_user", lambda *_: user)
    monkeypatch.setattr(image_upload, "get_redis_client", lambda: None)
    monkeypatch.setattr(image_upload, "cache", InMemoryCacheProvider())
    monkeypatch.setattr(image_upload, "UPLOADS_PER_HOUR", 2)
    clock = SimpleNamespace(time=lambda: 3600)
    monkeypatch.setattr(image_upload, "time", clock)
    stored = []

    def store(_app: object, **kwargs: object) -> SimpleNamespace:
        stored.append(kwargs)
        return SimpleNamespace(url="stored-image")

    monkeypatch.setattr(image_upload, "upload_to_storage", store)

    def upload() -> dict:
        return test_client.post(
            "/api/learn/images",
            headers={"Token": "test-token"},
            data={"file": (io.BytesIO(raster()), "photo.png")},
        ).get_json()

    assert upload()["code"] == 0
    assert upload()["code"] == 0
    refused = upload()
    assert refused["code"] != 0
    assert "Image upload limit reached" in refused["message"]
    assert len(stored) == 2

    user.user_id = "another-learner"
    assert upload()["code"] == 0
    user.user_id = "quota-learner"
    clock.time = lambda: 7200
    assert upload()["code"] == 0
    assert len(stored) == 4


def test_oversized_multipart_is_rejected_before_authentication(
    test_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shared route policy checks size before any middleware parses the upload."""
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda *_: pytest.fail("Oversized multipart reached authentication"),
    )
    body = io.BytesIO()
    environment = EnvironBuilder(
        path="/api/learn/images",
        method="POST",
        content_type="multipart/form-data; boundary=test",
        headers={"Token": "test-token"},
    ).get_environ()
    environment["wsgi.input"] = body
    environment["CONTENT_LENGTH"] = str(learner_images.MAX_IMAGE_BYTES + 64 * 1024 + 1)
    response = test_client.open(Request(environment))
    assert response.get_json()["code"] == 413
    assert response.headers["Cache-Control"] == "no-store"
    assert body.tell() == 0


def test_runtime_config_uses_the_same_trusted_learner_storage_locations(
    test_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Expose only the public image path prefixes used by submission validation."""
    monkeypatch.setattr(
        learner_images, "get_config", lambda _: "https://images.example/courses/"
    )
    response = test_client.get("/api/runtime-config")
    payload = response.get_json()["data"]
    prefixes = payload["learnerImageStoragePrefixes"]
    assert prefixes == [
        "/api/storage/courses/learner-images/",
        "https://images.example/courses/learner-images/",
    ]
    for prefix in prefixes:
        assert learner_images.is_stored_learner_image(prefix + "a" * 32 + ".png")
