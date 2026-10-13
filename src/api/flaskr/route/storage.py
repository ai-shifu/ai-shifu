"""Expose storage HTTP routes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Flask, Response, send_file

from flaskr.route.common import bypass_token_validation
from flaskr.service.common.storage import get_local_storage_path

if TYPE_CHECKING:
    from pathlib import Path


def _guess_mimetype(path: Path) -> str:
    """Identify passive media from bytes, never from an untrusted object key."""
    try:
        # Builtin open() avoids CodeQL's Path.open path-injection sink after
        # get_local_storage_path() already confined this path.
        with open(path, "rb") as f:  # noqa: PTH123
            header = f.read(16)
    except OSError:
        return "application/octet-stream"

    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    if header.startswith(b"\x00\x00\x01\x00"):
        return "image/x-icon"
    if header.startswith(b"ID3"):
        return "audio/mpeg"
    if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
        return "audio/mpeg"

    return "application/octet-stream"


def register_storage_handler(app: Flask, path_prefix: str) -> Flask:
    """Register the storage routes on the Flask application."""

    @app.route(path_prefix + "/storage/<profile>/<path:object_key>", methods=["GET"])
    @bypass_token_validation
    def serve_local_storage(profile: str, object_key: str) -> Response:
        try:
            file_path = get_local_storage_path(profile, object_key)
        except ValueError:
            return Response(status=400)

        if not file_path.exists() or not file_path.is_file():
            return Response(status=404)

        mimetype = _guess_mimetype(file_path)
        response = send_file(
            file_path,
            mimetype=mimetype,
            as_attachment=mimetype == "application/octet-stream",
            conditional=True,
        )
        # Cover historical objects and every upload producer, including range
        # and cache-revalidation responses. No uploaded document may inherit
        # application-origin privileges even if a browser interprets its bytes.
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "sandbox; default-src 'none'; base-uri 'none'; form-action 'none'"
        )
        return response

    return app
