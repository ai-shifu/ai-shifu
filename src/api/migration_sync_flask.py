#!/usr/bin/env python3
"""
基于Flask应用的数据库迁移同步任务
利用现有的Flask应用架构和数据库连接
"""

import logging
import sys
import os
from typing import Dict, Tuple
from sqlalchemy import text
from app import create_app
from flaskr.dao import db
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("/tmp/migration_sync.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class FlaskMigrationSync:
    """基于Flask应用的迁移同步任务类"""

    def __init__(self):
        self.app = create_app()
        self.sync_batch_size = 1000
        self.error_count = 0
        self.max_errors = 10

        logger.info("初始化Flask迁移同步任务")

    def sync_order_data(self) -> Tuple[int, int]:
        """同步订单数据：ai_course_buy_record -> order_orders"""
        with self.app.app_context():
            logger.info("开始同步订单数据...")

            try:
                # 首先检查表是否存在
                if not self._table_exists("order_orders"):
                    logger.warning("新表 order_orders 不存在，需要先执行数据库迁移")
                    return 0, 0

                if not self._table_exists("ai_course_buy_record"):
                    logger.warning("旧表 ai_course_buy_record 不存在，跳过同步")
                    return 0, 0

                # 查询需要同步的旧表数据（增量同步）
                last_sync_time = self._get_last_sync_time("order_sync")

                query = text(
                    """
                    SELECT record_id, course_id, user_id, price, paid_value,
                           status, created, updated
                    FROM ai_course_buy_record
                    WHERE updated > :last_sync_time
                    ORDER BY updated ASC
                    LIMIT :batch_size
                """
                )

                old_records = db.session.execute(
                    query,
                    {
                        "last_sync_time": last_sync_time,
                        "batch_size": self.sync_batch_size,
                    },
                ).fetchall()

                synced_count = 0
                error_count = 0

                for record in old_records:
                    try:
                        # 检查新表中是否已存在
                        existing_check = db.session.execute(
                            text(
                                """
                            SELECT COUNT(*) FROM order_orders WHERE order_bid = :order_bid
                        """
                            ),
                            {"order_bid": record.record_id},
                        ).scalar()

                        if existing_check > 0:
                            # 更新现有记录
                            db.session.execute(
                                text(
                                    """
                                UPDATE order_orders
                                SET payable_price = :payable_price,
                                    paid_price = :paid_price,
                                    status = :status,
                                    updated_at = :updated_at
                                WHERE order_bid = :order_bid
                            """
                                ),
                                {
                                    "payable_price": record.price,
                                    "paid_price": record.paid_value,
                                    "status": self._map_order_status(record.status),
                                    "updated_at": record.updated,
                                    "order_bid": record.record_id,
                                },
                            )
                            logger.debug(f"更新订单: {record.record_id}")
                        else:
                            # 创建新记录
                            db.session.execute(
                                text(
                                    """
                                INSERT INTO order_orders
                                (order_bid, shifu_bid, user_bid, payable_price, paid_price,
                                 status, deleted, created_at, updated_at)
                                VALUES (:order_bid, :shifu_bid, :user_bid, :payable_price,
                                        :paid_price, :status, 0, :created_at, :updated_at)
                            """
                                ),
                                {
                                    "order_bid": record.record_id,
                                    "shifu_bid": record.course_id,
                                    "user_bid": record.user_id,
                                    "payable_price": record.price,
                                    "paid_price": record.paid_value,
                                    "status": self._map_order_status(record.status),
                                    "created_at": record.created,
                                    "updated_at": record.updated,
                                },
                            )
                            logger.debug(f"创建订单: {record.record_id}")

                        synced_count += 1

                    except Exception as e:
                        error_count += 1
                        logger.error(f"同步订单记录失败 {record.record_id}: {e}")
                        if error_count > self.max_errors:
                            raise Exception(f"错误次数超过限制: {error_count}")

                # 提交事务
                db.session.commit()

                # 更新同步时间戳
                if old_records:
                    latest_time = max(record.updated for record in old_records)
                    self._update_sync_time("order_sync", latest_time)

                logger.info(
                    f"订单数据同步完成: {synced_count} 条记录, {error_count} 个错误"
                )
                return synced_count, error_count

            except Exception as e:
                db.session.rollback()
                logger.error(f"订单数据同步失败: {e}")
                raise

    def sync_pingxx_order_data(self) -> Tuple[int, int]:
        """同步Pingxx订单数据：pingxx_order -> order_pingxx_orders"""
        with self.app.app_context():
            logger.info("开始同步Pingxx订单数据...")

            try:
                # 检查表是否存在
                if not self._table_exists("order_pingxx_orders"):
                    logger.warning(
                        "新表 order_pingxx_orders 不存在，需要先执行数据库迁移"
                    )
                    return 0, 0

                if not self._table_exists("pingxx_order"):
                    logger.warning("旧表 pingxx_order 不存在，跳过同步")
                    return 0, 0

                last_sync_time = self._get_last_sync_time("pingxx_order_sync")

                query = text(
                    """
                    SELECT order_id, user_id, course_id, record_id,
                           pingxx_transaction_no, pingxx_app_id, channel,
                           amount, currency, subject, body, client_ip, extra,
                           status, charge_id, paid_at, refunded_at, closed_at,
                           failed_at, refund_id, failure_code, failure_msg,
                           charge_object, created, updated
                    FROM pingxx_order
                    WHERE updated > :last_sync_time
                    ORDER BY updated ASC
                    LIMIT :batch_size
                """
                )

                old_records = db.session.execute(
                    query,
                    {
                        "last_sync_time": last_sync_time,
                        "batch_size": self.sync_batch_size,
                    },
                ).fetchall()

                synced_count = 0
                error_count = 0

                for record in old_records:
                    try:
                        existing_check = db.session.execute(
                            text(
                                """
                            SELECT COUNT(*) FROM order_pingxx_orders
                            WHERE transaction_no = :transaction_no
                        """
                            ),
                            {"transaction_no": record.pingxx_transaction_no},
                        ).scalar()

                        if existing_check > 0:
                            # 更新现有记录
                            db.session.execute(
                                text(
                                    """
                                UPDATE order_pingxx_orders
                                SET amount = :amount, status = :status,
                                    charge_id = :charge_id, updated_at = :updated_at
                                WHERE transaction_no = :transaction_no
                            """
                                ),
                                {
                                    "amount": record.amount,
                                    "status": record.status,
                                    "charge_id": record.charge_id,
                                    "updated_at": record.updated,
                                    "transaction_no": record.pingxx_transaction_no,
                                },
                            )
                        else:
                            # 创建新记录
                            db.session.execute(
                                text(
                                    """
                                INSERT INTO order_pingxx_orders
                                (pingxx_order_bid, user_bid, shifu_bid, order_bid,
                                 transaction_no, app_id, channel, amount, currency,
                                 subject, body, client_ip, extra, status, charge_id,
                                 paid_at, refunded_at, closed_at, failed_at, refund_id,
                                 failure_code, failure_msg, charge_object,
                                 deleted, created_at, updated_at)
                                VALUES (:pingxx_order_bid, :user_bid, :shifu_bid, :order_bid,
                                        :transaction_no, :app_id, :channel, :amount, :currency,
                                        :subject, :body, :client_ip, :extra, :status, :charge_id,
                                        :paid_at, :refunded_at, :closed_at, :failed_at, :refund_id,
                                        :failure_code, :failure_msg, :charge_object,
                                        0, :created_at, :updated_at)
                            """
                                ),
                                {
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
                                    "created_at": record.created,
                                    "updated_at": record.updated,
                                },
                            )

                        synced_count += 1

                    except Exception as e:
                        error_count += 1
                        logger.error(
                            f"同步Pingxx订单记录失败 {record.pingxx_transaction_no}: {e}"
                        )
                        if error_count > self.max_errors:
                            raise Exception(f"错误次数超过限制: {error_count}")

                db.session.commit()

                if old_records:
                    latest_time = max(record.updated for record in old_records)
                    self._update_sync_time("pingxx_order_sync", latest_time)

                logger.info(
                    f"Pingxx订单数据同步完成: {synced_count} 条记录, {error_count} 个错误"
                )
                return synced_count, error_count

            except Exception as e:
                db.session.rollback()
                logger.error(f"Pingxx订单数据同步失败: {e}")
                raise

    def sync_learn_progress_data(self) -> Tuple[int, int]:
        """同步学习进度数据：ai_course_lesson_attend -> learn_progress_records"""
        with self.app.app_context():
            logger.info("开始同步学习进度数据...")

            try:
                # 检查表是否存在
                if not self._table_exists("learn_progress_records"):
                    logger.warning(
                        "新表 learn_progress_records 不存在，需要先执行数据库迁移"
                    )
                    return 0, 0

                if not self._table_exists("ai_course_lesson_attend"):
                    logger.warning("旧表 ai_course_lesson_attend 不存在，跳过同步")
                    return 0, 0

                last_sync_time = self._get_last_sync_time("learn_progress_sync")

                query = text(
                    """
                    SELECT attend_id, lesson_id, course_id, user_id,
                           lesson_updated, lesson_unique_id, status, script_index,
                           script_unique_id, created, updated
                    FROM ai_course_lesson_attend
                    WHERE updated > :last_sync_time
                    ORDER BY updated ASC
                    LIMIT :batch_size
                """
                )

                old_records = db.session.execute(
                    query,
                    {
                        "last_sync_time": last_sync_time,
                        "batch_size": self.sync_batch_size,
                    },
                ).fetchall()

                synced_count = 0
                error_count = 0

                for record in old_records:
                    try:
                        existing_check = db.session.execute(
                            text(
                                """
                            SELECT COUNT(*) FROM learn_progress_records
                            WHERE progress_record_bid = :progress_record_bid
                        """
                            ),
                            {"progress_record_bid": record.attend_id},
                        ).scalar()

                        if existing_check > 0:
                            # 更新现有记录
                            db.session.execute(
                                text(
                                    """
                                UPDATE learn_progress_records
                                SET outline_item_updated = :outline_item_updated,
                                    status = :status,
                                    block_position = :block_position,
                                    updated_at = :updated_at
                                WHERE progress_record_bid = :progress_record_bid
                            """
                                ),
                                {
                                    "outline_item_updated": record.lesson_updated,
                                    "status": self._map_learn_status(record.status),
                                    "block_position": record.script_index,
                                    "updated_at": record.updated,
                                    "progress_record_bid": record.attend_id,
                                },
                            )
                        else:
                            # 创建新记录
                            db.session.execute(
                                text(
                                    """
                                INSERT INTO learn_progress_records
                                (progress_record_bid, shifu_bid, outline_item_bid, user_bid,
                                 outline_item_updated, status, block_position,
                                 deleted, created_at, updated_at)
                                VALUES (:progress_record_bid, :shifu_bid, :outline_item_bid, :user_bid,
                                        :outline_item_updated, :status, :block_position,
                                        0, :created_at, :updated_at)
                            """
                                ),
                                {
                                    "progress_record_bid": record.attend_id,
                                    "shifu_bid": record.course_id,
                                    "outline_item_bid": record.lesson_unique_id
                                    or record.lesson_id,
                                    "user_bid": record.user_id,
                                    "outline_item_updated": record.lesson_updated,
                                    "status": self._map_learn_status(record.status),
                                    "block_position": record.script_index,
                                    "created_at": record.created,
                                    "updated_at": record.updated,
                                },
                            )

                        synced_count += 1

                    except Exception as e:
                        error_count += 1
                        logger.error(f"同步学习进度记录失败 {record.attend_id}: {e}")
                        if error_count > self.max_errors:
                            raise Exception(f"错误次数超过限制: {error_count}")

                db.session.commit()

                if old_records:
                    latest_time = max(record.updated for record in old_records)
                    self._update_sync_time("learn_progress_sync", latest_time)

                logger.info(
                    f"学习进度数据同步完成: {synced_count} 条记录, {error_count} 个错误"
                )
                return synced_count, error_count

            except Exception as e:
                db.session.rollback()
                logger.error(f"学习进度数据同步失败: {e}")
                raise

    def sync_learn_logs_data(self) -> Tuple[int, int]:
        """同步学习日志数据：ai_course_lesson_attendscript -> learn_generated_blocks"""
        with self.app.app_context():
            logger.info("开始同步学习日志数据...")

            try:
                # 检查表是否存在
                if not self._table_exists("learn_generated_blocks"):
                    logger.warning(
                        "新表 learn_generated_blocks 不存在，需要先执行数据库迁移"
                    )
                    return 0, 0

                if not self._table_exists("ai_course_lesson_attendscript"):
                    logger.warning(
                        "旧表 ai_course_lesson_attendscript 不存在，跳过同步"
                    )
                    return 0, 0

                last_sync_time = self._get_last_sync_time("learn_logs_sync")

                query = text(
                    """
                    SELECT log_id, attend_id, script_id, lesson_id, course_id,
                           user_id, script_ui_type, script_ui_conf, interaction_type,
                           script_index, script_role, script_content, status,
                           created, updated
                    FROM ai_course_lesson_attendscript
                    WHERE updated > :last_sync_time
                    ORDER BY updated ASC
                    LIMIT :batch_size
                """
                )

                old_records = db.session.execute(
                    query,
                    {
                        "last_sync_time": last_sync_time,
                        "batch_size": self.sync_batch_size,
                    },
                ).fetchall()

                synced_count = 0
                error_count = 0

                for record in old_records:
                    try:
                        existing_check = db.session.execute(
                            text(
                                """
                            SELECT COUNT(*) FROM learn_generated_blocks
                            WHERE generated_block_bid = :generated_block_bid
                        """
                            ),
                            {"generated_block_bid": record.log_id},
                        ).scalar()

                        if existing_check > 0:
                            # 更新现有记录
                            db.session.execute(
                                text(
                                    """
                                UPDATE learn_generated_blocks
                                SET type = :type, role = :role,
                                    generated_content = :generated_content,
                                    position = :position,
                                    block_content_conf = :block_content_conf,
                                    liked = :liked, status = :status,
                                    updated_at = :updated_at
                                WHERE generated_block_bid = :generated_block_bid
                            """
                                ),
                                {
                                    "type": record.script_ui_type,
                                    "role": record.script_role,
                                    "generated_content": record.script_content,
                                    "position": record.script_index,
                                    "block_content_conf": record.script_ui_conf or "",
                                    "liked": self._map_interaction_type(
                                        record.interaction_type
                                    ),
                                    "status": 1 if record.status == 1 else 0,
                                    "updated_at": record.updated,
                                    "generated_block_bid": record.log_id,
                                },
                            )
                        else:
                            # 创建新记录
                            db.session.execute(
                                text(
                                    """
                                INSERT INTO learn_generated_blocks
                                (generated_block_bid, progress_record_bid, user_bid,
                                 block_bid, outline_item_bid, shifu_bid, type, role,
                                 generated_content, position, block_content_conf, liked,
                                 deleted, status, created_at, updated_at)
                                VALUES (:generated_block_bid, :progress_record_bid, :user_bid,
                                        :block_bid, :outline_item_bid, :shifu_bid, :type, :role,
                                        :generated_content, :position, :block_content_conf, :liked,
                                        0, :status, :created_at, :updated_at)
                            """
                                ),
                                {
                                    "generated_block_bid": record.log_id,
                                    "progress_record_bid": record.attend_id,
                                    "user_bid": record.user_id,
                                    "block_bid": record.script_id,
                                    "outline_item_bid": record.lesson_id,
                                    "shifu_bid": record.course_id,
                                    "type": record.script_ui_type,
                                    "role": record.script_role,
                                    "generated_content": record.script_content,
                                    "position": record.script_index,
                                    "block_content_conf": record.script_ui_conf or "",
                                    "liked": self._map_interaction_type(
                                        record.interaction_type
                                    ),
                                    "status": 1 if record.status == 1 else 0,
                                    "created_at": record.created,
                                    "updated_at": record.updated,
                                },
                            )

                        synced_count += 1

                    except Exception as e:
                        error_count += 1
                        logger.error(f"同步学习日志记录失败 {record.log_id}: {e}")
                        if error_count > self.max_errors:
                            raise Exception(f"错误次数超过限制: {error_count}")

                db.session.commit()

                if old_records:
                    latest_time = max(record.updated for record in old_records)
                    self._update_sync_time("learn_logs_sync", latest_time)

                logger.info(
                    f"学习日志数据同步完成: {synced_count} 条记录, {error_count} 个错误"
                )
                return synced_count, error_count

            except Exception as e:
                db.session.rollback()
                logger.error(f"学习日志数据同步失败: {e}")
                raise

    def verify_data_consistency(self) -> Dict[str, bool]:
        """验证新旧表数据一致性"""
        with self.app.app_context():
            logger.info("开始验证数据一致性...")

            results = {}

            try:
                # 验证订单数据一致性
                if self._table_exists("ai_course_buy_record") and self._table_exists(
                    "order_orders"
                ):
                    old_order_count = db.session.execute(
                        text("SELECT COUNT(*) FROM ai_course_buy_record")
                    ).scalar()
                    new_order_count = db.session.execute(
                        text("SELECT COUNT(*) FROM order_orders WHERE deleted = 0")
                    ).scalar()
                    results["order_count_match"] = old_order_count == new_order_count
                    logger.info(
                        f"订单数量对比 - 旧表: {old_order_count}, 新表: {new_order_count}"
                    )
                else:
                    results["order_count_match"] = False
                    logger.warning("订单表不完整，无法验证")

                # 验证Pingxx订单数据一致性
                if self._table_exists("pingxx_order") and self._table_exists(
                    "order_pingxx_orders"
                ):
                    old_pingxx_count = db.session.execute(
                        text("SELECT COUNT(*) FROM pingxx_order")
                    ).scalar()
                    new_pingxx_count = db.session.execute(
                        text(
                            "SELECT COUNT(*) FROM order_pingxx_orders WHERE deleted = 0"
                        )
                    ).scalar()
                    results["pingxx_order_count_match"] = (
                        old_pingxx_count == new_pingxx_count
                    )
                    logger.info(
                        f"Pingxx订单数量对比 - 旧表: {old_pingxx_count}, 新表: {new_pingxx_count}"
                    )
                else:
                    results["pingxx_order_count_match"] = False
                    logger.warning("Pingxx订单表不完整，无法验证")

                # 验证学习进度数据一致性
                if self._table_exists("ai_course_lesson_attend") and self._table_exists(
                    "learn_progress_records"
                ):
                    old_learn_count = db.session.execute(
                        text("SELECT COUNT(*) FROM ai_course_lesson_attend")
                    ).scalar()
                    new_learn_count = db.session.execute(
                        text(
                            "SELECT COUNT(*) FROM learn_progress_records WHERE deleted = 0"
                        )
                    ).scalar()
                    results["learn_progress_count_match"] = (
                        old_learn_count == new_learn_count
                    )
                    logger.info(
                        f"学习进度数量对比 - 旧表: {old_learn_count}, 新表: {new_learn_count}"
                    )
                else:
                    results["learn_progress_count_match"] = False
                    logger.warning("学习进度表不完整，无法验证")

                # 验证学习日志数据一致性
                if self._table_exists(
                    "ai_course_lesson_attendscript"
                ) and self._table_exists("learn_generated_blocks"):
                    old_logs_count = db.session.execute(
                        text("SELECT COUNT(*) FROM ai_course_lesson_attendscript")
                    ).scalar()
                    new_logs_count = db.session.execute(
                        text(
                            "SELECT COUNT(*) FROM learn_generated_blocks WHERE deleted = 0"
                        )
                    ).scalar()
                    results["learn_logs_count_match"] = old_logs_count == new_logs_count
                    logger.info(
                        f"学习日志数量对比 - 旧表: {old_logs_count}, 新表: {new_logs_count}"
                    )
                else:
                    results["learn_logs_count_match"] = False
                    logger.warning("学习日志表不完整，无法验证")

                logger.info(f"数据一致性验证结果: {results}")
                return results

            except Exception as e:
                logger.error(f"数据一致性验证失败: {e}")
                return {"error": str(e)}

    def run_full_sync(self):
        """执行完整同步"""
        with self.app.app_context():
            logger.info("开始执行完整数据同步...")

            start_time = datetime.now()
            total_synced = 0
            total_errors = 0

            try:
                # 确保同步日志表存在
                self._ensure_sync_log_table()

                # 同步各个表的数据
                sync_results = []

                # 订单数据同步
                order_synced, order_errors = self.sync_order_data()
                sync_results.append(("orders", order_synced, order_errors))

                # Pingxx订单数据同步
                pingxx_synced, pingxx_errors = self.sync_pingxx_order_data()
                sync_results.append(("pingxx_orders", pingxx_synced, pingxx_errors))

                # 学习进度数据同步
                learn_progress_synced, learn_progress_errors = (
                    self.sync_learn_progress_data()
                )
                sync_results.append(
                    ("learn_progress", learn_progress_synced, learn_progress_errors)
                )

                # 学习日志数据同步
                learn_logs_synced, learn_logs_errors = self.sync_learn_logs_data()
                sync_results.append(
                    ("learn_logs", learn_logs_synced, learn_logs_errors)
                )

                # 统计总结果
                total_synced = sum(synced for _, synced, _ in sync_results)
                total_errors = sum(errors for _, _, errors in sync_results)

                # 验证数据一致性
                consistency_results = self.verify_data_consistency()

                end_time = datetime.now()
                duration = end_time - start_time

                logger.info(
                    f"""
                同步任务完成总结:
                - 总同步记录数: {total_synced}
                - 总错误数: {total_errors}
                - 执行时间: {duration}
                - 数据一致性: {consistency_results}
                - 详细结果: {sync_results}
                """
                )

            except Exception as e:
                logger.error(f"完整同步失败: {e}")
                raise

    def _map_order_status(self, old_status: int) -> int:
        """映射旧订单状态到新状态"""
        # 根据业务逻辑映射状态值
        status_mapping = {
            0: 501,  # 未支付 -> init
            1: 502,  # 已支付 -> paid
            2: 503,  # 已退款 -> refunded
            # 添加其他状态映射
        }
        return status_mapping.get(old_status, 501)

    def _map_learn_status(self, old_status: int) -> int:
        """映射旧学习状态到新状态"""
        # 根据 flaskr/service/order/consts.py 中的定义
        status_mapping = {
            0: 601,  # not started -> LEARN_STATUS_NOT_STARTED
            1: 602,  # in progress -> LEARN_STATUS_IN_PROGRESS
            2: 603,  # completed -> LEARN_STATUS_COMPLETED
            # 添加其他状态映射
        }
        return status_mapping.get(old_status, 605)  # 默认为 LEARN_STATUS_LOCKED

    def _map_interaction_type(self, old_interaction: int) -> int:
        """映射旧交互类型到新类型"""
        # 旧: 0-no interaction, 1-like, 2-dislike
        # 新: -1=disliked, 0=not available, 1=liked
        interaction_mapping = {
            0: 0,  # no interaction -> not available
            1: 1,  # like -> liked
            2: -1,  # dislike -> disliked
        }
        return interaction_mapping.get(old_interaction, 0)

    def _table_exists(self, table_name: str) -> bool:
        """检查表是否存在"""
        try:
            result = db.session.execute(
                text(f"SHOW TABLES LIKE '{table_name}'")
            ).fetchone()
            return result is not None
        except Exception as e:
            logger.error(f"检查表存在性失败 {table_name}: {e}")
            return False

    def _get_last_sync_time(self, sync_type: str) -> datetime:
        """获取上次同步时间"""
        try:
            # 先确保同步日志表存在
            self._ensure_sync_log_table()

            result = db.session.execute(
                text(
                    "SELECT sync_time FROM migration_sync_log WHERE sync_type = :type ORDER BY id DESC LIMIT 1"
                ),
                {"type": sync_type},
            ).fetchone()

            if result:
                return result[0]
            else:
                # 如果没有记录，返回一个很早的时间
                return datetime(2020, 1, 1)
        except Exception as e:
            logger.warning(f"获取同步时间失败: {e}")
            # 如果表不存在，返回一个很早的时间
            return datetime(2020, 1, 1)

    def _update_sync_time(self, sync_type: str, sync_time: datetime):
        """更新同步时间"""
        try:
            self._ensure_sync_log_table()

            db.session.execute(
                text(
                    "INSERT INTO migration_sync_log (sync_type, sync_time, created_at) VALUES (:type, :time, NOW())"
                ),
                {"type": sync_type, "time": sync_time},
            )
            db.session.commit()
        except Exception as e:
            logger.warning(f"更新同步时间失败: {e}")

    def _ensure_sync_log_table(self):
        """确保同步日志表存在"""
        try:
            db.session.execute(
                text(
                    """
                CREATE TABLE IF NOT EXISTS migration_sync_log (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    sync_type VARCHAR(50) NOT NULL,
                    sync_time DATETIME NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_sync_type (sync_type),
                    INDEX idx_sync_time (sync_time)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='迁移同步日志表'
            """
                )
            )
            db.session.commit()
        except Exception as e:
            logger.error(f"创建同步日志表失败: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="基于Flask的迁移同步任务")
    parser.add_argument(
        "action",
        choices=["sync", "verify", "init"],
        help="执行动作: sync(执行同步), verify(验证数据), init(初始化)",
    )

    args = parser.parse_args()

    # 创建同步任务实例
    sync_task = FlaskMigrationSync()

    if args.action == "sync":
        sync_task.run_full_sync()
    elif args.action == "verify":
        results = sync_task.verify_data_consistency()
        success = all(v for k, v in results.items() if k != "error")
        sys.exit(0 if success else 1)
    elif args.action == "init":
        with sync_task.app.app_context():
            sync_task._ensure_sync_log_table()
        logger.info("同步日志表初始化完成")
