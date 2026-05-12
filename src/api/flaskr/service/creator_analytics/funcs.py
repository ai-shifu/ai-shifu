"""Business orchestration for the creator-analytics DSL endpoint."""

from __future__ import annotations

from typing import Any, Dict

from flask import Flask

from flaskr.service.common.models import AppException, ERROR_CODE
from flaskr.service.shifu.permissions import get_user_shifu_permissions
from flaskr.i18n import _

from .dsl import parse_dsl
from .engine import get_analytics_engine, run_query
from .sql_builder import build_statement


ERR_NO_PERMISSION = "server.creatorAnalytics.noPermission"


def run_dsl(app: Flask, user_id: str, payload: Any) -> Dict[str, Any]:
    """Execute a DSL query on behalf of ``user_id``.

    Steps:
        1. Look up the user's viewable shifu set (owner + shared via
           ``ai_course_auth``).
        2. Parse and validate the DSL payload against the static whitelist.
        3. Reject if the requested ``shifu_bid`` is not in the viewable set.
        4. Compile to SQL with the configured analytics engine's dialect and
           execute it through the read-only engine.
    """

    limit_max = int(app.config.get("ANALYTICS_QUERY_LIMIT_MAX") or 1000)
    query_timeout = int(app.config.get("ANALYTICS_QUERY_TIMEOUT_SECONDS") or 15)

    dsl = parse_dsl(payload, limit_max=limit_max)

    permissions = get_user_shifu_permissions(app, user_id)
    allowed_perms = permissions.get(dsl.shifu_bid, set())
    if "view" not in allowed_perms:
        _raise(ERR_NO_PERMISSION)

    engine = get_analytics_engine(app)
    stmt = build_statement(
        dsl,
        dialect_name=engine.dialect.name,
        query_timeout_seconds=query_timeout,
    )

    result = run_query(app, stmt)
    result["limit"] = dsl.limit
    result["offset"] = dsl.offset
    return result


def _raise(error_name: str) -> None:
    message = _(error_name)
    code = ERROR_CODE.get(error_name, ERROR_CODE.get("server.common.unknownError"))
    raise AppException(message, code)


__all__ = ["run_dsl", "ERR_NO_PERMISSION"]
