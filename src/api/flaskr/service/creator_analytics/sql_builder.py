"""SQLAlchemy Core statement builder for creator-analytics DSL.

The builder never accepts raw user strings into the SQL text — every column
and operator passes through the whitelist enforced by
:mod:`flaskr.service.creator_analytics.dsl`, and every value is bound via
SQLAlchemy bindparam. Four cross-cutting predicates are applied automatically,
driven by :class:`flaskr.service.creator_analytics.whitelist.TableSpec` flags:

1. ``WHERE shifu_bid = :shifu_bid`` when ``has_shifu_bid`` is True — callers
   cannot widen the scope to courses they do not own.
2. ``AND deleted = 0`` when ``has_deleted`` is True — soft-deleted rows stay
   hidden.
3. ``AND <creator_scoped_column> = :__user_id`` when ``creator_scoped_column``
   is non-None — row ownership is enforced on top of the shifu-scope check.
   Used by the shifu metadata tables so co-authors cannot read author-only
   title rows even when they have query permission for the shifu.
4. ``AND status = 1`` when ``auto_filter_status_active`` is True — used by
   ``learn_generated_blocks`` to drop rerolled history (``status = 0``) from
   every result, so creator counts reflect the current learner experience.

The MySQL ``MAX_EXECUTION_TIME`` optimizer hint is injected only when the
target dialect is MySQL — under SQLite (tests) the hint would not parse.
"""

from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import (
    Column,
    and_,
    bindparam,
    func,
    select,
)
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ColumnElement

from .dsl import Aggregate, Filter, OrderBy, QueryDSL


def build_statement(
    dsl: QueryDSL,
    dialect_name: str,
    query_timeout_seconds: int = 15,
) -> Select:
    """Compile ``dsl`` to a SQLAlchemy :class:`Select` statement.

    ``dialect_name`` should be the value of ``engine.dialect.name`` (for
    example ``"mysql"`` or ``"sqlite"``).  ``query_timeout_seconds`` only
    affects MySQL execution via the ``MAX_EXECUTION_TIME`` hint.
    """

    table = dsl.spec.model.__table__

    select_items: list[ColumnElement[Any]] = []
    for col_name in dsl.select:
        select_items.append(table.c[col_name].label(col_name))
    for agg in dsl.aggregates:
        select_items.append(_compile_aggregate(table, agg))

    stmt = select(*select_items).select_from(table)

    where_clauses: list[ColumnElement[bool]] = []
    if dsl.spec.has_shifu_bid:
        # Shifu-scoped tables: the requested shifu_bid is enforced server-side
        # regardless of what the caller wrote in `where`. Tables without a
        # shifu_bid column (e.g. user_users) rely on funcs.run_dsl for the
        # permission check plus DSL-level guards (mandatory where user_bid,
        # capped limit, PII redaction).
        where_clauses.append(
            table.c.shifu_bid == bindparam("__shifu_bid", value=dsl.shifu_bid)
        )
    if dsl.spec.has_deleted:
        where_clauses.append(table.c.deleted == 0)
    if dsl.spec.creator_scoped_column:
        # Row-ownership enforcement on top of the shifu permission check in
        # funcs.run_dsl. The caller_user_id must be threaded through by the
        # entry point; if it is missing here we refuse to compile rather than
        # silently emit a WHERE col = '' clause that would always match
        # legacy rows whose creator field is empty.
        if not dsl.caller_user_id:
            raise ValueError(
                f"caller_user_id is required for creator-scoped table "
                f"'{dsl.spec.table_key}'"
            )
        where_clauses.append(
            table.c[dsl.spec.creator_scoped_column]
            == bindparam("__user_id", value=dsl.caller_user_id)
        )
    if dsl.spec.auto_filter_status_active:
        where_clauses.append(table.c.status == 1)

    for index, filt in enumerate(dsl.filters):
        where_clauses.append(_compile_filter(table.c[filt.field], filt, index))

    if where_clauses:
        stmt = stmt.where(and_(*where_clauses))

    if dsl.group_by:
        stmt = stmt.group_by(*[table.c[col] for col in dsl.group_by])

    if dsl.order_by:
        stmt = stmt.order_by(*_compile_order_by(table, dsl.order_by, dsl.aggregates))

    stmt = stmt.limit(dsl.limit).offset(dsl.offset)

    if dialect_name == "mysql" and query_timeout_seconds > 0:
        # MAX_EXECUTION_TIME accepts milliseconds.
        timeout_ms = max(1, int(query_timeout_seconds * 1000))
        stmt = stmt.prefix_with(
            f"/*+ MAX_EXECUTION_TIME({timeout_ms}) */",
            dialect="mysql",
        )

    return stmt


# ---------------------------------------------------------------------------
# Compilation helpers
# ---------------------------------------------------------------------------


def _compile_filter(column: Column, filt: Filter, index: int) -> ColumnElement[bool]:
    op = filt.op
    value = filt.value
    base_name = f"__where_{index}_{filt.field}"

    if op == "=":
        return column == bindparam(base_name, value=value)
    if op == "!=":
        return column != bindparam(base_name, value=value)
    if op == ">":
        return column > bindparam(base_name, value=value)
    if op == ">=":
        return column >= bindparam(base_name, value=value)
    if op == "<":
        return column < bindparam(base_name, value=value)
    if op == "<=":
        return column <= bindparam(base_name, value=value)
    if op == "in":
        return column.in_(value)
    if op == "not_in":
        return column.notin_(value)
    if op == "between":
        low, high = value
        return column.between(
            bindparam(f"{base_name}_lo", value=low),
            bindparam(f"{base_name}_hi", value=high),
        )
    if op == "like":
        # DSL has already rejected leading-% patterns.
        return column.like(bindparam(base_name, value=value))
    if op == "is_null":
        return column.is_(None)
    if op == "is_not_null":
        return column.isnot(None)

    raise ValueError(f"Unexpected DSL operator at sql_builder: {op!r}")


def _compile_aggregate(table, agg: Aggregate) -> ColumnElement[Any]:
    if agg.fn == "count":
        if agg.field is None:
            expr = func.count()
        else:
            target = table.c[agg.field]
            expr = func.count(target.distinct()) if agg.distinct else func.count(target)
    elif agg.fn == "count_distinct":
        target = table.c[agg.field]
        expr = func.count(target.distinct())
    elif agg.fn == "sum":
        expr = func.sum(table.c[agg.field])
    elif agg.fn == "avg":
        expr = func.avg(table.c[agg.field])
    elif agg.fn == "min":
        expr = func.min(table.c[agg.field])
    elif agg.fn == "max":
        expr = func.max(table.c[agg.field])
    else:
        raise ValueError(f"Unexpected aggregate fn at sql_builder: {agg.fn!r}")
    return expr.label(agg.alias)


def _compile_order_by(
    table,
    order_by: Sequence[OrderBy],
    aggregates: Sequence[Aggregate],
) -> list[ColumnElement[Any]]:
    aggregate_aliases = {agg.alias for agg in aggregates}
    compiled: list[ColumnElement[Any]] = []
    for item in order_by:
        if item.field in aggregate_aliases:
            target: ColumnElement[Any] = _aggregate_expression_by_alias(
                table, aggregates, item.field
            )
        else:
            target = table.c[item.field]
        compiled.append(target.desc() if item.direction == "desc" else target.asc())
    return compiled


def _aggregate_expression_by_alias(
    table, aggregates: Sequence[Aggregate], alias: str
) -> ColumnElement[Any]:
    for agg in aggregates:
        if agg.alias == alias:
            return _compile_aggregate(table, agg)
    raise ValueError(f"Unknown aggregate alias: {alias!r}")
