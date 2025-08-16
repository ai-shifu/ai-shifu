#!/usr/bin/env python3
"""
数据库迁移同步任务
用于在表结构重构期间同步旧表数据到新表，确保平滑迁移
"""

import logging
from datetime import datetime
from typing import Dict, Tuple
from sqlalchemy import text
import sys
import os


from flaskr.service.order.models import Order, PingxxOrder
from flaskr.service.promo.models import Coupon
from flaskr.dao import db

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("/tmp/migration_sync.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class MigrationSyncTask:
    """迁移同步任务类"""

    def __init__(self):
        self.session = db.session
        self.sync_batch_size = 1000
        self.error_count = 0
        self.max_errors = 10

    def sync_order_data(self) -> Tuple[int, int]:
        """同步订单数据：ai_course_buy_record -> order_orders"""
        logger.info("开始同步订单数据...")

        try:
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
                    existing = (
                        self.session.query(Order)
                        .filter(Order.order_bid == record.record_id)
                        .first()
                    )

                    if existing:
                        # 更新现有记录
                        existing.payable_price = record.price
                        existing.paid_price = record.paid_value
                        existing.status = self._map_order_status(record.status)
                        existing.updated_at = record.updated
                        logger.debug(f"更新订单: {record.record_id}")
                    else:
                        # 创建新记录
                        new_order = Order(
                            order_bid=record.record_id,
                            shifu_bid=record.course_id,
                            user_bid=record.user_id,
                            payable_price=record.price,
                            paid_price=record.paid_value,
                            status=self._map_order_status(record.status),
                            deleted=0,
                            created_at=record.created,
                            updated_at=record.updated,
                        )
                        self.session.add(new_order)
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

            logger.info(f"订单数据同步完成: {synced_count} 条记录")
            return synced_count, error_count

        except Exception as e:
            self.session.rollback()
            logger.error(f"订单数据同步失败: {e}")
            raise

    def sync_pingxx_order_data(self) -> Tuple[int, int]:
        """同步Pingxx订单数据：pingxx_order -> order_pingxx_orders"""
        logger.info("开始同步Pingxx订单数据...")

        try:
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
                    existing = (
                        self.session.query(PingxxOrder)
                        .filter(
                            PingxxOrder.transaction_no == record.pingxx_transaction_no
                        )
                        .first()
                    )

                    if existing:
                        # 更新现有记录
                        self._update_pingxx_order(existing, record)
                    else:
                        # 创建新记录
                        new_pingxx_order = PingxxOrder(
                            pingxx_order_bid=record.order_id,
                            user_bid=record.user_id,
                            shifu_bid=record.course_id,
                            order_bid=record.record_id,
                            transaction_no=record.pingxx_transaction_no,
                            app_id=record.pingxx_app_id,
                            channel=record.channel,
                            amount=record.amount,
                            currency=record.currency,
                            subject=record.subject,
                            body=record.body,
                            client_ip=record.client_ip,
                            extra=record.extra,
                            status=record.status,
                            charge_id=record.charge_id,
                            paid_at=record.paid_at,
                            refunded_at=record.refunded_at,
                            closed_at=record.closed_at,
                            failed_at=record.failed_at,
                            refund_id=record.refund_id,
                            failure_code=record.failure_code,
                            failure_msg=record.failure_msg,
                            charge_object=record.charge_object,
                            deleted=0,
                            created_at=record.created,
                            updated_at=record.updated,
                        )
                        self.session.add(new_pingxx_order)

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

            logger.info(f"Pingxx订单数据同步完成: {synced_count} 条记录")
            return synced_count, error_count

        except Exception as e:
            self.session.rollback()
            logger.error(f"Pingxx订单数据同步失败: {e}")
            raise

    def sync_coupon_data(self) -> Tuple[int, int]:
        """同步优惠券数据：discount -> promo_coupons"""
        logger.info("开始同步优惠券数据...")

        try:
            last_sync_time = self._get_last_sync_time("coupon_sync")

            query = text(
                """
                SELECT discount_id, discount_code, discount_type,
                       discount_apply_type, discount_value, discount_limit,
                       discount_start, discount_end, discount_channel,
                       discount_filter, discount_count, discount_used,
                       discount_generated_user, status, created, updated
                FROM discount
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
                    existing = (
                        self.session.query(Coupon)
                        .filter(Coupon.coupon_bid == record.discount_id)
                        .first()
                    )

                    if existing:
                        # 更新现有记录
                        self._update_coupon(existing, record)
                    else:
                        # 创建新记录
                        new_coupon = Coupon(
                            coupon_bid=record.discount_id,
                            code=record.discount_code,
                            discount_type=record.discount_type,
                            usage_type=record.discount_apply_type,
                            value=record.discount_value,
                            start=record.discount_start,
                            end=record.discount_end,
                            channel=record.discount_channel,
                            filter=record.discount_filter,
                            total_count=record.discount_count,
                            used_count=record.discount_used,
                            status=record.status,
                            deleted=0,
                            created_at=record.created,
                            created_user_bid=record.discount_generated_user,
                            updated_at=record.updated,
                        )
                        self.session.add(new_coupon)

                    synced_count += 1

                except Exception as e:
                    error_count += 1
                    logger.error(f"同步优惠券记录失败 {record.discount_id}: {e}")
                    if error_count > self.max_errors:
                        raise Exception(f"错误次数超过限制: {error_count}")

            self.session.commit()

            if old_records:
                latest_time = max(record.updated for record in old_records)
                self._update_sync_time("coupon_sync", latest_time)

            logger.info(f"优惠券数据同步完成: {synced_count} 条记录")
            return synced_count, error_count

        except Exception as e:
            self.session.rollback()
            logger.error(f"优惠券数据同步失败: {e}")
            raise

    def verify_data_consistency(self) -> Dict[str, bool]:
        """验证新旧表数据一致性"""
        logger.info("开始验证数据一致性...")

        results = {}

        try:
            # 验证订单数据一致性
            old_order_count = self.session.execute(
                text("SELECT COUNT(*) FROM ai_course_buy_record")
            ).scalar()
            new_order_count = self.session.query(Order).count()
            results["order_count_match"] = old_order_count == new_order_count

            # 验证Pingxx订单数据一致性
            old_pingxx_count = self.session.execute(
                text("SELECT COUNT(*) FROM pingxx_order")
            ).scalar()
            new_pingxx_count = self.session.query(PingxxOrder).count()
            results["pingxx_order_count_match"] = old_pingxx_count == new_pingxx_count

            # 验证优惠券数据一致性
            old_coupon_count = self.session.execute(
                text("SELECT COUNT(*) FROM discount")
            ).scalar()
            new_coupon_count = self.session.query(Coupon).count()
            results["coupon_count_match"] = old_coupon_count == new_coupon_count

            # 验证关键字段数据一致性（抽样检查）
            results["order_data_integrity"] = self._verify_order_data_integrity()
            results["coupon_data_integrity"] = self._verify_coupon_data_integrity()

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

            # 优惠券数据同步
            coupon_synced, coupon_errors = self.sync_coupon_data()
            sync_results.append(("coupons", coupon_synced, coupon_errors))

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

    def _update_pingxx_order(self, existing, record):
        """更新现有Pingxx订单记录"""
        existing.amount = record.amount
        existing.status = record.status
        existing.charge_id = record.charge_id
        existing.paid_at = record.paid_at
        existing.refunded_at = record.refunded_at
        existing.closed_at = record.closed_at
        existing.failed_at = record.failed_at
        existing.refund_id = record.refund_id
        existing.failure_code = record.failure_code
        existing.failure_msg = record.failure_msg
        existing.charge_object = record.charge_object
        existing.updated_at = record.updated

    def _update_coupon(self, existing, record):
        """更新现有优惠券记录"""
        existing.discount_type = record.discount_type
        existing.usage_type = record.discount_apply_type
        existing.value = record.discount_value
        existing.start = record.discount_start
        existing.end = record.discount_end
        existing.channel = record.discount_channel
        existing.filter = record.discount_filter
        existing.total_count = record.discount_count
        existing.used_count = record.discount_used
        existing.status = record.status
        existing.updated_at = record.updated

    def _get_last_sync_time(self, sync_type: str) -> datetime:
        """获取上次同步时间"""
        try:
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
            self.session.execute(
                text(
                    "INSERT INTO migration_sync_log (sync_type, sync_time, created_at) VALUES (:type, :time, NOW())"
                ),
                {"type": sync_type, "time": sync_time},
            )
            self.session.commit()
        except Exception as e:
            logger.warning(f"更新同步时间失败: {e}")

    def _verify_order_data_integrity(self) -> bool:
        """验证订单数据完整性（抽样检查）"""
        try:
            # 随机抽取10个记录进行验证
            sample_query = text(
                """
                SELECT record_id, price, paid_value
                FROM ai_course_buy_record
                ORDER BY RAND()
                LIMIT 10
            """
            )

            old_samples = self.session.execute(sample_query).fetchall()

            for sample in old_samples:
                new_record = (
                    self.session.query(Order)
                    .filter(Order.order_bid == sample.record_id)
                    .first()
                )

                if not new_record:
                    logger.error(f"新表中缺少订单记录: {sample.record_id}")
                    return False

                if (
                    abs(float(new_record.payable_price) - float(sample.price)) > 0.01
                    or abs(float(new_record.paid_price) - float(sample.paid_value))
                    > 0.01
                ):
                    logger.error(f"订单金额数据不匹配: {sample.record_id}")
                    return False

            return True

        except Exception as e:
            logger.error(f"订单数据完整性验证失败: {e}")
            return False

    def _verify_coupon_data_integrity(self) -> bool:
        """验证优惠券数据完整性（抽样检查）"""
        try:
            sample_query = text(
                """
                SELECT discount_id, discount_code, discount_value
                FROM discount
                ORDER BY RAND()
                LIMIT 10
            """
            )

            old_samples = self.session.execute(sample_query).fetchall()

            for sample in old_samples:
                new_record = (
                    self.session.query(Coupon)
                    .filter(Coupon.coupon_bid == sample.discount_id)
                    .first()
                )

                if not new_record:
                    logger.error(f"新表中缺少优惠券记录: {sample.discount_id}")
                    return False

                if (
                    new_record.code != sample.discount_code
                    or abs(float(new_record.value) - float(sample.discount_value))
                    > 0.01
                ):
                    logger.error(f"优惠券数据不匹配: {sample.discount_id}")
                    return False

            return True

        except Exception as e:
            logger.error(f"优惠券数据完整性验证失败: {e}")
            return False


def create_sync_log_table():
    """创建同步日志表"""
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
        logger.info("同步日志表创建成功")
    except Exception as e:
        logger.error(f"创建同步日志表失败: {e}")


if __name__ == "__main__":
    # 创建同步日志表
    create_sync_log_table()

    # 创建同步任务实例
    sync_task = MigrationSyncTask()

    # 执行完整同步
    sync_task.run_full_sync()
