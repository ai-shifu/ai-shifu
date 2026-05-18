"""Unit tests for the creator-analytics DSL parser/validator.

Pure in-memory tests — no DB, no Flask app context.
"""

from __future__ import annotations

import pytest

from flaskr.service.common.models import AppException, ERROR_CODE
from flaskr.service.creator_analytics.dsl import (
    ERR_INVALID_AGGREGATE,
    ERR_INVALID_COLUMN,
    ERR_INVALID_DSL,
    ERR_INVALID_LIMIT,
    ERR_INVALID_OPERATOR,
    ERR_INVALID_TABLE,
    parse_dsl,
)


DEFAULT_LIMIT_MAX = 1000


def _payload(**overrides):
    base = {
        "shifu_bid": "shifu-abc",
        "table": "learn_progress_records",
        "select": ["outline_item_bid", "status"],
        "limit": 10,
    }
    base.update(overrides)
    return base


def _parse(payload):
    return parse_dsl(payload, limit_max=DEFAULT_LIMIT_MAX)


def _assert_error(payload, error_name: str) -> None:
    with pytest.raises(AppException) as excinfo:
        _parse(payload)
    # Match by error code so the assertion holds regardless of whether i18n
    # is initialized (the localized message differs by locale).
    expected_code = ERROR_CODE.get(error_name)
    assert expected_code is not None, f"Unknown error name in test: {error_name}"
    assert excinfo.value.code == expected_code, (
        f"Expected error code for {error_name} ({expected_code}), "
        f"got code={excinfo.value.code} message={excinfo.value.message!r}"
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_minimal_select_query_parses() -> None:
    dsl = _parse(_payload())
    assert dsl.shifu_bid == "shifu-abc"
    assert dsl.table == "learn_progress_records"
    assert dsl.select == ("outline_item_bid", "status")
    assert dsl.aggregates == ()
    assert dsl.limit == 10
    assert dsl.offset == 0


def test_group_by_with_aggregate_parses() -> None:
    payload = _payload(
        select=["status"],
        group_by=["status"],
        aggregate=[{"fn": "count_distinct", "field": "user_bid", "alias": "n"}],
    )
    dsl = _parse(payload)
    assert dsl.aggregates[0].fn == "count_distinct"
    assert dsl.aggregates[0].distinct is True
    assert dsl.aggregates[0].alias == "n"
    assert dsl.output_columns == ("status", "n")


def test_aggregate_only_query_parses_without_select() -> None:
    payload = {
        "shifu_bid": "shifu-abc",
        "table": "order_orders",
        "aggregate": [
            {"fn": "sum", "field": "paid_price", "alias": "revenue"},
            {"fn": "count", "field": "order_bid", "alias": "orders"},
        ],
        "limit": 10,
    }
    dsl = _parse(payload)
    assert dsl.select == ()
    assert {a.alias for a in dsl.aggregates} == {"revenue", "orders"}


def test_where_in_with_list_parses() -> None:
    payload = _payload(
        where=[{"field": "status", "op": "in", "value": [602, 603]}],
    )
    dsl = _parse(payload)
    assert dsl.filters[0].op == "in"
    assert dsl.filters[0].value == [602, 603]


def test_order_by_aggregate_alias_parses() -> None:
    payload = _payload(
        select=["status"],
        group_by=["status"],
        aggregate=[{"fn": "count_distinct", "field": "user_bid", "alias": "n"}],
        order_by=[{"field": "n", "dir": "desc"}],
    )
    dsl = _parse(payload)
    assert dsl.order_by[0].field == "n"
    assert dsl.order_by[0].direction == "desc"


def test_shifu_user_archives_works_without_deleted_column() -> None:
    payload = {
        "shifu_bid": "shifu-abc",
        "table": "shifu_user_archives",
        "select": ["archived"],
        "where": [{"field": "archived", "op": "=", "value": 0}],
        "limit": 10,
    }
    dsl = _parse(payload)
    assert dsl.spec.has_deleted is False


# ---------------------------------------------------------------------------
# Negative path — shape / required fields
# ---------------------------------------------------------------------------


def test_payload_must_be_object() -> None:
    _assert_error([], ERR_INVALID_DSL)


def test_missing_shifu_bid_rejected() -> None:
    payload = _payload()
    del payload["shifu_bid"]
    _assert_error(payload, ERR_INVALID_DSL)


def test_empty_shifu_bid_rejected() -> None:
    _assert_error(_payload(shifu_bid=""), ERR_INVALID_DSL)


def test_missing_table_rejected() -> None:
    payload = _payload()
    del payload["table"]
    _assert_error(payload, ERR_INVALID_TABLE)


def test_unknown_table_rejected() -> None:
    # user_users is now in the whitelist; pick a name that definitely is not.
    _assert_error(_payload(table="auth_logs"), ERR_INVALID_TABLE)


def test_empty_select_and_aggregate_rejected() -> None:
    payload = _payload()
    del payload["select"]
    _assert_error(payload, ERR_INVALID_DSL)


def test_select_star_rejected() -> None:
    _assert_error(_payload(select=["*"]), ERR_INVALID_DSL)


def test_select_unknown_column_rejected() -> None:
    _assert_error(_payload(select=["definitely_not_a_column"]), ERR_INVALID_COLUMN)


def test_select_shifu_bid_rejected() -> None:
    # shifu_bid is injected, callers must never reference it
    _assert_error(_payload(select=["shifu_bid"]), ERR_INVALID_COLUMN)


def test_select_deleted_rejected() -> None:
    _assert_error(_payload(select=["deleted"]), ERR_INVALID_COLUMN)


# ---------------------------------------------------------------------------
# Negative path — where / operators
# ---------------------------------------------------------------------------


def test_where_unknown_op_rejected() -> None:
    payload = _payload(
        where=[{"field": "status", "op": "JOIN", "value": 1}],
    )
    _assert_error(payload, ERR_INVALID_OPERATOR)


def test_where_in_requires_list() -> None:
    payload = _payload(where=[{"field": "status", "op": "in", "value": 602}])
    _assert_error(payload, ERR_INVALID_DSL)


def test_where_between_requires_two_values() -> None:
    payload = _payload(
        where=[{"field": "created_at", "op": "between", "value": ["2026-01-01"]}],
    )
    _assert_error(payload, ERR_INVALID_DSL)


def test_where_like_rejects_leading_wildcard() -> None:
    payload = _payload(
        select=["user_bid"],
        where=[{"field": "user_bid", "op": "like", "value": "%abc"}],
    )
    _assert_error(payload, ERR_INVALID_DSL)


def test_where_is_null_requires_no_value() -> None:
    payload = _payload(
        where=[{"field": "status", "op": "is_null", "value": "something"}],
    )
    _assert_error(payload, ERR_INVALID_DSL)


def test_where_unknown_field_rejected() -> None:
    payload = _payload(
        where=[{"field": "shifu_bid", "op": "=", "value": "x"}],
    )
    _assert_error(payload, ERR_INVALID_COLUMN)


# ---------------------------------------------------------------------------
# Negative path — aggregates
# ---------------------------------------------------------------------------


def test_aggregate_unknown_fn_rejected() -> None:
    payload = _payload(
        select=["status"],
        group_by=["status"],
        aggregate=[{"fn": "median", "field": "user_bid", "alias": "n"}],
    )
    _assert_error(payload, ERR_INVALID_AGGREGATE)


def test_aggregate_field_required_for_non_count() -> None:
    payload = _payload(
        select=["status"],
        group_by=["status"],
        aggregate=[{"fn": "sum", "alias": "n"}],
    )
    _assert_error(payload, ERR_INVALID_AGGREGATE)


def test_aggregate_sum_on_non_numeric_rejected() -> None:
    payload = _payload(
        select=["status"],
        group_by=["status"],
        aggregate=[{"fn": "sum", "field": "user_bid", "alias": "x"}],
    )
    _assert_error(payload, ERR_INVALID_AGGREGATE)


def test_aggregate_duplicate_alias_rejected() -> None:
    payload = _payload(
        select=["status"],
        group_by=["status"],
        aggregate=[
            {"fn": "count_distinct", "field": "user_bid", "alias": "n"},
            {"fn": "count", "field": "progress_record_bid", "alias": "n"},
        ],
    )
    _assert_error(payload, ERR_INVALID_AGGREGATE)


def test_aggregate_bad_alias_rejected() -> None:
    payload = _payload(
        select=["status"],
        group_by=["status"],
        aggregate=[
            {"fn": "count_distinct", "field": "user_bid", "alias": "bad alias!"},
        ],
    )
    _assert_error(payload, ERR_INVALID_AGGREGATE)


def test_plain_select_must_appear_in_group_by_when_aggregating() -> None:
    payload = _payload(
        select=["user_bid", "status"],
        group_by=["status"],
        aggregate=[{"fn": "count_distinct", "field": "user_bid", "alias": "n"}],
    )
    _assert_error(payload, ERR_INVALID_DSL)


# ---------------------------------------------------------------------------
# Negative path — limit / offset
# ---------------------------------------------------------------------------


def test_limit_above_max_rejected() -> None:
    _assert_error(_payload(limit=DEFAULT_LIMIT_MAX + 1), ERR_INVALID_LIMIT)


def test_limit_zero_rejected() -> None:
    _assert_error(_payload(limit=0), ERR_INVALID_LIMIT)


def test_limit_not_integer_rejected() -> None:
    _assert_error(_payload(limit="10"), ERR_INVALID_LIMIT)


def test_offset_negative_rejected() -> None:
    _assert_error(_payload(offset=-1), ERR_INVALID_LIMIT)


# ---------------------------------------------------------------------------
# Negative path — order_by
# ---------------------------------------------------------------------------


def test_order_by_field_must_appear_in_select_or_alias() -> None:
    payload = _payload(
        select=["outline_item_bid"],
        order_by=[{"field": "status", "dir": "asc"}],
    )
    _assert_error(payload, ERR_INVALID_COLUMN)


def test_order_by_invalid_direction_rejected() -> None:
    payload = _payload(order_by=[{"field": "user_bid", "dir": "sideways"}])
    _assert_error(payload, ERR_INVALID_DSL)


# ---------------------------------------------------------------------------
# user_bid aggregation-only guard (per-learner analytics policy)
# ---------------------------------------------------------------------------


def test_count_distinct_user_bid_without_selecting_it_parses() -> None:
    """count_distinct(user_bid) — user_bid as aggregate target only — still works."""

    payload = _payload(
        select=["status"],
        group_by=["status"],
        aggregate=[{"fn": "count_distinct", "field": "user_bid", "alias": "n"}],
    )
    dsl = _parse(payload)
    assert "user_bid" not in dsl.select


def test_select_user_bid_without_group_by_user_bid_is_rejected() -> None:
    """Raw learner pseudo-ID listing must be blocked."""

    payload = {
        "shifu_bid": "shifu-abc",
        "table": "order_orders",
        "select": ["user_bid", "status", "paid_price"],
        "limit": 100,
    }
    _assert_error(payload, ERR_INVALID_DSL)


def test_select_user_bid_with_group_by_other_dimension_is_rejected() -> None:
    """select user_bid + group_by status — caught by the existing select-in-group-by rule.

    Documented here for clarity: the user_bid guard piggy-backs on the existing
    rule for the aggregate path, but we still want the surface behavior captured.
    """

    payload = _payload(
        select=["user_bid", "status"],
        group_by=["status"],
        aggregate=[{"fn": "count", "alias": "n"}],
    )
    _assert_error(payload, ERR_INVALID_DSL)


# ---------------------------------------------------------------------------
# generated_content access policy (conversation detail)
# ---------------------------------------------------------------------------


def _content_payload(**overrides):
    base = {
        "shifu_bid": "shifu-abc",
        "table": "learn_generated_blocks",
        "select": ["user_bid", "generated_content", "created_at"],
        "where": [{"field": "type", "op": "in", "value": [321, 322]}],
        "order_by": [{"field": "created_at", "dir": "asc"}],
        "limit": 50,
    }
    base.update(overrides)
    return base


def test_conversation_replay_parses() -> None:
    """user_bid + generated_content + safe type filter — the happy path."""

    dsl = _parse(_content_payload())
    assert "user_bid" in dsl.select
    assert "generated_content" in dsl.select
    assert dsl.limit == 50


def test_generated_content_without_type_filter_is_rejected() -> None:
    payload = _content_payload(where=[])
    _assert_error(payload, ERR_INVALID_DSL)


def test_generated_content_with_disallowed_type_is_rejected() -> None:
    """type=303 (input) holds learner free-form text → not allowed."""

    payload = _content_payload(
        where=[{"field": "type", "op": "=", "value": 303}],
    )
    _assert_error(payload, ERR_INVALID_DSL)


def test_generated_content_with_partial_disallowed_type_in_list_is_rejected() -> None:
    """One disallowed type in an `in` list taints the whole query."""

    payload = _content_payload(
        where=[{"field": "type", "op": "in", "value": [321, 309]}],
    )
    _assert_error(payload, ERR_INVALID_DSL)


def test_generated_content_with_unsupported_type_operator_is_rejected() -> None:
    payload = _content_payload(
        where=[{"field": "type", "op": ">=", "value": 321}],
    )
    _assert_error(payload, ERR_INVALID_DSL)


def test_generated_content_limit_above_100_is_rejected() -> None:
    payload = _content_payload(limit=101)
    _assert_error(payload, ERR_INVALID_LIMIT)


def test_generated_content_limit_at_100_is_allowed() -> None:
    dsl = _parse(_content_payload(limit=100))
    assert dsl.limit == 100


# ---------------------------------------------------------------------------
# user_users nickname lookup policy
# ---------------------------------------------------------------------------


def _user_users_payload(**overrides):
    base = {
        "shifu_bid": "shifu-abc",
        "table": "user_users",
        "select": ["user_bid", "nickname"],
        "where": [
            {"field": "user_bid", "op": "in", "value": ["u1", "u2", "u3"]},
        ],
        "limit": 10,
    }
    base.update(overrides)
    return base


def test_user_users_lookup_with_in_filter_parses() -> None:
    dsl = _parse(_user_users_payload())
    assert dsl.table == "user_users"
    assert dsl.select == ("user_bid", "nickname")


def test_user_users_lookup_with_equal_filter_parses() -> None:
    payload = _user_users_payload(
        where=[{"field": "user_bid", "op": "=", "value": "u1"}],
    )
    dsl = _parse(payload)
    assert dsl.filters[0].op == "="


def test_user_users_without_user_bid_filter_is_rejected() -> None:
    payload = _user_users_payload(where=[])
    _assert_error(payload, ERR_INVALID_DSL)


def test_user_users_with_like_user_bid_filter_is_rejected() -> None:
    payload = _user_users_payload(
        where=[{"field": "user_bid", "op": "like", "value": "abc"}],
    )
    _assert_error(payload, ERR_INVALID_DSL)


def test_user_users_limit_above_50_is_rejected() -> None:
    _assert_error(_user_users_payload(limit=51), ERR_INVALID_LIMIT)


def test_user_users_limit_at_50_is_allowed() -> None:
    dsl = _parse(_user_users_payload(limit=50))
    assert dsl.limit == 50


def test_user_users_group_by_is_rejected() -> None:
    payload = _user_users_payload(
        select=["nickname"],
        group_by=["nickname"],
        aggregate=[{"fn": "count", "alias": "n"}],
    )
    _assert_error(payload, ERR_INVALID_COLUMN)


def test_user_users_select_disallowed_column_rejected() -> None:
    payload = _user_users_payload(select=["user_bid", "avatar"])
    _assert_error(payload, ERR_INVALID_COLUMN)


# ---------------------------------------------------------------------------
# user_users user_identify filter policy (v2)
# ---------------------------------------------------------------------------


def _user_users_identify_payload(**overrides):
    base = {
        "shifu_bid": "shifu-abc",
        "table": "user_users",
        "select": ["user_bid", "user_identify"],
        "where": [
            {"field": "user_identify", "op": "=", "value": "13800138000"},
        ],
        "limit": 10,
    }
    base.update(overrides)
    return base


def test_user_users_filter_by_user_identify_eq_parses() -> None:
    dsl = _parse(_user_users_identify_payload())
    assert dsl.table == "user_users"
    assert "user_identify" in dsl.select
    assert dsl.filters[0].field == "user_identify"
    assert dsl.filters[0].op == "="


def test_user_users_select_user_identify_with_user_bid_anchor_parses() -> None:
    payload = _user_users_payload(select=["user_bid", "nickname", "user_identify"])
    dsl = _parse(payload)
    assert "user_identify" in dsl.select


def test_user_users_filter_by_user_identify_in_is_rejected() -> None:
    payload = _user_users_identify_payload(
        where=[
            {
                "field": "user_identify",
                "op": "in",
                "value": ["13800138000", "13900139000"],
            }
        ],
    )
    _assert_error(payload, ERR_INVALID_DSL)


def test_user_users_filter_by_user_identify_like_is_rejected() -> None:
    payload = _user_users_identify_payload(
        where=[{"field": "user_identify", "op": "like", "value": "138%"}],
    )
    _assert_error(payload, ERR_INVALID_DSL)


def test_user_users_filter_by_user_identify_gt_is_rejected() -> None:
    payload = _user_users_identify_payload(
        where=[{"field": "user_identify", "op": ">", "value": "13800138000"}],
    )
    _assert_error(payload, ERR_INVALID_DSL)


def test_user_users_no_anchor_filter_rejected() -> None:
    """Neither user_bid nor user_identify filter — must be rejected."""
    payload = _user_users_identify_payload(where=[])
    _assert_error(payload, ERR_INVALID_DSL)


def test_user_users_user_identify_not_groupable() -> None:
    payload = _user_users_identify_payload(
        select=["user_identify"],
        group_by=["user_identify"],
        aggregate=[{"fn": "count", "alias": "n"}],
    )
    _assert_error(payload, ERR_INVALID_COLUMN)


# ---------------------------------------------------------------------------
# bill_daily_usage_metrics — new credit-cost table (v3)
# ---------------------------------------------------------------------------


def _daily_metric_payload(**overrides):
    base = {
        "shifu_bid": "shifu-abc",
        "table": "bill_daily_usage_metrics",
        "aggregate": [
            {"fn": "sum", "field": "consumed_credits", "alias": "total_credits"}
        ],
        "where": [{"field": "usage_scene", "op": "=", "value": 1203}],
        "limit": 10,
    }
    base.update(overrides)
    return base


def test_bill_daily_consumed_credits_parses() -> None:
    """Sum consumed_credits filtered by stat_date range — baseline credit query."""

    payload = _daily_metric_payload(
        where=[
            {"field": "usage_scene", "op": "=", "value": 1203},
            {
                "field": "stat_date",
                "op": "between",
                "value": ["2026-05-01", "2026-05-14"],
            },
        ],
    )
    dsl = _parse(payload)
    assert dsl.table == "bill_daily_usage_metrics"
    assert dsl.aggregates[0].fn == "sum"
    assert dsl.aggregates[0].alias == "total_credits"


def test_bill_daily_group_by_usage_type_parses() -> None:
    """Group by usage_type and usage_scene — LLM vs TTS credit split."""

    payload = _daily_metric_payload(
        select=["usage_type", "usage_scene"],
        aggregate=[{"fn": "sum", "field": "consumed_credits", "alias": "credits"}],
        group_by=["usage_type", "usage_scene"],
        where=[{"field": "usage_scene", "op": "=", "value": 1203}],
    )
    dsl = _parse(payload)
    assert "usage_type" in dsl.group_by
    assert "usage_scene" in dsl.group_by


def test_bill_daily_select_shifu_bid_rejected() -> None:
    """shifu_bid is injected, callers must not reference it in bill_daily_usage_metrics."""

    payload = _daily_metric_payload(select=["shifu_bid", "stat_date"])
    _assert_error(payload, ERR_INVALID_COLUMN)


# ---------------------------------------------------------------------------
# bill_usage table removed from whitelist (credits-only policy)
# ---------------------------------------------------------------------------


def test_bill_usage_table_rejected() -> None:
    """`bill_usage` is no longer whitelisted; the DSL parser refuses it."""

    payload = {
        "shifu_bid": "shifu-abc",
        "table": "bill_usage",
        "aggregate": [{"fn": "count", "alias": "n"}],
        "limit": 1,
    }
    _assert_error(payload, ERR_INVALID_TABLE)


# ---------------------------------------------------------------------------
# learn_generated_blocks — new fields (status / position / outline_item_bid)
# ---------------------------------------------------------------------------


def _generated_blocks_payload(**overrides):
    """Build a baseline DSL payload for learn_generated_blocks tests."""
    base = {
        "shifu_bid": "shifu-abc",
        "table": "learn_generated_blocks",
        "where": [{"field": "type", "op": "=", "value": 321}],
        "aggregate": [{"fn": "count", "alias": "asks"}],
        "limit": 10,
    }
    base.update(overrides)
    return base


def test_learn_generated_blocks_status_filterable() -> None:
    """status is filterable even though sql_builder auto-injects status=1.
    Allowing explicit filtering lets a caller debug `status=0` history rows
    in tests / one-off audits if the auto-injection is ever relaxed."""

    payload = _generated_blocks_payload(
        where=[
            {"field": "type", "op": "=", "value": 321},
            {"field": "status", "op": "=", "value": 1},
        ],
    )
    dsl = _parse(payload)
    assert any(f.field == "status" for f in dsl.filters)


def test_learn_generated_blocks_outline_item_bid_groupable() -> None:
    """Group by outline_item_bid answers "follow-up questions per lesson"."""

    payload = _generated_blocks_payload(
        select=["outline_item_bid"],
        where=[{"field": "type", "op": "=", "value": 321}],
        aggregate=[{"fn": "count_distinct", "field": "user_bid", "alias": "askers"}],
        group_by=["outline_item_bid"],
    )
    dsl = _parse(payload)
    assert "outline_item_bid" in dsl.group_by


def test_learn_generated_blocks_position_selectable() -> None:
    """position is needed for the four-key follow-up pairing
    (progress_record_bid + shifu_bid + outline_item_bid + position).
    The conversation-replay path (generated_content in select) exempts
    user_bid from the group-by guard, so list mode is the right test."""

    payload = {
        "shifu_bid": "shifu-abc",
        "table": "learn_generated_blocks",
        "select": [
            "user_bid",
            "progress_record_bid",
            "outline_item_bid",
            "position",
            "generated_content",
            "created_at",
        ],
        "where": [{"field": "type", "op": "=", "value": 321}],
        "limit": 10,
    }
    dsl = _parse(payload)
    assert "position" in dsl.select
    assert "outline_item_bid" in dsl.select


def test_learn_generated_blocks_position_not_groupable() -> None:
    """position is row-ordering, not a dimension; grouping on it would
    multiply rows. Reject `group_by=["position"]`."""

    payload = _generated_blocks_payload(
        select=["position"],
        group_by=["position"],
        aggregate=[{"fn": "count", "alias": "n"}],
    )
    _assert_error(payload, ERR_INVALID_COLUMN)


# ---------------------------------------------------------------------------
# bill_daily_usage_metrics.creator_bid — selectable + groupable, not filterable
# ---------------------------------------------------------------------------


def test_bill_daily_creator_bid_groupable() -> None:
    """creator_bid lets the author see which wallet absorbed the course's
    credit cost — shifu_bid isolation guarantees the value is the caller's
    own bid, but exposing it confirms that explicitly in the result."""

    payload = _daily_metric_payload(
        select=["creator_bid", "stat_date"],
        aggregate=[{"fn": "sum", "field": "consumed_credits", "alias": "credits"}],
        group_by=["creator_bid", "stat_date"],
        where=[{"field": "usage_scene", "op": "=", "value": 1203}],
    )
    dsl = _parse(payload)
    assert "creator_bid" in dsl.group_by


def test_bill_daily_creator_bid_filter_rejected() -> None:
    """Filtering by creator_bid is intentionally blocked — shifu_bid scope
    already binds the value, so an explicit filter is either redundant
    (same caller) or an attempt to look at someone else's wallet."""

    payload = _daily_metric_payload(
        where=[
            {"field": "usage_scene", "op": "=", "value": 1203},
            {"field": "creator_bid", "op": "=", "value": "someone-else"},
        ],
    )
    _assert_error(payload, ERR_INVALID_COLUMN)


# ---------------------------------------------------------------------------
# shifu metadata tables — strict row-lookup surface
# ---------------------------------------------------------------------------


def _shifu_meta_payload(table_key="shifu_published_shifus", **overrides):
    """Build a baseline DSL payload for shifu metadata-table tests."""
    base = {
        "shifu_bid": "shifu-abc",
        "table": table_key,
        # shifu_bid is intentionally not in select — the CLI already injected
        # it and exposing it on the metadata table would re-introduce the
        # column to the user-addressable surface.
        "select": ["title", "updated_at"],
        "limit": 10,
    }
    base.update(overrides)
    return base


def test_shifu_published_select_parses() -> None:
    """Baseline: select-only query on the published metadata table."""

    dsl = _parse(_shifu_meta_payload())
    assert dsl.table == "shifu_published_shifus"
    assert "title" in dsl.select


def test_shifu_draft_select_parses() -> None:
    """Baseline: select-only query on the draft metadata table."""

    dsl = _parse(_shifu_meta_payload(table_key="shifu_draft_shifus"))
    assert dsl.table == "shifu_draft_shifus"


def test_shifu_meta_aggregate_rejected() -> None:
    """count / count_distinct on metadata tables would leak permission
    edges (e.g. count_distinct(shifu_bid) reveals "how many courses do I
    own that match this filter")."""

    payload = {
        "shifu_bid": "shifu-abc",
        "table": "shifu_published_shifus",
        "aggregate": [{"fn": "count", "alias": "n"}],
        "limit": 10,
    }
    _assert_error(payload, ERR_INVALID_DSL)


def test_shifu_meta_group_by_rejected() -> None:
    """group_by has no row-lookup use. With groupable=frozenset(), the
    parser actually rejects at the column-membership check (column not
    groupable) before reaching the per-table guard; either rejection
    satisfies the security goal."""

    payload = _shifu_meta_payload(
        select=["title"],
        group_by=["title"],
    )
    _assert_error(payload, ERR_INVALID_COLUMN)


def test_shifu_meta_title_like_too_short_rejected() -> None:
    """`title like 'a%'` is rejected — 1 non-wildcard char approaches full
    enumeration. Minimum is 2 non-wildcard chars."""

    payload = _shifu_meta_payload(
        where=[{"field": "title", "op": "like", "value": "a%"}],
    )
    _assert_error(payload, ERR_INVALID_DSL)


def test_shifu_meta_title_like_minimum_accepted() -> None:
    """`title like 'ai%'` (2 non-wildcard chars) is accepted."""

    payload = _shifu_meta_payload(
        where=[{"field": "title", "op": "like", "value": "ai%"}],
    )
    dsl = _parse(payload)
    assert dsl.filters[0].op == "like"


def test_shifu_meta_title_like_underscore_rejected() -> None:
    """SQL `_` single-char wildcard would let a caller scan with `'a_%'`
    (one literal char + a wildcard floor). The metadata contract is strict
    prefix matching — reject any `_` regardless of position."""

    payload = _shifu_meta_payload(
        where=[{"field": "title", "op": "like", "value": "a_%"}],
    )
    _assert_error(payload, ERR_INVALID_DSL)


def test_shifu_meta_title_like_double_underscore_rejected() -> None:
    """Original bypass case raised in PR #1769 review: `'__%'` passes the
    `rstrip('%')` length check (2 chars) but is wildcard-only. Must reject."""

    payload = _shifu_meta_payload(
        where=[{"field": "title", "op": "like", "value": "__%"}],
    )
    _assert_error(payload, ERR_INVALID_DSL)


def test_shifu_meta_title_like_internal_percent_rejected() -> None:
    """`'a%b'` would be 3 non-wildcard chars under naive counting, but the
    middle `%` violates the prefix-only contract — reject."""

    payload = _shifu_meta_payload(
        where=[{"field": "title", "op": "like", "value": "a%b"}],
    )
    _assert_error(payload, ERR_INVALID_DSL)


def test_shifu_meta_title_like_exact_match_accepted() -> None:
    """A `like` value without any wildcard is just an exact match;
    accepting it preserves the "look up this exact title" use case."""

    payload = _shifu_meta_payload(
        where=[{"field": "title", "op": "like", "value": "AI"}],
    )
    dsl = _parse(payload)
    assert dsl.filters[0].op == "like"
    assert dsl.filters[0].value == "AI"


def test_shifu_meta_limit_capped_at_50() -> None:
    """Hard cap at 50 even when the global limit_max is 1000."""

    payload = _shifu_meta_payload(limit=51)
    _assert_error(payload, ERR_INVALID_LIMIT)


def test_shifu_meta_limit_50_accepted() -> None:
    """Exactly 50 is accepted (cap is inclusive)."""

    payload = _shifu_meta_payload(limit=50)
    dsl = _parse(payload)
    assert dsl.limit == 50


def test_shifu_meta_caller_user_id_threaded() -> None:
    """parse_dsl propagates user_id into QueryDSL.caller_user_id; the SQL
    builder reads it to inject WHERE created_user_bid = :__user_id."""

    payload = _shifu_meta_payload()
    dsl = parse_dsl(payload, limit_max=DEFAULT_LIMIT_MAX, user_id="teacher-1")
    assert dsl.caller_user_id == "teacher-1"


def test_shifu_meta_select_forbidden_field_rejected() -> None:
    """Author-secret fields like `llm_system_prompt` must not be selectable
    even on the caller's own course."""

    payload = _shifu_meta_payload(select=["title", "llm_system_prompt"])
    _assert_error(payload, ERR_INVALID_COLUMN)
