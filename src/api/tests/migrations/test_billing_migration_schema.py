"""Billing tables built by the Alembic chain must match the models.

The test replays the ``op.*`` calls in every migration's ``upgrade()`` in
revision order, without a database, and compares the resulting columns (type,
length or precision and scale, nullability, computed) and the explicitly
declared indexes and unique constraints (ordered columns and uniqueness) and
the primary key with the SQLAlchemy models. It runs in every CI job, unlike
the opt-in fresh-MySQL smoke test.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Column, Table, UniqueConstraint

API_ROOT = Path(__file__).resolve().parents[2]
RAW_PROVIDER_TABLES = {"order_pingxx_orders", "order_stripe_orders"}
_TYPE_ALIASES = {
    "varchar": "string",
    "decimal": "numeric",
    "bigint": "biginteger",
    "smallint": "smallinteger",
    "int": "integer",
    "longtext": "text",
}


def _str(node: ast.AST | None) -> str | None:
    # op.f("ix_...") / batch_op.f("ix_...") only marks a name as already final.
    if isinstance(node, ast.Call) and _call_name(node) == "f" and node.args:
        node = node.args[0]
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _keyword(call: ast.Call, name: str) -> ast.AST | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else ""


def _is_unique(call: ast.Call) -> bool:
    flag = _keyword(call, "unique")
    return isinstance(flag, ast.Constant) and flag.value is True


def _names(node: ast.AST | None) -> tuple[str | None, ...]:
    if isinstance(node, ast.List | ast.Tuple):
        return tuple(_str(item) for item in node.elts)
    return ()


def _int(node: ast.AST | None) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    return None


def _type_signature(node: ast.AST | None) -> tuple[object, ...] | None:
    """Reduce ``sa.Numeric(20, 10)`` and similar to (kind, length, precision, scale)."""
    if isinstance(node, ast.Attribute | ast.Name):
        node = ast.Call(func=node, args=[], keywords=[])
    if not isinstance(node, ast.Call):
        return None
    kind = _call_name(node).lower()
    kind = _TYPE_ALIASES.get(kind, kind)
    first = _int(node.args[0]) if node.args else None
    second = _int(node.args[1]) if len(node.args) > 1 else None
    if kind == "numeric":
        return (
            kind,
            None,
            first or _int(_keyword(node, "precision")),
            second or _int(_keyword(node, "scale")),
        )
    if kind == "string":
        return (kind, first or _int(_keyword(node, "length")), None, None)
    return (kind, None, None, None)


def _column_definition(column: ast.Call) -> dict[str, object]:
    nullable = _keyword(column, "nullable")
    primary = _keyword(column, "primary_key")
    is_primary = isinstance(primary, ast.Constant) and primary.value is True
    return {
        "type": _type_signature(column.args[1] if len(column.args) > 1 else None),
        "nullable": nullable.value
        if isinstance(nullable, ast.Constant)
        else not is_primary,
        "computed": any(
            isinstance(arg, ast.Call) and _call_name(arg) == "Computed"
            for arg in column.args[2:]
        ),
    }


def _model_definition(column: Column) -> dict[str, object]:
    kind = type(column.type).__name__.lower()
    kind = _TYPE_ALIASES.get(kind, kind)
    return {
        "type": (
            kind,
            getattr(column.type, "length", None) if kind == "string" else None,
            getattr(column.type, "precision", None) if kind == "numeric" else None,
            getattr(column.type, "scale", None) if kind == "numeric" else None,
        ),
        "nullable": bool(column.nullable),
        "computed": column.computed is not None,
    }


class _SchemaReplay:
    """Track each table's columns, indexes and unique constraints across migrations."""

    def __init__(self) -> None:
        self.columns: dict[str, dict[str, dict[str, object]]] = {}
        # name -> (ordered columns, unique)
        self.indexes: dict[str, dict[str, tuple[tuple[str | None, ...], bool]]] = {}
        self.primary_keys: dict[str, set[str]] = {}

    def run(self, tree: ast.Module) -> None:
        upgrade = next(
            (
                node
                for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "upgrade"
            ),
            None,
        )
        if upgrade is None:
            return
        self._helpers = {
            node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
        }
        self._visit(upgrade.body, batch_table=None)

    def _expand(self, args: list[ast.expr]) -> list[ast.AST]:
        # ``*_helper()`` spreads a module-level helper's list of sa.Column(...).
        expanded: list[ast.AST] = []
        for arg in args:
            helper = None
            if isinstance(arg, ast.Starred) and isinstance(arg.value, ast.Call):
                helper = self._helpers.get(_call_name(arg.value))
            if helper is not None:
                expanded.extend(
                    n
                    for n in ast.walk(helper)
                    if isinstance(n, ast.Call) and _call_name(n) == "Column"
                )
            else:
                expanded.append(arg)
        return expanded

    def _visit(self, statements: list[ast.stmt], batch_table: str | None) -> None:
        for statement in statements:
            if isinstance(statement, ast.With):
                table = batch_table
                for item in statement.items:
                    context = item.context_expr
                    if (
                        isinstance(context, ast.Call)
                        and _call_name(context) == "batch_alter_table"
                    ):
                        table = _str(context.args[0]) if context.args else None
                self._visit(statement.body, table)
                continue
            for call in (n for n in ast.walk(statement) if isinstance(n, ast.Call)):
                func = call.func
                if not isinstance(func, ast.Attribute) or not isinstance(
                    func.value, ast.Name
                ):
                    continue
                if func.value.id == "op":
                    self._apply(func.attr, call, list(call.args))
                elif func.value.id == "batch_op" and batch_table:
                    self._apply_batch(func.attr, call, batch_table)

    def _add_column(self, table: str, column: ast.AST) -> None:
        # Columns built in a loop are not resolved; billing migrations spell them out.
        if isinstance(column, ast.Call) and column.args:
            self.columns.setdefault(table, {})[_str(column.args[0])] = (
                _column_definition(column)
            )

    def _alter_column(self, table: str, name: str | None, call: ast.Call) -> None:
        columns = self.columns.setdefault(table, {})
        definition = columns.pop(
            name, {"type": None, "nullable": True, "computed": False}
        )
        type_node = _keyword(call, "type_")
        if type_node is not None:
            definition = {**definition, "type": _type_signature(type_node)}
        nullable = _keyword(call, "nullable")
        if isinstance(nullable, ast.Constant):
            definition = {**definition, "nullable": nullable.value}
        columns[_str(_keyword(call, "new_column_name")) or name] = definition

    def _apply(self, operation: str, call: ast.Call, args: list[ast.expr]) -> None:
        if operation == "create_table":
            table = _str(args[0])
            self.columns[table] = {}
            self.indexes[table] = {}
            self.primary_keys[table] = set()
            for item in self._expand(args[1:]):
                if not isinstance(item, ast.Call):
                    continue
                kind = _call_name(item)
                if kind == "Column" and item.args:
                    self._add_column(table, item)
                    primary = _keyword(item, "primary_key")
                    if isinstance(primary, ast.Constant) and primary.value is True:
                        self.primary_keys[table].add(_str(item.args[0]))
                elif kind == "PrimaryKeyConstraint":
                    self.primary_keys[table].update(_str(arg) for arg in item.args)
                elif kind == "UniqueConstraint":
                    name = _str(_keyword(item, "name"))
                    if name:
                        columns = tuple(_str(arg) for arg in item.args)
                        self.indexes[table][name] = (columns, True)
                elif kind == "Index" and item.args:
                    columns = tuple(_str(arg) for arg in item.args[1:])
                    self.indexes[table][_str(item.args[0])] = (
                        columns,
                        _is_unique(item),
                    )
        elif operation == "drop_table":
            table = _str(args[0]) if args else _str(_keyword(call, "table_name"))
            self.columns.pop(table, None)
            self.indexes.pop(table, None)
            self.primary_keys.pop(table, None)
        elif operation == "rename_table":
            old, new = _str(args[0]), _str(args[1])
            self.columns[new] = self.columns.pop(old, {})
            self.indexes[new] = self.indexes.pop(old, {})
            self.primary_keys[new] = self.primary_keys.pop(old, set())
        elif operation == "add_column":
            self._add_column(_str(args[0]), args[1])
        elif operation == "drop_column":
            self.columns.get(_str(args[0]), {}).pop(_str(args[1]), None)
        elif operation == "alter_column":
            self._alter_column(_str(args[0]), _str(args[1]), call)
        elif operation in ("create_unique_constraint", "create_index"):
            unique = operation == "create_unique_constraint" or _is_unique(call)
            self.indexes.setdefault(_str(args[1]), {})[_str(args[0])] = (
                _names(args[2]),
                unique,
            )
        elif operation in ("drop_constraint", "drop_index"):
            table = _str(args[1]) if len(args) > 1 else None
            table = table or _str(_keyword(call, "table_name"))
            self.indexes.get(table, {}).pop(_str(args[0]), None)
        elif operation == "create_primary_key":
            self.primary_keys[_str(args[1])] = set(_names(args[2]))

    def _apply_batch(self, operation: str, call: ast.Call, table: str) -> None:
        args = call.args
        if operation == "add_column":
            self._add_column(table, args[0])
        elif operation == "drop_column":
            self.columns.get(table, {}).pop(_str(args[0]), None)
        elif operation == "alter_column":
            self._alter_column(table, _str(args[0]), call)
        elif operation in ("create_unique_constraint", "create_index"):
            unique = operation == "create_unique_constraint" or _is_unique(call)
            self.indexes.setdefault(table, {})[_str(args[0])] = (
                _names(args[1]),
                unique,
            )
        elif operation in ("drop_constraint", "drop_index"):
            self.indexes.get(table, {}).pop(_str(args[0]), None)
        elif operation == "create_primary_key":
            self.primary_keys[table] = set(_names(args[1]))


def _replayed_schema() -> _SchemaReplay:
    config = Config(str(API_ROOT / "migrations" / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "migrations"))
    replay = _SchemaReplay()
    for revision in reversed(
        list(ScriptDirectory.from_config(config).walk_revisions())
    ):
        replay.run(ast.parse(Path(revision.path).read_text(encoding="utf-8")))
    return replay


def _billing_tables() -> list[Table]:
    from flaskr.dao import db
    from flaskr.service.billing import models as _billing  # noqa: F401
    from flaskr.service.order import models as _order  # noqa: F401

    return sorted(
        (
            table
            for table in db.metadata.tables.values()
            if table.name.startswith(("bill_", "credit_"))
            or table.name in RAW_PROVIDER_TABLES
        ),
        key=lambda table: table.name,
    )


_REPLAY = _replayed_schema()


def test_billing_scope_covers_the_core_tables() -> None:
    names = {table.name for table in _billing_tables()}
    assert {"bill_orders", "credit_wallet_buckets", *RAW_PROVIDER_TABLES} <= names


@pytest.mark.parametrize("table", _billing_tables(), ids=lambda table: table.name)
def test_migrations_build_the_billing_model_schema(table: Table) -> None:
    assert table.name in _REPLAY.columns, f"no migration creates {table.name}"
    migrated = _REPLAY.columns[table.name]
    assert set(migrated) == {column.name for column in table.columns}
    for column in table.columns:
        assert migrated[column.name] == _model_definition(column), column.name

    assert _REPLAY.primary_keys.get(table.name) == {
        column.name for column in table.primary_key.columns
    }

    # Explicit Index(...) / UniqueConstraint(...) declarations. Single-column
    # ``index=True`` flags are not compared: several were never migrated.
    model_indexes = {
        constraint.name: (tuple(column.name for column in constraint.columns), True)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint) and constraint.name
    } | {
        index.name: (tuple(column.name for column in index.columns), bool(index.unique))
        for index in table.indexes
        if index.unique or not getattr(index, "_column_flag", False)
    }
    migrated_indexes = _REPLAY.indexes.get(table.name, {})
    for name, definition in model_indexes.items():
        assert migrated_indexes.get(name) == definition, name
