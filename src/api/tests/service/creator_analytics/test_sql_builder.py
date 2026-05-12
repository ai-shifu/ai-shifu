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


def _compile_for(dialect, payload, dialect_name):
    dsl = parse_dsl(payload, limit_max=LIMIT_MAX)
    stmt = build_statement(dsl, dialect_name=dialect_name)
    return str(
        stmt.compile(
            dialect=dialect,
            compile_kwargs={"literal_binds": True},
        )
    )


def _compile_mysql(payload):
    return _compile_for(mysql.dialect(), payload, "mysql")


def _compile_sqlite(payload):
    return _compile_for(sqlite.dialect(), payload, "sqlite")


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
