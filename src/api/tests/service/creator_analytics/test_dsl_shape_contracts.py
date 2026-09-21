"""Reject malformed analytics sections before composing any SQL."""

import pytest
from flaskr.service.creator_analytics import dsl

from tests.service.creator_analytics.test_dsl import _assert_error, _parse, _payload


@pytest.mark.parametrize(
    "overrides",
    [
        {"select": "status"},
        {"select": [1]},
        {"select": ["status", "status"]},
        {"group_by": "status"},
        {"group_by": ["status", "status"]},
        {"aggregate": {}},
        {"aggregate": [1]},
        {"where": {}},
        {"where": [1]},
        {"where": [{"field": 1, "op": "=", "value": 1}]},
        {"order_by": {}},
        {"order_by": [1]},
        {"where": [{"field": "status", "op": "is_null", "value": 1}]},
        {"where": [{"field": "status", "op": "in", "value": list(range(1001))}]},
        {"where": [{"field": "status", "op": "=", "value": {"nested": 1}}]},
        {"where": [{"field": "status", "op": "=", "value": None}]},
        {"where": [{"field": "outline_item_bid", "op": "like", "value": ""}]},
        {"where": [{"field": "outline_item_bid", "op": "like", "value": 1}]},
    ],
)
def test_malformed_query_sections_return_stable_validation_error(
    overrides: dict,
) -> None:
    _assert_error(_payload(**overrides), dsl.ERR_INVALID_DSL)


@pytest.mark.parametrize(
    "aggregate",
    [
        [{"fn": "count_distinct", "field": 1}],
        [{"fn": "sum", "field": "user_bid"}],
        [{"fn": "count", "alias": ""}],
        [{"fn": "count", "alias": 1}],
        [{"fn": "count", "alias": "2invalid"}],
        [{"fn": "count", "alias": "repeated"}, {"fn": "count", "alias": "repeated"}],
    ],
)
def test_invalid_aggregate_target_or_alias_is_rejected(aggregate: object) -> None:
    _assert_error(_payload(select=[], aggregate=aggregate), dsl.ERR_INVALID_AGGREGATE)


@pytest.mark.parametrize("offset", [True, 1.5, "1"])
def test_pagination_offset_requires_an_actual_integer(offset: object) -> None:
    _assert_error(_payload(offset=offset), dsl.ERR_INVALID_LIMIT)


def test_count_without_field_has_safe_default_alias_and_can_be_sorted() -> None:
    result = _parse(
        _payload(
            select=[], aggregate=[{"fn": "count"}], order_by=[{"field": "count_rows"}]
        )
    )
    assert result.aggregates == (
        dsl.Aggregate(fn="count", field=None, alias="count_rows", distinct=False),
    )
    assert result.order_by == (dsl.OrderBy(field="count_rows", direction="asc"),)
    assert result.output_columns == ("count_rows",)


@pytest.mark.parametrize(
    ("op", "value"),
    [("is_null", None), ("is_not_null", None), ("between", [1, 3])],
)
def test_null_and_range_filters_preserve_typed_predicates(
    op: str, value: object
) -> None:
    result = _parse(_payload(where=[{"field": "status", "op": op, "value": value}]))
    assert result.filters == (dsl.Filter(field="status", op=op, value=value),)


@pytest.mark.parametrize("table", ["shifu_published_shifus", "shifu_draft_shifus"])
@pytest.mark.parametrize("pattern", ["ab_cd", "ab%cd", "a%"])
def test_course_title_lookup_cannot_enumerate_with_short_or_internal_wildcards(
    table: str, pattern: str
) -> None:
    _assert_error(
        _payload(
            table=table,
            select=["title"],
            where=[{"field": "title", "op": "like", "value": pattern}],
        ),
        dsl.ERR_INVALID_DSL,
    )


@pytest.mark.parametrize("table", ["shifu_published_shifus", "shifu_draft_shifus"])
def test_course_metadata_does_not_allow_aggregate_counts(table: str) -> None:
    _assert_error(
        _payload(table=table, select=[], aggregate=[{"fn": "count"}]),
        dsl.ERR_INVALID_DSL,
    )


def test_nonaggregatable_status_column_is_rejected_with_column_error() -> None:
    _assert_error(
        _payload(select=[], aggregate=[{"fn": "sum", "field": "status"}]),
        dsl.ERR_INVALID_COLUMN,
    )


def test_learner_ids_are_allowed_when_each_row_is_a_grouped_aggregate() -> None:
    result = _parse(
        _payload(
            select=["user_bid"],
            group_by=["user_bid"],
            aggregate=[{"fn": "count"}],
        )
    )
    assert result.select == ("user_bid",)
    assert result.group_by == ("user_bid",)
    assert result.output_columns == ("user_bid", "count_rows")
