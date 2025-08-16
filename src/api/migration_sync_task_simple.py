#!/usr/bin/env python3
"""
简化版数据库迁移同步任务
用于在表结构重构期间同步旧表数据到新表，确保平滑迁移
"""

import logging
from datetime import datetime
from typing import Dict, Tuple
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("/tmp/migration_sync.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class SimpleMigrationSync:
    """简化版迁移同步任务类"""

    def __init__(self, database_url=None):
        if database_url is None:
            database_url = os.getenv(
                "DATABASE_URL", "mysql+pymysql://root:@localhost/ai_shifu"
            )

        # 确保使用 PyMySQL 驱动
        if database_url.startswith("mysql://"):
            database_url = database_url.replace("mysql://", "mysql+pymysql://")

        self.engine = create_engine(database_url, echo=False)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        self.sync_batch_size = 1000
        self.error_count = 0
        self.max_errors = 10

        logger.info(f"初始化同步任务，数据库: {database_url}")

    def sync_order_data(self) -> Tuple[int, int]:
        """同步订单数据：ai_course_buy_record -> order_orders"""
        logger.info("开始同步订单数据...")

        try:
            # 首先检查表是否存在
            if not self._table_exists("order_orders"):
                logger.warning("新表 order_orders 不存在，跳过同步")
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

            old_records = self.session.execute(
                query,
                {"last_sync_time": last_sync_time, "batch_size": self.sync_batch_size},
            ).fetchall()

            synced_count = 0
            error_count = 0

            for record in old_records:
                try:
                    # 检查新表中是否已存在
                    existing_check = self.session.execute(
                        text(
                            """
                        SELECT COUNT(*) FROM order_orders WHERE order_bid = :order_bid
                    """
                        ),
                        {"order_bid": record.record_id},
                    ).scalar()

                    if existing_check > 0:
                        # 更新现有记录
                        self.session.execute(
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
                        self.session.execute(
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
            self.session.commit()

            # 更新同步时间戳
            if old_records:
                latest_time = max(record.updated for record in old_records)
                self._update_sync_time("order_sync", latest_time)

            logger.info(
                f"订单数据同步完成: {synced_count} 条记录, {error_count} 个错误"
            )
            return synced_count, error_count

        except Exception as e:
            self.session.rollback()
            logger.error(f"订单数据同步失败: {e}")
            raise

    def sync_pingxx_order_data(self) -> Tuple[int, int]:
        """同步Pingxx订单数据：pingxx_order -> order_pingxx_orders"""
        logger.info("开始同步Pingxx订单数据...")

        try:
            # 检查表是否存在
            if not self._table_exists("order_pingxx_orders"):
                logger.warning("新表 order_pingxx_orders 不存在，跳过同步")
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

            old_records = self.session.execute(
                query,
                {"last_sync_time": last_sync_time, "batch_size": self.sync_batch_size},
            ).fetchall()

            synced_count = 0
            error_count = 0

            for record in old_records:
                try:
                    existing_check = self.session.execute(
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
                        self.session.execute(
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
                        self.session.execute(
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

            self.session.commit()

            if old_records:
                latest_time = max(record.updated for record in old_records)
                self._update_sync_time("pingxx_order_sync", latest_time)

            logger.info(
                f"Pingxx订单数据同步完成: {synced_count} 条记录, {error_count} 个错误"
            )
            return synced_count, error_count

        except Exception as e:
            self.session.rollback()
            logger.error(f"Pingxx订单数据同步失败: {e}")
            raise

    def verify_data_consistency(self) -> Dict[str, bool]:
        """验证新旧表数据一致性"""
        logger.info("开始验证数据一致性...")

        results = {}

        try:
            # 验证订单数据一致性
            if self._table_exists("ai_course_buy_record") and self._table_exists(
                "order_orders"
            ):
                old_order_count = self.session.execute(
                    text("SELECT COUNT(*) FROM ai_course_buy_record")
                ).scalar()
                new_order_count = self.session.execute(
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
                old_pingxx_count = self.session.execute(
                    text("SELECT COUNT(*) FROM pingxx_order")
                ).scalar()
                new_pingxx_count = self.session.execute(
                    text("SELECT COUNT(*) FROM order_pingxx_orders WHERE deleted = 0")
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

            logger.info(f"数据一致性验证结果: {results}")
            return results

        except Exception as e:
            logger.error(f"数据一致性验证失败: {e}")
            return {"error": str(e)}

    def run_full_sync(self):
        """执行完整同步"""
        logger.info("开始执行完整数据同步...")

        start_time = datetime.now()
        total_synced = 0
        total_errors = 0

        try:
            # 同步各个表的数据
            sync_results = []

            # 订单数据同步
            order_synced, order_errors = self.sync_order_data()
            sync_results.append(("orders", order_synced, order_errors))

            # Pingxx订单数据同步
            pingxx_synced, pingxx_errors = self.sync_pingxx_order_data()
            sync_results.append(("pingxx_orders", pingxx_synced, pingxx_errors))

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

    def _table_exists(self, table_name: str) -> bool:
        """检查表是否存在"""
        try:
            result = self.session.execute(
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

            result = self.session.execute(
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

            self.session.execute(
                text(
                    "INSERT INTO migration_sync_log (sync_type, sync_time, created_at) VALUES (:type, :time, NOW())"
                ),
                {"type": sync_type, "time": sync_time},
            )
            self.session.commit()
        except Exception as e:
            logger.warning(f"更新同步时间失败: {e}")

    def _ensure_sync_log_table(self):
        """确保同步日志表存在"""
        try:
            self.session.execute(
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
            self.session.commit()
        except Exception as e:
            logger.error(f"创建同步日志表失败: {e}")

    def close(self):
        """关闭数据库连接"""
        if self.session:
            self.session.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="简化版迁移同步任务")
    parser.add_argument(
        "action",
        choices=["sync", "verify"],
        help="执行动作: sync(执行同步), verify(验证数据)",
    )
    parser.add_argument("--database-url", type=str, help="数据库连接字符串")

    args = parser.parse_args()

    # 创建同步任务实例
    sync_task = SimpleMigrationSync(args.database_url)

    try:
        if args.action == "sync":
            sync_task.run_full_sync()
        elif args.action == "verify":
            results = sync_task.verify_data_consistency()
            success = all(v for k, v in results.items() if k != "error")
            sys.exit(0 if success else 1)
    finally:
        sync_task.close()
