"""Credit-detail endpoint — server-side join of bill_usage x credit_ledger_entries.

The DSL path (``funcs.run_dsl``) intentionally does not expose
``credit_ledger_entries`` and (since 2026-05-15) does not expose
``bill_usage`` either. The motivation was that ``bill_daily_usage_metrics``
would carry an aggregated ``consumed_credits`` figure that creators could
query directly. In practice that table is empty in production because the
daily aggregation Celery beat schedule never registered the
``billing.aggregate_daily_usage_metrics`` task (see
``flaskr.common.celery_app._build_billing_beat_schedule``), so creators have
no way to see actual credit consumption through the DSL.

This module fills that gap with a single purpose-built endpoint. It joins
``bill_usage`` to ``credit_ledger_entries`` on
``source_bid = usage_bid AND source_type = USAGE`` and returns one row per
real credit deduction tied to the requested shifu. The DSL surface is
left untouched — ``credit_ledger_entries`` still does not appear in the
whitelist.

Security model:

* Permission check uses :func:`get_user_shifu_permissions` exactly like the
  DSL path; callers must hold ``"view"`` on the requested ``shifu_bid``.
* The join is anchored on ``bill_usage.shifu_bid``, so rows for other
  courses cannot leak even though ``credit_ledger_entries`` itself has no
  ``shifu_bid`` column.
* ``source_type = CREDIT_SOURCE_TYPE_USAGE`` is asserted as a join condition
  to keep subscription / top-up / gift / refund / manual adjustments out of
  the result — those are wallet-level ledger entries unrelated to the
  course's runtime spend.
* The response exposes only the fields creators need (``usage_bid``,
  ``created_at``, ``user_bid``, ``progress_record_bid``, ``outline_item_bid``,
  ``usage_type``, ``usage_scene``, ``provider``, ``model``, ``credits``,
  ``wallet_creator_bid``). Internal ledger fields (``wallet_bid``,
  ``wallet_bucket_bid``, ``idempotency_key``, ``balance_after``,
  ``metadata_json``) are not selected.
* ``amount`` is stored as a negative number for deductions; the API returns
  ``ABS(amount)`` so creators see a positive credit-consumption figure.

A separate aggregate query computes the summary (total records, total
credits, distinct users / progress records, wallet creator id, time range)
over the full filtered set — independent of the pagination on the row
result so the summary is stable.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from datetime import date, datetime
from flask import Flask
from sqlalchemy import and_, bindparam, func, select
from sqlalchemy.sql import Select

from flaskr.service.billing.consts import CREDIT_SOURCE_TYPE_USAGE
from flaskr.service.billing.models import CreditLedgerEntry
from flaskr.service.common.models import AppException, ERROR_CODE
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.shifu.permissions import get_user_shifu_permissions
from flaskr.i18n import _

from .engine import get_analytics_engine


# Reuse the DSL-path error names so the HTTP wrapper maps them consistently
# (the error name → HTTP code mapping lives in error_codes.json).
ERR_NO_PERMISSION = "server.creatorAnalytics.noPermission"
ERR_INVALID_DSL = "server.creatorAnalytics.invalidDsl"
ERR_INVALID_LIMIT = "server.creatorAnalytics.invalidLimit"


# Allowed enum values for the optional filters. Anything outside these sets
# is rejected with ERR_INVALID_DSL so the caller learns about typos quickly
# rather than getting a silently empty result set.
_ALLOWED_USAGE_SCENES = frozenset({1201, 1202, 1203})
_ALLOWED_USAGE_TYPES = frozenset({1101, 1102})

_DEFAULT_LIMIT = 100


def run(app: Flask, user_id: str, payload: Any) -> Dict[str, Any]:
    """Execute the credit-detail query for ``user_id``.

    Validates the payload, enforces the per-shifu permission check, then
    issues two SQL statements against the analytics engine: one paginated
    detail query and one aggregate summary query.
    """

    limit_max = int(app.config.get("ANALYTICS_QUERY_LIMIT_MAX") or 1000)

    params = _parse_payload(payload, limit_max=limit_max)

    permissions = get_user_shifu_permissions(app, user_id)
    allowed_perms = permissions.get(params.shifu_bid, set())
    if "view" not in allowed_perms:
        _raise(ERR_NO_PERMISSION)

    detail_stmt = _build_detail_statement(params)
    summary_stmt = _build_summary_statement(params)

    engine = get_analytics_engine(app)
    with engine.connect() as connection:
        detail_result = connection.execute(detail_stmt)
        detail_columns = list(detail_result.keys())
        # Iterate the result proxy directly instead of fetchall() + list comp:
        # avoids materialising an intermediate per-row list copy. The page
        # size is already capped at `limit` (≤ 1000) so memory is bounded
        # either way, but the shorter form is the conventional SQLAlchemy
        # pattern and was flagged by review on PR #1771.
        rows = [_row_to_dict(detail_columns, row) for row in detail_result]

        summary_result = connection.execute(summary_stmt)
        summary_row = summary_result.first()

    summary = _summary_row_to_dict(summary_row)

    # Audit: who hit credit-detail for which shifu with which filters. The
    # row count plus the resolved time window is enough for retroactive
    # auditing without dumping the (potentially large) row payload itself.
    app.logger.info(
        "creator_analytics.credit_detail user_id=%s shifu_bid=%s "
        "rows=%d total_credits=%s scene=%s usage_type=%s "
        "start_date=%s end_date=%s limit=%s offset=%s",
        user_id,
        params.shifu_bid,
        len(rows),
        summary.get("total_credits"),
        sorted(params.usage_scene) if params.usage_scene else None,
        sorted(params.usage_type) if params.usage_type else None,
        params.start_date.isoformat() if params.start_date else None,
        params.end_date.isoformat() if params.end_date else None,
        params.limit,
        params.offset,
    )

    return {
        "summary": summary,
        "rows": rows,
        "limit": params.limit,
        "offset": params.offset,
    }


# ---------------------------------------------------------------------------
# Parameter parsing
# ---------------------------------------------------------------------------


class _Params:
    """Parsed and validated request payload — internal type only."""

    __slots__ = (
        "shifu_bid",
        "start_date",
        "end_date",
        "usage_scene",
        "usage_type",
        "limit",
        "offset",
    )

    def __init__(
        self,
        *,
        shifu_bid: str,
        start_date: Optional[date],
        end_date: Optional[date],
        usage_scene: Optional[Tuple[int, ...]],
        usage_type: Optional[Tuple[int, ...]],
        limit: int,
        offset: int,
    ) -> None:
        self.shifu_bid = shifu_bid
        self.start_date = start_date
        self.end_date = end_date
        self.usage_scene = usage_scene
        self.usage_type = usage_type
        self.limit = limit
        self.offset = offset


def _parse_payload(payload: Any, limit_max: int) -> _Params:
    if not isinstance(payload, dict):
        _raise(ERR_INVALID_DSL, "payload must be a JSON object")

    shifu_bid = payload.get("shifu_bid")
    if not isinstance(shifu_bid, str) or not shifu_bid:
        _raise(ERR_INVALID_DSL, "shifu_bid is required and must be a non-empty string")

    start_date = _parse_optional_date(payload.get("start_date"), "start_date")
    end_date = _parse_optional_date(payload.get("end_date"), "end_date")
    if start_date and end_date and end_date < start_date:
        _raise(ERR_INVALID_DSL, "end_date must be on or after start_date")

    usage_scene = _parse_int_set(
        payload.get("usage_scene"), "usage_scene", _ALLOWED_USAGE_SCENES
    )
    usage_type = _parse_int_set(
        payload.get("usage_type"), "usage_type", _ALLOWED_USAGE_TYPES
    )

    limit = _parse_int(payload.get("limit"), "limit", default=_DEFAULT_LIMIT)
    if limit < 1 or limit > limit_max:
        _raise(ERR_INVALID_LIMIT, f"'limit' must be in [1, {limit_max}]")

    offset = _parse_int(payload.get("offset"), "offset", default=0)
    if offset < 0:
        _raise(ERR_INVALID_LIMIT, "'offset' must be >= 0")

    return _Params(
        shifu_bid=shifu_bid,
        start_date=start_date,
        end_date=end_date,
        usage_scene=usage_scene,
        usage_type=usage_type,
        limit=limit,
        offset=offset,
    )


def _parse_optional_date(raw: Any, field_name: str) -> Optional[date]:
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        _raise(
            ERR_INVALID_DSL, f"'{field_name}' must be an ISO date string (YYYY-MM-DD)"
        )
    try:
        return date.fromisoformat(raw)
    except ValueError:
        _raise(
            ERR_INVALID_DSL, f"'{field_name}' must be an ISO date string (YYYY-MM-DD)"
        )
        return None  # unreachable — _raise raises


def _parse_int_set(
    raw: Any, field_name: str, allowed: Iterable[int]
) -> Optional[Tuple[int, ...]]:
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        _raise(ERR_INVALID_DSL, f"'{field_name}' must be a non-empty list of integers")
    allowed_set = set(allowed)
    out: List[int] = []
    seen: set[int] = set()
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, int):
            _raise(ERR_INVALID_DSL, f"'{field_name}' values must be integers")
        if item not in allowed_set:
            _raise(
                ERR_INVALID_DSL,
                f"'{field_name}' value {item} is not in the allowed set "
                f"{sorted(allowed_set)}",
            )
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return tuple(out)


def _parse_int(raw: Any, field_name: str, *, default: int) -> int:
    if raw is None:
        return default
    if isinstance(raw, bool) or not isinstance(raw, int):
        _raise(ERR_INVALID_LIMIT, f"'{field_name}' must be an integer")
    return int(raw)


# ---------------------------------------------------------------------------
# SQL construction
# ---------------------------------------------------------------------------


def _join_conditions(params: _Params):
    """Build the bill_usage x credit_ledger_entries ON clause.

    ``source_type = USAGE`` is part of the JOIN (not the WHERE) so the
    optimizer can use the
    ``ix_credit_ledger_entries_source_type_source_bid`` composite index
    rather than scanning every ledger row tied to the matching usage_bid.
    """

    bu = BillUsageRecord.__table__
    cle = CreditLedgerEntry.__table__
    return cle.join(
        bu,
        and_(
            cle.c.source_bid == bu.c.usage_bid,
            cle.c.source_type
            == bindparam("__source_type", value=CREDIT_SOURCE_TYPE_USAGE),
            cle.c.deleted == 0,
            bu.c.deleted == 0,
        ),
    )


def _where_clauses(params: _Params):
    """Common WHERE predicates shared by detail + summary queries."""

    bu = BillUsageRecord.__table__
    clauses = [bu.c.shifu_bid == bindparam("__shifu_bid", value=params.shifu_bid)]
    if params.start_date is not None:
        clauses.append(
            bu.c.created_at
            >= bindparam(
                "__start_at",
                value=datetime.combine(params.start_date, datetime.min.time()),
            )
        )
    if params.end_date is not None:
        # end_date is inclusive in the user-facing API; convert to an
        # exclusive upper bound at midnight of the *next* day so the
        # comparison stays consistent regardless of how the underlying
        # `created_at` carries fractional seconds.
        next_day = datetime.combine(params.end_date, datetime.min.time())
        # Pull in timedelta locally to avoid a top-level import for one use.
        from datetime import timedelta

        next_day = next_day + timedelta(days=1)
        clauses.append(bu.c.created_at < bindparam("__end_at", value=next_day))
    if params.usage_scene:
        clauses.append(bu.c.usage_scene.in_(list(params.usage_scene)))
    if params.usage_type:
        clauses.append(bu.c.usage_type.in_(list(params.usage_type)))
    return clauses


def _build_detail_statement(params: _Params) -> Select:
    bu = BillUsageRecord.__table__
    cle = CreditLedgerEntry.__table__

    stmt = (
        select(
            bu.c.usage_bid,
            bu.c.created_at,
            bu.c.user_bid,
            bu.c.progress_record_bid,
            bu.c.outline_item_bid,
            bu.c.usage_type,
            bu.c.usage_scene,
            bu.c.provider,
            bu.c.model,
            func.abs(cle.c.amount).label("credits"),
            cle.c.creator_bid.label("wallet_creator_bid"),
        )
        .select_from(_join_conditions(params))
        .where(and_(*_where_clauses(params)))
        .order_by(bu.c.created_at.desc())
        .limit(params.limit)
        .offset(params.offset)
    )
    return stmt


def _build_summary_statement(params: _Params) -> Select:
    bu = BillUsageRecord.__table__
    cle = CreditLedgerEntry.__table__

    stmt = (
        select(
            func.count().label("total_records"),
            func.coalesce(func.sum(func.abs(cle.c.amount)), 0).label("total_credits"),
            func.count(func.distinct(bu.c.user_bid)).label("unique_users"),
            func.count(func.distinct(bu.c.progress_record_bid)).label(
                "unique_progress"
            ),
            # unique_wallets counts how many distinct wallets paid for this
            # shifu's runtime. Normally 1 (the course author's own wallet),
            # but subscription / sponsor / proxy-payment scenarios can split
            # it across multiple wallets. Per-row `wallet_creator_bid` shows
            # which wallet absorbed each charge; the summary intentionally
            # exposes only the count so callers do not treat a single
            # ``min(creator_bid)`` value as "the" wallet for the course
            # (raised on PR #1771 review).
            func.count(func.distinct(cle.c.creator_bid)).label("unique_wallets"),
            func.min(bu.c.created_at).label("first_at"),
            func.max(bu.c.created_at).label("last_at"),
        )
        .select_from(_join_conditions(params))
        .where(and_(*_where_clauses(params)))
    )
    return stmt


# ---------------------------------------------------------------------------
# Result shaping
# ---------------------------------------------------------------------------


def _row_to_dict(columns: Sequence[str], values: Sequence[Any]) -> Dict[str, Any]:
    row: Dict[str, Any] = {}
    for col, val in zip(columns, values):
        row[col] = _coerce_value(val)
    return row


def _summary_row_to_dict(summary_row: Any) -> Dict[str, Any]:
    if summary_row is None:
        return {
            "total_records": 0,
            "total_credits": 0,
            "unique_users": 0,
            "unique_progress": 0,
            "unique_wallets": 0,
            "time_range": [None, None],
        }
    mapping = summary_row._mapping  # noqa: SLF001 — SQLAlchemy public-ish API
    total_records = int(mapping.get("total_records") or 0)
    total_credits = _coerce_value(mapping.get("total_credits") or 0)
    unique_users = int(mapping.get("unique_users") or 0)
    unique_progress = int(mapping.get("unique_progress") or 0)
    unique_wallets = int(mapping.get("unique_wallets") or 0)
    first_at = _coerce_value(mapping.get("first_at"))
    last_at = _coerce_value(mapping.get("last_at"))
    return {
        "total_records": total_records,
        "total_credits": total_credits,
        "unique_users": unique_users,
        "unique_progress": unique_progress,
        "unique_wallets": unique_wallets,
        "time_range": [first_at, last_at],
    }


def _coerce_value(value: Any) -> Any:
    """Coerce non-JSON-friendly values (Decimal, datetime) to strings.

    The HTTP response wrapper turns the dict into JSON; SQLAlchemy returns
    ``Decimal`` for ``CREDIT_NUMERIC`` columns and ``datetime`` for timestamp
    columns. JSON serialization on either would raise; rendering as strings
    keeps the response stable and lets the CLI / frontend parse on demand.
    """

    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    # Decimal carries arbitrary precision; str() keeps the exact value the
    # billing ledger stored (avoids float rounding).
    try:
        from decimal import Decimal

        if isinstance(value, Decimal):
            return str(value)
    except ImportError:  # pragma: no cover - stdlib
        pass
    return value


# ---------------------------------------------------------------------------
# Error raising — keep the shape identical to dsl._raise
# ---------------------------------------------------------------------------


def _raise(error_name: str, detail: Optional[str] = None) -> None:
    message = _(error_name)
    if detail:
        message = f"{message} ({detail})"
    code = ERROR_CODE.get(error_name, ERROR_CODE.get("server.common.unknownError"))
    raise AppException(message, code)


__all__ = ["run", "ERR_NO_PERMISSION", "ERR_INVALID_DSL", "ERR_INVALID_LIMIT"]
