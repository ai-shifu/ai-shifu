# Desc: Common models for the application
from flaskr.i18n import _
import json
from pathlib import Path


class AppException(Exception):
    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        self.code = status_code
        self.payload = payload

    def __json__(self):
        rv = dict(self.payload or ())
        rv["message"] = self.message
        rv["code"] = self.code
        return rv

    def __str__(self):
        return self.message

    def __html__(self):
        return self.__json__()


def _load_error_codes() -> dict[str, int]:
    # Locate src/api/error_codes.json
    api_root = Path(__file__).resolve().parents[3]
    manifest_path = api_root / "error_codes.json"
    if not manifest_path.exists():
        # Fallback to legacy in-file mapping (minimal set)
        return {
            "module.backend.common.unknownError": 9999,
        }

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    codes: dict[str, int] = {}
    for key, value in data.items():
        if not isinstance(value, int):
            continue
        # Primary key (expected to be 'server.*')
        codes[key] = value
        # Legacy alias for gradual migration: module.backend.<...>
        if key.startswith("server."):
            legacy = "module.backend." + key[len("server.") :]
            codes[legacy] = value
    return codes


ERROR_CODE = _load_error_codes()


def register_error(error_name, error_code):
    ERROR_CODE[error_name] = error_code


def raise_param_error(param_message):
    raise AppException(
        _("module.backend.common.paramsError").format(param_message=param_message),
        ERROR_CODE["module.backend.common.paramsError"],
    )


def raise_error(error_name):
    raise AppException(
        _(error_name),
        ERROR_CODE.get(error_name, ERROR_CODE["module.backend.common.unknownError"]),
    )


def raise_error_with_args(error_name, **kwargs):
    raise AppException(
        _(error_name).format(**kwargs),
        ERROR_CODE.get(error_name, ERROR_CODE["module.backend.common.unknownError"]),
    )


def reg_error_code(error_name, error_code):
    ERROR_CODE[error_name] = error_code
