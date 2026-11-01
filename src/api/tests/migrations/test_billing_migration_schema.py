"""Billing tables built by the Alembic chain must match the models.

The test replays the ``op.*`` calls in every migration's ``upgrade()`` in
revision order, without a database, and compares the resulting columns and
unique constraints with the SQLAlchemy models. It runs in every CI job, unlike
the opt-in fresh-MySQL smoke test.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Table, UniqueConstraint

API_ROOT = Path(__file__).resolve().parents[2]
RAW_PROVIDER_TABLES = {"order_pingxx_orders", "order_stripe_orders"}


def _str(node: ast.AST | None) -> str | None:
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


class _SchemaReplay:
    """Track table columns and unique constraint names across migrations."""

    def __init__(self) -> None:
        self.columns: dict[str, set[str]] = {}
        self.uniques: dict[str, set[str]] = {}

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
                expanded.extend(n for n in ast.walk(helper) if isinstance(n, ast.Call))
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
                    self._apply(func.attr, call, call.args)
                elif func.value.id == "batch_op" and batch_table:
                    self._apply(
                        func.attr, call, [ast.Constant(batch_table), *call.args]
                    )

    def _apply(self, operation: str, call: ast.Call, args: list[ast.expr]) -> None:
        table = _str(args[0]) if args else _str(_keyword(call, "table_name"))
        if operation == "create_table":
            self.columns[table] = set()
            self.uniques[table] = set()
            for item in self._expand(args[1:]):
                if (
                    isinstance(item, ast.Call)
                    and item.args
                    and _call_name(item) == "Column"
                ):
                    self.columns[table].add(_str(item.args[0]))
                if (
                    isinstance(item, ast.Call)
                    and _call_name(item) == "UniqueConstraint"
                ):
                    name = _str(_keyword(item, "name"))
                    if name:
                        self.uniques[table].add(name)
        elif operation == "drop_table":
            self.columns.pop(table, None)
            self.uniques.pop(table, None)
        elif operation == "rename_table":
            new = _str(args[1])
            self.columns[new] = self.columns.pop(table, set())
            self.uniques[new] = self.uniques.pop(table, set())
        elif operation == "add_column":
            column = args[1]
            # Columns built in a loop are not resolved; billing migrations spell them out.
            if isinstance(column, ast.Call) and column.args:
                self.columns.setdefault(table, set()).add(_str(column.args[0]))
        elif operation == "drop_column":
            self.columns.get(table, set()).discard(_str(args[1]))
        elif operation == "alter_column":
            new = _str(_keyword(call, "new_column_name"))
            if new:
                self.columns.get(table, set()).discard(_str(args[1]))
                self.columns.setdefault(table, set()).add(new)
        elif operation == "create_unique_constraint" or (
            operation == "create_index" and _is_unique(call)
        ):
            # op takes the constraint name then the table; batch_op only the name.
            name, target = (
                (_str(args[1]), table)
                if call.func.value.id == "batch_op"
                else (_str(args[0]), _str(args[1]))
            )
            self.uniques.setdefault(target, set()).add(name)
        elif operation in ("drop_constraint", "drop_index"):
            if call.func.value.id == "batch_op":
                name, target = _str(args[1]), table
            else:
                name = _str(args[0])
                target = _str(args[1]) if len(args) > 1 else None
                target = target or _str(_keyword(call, "table_name"))
            self.uniques.get(target, set()).discard(name)


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
    model_columns = {column.name for column in table.columns}
    assert model_columns == _REPLAY.columns[table.name]

    model_uniques = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint) and constraint.name
    } | {index.name for index in table.indexes if index.unique}
    assert model_uniques <= _REPLAY.uniques.get(table.name, set())
