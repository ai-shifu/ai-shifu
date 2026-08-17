#!/usr/bin/env python3
"""
Migrate OSS domain names in the database.

Replaces occurrences of the old OSS base URL with a new one across all
relevant tables and columns.

Usage:
    # Dry run (show what would change, no writes)
    python scripts/migrate_oss_domain.py \\
        --old-url https://resource.ai-shifu.cn \\
        --new-url https://res.ai-shifu.cn

    # Apply changes
    python scripts/migrate_oss_domain.py --apply \\
        --old-url https://resource.ai-shifu.cn \\
        --new-url https://res.ai-shifu.cn

Environment variables (DB connection):
    DATABASE_URL                   -> SQLAlchemy connection string (highest priority)
    DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME  -> fallback DB config

Notes:
    - Runs as a single transaction; any error causes a full rollback.
    - Large tables are updated in batches of --batch-size rows to avoid lock contention.
    - DB credentials are masked in terminal output.
    - After running, remember to flush any application-layer / CDN caches that
      may still hold the old URLs.
"""

import argparse
import logging
import os
import re
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tables / columns that may contain OSS URLs
# Each entry: (table, column, is_content)
#   is_content=True  -> column may contain embedded URLs inside larger text
#   is_content=False -> column stores a bare URL
# ---------------------------------------------------------------------------
TARGETS: list[tuple[str, str, bool]] = [
    # course outline content (MarkdownFlow – may embed multiple image URLs)
    ("shifu_draft_outline_items", "content", True),
    ("shifu_published_outline_items", "content", True),
    # course resource references
    ("scenario_resource", "url", False),
    # generic resource table
    ("resource", "url", False),
    # TTS audio
    ("learn_generated_audios", "oss_url", False),
    # user avatar
    ("user_users", "avatar", False),
]

_ALLOWED_TABLES = {t for t, _, _ in TARGETS}
_ALLOWED_COLUMNS = {c for _, c, _ in TARGETS}

DEFAULT_BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mask_url(url: str) -> str:
    """Replace credentials in a DB URL with ***."""
    return re.sub(r"(?<=://)[^:@]+:[^@]+@", "***:***@", url)


def get_db_url(args: argparse.Namespace) -> str:
    if args.db_url:
        return args.db_url
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        return explicit
    host = os.getenv("DB_HOST", "127.0.0.1")
    port = os.getenv("DB_PORT", "3306")
    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "")
    name = os.getenv("DB_NAME", "")
    if not name:
        log.error(
            "Database name is not set. "
            "Provide DB_NAME env var, DATABASE_URL, or --db-url."
        )
        sys.exit(1)
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"


# ---------------------------------------------------------------------------
# Core migration
# ---------------------------------------------------------------------------


def migrate(
    apply: bool,
    old_url: str,
    new_url: str,
    db_url: str,
    batch_size: int,
) -> None:
    try:
        import sqlalchemy as sa
    except ImportError:
        sys.exit("sqlalchemy is required: pip install sqlalchemy pymysql")

    engine = sa.create_engine(db_url, echo=False)
    total_rows = 0
    pat = f"%{old_url}%"

    # Single transaction: if anything fails, everything rolls back.
    with engine.begin() as conn:
        for table, column, is_content in TARGETS:
            # Whitelist check (defence-in-depth; values come from the constant above)
            assert table in _ALLOWED_TABLES, f"Unknown table: {table!r}"
            assert column in _ALLOWED_COLUMNS, f"Unknown column: {column!r}"

            # Check table exists in this deployment
            exists = conn.execute(
                sa.text("SHOW TABLES LIKE :t"), {"t": table}
            ).fetchone()
            if not exists:
                log.info("skip  %s.%s — table not found", table, column)
                continue

            count: int = (
                conn.execute(
                    sa.text(
                        f"SELECT COUNT(*) FROM `{table}` WHERE `{column}` LIKE :pat"
                    ),
                    {"pat": pat},
                ).scalar()
                or 0
            )

            if count == 0:
                continue

            label = "[apply]" if apply else "[dry-run]"
            suffix = " (embedded URLs)" if is_content else ""
            log.info(
                "%s  %s.%s: %d row(s)%s",
                label,
                table,
                column,
                count,
                suffix,
            )

            if apply:
                updated = 0
                while True:
                    result = conn.execute(
                        sa.text(
                            f"UPDATE `{table}` SET `{column}` = "
                            f"REPLACE(`{column}`, :old, :new) "
                            f"WHERE `{column}` LIKE :pat "
                            f"LIMIT :lim"
                        ),
                        {"old": old_url, "new": new_url, "pat": pat, "lim": batch_size},
                    )
                    updated += result.rowcount
                    if result.rowcount < batch_size:
                        break
                    log.info("  ... %d rows updated so far", updated)

            total_rows += count

    if total_rows == 0:
        log.info("Nothing to migrate — no matching rows found.")
    else:
        action = "Updated" if apply else "Would update"
        log.info("%s %d row(s) total.", action, total_rows)
        if not apply:
            log.info("Run with --apply to commit changes.")
        else:
            log.warning(
                "Migration complete. "
                "Remember to flush application caches / CDN that may still "
                "serve the old URLs."
            )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to the database (default: dry run)",
    )
    parser.add_argument(
        "--old-url",
        required=True,
        help="Old OSS base URL to replace (e.g. https://resource.ai-shifu.cn)",
    )
    parser.add_argument(
        "--new-url",
        required=True,
        help="New OSS base URL (e.g. https://res.ai-shifu.cn)",
    )
    parser.add_argument(
        "--db-url",
        default="",
        help="SQLAlchemy DB URL (overrides DATABASE_URL env and DB_* vars)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Rows per UPDATE batch (default: {DEFAULT_BATCH_SIZE})",
    )
    args = parser.parse_args()

    old_url = args.old_url.rstrip("/")
    new_url = args.new_url.rstrip("/")

    if old_url == new_url:
        log.error("--old-url and --new-url are the same, nothing to do.")
        sys.exit(1)

    db_url = get_db_url(args)

    log.info("Mode:    %s", "APPLY" if args.apply else "DRY RUN")
    log.info("DB:      %s", _mask_url(db_url))
    log.info("Replace: %r  ->  %r", old_url, new_url)

    migrate(args.apply, old_url, new_url, db_url, args.batch_size)


if __name__ == "__main__":
    main()
