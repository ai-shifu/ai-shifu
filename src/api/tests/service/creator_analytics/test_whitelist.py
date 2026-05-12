"""Whitelist sanity tests for creator-analytics.

These exercise the static metadata only — no DB, no Flask app.
"""

from __future__ import annotations

import pytest

from flaskr.service.creator_analytics.whitelist import (
    ALLOWED_AGGREGATE_FUNCTIONS,
    ALLOWED_OPERATORS,
    WHITELIST,
    TableSpec,
    get_table_spec,
)


EXPECTED_TABLE_KEYS = {
    "learn_progress_records",
    "learn_generated_blocks",
    "learn_lesson_feedbacks",
    "order_orders",
    "var_variable_values",
    "bill_usage",
    "shifu_user_archives",
    "user_users",
}

# Tables whose rows are shifu-scoped (sql_builder injects WHERE shifu_bid=:sb).
# user_users is global and gated by funcs.run_dsl permission check instead.
SHIFU_SCOPED_TABLE_KEYS = EXPECTED_TABLE_KEYS - {"user_users"}


def test_whitelist_covers_expected_tables() -> None:
    assert set(WHITELIST.keys()) == EXPECTED_TABLE_KEYS


@pytest.mark.parametrize("table_key", sorted(EXPECTED_TABLE_KEYS))
def test_every_declared_column_exists_on_the_model(table_key: str) -> None:
    spec = WHITELIST[table_key]
    table = spec.model.__table__
    available = set(table.c.keys())
    declared = (
        spec.selectable
        | spec.filterable
        | spec.groupable
        | set(spec.aggregatable.keys())
    )
    missing = declared - available
    assert not missing, f"{table_key}: declared columns missing on the model: {missing}"


@pytest.mark.parametrize("table_key", sorted(EXPECTED_TABLE_KEYS))
def test_filterable_and_groupable_subset_of_selectable(table_key: str) -> None:
    spec = WHITELIST[table_key]
    assert spec.filterable <= spec.selectable
    assert spec.groupable <= spec.selectable


@pytest.mark.parametrize("table_key", sorted(EXPECTED_TABLE_KEYS))
def test_aggregate_functions_are_allowed(table_key: str) -> None:
    spec = WHITELIST[table_key]
    for field, fns in spec.aggregatable.items():
        bad = fns - ALLOWED_AGGREGATE_FUNCTIONS
        assert not bad, f"{table_key}.{field}: disallowed aggregate fns {bad}"


def test_shifu_user_archives_has_no_deleted_column() -> None:
    spec = WHITELIST["shifu_user_archives"]
    assert spec.has_deleted is False
    assert "deleted" not in spec.model.__table__.c.keys()


@pytest.mark.parametrize(
    "table_key",
    sorted(EXPECTED_TABLE_KEYS - {"shifu_user_archives"}),
)
def test_other_tables_have_deleted_column(table_key: str) -> None:
    spec = WHITELIST[table_key]
    assert spec.has_deleted is True
    assert "deleted" in spec.model.__table__.c.keys()


@pytest.mark.parametrize("table_key", sorted(SHIFU_SCOPED_TABLE_KEYS))
def test_shifu_scoped_tables_have_shifu_bid_column(table_key: str) -> None:
    spec = WHITELIST[table_key]
    assert spec.has_shifu_bid is True
    assert "shifu_bid" in spec.model.__table__.c.keys(), (
        f"{table_key} declares has_shifu_bid=True but the column is missing"
    )


def test_user_users_is_global_table() -> None:
    """user_users has no shifu_bid column; gated by permission check instead."""

    spec = WHITELIST["user_users"]
    assert spec.has_shifu_bid is False
    assert "shifu_bid" not in spec.model.__table__.c.keys()


def test_shifu_bid_and_deleted_are_never_user_addressable() -> None:
    """The DSL must never let callers reference these — they are injected."""

    for spec in WHITELIST.values():
        assert "shifu_bid" not in spec.selectable
        assert "shifu_bid" not in spec.filterable
        assert "shifu_bid" not in spec.groupable
        assert "shifu_bid" not in spec.aggregatable
        assert "deleted" not in spec.selectable
        assert "deleted" not in spec.filterable
        assert "deleted" not in spec.groupable
        assert "deleted" not in spec.aggregatable


def test_get_table_spec_returns_typed_instance() -> None:
    spec = get_table_spec("order_orders")
    assert isinstance(spec, TableSpec)
    assert spec.table_key == "order_orders"


@pytest.mark.parametrize("table_key", sorted(SHIFU_SCOPED_TABLE_KEYS))
def test_user_bid_is_groupable_on_every_shifu_scoped_table(table_key: str) -> None:
    """user_bid is groupable on the 7 shifu-scoped tables — per-learner aggregation."""

    spec = WHITELIST[table_key]
    assert "user_bid" in spec.groupable, (
        f"{table_key}: user_bid must be groupable for per-learner aggregation"
    )


def test_user_users_does_not_allow_group_by_or_aggregation() -> None:
    """user_users is restricted to plain lookups — no group_by, no aggregation."""

    spec = WHITELIST["user_users"]
    assert spec.groupable == frozenset()
    assert spec.aggregatable == {}


def test_operators_baseline() -> None:
    """Pin the operator set so regressions are deliberate."""

    assert "=" in ALLOWED_OPERATORS
    assert "in" in ALLOWED_OPERATORS
    assert "between" in ALLOWED_OPERATORS
    assert "like" in ALLOWED_OPERATORS
    assert "is_null" in ALLOWED_OPERATORS
    assert "join" not in ALLOWED_OPERATORS
