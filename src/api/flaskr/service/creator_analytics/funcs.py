"""Business orchestration for the creator-analytics DSL endpoint."""

from __future__ import annotations

from typing import Any, Dict

from flask import Flask

from flaskr.service.common.models import AppException, ERROR_CODE
from flaskr.service.shifu.permissions import get_user_shifu_permissions
from flaskr.i18n import _

from .dsl import parse_dsl
from .engine import get_analytics_engine, run_query
from .pii import redact_pii
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

    if "generated_content" in dsl.select:
        # Audit log for raw conversation-content access. Surfaces in application
        # logs (Loki/Grafana) so any after-the-fact review can attribute who
        # pulled which course's content.
        type_values = sorted(
            {
                value
                for f in dsl.filters
                if f.field == "type"
                for value in (f.value if isinstance(f.value, list) else [f.value])
            }
        )
        app.logger.info(
            "creator_analytics.content_access user_id=%s shifu_bid=%s "
            "table=%s types=%s limit=%s offset=%s",
            user_id,
            dsl.shifu_bid,
            dsl.table,
            type_values,
            dsl.limit,
            dsl.offset,
        )

    if dsl.table == "user_users":
        # Audit log for nickname lookup. The user_bid candidates were supplied
        # by the caller; we log the count, not the values, to keep the log line
        # bounded.
        requested_user_bids = _user_bid_candidates(dsl.filters)
        app.logger.info(
            "creator_analytics.user_lookup user_id=%s shifu_bid=%s "
            "table=user_users user_bid_count=%s limit=%s",
            user_id,
            dsl.shifu_bid,
            len(requested_user_bids),
            dsl.limit,
        )

    result = run_query(app, stmt)
    if dsl.table == "user_users":
        _redact_user_users_rows(result)
    result["limit"] = dsl.limit
    result["offset"] = dsl.offset
    return result


def _user_bid_candidates(filters) -> list[str]:
    """Flatten the user_bid candidates out of the DSL filters for audit."""

    out: list[str] = []
    for f in filters:
        if f.field != "user_bid":
            continue
        if isinstance(f.value, list):
            out.extend(str(v) for v in f.value)
        elif f.value is not None:
            out.append(str(f.value))
    return out


def _redact_user_users_rows(result: Dict[str, Any]) -> None:
    """Apply :func:`redact_pii` to the ``nickname`` column in-place."""

    columns = result.get("columns") or []
    rows = result.get("rows") or []
    if not rows:
        return
    try:
        nickname_idx = columns.index("nickname")
    except ValueError:
        return
    for row in rows:
        if 0 <= nickname_idx < len(row):
            row[nickname_idx] = redact_pii(row[nickname_idx])


def _raise(error_name: str) -> None:
    message = _(error_name)
    code = ERROR_CODE.get(error_name, ERROR_CODE.get("server.common.unknownError"))
    raise AppException(message, code)


__all__ = ["run_dsl", "ERR_NO_PERMISSION"]
