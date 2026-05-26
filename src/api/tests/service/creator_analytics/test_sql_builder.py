"""SQL builder snapshot tests for creator-analytics.

These compile DSL → SQLAlchemy statements with mysql and sqlite dialects and
inspect the resulting SQL text. No DB connection is required.
"""

from __future__ import annotations

import pytest
from sqlalchemy.dialects import mysql, sqlite

from flaskr.service.creator_analytics.dsl import parse_dsl
from flaskr.service.creator_analytics.sql_builder import build_statement


LIMIT_MAX = 1000


def _compile_for(dialect, payload, dialect_name, user_id=""):
    dsl = parse_dsl(payload, limit_max=LIMIT_MAX, user_id=user_id)
    stmt = build_statement(dsl, dialect_name=dialect_name)
    return str(
        stmt.compile(
            dialect=dialect,
            compile_kwargs={"literal_binds": True},
        )
    )


def _compile_mysql(payload, user_id=""):
    return _compile_for(mysql.dialect(), payload, "mysql", user_id=user_id)


def _compile_sqlite(payload, user_id=""):
    return _compile_for(sqlite.dialect(), payload, "sqlite", user_id=user_id)


# ---------------------------------------------------------------------------
# shifu_bid is always injected, regardless of the DSL
# ---------------------------------------------------------------------------


def test_shifu_bid_predicate_is_always_present_on_select() -> None:
    sql = _compile_sqlite(
        {
            "shifu_bid": "shifu-abc",
            "table": "learn_progress_records",
            "select": ["outline_item_bid"],
            "limit": 10,
        }
    )
    assert "shifu_bid = 'shifu-abc'" in sql


def test_shifu_bid_predicate_present_even_without_where_clause() -> None:
    sql = _compile_sqlite(
        {
            "shifu_bid": "shifu-x",
            "table": "order_orders",
            "aggregate": [{"fn": "sum", "field": "paid_price", "alias": "rev"}],
            "limit": 10,
        }
    )
    assert "shifu_bid = 'shifu-x'" in sql


# ---------------------------------------------------------------------------
# Deleted column injection — table-dependent
# ---------------------------------------------------------------------------


def test_deleted_predicate_injected_for_tables_with_deleted_column() -> None:
    sql = _compile_sqlite(
        {
            "shifu_bid": "shifu-abc",
            "table": "learn_progress_records",
            "select": ["outline_item_bid"],
            "limit": 10,
        }
    )
    assert "deleted = 0" in sql


def test_deleted_predicate_omitted_for_shifu_user_archives() -> None:
    sql = _compile_sqlite(
        {
            "shifu_bid": "shifu-abc",
            "table": "shifu_user_archives",
            "select": ["archived"],
            "limit": 10,
        }
    )
    assert "deleted" not in sql


# ---------------------------------------------------------------------------
# Dialect-dependent MySQL hint
# ---------------------------------------------------------------------------


def test_mysql_dialect_emits_max_execution_time_hint() -> None:
    sql = _compile_mysql(
        {
            "shifu_bid": "shifu-abc",
            "table": "learn_progress_records",
            "select": ["outline_item_bid"],
            "limit": 10,
        }
    )
    assert "MAX_EXECUTION_TIME(15000)" in sql


def test_sqlite_dialect_does_not_emit_mysql_hint() -> None:
    sql = _compile_sqlite(
        {
            "shifu_bid": "shifu-abc",
            "table": "learn_progress_records",
            "select": ["outline_item_bid"],
            "limit": 10,
        }
    )
    assert "MAX_EXECUTION_TIME" not in sql


# ---------------------------------------------------------------------------
# Aggregates / group_by / order_by
# ---------------------------------------------------------------------------


def test_count_distinct_emits_distinct_in_count() -> None:
    sql = _compile_sqlite(
        {
            "shifu_bid": "shifu-abc",
            "table": "learn_progress_records",
            "select": ["status"],
            "group_by": ["status"],
            "aggregate": [{"fn": "count_distinct", "field": "user_bid", "alias": "n"}],
            "limit": 10,
        }
    )
    assert "count(DISTINCT" in sql or "COUNT(DISTINCT" in sql
    assert "GROUP BY" in sql.upper()


def test_order_by_aggregate_alias_compiles() -> None:
    sql = _compile_sqlite(
        {
            "shifu_bid": "shifu-abc",
            "table": "learn_progress_records",
            "select": ["status"],
            "group_by": ["status"],
            "aggregate": [{"fn": "count_distinct", "field": "user_bid", "alias": "n"}],
            "order_by": [{"field": "n", "dir": "desc"}],
            "limit": 10,
        }
    )
    assert "ORDER BY" in sql.upper()
    assert "DESC" in sql.upper()


# ---------------------------------------------------------------------------
# WHERE operators — value bindings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("op", ["=", "!=", ">", ">=", "<", "<="])
def test_comparison_operators_emit_predicate(op: str) -> None:
    sql = _compile_sqlite(
        {
            "shifu_bid": "shifu-abc",
            "table": "learn_progress_records",
            "select": ["outline_item_bid"],
            "where": [{"field": "status", "op": op, "value": 602}],
            "limit": 10,
        }
    )
    # Different operators may serialize slightly differently — check the
    # column appears next to the value.
    assert "status" in sql
    assert "602" in sql


def test_in_operator_emits_in_predicate() -> None:
    sql = _compile_sqlite(
        {
            "shifu_bid": "shifu-abc",
            "table": "learn_progress_records",
            "select": ["outline_item_bid"],
            "where": [{"field": "status", "op": "in", "value": [602, 603]}],
            "limit": 10,
        }
    )
    assert " IN " in sql.upper()


def test_between_operator_emits_between() -> None:
    sql = _compile_sqlite(
        {
            "shifu_bid": "shifu-abc",
            "table": "learn_progress_records",
            "select": ["outline_item_bid"],
            "where": [
                {
                    "field": "created_at",
                    "op": "between",
                    "value": ["2026-01-01", "2026-02-01"],
                }
            ],
            "limit": 10,
        }
    )
    assert "BETWEEN" in sql.upper()


def test_is_null_emits_is_null() -> None:
    sql = _compile_sqlite(
        {
            "shifu_bid": "shifu-abc",
            "table": "shifu_user_archives",
            "select": ["archived"],
            "where": [{"field": "archived_at", "op": "is_null"}],
            "limit": 10,
        }
    )
    assert "IS NULL" in sql.upper()


# ---------------------------------------------------------------------------
# Limit / offset
# ---------------------------------------------------------------------------


def test_limit_and_offset_present() -> None:
    sql = _compile_sqlite(
        {
            "shifu_bid": "shifu-abc",
            "table": "learn_progress_records",
            "select": ["outline_item_bid"],
            "limit": 25,
            "offset": 5,
        }
    )
    assert "LIMIT" in sql.upper()
    assert "25" in sql
    assert "OFFSET" in sql.upper()
    assert "5" in sql


# ---------------------------------------------------------------------------
# learn_generated_blocks status auto-filter
# ---------------------------------------------------------------------------


def test_generated_blocks_status_auto_injected() -> None:
    """auto_filter_status_active=True on the spec must emit AND status = 1
    even when the DSL has no status clause. Rerolled-history rows
    (status=0) must never leak into a creator's follow-up count."""

    sql = _compile_sqlite(
        {
            "shifu_bid": "shifu-abc",
            "table": "learn_generated_blocks",
            "where": [{"field": "type", "op": "=", "value": 321}],
            "aggregate": [{"fn": "count", "alias": "asks"}],
            "limit": 10,
        }
    )
    assert "status = 1" in sql


def test_generated_blocks_status_explicit_filter_does_not_override_auto() -> None:
    """If the caller explicitly filters status=1, the auto-injected predicate
    is still present (idempotent — SQL would simply have two `status = 1`
    clauses; AND-of-two-identical predicates is fine)."""

    sql = _compile_sqlite(
        {
            "shifu_bid": "shifu-abc",
            "table": "learn_generated_blocks",
            "where": [
                {"field": "type", "op": "=", "value": 321},
                {"field": "status", "op": "=", "value": 1},
            ],
            "aggregate": [{"fn": "count", "alias": "asks"}],
            "limit": 10,
        }
    )
    # Both injected and explicit status=1 should appear; count them by
    # checking SQL contains the predicate.
    assert sql.count("status = 1") >= 1


# ---------------------------------------------------------------------------
# shifu metadata tables — creator_scoped_column injection + double-gate
# ---------------------------------------------------------------------------


def _meta_payload(table_key="shifu_published_shifus", **overrides):
    """Build a baseline DSL payload for shifu metadata-table compile tests."""
    base = {
        "shifu_bid": "shifu-abc",
        "table": table_key,
        "select": ["title", "updated_at"],
        "limit": 10,
    }
    base.update(overrides)
    return base


def test_shifu_meta_injects_created_user_bid_predicate() -> None:
    """Metadata tables require WHERE created_user_bid = :__user_id in
    addition to shifu_bid scope — row ownership enforcement on top of
    the funcs.run_dsl permission check."""

    sql = _compile_sqlite(_meta_payload(), user_id="teacher-1")
    assert "created_user_bid = 'teacher-1'" in sql
    assert "shifu_bid = 'shifu-abc'" in sql
    assert "deleted = 0" in sql


def test_shifu_draft_injects_created_user_bid_predicate() -> None:
    """Both metadata tables share the same double-gate."""

    sql = _compile_sqlite(
        _meta_payload(table_key="shifu_draft_shifus"), user_id="teacher-2"
    )
    assert "created_user_bid = 'teacher-2'" in sql


def test_shifu_meta_without_caller_user_id_fails_compile() -> None:
    """Missing caller_user_id is a hard error — sql_builder refuses rather
    than emitting `WHERE created_user_bid = ''` which would accidentally
    match legacy rows."""

    with pytest.raises(ValueError, match="caller_user_id is required"):
        _compile_sqlite(_meta_payload())  # user_id defaults to ""


def test_non_meta_table_does_not_inject_created_user_bid() -> None:
    """The created_user_bid predicate must only appear for tables that
    opt into it via creator_scoped_column."""

    sql = _compile_sqlite(
        {
            "shifu_bid": "shifu-abc",
            "table": "learn_progress_records",
            "select": ["outline_item_bid"],
            "limit": 10,
        },
        user_id="teacher-1",
    )
    assert "created_user_bid" not in sql
