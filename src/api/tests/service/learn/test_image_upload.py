"""Exercise raster validation, input limits and local image transport offline."""

import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask.testing import FlaskClient
from flaskr.api.llm import learner_images
from flaskr.service.common.models import AppError
from flaskr.service.learn import image_upload
from PIL import Image
from werkzeug.datastructures import FileStorage


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
    monkeypatch.setattr(learner_images, "build_local_storage_url", lambda *_: url)
    messages = [
        {
            "role": "user",
            "content": learner_images.learner_content(
                f"What color?\n![learner-image]({url})"
            ),
        }
    ]
    result = learner_images.materialize_local_images(messages)
    assert result[0]["content"][0] == {"type": "text", "text": "What color?"}
    assert result[0]["content"][1]["image_url"]["url"].startswith(
        "data:image/png;base64,iVBOR"
    )
    assert messages[0]["content"][1]["image_url"]["url"] == url


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
