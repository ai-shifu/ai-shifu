from __future__ import annotations

import mimetypes
from pathlib import Path

from flask import Flask, Response, send_file

from flaskr.route.common import bypass_token_validation
from flaskr.service.common.storage import get_local_storage_path


def _guess_mimetype(path: Path) -> str:
    guessed, _encoding = mimetypes.guess_type(path.name)
    if guessed:
        return guessed

    try:
        with open(path, "rb") as f:
            header = f.read(16)
    except OSError:
        return "application/octet-stream"

    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if header.startswith(b"ID3"):
        return "audio/mpeg"
    if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
        return "audio/mpeg"

    return "application/octet-stream"


def register_storage_handler(app: Flask, path_prefix: str) -> Flask:
    @app.route(path_prefix + "/storage/<profile>/<path:object_key>", methods=["GET"])
    @bypass_token_validation
    def serve_local_storage(profile: str, object_key: str):
        try:
            file_path = get_local_storage_path(profile, object_key)
        except ValueError:
            return Response(status=400)

        if not file_path.exists() or not file_path.is_file():
            return Response(status=404)

        return send_file(
            file_path,
            mimetype=_guess_mimetype(file_path),
            as_attachment=False,
            conditional=True,
        )

    return app
