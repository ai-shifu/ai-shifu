from flask import Flask
import click
import asyncio
import logging
from sqlalchemy import create_engine, text
from .import_user import import_user
from .unified_migration_task import UnifiedMigrationTask, MigrationConfig
from flaskr.service.shifu.migration import migrate_shifu_to_mdflow_content


def setup_migration_logging():
    """Setup logging for migration commands"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("/tmp/flask_migration.log"),
            logging.StreamHandler(),
        ],
    )


def enable_commands(app: Flask):
    @app.cli.group()
    def console():
        """AI Shifu Console management commands."""
        pass

    @console.command(name="import_user")
    @click.argument("mobile")
    @click.argument("course_id")
    @click.argument("discount_code")
    @click.argument("user_nick_name")
    def import_user_command(mobile, course_id, discount_code, user_nick_name):
        """Import user and enable course"""
        import_user(app, mobile, course_id, discount_code, user_nick_name)

    @console.command(name="migrate")
    @click.option("--batch-size", default=1000, help="Batch size for processing")
    @click.option("--max-workers", default=3, help="Maximum worker threads")
    @click.option(
        "--force-full", is_flag=True, help="Force full migration instead of incremental"
    )
    @click.option("--output-file", help="Save migration report to file")
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Show what would be migrated without actually doing it",
    )
    def migrate_command(batch_size, max_workers, force_full, output_file, dry_run):
        """Run unified legacy data migration"""
        setup_migration_logging()
        logger = logging.getLogger(__name__)

        if dry_run:
            click.echo("DRY RUN MODE - No data will be actually migrated")

        try:
            database_url = app.config["SQLALCHEMY_DATABASE_URI"]

            # Create migration configuration
            migration_config = MigrationConfig(
                batch_size=batch_size,
                max_workers=max_workers,
                max_retries=3,
                retry_delay=1.0,
                consistency_check_sample_size=100,
            )

            # Initialize migration task
            migration_task = UnifiedMigrationTask(database_url, migration_config)
            migration_task.force_full_migration = force_full

            if dry_run:
                # Just show what tables would be migrated
                click.echo("\nTables that would be migrated:")
                for source_table, table_config in migration_task.table_mappings.items():
                    target_table = table_config["target"]
                    click.echo(f"  {source_table} -> {target_table}")
                click.echo("\nConfiguration:")
                click.echo(f"  Batch size: {batch_size}")
                click.echo(f"  Max workers: {max_workers}")
                click.echo(f"  Force full: {force_full}")
                return

            # Run the actual migration
            logger.info("Starting unified legacy data migration via Flask CLI...")

            # Execute migration
            migration_results = asyncio.run(migration_task.migrate_all_tables())

            # Verify data consistency
            logger.info("Verifying data consistency...")
            consistency_results = asyncio.run(migration_task.verify_data_consistency())

            # Generate report
            report = migration_task.generate_migration_report(
                migration_results, consistency_results
            )

            # Save or display report
            if output_file:
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(report)
                click.echo(f"Migration report saved to: {output_file}")
            else:
                click.echo("\n" + "=" * 80)
                click.echo(report)
                click.echo("=" * 80)

            # Check success and display summary
            failed_tables = []
            for table_name, result in migration_results.items():
                if result.success_rate < 95.0:
                    failed_tables.append(f"{table_name} ({result.success_rate:.1f}%)")

            failed_consistency = []
            for table_name, result in consistency_results.items():
                if not result.is_consistent:
                    failed_consistency.append(table_name)

            if failed_tables:
                click.echo(
                    click.style(
                        f"❌ Migration failed for tables: {', '.join(failed_tables)}",
                        fg="red",
                    )
                )
                raise click.ClickException("Migration failed")

            if failed_consistency:
                click.echo(
                    click.style(
                        f"⚠️  Consistency check failed for: {', '.join(failed_consistency)}",
                        fg="yellow",
                    )
                )

            # Success summary
            total_migrated = sum(r.synced_records for r in migration_results.values())
            total_records = sum(r.total_records for r in migration_results.values())
            overall_rate = (
                (total_migrated / total_records * 100) if total_records > 0 else 0
            )

            click.echo(
                click.style(
                    f"✅ Migration completed: {total_migrated}/{total_records} records ({overall_rate:.1f}%)",
                    fg="green",
                )
            )

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise click.ClickException(f"Migration failed: {e}")
        finally:
            if "migration_task" in locals():
                migration_task.close()

    @console.command(name="migrate_to_mdflow")
    @click.argument("shifu_bid")
    def migrate_to_mdflow_command(shifu_bid):
        """This command is used to migrate shifu's original structure based on blocks to MarkdownFlow content
        usage: flask console migrate_to_mdflow <shifu_bid>
        """
        migrate_shifu_to_mdflow_content(app, shifu_bid)

    @console.command(name="verify")
    def verify_command():
        """Verify data consistency between old and new tables"""
        setup_migration_logging()
        logger = logging.getLogger(__name__)

        try:
            # Get database URL from Flask config
            from ..common.config import get_config

            config = get_config()
            database_url = config.SQLALCHEMY_DATABASE_URI

            # Initialize migration task
            migration_task = UnifiedMigrationTask(database_url)

            logger.info("Running data consistency verification...")
            consistency_results = asyncio.run(migration_task.verify_data_consistency())

            click.echo("\nData Consistency Verification Results:")
            click.echo("=" * 50)

            all_passed = True
            for table_name, result in consistency_results.items():
                if result.is_consistent:
                    status_icon = click.style("✅", fg="green")
                    status_text = click.style("PASSED", fg="green")
                else:
                    status_icon = click.style("❌", fg="red")
                    status_text = click.style("FAILED", fg="red")
                    all_passed = False

                click.echo(f"{status_icon} {status_text}: {result.table_pair}")
                click.echo(f"   Count: {result.old_count} -> {result.new_count}")

                if result.data_mismatches:
                    click.echo(f"   Mismatches: {len(result.data_mismatches)}")

            if all_passed:
                click.echo(
                    click.style("\n🎉 All consistency checks passed!", fg="green")
                )
            else:
                click.echo(
                    click.style("\n⚠️  Some consistency checks failed.", fg="yellow")
                )
                click.echo("Consider re-running the migration for failed tables.")

        except Exception as e:
            logger.error(f"Verification failed: {e}")
            raise click.ClickException(f"Verification failed: {e}")
        finally:
            if "migration_task" in locals():
                migration_task.close()

    @console.command(name="status")
    def status_command():
        """Show migration status and table counts"""
        setup_migration_logging()
        logger = logging.getLogger(__name__)

        try:
            # Get database URL from Flask config
            from ..common.config import get_config

            config = get_config()
            database_url = config.SQLALCHEMY_DATABASE_URI

            # Create engine for direct queries
            engine = create_engine(database_url)

            # Initialize migration task to get table mappings
            migration_task = UnifiedMigrationTask(database_url)

            click.echo("\nMigration Status Overview:")
            click.echo("=" * 60)

            for source_table, table_config in migration_task.table_mappings.items():
                target_table = table_config["target"]

                try:
                    # Get counts
                    source_count = migration_task._get_table_count(source_table)
                    target_count = migration_task._get_table_count(
                        target_table, "deleted = 0"
                    )

                    # Calculate percentage
                    percentage = (
                        (target_count / source_count * 100) if source_count > 0 else 0
                    )

                    # Format output
                    if percentage >= 95:
                        status_icon = click.style("✅", fg="green")
                    elif percentage >= 50:
                        status_icon = click.style("⚠️", fg="yellow")
                    else:
                        status_icon = click.style("❌", fg="red")

                    click.echo(f"{status_icon} {source_table} -> {target_table}")
                    click.echo(
                        f"   Records: {target_count:,}/{source_count:,} ({percentage:.1f}%)"
                    )

                except Exception as e:
                    click.echo(f"❌ {source_table} -> {target_table}")
                    click.echo(f"   Error: {e}")

            # Check migration sync log
            try:
                with engine.connect() as conn:
                    result = conn.execute(
                        text(
                            "SELECT sync_type, MAX(sync_time) as last_sync, MAX(last_synced_id) as last_id "
                            "FROM migration_sync_log GROUP BY sync_type"
                        )
                    ).fetchall()

                    if result:
                        click.echo("\nLast Migration Activity:")
                        click.echo("-" * 40)
                        for row in result:
                            click.echo(
                                f"{row.sync_type}: {row.last_sync} (ID: {row.last_id or 'N/A'})"
                            )
                    else:
                        click.echo("\nNo migration activity recorded.")

            except Exception as e:
                click.echo(f"\nCould not read migration log: {e}")

        except Exception as e:
            logger.error(f"Status check failed: {e}")
            raise click.ClickException(f"Status check failed: {e}")
        finally:
            if "migration_task" in locals():
                migration_task.close()
