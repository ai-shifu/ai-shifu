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
    "bill_daily_usage_metrics",
    "shifu_user_archives",
    "user_users",
    "shifu_published_shifus",
    "shifu_draft_shifus",
}

# Tables whose rows are shifu-scoped (sql_builder injects WHERE shifu_bid=:sb).
# user_users is global and gated by funcs.run_dsl permission check instead.
SHIFU_SCOPED_TABLE_KEYS = EXPECTED_TABLE_KEYS - {"user_users"}

# Course metadata tables — answer "what is this course currently called".
# Aggregates and group_by are blocked here to prevent permission-edge probes.
SHIFU_META_TABLE_KEYS = {"shifu_published_shifus", "shifu_draft_shifus"}

# Learner-grained tables that expose user_bid — bill_daily_usage_metrics is a
# daily summary table without user_bid; shifu metadata tables describe the
# course, not learner activity.
USER_BID_GROUPABLE_TABLE_KEYS = (
    SHIFU_SCOPED_TABLE_KEYS - {"bill_daily_usage_metrics"} - SHIFU_META_TABLE_KEYS
)


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


@pytest.mark.parametrize("table_key", sorted(USER_BID_GROUPABLE_TABLE_KEYS))
def test_user_bid_is_groupable_on_every_shifu_scoped_table(table_key: str) -> None:
    """user_bid is groupable on learner-grained shifu-scoped tables."""

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


def test_bill_daily_usage_metrics_has_shifu_bid_and_deleted() -> None:
    """bill_daily_usage_metrics is shifu-scoped and soft-deletable."""

    spec = WHITELIST["bill_daily_usage_metrics"]
    assert spec.has_shifu_bid is True
    assert spec.has_deleted is True


def test_bill_usage_is_not_whitelisted() -> None:
    """Creators cannot query raw token usage; only credit aggregates are exposed."""

    assert "bill_usage" not in WHITELIST


# ---------------------------------------------------------------------------
# learn_generated_blocks — new field coverage + status auto-filter
# ---------------------------------------------------------------------------


def test_learn_generated_blocks_exposes_new_followup_fields() -> None:
    """status / position / outline_item_bid are needed for follow-up pairing
    (per the 2026-05-15 follow-up query handbook PDF §6)."""

    spec = WHITELIST["learn_generated_blocks"]
    for col in ("status", "position", "outline_item_bid"):
        assert col in spec.selectable, (
            f"learn_generated_blocks.{col} must be selectable"
        )
        assert col in spec.filterable, (
            f"learn_generated_blocks.{col} must be filterable"
        )
    assert "outline_item_bid" in spec.groupable
    assert "status" in spec.groupable
    # position is not group-able — it is a within-row ordering index, not a
    # dimension; grouping on it would explode the row count and is rarely
    # what an author intends.
    assert "position" not in spec.groupable
    assert "outline_item_bid" in spec.aggregatable


def test_learn_generated_blocks_auto_filters_active_status() -> None:
    """Rerolled history rows (status=0) must be excluded from creator views.

    This pairs with sql_builder which injects AND status = 1; the spec flag
    is the source of truth for that injection.
    """

    spec = WHITELIST["learn_generated_blocks"]
    assert spec.auto_filter_status_active is True


@pytest.mark.parametrize(
    "table_key",
    sorted(EXPECTED_TABLE_KEYS - {"learn_generated_blocks"}),
)
def test_other_tables_do_not_auto_filter_status(table_key: str) -> None:
    """Only learn_generated_blocks opts into status=1 auto-injection."""

    spec = WHITELIST[table_key]
    assert spec.auto_filter_status_active is False


# ---------------------------------------------------------------------------
# bill_daily_usage_metrics — creator_bid surface
# ---------------------------------------------------------------------------


def test_bill_daily_usage_metrics_exposes_creator_bid() -> None:
    """creator_bid lets the author see which wallet the course's credits hit;
    shifu_bid isolation already constrains the value to the caller's own bid."""

    spec = WHITELIST["bill_daily_usage_metrics"]
    assert "creator_bid" in spec.selectable
    assert "creator_bid" in spec.groupable
    # Deliberately NOT in filterable / aggregatable: the SQL builder already
    # restricts rows via shifu_bid, so a creator_bid filter would be
    # redundant; keeping it out blocks "where creator_bid = 'someone-else'"
    # attempts even though shifu_bid isolation would still defeat them.
    assert "creator_bid" not in spec.filterable
    assert "creator_bid" not in spec.aggregatable


# ---------------------------------------------------------------------------
# shifu metadata tables — double-gate + no-aggregate side channel
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table_key", sorted(SHIFU_META_TABLE_KEYS))
def test_shifu_meta_tables_are_creator_scoped(table_key: str) -> None:
    """Both metadata tables enforce row ownership via created_user_bid in
    addition to the funcs.run_dsl shifu permission check."""

    spec = WHITELIST[table_key]
    assert spec.creator_scoped_column == "created_user_bid"
    assert spec.has_shifu_bid is True  # double-gate: shifu scope + row owner
    assert spec.has_deleted is True


@pytest.mark.parametrize("table_key", sorted(SHIFU_META_TABLE_KEYS))
def test_shifu_meta_tables_block_aggregate_and_group_by(table_key: str) -> None:
    """count_distinct(shifu_bid) etc. would leak the size of the caller's
    owned set; keep these tables strictly row-lookup only."""

    spec = WHITELIST[table_key]
    assert spec.aggregatable == {}
    assert spec.groupable == frozenset()


@pytest.mark.parametrize("table_key", sorted(SHIFU_META_TABLE_KEYS))
def test_shifu_meta_tables_minimum_select_surface(table_key: str) -> None:
    """Author-secret prompt fields (llm_system_prompt, ask_*) must never be
    selectable — they are creator IP and stay out of the analytics surface
    even for the owner. shifu_bid is also intentionally not selectable here
    (covered by test_shifu_bid_and_deleted_are_never_user_addressable)."""

    spec = WHITELIST[table_key]
    assert spec.selectable == frozenset(
        {"title", "created_user_bid", "created_at", "updated_at"}
    )
    for forbidden in (
        "llm",
        "llm_system_prompt",
        "ask_llm",
        "ask_llm_system_prompt",
        "ask_provider_config",
        "keywords",
        "description",
        "avatar_res_bid",
        "price",
    ):
        assert forbidden not in spec.selectable
        assert forbidden not in spec.filterable


@pytest.mark.parametrize(
    "table_key",
    sorted(EXPECTED_TABLE_KEYS - SHIFU_META_TABLE_KEYS),
)
def test_other_tables_have_no_creator_scoped_column(table_key: str) -> None:
    """Only the metadata tables opt into the created_user_bid auto-injection;
    every other table goes through the standard shifu_bid scope path."""

    spec = WHITELIST[table_key]
    assert spec.creator_scoped_column is None
