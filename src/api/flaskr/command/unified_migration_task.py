#!/usr/bin/env python3
"""
Unified Database Migration Task
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker
import os
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("/tmp/unified_migration.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


@dataclass
class MigrationConfig:
    """Migration configuration"""

    batch_size: int = 1000
    max_workers: int = 4
    max_retries: int = 3
    retry_delay: float = 1.0
    consistency_check_sample_size: int = 100


@dataclass
class MigrationResult:
    """Migration result for a single table"""

    table_name: str
    total_records: int
    synced_records: int
    error_records: int
    start_time: datetime
    end_time: datetime
    errors: List[str]

    @property
    def duration(self) -> float:
        """Get migration duration in seconds"""
        return (self.end_time - self.start_time).total_seconds()

    @property
    def success_rate(self) -> float:
        """Get success rate as percentage"""
        if self.total_records == 0:
            return 100.0
        return (self.synced_records / self.total_records) * 100


@dataclass
class ConsistencyCheckResult:
    """Consistency check result"""

    table_pair: str
    old_count: int
    new_count: int
    sample_integrity_passed: bool
    data_mismatches: List[str]

    @property
    def count_match(self) -> bool:
        return self.old_count == self.new_count

    @property
    def is_consistent(self) -> bool:
        return self.count_match and self.sample_integrity_passed


class UnifiedMigrationTask:
    """Unified migration task for study, order, and coupon tables"""

    def __init__(
        self,
        database_url: Optional[str] = None,
        config: Optional[MigrationConfig] = None,
    ):
        if database_url is None:
            database_url = os.getenv(
                "SQLALCHEMY_DATABASE_URI", "mysql+pymysql://root:@localhost/ai_shifu"
            )

        # Ensure PyMySQL driver
        if database_url.startswith("mysql://"):
            database_url = database_url.replace("mysql://", "mysql+pymysql://")

        # Use connection pooling for concurrent operations
        self.engine = create_engine(
            database_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,
        )
        self.SessionClass = sessionmaker(bind=self.engine)
        self.config = config or MigrationConfig()
        self.force_full_migration = False

        # Table mapping configuration
        self.table_mappings = {
            # Study tables (Study related tables)
            "ai_course_lesson_attend": {
                "target": "learn_progress_records",
                "mapping": self._map_attendscript_to_progress_record,
                "key_field": "attend_id",
                "target_key": "progress_record_bid",
            },
            "ai_course_lesson_attendscript": {
                "target": "learn_generated_blocks",
                "mapping": self._map_log_script_to_generated_block,
                "key_field": "log_id",
                "target_key": "generated_block_bid",
            },
            # Order tables (Order related tables)
            "ai_course_buy_record": {
                "target": "order_orders",
                "mapping": self._map_buy_record_to_order,
                "key_field": "record_id",
                "target_key": "order_bid",
            },
            "pingxx_order": {
                "target": "order_pingxx_orders",
                "mapping": self._map_pingxx_order,
                "key_field": "order_id",
                "target_key": "pingxx_order_bid",
            },
            # Coupon tables (Coupon related tables)
            "discount": {
                "target": "promo_coupons",
                "mapping": self._map_discount_to_coupon,
                "key_field": "discount_id",
                "target_key": "coupon_bid",
            },
            "discount_record": {
                "target": "promo_coupon_usages",
                "mapping": self._map_discount_log_to_usage,
                "key_field": "record_id",
                "target_key": "coupon_usage_bid",
            },
        }

        logger.info(f"Initialized unified migration task with database: {database_url}")

    async def migrate_all_tables(self) -> Dict[str, MigrationResult]:
        """Migrate all configured tables asynchronously"""
        logger.info("Starting unified migration for all tables...")

        results = {}
        tasks = []

        # Create migration tasks for each table
        for source_table, config in self.table_mappings.items():
            task = self._migrate_table_async(source_table, config)
            tasks.append(task)

        # Execute migrations concurrently
        migration_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for i, (source_table, _) in enumerate(self.table_mappings.items()):
            result = migration_results[i]
            if isinstance(result, Exception):
                logger.error(f"Migration failed for {source_table}: {result}")
                results[source_table] = MigrationResult(
                    table_name=source_table,
                    total_records=0,
                    synced_records=0,
                    error_records=0,
                    start_time=datetime.now(),
                    end_time=datetime.now(),
                    errors=[str(result)],
                )
            else:
                results[source_table] = result

        return results

    async def _migrate_table_async(
        self, source_table: str, table_config: Dict
    ) -> MigrationResult:
        """Migrate a single table asynchronously"""
        logger.info(f"Starting migration for table: {source_table}")
        start_time = datetime.now()

        target_table = table_config["target"]
        mapping_func = table_config["mapping"]
        key_field = table_config["key_field"]
        target_key = table_config["target_key"]

        # Check if tables exist
        if not await self._table_exists_async(source_table):
            logger.warning(f"Source table {source_table} does not exist, skipping...")
            return MigrationResult(
                table_name=source_table,
                total_records=0,
                synced_records=0,
                error_records=0,
                start_time=start_time,
                end_time=datetime.now(),
                errors=[f"Source table {source_table} does not exist"],
            )

        if not await self._table_exists_async(target_table):
            logger.warning(f"Target table {target_table} does not exist, skipping...")
            return MigrationResult(
                table_name=source_table,
                total_records=0,
                synced_records=0,
                error_records=0,
                start_time=start_time,
                end_time=datetime.now(),
                errors=[f"Target table {target_table} does not exist"],
            )

        # Get total record count
        total_count = await self._get_table_count_async(source_table)
        logger.info(f"Total records to migrate from {source_table}: {total_count}")

        # Process in batches
        synced_count = 0
        error_count = 0
        errors = []
        offset = 0

        while offset < total_count:
            try:
                batch_result = await self._process_batch_async(
                    source_table,
                    target_table,
                    mapping_func,
                    key_field,
                    target_key,
                    offset,
                )
                synced_count += batch_result["synced"]
                error_count += batch_result["errors"]
                errors.extend(batch_result["error_messages"])

                offset += self.config.batch_size

                # Log progress with more detail
                progress = min(100, (offset / total_count) * 100)
                logger.info(
                    f"Migration progress for {source_table}: {progress:.1f}% ({synced_count}/{total_count}) - Batch {offset // self.config.batch_size + 1}"
                )

                # Also print for visibility during flask db upgrade
                print(
                    f"[MIGRATION] {source_table}: {progress:.1f}% ({synced_count}/{total_count})"
                )
                import sys

                sys.stdout.flush()

            except Exception as e:
                logger.error(
                    f"Batch processing failed for {source_table} at offset {offset}: {e}"
                )
                errors.append(f"Batch error at offset {offset}: {str(e)}")
                error_count += self.config.batch_size
                offset += self.config.batch_size

        end_time = datetime.now()
        result = MigrationResult(
            table_name=source_table,
            total_records=total_count,
            synced_records=synced_count,
            error_records=error_count,
            start_time=start_time,
            end_time=end_time,
            errors=errors,
        )

        completion_message = f"Migration completed for {source_table}: {synced_count}/{total_count} records, {error_count} errors"
        logger.info(completion_message)
        print(f"[MIGRATION] ✅ {completion_message}")
        import sys

        sys.stdout.flush()
        return result

    async def _process_batch_async(
        self,
        source_table: str,
        target_table: str,
        mapping_func,
        key_field: str,
        target_key: str,
        offset: int,
    ) -> Dict:
        """Process a batch of records asynchronously"""
        loop = asyncio.get_event_loop()

        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            future = executor.submit(
                self._process_batch_sync,
                source_table,
                target_table,
                mapping_func,
                key_field,
                target_key,
                offset,
            )
            return await loop.run_in_executor(None, lambda: future.result())

    def _process_batch_sync(
        self,
        source_table: str,
        target_table: str,
        mapping_func,
        key_field: str,
        target_key: str,
        offset: int,
    ) -> Dict:
        """Process a batch of records synchronously"""
        # Create a new session for this batch to avoid concurrency issues
        session = self.SessionClass()
        try:
            # Get last synced ID for incremental updates
            last_synced_id = self._get_last_synced_id_with_session(
                session, f"{source_table}_sync"
            )

            # Determine migration mode
            should_do_full_migration = self.force_full_migration

            if not should_do_full_migration:
                # Check if this is a fresh migration by looking at target table count
                target_table_name = self.table_mappings[source_table]["target"]
                target_count = self._get_table_count_with_session(
                    session, target_table_name, "deleted = 0"
                )
                should_do_full_migration = (
                    target_count < 100
                )  # If less than 100 records, consider it fresh

            # Fetch batch of records using ID-based pagination
            if not should_do_full_migration and last_synced_id > 0:
                # Incremental migration - get records with ID greater than last synced ID
                query = text(
                    f"""
                    SELECT * FROM {source_table}
                    WHERE id > :last_synced_id
                    ORDER BY id ASC
                    LIMIT :batch_size
                """
                )
                params = {
                    "last_synced_id": last_synced_id,
                    "batch_size": self.config.batch_size,
                }
                logger.info(
                    f"Running incremental migration for {source_table} starting from ID {last_synced_id + 1}"
                )
            else:
                # Full migration - use OFFSET-based pagination
                query = text(
                    f"""
                    SELECT * FROM {source_table}
                    ORDER BY id ASC
                    LIMIT :batch_size OFFSET :offset
                """
                )
                params = {"batch_size": self.config.batch_size, "offset": offset}
                logger.info(
                    f"Running full migration for {source_table} batch at offset {offset}"
                )

            records = session.execute(query, params).fetchall()

            synced_count = 0
            error_count = 0
            error_messages = []

            for record in records:
                try:
                    # Check if record already exists in target table
                    existing_query = text(
                        f"""
                        SELECT COUNT(*) FROM {target_table}
                        WHERE {target_key} = :key_value AND deleted = 0
                    """
                    )

                    existing_count = session.execute(
                        existing_query, {"key_value": getattr(record, key_field)}
                    ).scalar()

                    # Map the record
                    mapped_data = mapping_func(record)

                    if existing_count > 0:
                        # Update existing record
                        update_fields = []
                        update_params = {"key_value": getattr(record, key_field)}

                        for field, value in mapped_data.items():
                            if field != target_key:  # Don't update the key field
                                update_fields.append(f"{field} = :{field}")
                                update_params[field] = value

                        if update_fields:
                            update_query = text(
                                f"""
                                UPDATE {target_table}
                                SET {", ".join(update_fields)}
                                WHERE {target_key} = :key_value
                            """
                            )
                            session.execute(update_query, update_params)
                    else:
                        # Insert new record
                        field_names = list(mapped_data.keys())
                        field_placeholders = [f":{field}" for field in field_names]

                        insert_query = text(
                            f"""
                            INSERT INTO {target_table} ({", ".join(field_names)})
                            VALUES ({", ".join(field_placeholders)})
                        """
                        )
                        session.execute(insert_query, mapped_data)

                    synced_count += 1

                except Exception as e:
                    error_count += 1
                    error_msg = f"Record migration failed for {getattr(record, key_field)}: {str(e)}"
                    error_messages.append(error_msg)
                    logger.error(error_msg)

                    if (
                        error_count > self.config.batch_size * 0.5
                    ):  # If more than 50% errors
                        raise Exception(f"Too many errors in batch: {error_count}")

            # Commit the batch
            session.commit()

            # Update last synced ID
            if records:
                latest_id = max(
                    record.id for record in records if hasattr(record, "id")
                )
                self._update_last_synced_id_with_session(
                    session, f"{source_table}_sync", latest_id
                )

            return {
                "synced": synced_count,
                "errors": error_count,
                "error_messages": error_messages,
            }

        except Exception as e:
            session.rollback()
            logger.error(f"Batch processing failed: {e}")
            raise
        finally:
            session.close()

    async def verify_data_consistency(self) -> Dict[str, ConsistencyCheckResult]:
        """Verify data consistency between old and new tables"""
        logger.info("Starting comprehensive data consistency verification...")

        results = {}

        for source_table, config in self.table_mappings.items():
            target_table = config["target"]
            key_field = config["key_field"]
            target_key = config["target_key"]

            try:
                # Count verification
                old_count = await self._get_table_count_async(source_table)
                new_count = await self._get_table_count_async(
                    target_table, where_clause="deleted = 0"
                )

                # Sample integrity check
                (
                    sample_check_passed,
                    mismatches,
                ) = await self._verify_sample_integrity_async(
                    source_table, target_table, key_field, target_key
                )

                result = ConsistencyCheckResult(
                    table_pair=f"{source_table} -> {target_table}",
                    old_count=old_count,
                    new_count=new_count,
                    sample_integrity_passed=sample_check_passed,
                    data_mismatches=mismatches,
                )

                results[source_table] = result

                status = "✓ PASSED" if result.is_consistent else "✗ FAILED"
                logger.info(
                    f"Consistency check {status} for {source_table}: {old_count} -> {new_count}"
                )

            except Exception as e:
                logger.error(f"Consistency check failed for {source_table}: {e}")
                results[source_table] = ConsistencyCheckResult(
                    table_pair=f"{source_table} -> {target_table}",
                    old_count=0,
                    new_count=0,
                    sample_integrity_passed=False,
                    data_mismatches=[f"Check failed: {str(e)}"],
                )

        return results

    async def _verify_sample_integrity_async(
        self, source_table: str, target_table: str, key_field: str, target_key: str
    ) -> Tuple[bool, List[str]]:
        """Verify data integrity using random sampling"""
        session = self.SessionClass()
        try:
            # Get random sample from source table
            sample_query = text(
                f"""
                SELECT * FROM {source_table}
                ORDER BY RAND()
                LIMIT :sample_size
            """
            )

            samples = session.execute(
                sample_query, {"sample_size": self.config.consistency_check_sample_size}
            ).fetchall()

            mismatches = []

            for sample in samples:
                key_value = getattr(sample, key_field)

                # Find corresponding record in target table
                target_query = text(
                    f"""
                    SELECT * FROM {target_table}
                    WHERE {target_key} = :key_value AND deleted = 0
                    LIMIT 1
                """
                )

                target_record = session.execute(
                    target_query, {"key_value": key_value}
                ).fetchone()

                if not target_record:
                    mismatches.append(f"Missing record in target: {key_value}")
                    continue

                # Verify specific field mappings based on table type
                verification_passed = self._verify_record_mapping(
                    source_table, sample, target_record
                )

                if not verification_passed:
                    mismatches.append(f"Data mismatch for record: {key_value}")

            success_rate = (
                (len(samples) - len(mismatches)) / len(samples) if samples else 1.0
            )
            passed = success_rate >= 0.95  # 95% success rate required

            return passed, mismatches

        except Exception as e:
            logger.error(f"Sample integrity check failed: {e}")
            return False, [f"Integrity check error: {str(e)}"]
        finally:
            session.close()

    def _verify_record_mapping(
        self, source_table: str, source_record, target_record
    ) -> bool:
        """Verify specific field mappings for a record"""
        try:
            if source_table == "ai_course_buy_record":
                return (
                    abs(float(target_record.payable_price) - float(source_record.price))
                    < 0.01
                    and abs(
                        float(target_record.paid_price)
                        - float(source_record.paid_value)
                    )
                    < 0.01
                )
            elif source_table == "discount":
                return (
                    target_record.code == source_record.discount_code
                    and abs(
                        float(target_record.value) - float(source_record.discount_value)
                    )
                    < 0.01
                )
            elif source_table == "pingxx_order":
                return (
                    target_record.transaction_no == source_record.pingxx_transaction_no
                    and target_record.amount == source_record.amount
                )
            elif source_table in [
                "ai_course_lesson_attendscript",
                "ai_course_lesson_attend",
            ]:
                # For study tables, verify basic bid mapping
                return (
                    hasattr(target_record, "user_bid")
                    and target_record.user_bid is not None
                )
            else:
                return True  # Basic existence check for other tables

        except Exception as e:
            logger.error(f"Record mapping verification failed: {e}")
            return False

    # Table mapping functions
    def _map_attendscript_to_progress_record(self, record) -> Dict:
        """Map ai_course_lesson_attend to learn_progress_records"""
        return {
            "progress_record_bid": getattr(record, "attend_id", ""),
            "shifu_bid": getattr(record, "course_id", ""),
            "outline_item_bid": getattr(record, "lesson_id", ""),
            "user_bid": getattr(record, "user_id", ""),
            "outline_item_updated": getattr(record, "lesson_is_updated", 0),
            "status": getattr(record, "status", 605),  # Default to locked
            "block_position": getattr(record, "script_index", 0),
            "deleted": 0,
            "created_at": getattr(record, "created", None),
            "updated_at": getattr(record, "updated", None),
        }

    def _map_log_script_to_generated_block(self, record) -> Dict:
        """Map ai_course_lesson_attendscript to learn_generated_blocks"""
        return {
            "generated_block_bid": getattr(record, "log_id", ""),
            "progress_record_bid": getattr(record, "attend_id", ""),
            "user_bid": getattr(record, "user_id", ""),
            "block_bid": getattr(record, "script_id", ""),
            "outline_item_bid": getattr(record, "lesson_id", ""),
            "shifu_bid": getattr(record, "course_id", ""),
            "type": getattr(record, "script_ui_type", 0),
            "role": getattr(record, "script_role", 0),
            "generated_content": getattr(record, "script_content", ""),
            "position": getattr(record, "script_index", 0),
            "block_content_conf": getattr(record, "script_ui_conf", ""),
            "liked": getattr(record, "interaction_type", 0),
            "deleted": 0,
            "status": getattr(record, "status", 1),
            "created_at": getattr(record, "created", None),
            "updated_at": getattr(record, "updated", None),
        }

    def _map_buy_record_to_order(self, record) -> Dict:
        """Map ai_course_buy_record to order_orders"""
        return {
            "order_bid": getattr(record, "record_id", ""),
            "shifu_bid": getattr(record, "course_id", ""),
            "user_bid": getattr(record, "user_id", ""),
            "payable_price": getattr(record, "price", 0),
            "paid_price": getattr(record, "paid_value", 0),
            "status": getattr(record, "status", 0),
            "deleted": 0,
            "created_at": getattr(record, "created", None),
            "updated_at": getattr(record, "updated", None),
        }

    def _map_pingxx_order(self, record) -> Dict:
        """Map pingxx_order to order_pingxx_orders"""
        return {
            "pingxx_order_bid": record.order_id,
            "user_bid": record.user_id,
            "shifu_bid": record.course_id,
            "order_bid": record.record_id,
            "transaction_no": record.pingxx_transaction_no,
            "app_id": record.pingxx_app_id,
            "channel": record.channel,
            "amount": record.amount,
            "currency": record.currency,
            "subject": record.subject,
            "body": record.body,
            "client_ip": record.client_ip,
            "extra": record.extra,
            "status": record.status,
            "charge_id": record.charge_id,
            "paid_at": record.paid_at,
            "refunded_at": record.refunded_at,
            "closed_at": record.closed_at,
            "failed_at": record.failed_at,
            "refund_id": record.refund_id,
            "failure_code": record.failure_code,
            "failure_msg": record.failure_msg,
            "charge_object": record.charge_object,
            "deleted": 0,
            "created_at": record.created,
            "updated_at": record.updated,
        }

    def _map_discount_to_coupon(self, record) -> Dict:
        """Map discount to promo_coupons"""
        return {
            "coupon_bid": record.discount_id,
            "code": record.discount_code,
            "discount_type": record.discount_type,
            "usage_type": record.discount_apply_type,
            "value": record.discount_value,
            "start": record.discount_start,
            "end": record.discount_end,
            "channel": record.discount_channel,
            "filter": record.discount_filter,
            "total_count": record.discount_count,
            "used_count": record.discount_used,
            "status": record.status,
            "deleted": 0,
            "created_at": record.created,
            "created_user_bid": getattr(record, "discount_generated_user", ""),
            "updated_at": record.updated,
        }

    def _map_discount_log_to_usage(self, record) -> Dict:
        """Map discount_use_log to promo_coupon_usages"""
        return {
            "coupon_usage_bid": record.record_id,
            "coupon_bid": record.discount_id,
            "name": getattr(record, "discount_name", ""),
            "user_bid": record.user_id,
            "shifu_bid": getattr(record, "course_id", ""),
            "order_bid": getattr(record, "order_id", ""),
            "code": getattr(record, "discount_code", ""),
            "discount_type": getattr(record, "discount_type", 701),
            "value": getattr(record, "discount_value", 0),
            "status": getattr(record, "status", 902),
            "deleted": 0,
            "created_at": record.created,
            "updated_at": record.updated,
        }

    # Helper methods
    async def _table_exists_async(self, table_name: str) -> bool:
        """Check if table exists asynchronously"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._table_exists, table_name)

    def _table_exists(self, table_name: str) -> bool:
        """Check if table exists"""
        session = self.SessionClass()
        try:
            result = session.execute(
                text(f"SHOW TABLES LIKE '{table_name}'")
            ).fetchone()
            return result is not None
        except Exception as e:
            logger.error(f"Error checking table existence {table_name}: {e}")
            return False
        finally:
            session.close()

    def _get_table_count_with_session(
        self, session, table_name: str, where_clause: str = ""
    ) -> int:
        """Get table record count using provided session"""
        try:
            query = f"SELECT COUNT(*) FROM {table_name}"
            if where_clause:
                query += f" WHERE {where_clause}"

            count = session.execute(text(query)).scalar()
            return count or 0
        except Exception as e:
            logger.error(f"Error getting table count for {table_name}: {e}")
            return 0

    def _check_column_exists_with_session(
        self, session, table_name: str, column_name: str
    ) -> bool:
        """Check if column exists in table"""
        try:
            result = session.execute(
                text(
                    f"""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = '{table_name}'
                AND COLUMN_NAME = '{column_name}'
            """
                )
            ).scalar()
            return result > 0
        except Exception as e:
            logger.error(
                f"Error checking column existence {table_name}.{column_name}: {e}"
            )
            return False

    async def _get_table_count_async(
        self, table_name: str, where_clause: str = ""
    ) -> int:
        """Get table record count asynchronously"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._get_table_count, table_name, where_clause
        )

    def _get_table_count(self, table_name: str, where_clause: str = "") -> int:
        """Get table record count"""
        session = self.SessionClass()
        try:
            query = f"SELECT COUNT(*) FROM {table_name}"
            if where_clause:
                query += f" WHERE {where_clause}"

            count = session.execute(text(query)).scalar()
            return count or 0
        except Exception as e:
            logger.error(f"Error getting table count for {table_name}: {e}")
            return 0
        finally:
            session.close()

    def _get_last_sync_time(self, sync_type: str) -> datetime:
        """Get last sync time from log table"""
        session = self.SessionClass()
        try:
            return self._get_last_sync_time_with_session(session, sync_type)
        finally:
            session.close()

    def _get_last_sync_time_with_session(self, session, sync_type: str) -> datetime:
        """Get last sync time from log table using provided session"""
        try:
            self._ensure_sync_log_table_with_session(session)

            result = session.execute(
                text(
                    "SELECT sync_time FROM migration_sync_log WHERE sync_type = :type ORDER BY id DESC LIMIT 1"
                ),
                {"type": sync_type},
            ).fetchone()

            return result[0] if result else datetime(2020, 1, 1)
        except Exception as e:
            logger.warning(f"Error getting sync time: {e}")
            return datetime(2020, 1, 1)

    def _get_last_synced_id_with_session(self, session, sync_type: str) -> int:
        """Get last synced ID from log table using provided session"""
        try:
            self._ensure_sync_log_table_with_session(session)

            result = session.execute(
                text(
                    "SELECT last_synced_id FROM migration_sync_log WHERE sync_type = :type ORDER BY id DESC LIMIT 1"
                ),
                {"type": sync_type},
            ).fetchone()

            return result[0] if result and result[0] else 0
        except Exception as e:
            logger.warning(f"Error getting last synced ID: {e}")
            return 0

    def _update_sync_time(self, sync_type: str, sync_time: datetime):
        """Update sync time in log table"""
        session = self.SessionClass()
        try:
            self._update_sync_time_with_session(session, sync_type, sync_time)
        finally:
            session.close()

    def _update_sync_time_with_session(
        self, session, sync_type: str, sync_time: datetime
    ):
        """Update sync time in log table using provided session"""
        try:
            self._ensure_sync_log_table_with_session(session)

            session.execute(
                text(
                    "INSERT INTO migration_sync_log (sync_type, sync_time, created_at) VALUES (:type, :time, NOW())"
                ),
                {"type": sync_type, "time": sync_time},
            )
            session.commit()
        except Exception as e:
            logger.warning(f"Error updating sync time: {e}")

    def _update_last_synced_id_with_session(
        self, session, sync_type: str, last_synced_id: int
    ):
        """Update last synced ID in log table using provided session"""
        try:
            self._ensure_sync_log_table_with_session(session)

            session.execute(
                text(
                    "INSERT INTO migration_sync_log (sync_type, last_synced_id, sync_time, created_at) VALUES (:type, :last_id, NOW(), NOW())"
                ),
                {"type": sync_type, "last_id": last_synced_id},
            )
            session.commit()
        except Exception as e:
            logger.warning(f"Error updating last synced ID: {e}")

    def _ensure_sync_log_table(self):
        """Ensure sync log table exists"""
        session = self.SessionClass()
        try:
            self._ensure_sync_log_table_with_session(session)
        finally:
            session.close()

    def _ensure_sync_log_table_with_session(self, session):
        """Ensure sync log table exists using provided session"""
        try:
            session.execute(
                text(
                    """
                CREATE TABLE IF NOT EXISTS migration_sync_log (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    sync_type VARCHAR(50) NOT NULL,
                    sync_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_synced_id BIGINT DEFAULT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_sync_type (sync_type),
                    INDEX idx_sync_time (sync_time),
                    INDEX idx_last_synced_id (last_synced_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Migration sync log table'
            """
                )
            )

            # Check if last_synced_id column exists and add it if it doesn't
            try:
                result = session.execute(
                    text(
                        """
                    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'migration_sync_log'
                    AND COLUMN_NAME = 'last_synced_id'
                """
                    )
                ).scalar()

                if result == 0:
                    # Column doesn't exist, add it
                    session.execute(
                        text(
                            """
                        ALTER TABLE migration_sync_log
                        ADD COLUMN last_synced_id BIGINT DEFAULT NULL,
                        ADD INDEX idx_last_synced_id (last_synced_id)
                    """
                        )
                    )
                    logger.info(
                        "Added last_synced_id column to migration_sync_log table"
                    )
            except Exception as e:
                logger.warning(f"Error checking/adding last_synced_id column: {e}")

            session.commit()
        except Exception as e:
            logger.error(f"Error creating sync log table: {e}")

    def generate_migration_report(
        self,
        migration_results: Dict[str, MigrationResult],
        consistency_results: Dict[str, ConsistencyCheckResult],
    ) -> str:
        """Generate comprehensive migration report"""
        report = []
        report.append("=" * 80)
        report.append("UNIFIED DATABASE MIGRATION REPORT")
        report.append("=" * 80)
        report.append(f"Generated at: {datetime.now()}")
        report.append("")

        # Migration Summary
        report.append("MIGRATION SUMMARY")
        report.append("-" * 40)
        total_records = sum(r.total_records for r in migration_results.values())
        total_synced = sum(r.synced_records for r in migration_results.values())
        total_errors = sum(r.error_records for r in migration_results.values())
        overall_success_rate = (
            (total_synced / total_records * 100) if total_records > 0 else 0
        )

        report.append(f"Total Records: {total_records}")
        report.append(f"Successfully Migrated: {total_synced}")
        report.append(f"Errors: {total_errors}")
        report.append(f"Overall Success Rate: {overall_success_rate:.2f}%")
        report.append("")

        # Per-table results
        report.append("PER-TABLE MIGRATION RESULTS")
        report.append("-" * 40)
        for table_name, result in migration_results.items():
            report.append(f"Table: {table_name}")
            report.append(f"  Records: {result.synced_records}/{result.total_records}")
            report.append(f"  Success Rate: {result.success_rate:.2f}%")
            report.append(f"  Duration: {result.duration:.2f}s")
            if result.errors:
                report.append(f"  Errors: {len(result.errors)}")
            report.append("")

        # Consistency Check Results
        report.append("DATA CONSISTENCY VERIFICATION")
        report.append("-" * 40)
        for table_name, result in consistency_results.items():
            status = "✓ PASSED" if result.is_consistent else "✗ FAILED"
            report.append(f"{status} {result.table_pair}")
            report.append(
                f"  Count Match: {result.old_count} -> {result.new_count} {'✓' if result.count_match else '✗'}"
            )
            report.append(
                f"  Sample Integrity: {'✓' if result.sample_integrity_passed else '✗'}"
            )
            if result.data_mismatches:
                report.append(f"  Mismatches: {len(result.data_mismatches)}")
            report.append("")

        # Recommendations
        failed_consistency = [
            t for t, r in consistency_results.items() if not r.is_consistent
        ]
        if failed_consistency:
            report.append("RECOMMENDATIONS")
            report.append("-" * 40)
            report.append("The following tables failed consistency checks:")
            for table in failed_consistency:
                report.append(f"  - {table}: Review data mapping and re-run migration")
            report.append("")

        return "\n".join(report)

    def close(self):
        """Close database connections"""
        if self.engine:
            self.engine.dispose()


async def main():
    """Main execution function"""
    import argparse

    parser = argparse.ArgumentParser(description="Unified Database Migration Task")
    parser.add_argument(
        "action", choices=["migrate", "verify", "report"], help="Action to perform"
    )
    parser.add_argument("--database-url", help="Database connection URL")
    parser.add_argument(
        "--batch-size", type=int, default=1000, help="Batch size for processing"
    )
    parser.add_argument(
        "--max-workers", type=int, default=4, help="Maximum worker threads"
    )
    parser.add_argument("--output-file", help="Output file for report")
    parser.add_argument(
        "--force-full",
        action="store_true",
        help="Force full migration instead of incremental",
    )

    args = parser.parse_args()

    # Create migration config
    config = MigrationConfig(batch_size=args.batch_size, max_workers=args.max_workers)

    # Initialize migration task
    migration_task = UnifiedMigrationTask(args.database_url, config)
    migration_task.force_full_migration = getattr(args, "force_full", False)

    try:
        if args.action == "migrate":
            logger.info("Starting unified migration...")
            migration_results = await migration_task.migrate_all_tables()

            logger.info("Migration completed. Starting consistency verification...")
            consistency_results = await migration_task.verify_data_consistency()

            # Generate report
            report = migration_task.generate_migration_report(
                migration_results, consistency_results
            )

            if args.output_file:
                with open(args.output_file, "w", encoding="utf-8") as f:
                    f.write(report)
                logger.info(f"Report saved to: {args.output_file}")
            else:
                print(report)

        elif args.action == "verify":
            logger.info("Starting data consistency verification...")
            consistency_results = await migration_task.verify_data_consistency()

            for table_name, result in consistency_results.items():
                status = "PASSED" if result.is_consistent else "FAILED"
                print(f"{status}: {result.table_pair}")
                if not result.is_consistent:
                    sys.exit(1)

        elif args.action == "report":
            # Generate report for existing migration
            migration_results = {}  # Would need to load from previous run
            consistency_results = await migration_task.verify_data_consistency()
            report = migration_task.generate_migration_report(
                migration_results, consistency_results
            )
            print(report)

    finally:
        migration_task.close()


if __name__ == "__main__":
    asyncio.run(main())
