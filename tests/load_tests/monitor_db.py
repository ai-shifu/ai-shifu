"""
Database monitoring script to detect locks and timeouts during load testing.
This script connects to MySQL and Redis to monitor for locks and connection issues.
"""

import time
import subprocess
import argparse
import logging
import re
import os
import signal
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("db_monitor.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

MYSQL_HOST = "localhost"
MYSQL_USER = "root"
MYSQL_PASSWORD = ""
MYSQL_DATABASE = "ai_shifu"

REDIS_HOST = "localhost"
REDIS_PORT = 6379


class DatabaseMonitor:
    def __init__(self, interval=5):
        """初始化监控器"""
        self.interval = interval  # 监控间隔（秒）
        self.running = False
        self.lock_count = 0
        self.timeout_count = 0
        self.start_time = None
        self.mysql_cmd_base = f"mysql -h {MYSQL_HOST} -u {MYSQL_USER}"
        if MYSQL_PASSWORD:
            self.mysql_cmd_base += f" -p{MYSQL_PASSWORD}"
        self.mysql_cmd_base += f" {MYSQL_DATABASE}"

    def start(self):
        """开始监控"""
        self.running = True
        self.start_time = datetime.now()
        logger.info(f"Starting database monitoring at {self.start_time}")

        try:
            while self.running:
                self.check_mysql_locks()
                self.check_redis_locks()
                time.sleep(self.interval)
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
        finally:
            self.stop()

    def stop(self):
        """停止监控"""
        self.running = False
        end_time = datetime.now()
        duration = (
            (end_time - self.start_time).total_seconds() if self.start_time else 0
        )

        logger.info(f"Monitoring stopped at {end_time}")
        logger.info(f"Total duration: {duration:.2f} seconds")
        logger.info(
            f"Detected {self.lock_count} locks and {self.timeout_count} timeouts"
        )

    def check_mysql_locks(self):
        """检查MySQL锁和超时"""
        try:
            cmd = f"{self.mysql_cmd_base} -e 'SHOW ENGINE INNODB STATUS\\G'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if result.returncode == 0:
                output = result.stdout

                if "DEADLOCK" in output:
                    self.lock_count += 1
                    logger.warning("MySQL deadlock detected!")
                    deadlock_section = re.search(
                        r"LATEST DETECTED DEADLOCK(.*?)TRANSACTIONS", output, re.DOTALL
                    )
                    if deadlock_section:
                        logger.warning(f"Deadlock details: {deadlock_section.group(1)}")

                if "lock wait timeout" in output.lower():
                    self.timeout_count += 1
                    logger.warning("MySQL lock wait timeout detected!")

            cmd = f"{self.mysql_cmd_base} -e 'SELECT * FROM information_schema.innodb_trx\\G'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if result.returncode == 0:
                output = result.stdout
                trx_count = output.count("trx_id")
                if trx_count > 5:  # 如果有大量事务，可能表示问题
                    logger.warning(f"High number of active transactions: {trx_count}")

            cmd = f"{self.mysql_cmd_base} -e 'SHOW PROCESSLIST'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if result.returncode == 0:
                output = result.stdout
                long_queries = [
                    line
                    for line in output.split("\n")
                    if "Time" in line and re.search(r"Time:\s+[3-9][0-9]+", line)
                ]
                if long_queries:
                    logger.warning(
                        f"Long running queries detected: {len(long_queries)}"
                    )
                    for query in long_queries[:3]:  # 只记录前3个
                        logger.warning(f"Long query: {query}")

        except Exception as e:
            logger.error(f"Error checking MySQL locks: {str(e)}")

    def check_redis_locks(self):
        """检查Redis锁"""
        try:
            cmd = f"redis-cli -h {REDIS_HOST} -p {REDIS_PORT} keys '*lock*'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if result.returncode == 0:
                output = result.stdout
                lock_keys = output.strip().split("\n")
                lock_keys = [k for k in lock_keys if k]  # 过滤空行

                if len(lock_keys) > 5:  # 如果有大量锁，可能表示问题
                    logger.warning(f"High number of Redis locks: {len(lock_keys)}")
                    for key in lock_keys[:5]:  # 只记录前5个
                        logger.warning(f"Redis lock key: {key}")

                        ttl_cmd = f"redis-cli -h {REDIS_HOST} -p {REDIS_PORT} ttl {key}"
                        ttl_result = subprocess.run(
                            ttl_cmd, shell=True, capture_output=True, text=True
                        )
                        if ttl_result.returncode == 0:
                            ttl = ttl_result.stdout.strip()
                            logger.warning(f"Lock TTL: {ttl}")

        except Exception as e:
            logger.error(f"Error checking Redis locks: {str(e)}")


def signal_handler(sig, frame):
    """处理信号以优雅地停止监控"""
    logger.info("Received signal to stop monitoring")
    sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor database locks and timeouts")
    parser.add_argument(
        "--interval", type=int, default=5, help="Monitoring interval in seconds"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=0,
        help="Total monitoring duration in seconds (0 for indefinite)",
    )
    args = parser.parse_args()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    monitor = DatabaseMonitor(interval=args.interval)

    if args.duration > 0:
        logger.info(f"Will monitor for {args.duration} seconds")
        try:
            monitor.start()
            time.sleep(args.duration)
            monitor.stop()
        except KeyboardInterrupt:
            pass
    else:
        monitor.start()
