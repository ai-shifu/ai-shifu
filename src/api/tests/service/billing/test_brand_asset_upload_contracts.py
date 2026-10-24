"""Verify uploaded brand assets are validated and normalized before storage."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.service.billing import customization
from flaskr.service.common.models import AppError
from PIL import Image
from werkzeug.datastructures import FileStorage


def _file(
    mode: str, suffix: str, *, size: tuple[int, int] = (1200, 300)
) -> FileStorage:
    stream = BytesIO()
    format_name = {"png": "PNG", "jpg": "JPEG", "webp": "WEBP", "ico": "ICO"}[suffix]
    Image.new(mode, size).save(stream, format=format_name)
    stream.seek(0)
    return FileStorage(stream=stream, filename="brand." + suffix)


@pytest.mark.parametrize(
    ("mode", "suffix", "target", "output_size"),
    [
        ("RGB", "jpg", "wide", (384, 96)),
        ("RGB", "jpg", "square", (96, 96)),
        ("RGBA", "webp", "square", (96, 96)),
        ("P", "png", "wide", (384, 96)),
        ("RGB", "png", "square", (96, 96)),
        ("RGBA", "png", "favicon", (48, 48)),
    ],
)
def test_admin_brand_asset_upload_stores_normalized_pixels_and_correct_content_type(
    mode: str,
    suffix: str,
    target: str,
    output_size: tuple[int, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload = Mock(return_value=SimpleNamespace(url="https://assets.example.test/logo"))
    monkeypatch.setattr(customization, "upload_to_storage", upload)
    result = customization.upload_admin_creator_draft_logo(
        Flask(__name__),
        creator_bid="teacher-test",
        file=_file(mode, suffix),
        target=target,
    )
    assert result == "https://assets.example.test/logo"
    kwargs = upload.call_args.kwargs
    expected_suffix = "ico" if target == "favicon" else suffix
    assert kwargs["object_key"].startswith(
        "creator-branding-drafts/billing-admin-draft:creator:teacher-test/"
    )
    assert kwargs["object_key"].endswith("." + expected_suffix)
    assert kwargs["warm_up"] is False
    with Image.open(kwargs["file_content"]) as uploaded:
        assert uploaded.size == output_size
        assert (
            uploaded.format
            == {"ico": "ICO", "jpg": "JPEG", "png": "PNG", "webp": "WEBP"}[
                expected_suffix
            ]
        )
    assert (
        kwargs["content_type"]
        == {
            "ico": "image/x-icon",
            "jpg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
        }[expected_suffix]
    )


@pytest.mark.parametrize("target", ["wide", "square", "favicon"])
def test_corrupt_image_with_valid_magic_header_cannot_reach_storage(
    target: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload = Mock()
    monkeypatch.setattr(customization, "upload_to_storage", upload)
    with pytest.raises(AppError):
        customization.upload_admin_creator_draft_logo(
            Flask(__name__),
            creator_bid="teacher-test",
            file=FileStorage(
                stream=BytesIO(b"\x89PNG\r\n\x1a\ninvalid"), filename="brand.png"
            ),
            target=target,
        )
    upload.assert_not_called()


@pytest.mark.parametrize(
    ("target", "suffix"), [("wide", "png"), ("favicon", "png"), ("favicon", "ico")]
)
def test_pixel_limit_applies_before_normalizing_logo_or_icon(
    target: str,
    suffix: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(customization, "_LOGO_MAX_PIXELS", 32)
    upload = Mock()
    monkeypatch.setattr(customization, "upload_to_storage", upload)
    with pytest.raises(AppError):
        customization.upload_admin_creator_draft_logo(
            Flask(__name__),
            creator_bid="teacher-test",
            file=_file("RGBA", suffix, size=(64, 64)),
            target=target,
        )
    upload.assert_not_called()


def test_ico_upload_validates_and_preserves_existing_icon_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file = _file("RGBA", "ico", size=(48, 48))
    original = file.stream.getvalue()
    upload = Mock(return_value=SimpleNamespace(url="/storage/icon.ico"))
    monkeypatch.setattr(customization, "upload_to_storage", upload)
    assert (
        customization.upload_admin_creator_draft_logo(
            Flask(__name__), creator_bid="teacher-test", file=file, target="favicon"
        )
        == "/storage/icon.ico"
    )
    assert upload.call_args.kwargs["file_content"].getvalue() == original


def test_unknown_brand_asset_target_is_rejected_before_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload = Mock()
    monkeypatch.setattr(customization, "upload_to_storage", upload)
    with pytest.raises(AppError):
        customization.upload_admin_creator_draft_logo(
            Flask(__name__),
            creator_bid="teacher-test",
            file=_file("RGB", "png"),
            target="avatar",
        )
    upload.assert_not_called()
