#!/usr/bin/env python3
"""Repair known non-transactional migration residue in the dev database."""

from __future__ import annotations

from pathlib import Path
import sys

from sqlalchemy import inspect, text

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app import create_app  # noqa: E402
from flaskr.dao import db  # noqa: E402


TARGET_REVISION = "9f3a0c3aebe0"
TARGET_TABLE = "profile_item"
TARGET_COLUMN = "is_hidden"
TARGET_INDEX = "ix_profile_item_is_hidden"


def main() -> int:
    app = create_app()
    with app.app_context():
        bind = db.session.get_bind()
        inspector = inspect(bind)
        tables = set(inspector.get_table_names())
        if TARGET_TABLE not in tables or "alembic_version" not in tables:
            print("No migration repair needed: missing target tables.")
            return 0

        version_rows = (
            db.session.execute(text("SELECT version_num FROM alembic_version"))
            .scalars()
            .all()
        )
        if TARGET_REVISION in version_rows:
            print(f"No migration repair needed: {TARGET_REVISION} already applied.")
            return 0

        columns = {column["name"] for column in inspector.get_columns(TARGET_TABLE)}
        if TARGET_COLUMN not in columns:
            print("No migration repair needed: transient column absent.")
            return 0

        indexes = {index["name"] for index in inspector.get_indexes(TARGET_TABLE)}
        if TARGET_INDEX in indexes:
            db.session.execute(
                text(f"ALTER TABLE {TARGET_TABLE} DROP INDEX {TARGET_INDEX}")
            )
            print(f"Dropped transient index {TARGET_TABLE}.{TARGET_INDEX}.")

        db.session.execute(
            text(f"ALTER TABLE {TARGET_TABLE} DROP COLUMN {TARGET_COLUMN}")
        )
        db.session.commit()
        print(
            "Dropped transient migration residue "
            f"{TARGET_TABLE}.{TARGET_COLUMN} before rerunning Alembic."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
