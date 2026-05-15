"""DSL parser and validator for creator-analytics queries.

The DSL is a structured JSON payload sent by the creator-side LLM. The parser
turns it into typed :class:`QueryDSL` instances after enforcing the whitelist
declared in :mod:`flaskr.service.creator_analytics.whitelist`. The output is
then consumed by :mod:`flaskr.service.creator_analytics.sql_builder`.

Validation is intentionally strict — every shape, table, column, operator,
aggregate, and limit is checked against an explicit allowlist before any SQL
is composed. Errors are raised as :class:`AppException` with stable error
names registered in ``src/api/error_codes.json``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional, Sequence, Tuple

from flaskr.service.common.models import AppException, ERROR_CODE
from flaskr.i18n import _

from .whitelist import (
    ALLOWED_AGGREGATE_FUNCTIONS,
    ALLOWED_OPERATORS,
    TableSpec,
    WHITELIST,
)


# Error names — registered in src/api/error_codes.json by Step 7.
ERR_INVALID_DSL = "server.creatorAnalytics.invalidDsl"
ERR_INVALID_TABLE = "server.creatorAnalytics.invalidTable"
ERR_INVALID_COLUMN = "server.creatorAnalytics.invalidColumn"
ERR_INVALID_OPERATOR = "server.creatorAnalytics.invalidOperator"
ERR_INVALID_AGGREGATE = "server.creatorAnalytics.invalidAggregate"
ERR_INVALID_LIMIT = "server.creatorAnalytics.invalidLimit"


def _translation_keys_used() -> None:
    """Static registry consumed by the translation-usage checker.

    Never invoked at runtime — translation keys are referenced through the
    ERR_* constants above. Listing them as literal `_()` calls inside an
    unused function lets the static checker confirm they are wired without
    forcing every error site to inline the string.
    """

    _("server.creatorAnalytics.invalidDsl")
    _("server.creatorAnalytics.invalidTable")
    _("server.creatorAnalytics.invalidColumn")
    _("server.creatorAnalytics.invalidOperator")
    _("server.creatorAnalytics.invalidAggregate")
    _("server.creatorAnalytics.invalidLimit")
    _("server.creatorAnalytics.noPermission")
    _("server.creatorAnalytics.queryTimeout")


_OPS_REQUIRING_LIST_VALUE = frozenset({"in", "not_in"})
_OPS_REQUIRING_BETWEEN = frozenset({"between"})
_OPS_REQUIRING_NO_VALUE = frozenset({"is_null", "is_not_null"})
_COMPARISON_OPS = frozenset({"=", "!=", ">", ">=", "<", "<=", "like"})

_MAX_IN_VALUES = 1000

# Block types whose ``generated_content`` is safe to expose to creators:
# 301 content / 311 mdcontent / 312 mdinteraction / 321 mdask / 322 mdanswer.
# Phone/input/checkcode/options block types are intentionally excluded — they
# contain learner-typed PII (phone numbers, free-form answers, etc.).
_GENERATED_CONTENT_ALLOWED_TYPES = frozenset({301, 311, 312, 321, 322})

# When ``generated_content`` is selected the per-page limit is capped low so
# the API cannot be used to export the entire conversation history in one go.
_GENERATED_CONTENT_LIMIT_MAX = 100

# Querying user_users is restricted to "look up nickname for these N known
# user_bids" — the caller must already know the user_bid list from another
# DSL query, and may resolve at most this many per call.
_USER_USERS_LIMIT_MAX = 50

# Querying the shifu metadata tables (shifu_published_shifus /
# shifu_draft_shifus) is restricted to "look up the current title for the
# shifu I own / list courses I created that match a substring". Aggregates
# and group_by are blocked (would let a caller probe permission edges via
# count_distinct(shifu_bid) etc.), the limit is hard-capped, and a
# `title like` value must include at least _LIKE_MIN_NON_WILDCARD_CHARS
# non-wildcard characters so a caller cannot scan with `like "a%"`.
_SHIFU_META_LIMIT_MAX = 50
_SHIFU_META_TABLES = frozenset({"shifu_published_shifus", "shifu_draft_shifus"})
_LIKE_MIN_NON_WILDCARD_CHARS = 2


def _raise(error_name: str, detail: Optional[str] = None) -> None:
    """Raise an :class:`AppException` with a stable error name.

    ``detail`` is appended in parentheses so the client gets actionable
    feedback (e.g. which column failed validation) without leaking internals.
    """

    message = _(error_name)
    if detail:
        message = f"{message} ({detail})"
    code = ERROR_CODE.get(error_name, ERROR_CODE.get("server.common.unknownError"))
    raise AppException(message, code)


@dataclass(frozen=True)
class Filter:
    field: str
    op: str
    value: Any = None


@dataclass(frozen=True)
class Aggregate:
    fn: str
    field: Optional[str]
    alias: str
    distinct: bool = False


@dataclass(frozen=True)
class OrderBy:
    field: str
    direction: str  # "asc" or "desc"


@dataclass(frozen=True)
class QueryDSL:
    shifu_bid: str
    table: str
    spec: TableSpec
    select: Tuple[str, ...]
    filters: Tuple[Filter, ...]
    group_by: Tuple[str, ...]
    aggregates: Tuple[Aggregate, ...]
    order_by: Tuple[OrderBy, ...]
    limit: int
    offset: int

    output_columns: Tuple[str, ...] = field(default_factory=tuple)
    # Caller's authenticated user_id, threaded from funcs.run_dsl. Consumed
    # by sql_builder when the target TableSpec declares a
    # `creator_scoped_column` (currently the shifu metadata tables).
    caller_user_id: str = ""


# ---------------------------------------------------------------------------
# Top-level parser
# ---------------------------------------------------------------------------


def parse_dsl(payload: Any, limit_max: int, user_id: str = "") -> QueryDSL:
    """Validate ``payload`` and return a :class:`QueryDSL`.

    ``limit_max`` is the upper bound for the DSL ``limit`` field (typically
    ``ANALYTICS_QUERY_LIMIT_MAX``).

    ``user_id`` is the caller's authenticated user_id. It is threaded into
    :attr:`QueryDSL.caller_user_id` so :mod:`sql_builder` can inject the
    ``creator_scoped_column = :__user_id`` predicate for tables that opt
    into row-ownership enforcement. The default empty string is allowed
    for legacy call sites that never hit a creator-scoped table (the SQL
    builder still validates this combination).
    """

    if not isinstance(payload, Mapping):
        _raise(ERR_INVALID_DSL, "payload must be a JSON object")

    shifu_bid = payload.get("shifu_bid")
    if not isinstance(shifu_bid, str) or not shifu_bid:
        _raise(ERR_INVALID_DSL, "shifu_bid is required and must be a non-empty string")

    table_key = payload.get("table")
    if not isinstance(table_key, str):
        _raise(ERR_INVALID_TABLE, "table is required")
    if table_key not in WHITELIST:
        _raise(ERR_INVALID_TABLE, f"unknown table '{table_key}'")
    spec = WHITELIST[table_key]

    select = _parse_select(payload.get("select"), spec)
    aggregates = _parse_aggregates(payload.get("aggregate"), spec)

    if not select and not aggregates:
        _raise(ERR_INVALID_DSL, "either 'select' or 'aggregate' must be provided")

    group_by = _parse_group_by(payload.get("group_by"), spec)
    _enforce_select_group_by_compatibility(select, group_by, aggregates)
    _enforce_user_bid_aggregation_only(select, group_by, aggregates, table_key)

    filters = _parse_filters(payload.get("where"), spec)
    _enforce_generated_content_type_filter(select, filters)
    _enforce_user_users_requires_user_bid_filter(table_key, filters)
    _enforce_shifu_meta_table_constraints(table_key, aggregates, group_by, filters)
    order_by = _parse_order_by(payload.get("order_by"), select, aggregates, group_by)
    if table_key == "user_users":
        effective_limit_max = _USER_USERS_LIMIT_MAX
    elif table_key in _SHIFU_META_TABLES:
        effective_limit_max = _SHIFU_META_LIMIT_MAX
    elif "generated_content" in select:
        effective_limit_max = _GENERATED_CONTENT_LIMIT_MAX
    else:
        effective_limit_max = limit_max
    limit, offset = _parse_paging(
        payload.get("limit"), payload.get("offset"), effective_limit_max
    )

    output_columns = (
        tuple(group_by) + tuple(agg.alias for agg in aggregates)
        if aggregates
        else tuple(select)
    )

    return QueryDSL(
        shifu_bid=shifu_bid,
        table=table_key,
        spec=spec,
        select=tuple(select),
        filters=tuple(filters),
        group_by=tuple(group_by),
        aggregates=tuple(aggregates),
        order_by=tuple(order_by),
        limit=limit,
        offset=offset,
        output_columns=output_columns,
        caller_user_id=user_id,
    )


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------


def _parse_select(raw: Any, spec: TableSpec) -> List[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        _raise(ERR_INVALID_DSL, "'select' must be a list of strings")
    if "*" in raw:
        _raise(ERR_INVALID_DSL, "'select *' is not allowed; list columns explicitly")
    for col in raw:
        if col not in spec.selectable:
            _raise(
                ERR_INVALID_COLUMN,
                f"column '{col}' is not selectable on '{spec.table_key}'",
            )
    if len(raw) != len(set(raw)):
        _raise(ERR_INVALID_DSL, "'select' contains duplicate columns")
    return list(raw)


def _parse_group_by(raw: Any, spec: TableSpec) -> List[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        _raise(ERR_INVALID_DSL, "'group_by' must be a list of strings")
    for col in raw:
        if col not in spec.groupable:
            _raise(
                ERR_INVALID_COLUMN,
                f"column '{col}' is not groupable on '{spec.table_key}'",
            )
    if len(raw) != len(set(raw)):
        _raise(ERR_INVALID_DSL, "'group_by' contains duplicate columns")
    return list(raw)


def _parse_aggregates(raw: Any, spec: TableSpec) -> List[Aggregate]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        _raise(ERR_INVALID_DSL, "'aggregate' must be a list of aggregate objects")
    aggregates: List[Aggregate] = []
    seen_aliases: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            _raise(ERR_INVALID_DSL, f"aggregate[{index}] must be an object")
        fn = item.get("fn")
        if fn not in ALLOWED_AGGREGATE_FUNCTIONS:
            _raise(
                ERR_INVALID_AGGREGATE, f"aggregate[{index}].fn '{fn}' is not allowed"
            )

        field_name = item.get("field")
        if fn == "count" and field_name is None:
            target_field: Optional[str] = None
        else:
            if not isinstance(field_name, str):
                _raise(
                    ERR_INVALID_AGGREGATE,
                    f"aggregate[{index}].field is required for fn '{fn}'",
                )
            allowed_fns = spec.aggregatable.get(field_name)
            if allowed_fns is None:
                _raise(
                    ERR_INVALID_COLUMN,
                    f"aggregate[{index}] column '{field_name}' is not aggregatable on '{spec.table_key}'",
                )
            normalized_fn = "count" if fn == "count_distinct" else fn
            if normalized_fn not in allowed_fns and fn not in allowed_fns:
                _raise(
                    ERR_INVALID_AGGREGATE,
                    f"aggregate[{index}].fn '{fn}' is not allowed on column '{field_name}'",
                )
            target_field = field_name

        distinct = bool(item.get("distinct", False))
        if fn == "count_distinct":
            distinct = True

        alias = item.get("alias")
        if alias is None:
            alias = _default_alias(fn, target_field)
        if not isinstance(alias, str) or not alias:
            _raise(
                ERR_INVALID_AGGREGATE,
                f"aggregate[{index}].alias must be a non-empty string",
            )
        if not _is_safe_identifier(alias):
            _raise(
                ERR_INVALID_AGGREGATE,
                f"aggregate[{index}].alias '{alias}' contains forbidden characters",
            )
        if alias in seen_aliases:
            _raise(ERR_INVALID_AGGREGATE, f"duplicate aggregate alias '{alias}'")
        seen_aliases.add(alias)

        aggregates.append(
            Aggregate(fn=fn, field=target_field, alias=alias, distinct=distinct)
        )
    return aggregates


def _parse_filters(raw: Any, spec: TableSpec) -> List[Filter]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        _raise(ERR_INVALID_DSL, "'where' must be a list of filter objects")
    filters: List[Filter] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            _raise(ERR_INVALID_DSL, f"where[{index}] must be an object")
        field_name = item.get("field")
        if not isinstance(field_name, str):
            _raise(ERR_INVALID_DSL, f"where[{index}].field must be a string")
        if field_name not in spec.filterable:
            _raise(
                ERR_INVALID_COLUMN,
                f"column '{field_name}' is not filterable on '{spec.table_key}'",
            )
        op = item.get("op")
        if op not in ALLOWED_OPERATORS:
            _raise(ERR_INVALID_OPERATOR, f"where[{index}].op '{op}' is not allowed")

        value = item.get("value")
        _validate_filter_value(index, op, value)
        filters.append(Filter(field=field_name, op=op, value=value))
    return filters


def _parse_order_by(
    raw: Any,
    select: Sequence[str],
    aggregates: Sequence[Aggregate],
    group_by: Sequence[str],
) -> List[OrderBy]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        _raise(ERR_INVALID_DSL, "'order_by' must be a list")
    allowed_targets = set(select) | set(group_by) | {agg.alias for agg in aggregates}
    out: List[OrderBy] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            _raise(ERR_INVALID_DSL, f"order_by[{index}] must be an object")
        field_name = item.get("field")
        direction = (item.get("dir") or item.get("direction") or "asc").lower()
        if direction not in ("asc", "desc"):
            _raise(ERR_INVALID_DSL, f"order_by[{index}].dir must be 'asc' or 'desc'")
        if not isinstance(field_name, str) or field_name not in allowed_targets:
            _raise(
                ERR_INVALID_COLUMN,
                f"order_by[{index}].field '{field_name}' must appear in select/group_by/aggregate alias",
            )
        out.append(OrderBy(field=field_name, direction=direction))
    return out


def _parse_paging(raw_limit: Any, raw_offset: Any, limit_max: int) -> Tuple[int, int]:
    limit = raw_limit if raw_limit is not None else min(100, limit_max)
    if not isinstance(limit, int) or isinstance(limit, bool):
        _raise(ERR_INVALID_LIMIT, "'limit' must be an integer")
    if limit < 1 or limit > limit_max:
        _raise(ERR_INVALID_LIMIT, f"'limit' must be in [1, {limit_max}]")

    offset = raw_offset if raw_offset is not None else 0
    if not isinstance(offset, int) or isinstance(offset, bool):
        _raise(ERR_INVALID_LIMIT, "'offset' must be an integer")
    if offset < 0:
        _raise(ERR_INVALID_LIMIT, "'offset' must be >= 0")
    return limit, offset


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_filter_value(index: int, op: str, value: Any) -> None:
    if op in _OPS_REQUIRING_NO_VALUE:
        if value is not None:
            _raise(ERR_INVALID_DSL, f"where[{index}] '{op}' must not carry a value")
        return

    if op in _OPS_REQUIRING_LIST_VALUE:
        if not isinstance(value, list) or not value:
            _raise(ERR_INVALID_DSL, f"where[{index}] '{op}' requires a non-empty list")
        if len(value) > _MAX_IN_VALUES:
            _raise(
                ERR_INVALID_DSL,
                f"where[{index}] '{op}' supports up to {_MAX_IN_VALUES} values",
            )
        return

    if op in _OPS_REQUIRING_BETWEEN:
        if (
            not isinstance(value, list)
            or len(value) != 2
            or value[0] is None
            or value[1] is None
        ):
            _raise(ERR_INVALID_DSL, f"where[{index}] 'between' requires [low, high]")
        return

    if op == "like":
        if not isinstance(value, str) or not value:
            _raise(
                ERR_INVALID_DSL, f"where[{index}] 'like' requires a non-empty string"
            )
        if value.startswith("%"):
            _raise(
                ERR_INVALID_DSL,
                f"where[{index}] 'like' must not start with '%' (full-scan guard)",
            )
        return

    if op in _COMPARISON_OPS:
        if isinstance(value, (list, dict)):
            _raise(ERR_INVALID_DSL, f"where[{index}] '{op}' requires a scalar value")
        if value is None:
            _raise(
                ERR_INVALID_DSL,
                f"where[{index}] '{op}' requires a value (use 'is_null' for NULL checks)",
            )
        return


def _enforce_select_group_by_compatibility(
    select: Sequence[str],
    group_by: Sequence[str],
    aggregates: Sequence[Aggregate],
) -> None:
    """If aggregates are present, every plain ``select`` column must appear in ``group_by``."""

    if not aggregates:
        return
    group_set = set(group_by)
    for col in select:
        if col not in group_set:
            _raise(
                ERR_INVALID_DSL,
                f"'select' column '{col}' must appear in 'group_by' when aggregating",
            )


def _enforce_user_bid_aggregation_only(
    select: Sequence[str],
    group_by: Sequence[str],
    aggregates: Sequence[Aggregate],
    table_key: str,
) -> None:
    """``user_bid`` may only surface as a group-by dimension, never as a raw column.

    Without this guard, ``select=["user_bid", ...]`` with no aggregate would
    return a raw learner pseudo-ID list. We require ``user_bid`` to appear in
    ``group_by`` whenever it appears in ``select`` — that way every row is a
    per-learner aggregate (e.g. token spend, completion count) rather than a
    line of detail.

    Exemptions:
      - ``generated_content`` in select: conversation-detail mode (other guards
        gate that path — type allowlist + limit cap + audit log).
      - ``table_key == "user_users"``: this table's only purpose is to resolve
        a known user_bid list into nicknames; the user_bid filter is
        mandatory (see :func:`_enforce_user_users_requires_user_bid_filter`)
        and limit is capped to 50, so the row-detail concern doesn't apply.
    """

    if "user_bid" not in select:
        return
    if "user_bid" in group_by:
        return
    if "generated_content" in select:
        return
    if table_key == "user_users":
        return
    _raise(
        ERR_INVALID_DSL,
        "'select' containing 'user_bid' must also 'group_by' user_bid "
        "(raw learner-id listing is not allowed)",
    )


def _enforce_generated_content_type_filter(
    select: Sequence[str],
    filters: Sequence[Filter],
) -> None:
    """``generated_content`` requires a narrow ``type`` filter.

    The column holds free-form text for many block kinds, including ones that
    contain learner-typed PII (phone, checkcode, input answers, options).
    When the caller wants the raw text, they must restrict the query to the
    safe block types — system-pushed content (301/311/312) and ask/answer
    pairs (321/322). This is enforced at the DSL layer so the SQL builder
    cannot accidentally widen the scope.
    """

    if "generated_content" not in select:
        return

    type_filters = [f for f in filters if f.field == "type"]
    if not type_filters:
        _raise(
            ERR_INVALID_DSL,
            "'select' containing 'generated_content' requires a 'where' filter "
            f"on 'type' restricted to {sorted(_GENERATED_CONTENT_ALLOWED_TYPES)}",
        )

    for filt in type_filters:
        if filt.op == "=":
            if filt.value not in _GENERATED_CONTENT_ALLOWED_TYPES:
                _raise(
                    ERR_INVALID_DSL,
                    f"'generated_content' may only be selected for type in "
                    f"{sorted(_GENERATED_CONTENT_ALLOWED_TYPES)} (got {filt.value})",
                )
        elif filt.op == "in":
            if not isinstance(filt.value, list) or not all(
                v in _GENERATED_CONTENT_ALLOWED_TYPES for v in filt.value
            ):
                _raise(
                    ERR_INVALID_DSL,
                    f"'generated_content' may only be selected for type in "
                    f"{sorted(_GENERATED_CONTENT_ALLOWED_TYPES)} (got {filt.value})",
                )
        else:
            _raise(
                ERR_INVALID_DSL,
                "'generated_content' requires 'type' filter using op '=' or 'in'",
            )


def _enforce_user_users_requires_user_bid_filter(
    table_key: str,
    filters: Sequence[Filter],
) -> None:
    """``user_users`` must be queried by an explicit anchor filter.

    user_users is a global table (no shifu_bid column). To prevent it being
    used as "list every learner's nickname/phone for course X", the caller
    must supply one of:

    - ``user_bid`` filter with op ``=`` or ``in`` (look up a known set), OR
    - ``user_identify`` filter with op ``=`` only (exact phone/email reverse
      lookup — ``in`` is blocked to prevent batch enumeration attacks).
    """

    if table_key != "user_users":
        return

    user_bid_filters = [f for f in filters if f.field == "user_bid"]
    user_identify_filters = [f for f in filters if f.field == "user_identify"]

    if not user_bid_filters and not user_identify_filters:
        _raise(
            ERR_INVALID_DSL,
            "querying 'user_users' requires a 'where' filter on 'user_bid' "
            "(op '=' or 'in') or 'user_identify' (op '=') "
            "(cannot enumerate all learners)",
        )

    for filt in user_bid_filters:
        if filt.op not in {"=", "in"}:
            _raise(
                ERR_INVALID_DSL,
                "user_users.user_bid filter must use op '=' or 'in' "
                f"(got '{filt.op}'); 'like' and ranges are not allowed",
            )

    for filt in user_identify_filters:
        if filt.op != "=":
            _raise(
                ERR_INVALID_DSL,
                "user_users.user_identify filter must use op '=' only "
                f"(got '{filt.op}'); 'in', 'like', and ranges are not allowed "
                "(batch enumeration of registered phone/email is not permitted)",
            )


def _enforce_shifu_meta_table_constraints(
    table_key: str,
    aggregates: Sequence[Aggregate],
    group_by: Sequence[str],
    filters: Sequence[Filter],
) -> None:
    """Block aggregate / group_by on metadata tables and tighten title like.

    The metadata tables are for "what is this course currently called" / "list
    courses I own that match this substring" — pure row lookups. Allowing
    aggregate or group_by would let a caller probe permission edges (e.g.
    ``count_distinct(shifu_bid)`` returns the size of the caller's owned set,
    which is a side channel even without revealing the individual bids).

    The ``title`` column is the only free-text filter target. The generic
    :func:`_validate_filter_value` only blocks leading ``%``; that is too
    permissive for metadata lookups, where the design contract is strict
    prefix matching. Here we additionally reject any ``_`` (SQL single-char
    wildcard) and any ``%`` other than a single trailing one, then require
    at least :data:`_LIKE_MIN_NON_WILDCARD_CHARS` literal characters so a
    caller cannot enumerate with ``like "__%"`` / ``like "a%b"`` / etc.
    """

    if table_key not in _SHIFU_META_TABLES:
        return
    if aggregates:
        _raise(
            ERR_INVALID_DSL,
            f"'{table_key}' does not support 'aggregate' "
            "(metadata tables are row-lookup only)",
        )
    if group_by:
        _raise(
            ERR_INVALID_DSL,
            f"'{table_key}' does not support 'group_by' "
            "(metadata tables are row-lookup only)",
        )
    for filt in filters:
        if filt.field == "title" and filt.op == "like":
            value = filt.value
            # Metadata-table title lookup is strict prefix matching:
            # only an optional trailing '%' wildcard is allowed. Reject any
            # '_' (SQL single-char wildcard) and any '%' that is not the
            # final character, so patterns like "__%" / "a%b" cannot bypass
            # the non-wildcard length floor below.
            if "_" in value or "%" in value[:-1]:
                _raise(
                    ERR_INVALID_DSL,
                    "'title' 'like' only supports an optional trailing '%' "
                    "wildcard (no '_' / no internal '%')",
                )
            non_wildcard = value[:-1] if value.endswith("%") else value
            if len(non_wildcard) < _LIKE_MIN_NON_WILDCARD_CHARS:
                _raise(
                    ERR_INVALID_DSL,
                    f"'title' 'like' requires at least "
                    f"{_LIKE_MIN_NON_WILDCARD_CHARS} non-wildcard characters "
                    "(anti-enumeration guard)",
                )


def _default_alias(fn: str, field_name: Optional[str]) -> str:
    base = field_name or "rows"
    return f"{fn}_{base}"


_ALIAS_ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


def _is_safe_identifier(value: str) -> bool:
    if not value:
        return False
    if value[0].isdigit():
        return False
    return all(ch in _ALIAS_ALLOWED for ch in value)
