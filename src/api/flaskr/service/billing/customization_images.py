"""Brand logo and favicon validation and normalization for customization.

Size and format limits stay defined in ``customization`` and are read through
``_customization_facade()`` so patches applied there keep reaching this code.
"""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING, Any

from flaskr.service.common.models import raise_param_error
from PIL import Image, ImageOps, UnidentifiedImageError

if TYPE_CHECKING:
    from types import ModuleType

    from werkzeug.datastructures import FileStorage


def _customization_facade() -> ModuleType:
    """Resolve limits through ``customization`` so its patch points stay live."""
    from . import customization

    return customization


def _detect_logo_content_type(content: bytes) -> str:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith(b"\x00\x00\x01\x00"):
        return "image/x-icon"
    return ""


def _build_favicon_bytes(content: bytes) -> bytes:
    """Convert an uploaded raster logo into a multi-size ICO favicon."""
    customization = _customization_facade()
    try:
        with Image.open(BytesIO(content)) as image:
            if image.width * image.height > customization._LOGO_MAX_PIXELS:
                raise_param_error("file")
            normalized_image = ImageOps.exif_transpose(image).convert("RGBA")
            side = max(normalized_image.size)
            canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
            canvas.paste(
                normalized_image,
                (
                    (side - normalized_image.width) // 2,
                    (side - normalized_image.height) // 2,
                ),
            )
            canvas = canvas.resize(
                (
                    customization._FAVICON_CANVAS_SIZE,
                    customization._FAVICON_CANVAS_SIZE,
                ),
                Image.LANCZOS,
            )
            output = BytesIO()
            canvas.save(output, format="ICO", sizes=customization._FAVICON_SIZES)
            return output.getvalue()
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError):
        raise_param_error("file")


def _validate_ico_bytes(content: bytes) -> None:
    """Ensure an uploaded .ico actually decodes as an ICO before storing it."""
    customization = _customization_facade()
    try:
        with Image.open(BytesIO(content), formats=["ICO"]) as image:
            if image.width * image.height > customization._LOGO_MAX_PIXELS:
                raise_param_error("file")
            image.load()
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError):
        raise_param_error("file")


def _read_validated_brand_image(
    file: FileStorage, target: str
) -> tuple[bytes, str, str]:
    """Validate an uploaded brand asset and return (bytes, suffix, content type).

    Favicon uploads accept the regular raster formats plus .ico; raster input
    is converted into a real multi-size ICO so operators can upload a PNG.
    """
    customization = _customization_facade()
    filename = str(file.filename or "").strip()
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    content_types = (
        customization._FAVICON_CONTENT_TYPES
        if target == "favicon"
        else customization._LOGO_CONTENT_TYPES
    )
    expected_content_type = content_types.get(suffix)
    content = file.stream.read(customization._LOGO_MAX_BYTES + 1)
    if (
        expected_content_type is None
        or not content
        or len(content) > customization._LOGO_MAX_BYTES
        or _detect_logo_content_type(content) != expected_content_type
    ):
        raise_param_error("file")
    if target == "favicon":
        if suffix != ".ico":
            content = _build_favicon_bytes(content)
        else:
            _validate_ico_bytes(content)
        return content, ".ico", "image/x-icon"
    return (
        _normalize_logo_image(content, suffix=suffix, target=target),
        suffix,
        expected_content_type,
    )


def _normalize_logo_target(value: object) -> str:
    customization = _customization_facade()
    normalized = str(value or "wide").strip().lower()
    if normalized not in customization._LOGO_VARIANTS:
        raise_param_error("target")
    return normalized


def _normalize_logo_image(content: bytes, *, suffix: str, target: str) -> bytes:
    customization = _customization_facade()
    try:
        with Image.open(BytesIO(content)) as image:
            if image.width * image.height > customization._LOGO_MAX_PIXELS:
                raise_param_error("file")
            normalized_image = ImageOps.exif_transpose(image)
            if target == "square":
                rendered = _contain_logo_without_upscale(
                    normalized_image,
                    customization._LOGO_SQUARE_MAX_SIZE,
                )
                canvas_size = (
                    min(
                        customization._LOGO_SQUARE_MAX_SIZE[0],
                        max(rendered.width, rendered.height),
                    ),
                    min(
                        customization._LOGO_SQUARE_MAX_SIZE[1],
                        max(rendered.width, rendered.height),
                    ),
                )
                canvas = _create_logo_canvas(
                    size=canvas_size,
                    suffix=suffix,
                    source_mode=rendered.mode,
                )
                offset = (
                    (canvas_size[0] - rendered.width) // 2,
                    (canvas_size[1] - rendered.height) // 2,
                )
                _paste_logo(canvas, rendered, offset)
                return _save_logo_image(canvas, suffix=suffix)

            rendered = _contain_logo_without_upscale(
                normalized_image,
                customization._LOGO_WIDE_MAX_SIZE,
            )
            return _save_logo_image(rendered, suffix=suffix)
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError):
        raise_param_error("file")


def _contain_logo_without_upscale(
    image: Image.Image,
    size: tuple[int, int],
) -> Image.Image:
    rendered = image.copy()
    if rendered.width > size[0] or rendered.height > size[1]:
        rendered.thumbnail(size, Image.Resampling.LANCZOS)
    return rendered


def _create_logo_canvas(
    *,
    size: tuple[int, int],
    suffix: str,
    source_mode: str,
) -> Image.Image:
    if suffix in {".jpg", ".jpeg"}:
        return Image.new("RGB", size, (255, 255, 255))
    if "A" in source_mode:
        return Image.new("RGBA", size, (255, 255, 255, 0))
    return Image.new("RGB", size, (255, 255, 255))


def _paste_logo(
    canvas: Image.Image,
    rendered: Image.Image,
    offset: tuple[int, int],
) -> None:
    if "A" in rendered.getbands():
        canvas.paste(rendered, offset, rendered)
        return
    canvas.paste(rendered, offset)


def _save_logo_image(image: Image.Image, *, suffix: str) -> bytes:
    output = BytesIO()
    save_kwargs: dict[str, Any] = {}
    if suffix == ".webp":
        save_format = "WEBP"
    elif suffix in {".jpg", ".jpeg"}:
        save_format = "JPEG"
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        save_kwargs["quality"] = 95
    else:
        save_format = "PNG"
        if image.mode not in {"RGB", "RGBA", "L"}:
            image = image.convert("RGBA")
    image.save(output, format=save_format, **save_kwargs)
    return output.getvalue()
