#!/usr/bin/env python3
"""
迁移同步任务调度器
支持定时执行、手动执行、监控等功能
"""

import os
import sys
import time
import signal
import argparse
import schedule
from datetime import datetime
from app import create_app
from migration_sync_task import MigrationSyncTask, create_sync_log_table


# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class MigrationSyncScheduler:
    """迁移同步调度器"""

    def __init__(self):
        self.app = create_app()
        self.running = False
        self.sync_task = None

        # 注册信号处理器
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """处理停止信号"""
        print(f"\n收到停止信号 {signum}，正在优雅关闭...")
        self.running = False

    def _execute_sync(self):
        """执行同步任务"""
        with self.app.app_context():
            try:
                print(f"[{datetime.now()}] 开始执行同步任务...")

                if not self.sync_task:
                    self.sync_task = MigrationSyncTask()

                self.sync_task.run_full_sync()
                print(f"[{datetime.now()}] 同步任务执行完成")

            except Exception as e:
                print(f"[{datetime.now()}] 同步任务执行失败: {e}")

    def start_scheduler(self, interval_minutes=30):
        """启动定时调度器"""
        print(f"启动迁移同步调度器，间隔: {interval_minutes} 分钟")

        # 设置定时任务
        schedule.every(interval_minutes).minutes.do(self._execute_sync)

        # 立即执行一次
        self._execute_sync()

        self.running = True

        # 调度循环
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(10)  # 每10秒检查一次
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"调度器异常: {e}")
                time.sleep(60)  # 异常后等待1分钟再继续

        print("迁移同步调度器已停止")

    def run_once(self):
        """手动执行一次同步"""
        print("手动执行迁移同步任务...")
        with self.app.app_context():
            self._execute_sync()

    def verify_data(self):
        """验证数据一致性"""
        print("验证数据一致性...")
        with self.app.app_context():
            try:
                sync_task = MigrationSyncTask()
                results = sync_task.verify_data_consistency()

                print("数据一致性验证结果:")
                for key, value in results.items():
                    status = "✓" if value else "✗"
                    print(f"  {status} {key}: {value}")

                return all(results.values())

            except Exception as e:
                print(f"数据验证失败: {e}")
                return False

    def init_sync_tables(self):
        """初始化同步相关表"""
        print("初始化同步日志表...")
        with self.app.app_context():
            create_sync_log_table()
            print("同步日志表初始化完成")


def main():
    parser = argparse.ArgumentParser(description="迁移同步任务管理器")
    parser.add_argument(
        "action",
        choices=["start", "once", "verify", "init"],
        help="执行动作: start(启动调度器), once(执行一次), verify(验证数据), init(初始化)",
    )
    parser.add_argument(
        "--interval", type=int, default=30, help="调度间隔（分钟，默认30分钟）"
    )

    args = parser.parse_args()

    scheduler = MigrationSyncScheduler()

    if args.action == "start":
        scheduler.start_scheduler(args.interval)
    elif args.action == "once":
        scheduler.run_once()
    elif args.action == "verify":
        success = scheduler.verify_data()
        sys.exit(0 if success else 1)
    elif args.action == "init":
        scheduler.init_sync_tables()


if __name__ == "__main__":
    main()
