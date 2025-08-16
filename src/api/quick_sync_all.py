#!/usr/bin/env python3
"""
快速同步所有数据脚本
"""

import time
from migration_sync_flask import FlaskMigrationSync


def main():
    sync_task = FlaskMigrationSync()

    print("开始快速同步所有数据...")
    print("=" * 50)

    max_rounds = 200  # 最多同步200轮
    round_count = 0

    while round_count < max_rounds:
        round_count += 1
        print(f"\n第 {round_count} 轮同步:")

        try:
            # 执行同步
            with sync_task.app.app_context():
                # 记录同步前的状态
                start_time = time.time()

                # 同步各个表
                order_synced, order_errors = sync_task.sync_order_data()
                pingxx_synced, pingxx_errors = sync_task.sync_pingxx_order_data()
                learn_progress_synced, learn_progress_errors = (
                    sync_task.sync_learn_progress_data()
                )
                learn_logs_synced, learn_logs_errors = sync_task.sync_learn_logs_data()

                total_synced = (
                    order_synced
                    + pingxx_synced
                    + learn_progress_synced
                    + learn_logs_synced
                )
                total_errors = (
                    order_errors
                    + pingxx_errors
                    + learn_progress_errors
                    + learn_logs_errors
                )

                end_time = time.time()
                duration = end_time - start_time

                print(
                    f"  订单: +{order_synced}, Pingxx: +{pingxx_synced}, 学习进度: +{learn_progress_synced}, 学习日志: +{learn_logs_synced}"
                )
                print(
                    f"  本轮同步: {total_synced} 条记录, {total_errors} 个错误, 耗时: {duration:.2f}秒"
                )

                # 如果没有新数据同步，说明已经完成
                if total_synced == 0:
                    print("\n✅ 所有数据同步完成！")
                    break

                # 每5轮检查一次数据一致性
                if round_count % 5 == 0:
                    print("\n检查数据一致性...")
                    results = sync_task.verify_data_consistency()

                    all_match = all(v for k, v in results.items() if k != "error")
                    if all_match:
                        print("✅ 数据一致性检查通过！")
                        break
                    else:
                        print("⚠️  数据还未完全一致，继续同步...")

        except Exception as e:
            print(f"❌ 第 {round_count} 轮同步失败: {e}")
            break

        # 短暂休息
        time.sleep(0.5)

    print("\n" + "=" * 50)
    print("最终验证...")

    try:
        results = sync_task.verify_data_consistency()
        print("\n最终数据一致性结果:")
        for key, value in results.items():
            if key != "error":
                status = "✅" if value else "❌"
                print(f"  {status} {key}: {value}")

        all_match = all(v for k, v in results.items() if k != "error")
        if all_match:
            print("\n🎉 恭喜！所有数据同步完成，数据一致性检查通过！")
        else:
            print("\n⚠️  数据同步基本完成，但还有部分数据需要继续同步")

    except Exception as e:
        print(f"❌ 最终验证失败: {e}")


if __name__ == "__main__":
    main()
