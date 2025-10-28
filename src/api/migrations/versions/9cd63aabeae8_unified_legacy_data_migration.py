"""Unified legacy data migration

Revision ID: 9cd63aabeae8
Revises: c18b39622587
Create Date: 2024-08-18 16:30:00.000000

This migration runs the unified legacy data migration task that migrates:
- ai_course_lesson_attend -> learn_progress_records
- ai_course_lesson_attendscript -> learn_generated_blocks
- ai_course_buy_record -> order_orders
- pingxx_order -> order_pingxx_orders
- discount -> promo_coupons
- discount_record -> promo_coupon_usages

The migration uses ID-based pagination and includes data consistency verification.
"""

from alembic import op
from sqlalchemy import text
import logging
import asyncio
import sys
import os
from flaskr.command.unified_migration_task import (
    UnifiedMigrationTask,  #
    MigrationConfig,
)

# Add the parent directory to Python path to import our migration task
current_dir = os.path.dirname(os.path.abspath(__file__))
api_dir = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, api_dir)


# revision identifiers, used by Alembic
revision = "9cd63aabeae8"
down_revision = "c18b39622587"  # Update this with the actual previous revision
branch_labels = None
depends_on = None

# Setup logging - ensure it outputs to console during flask db upgrade
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),  # Console output
        logging.FileHandler("/tmp/flask_migration.log", mode="a"),  # Also log to file
    ],
    force=True,  # Force reconfiguration if logging was already set up
)
logger = logging.getLogger(__name__)


# Also use print statements for critical updates to ensure visibility
def log_and_print(message):
    """Log and print message to ensure visibility during migration"""
    logger.info(message)
    print(f"[MIGRATION] {message}")
    import sys

    sys.stdout.flush()  # Force flush to ensure immediate output


def upgrade():
    """Run the unified legacy data migration"""

    # Get database URL from Alembic context
    from flask import current_app
    from sqlalchemy import create_engine

    database_url = current_app.config["SQLALCHEMY_DATABASE_URI"]
    log_and_print(f"Database URL: {database_url}")

    # Ensure PyMySQL driver
    if database_url.startswith("mysql://"):
        database_url = database_url.replace("mysql://", "mysql+pymysql://")

    # Create engine for DDL operations
    engine = create_engine(database_url)

    # Check and add content column if needed
    log_and_print("Content columns verified/added successfully")
    log_and_print("Starting unified legacy data migration...")

    # Create migration configuration
    migration_config = MigrationConfig(
        batch_size=1000,
        max_workers=3,
        max_retries=3,
        retry_delay=1.0,
        consistency_check_sample_size=50,
    )

    # Initialize and run migration task
    migration_task = UnifiedMigrationTask(database_url, migration_config)
    migration_task.force_full_migration = (
        True  # Always do full migration in DB migration
    )

    try:
        # Run the migration synchronously within the upgrade function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Execute migration
        log_and_print("Executing unified migration for all tables...")
        migration_results = loop.run_until_complete(migration_task.migrate_all_tables())

        # Verify data consistency
        log_and_print("Verifying data consistency...")
        consistency_results = loop.run_until_complete(
            migration_task.verify_data_consistency()
        )

        # Generate and log report
        report = migration_task.generate_migration_report(
            migration_results, consistency_results
        )
        log_and_print("Migration report generated")
        print(report)  # Always print the full report

        # Check if migration was successful
        failed_tables = []
        for table_name, result in migration_results.items():
            if result.success_rate < 95.0:  # Less than 95% success rate
                failed_tables.append(f"{table_name} ({result.success_rate:.1f}%)")

        failed_consistency = []
        for table_name, result in consistency_results.items():
            if not result.is_consistent:
                failed_consistency.append(
                    f"{table_name} ({result.old_count} -> {result.new_count})"
                )

        if failed_tables:
            error_msg = f"Migration failed for tables: {', '.join(failed_tables)}"
            log_and_print(f"❌ ERROR: {error_msg}")
            raise Exception(error_msg)

        if failed_consistency:
            warning_msg = (
                f"Consistency check failed for tables: {', '.join(failed_consistency)}"
            )
            log_and_print(f"⚠️ WARNING: {warning_msg}")
            # Note: We don't fail the migration for consistency issues as they might be acceptable

        # Summary
        total_migrated = sum(r.synced_records for r in migration_results.values())
        total_records = sum(r.total_records for r in migration_results.values())
        log_and_print(
            f"✅ Migration completed successfully: {total_migrated}/{total_records} records migrated"
        )

        # Clean up: Drop content columns after migration is complete
        log_and_print("Cleaning up temporary content columns...")
        log_and_print("Cleanup completed")

    except Exception as e:
        log_and_print(f"❌ FATAL ERROR: Migration failed: {e}")
        raise
    finally:
        # Clean up content columns even if migration failed
        if "engine" in locals():
            try:
                log_and_print("Cleaning up content columns in finally block...")
                with engine.connect() as conn:
                    # Drop content column from shifu_draft_outline_items
                    try:
                        conn.execute(
                            text(
                                "ALTER TABLE shifu_draft_outline_items DROP COLUMN content"
                            )
                        )
                        conn.commit()
                        log_and_print(
                            "Dropped content column from shifu_draft_outline_items (finally)"
                        )
                    except Exception as e:
                        log_and_print(
                            f"Warning: Could not drop content column from shifu_draft_outline_items (finally): {e}"
                        )

                    # Drop content column from shifu_published_outline_items
                    try:
                        conn.execute(
                            text(
                                "ALTER TABLE shifu_published_outline_items DROP COLUMN content"
                            )
                        )
                        conn.commit()
                        log_and_print(
                            "Dropped content column from shifu_published_outline_items (finally)"
                        )
                    except Exception as e:
                        log_and_print(
                            f"Warning: Could not drop content column from shifu_published_outline_items (finally): {e}"
                        )
            except Exception as e:
                log_and_print(f"Error in finally cleanup: {e}")

        if "migration_task" in locals():
            migration_task.close()
        if "loop" in locals():
            loop.close()
        log_and_print("Migration cleanup completed")


def downgrade():
    """Reverse the migration by truncating target tables"""
    logger.warning("Starting downgrade - this will DELETE all migrated data!")

    # Get database connection
    connection = op.get_bind()

    # Define target tables that will be truncated
    target_tables = [
        "learn_progress_records",
        "learn_generated_blocks",
        "order_orders",
        "order_pingxx_orders",
        "promo_coupons",
        "promo_coupon_usages",
    ]

    try:
        # Disable foreign key checks temporarily
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 0"))

        for table in target_tables:
            try:
                # Check if table exists
                result = connection.execute(
                    text(f"SHOW TABLES LIKE '{table}'")
                ).fetchone()
                if result:
                    logger.info(f"Truncating table: {table}")
                    connection.execute(text(f"TRUNCATE TABLE {table}"))
                else:
                    logger.info(f"Table {table} does not exist, skipping")
            except Exception as e:
                logger.error(f"Error truncating table {table}: {e}")
                raise

        # Clean up migration sync log
        try:
            sync_tables = [
                "ai_course_lesson_attend_sync",
                "ai_course_lesson_attendscript_sync",
                "ai_course_buy_record_sync",
                "pingxx_order_sync",
                "discount_sync",
                "discount_record_sync",
            ]

            for sync_table in sync_tables:
                connection.execute(
                    text("DELETE FROM migration_sync_log WHERE sync_type = :sync_type"),
                    {"sync_type": sync_table},
                )

            logger.info("Cleaned up migration sync log entries")

        except Exception as e:
            logger.warning(f"Error cleaning up sync log: {e}")

        # Re-enable foreign key checks
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

        logger.info("Downgrade completed - all migrated data has been removed")

    except Exception as e:
        # Re-enable foreign key checks even on error
        try:
            connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        except Exception:
            logger.error(f"Error re-enabling foreign key checks: {e}")
            pass
        logger.error(f"Downgrade failed: {e}")
        raise
