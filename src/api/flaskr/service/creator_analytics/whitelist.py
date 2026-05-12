"""Creator-analytics table / column whitelist.

Every DSL request is constrained by :data:`WHITELIST`. The set of tables, the
columns that may appear in ``select`` / ``where`` / ``group_by``, and the
aggregations allowed per column are declared here. ``shifu_bid`` and ``deleted``
are not exposed in the DSL surface — they are injected by the SQL builder
based on :attr:`TableSpec.has_deleted` and the authenticated user's
permissions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Mapping, Type

from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnLessonFeedback,
    LearnProgressRecord,
)
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.order.models import Order
from flaskr.service.profile.models import VariableValue
from flaskr.service.shifu.models import ShifuUserArchive
from flaskr.service.user.models import UserInfo


ALLOWED_AGGREGATE_FUNCTIONS: FrozenSet[str] = frozenset(
    {"count", "count_distinct", "sum", "avg", "min", "max"}
)

ALLOWED_OPERATORS: FrozenSet[str] = frozenset(
    {
        "=",
        "!=",
        ">",
        ">=",
        "<",
        "<=",
        "in",
        "not_in",
        "between",
        "like",
        "is_null",
        "is_not_null",
    }
)


@dataclass(frozen=True)
class TableSpec:
    """Declarative whitelist for one analyzable table."""

    table_key: str
    model: Type
    selectable: FrozenSet[str]
    filterable: FrozenSet[str]
    groupable: FrozenSet[str]
    aggregatable: Mapping[str, FrozenSet[str]]
    has_deleted: bool
    # True for shifu-scoped tables (sql_builder injects WHERE shifu_bid=:sb).
    # False for global tables like user_users — permission is still enforced
    # by funcs.run_dsl using get_user_shifu_permissions, but the SQL cannot
    # filter by a column the table does not have.
    has_shifu_bid: bool = True


_DIMENSION_AGGS: FrozenSet[str] = frozenset({"count", "count_distinct"})
_NUMERIC_AGGS: FrozenSet[str] = frozenset({"count", "sum", "avg", "min", "max"})
_TIMESTAMP_AGGS: FrozenSet[str] = frozenset({"count", "min", "max"})


WHITELIST: Mapping[str, TableSpec] = {
    "learn_progress_records": TableSpec(
        table_key="learn_progress_records",
        model=LearnProgressRecord,
        selectable=frozenset(
            {
                "progress_record_bid",
                "user_bid",
                "outline_item_bid",
                "status",
                "block_position",
                "created_at",
                "updated_at",
            }
        ),
        filterable=frozenset(
            {
                "user_bid",
                "outline_item_bid",
                "status",
                "block_position",
                "created_at",
                "updated_at",
            }
        ),
        groupable=frozenset(
            {"user_bid", "outline_item_bid", "status", "block_position"}
        ),
        aggregatable={
            "progress_record_bid": _DIMENSION_AGGS,
            "user_bid": _DIMENSION_AGGS,
            "outline_item_bid": _DIMENSION_AGGS,
            "created_at": _TIMESTAMP_AGGS,
            "updated_at": _TIMESTAMP_AGGS,
        },
        has_deleted=True,
    ),
    "learn_generated_blocks": TableSpec(
        table_key="learn_generated_blocks",
        model=LearnGeneratedBlock,
        selectable=frozenset(
            {
                "generated_block_bid",
                "user_bid",
                "progress_record_bid",
                "type",
                "role",
                "liked",
                "created_at",
                "generated_content",
            }
        ),
        filterable=frozenset(
            {
                "user_bid",
                "progress_record_bid",
                "type",
                "role",
                "liked",
                "created_at",
            }
        ),
        groupable=frozenset({"user_bid", "type", "role", "liked"}),
        aggregatable={
            "generated_block_bid": _DIMENSION_AGGS,
            "user_bid": _DIMENSION_AGGS,
            "liked": _NUMERIC_AGGS,
            "created_at": _TIMESTAMP_AGGS,
        },
        has_deleted=True,
    ),
    "learn_lesson_feedbacks": TableSpec(
        table_key="learn_lesson_feedbacks",
        model=LearnLessonFeedback,
        selectable=frozenset(
            {
                "lesson_feedback_bid",
                "user_bid",
                "progress_record_bid",
                "mode",
                "score",
                "created_at",
            }
        ),
        filterable=frozenset(
            {
                "user_bid",
                "progress_record_bid",
                "mode",
                "score",
                "created_at",
            }
        ),
        groupable=frozenset({"user_bid", "progress_record_bid", "mode", "score"}),
        aggregatable={
            "lesson_feedback_bid": _DIMENSION_AGGS,
            "user_bid": _DIMENSION_AGGS,
            "score": _NUMERIC_AGGS,
            "created_at": _TIMESTAMP_AGGS,
        },
        has_deleted=True,
    ),
    "order_orders": TableSpec(
        table_key="order_orders",
        model=Order,
        selectable=frozenset(
            {
                "order_bid",
                "user_bid",
                "status",
                "payment_channel",
                "paid_price",
                "created_at",
            }
        ),
        filterable=frozenset(
            {
                "user_bid",
                "status",
                "payment_channel",
                "paid_price",
                "created_at",
            }
        ),
        groupable=frozenset({"user_bid", "status", "payment_channel"}),
        aggregatable={
            "order_bid": _DIMENSION_AGGS,
            "user_bid": _DIMENSION_AGGS,
            "paid_price": _NUMERIC_AGGS,
            "created_at": _TIMESTAMP_AGGS,
        },
        has_deleted=True,
    ),
    "var_variable_values": TableSpec(
        table_key="var_variable_values",
        model=VariableValue,
        selectable=frozenset(
            {
                "variable_value_bid",
                "user_bid",
                "variable_bid",
                "value",
                "updated_at",
            }
        ),
        filterable=frozenset({"user_bid", "variable_bid", "value", "updated_at"}),
        groupable=frozenset({"user_bid", "variable_bid", "value"}),
        aggregatable={
            "variable_value_bid": _DIMENSION_AGGS,
            "user_bid": _DIMENSION_AGGS,
            "updated_at": _TIMESTAMP_AGGS,
        },
        has_deleted=True,
    ),
    "bill_usage": TableSpec(
        table_key="bill_usage",
        model=BillUsageRecord,
        selectable=frozenset(
            {
                "usage_bid",
                "user_bid",
                "progress_record_bid",
                "usage_type",
                "usage_scene",
                "input",
                "output",
                "latency_ms",
                "created_at",
            }
        ),
        filterable=frozenset(
            {
                "user_bid",
                "progress_record_bid",
                "usage_type",
                "usage_scene",
                "created_at",
            }
        ),
        groupable=frozenset(
            {"user_bid", "progress_record_bid", "usage_type", "usage_scene"}
        ),
        aggregatable={
            "usage_bid": _DIMENSION_AGGS,
            "user_bid": _DIMENSION_AGGS,
            "input": _NUMERIC_AGGS,
            "output": _NUMERIC_AGGS,
            "latency_ms": _NUMERIC_AGGS,
            "created_at": _TIMESTAMP_AGGS,
        },
        has_deleted=True,
    ),
    "shifu_user_archives": TableSpec(
        table_key="shifu_user_archives",
        model=ShifuUserArchive,
        selectable=frozenset({"user_bid", "archived", "archived_at", "created_at"}),
        filterable=frozenset({"user_bid", "archived", "archived_at", "created_at"}),
        groupable=frozenset({"user_bid", "archived"}),
        aggregatable={
            "user_bid": _DIMENSION_AGGS,
            "archived_at": _TIMESTAMP_AGGS,
            "created_at": _TIMESTAMP_AGGS,
        },
        has_deleted=False,
    ),
    # ------------------------------------------------------------------
    # Global user table — strictly limited to nickname lookup by a known
    # user_bid list. Compared to the other tables this one is special:
    #   - selectable only {user_bid, nickname} (no phone / email / avatar)
    #   - filterable only {user_bid}; DSL enforces a where user_bid clause
    #   - groupable / aggregatable empty (no nickname distribution probing)
    #   - has_shifu_bid=False — table has no shifu_bid column; permission
    #     is still gated by funcs.run_dsl via get_user_shifu_permissions
    #   - per-query limit hard-capped to 50 (see dsl._USER_USERS_LIMIT_MAX)
    #   - nickname values pass through PII redaction in funcs
    #   - access is audit-logged
    # ------------------------------------------------------------------
    "user_users": TableSpec(
        table_key="user_users",
        model=UserInfo,
        selectable=frozenset({"user_bid", "nickname"}),
        filterable=frozenset({"user_bid"}),
        groupable=frozenset(),
        aggregatable={},
        has_deleted=True,
        has_shifu_bid=False,
    ),
}


def get_table_spec(table_key: str) -> TableSpec:
    """Return the spec for ``table_key`` or raise :class:`KeyError`."""

    return WHITELIST[table_key]
