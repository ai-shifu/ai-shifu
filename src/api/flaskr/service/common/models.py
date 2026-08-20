# Desc: Common models for the application
"""Define persistence models for shared backend behavior."""

import json
from pathlib import Path

from flaskr.i18n import _
from flaskr.util.deprecation import deprecated_alias_getattr


class AppError(Exception):
    def __init__(self, message, status_code=None, payload=None) -> None:
        """Initialize an application error and response payload."""
        Exception.__init__(self)
        self.message = message
        self.code = status_code
        self.payload = payload

    def __json__(self) -> dict:
        """Return the application error as JSON-compatible data."""
        rv = dict(self.payload or ())
        rv["message"] = self.message
        rv["code"] = self.code
        return rv

    def __str__(self) -> str:
        """Return the application error message."""
        return self.message

    def __html__(self) -> dict:
        """Return the serialized application-error payload."""
        return self.__json__()


def _load_error_codes() -> dict[str, int]:
    # Locate src/api/error_codes.json
    api_root = Path(__file__).resolve().parents[3]
    manifest_path = api_root / "error_codes.json"
    if not manifest_path.exists():
        # Fallback to legacy in-file mapping (minimal set)
        return {
            "server.common.unknownError": 9999,
        }

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    codes: dict[str, int] = {}
    for key, value in data.items():
        if not isinstance(value, int):
            continue
        # Primary keys are defined as server.*; legacy module.backend.* is no longer supported
        codes[key] = value
    return codes


ERROR_CODE = _load_error_codes()


def register_error(error_name, error_code):
    ERROR_CODE[error_name] = error_code


def raise_param_error(param_message):
    raise AppError(
        _("server.common.paramsError").format(param_message=param_message),
        ERROR_CODE["server.common.paramsError"],
    )


def raise_error(error_name):
    raise AppError(
        _(error_name),
        ERROR_CODE.get(error_name, ERROR_CODE["server.common.unknownError"]),
    )


def raise_error_with_args(error_name, **kwargs):
    raise AppError(
        _(error_name).format(**kwargs),
        ERROR_CODE.get(error_name, ERROR_CODE["server.common.unknownError"]),
    )


__getattr__ = deprecated_alias_getattr(
    __name__, {"AppException": "AppError"}, globals()
)
