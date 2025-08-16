#!/usr/bin/env python3
"""
数据库迁移回滚工具
提供紧急回滚和数据恢复功能
"""

import os
import sys
import logging
import argparse
from sqlalchemy import text
from app import create_app
from flaskr.dao import db

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("/tmp/migration_rollback.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class MigrationRollback:
    """迁移回滚工具类"""

    def __init__(self):
        self.app = create_app()
        self.session = db.session

    def emergency_rollback(self, backup_file=None):
        """紧急回滚到旧表结构"""
        logger.info("开始执行紧急回滚...")

        with self.app.app_context():
            try:
                # 1. 停止所有新表的写入操作
                self._disable_new_table_writes()

                # 2. 如果提供了备份文件，恢复数据
                if backup_file:
                    self._restore_from_backup(backup_file)

                # 3. 同步新表数据回旧表（如果有新数据）
                self._sync_new_data_to_old_tables()

                # 4. 验证旧表数据完整性
                self._verify_old_table_integrity()

                logger.info("紧急回滚完成")
                return True

            except Exception as e:
                logger.error(f"紧急回滚失败: {e}")
                return False

    def sync_new_to_old(self):
        """将新表数据同步回旧表"""
        logger.info("开始将新表数据同步回旧表...")

        with self.app.app_context():
            try:
                # 同步订单数据
                self._sync_orders_to_old()

                # 同步Pingxx订单数据
                self._sync_pingxx_orders_to_old()

                # 同步优惠券数据
                self._sync_coupons_to_old()

                logger.info("新表数据同步回旧表完成")
                return True

            except Exception as e:
                logger.error(f"新表数据同步回旧表失败: {e}")
                return False

    def verify_rollback(self):
        """验证回滚后数据完整性"""
        logger.info("验证回滚后数据完整性...")

        with self.app.app_context():
            try:
                results = {}

                # 验证旧表数据完整性
                results["old_tables_integrity"] = self._verify_old_table_integrity()

                # 验证业务功能
                results["business_functions"] = self._verify_business_functions()

                # 验证数据一致性
                results["data_consistency"] = self._verify_data_after_rollback()

                logger.info(f"回滚验证结果: {results}")
                return all(results.values())

            except Exception as e:
                logger.error(f"回滚验证失败: {e}")
                return False

    def _disable_new_table_writes(self):
        """禁用新表写入（通过配置或标志位）"""
        try:
            # 这里可以通过配置文件、环境变量或数据库标志位来控制
            # 示例：设置一个全局标志
            self.session.execute(
                text(
                    """
                INSERT INTO system_config (config_key, config_value, updated_at)
                VALUES ('migration_rollback_mode', '1', NOW())
                ON DUPLICATE KEY UPDATE config_value = '1', updated_at = NOW()
            """
                )
            )
            self.session.commit()

            logger.info("已禁用新表写入")

        except Exception as e:
            logger.warning(f"禁用新表写入失败: {e}")

    def _restore_from_backup(self, backup_file):
        """从备份文件恢复数据"""
        try:
            import subprocess

            logger.info(f"从备份文件恢复数据: {backup_file}")

            # 获取数据库配置
            db_url = os.getenv("DATABASE_URL", "")
            if not db_url:
                raise Exception("DATABASE_URL 环境变量未设置")

            # 解析数据库连接信息
            # mysql://user:password@host:port/database
            import re

            match = re.match(r"mysql://([^:]+):([^@]+)@([^:]+):?(\d+)?/(.+)", db_url)
            if not match:
                raise Exception("无法解析数据库连接字符串")

            user, password, host, port, database = match.groups()
            port = port or "3306"

            # 执行恢复命令
            cmd = f"mysql -h {host} -P {port} -u {user} -p{password} {database} < {backup_file}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if result.returncode != 0:
                raise Exception(f"备份恢复失败: {result.stderr}")

            logger.info("备份恢复完成")

        except Exception as e:
            logger.error(f"备份恢复失败: {e}")
            raise

    def _sync_orders_to_old(self):
        """同步订单数据到旧表"""
        try:
            # 查询新表中不在旧表的数据
            new_orders = self.session.execute(
                text(
                    """
                SELECT o.order_bid, o.shifu_bid, o.user_bid, o.payable_price,
                       o.paid_price, o.status, o.created_at, o.updated_at
                FROM order_orders o
                LEFT JOIN ai_course_buy_record a ON o.order_bid = a.record_id
                WHERE a.record_id IS NULL AND o.deleted = 0
            """
                )
            ).fetchall()

            synced_count = 0

            for order in new_orders:
                # 映射状态
                old_status = self._map_new_order_status_to_old(order.status)

                # 插入到旧表
                self.session.execute(
                    text(
                        """
                    INSERT INTO ai_course_buy_record
                    (record_id, course_id, user_id, price, pay_value,
                     discount_value, paid_value, status, created, updated)
                    VALUES (:record_id, :course_id, :user_id, :price, :pay_value,
                            0.00, :paid_value, :status, :created, :updated)
                """
                    ),
                    {
                        "record_id": order.order_bid,
                        "course_id": order.shifu_bid,
                        "user_id": order.user_bid,
                        "price": order.payable_price,
                        "pay_value": order.payable_price,
                        "paid_value": order.paid_price,
                        "status": old_status,
                        "created": order.created_at,
                        "updated": order.updated_at,
                    },
                )

                synced_count += 1

            self.session.commit()
            logger.info(f"订单数据同步到旧表完成: {synced_count} 条记录")

        except Exception as e:
            self.session.rollback()
            logger.error(f"订单数据同步到旧表失败: {e}")
            raise

    def _sync_pingxx_orders_to_old(self):
        """同步Pingxx订单数据到旧表"""
        try:
            # 查询新表中不在旧表的数据
            new_pingxx_orders = self.session.execute(
                text(
                    """
                SELECT p.pingxx_order_bid, p.user_bid, p.shifu_bid, p.order_bid,
                       p.transaction_no, p.app_id, p.channel, p.amount, p.currency,
                       p.subject, p.body, p.client_ip, p.extra, p.status,
                       p.charge_id, p.paid_at, p.refunded_at, p.closed_at,
                       p.failed_at, p.refund_id, p.failure_code, p.failure_msg,
                       p.charge_object, p.created_at, p.updated_at
                FROM order_pingxx_orders p
                LEFT JOIN pingxx_order o ON p.transaction_no = o.pingxx_transaction_no
                WHERE o.pingxx_transaction_no IS NULL AND p.deleted = 0
            """
                )
            ).fetchall()

            synced_count = 0

            for pingxx_order in new_pingxx_orders:
                # 插入到旧表
                self.session.execute(
                    text(
                        """
                    INSERT INTO pingxx_order
                    (order_id, user_id, course_id, record_id, pingxx_transaction_no,
                     pingxx_app_id, pingxx_channel, pingxx_id, channel, amount,
                     currency, subject, body, order_no, client_ip, extra,
                     status, charge_id, paid_at, refunded_at, closed_at,
                     failed_at, refund_id, failure_code, failure_msg,
                     charge_object, created, updated)
                    VALUES (:order_id, :user_id, :course_id, :record_id, :transaction_no,
                            :app_id, :channel, '', :channel, :amount,
                            :currency, :subject, :body, :transaction_no, :client_ip, :extra,
                            :status, :charge_id, :paid_at, :refunded_at, :closed_at,
                            :failed_at, :refund_id, :failure_code, :failure_msg,
                            :charge_object, :created, :updated)
                """
                    ),
                    {
                        "order_id": pingxx_order.pingxx_order_bid,
                        "user_id": pingxx_order.user_bid,
                        "course_id": pingxx_order.shifu_bid,
                        "record_id": pingxx_order.order_bid,
                        "transaction_no": pingxx_order.transaction_no,
                        "app_id": pingxx_order.app_id,
                        "channel": pingxx_order.channel,
                        "amount": pingxx_order.amount,
                        "currency": pingxx_order.currency,
                        "subject": pingxx_order.subject,
                        "body": pingxx_order.body,
                        "client_ip": pingxx_order.client_ip,
                        "extra": pingxx_order.extra,
                        "status": pingxx_order.status,
                        "charge_id": pingxx_order.charge_id,
                        "paid_at": pingxx_order.paid_at,
                        "refunded_at": pingxx_order.refunded_at,
                        "closed_at": pingxx_order.closed_at,
                        "failed_at": pingxx_order.failed_at,
                        "refund_id": pingxx_order.refund_id,
                        "failure_code": pingxx_order.failure_code,
                        "failure_msg": pingxx_order.failure_msg,
                        "charge_object": pingxx_order.charge_object,
                        "created": pingxx_order.created_at,
                        "updated": pingxx_order.updated_at,
                    },
                )

                synced_count += 1

            self.session.commit()
            logger.info(f"Pingxx订单数据同步到旧表完成: {synced_count} 条记录")

        except Exception as e:
            self.session.rollback()
            logger.error(f"Pingxx订单数据同步到旧表失败: {e}")
            raise

    def _sync_coupons_to_old(self):
        """同步优惠券数据到旧表"""
        try:
            # 查询新表中不在旧表的数据
            new_coupons = self.session.execute(
                text(
                    """
                SELECT c.coupon_bid, c.code, c.discount_type, c.usage_type,
                       c.value, c.start, c.end, c.channel, c.filter,
                       c.total_count, c.used_count, c.status, c.created_at,
                       c.created_user_bid, c.updated_at
                FROM promo_coupons c
                LEFT JOIN discount d ON c.coupon_bid = d.discount_id
                WHERE d.discount_id IS NULL AND c.deleted = 0
            """
                )
            ).fetchall()

            synced_count = 0

            for coupon in new_coupons:
                # 插入到旧表
                self.session.execute(
                    text(
                        """
                    INSERT INTO discount
                    (discount_id, discount_code, discount_type, discount_apply_type,
                     discount_value, discount_limit, discount_start, discount_end,
                     discount_channel, discount_filter, discount_count, discount_used,
                     discount_generated_user, status, created, updated)
                    VALUES (:discount_id, :discount_code, :discount_type, :discount_apply_type,
                            :discount_value, 0.00, :discount_start, :discount_end,
                            :discount_channel, :discount_filter, :discount_count, :discount_used,
                            :discount_generated_user, :status, :created, :updated)
                """
                    ),
                    {
                        "discount_id": coupon.coupon_bid,
                        "discount_code": coupon.code,
                        "discount_type": coupon.discount_type,
                        "discount_apply_type": coupon.usage_type,
                        "discount_value": coupon.value,
                        "discount_start": coupon.start,
                        "discount_end": coupon.end,
                        "discount_channel": coupon.channel,
                        "discount_filter": coupon.filter,
                        "discount_count": coupon.total_count,
                        "discount_used": coupon.used_count,
                        "discount_generated_user": coupon.created_user_bid,
                        "status": coupon.status,
                        "created": coupon.created_at,
                        "updated": coupon.updated_at,
                    },
                )

                synced_count += 1

            self.session.commit()
            logger.info(f"优惠券数据同步到旧表完成: {synced_count} 条记录")

        except Exception as e:
            self.session.rollback()
            logger.error(f"优惠券数据同步到旧表失败: {e}")
            raise

    def _map_new_order_status_to_old(self, new_status):
        """映射新订单状态到旧状态"""
        status_mapping = {
            501: 0,  # init -> 未支付
            502: 1,  # paid -> 已支付
            503: 2,  # refunded -> 已退款
            504: 0,  # unpaid -> 未支付
            505: 0,  # timeout -> 未支付
        }
        return status_mapping.get(new_status, 0)

    def _verify_old_table_integrity(self):
        """验证旧表数据完整性"""
        try:
            # 检查旧表是否存在
            tables_to_check = [
                "ai_course_buy_record",
                "pingxx_order",
                "discount",
                "discount_record",
            ]

            for table in tables_to_check:
                result = self.session.execute(
                    text(f"SHOW TABLES LIKE '{table}'")
                ).fetchone()
                if not result:
                    logger.error(f"旧表 {table} 不存在")
                    return False

                # 检查表结构
                count = self.session.execute(
                    text(f"SELECT COUNT(*) FROM {table}")
                ).scalar()
                logger.info(f"表 {table} 记录数: {count}")

            return True

        except Exception as e:
            logger.error(f"旧表完整性验证失败: {e}")
            return False

    def _verify_business_functions(self):
        """验证关键业务功能"""
        try:
            # 测试订单查询
            order_count = self.session.execute(
                text("SELECT COUNT(*) FROM ai_course_buy_record WHERE status = 1")
            ).scalar()

            # 测试优惠券查询
            coupon_count = self.session.execute(
                text("SELECT COUNT(*) FROM discount WHERE status = 1")
            ).scalar()

            logger.info(
                f"业务功能验证 - 已支付订单: {order_count}, 活跃优惠券: {coupon_count}"
            )
            return True

        except Exception as e:
            logger.error(f"业务功能验证失败: {e}")
            return False

    def _verify_data_after_rollback(self):
        """验证回滚后数据一致性"""
        try:
            # 这里可以添加具体的数据一致性检查逻辑
            # 例如：检查关键业务数据是否正确

            # 检查订单总数
            total_orders = self.session.execute(
                text("SELECT COUNT(*) FROM ai_course_buy_record")
            ).scalar()

            # 检查支付订单金额
            total_amount = (
                self.session.execute(
                    text(
                        "SELECT SUM(paid_value) FROM ai_course_buy_record WHERE status = 1"
                    )
                ).scalar()
                or 0
            )

            logger.info(
                f"回滚后数据 - 总订单数: {total_orders}, 总支付金额: {total_amount}"
            )

            return total_orders > 0

        except Exception as e:
            logger.error(f"回滚后数据一致性验证失败: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(description="数据库迁移回滚工具")
    parser.add_argument(
        "action",
        choices=["emergency", "sync-back", "verify"],
        help="执行动作: emergency(紧急回滚), sync-back(同步新数据回旧表), verify(验证回滚)",
    )
    parser.add_argument("--backup", type=str, help="备份文件路径（用于紧急回滚）")

    args = parser.parse_args()

    rollback = MigrationRollback()

    if args.action == "emergency":
        success = rollback.emergency_rollback(args.backup)
        sys.exit(0 if success else 1)
    elif args.action == "sync-back":
        success = rollback.sync_new_to_old()
        sys.exit(0 if success else 1)
    elif args.action == "verify":
        success = rollback.verify_rollback()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
