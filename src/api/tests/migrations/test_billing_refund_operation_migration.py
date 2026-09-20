"""Verify the refund journal migration preserves data and enforces identity."""

from __future__ import annotations

import importlib.util
import os
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flaskr.service.billing.models import BillingRefundOperation
from flaskr.util.datetime import now_utc
from sqlalchemy.exc import IntegrityError

from tests.migrations.test_fresh_mysql_upgrade import (
    _create_temp_database,
    _drop_temp_database,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

    from sqlalchemy.engine import Engine

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/444f5ed66d94_add_billing_refund_operation_journal.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "refund_journal_migration", MIGRATION_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=["sqlite", "mysql"])
def migration_engine(request: pytest.FixtureRequest) -> Iterator[Engine]:
    """Exercise the same migration against isolated SQLite and MySQL schemas."""
    base_uri = os.getenv("TEST_BILLING_REFUND_MYSQL_URI")
    database_name = None
    if request.param == "mysql":
        if not base_uri:
            pytest.skip(
                "Set TEST_BILLING_REFUND_MYSQL_URI for MySQL migration coverage."
            )
        if not sa.engine.make_url(base_uri).drivername.startswith("mysql"):
            pytest.fail("TEST_BILLING_REFUND_MYSQL_URI must use a MySQL driver")
        uri, database_name = _create_temp_database(base_uri)
    else:
        uri = "sqlite://"
    engine = sa.create_engine(uri)
    try:
        yield engine
    finally:
        engine.dispose()
        if database_name is not None:
            _drop_temp_database(base_uri, database_name)


@pytest.mark.parametrize(
    "duplicate_field", ["bill_order_bid", "refund_operation_bid", "idempotency_key"]
)
def test_migration_enforces_one_operation_and_preserves_existing_records(
    duplicate_field: str,
    monkeypatch: pytest.MonkeyPatch,
    migration_engine: Engine,
) -> None:
    migration = _load_migration()
    engine = migration_engine
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "CREATE TABLE bill_orders (id INTEGER PRIMARY KEY, paid_amount BIGINT)"
                )
            )
            connection.execute(sa.text("INSERT INTO bill_orders VALUES (1, 2500)"))
            monkeypatch.setattr(
                migration, "op", Operations(MigrationContext.configure(connection))
            )
            migration.upgrade()
            inspector = sa.inspect(connection)
            assert set(inspector.get_table_names()) == {
                "bill_orders",
                "bill_refund_operations",
            }
            actual_columns = {
                column["name"]: column
                for column in inspector.get_columns("bill_refund_operations")
            }
            assert set(actual_columns) == set(
                BillingRefundOperation.__table__.columns.keys()
            )
            for name in ("created_at", "updated_at", "submitted_at", "finalized_at"):
                assert actual_columns[name]["default"] is None
            assert not inspector.get_foreign_keys("bill_refund_operations")

            journal = sa.Table(
                "bill_refund_operations", sa.MetaData(), autoload_with=connection
            )
            values = {
                "refund_operation_bid": "refund-operation-1",
                "bill_order_bid": "billing-order-1",
                "creator_bid": "teacher-1",
                "payment_provider": "stripe",
                "amount": 2500,
                "payment_amount": 2500,
                "currency": "USD",
                "reason": "requested_by_customer",
                "payment_intent_id": "pi_journal",
                "charge_id": "ch_journal",
                "idempotency_key": "billing-refund-operation-1",
                "product_bid": "product-1",
                "subscription_bid": "",
                "order_type": 7304,
                "credit_amount": 10,
                "provider_refund_id": "",
                "provider_status": "",
                "provider_result_version": 0,
                "provider_payload": None,
                "status": "submitted",
                "submitted_at": now_utc(),
                "finalized_at": None,
                "deleted": 0,
                "created_at": now_utc(),
                "updated_at": now_utc(),
            }
            connection.execute(journal.insert().values(**values))
            duplicate = {
                **values,
                "refund_operation_bid": "refund-operation-2",
                "bill_order_bid": "billing-order-2",
                "idempotency_key": "billing-refund-operation-2",
            }
            duplicate[duplicate_field] = values[duplicate_field]
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(journal.insert().values(**duplicate))
            assert (
                connection.execute(
                    sa.select(sa.func.count()).select_from(journal)
                ).scalar_one()
                == 1
            )
            assert (
                connection.execute(
                    sa.text("SELECT paid_amount FROM bill_orders WHERE id=1")
                ).scalar_one()
                == 2500
            )

            migration.downgrade()
            assert sa.inspect(connection).get_table_names() == ["bill_orders"]
            assert (
                connection.execute(
                    sa.text("SELECT paid_amount FROM bill_orders WHERE id=1")
                ).scalar_one()
                == 2500
            )
            migration.upgrade()
            assert "bill_refund_operations" in sa.inspect(connection).get_table_names()
    finally:
        engine.dispose()


def test_migration_renders_mysql_journal_without_unrelated_schema_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="mysql",
        opts={"as_sql": True, "output_buffer": output},
    )
    monkeypatch.setattr(migration, "op", Operations(context))
    migration.upgrade()
    sql = output.getvalue()
    assert "CREATE TABLE bill_refund_operations" in sql
    assert "AUTO_INCREMENT" in sql
    assert "uq_bill_refund_operations_bill_order_bid" in sql
    assert "uq_bill_refund_operations_idempotency_key" in sql
    assert "notification_records" not in sql
    assert "CURRENT_TIMESTAMP" not in sql
    assert "FOREIGN KEY" not in sql


def test_journal_timestamp_defaults_use_shared_utc_clock() -> None:
    table = BillingRefundOperation.__table__
    assert table.c.created_at.default.arg.__wrapped__ is now_utc
    assert table.c.updated_at.default.arg.__wrapped__ is now_utc
    assert table.c.updated_at.onupdate.arg.__wrapped__ is now_utc
