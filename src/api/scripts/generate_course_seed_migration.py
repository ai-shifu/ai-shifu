"""Extract course data from the current database and generate a seed migration file.

Usage:
    cd src/api
    .venv/Scripts/python.exe scripts/generate_course_seed_migration.py <migration_name>

This script:
1. Connects to the configured database via Flask app context
2. Extracts all rows from course-related tables
3. Generates an Alembic migration file with DELETE + INSERT statements
4. The generated migration can be run on another instance (e.g., Mac) to sync data

The generated migration is idempotent: it first deletes existing rows for the
same shifu_bid values, then inserts the fresh data.
"""

import sys
import json
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path


# Core tables to extract (excludes log/snapshot tables which are too large)
COURSE_TABLES = [
    "shifu_draft_shifus",
    "shifu_published_shifus",
    "shifu_draft_outline_items",
    "shifu_published_outline_items",
    "scenario_resource",
]


def to_sql_literal(value):
    """Convert a value to a SQL literal string."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        inner = value.replace("'", "''")
        return f"'{inner}'"
    if isinstance(value, datetime):
        return f"'{value.strftime('%Y-%m-%d %H:%M:%S')}'"
    if isinstance(value, date):
        return f"'{value.strftime('%Y-%m-%d %H:%M:%S')}'"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (dict, list)):
        inner = json.dumps(value, ensure_ascii=False).replace("'", "''")
        return f"'{inner}'"
    inner = str(value).replace("'", "''")
    return f"'{inner}'"


def generate_migration_file(app, migration_name):
    """Extract course data and generate a migration file."""
    import re
    import uuid

    versions_dir = Path(__file__).parent.parent / "migrations" / "versions"

    # Find the current head revision
    revisions = {}
    for f in sorted(versions_dir.glob("*.py")):
        content = f.read_text(encoding="utf-8")
        rev_match = re.search(r'^revision = "([^"]+)"', content, re.M)
        dn_match = re.search(r'^down_revision = (?:None|"([^"]+)")', content, re.M)
        if rev_match:
            rev = rev_match.group(1)
            dn = dn_match.group(1) if dn_match else None
            revisions[rev] = dn

    all_revs = set(revisions.keys())
    all_down = set(revisions.values())
    head = list(all_revs - all_down)
    if not head:
        print("ERROR: Could not determine migration head")
        sys.exit(1)
    head_rev = head[0]

    print(f"Migration chain head: {head_rev}")

    # Extract data within Flask app context
    with app.app_context():
        from flaskr.dao import db

        tables_data = {}
        total_rows = 0
        shifu_bids = set()

        for table_name in COURSE_TABLES:
            result = db.session.execute(db.text(f"SELECT * FROM {table_name}"))
            rows = result.fetchall()
            columns = list(result.keys())

            print(f"  {table_name}: {len(rows)} rows")

            if rows:
                tables_data[table_name] = {
                    "columns": columns,
                    "rows": [
                        {col: row[i] for i, col in enumerate(columns)} for row in rows
                    ],
                }
                total_rows += len(rows)

                # Collect shifu_bid values (skip tables without shifu_bid column)
                for row in rows:
                    bid = row._mapping.get("shifu_bid")
                    if bid:
                        shifu_bids.add(bid)

        if total_rows == 0:
            print("\nNo data found in any course table. Nothing to generate.")
            sys.exit(1)

        print(f"\nFound shifu_bids: {shifu_bids}")

        # Separate tables: those with shifu_bid vs those that need subquery DELETE
        tables_with_shifu_bid = []
        tables_without_shifu_bid = []
        for table_name in COURSE_TABLES:
            cols = tables_data.get(table_name, {}).get("columns", [])
            if "shifu_bid" in cols:
                tables_with_shifu_bid.append(table_name)
            else:
                tables_without_shifu_bid.append(table_name)

        # Generate DELETE + INSERT statements
        lines = []

        # DELETE existing data for tables that have shifu_bid
        lines.append("    # Delete existing data for the same shifu_bids")
        lines.append(f"    shifu_bids = {repr(list(shifu_bids))}")
        if tables_with_shifu_bid:
            lines.append("    for table_name in [")
            for table_name in tables_with_shifu_bid:
                lines.append(f'        "{table_name}",')
            lines.append("    ]:")
            lines.append("        bind.execute(")
            lines.append(
                '            sa.text(f"DELETE FROM {table_name} WHERE shifu_bid IN :bids")'
            )
            lines.append(
                "            .bindparams(sa.bindparam('bids', expanding=True)),"
            )
            lines.append("            {'bids': shifu_bids}")
            lines.append("        )")
            lines.append("")

        # DELETE for tables without shifu_bid (use scenario_id subquery)
        for table_name in tables_without_shifu_bid:
            lines.append(f"    # Delete {table_name} rows linked via scenario_id")
            lines.append("    bind.execute(")
            lines.append("        sa.text(")
            lines.append(
                '            f"DELETE FROM {table_name} WHERE scenario_id IN :bids"'
            )
            lines.append("        ).bindparams(sa.bindparam('bids', expanding=True)),")
            lines.append("        {'bids': shifu_bids}")
            lines.append("    )")
            lines.append("")

        for table_name, data in tables_data.items():
            columns = data["columns"]
            rows = data["rows"]

            cols_sql = ", ".join([f"`{c}`" for c in columns])

            lines.append(f"    # --- {table_name}: {len(rows)} rows ---")
            for row in rows:
                sql_vals = []
                for col in columns:
                    val = row.get(col)
                    sql_vals.append(to_sql_literal(val))
                vals_str = ",\n            ".join(sql_vals)
                lines.append(
                    f'    bind.execute(sa.text("""INSERT INTO {table_name} ({cols_sql}) VALUES (\n'
                    f"            {vals_str}\n"
                    f'        )"""))'
                )

        inserts_block = "\n".join(lines)
        table_names_str = ", ".join(tables_data.keys())

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.000000")
        new_rev_id = uuid.uuid4().hex[:12]

        migration_content = f'''"""seed course data ({table_names_str}, {total_rows} rows total)

Revision ID: {new_rev_id}
Revises: {head_rev}
Create Date: {now}

NOTE:
    This migration was auto-generated by scripts/generate_course_seed_migration.py
    to seed course data from a source database. Run `flask db upgrade` on the
    target instance to sync the data.

    The migration is idempotent: it deletes existing rows for the same shifu_bid
    values before inserting fresh data.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "{new_rev_id}"
down_revision = "{head_rev}"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
{inserts_block}


def downgrade():
    # NOTE: This downgrade removes all seeded data for the same shifu_bids.
    pass
'''

        # Write migration file
        migration_path = versions_dir / f"{new_rev_id}_{migration_name}.py"
        migration_path.write_text(migration_content, encoding="utf-8")
        print(
            f"\nMigration file generated: migrations/versions/{new_rev_id}_{migration_name}.py"
        )
        print(f"Total rows extracted: {total_rows}")
        print("\nTo sync data on Mac: cd src/api && flask db upgrade")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print(
            "Usage: python scripts/generate_course_seed_migration.py <migration_name>"
        )
        print(
            "Example: python scripts/generate_course_seed_migration.py seed_course_data"
        )
        sys.exit(1)

    migration_name = sys.argv[1]
    # Sanitize migration name
    migration_name = migration_name.replace("_", "").replace("-", "")
    migration_name = "".join(c for c in migration_name if c.isalnum() or c == "_")

    # Import Flask app
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from app import create_app

    app = create_app()
    generate_migration_file(app, migration_name)


if __name__ == "__main__":
    main()
