"""Run narrowly scoped backend operations inside an existing configured environment."""

from __future__ import annotations

import base64
import contextlib
import gzip
import io
import json
import os
import sys
from typing import TYPE_CHECKING

from .state import REQUESTED_MODELS, ArenaError, validate_config

if TYPE_CHECKING:
    from flask import Flask

WORKER_PROTOCOL_VERSION = 1
COMPRESS_RESPONSE_BYTES = 1024 * 1024


def _success_response(result: object) -> dict:
    """Keep large UTF-8 snapshots compact and ASCII-safe across operator transports."""
    serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    response = {"ok": True, "protocol_version": WORKER_PROTOCOL_VERSION, "data": result}
    if len(serialized) > COMPRESS_RESPONSE_BYTES:
        response["encoding"] = "gzip+base64"
        response["data"] = base64.b64encode(gzip.compress(serialized, mtime=0)).decode(
            "ascii"
        )
    return response


def build_app(config: dict) -> Flask:
    """Initialize required services without routes, migrations, or app plugins."""
    os.environ["SKIP_APP_AUTOCREATE"] = "1"
    from dotenv import load_dotenv

    if not os.environ.get("SKIP_LOAD_DOTENV"):
        load_dotenv()
    routes = config.get("model_routes")
    if routes:
        # The override belongs to this short-lived evaluation process only.
        os.environ["LLM_ALLOWED_MODELS"] = ",".join(routes)
        os.environ["LLM_ALLOWED_MODEL_DISPLAY_NAMES"] = ",".join(config["models"])
    import pymysql
    from flask import Flask
    from flaskr import dao
    from flaskr.common.config import Config
    from flaskr.i18n import load_translations

    pymysql.install_as_MySQLdb()
    app = Flask("markdownflow-arena")
    app.config = Config(app.config, app)
    dao.init_db(app)
    dao.init_redis(app)
    load_translations(app)
    return app


def execute(request: dict) -> object:
    """Dispatch an explicit operation; the transport never accepts Python code."""
    from . import engine, source

    config = validate_config(request["config"])
    app = build_app(config)
    with app.app_context():
        operation = request["operation"]
        if operation == "snapshot":
            snapshot = source.snapshot_courses(app, config["owner_phone"])
            cases = source.prepare_cases(
                snapshot, config["case_count"], config["seed"], config["variables"]
            )
            return {"snapshot": snapshot, "cases": cases}
        if operation == "resolve_models":
            return engine.resolve_models(app, config["models"])
        if operation == "revalidate":
            # Resolve the configured identity again, rather than trusting a stale ID.
            if (
                source.resolve_owner_user_bid(app, config["owner_phone"])
                != request["owner_user_bid"]
            ):
                msg = "The configured owner identity changed"
                raise ArenaError(msg)
            return sorted(
                source.revalidate_sources(
                    app, request["owner_user_bid"], request["cases"]
                )
            )
        if operation == "generate":
            from flaskr.api.langfuse import init_langfuse

            init_langfuse(app)
            case, model = request["case"], request["model"]
            if (
                source.resolve_owner_user_bid(app, config["owner_phone"])
                != case["owner_user_bid"]
            ):
                msg = "The frozen case does not belong to the configured identity"
                raise ArenaError(msg)
            if model["requested"] not in REQUESTED_MODELS:
                msg = "Unexpected model version"
                raise ArenaError(msg)
            resolved = engine.resolve_models(app, [model["requested"]])
            if resolved[0]["model"] != model["model"]:
                msg = "The frozen model route is no longer available"
                raise ArenaError(msg)
            allowed = source.revalidate_sources(app, case["owner_user_bid"], [case])
            if case["case_id"] not in allowed:
                msg = "Course prompt access was revoked"
                raise ArenaError(msg)
            return engine.generate_case(app, case, model)
        msg = "Unsupported arena worker operation"
        raise ArenaError(msg)


def worker_main() -> int:
    """Keep protocol stdout free of provider logs, credentials, and tracebacks."""
    try:
        request = json.load(sys.stdin)
        with contextlib.redirect_stdout(io.StringIO()):
            result = execute(request)
        print(json.dumps(_success_response(result), ensure_ascii=False))
    except ArenaError as error:
        # These errors originate from the explicit arena contracts. No raw
        # provider exception or network request is returned across the protocol.
        print(
            json.dumps(
                {
                    "ok": False,
                    "protocol_version": WORKER_PROTOCOL_VERSION,
                    "error": {"type": type(error).__name__, "message": str(error)},
                },
                ensure_ascii=False,
            )
        )
        return 1
    except Exception as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "protocol_version": WORKER_PROTOCOL_VERSION,
                    "error": {
                        "type": type(error).__name__,
                        "message": "Backend operation failed; verify runtime configuration and connectivity",
                    },
                }
            )
        )
        return 1
    else:
        return 0
